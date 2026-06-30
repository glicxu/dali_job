from __future__ import annotations

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.job_search.apify_indeed import get_apify_indeed_client, normalize_indeed_item
from app.modules.job_search.router import get_job_search_description_parser, get_job_search_resume_matcher
from app.modules.jobs.schemas import IndeedJobSearchResult, JobDescriptionData
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest, ResumeJobMatchResponse


class FakeApifyIndeedClient:
    def search(self, *, keyword: str, location: str, max_results: int = 5) -> list[IndeedJobSearchResult]:
        assert keyword == "software engineer"
        assert location == "Maryland"
        assert max_results == 5
        return [
            IndeedJobSearchResult(
                external_id="abc123",
                title="Software Engineer",
                company="Example Systems",
                location="Maryland",
                source_url="https://www.indeed.com/viewjob?jk=abc123",
                summary="Build APIs using Python and PostgreSQL.",
                raw_description_text="Build APIs using Python and PostgreSQL for customer workflows.",
                employment_type="Full-time",
            )
        ]


class FailingApifyIndeedClient:
    def search(self, *, keyword: str, location: str, max_results: int = 5) -> list[IndeedJobSearchResult]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APIFY_API_TOKEN is not configured for the server process.",
        )


class FakeJobDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        assert "Build APIs using Python" in raw_description_text
        return JobDescriptionData(
            title="Software Engineer",
            company="Example Systems",
            summary="Build APIs using PostgreSQL.",
            responsibilities=["Build APIs using Python."],
            required_skills=["Python", "PostgreSQL"],
            preferred_skills=[],
            required_experience=["Backend API development"],
            preferred_experience=[],
            education=[],
            certifications=[],
            tools_and_technologies=["Python", "PostgreSQL"],
            keywords=["software engineer", "Python", "PostgreSQL"],
            seniority_level="",
            employment_type="Full-time",
            security_clearance="",
            work_location="Maryland",
            salary_range="",
            application_deadline="",
        )


class FakeMatcher:
    def compare(self, request: ResumeJobMatchRequest) -> ResumeJobMatchResponse:
        assert request.resume_text is not None
        assert "FastAPI" in request.resume_text
        assert request.job_description_text is not None
        assert "PostgreSQL" in request.job_description_text
        return ResumeJobMatchResponse(
            id=None,
            match_score=8,
            summary="Strong backend match.",
            matched_skills=["Python"],
            missing_skills=[],
            matched_keywords=["PostgreSQL"],
            missing_keywords=[],
            supported_requirements=[],
            unsupported_requirements=[],
            recommended_resume_updates=[],
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
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_apify_indeed_client] = lambda: FakeApifyIndeedClient()
    app.dependency_overrides[get_job_search_description_parser] = lambda: FakeJobDescriptionParser()
    app.dependency_overrides[get_job_search_resume_matcher] = lambda: FakeMatcher()
    return TestClient(app)


def test_normalize_indeed_item_handles_actor_field_variants() -> None:
    result = normalize_indeed_item(
        {
            "jobKey": "abc123",
            "jobTitle": "Software Engineer",
            "companyName": "Example Systems",
            "formattedLocation": "Maryland",
            "descriptionHtml": "<div><p>Build APIs using Python.</p></div>",
        }
    )

    assert result is not None
    assert result.source_url == "https://www.indeed.com/viewjob?jk=abc123"
    assert result.title == "Software Engineer"
    assert result.company == "Example Systems"
    assert result.raw_description_text == "Build APIs using Python."


def test_indeed_search_returns_results() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/job-search/indeed",
        json={"keyword": "software engineer", "location": "Maryland"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "apify_indeed"
    assert payload["results"][0]["title"] == "Software Engineer"
    assert payload["results"][0]["status"] == "new"


def test_indeed_search_reports_provider_errors() -> None:
    client = create_test_client()
    client.app.dependency_overrides[get_apify_indeed_client] = lambda: FailingApifyIndeedClient()

    response = client.post(
        "/api/v1/job-search/indeed",
        json={"keyword": "software engineer", "location": "Maryland"},
    )

    assert response.status_code == 503
    assert "APIFY_API_TOKEN" in response.json()["detail"]


def test_indeed_search_import_saves_selected_result() -> None:
    client = create_test_client()
    search_response = client.post(
        "/api/v1/job-search/indeed",
        json={"keyword": "software engineer", "location": "Maryland"},
    )
    selected = search_response.json()["results"]

    import_response = client.post(
        "/api/v1/job-search/indeed/import",
        json={"selected_results": selected},
    )

    assert import_response.status_code == 200
    payload = import_response.json()
    assert payload["failed"] == []
    assert payload["imported"][0]["title"] == "Software Engineer"
    assert payload["imported"][0]["match_score"] is None

    jobs = client.get("/api/v1/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["source_url"] == "https://www.indeed.com/viewjob?jk=abc123"

    duplicate_import_response = client.post(
        "/api/v1/job-search/indeed/import",
        json={"selected_results": selected},
    )
    assert duplicate_import_response.status_code == 200
    assert len(client.get("/api/v1/jobs").json()) == 1

    cached_search_response = client.post(
        "/api/v1/job-search/indeed",
        json={"keyword": "software engineer", "location": "Maryland"},
    )
    assert cached_search_response.json()["results"][0]["status"] == "already_cached"


def test_indeed_search_import_can_match_selected_resume_profile() -> None:
    client = create_test_client()
    profile_response = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Backend Resume",
            "resume_data": {
                "headline": "Backend Engineer",
                "summary": "Builds APIs.",
                "experience": ["Built FastAPI services with Python."],
                "skills": ["Python", "FastAPI"],
                "education": [],
                "certifications": [],
                "projects": [],
                "awards": [],
                "publications": [],
                "languages": [],
                "volunteer": [],
                "target_roles": [],
                "notes": [],
            },
            "is_favorite": True,
        },
    )
    assert profile_response.status_code == 200
    search_response = client.post(
        "/api/v1/job-search/indeed",
        json={"keyword": "software engineer", "location": "Maryland"},
    )

    import_response = client.post(
        "/api/v1/job-search/indeed/import",
        json={
            "selected_results": search_response.json()["results"],
            "run_matching": True,
            "resume_profile_id": profile_response.json()["id"],
        },
    )

    assert import_response.status_code == 200
    payload = import_response.json()
    assert payload["failed"] == []
    assert payload["imported"][0]["match_score"] == 8
    jobs = client.get("/api/v1/jobs").json()
    assert jobs[0]["match_data"]["summary"] == "Strong backend match."
