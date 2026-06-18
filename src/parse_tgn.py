"""
parse_tgn.py — Convierte un export CSV de The Guide Network (TGN) en el dict
de datos que consume el dashboard, para un lodge de temporada nov–abr (RHL, AP).

Lógica validada a mano sobre los exports reales. Maneja:
  - separador ';' o ',' (autodetección)
  - fechas en formato d/m/Y
  - estados: 'Confirmada con sena' / 'Confirmada Sin Sena' / 'Tentativa'
  - KPIs = solo confirmadas (con + sin seña); tentativas van aparte
  - pacing semanal reconstruido desde 'Created On' de las confirmadas

La REFERENCIA del año pasado (refBN, refRev, p[] por mes) NO se recalcula acá:
es una temporada cerrada, va fija en config.yaml por lodge.
"""
from __future__ import annotations
import csv, io, math, datetime as dt
from collections import defaultdict

# meses de la temporada nov–abr, en orden, con su etiqueta
SEASON_MONTHS = [(11, "Nov"), (12, "Dic"), (1, "Ene"), (2, "Feb"), (3, "Mar"), (4, "Abr")]

# nombres de columna esperados (se normalizan a minúscula sin espacios para matchear)
COLS = {
    "status": ["status"],
    "start": ["start date", "startdate"],
    "guests": ["guest count", "guestcount", "guests"],
    "bn": ["bed nights", "bednights"],
    "price": ["total price", "totalprice", "price"],
    "paid": ["total paid", "totalpaid", "paid"],
    "balance": ["balance due", "balancedue", "balance"],
    "created": ["created on", "createdon", "created"],
    "source": ["source"],
}


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("_", " ")


def _detect_delimiter(text: str) -> str:
    head = text.splitlines()[0] if text else ""
    return ";" if head.count(";") >= head.count(",") else ","


def _colmap(header: list[str]) -> dict:
    norm = [_norm(h) for h in header]
    out = {}
    for key, aliases in COLS.items():
        for i, h in enumerate(norm):
            if h in aliases:
                out[key] = i
                break
    missing = [k for k in ("status", "start", "guests", "bn") if k not in out]
    if missing:
        raise ValueError(f"Faltan columnas esperadas en el CSV: {missing} (header={header})")
    return out


