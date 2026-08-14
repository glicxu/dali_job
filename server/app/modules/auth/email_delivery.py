from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from app.config import RuntimeConfig


def send_account_email(runtime: RuntimeConfig, recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = runtime.email_from_address
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    if runtime.email_delivery_mode == "file":
        outbox = Path(runtime.email_outbox_dir)
        outbox.mkdir(parents=True, exist_ok=True)
        try:
            outbox.chmod(0o700)
        except OSError:
            pass
        target = outbox / f"{uuid4().hex}.eml"
        target.write_bytes(message.as_bytes())
        return

    if runtime.email_delivery_mode != "smtp":
        raise RuntimeError(f"Unsupported email delivery mode: {runtime.email_delivery_mode}")

    with smtplib.SMTP(runtime.smtp_host, runtime.smtp_port, timeout=15) as smtp:
        if runtime.smtp_use_tls:
            smtp.starttls()
        if runtime.smtp_username:
            smtp.login(runtime.smtp_username, runtime.smtp_password)
        smtp.send_message(message)
