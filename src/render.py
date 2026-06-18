"""
render.py — Inyecta el dict de lodges en la plantilla y escribe el HTML final.
La plantilla reusa TODO el JS de rendering del dashboard; solo cambia la fuente
de datos (const LODGES = ...) y la fecha del footer.
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"


def render_dashboard(lodges: dict, out_path: Path, *, generated_date: str | None = None) -> Path:
    try:
        from jinja2 import Template
        tpl = Template(TEMPLATE.read_text(encoding="utf-8"))
        html = tpl.render(
            lodges_json=json.dumps(lodges, ensure_ascii=False),
            generated_date=generated_date or dt.date.today().strftime("%d de %B de %Y"),
        )
    except ImportError:
        # fallback sin jinja: reemplazo simple de tokens
        html = TEMPLATE.read_text(encoding="utf-8")
        html = html.replace("{{ lodges_json | safe }}", json.dumps(lodges, ensure_ascii=False))
        html = html.replace("{{ generated_date }}",
                             generated_date or dt.date.today().strftime("%d de %B de %Y"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
