from __future__ import annotations

from types import SimpleNamespace

from app.modules.auth.email_delivery import send_account_email


class RecordingSmtp:
    instance: "RecordingSmtp | None" = None

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.credentials: tuple[str, str] | None = None
        self.message = None
        RecordingSmtp.instance = self

    def __enter__(self) -> "RecordingSmtp":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def send_message(self, message) -> None:
        self.message = message


def test_smtp_delivery_uses_resolved_runtime_credentials(monkeypatch) -> None:
    monkeypatch.setattr("app.modules.auth.email_delivery.smtplib.SMTP", RecordingSmtp)
    runtime = SimpleNamespace(
        email_from_address="report@dalifin.com",
        email_delivery_mode="smtp",
        email_outbox_dir="unused",
        smtp_host="dalifin-com-smtp.dynu.com",
        smtp_port=587,
        smtp_username="shared-login",
        smtp_password="shared-password",
        smtp_use_tls=True,
    )

    send_account_email(runtime, "candidate@example.com", "Verify DaliJob", "Verification body")

    smtp = RecordingSmtp.instance
    assert smtp is not None
    assert (smtp.host, smtp.port, smtp.timeout) == ("dalifin-com-smtp.dynu.com", 587, 15)
    assert smtp.started_tls is True
    assert smtp.credentials == ("shared-login", "shared-password")
    assert smtp.message["From"] == "report@dalifin.com"
    assert smtp.message["To"] == "candidate@example.com"
    assert smtp.message.get_content().strip() == "Verification body"
