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
from app.modules.job_search import criteria_repository
from app.modules.job_search.models import JobSearchCriterion
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.job_search.router import (
    build_quick_find_recommendations,
    get_job_search_description_parser,
    get_job_search_resume_matcher,
    save_quick_find_recommendations,
)
from app.modules.jobs.models import JobCache, UserSavedJob
from app.modules.jobs.schemas import (
    IndeedJobSearchResult,
    JobDescriptionData,
    QuickFindRequest,
    QuickFindSaveRequest,
)
from app.modules.operations.models import ManagedOperation
from app.modules.profiles import repository as profile_repository
from app.modules.profiles.schemas import ResumeProfileCreateRequest
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest, ResumeJobMatchResponse


class FakeApifyIndeedClient:
    def search(self, *, keyword: str, location: str, max_results: int = 10) -> list[IndeedJobSearchResult]:
        assert keyword == "software engineer"
        assert location == "Maryland"
        assert max_results == 10
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
    def search(self, *, keyword: str, location: str, max_results: int = 10) -> list[IndeedJobSearchResult]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APIFY_API_TOKEN is not configured for the server process.",
        )


class FakeQuickFindProvider:
    def search(self, *, keyword: str, location: str, max_results: int = 5) -> list[IndeedJobSearchResult]:
        assert keyword == "Backend Engineer"
        assert location == "Maryland"
        assert max_results == 5
        return [
            IndeedJobSearchResult(
                external_id="quick123",
                title="Backend Engineer",
                company="Example Systems",
                location="Maryland",
                source_url="https://www.indeed.com/viewjob?jk=quick123",
                summary="Build APIs using Python and PostgreSQL.",
                raw_description_text="Build APIs using Python and PostgreSQL for customer workflows.",
            )
        ]


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


class FailingJobDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        raise AssertionError("Apify import should not parse unless matching is requested")


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


def test_indeed_search_uses_and_marks_selected_saved_criterion() -> None:
    client = create_test_client()
    created = client.post(
        "/api/v1/job-search/criteria",
        json={"keyword": "software engineer", "location": "Maryland"},
    )
    assert created.status_code == 200

    response = client.post(
        "/api/v1/job-search/indeed",
        json={
            "keyword": "ignored keyword",
            "location": "ignored location",
            "search_criterion_id": created.json()["id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["keyword"] == "software engineer"
    assert response.json()["location"] == "Maryland"
    criteria = client.get("/api/v1/job-search/criteria").json()["criteria"]
    assert criteria[0]["last_used_at"] is not None


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
    client.app.dependency_overrides[get_job_search_description_parser] = lambda: FailingJobDescriptionParser()
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
    assert jobs[0]["title"] == "Software Engineer"
    assert jobs[0]["company"] == "Example Systems"
    assert jobs[0]["job_data"] is None

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
            "is_default": True,
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


def test_quick_find_caches_matches_then_saves_only_selected_job() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    identity = AuthenticatedIdentity(
        external_user_id="quick-find-user",
        email="quick-find@example.com",
        display_name="Quick Find User",
        timezone="UTC",
        provider="local",
    )

    with session_factory() as db:
        resume = profile_repository.create_resume_profile(
            db,
            ResumeProfileCreateRequest(
                title="Backend Resume",
                resume_data={
                    "headline": "Backend Engineer",
                    "summary": "Builds APIs.",
                    "experience": ["Built FastAPI services with Python."],
                    "skills": ["Python", "FastAPI"],
                    "target_roles": ["Backend Engineer"],
                },
                is_default=True,
            ),
            identity,
        )
        response = build_quick_find_recommendations(
            QuickFindRequest(resume_profile_id=resume.id, location="Maryland"),
            operation_id=77,
            provider=FakeQuickFindProvider(),
            parser=FakeJobDescriptionParser(),
            matcher=FakeMatcher(),
            db=db,
            identity=identity,
        )

        assert response.keyword == "Backend Engineer"
        assert response.candidates[0].match_score == 8
        assert db.query(JobCache).count() == 1
        assert db.query(UserSavedJob).count() == 0

        operation = ManagedOperation(
            id=77,
            workspace_id=resume.workspace_id,
            user_id=resume.user_id,
            operation_type="quick_find_jobs",
            idempotency_key="quick-find-operation",
            status="succeeded",
            request_payload={},
            result_payload=response.model_dump(mode="json"),
        )
        db.add(operation)
        db.flush()

        saved = save_quick_find_recommendations(
            QuickFindSaveRequest(operation_id=77, jobs_cache_ids=[response.candidates[0].jobs_cache_id]),
            db=db,
            identity=identity,
        )

        assert saved.failed == []
        assert saved.imported[0].match_score == 8
        assert db.query(UserSavedJob).count() == 1


def test_search_criteria_crud_is_soft_deleted() -> None:
    client = create_test_client()

    created = client.post(
        "/api/v1/job-search/criteria",
        json={"keyword": "Data Engineer", "location": "Virginia"},
    )
    assert created.status_code == 200
    criterion_id = created.json()["id"]
    assert created.json()["source"] == "custom"

    listed = client.get("/api/v1/job-search/criteria")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["criteria"]] == [criterion_id]

    updated = client.patch(
        f"/api/v1/job-search/criteria/{criterion_id}",
        json={"keyword": "Senior Data Engineer", "location": "Remote"},
    )
    assert updated.status_code == 200
    assert updated.json()["keyword"] == "Senior Data Engineer"
    assert updated.json()["location"] == "Remote"

    deleted = client.delete(f"/api/v1/job-search/criteria/{criterion_id}")
    assert deleted.status_code == 204
    assert client.get("/api/v1/job-search/criteria").json()["criteria"] == []


def test_active_search_criteria_exclude_legacy_resume_generated_rows() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    identity = AuthenticatedIdentity(
        external_user_id="saved-search-user",
        email="saved-search@example.com",
        display_name="Saved Search User",
        timezone="UTC",
        provider="local",
    )

    with session_factory() as db:
        user, workspace = profile_repository.ensure_account_for_identity(db, identity)
        legacy = JobSearchCriterion(
            workspace_id=workspace.id,
            user_id=user.id,
            keyword="Automatically Generated Role",
            location=None,
            source="resume_generated",
        )
        db.add(legacy)
        explicit = criteria_repository.create_criterion(
            db,
            identity,
            keyword="Data Engineer",
            location="Maryland",
            resume_profile_id=None,
        )
        db.flush()

        assert [item["id"] for item in criteria_repository.list_criteria(db, identity)] == [explicit["id"]]
        assert criteria_repository.get_criterion(db, identity, legacy.id) is None
