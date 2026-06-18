"""
notify.py — Emails de error y de actualización exitosa del dashboard.
Usa SMTP estándar (Gmail/Workspace: smtp.gmail.com:587 con app password).
"""
from __future__ import annotations
import os, smtplib, ssl
from email.message import EmailMessage

DASHBOARD_URL = "https://iachettiluca-sys.github.io/river-house-dashboard/"


def _send(msg: EmailMessage) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pwd  = os.environ.get("SMTP_PASS")
    if not (user and pwd):
        print("[notify] Sin credenciales SMTP; salteo email.")
        return
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port) as s:
        s.starttls(context=ctx)
        s.login(user, pwd)
        s.send_message(msg)


def send_failure_email(subject: str, body: str, attachments: list[str] | None = None) -> None:
    user = os.environ.get("SMTP_USER")
    to   = os.environ.get("NOTIFY_TO", user)
    if not (user and to):
        print("[notify] Sin credenciales SMTP; salteo email. Mensaje era:\n", body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

    for path in attachments or []:
        try:
            with open(path, "rb") as f:
                data = f.read()
            msg.add_attachment(data, maintype="image", subtype="png",
                               filename=os.path.basename(path))
        except OSError:
            pass

    _send(msg)
    print(f"[notify] Email de error enviado a {to}")


def send_unknown_source_email(lodge_key: str, unknown_sources: list[str]) -> None:
    user = os.environ.get("SMTP_USER")
    to   = os.environ.get("NOTIFY_TO", user)
    if not (user and to):
        return
    src_list = "\n".join(f"  - {s}" for s in unknown_sources)
    body = (
        f"Aparecieron sources nuevos en [{lodge_key.upper()}] que no están clasificados:\n\n"
        f"{src_list}\n\n"
        f"Respondé a este mail indicando si son outfitters o agencias "
        f"para agregarlos a config.yaml."
    )
    msg = EmailMessage()
    msg["Subject"] = f"Dashboard RHG — source nuevo en {lodge_key.upper()} sin clasificar"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)
    _send(msg)
    print(f"[notify] Email de source desconocido enviado a {to}: {unknown_sources}")


def send_success_email(lodges_updated: list[str], week_now: int) -> None:
    user = os.environ.get("SMTP_USER")
    team = os.environ.get("NOTIFY_TEAM", "")
    if not (user and team.strip()):
        print("[notify] NOTIFY_TEAM no configurado; salteo email de actualización.")
        return

    lodge_list = ", ".join(l.upper() for l in lodges_updated)
    body = (
        f"El dashboard de River House Group fue actualizado correctamente.\n\n"
        f"Lodges actualizados: {lodge_list}\n"
        f"Semana: {week_now}\n\n"
        f"Ver dashboard: {DASHBOARD_URL}\n"
    )

    msg = EmailMessage()
    msg["Subject"] = f"Dashboard RHG actualizado — Semana {week_now}"
    msg["From"] = user
    msg["To"] = ", ".join(e.strip() for e in team.split(",") if e.strip())
    msg.set_content(body)

    _send(msg)
    print(f"[notify] Email de actualización enviado a: {msg['To']}")
