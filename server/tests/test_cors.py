from fastapi.testclient import TestClient

from app.main import create_app


def test_managed_operation_preflight_allows_idempotency_key() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/v1/operations/tailored-resume",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
        },
    )

    assert response.status_code == 200
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "idempotency-key" in allowed_headers
