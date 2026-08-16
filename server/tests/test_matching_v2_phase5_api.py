from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.secrets import clear_secret_cache
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.matching_v2.models import EligibilityRevision, PreferenceRevision


def test_preference_and_encrypted_eligibility_revision_apis(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ELIGIBILITY_ENCRYPTION_KEY", "phase5-api-test-key")
    clear_secret_cache()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        with factory() as session:
            yield session

    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, shadow_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    preferences = client.put(
        "/api/v1/users/me/matching-preferences",
        json={
            "expected_revision": 0,
            "preferences": {
                "desired_roles": [{"value": "software_engineering", "importance": "high"}],
                "locations": None,
                "workplace_types": [],
                "compensation": None,
                "employment_types": None,
                "desired_skills": [],
                "avoided_industries": [],
                "hard_constraints": [],
            },
        },
    )
    assert preferences.status_code == 200
    assert preferences.json()["revision"] == 1
    assert client.get("/api/v1/users/me/matching-preferences").json() == preferences.json()

    eligibility = client.put(
        "/api/v1/users/me/eligibility-facts",
        json={
            "expected_revision": 0,
            "facts": {
                "work_authorizations": [
                    {"country": "US", "status": "authorized", "requires_sponsorship": False}
                ],
                "clearances": None,
                "licenses": None,
                "travel_availability_percent": 25,
                "relocation": "maybe",
            },
        },
    )
    assert eligibility.status_code == 200
    assert eligibility.json()["facts"]["work_authorizations"][0]["status"] == "authorized"
    assert client.get("/api/v1/users/me/eligibility-facts").json() == eligibility.json()

    stale = client.put(
        "/api/v1/users/me/eligibility-facts",
        json={"expected_revision": 0, "facts": eligibility.json()["facts"]},
    )
    assert stale.status_code == 409

    with factory() as db:
        preference_row = db.scalar(select(PreferenceRevision))
        eligibility_row = db.scalar(select(EligibilityRevision))
        assert preference_row is not None and preference_row.artifact["desired_roles"]
        assert eligibility_row is not None
        assert "authorized" not in eligibility_row.encrypted_artifact
        assert eligibility_row.encryption_version == "aes256-gcm.v1"
        assert eligibility_row.content_hash.startswith("hmac-sha256:")
