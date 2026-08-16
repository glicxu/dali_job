from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.matching_v2.models import MatchingOperation, MatchingOperationStage
from app.modules.matching_v2.router import get_qualification_matcher
from test_matching_v2_qualification import StubQualificationMatcher, _foundation


def _client() -> tuple[TestClient, sessionmaker, StubQualificationMatcher, str, str]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory.begin() as db:
        _, candidate, job = _foundation(db)
        candidate_id = candidate.public_id
        job_id = job.public_id

    def override_db():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    matcher = StubQualificationMatcher()
    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, shadow_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_qualification_matcher] = lambda: matcher
    return TestClient(app), factory, matcher, candidate_id, job_id


def _payload(candidate_id: str, job_id: str) -> dict:
    return {
        "candidate_profile_id": candidate_id,
        "candidate_career_selection_revision": 1,
        "job_profile_id": job_id,
        "preference_revision": None,
        "eligibility_revision": None,
        "mode": "immediate",
        "idempotency_key": "match-request-0001",
    }


def test_match_operation_consumes_persisted_profiles_and_is_idempotent() -> None:
    client, factory, matcher, candidate_id, job_id = _client()

    first = client.post("/api/v1/matches", json=_payload(candidate_id, job_id))
    repeated = client.post("/api/v1/matches", json=_payload(candidate_id, job_id))

    assert first.status_code == 200, first.text
    assert repeated.status_code == 200
    assert first.json()["operation_id"] == repeated.json()["operation_id"]
    assert first.json()["status"] == "completed"
    assert first.json()["match"]["match_id"].startswith("match_")
    assert [stage["status"] for stage in first.json()["stages"]] == ["completed"] * 6
    assert first.json()["stages"][0]["cache_hit"] is True
    assert first.json()["stages"][1]["cache_hit"] is True
    assert matcher.calls == 1

    changed = _payload(candidate_id, "jp_different_input")
    conflict = client.post("/api/v1/matches", json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    match_id = first.json()["match"]["match_id"]
    assert client.get(f"/api/v1/matches/{match_id}").status_code == 200
    assert client.get(f"/api/v1/matching-operations/{first.json()['operation_id']}").status_code == 200

    with factory() as db:
        operation = db.scalar(select(MatchingOperation))
        stages = list(
            db.scalars(
                select(MatchingOperationStage).where(MatchingOperationStage.matching_operation_id == operation.id)
            )
        )
        assert operation.request_payload.keys() == {
            "candidate_profile_id",
            "candidate_career_selection_revision",
            "job_profile_id",
            "preference_revision",
            "eligibility_revision",
        }
        assert all("resume" not in str(stage.input_artifact_ids).lower() for stage in stages)


def test_match_operation_retry_resumes_at_qualification_without_revalidating_profiles() -> None:
    client, factory, matcher, candidate_id, job_id = _client()
    original_assess = matcher.assess
    calls = 0

    def fail_once(value):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("provider timeout details must stay private")
        return original_assess(value)

    matcher.assess = fail_once
    failed = client.post("/api/v1/matches", json=_payload(candidate_id, job_id))

    assert failed.status_code == 202
    assert failed.json()["status"] == "retryable_failure"
    assert [stage["status"] for stage in failed.json()["stages"][:3]] == [
        "completed",
        "completed",
        "retryable_failure",
    ]
    assert "provider timeout" not in failed.text

    retried = client.post(f"/api/v1/matching-operations/{failed.json()['operation_id']}/retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "completed"
    assert retried.json()["stages"][0]["attempt_count"] == 1
    assert retried.json()["stages"][1]["attempt_count"] == 1
    assert retried.json()["stages"][2]["attempt_count"] == 2

    with factory() as db:
        assert db.scalar(select(MatchingOperation)).status == "completed"
