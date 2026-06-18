"""
notify.py — Avisa por email cuando el scraping falla (modo /inbox necesario).
Usa SMTP estándar (Gmail/Workspace: smtp.gmail.com:587 con app password).
"""
from __future__ import annotations
import os, smtplib, ssl
from email.message import EmailMessage


def send_failure_email(subject: str, body: str, attachments: list[str] | None = None) -> None:
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    to = os.environ.get("NOTIFY_TO", user)
    if not (user and pwd and to):
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

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port) as s:
        s.starttls(context=ctx)
        s.login(user, pwd)
        s.send_message(msg)
    print(f"[notify] Email de error enviado a {to}")
