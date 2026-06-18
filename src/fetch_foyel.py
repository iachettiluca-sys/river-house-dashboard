"""
fetch_foyel.py — Descarga el Excel de Foyel desde Google Drive usando una
service account (sin intervención). Compartí el archivo (o su carpeta) con el
email de la service account y poné el FILE_ID en config.
"""
from __future__ import annotations
import io, json, os
from pathlib import Path


class FetchError(Exception):
    pass


def download_foyel_xlsx(file_id: str, out_dir: Path) -> Path:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as e:
        raise FetchError(f"Faltan libs de Google: {e}")

    sa_json = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json:
        raise FetchError("Falta GOOGLE_SA_JSON (credenciales de la service account)")

    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "foyel.xlsx"

    # export si es Google Sheet nativo; descarga directa si ya es .xlsx
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    if meta["mimeType"] == "application/vnd.google-apps.spreadsheet":
        request = service.files().export_media(
            fileId=file_id,
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        request = service.files().get_media(fileId=file_id)

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    target.write_bytes(buf.getvalue())
    return target
