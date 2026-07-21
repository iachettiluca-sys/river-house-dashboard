"""
scrape_tgn.py — Descarga el CSV de "Bookings In Range" desde TGN para un lodge.

Flujo confirmado:
  1. Login en la home (modal) con email/password
  2. Navegar a /dashboard/select y hacer Enter al lodge target
  3. Ir a analytics/advanced, setear el rango de fechas, clickear Export Data
  4. Guardar el CSV en out_dir/tgn_{lodge_key}.csv

Si algo falla, lanza ScrapeError → build.py cae al modo /inbox.
"""
from __future__ import annotations
import os, re, time
from pathlib import Path

# Nombres tal como aparecen en la página /dashboard/select de TGN
LODGE_NAMES = {
    "rhl":   "The River House Group",
    "ap":    "Arroyo Pescado Lodge Patagonia",
    "foyel": "Foyel - Southland Outfitters",
}

BASE_URL = "https://www.theguidenetwork.com"


class ScrapeError(Exception):
    """Fallo recuperable: dispara notificación por mail + fallback inbox."""


def download_csv(lodge_key: str, *, start_date: str, end_date: str,
                 out_dir: Path, headless: bool = True) -> Path:
    """
    Descarga el CSV de Bookings In Range para el lodge indicado.
    lodge_key : 'rhl' | 'ap' | 'foyel'
    start_date: 'YYYY-MM-DD'
    end_date  : 'YYYY-MM-DD'
    Retorna el Path del CSV guardado.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    user = (os.environ.get("TGN_USER") or "").strip()
    pwd  = (os.environ.get("TGN_PASS") or "").strip()
    if not user or not pwd:
        raise ScrapeError("Faltan credenciales TGN_USER / TGN_PASS en el entorno.")

    lodge_name = LODGE_NAMES.get(lodge_key)
    if not lodge_name:
        raise ScrapeError(f"lodge_key desconocido: {lodge_key!r}. Válidos: {list(LODGE_NAMES)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    shot = out_dir / f"_error_{lodge_key}.png"
    date_re = re.compile(r"\w{3} \d{2} \d{4} - \w{3} \d{2} \d{4}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            accept_downloads=True,
        )
        page = ctx.new_page()
        try:
            # ---- 1. LOGIN ----
            page.goto(BASE_URL, timeout=45000)
            page.wait_for_load_state("networkidle", timeout=20000)
            page.click("text=Log In", timeout=15000)
            # Esperar a que el modal esté listo
            page.wait_for_selector("input[type='email']", timeout=10000)
            time.sleep(0.5)
            # .type() simula tecla por tecla y dispara onChange de React correctamente
            page.locator("input[type='email']").type(user, delay=40)
            time.sleep(0.3)
            page.locator("input[name='password']").type(pwd, delay=40)
            time.sleep(0.3)
            # Esperar a que el botón se habilite (React valida el form)
            page.wait_for_selector("button[type='submit']:not([disabled])", timeout=10000)
            page.click("button[type='submit']")
            page.wait_for_url(
                lambda url: "/dashboard/" in url and "/select" not in url,
                timeout=25000,
            )
            time.sleep(2)

            # ---- 2. SELECCIÓN DE LODGE ----
            page.goto(f"{BASE_URL}/dashboard/select", timeout=30000)
            time.sleep(3)

            # Buscar el botón Enter dentro de la tarjeta del lodge
            clicked = False
            for enter_btn in page.query_selector_all("button:has-text('Enter')"):
                if not enter_btn.is_visible():
                    continue
                try:
                    card_text = enter_btn.evaluate(
                        "btn => btn.closest('div') ? btn.closest('div').parentElement.innerText : ''"
                    )
                except Exception:
                    card_text = ""
                if lodge_name.lower() in card_text.lower():
                    enter_btn.click()
                    clicked = True
                    break

            if not clicked:
                # fallback: click en el nombre del lodge (puede navegar igual)
                page.click(f"text={lodge_name}", timeout=8000)

            # esperar a estar en el dashboard del lodge (no en /select)
            page.wait_for_url(
                lambda url: "/dashboard/" in url and "/select" not in url,
                timeout=20000,
            )
            time.sleep(2)

            # extraer UUID del lodge actual
            m = re.search(r"/dashboard/([0-9a-f-]{36})", page.url)
            if not m:
                raise ScrapeError(f"No pude extraer UUID tras seleccionar {lodge_key}: {page.url}")
            dash = f"{BASE_URL}/dashboard/{m.group(1)}"

            # ---- 3. ANALYTICS > ADVANCED (Bookings In Range) ----
            page.goto(f"{dash}/analytics/advanced", timeout=30000)
            time.sleep(4)

            # Buscar y clickear el botón de rango de fechas
            date_btn = None
            for b in page.query_selector_all("button"):
                if date_re.match(b.inner_text().strip()):
                    date_btn = b
                    break
            if not date_btn:
                page.screenshot(path=str(shot))
                raise ScrapeError(f"No encontré el botón de rango de fechas en analytics/advanced ({lodge_key})")

            date_btn.click()
            time.sleep(2)

            # Setear fechas en el modal
            page.locator("input[type='date']").first.fill(start_date)
            time.sleep(0.5)
            page.locator("input[type='date']").nth(1).fill(end_date)
            time.sleep(0.5)
            page.click("button:has-text('Save')")
            time.sleep(2)

            # ---- 4. EXPORT DATA ----
            try:
                page.wait_for_selector("button:has-text('Export Data')", timeout=20000)
            except Exception:
                page.screenshot(path=str(shot))
                raise ScrapeError(f"No encontré el botón Export Data ({lodge_key}). "
                                   "¿Cambió TGN o no hay bookings en el rango?")
            export_btn = page.query_selector("button:has-text('Export Data')")

            with page.expect_download(timeout=45000) as dl_info:
                export_btn.click()
            download = dl_info.value
            target = out_dir / f"tgn_{lodge_key}.csv"
            download.save_as(str(target))
            return target

        except PWTimeout as e:
            try:
                page.screenshot(path=str(shot))
            except Exception:
                pass
            raise ScrapeError(f"Timeout en TGN ({lodge_key}). Screenshot: {shot}. Detalle: {e}")
        except ScrapeError:
            raise
        except Exception as e:
            try:
                page.screenshot(path=str(shot))
            except Exception:
                pass
            raise ScrapeError(f"Fallo scraping TGN ({lodge_key}): {e}. Screenshot: {shot}")
        finally:
            ctx.close()
            browser.close()
