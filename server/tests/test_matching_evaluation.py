from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.evaluation.router import get_job_snapshot_fetcher
from app.modules.matching_v2.extraction import JobExtractionResult as ProfileExtractionResult
from app.modules.matching_v2.router import (
    get_candidate_profile_extractor,
    get_job_profile_extractor,
    get_qualification_matcher,
)
from app.modules.resume_job_match.job_url_import import JobExtractionResult as WebExtractionResult
from tests.test_matching_v2_candidate_profiles import StubCandidateExtractor
from tests.test_matching_v2_qualification import StubQualificationMatcher, _job_artifact


class EvaluationJobExtractor:
    def extract(self, spans):
        return ProfileExtractionResult(
            artifact=_job_artifact(spans[0].span_id),
            model_id="gpt-4.1-mini",
            provider_execution_reference="provider-evaluation-job-test-1",
        )


def _fetched_job(_: str) -> WebExtractionResult:
    return WebExtractionResult(
        source_url="https://example.com/jobs/quality-1",
        canonical_url="https://example.com/jobs/quality-1",
        title="Senior Software Engineer",
        company="Tier One Co",
        location="Seattle, WA",
        sections={"requirements": ["Production Python experience"]},
        focused_text=(
            "Senior Software Engineer\n\nRequirements\nProduction Python experience\n"
            "TypeScript, JavaScript, or a comparable language"
        ),
        raw_visible_text=None,
        extraction_method="test-fixture",
        confidence=0.99,
        warnings=[],
        extractor_version="test.v1",
    )


def test_admin_can_capture_and_inspect_a_repeatable_three_stage_run() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, evaluation_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_job_snapshot_fetcher] = lambda: _fetched_job
    app.dependency_overrides[get_candidate_profile_extractor] = lambda: StubCandidateExtractor()
    app.dependency_overrides[get_job_profile_extractor] = lambda: EvaluationJobExtractor()
    app.dependency_overrides[get_qualification_matcher] = lambda: StubQualificationMatcher()
    client = TestClient(app)

    resume = client.post("/api/v1/resume-profiles", json={
        "title": "Evaluation Candidate",
        "resume_data": {
            "headline": "Software Engineer",
            "summary": "Builds production Python services.",
            "experience": ["Delivered APIs used by customers."],
            "skills": ["Python"],
        },
    })
    assert resume.status_code == 200

    captured = client.post("/api/v1/internal/evaluation/job-snapshots/import", json={
        "source_url": "https://example.com/jobs/quality-1",
        "benchmark_release": "matching-benchmark-jobs.v1",
        "coverage_slot": "senior-software",
    })
    assert captured.status_code == 200
    assert captured.json()["source_hash"].startswith("sha256:")

    run = client.post("/api/v1/internal/evaluation/runs", json={
        "job_snapshot_id": captured.json()["public_id"],
        "resume_profile_id": resume.json()["id"],
    })
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["run_metadata"]["score_generated"] is False
    assert body["resume_source"]["spans"]
    assert body["job_source"]["spans"]
    assert body["candidate_profile"]["candidate_profile_id"].startswith("cp_")
    assert body["job_profile"]["job_profile_id"].startswith("jp_")
    assert len(body["qualification"]["assessment"]["requirement_assessments"]) == 1
    assert len(body["qualification"]["assessment"]["hard_constraint_assessments"]) == 1

    fetched = client.get(f"/api/v1/internal/evaluation/runs/{body['public_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    assert len(client.get("/api/v1/internal/evaluation/job-snapshots").json()["snapshots"]) == 1
    assert len(client.get("/api/v1/internal/evaluation/runs").json()["runs"]) == 1


def test_evaluation_routes_are_hidden_by_default() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, future=True)

    def override_db():
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    response = client.get("/api/v1/internal/evaluation/job-snapshots")

    assert response.status_code == 404
