"""
fetch_history.py — Descarga y parsea la temporada pasada (25/26) para RHL y AP.
Corre UNA SOLA VEZ. Actualiza config.yaml con ref.channels por lodge.

Uso:
    python fetch_history.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import datetime as dt
import yaml
from scrape_tgn import download_csv, ScrapeError
from parse_tgn import parse_tgn_csv

ROOT    = Path(__file__).parent
WORK    = ROOT / "output" / "_work"
CONFIG  = ROOT / "config.yaml"

HIST_START = "2025-11-01"
HIST_END   = "2026-04-30"
LODGES     = ["rhl", "ap"]

cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
known_sources = cfg.get("sources", {})

for key in LODGES:
    print(f"\n{'='*50}")
    print(f"Descargando historial {key} ({HIST_START} - {HIST_END}) ...")
    try:
        hist_path = WORK / f"tgn_{key}_hist.csv"
        if hist_path.exists():
            path = hist_path
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            print(f"  Usando CSV existente: {path.name} — {len(lines)-1} bookings")
        else:
            path = download_csv(
                key,
                start_date=HIST_START,
                end_date=HIST_END,
                out_dir=WORK,
                headless=False,
            )
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
            print(f"  OK — {path.name} — {len(lines)-1} bookings")

        anchor = dt.date(2026, 4, 30)
        lc = cfg["lodges"][key]
        data = parse_tgn_csv(
            path.read_bytes(),
            anchor_date=anchor,
            week_now=52,
            ref=lc["ref"],
            meta={"name": lc["name"], "sub": lc["sub"]},
            known_sources=known_sources,
        )

        ch = data["channels"]
        print(f"  Canales — directo: {ch['direct']} BN")
        for o in ch["outfitters"]:
            print(f"    {o['name']}: {o['bn']} BN")
        if ch.get("unknown"):
            print(f"  DESCONOCIDOS: {ch['unknown']}")

        # Guardar en config.yaml bajo ref.channels
        cfg["lodges"][key]["ref"]["channels"] = {
            "direct": ch["direct"],
            "outfitters": ch["outfitters"],
            "agencies": ch.get("agencies", []),
        }

        # Guardar como hist si vino de descarga fresca
        if path.name != f"tgn_{key}_hist.csv":
            hist_path = WORK / f"tgn_{key}_hist.csv"
            path.replace(hist_path)
            print(f"  CSV guardado como {hist_path.name}")

    except ScrapeError as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

# Escribir config.yaml actualizado
CONFIG.write_text(
    yaml.dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False),
    encoding="utf-8",
)
print(f"\nconfig.yaml actualizado con ref.channels para: {LODGES}")
print("Listo.")
