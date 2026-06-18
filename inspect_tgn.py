"""
inspect_tgn.py — Prueba end-to-end del scraper para RHL, AP y Foyel.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from scrape_tgn import download_csv, ScrapeError

WORK = Path(__file__).parent / "output" / "_work"

for key, sd, ed in [
    ("rhl",   "2026-11-01", "2027-04-30"),
    ("ap",    "2026-11-01", "2027-04-30"),
    ("foyel", "2027-03-01", "2027-04-30"),
]:
    print(f"\n{'='*50}")
    print(f"Descargando {key} ({sd} - {ed}) ...")
    try:
        path = download_csv(key, start_date=sd, end_date=ed, out_dir=WORK, headless=False)
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        print(f"  OK — {path.name} — {len(lines)-1} bookings")
        print(f"  Header: {lines[0][:100]}")
    except ScrapeError as e:
        print(f"  ERROR: {e}")

print("\nListo.")
