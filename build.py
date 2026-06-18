#!/usr/bin/env python3
"""
build.py — Orquestador. Para cada lodge:
  1. intenta obtener los datos frescos vía scraping TGN
  2. si falla, busca el archivo en /inbox (modo manual) y, si tampoco está,
     avisa por mail y SALTEA ese lodge sin romper el resto
  3. parsea -> arma el dict del lodge
Luego renderiza el HTML final con lo que se haya podido actualizar.

Patrón "scrapeá-o-bandeja": cada corrida intenta automático; si TGN cambió,
te llega un mail y vos dejás el CSV en /inbox -> la próxima corrida lo usa.
"""
from __future__ import annotations
import sys, datetime as dt
from pathlib import Path

import yaml
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from parse_tgn import parse_tgn_csv          # noqa: E402
from render import render_dashboard          # noqa: E402
from notify import send_failure_email, send_success_email  # noqa: E402

INBOX = ROOT / "inbox"
WORK = ROOT / "output" / "_work"
OUT = ROOT / "output" / "index.html"

# Meses de la temporada de Foyel (solo otoño: mar–abr)
FOYEL_MONTHS = [(3, "Mar"), (4, "Abr")]


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def _inbox_file(*names: str) -> Path | None:
    for n in names:
        p = INBOX / n
        if p.exists():
            return p
    return None


def build_tgn_lodge(key: str, cfg: dict, anchor: dt.date, errors: list,
                    start_date: str | None = None, end_date: str | None = None) -> dict | None:
    lc = cfg["lodges"][key]
    sd = start_date or cfg["tgn"]["start_date"]
    ed = end_date   or cfg["tgn"]["end_date"]
    csv_path = None
    try:
        from scrape_tgn import download_csv, ScrapeError
        csv_path = download_csv(key, start_date=sd, end_date=ed, out_dir=WORK, headless=True)
    except Exception as e:  # noqa: BLE001
        csv_path = _inbox_file(f"tgn_{key}.csv", f"{key}.csv")
        if csv_path is None:
            errors.append(f"[{key}] No se pudo scrapear ni encontrar /inbox: {e}")
            return None
        print(f"[{key}] Scraping falló, uso archivo manual de /inbox: {csv_path.name}")

    data = csv_path.read_bytes()
    return parse_tgn_csv(
        data, anchor_date=anchor, week_now=cfg["week_now"],
        ref=lc["ref"], meta=dict(name=lc["name"], sub=lc["sub"], logo=lc.get("logo")),
        season_months=FOYEL_MONTHS if key == "foyel" else None,
    )


def main() -> int:
    cfg = load_config()
    anchor = dt.date.today()
    errors: list[str] = []
    lodges: dict = {}

    for key in ("rhl", "ap"):
        d = build_tgn_lodge(key, cfg, anchor, errors)
        if d:
            lodges[key] = d

    # Foyel: mismo flujo TGN pero con rango de fechas propio
    foyel_cfg = cfg.get("foyel_tgn", {})
    f = build_tgn_lodge(
        "foyel", cfg, anchor, errors,
        start_date=foyel_cfg.get("start_date"),
        end_date=foyel_cfg.get("end_date"),
    )
    if f:
        lodges["foyel"] = f

    ordered = {k: lodges[k] for k in ("rhl", "ap", "foyel") if k in lodges}
    if ordered:
        render_dashboard(ordered, OUT)
        print(f"[build] Dashboard escrito en {OUT} ({len(ordered)} lodges)")
        if not errors:
            send_success_email(list(ordered.keys()), cfg["week_now"])

    if errors:
        body = ("El update semanal del dashboard tuvo problemas:\n\n"
                + "\n".join(errors)
                + "\n\nDejá el/los archivo(s) en la carpeta /inbox y volvé a correr, "
                  "o re-dispará el workflow.")
        shots = [str(p) for p in WORK.glob("_error_*.png")]
        send_failure_email("⚠️ Dashboard RHG — update semanal con errores", body, shots)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