def _to_float(v) -> float:
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _parse_date(v) -> dt.date | None:
    v = (v or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _status_bucket(status: str) -> str:
    s = _norm(status)
    if "tentativ" in s:
        return "t"
    if "con sena" in s or "con seña" in s:
        return "cs"
    if "sin sena" in s or "sin seña" in s:
        return "cn"
    return "t"  # desconocido => tratar como tentativa (no suma a confirmado)


def parse_tgn_csv(csv_bytes: bytes, *, anchor_date: dt.date, week_now: int,
                  ref: dict, meta: dict, season_months: list | None = None,
                  known_sources: dict | None = None) -> dict:
    """
    csv_bytes  : contenido del CSV de TGN (temporada corriente)
    anchor_date: fecha de corte (normalmente hoy); ancla la 'semana actual'
    week_now   : número de semana actual del ciclo de ventas (ej. 23)
    ref        : referencia 25/26 fija -> {refBN, refRev, p: {"Nov":127,...}}
    meta       : {name, sub, logo} del lodge
    return     : dict con la forma que espera el front (LODGES[key])
    """
    sm = season_months if season_months is not None else SEASON_MONTHS

    ks = known_sources or {}
    direct_set   = {s.lower() for s in ks.get("direct",   ["directo"])}
    outfitter_set = {s.lower() for s in ks.get("outfitters", [])}
    agency_set   = {s.lower() for s in ks.get("agencies",  [])}

    text = csv_bytes.decode("utf-8-sig", errors="replace")
    delim = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = list(reader)
    if not rows:
        raise ValueError("CSV vacío")
    cm = _colmap(rows[0])

    # acumuladores mensuales
    months = {m: dict(cs=0, cn=0, t=0, gs=0, gn=0, gt=0, rS=0.0, rN=0.0) for m, _ in sm}
    confirmed = []  # (created_date, bn, revenue) para el pacing
    kpi = dict(bnConf=0, bnPipe=0, guestsConf=0, guestsPipe=0, revConf=0.0, cobrado=0.0, saldo=0.0)
    channel_bn: dict[str, float] = defaultdict(float)  # source -> BN confirmadas

    for r in rows[1:]:
        if not r or len(r) <= cm["bn"]:
            continue
        bucket = _status_bucket(r[cm["status"]])
        start = _parse_date(r[cm["start"]])
        if start is None or start.month not in months:
            continue
        mo = start.month
        bn = _to_float(r[cm["bn"]])
        g = _to_float(r[cm["guests"]])
        price = _to_float(r[cm["price"]]) if "price" in cm else 0.0
        paid = _to_float(r[cm["paid"]]) if "paid" in cm else 0.0
        bal = _to_float(r[cm["balance"]]) if "balance" in cm else 0.0

        kpi["bnPipe"] += bn
        kpi["guestsPipe"] += g

        if bucket == "cs":
            months[mo]["cs"] += bn; months[mo]["gs"] += g; months[mo]["rS"] += price
        elif bucket == "cn":
            months[mo]["cn"] += bn; months[mo]["gn"] += g; months[mo]["rN"] += price
        else:
            months[mo]["t"] += bn; months[mo]["gt"] += g

        if bucket in ("cs", "cn"):  # confirmado
            kpi["bnConf"] += bn
            kpi["guestsConf"] += g
            kpi["revConf"] += price
            kpi["cobrado"] += paid
            kpi["saldo"] += bal
            created = _parse_date(r[cm["created"]]) if "created" in cm else None
            confirmed.append((created or anchor_date, bn, price))
            src = r[cm["source"]].strip() if "source" in cm else ""
            channel_bn[src] += bn

    adr = round(kpi["revConf"] / kpi["bnConf"]) if kpi["bnConf"] else 0

    # ms[] en el orden de la temporada, con la referencia p[] del año pasado
    ms = []
    for m, label in sm:
        d = months[m]
        ms.append(dict(
            l=label, cs=int(d["cs"]), cn=int(d["cn"]), t=int(d["t"]),
            gs=int(d["gs"]), gn=int(d["gn"]), gt=int(d["gt"]),
            rS=int(d["rS"]), rN=int(d["rN"]),
            p=int(ref.get("p", {}).get(label, 0)),
        ))

    pts = _build_pacing(confirmed, anchor_date=anchor_date, week_now=week_now)

    # canal breakdown (solo confirmadas)
    direct_bn = int(sum(v for k, v in channel_bn.items() if k.lower() in direct_set))
    outfitters_out = sorted(
        [{"name": k, "bn": int(v)} for k, v in channel_bn.items()
         if k.lower() in outfitter_set],
        key=lambda x: -x["bn"],
    )
    agencies_out = sorted(
        [{"name": k, "bn": int(v)} for k, v in channel_bn.items()
         if k.lower() in agency_set],
        key=lambda x: -x["bn"],
    )
    unknown_sources = [k for k in channel_bn
                       if k.lower() not in direct_set
                       and k.lower() not in outfitter_set
                       and k.lower() not in agency_set
                       and k]
    channels = dict(
        direct=direct_bn,
        outfitters=outfitters_out,
        agencies=agencies_out,
        unknown=unknown_sources,
    )

    return dict(
        name=meta["name"], sub=meta["sub"], logo=meta.get("logo"),
        week=week_now,
        kpis=dict(
            bnConf=int(kpi["bnConf"]), bnPipe=int(kpi["bnPipe"]),
            guestsConf=int(kpi["guestsConf"]), guestsPipe=int(kpi["guestsPipe"]),
            revConf=int(kpi["revConf"]), adr=int(adr),
            cobrado=int(kpi["cobrado"]), saldo=int(kpi["saldo"]),
        ),
        refBN=int(ref["refBN"]), refRev=int(ref["refRev"]),
        ms=ms, pts=pts, channels=channels,
    )


def _build_pacing(confirmed: list, *, anchor_date: dt.date, week_now: int) -> list:
    """Curva acumulada de BN/revenue confirmados por semana, anclada a week_now=hoy."""
    def weeknum(created: dt.date) -> int:
        delta = (anchor_date - created).days
        return max(1, week_now - (delta // 7))

    by_week = defaultdict(lambda: [0.0, 0.0])  # week -> [bn, rev] incremental
    for created, bn, rev in confirmed:
        w = weeknum(created)
        by_week[w][0] += bn
        by_week[w][1] += rev

    pts = [dict(w=1, b=0, r=0)]
    cum_b = cum_r = 0.0
    for w in sorted(by_week):
        cum_b += by_week[w][0]
        cum_r += by_week[w][1]
        pts.append(dict(w=w, b=int(cum_b), r=int(cum_r)))
    if not pts or pts[-1]["w"] != week_now:
        pts.append(dict(w=week_now, b=int(cum_b), r=int(cum_r)))
    return pts
