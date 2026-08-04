from fastapi.testclient import TestClient

from app.main import create_app


def test_managed_operation_preflight_allows_idempotency_key() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/v1/operations/tailored-resume",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,idempotency-key,x-csrf-token",
        },
    )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed_headers
    assert "x-csrf-token" in allowed_headers


def test_production_cors_allows_only_configured_https_origin(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ENV", "production")
    monkeypatch.setenv("DALIJOB_AUTH_MODE", "local")
    monkeypatch.setenv("DALIJOB_CLIENT_ORIGINS", "https://jobmatch.dalifin.com")
    monkeypatch.setenv("DALIJOB_PUBLIC_CLIENT_URL", "https://jobmatch.dalifin.com")
    monkeypatch.setenv("DALIJOB_EMAIL_DELIVERY_MODE", "smtp")
    monkeypatch.setenv("DALIJOB_EMAIL_FROM", "no-reply@dalifin.com")
    monkeypatch.setenv("DALIJOB_SMTP_HOST", "smtp.example.com")
    client = TestClient(create_app())

    allowed = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://jobmatch.dalifin.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    localhost = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://jobmatch.dalifin.com"
    assert localhost.status_code == 400
    assert "access-control-allow-origin" not in localhost.headers
