# Dashboard semanal — The River House Group

Genera el dashboard de pacing de los tres lodges (River House Lodge, Arroyo Pescado, Foyel)
de forma automática, una vez por semana, vía GitHub Actions, y lo publica en GitHub Pages.

## Cómo funciona

Cada lunes (o cuando lo dispares a mano) el workflow corre `build.py`, que para cada lodge:

1. **Intenta obtener los datos frescos**
   - RHL y AP: scraping de The Guide Network (login + búsqueda por rango fijo + descarga del CSV).
   - Foyel: descarga el Excel desde Google Drive (service account).
2. **Patrón "scrapeá-o-bandeja"**: si el scraping de TGN falla (cambió la web, se cayó la sesión, el CSV vino raro), el programa **no regenera con datos rotos**: te manda un **mail con el error + screenshot** y busca el archivo en la carpeta `inbox/`. Si lo dejaste ahí a mano, lo usa igual; si no, saltea ese lodge y sigue con el resto.
3. **Parsea** cada fuente con la lógica ya validada y arma el dict del lodge.
4. **Renderiza** el HTML final reusando la plantilla (`templates/dashboard.html.j2`) y lo publica.

La **referencia de la temporada pasada** (25/26) es fija y vive en `config.yaml`; no se re-scrapea porque ya está cerrada. Solo la temporada corriente se actualiza.

## Lo que ya está listo (no tocar salvo que cambien los datos)

- `src/parse_tgn.py` — CSV de TGN → KPIs, pipeline mensual, pacing semanal. Maneja separador `;`/`,`, fechas `d/m/Y`, estados con/sin seña/tentativa, ADR, cobrado/saldo, y reconstruye el pacing acumulado desde `Created On`.
- `src/parse_foyel.py` — Excel de Foyel → bed nights por mes (2027 vs 2026). Usa el total que calcula la propia planilla y lo cruza con un recuento independiente. **Solo bed nights**, sin desglose por estado (los colores de la grilla no matchean la leyenda) ni plata (no hay).
- `src/render.py` + `templates/dashboard.html.j2` — la plantilla es el dashboard que ya validamos; solo se le inyecta `const LODGES = {...}` y la fecha.
- `build.py`, `notify.py` — orquestador y aviso por mail.

## Lo que hay que completar (depende del entorno real)

1. **Selectores de TGN** en `src/scrape_tgn.py` — están marcados con `# >>> AJUSTAR`. No puedo verlos sin acceso al sitio. La primera vez, corré el scraper en modo visible y ajustá: campos de login, inputs de fecha, botón de buscar y botón de exportar CSV.
   ```bash
   # local, navegador visible para ajustar selectores:
   python -c "from pathlib import Path; import datetime as dt; \
     from src.scrape_tgn import download_csv; \
     download_csv('ap', start_date='2026-11-01', end_date='2027-04-30', \
                  out_dir=Path('output/_work'), headless=False)"
   ```
2. **`config.yaml`** — pegar el `drive_file_id` del Excel de Foyel y revisar `week_now` y el rango de fechas.
3. **Secrets** (GitHub → Settings → Secrets and variables → Actions): `TGN_USER`, `TGN_PASS`, `TGN_LOGIN_URL`, `TGN_SEARCH_URL`, `GOOGLE_SA_JSON`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `NOTIFY_TO`. Ver `.env.example`.
4. **Google Drive**: crear una service account, descargar su JSON (va en `GOOGLE_SA_JSON`), y **compartir el Excel de Foyel con el email de la service account** (permiso lector).
5. **GitHub Pages**: activarlo en Settings → Pages → Source: "GitHub Actions".

## Correr local

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env   # completar
python build.py
# abre output/index.html
```

## Notas / decisiones

- **Email para Gmail/Workspace**: usar un *app password* (no la contraseña normal); requiere 2FA en la cuenta.
- **GitHub Actions e IP de datacenter**: TGN podría ver el login desde una IP distinta a la tuya y pedir verificación extra. Si pasa seguido, el modo `inbox/` es tu red de seguridad; si se vuelve crónico, conviene mover el cron a una máquina/VPS tuya (mismo código, solo cambia el scheduler).
- **`week_now`**: hoy se setea a mano en `config.yaml`. Si querés, se puede calcular automáticamente desde una fecha de inicio de temporada.
- **Pacing de RHL**: ahora se recalcula desde el CSV (metodología consistente con AP), así que puede diferir un poco de los puntos que estaban cargados a mano en la primera versión.
