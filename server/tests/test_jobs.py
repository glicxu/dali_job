from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.jobs import router as jobs_router
from app.modules.jobs.router import get_job_description_parser
from app.modules.jobs.schemas import JobDescriptionData


class FakeJobDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        assert "Build APIs using Python" in raw_description_text
        return JobDescriptionData(
            title="Backend Engineer",
            company="Example Co",
            summary="Build backend services.",
            responsibilities=["Build APIs using Python."],
            required_skills=["Python", "API design"],
            preferred_skills=["FastAPI"],
            required_experience=["Backend service development"],
            preferred_experience=[],
            education=[],
            certifications=[],
            tools_and_technologies=["Python", "PostgreSQL"],
            keywords=["backend", "Python", "PostgreSQL"],
            seniority_level="Mid-level",
            employment_type="Full-time",
            security_clearance="",
            work_location="Remote",
            salary_range="",
            application_deadline="",
        )


def create_test_client() -> TestClient:
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
    app.dependency_overrides[get_job_description_parser] = lambda: FakeJobDescriptionParser()
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app)


def test_import_job_description_from_url_saves_raw_text_and_json(monkeypatch) -> None:
    client = create_test_client()
    monkeypatch.setattr(
        jobs_router,
        "fetch_job_page_text_from_url",
        lambda _url: "Build APIs using Python and PostgreSQL for customer workflows.",
    )

    response = client.post(
        "/api/v1/jobs/import-description",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Backend Engineer"
    assert payload["company"] == "Example Co"
    assert payload["source_url"] == "https://example.com/jobs/backend-engineer"
    assert "Build APIs using Python" in payload["raw_description_text"]
    assert payload["job_data"]["required_skills"] == ["Python", "API design"]
    assert payload["job_data"]["tools_and_technologies"] == ["Python", "PostgreSQL"]

    list_response = client.get("/api/v1/jobs")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == payload["id"]


def test_import_job_description_from_pasted_text_saves_raw_text_and_json() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/jobs/import-description",
        json={"job_description_text": "Build APIs using Python and PostgreSQL for customer workflows."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_url"] is None
    assert payload["job_data"]["summary"] == "Build backend services."


def test_draft_job_description_does_not_save_until_user_creates_job(monkeypatch) -> None:
    client = create_test_client()
    monkeypatch.setattr(
        jobs_router,
        "fetch_job_page_text_from_url",
        lambda _url: "Build APIs using Python and PostgreSQL for customer workflows.",
    )

    draft_response = client.post(
        "/api/v1/jobs/draft",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
    )

    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["source_url"] == "https://example.com/jobs/backend-engineer"
    assert draft["job_data"]["title"] == "Backend Engineer"
    assert client.get("/api/v1/jobs").json() == []

    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": draft["job_data"]["title"],
            "company": draft["job_data"]["company"],
            "source_url": draft["source_url"],
            "raw_description_text": draft["raw_description_text"],
            "job_data": draft["job_data"],
            "notes": "Looks promising.",
        },
    )

    assert create_response.status_code == 200
    saved = create_response.json()
    assert saved["notes"] == "Looks promising."
    assert client.get("/api/v1/jobs").json()[0]["id"] == saved["id"]


def test_update_saved_job_edits_metadata_and_json() -> None:
    client = create_test_client()
    create_response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "company": "Example Co",
            "raw_description_text": "Build APIs using Python and PostgreSQL for customer workflows.",
            "job_data": {
                "title": "Backend Engineer",
                "company": "Example Co",
                "summary": "Build backend services.",
                "responsibilities": ["Build APIs using Python."],
                "required_skills": ["Python"],
                "preferred_skills": [],
                "required_experience": [],
                "preferred_experience": [],
                "education": [],
                "certifications": [],
                "tools_and_technologies": ["Python"],
                "keywords": ["backend"],
                "seniority_level": "",
                "employment_type": "",
                "security_clearance": "",
                "work_location": "",
                "salary_range": "",
                "application_deadline": "",
            },
            "notes": "",
        },
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/jobs/{job_id}",
        json={
            "title": "Senior Backend Engineer",
            "job_data": {
                "title": "Senior Backend Engineer",
                "company": "Example Co",
                "summary": "Build backend platform services.",
                "responsibilities": ["Build APIs using Python."],
                "required_skills": ["Python", "PostgreSQL"],
                "preferred_skills": ["FastAPI"],
                "required_experience": ["Backend API development"],
                "preferred_experience": [],
                "education": [],
                "certifications": [],
                "tools_and_technologies": ["Python", "PostgreSQL"],
                "keywords": ["backend", "PostgreSQL"],
                "seniority_level": "Senior",
                "employment_type": "Full-time",
                "security_clearance": "",
                "work_location": "Remote",
                "salary_range": "$100,000 - $130,000",
                "application_deadline": "2026-07-01",
            },
            "notes": "Updated after review.",
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["title"] == "Senior Backend Engineer"
    assert payload["job_data"]["required_skills"] == ["Python", "PostgreSQL"]
    assert payload["notes"] == "Updated after review."


def test_updating_saved_job_does_not_mutate_cached_url_job(monkeypatch) -> None:
    client = create_test_client()
    monkeypatch.setattr(
        jobs_router,
        "fetch_job_page_text_from_url",
        lambda _url: "Build APIs using Python and PostgreSQL for customer workflows.",
    )
    create_response = client.post(
        "/api/v1/jobs/import-description",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
    )
    assert create_response.status_code == 200
    saved = create_response.json()

    update_response = client.patch(
        f"/api/v1/jobs/{saved['id']}",
        json={
            "title": "My Edited Job Title",
            "job_data": {
                **saved["job_data"],
                "title": "My Edited Job Title",
                "required_skills": ["Custom Skill"],
            },
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["job_data"]["required_skills"] == ["Custom Skill"]

    draft_response = client.post(
        "/api/v1/jobs/draft",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["job_data"]["title"] == "Backend Engineer"
    assert draft["job_data"]["required_skills"] == ["Python", "API design"]
