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
    assert "/api/v1/operations/quick-find-jobs" in schema["paths"]
    assert "/api/v1/job-search/quick-find/save" in schema["paths"]
    assert "/api/v1/job-search/criteria" in schema["paths"]
    assert "/api/v1/job-search/criteria/{criterion_id}" in schema["paths"]
    assert "/api/v1/application-materials" in schema["paths"]
    assert "/api/v1/operations/tailored-resume" in schema["paths"]
    assert "/api/v1/operations/cover-letter" in schema["paths"]
    assert "/api/v1/reports" in schema["paths"]
    assert "/api/v1/admin/reports" in schema["paths"]
    assert "/api/v1/me/tutorial/complete" in schema["paths"]
    assert "/api/v1/account/entitlements" in schema["paths"]
    assert "/api/v1/account/usage" in schema["paths"]
    assert "/api/v1/automation/schedules" in schema["paths"]
    assert "/api/v1/automation/schedules/{schedule_id}" in schema["paths"]
    assert "/api/v1/automation/runs" in schema["paths"]
    assert "/api/v1/automation/runs/{run_id}" in schema["paths"]
    assert "/api/v1/notification-preferences" in schema["paths"]
    assert "/api/v1/match-inbox" in schema["paths"]
    assert "/api/v1/match-inbox/{match_id}" in schema["paths"]
    assert "/api/v1/match-inbox/{match_id}/read" in schema["paths"]
    assert "/api/v1/match-inbox/{match_id}/feedback" in schema["paths"]
    assert "/api/v1/matches" in schema["paths"]
    assert "/api/v1/matches/{match_id}" in schema["paths"]
    assert "/api/v1/matches/{match_id}/rerun" in schema["paths"]
    assert "/api/v1/candidate-profiles/{candidate_profile_id}/matching-intents" in schema["paths"]
    assert "/api/v1/matching-intents/{matching_intent_id}" in schema["paths"]
    assert "/api/v1/job-family-pre-matches/{pre_match_id}" in schema["paths"]
    assert "/api/v1/matching-operations/{operation_id}" in schema["paths"]
    assert "/api/v1/matching-operations/{operation_id}/retry" in schema["paths"]
    assert schema["paths"]["/api/v1/resume-job-matches"]["post"]["deprecated"] is True
    assert schema["paths"]["/api/v1/operations/resume-job-match"]["post"]["deprecated"] is True
    assert "/api/v1/auth/mobile/sessions" in schema["paths"]
    assert "/api/v1/auth/mobile/sessions/refresh" in schema["paths"]
    assert "/api/v1/auth/mobile/sessions/{session_id}" in schema["paths"]
    assert "/api/v1/auth/mobile/sessions/current" in schema["paths"]


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
    assert body["role"] == "admin"
    assert body["tutorial_completed"] is True
