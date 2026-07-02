from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import get_dev_identity
from app.modules.jobs import repository as job_repository
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.profiles import repository as profile_repository
from app.modules.profiles.schemas import ResumeData, ResumeProfileCreateRequest


def create_test_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
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
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app), session_factory


def test_dashboard_returns_setup_recommendation_when_empty() -> None:
    client, _session_factory = create_test_client()

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_next_step"]["kind"] == "create_resume_profile"
    assert payload["setup_alerts"][0]["kind"] == "missing_resume_profile"
    assert payload["best_matches"] == []
    assert payload["recently_saved_jobs"] == []


def test_dashboard_returns_best_matches_and_recent_jobs() -> None:
    client, session_factory = create_test_client()
    identity = get_dev_identity()

    with session_factory() as session:
        resume_profile = profile_repository.create_resume_profile(
            session,
            ResumeProfileCreateRequest(
                title="Backend Resume",
                resume_data=ResumeData(
                    headline="Backend Engineer",
                    summary="Builds APIs.",
                    skills=["Python", "FastAPI"],
                ),
                is_favorite=True,
            ),
            identity,
        )
        saved_job = job_repository.create_job_from_description(
            session,
            identity,
            source_url="https://example.com/jobs/backend-engineer",
            raw_description_text="Build APIs using Python.",
            job_data=JobDescriptionData(
                title="Backend Engineer",
                company="Example Co",
                summary="Build backend services.",
                required_skills=["Python"],
            ),
        )
        job_repository.create_job_resume_match(
            session,
            identity,
            user_job_id=saved_job["id"],
            jobs_cache_id=saved_job["jobs_cache_id"],
            resume_profile_id=resume_profile.id,
            resume_source="resume_profile",
            match_score=8,
            match_data={"summary": "Strong backend match."},
        )
        session.commit()

    response = client.get("/api/v1/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_next_step"]["kind"] == "review_best_matches"
    assert payload["best_matches"][0]["title"] == "Backend Engineer"
    assert payload["best_matches"][0]["match_score"] == 8
    assert payload["best_matches"][0]["resume_label"] == "Backend Resume"
    assert payload["best_matches"][0]["href"] == f"/jobs?job_id={saved_job['id']}&view=match"
    assert payload["recently_saved_jobs"][0]["status"] == "matched"
