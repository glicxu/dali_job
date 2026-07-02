from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_is_in_openapi_contract() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/dashboard" in schema["paths"]


def test_health_endpoint_returns_ok() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_me_endpoint_returns_dev_identity_by_default() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["auth_mode"] == "dev"
    assert body["provider"] == "dev"
    assert body["email"] == "local.user@dalijob.dev"
