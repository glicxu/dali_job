from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.resume_job_match import job_url_import
from app.modules.resume_job_match import router as match_router
from app.modules.resume_job_match.adapters import REGISTERED_ADAPTERS, AdapterExtraction
from app.modules.resume_job_match.adapters.registry import extract_from_adapters
from app.modules.resume_job_match.extraction_quality import measure_extraction_quality
from app.modules.resume_job_match.job_url_import import (
    RenderableFetchError,
    extract_job_description_from_html,
    extract_job_result_from_html,
    extract_job_page_text_from_html,
    extract_job_links_from_html,
    extract_next_page_url_from_html,
    fetch_job_description_from_url,
    fetch_job_page_text_from_url,
    normalize_job_sections,
    validate_public_job_url,
)
from app.modules.resume_job_match.router import get_match_job_description_parser, get_resume_job_matcher
from app.modules.resume_job_match.schemas import (
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
    SupportedRequirement,
    UnsupportedRequirement,
)


JOB_PAGE_FIXTURES = Path(__file__).parent / "fixtures" / "job_pages"


class FakeMatcher:
    def compare(self, request: ResumeJobMatchRequest) -> ResumeJobMatchResponse:
        assert request.resume_text is not None
        assert request.job_description_text is not None
        assert "FastAPI" in request.resume_text
        assert "PostgreSQL" in request.job_description_text
        return ResumeJobMatchResponse(
            id=None,
            match_score=7,
            summary="Good backend match with one infrastructure gap.",
            matched_skills=["Python", "FastAPI"],
            missing_skills=["Kubernetes"],
            matched_keywords=["API", "PostgreSQL"],
            missing_keywords=["Kubernetes"],
            supported_requirements=[
                SupportedRequirement(
                    requirement="Build APIs",
                    resume_evidence="Built FastAPI services.",
                    confidence=0.9,
                )
            ],
            unsupported_requirements=[
                UnsupportedRequirement(
                    requirement="Operate Kubernetes workloads",
                    reason="No Kubernetes evidence found.",
                )
            ],
            recommended_resume_updates=["Mention PostgreSQL work more clearly if accurate."],
        )


class FakeLowScoreMatcher:
    def compare(self, request: ResumeJobMatchRequest) -> ResumeJobMatchResponse:
        assert request.resume_text is not None
        assert request.job_description_text is not None
        return ResumeJobMatchResponse(
            id=None,
            match_score=3,
            summary="Low match with major gaps.",
            matched_skills=[],
            missing_skills=["PostgreSQL"],
            matched_keywords=[],
            missing_keywords=["PostgreSQL"],
            supported_requirements=[],
            unsupported_requirements=[
                UnsupportedRequirement(
                    requirement="Build APIs with PostgreSQL",
                    reason="Resume does not show PostgreSQL evidence.",
                )
            ],
            recommended_resume_updates=[],
        )


class FakeJobDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        assert "PostgreSQL" in raw_description_text
        return JobDescriptionData(
            title="Backend Engineer",
            company="Example Co",
            summary="Build APIs using PostgreSQL.",
            responsibilities=["Build APIs using PostgreSQL."],
            required_skills=["PostgreSQL"],
            preferred_skills=["Kubernetes"],
            required_experience=["Backend API development"],
            preferred_experience=[],
            education=[],
            certifications=[],
            tools_and_technologies=["PostgreSQL", "Kubernetes"],
            keywords=["API", "PostgreSQL", "Kubernetes"],
            seniority_level="",
            employment_type="",
            security_clearance="",
            work_location="",
            salary_range="",
            application_deadline="",
        )


class FailingJobDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        raise AssertionError("cached job URL should not be parsed again")


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
    app.dependency_overrides[get_resume_job_matcher] = lambda: FakeMatcher()
    app.dependency_overrides[get_match_job_description_parser] = lambda: FakeJobDescriptionParser()
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app)


def create_document_test_client() -> tuple[TestClient, str]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        from app.modules.profiles.repository import ensure_dev_account

        user, workspace = ensure_dev_account(session)
        document = Document(
            workspace_id=workspace.id,
            user_id=user.id,
            title="Master Resume",
            document_type="resume",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            file_name="resume.txt",
            content_type="text/plain",
            size_bytes=42,
            sha256="a" * 64,
            storage_path="resume.txt",
            extracted_text="Built FastAPI services with Python.",
        )
        session.add(version)
        session.commit()
        document_id = document.id

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
    app.dependency_overrides[get_resume_job_matcher] = lambda: FakeMatcher()
    app.dependency_overrides[get_match_job_description_parser] = lambda: FakeJobDescriptionParser()
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app), document_id


def test_resume_job_match_returns_score_and_skills() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_text": "Built FastAPI services with Python.",
            "job_title": "Senior API Engineer",
            "job_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_score"] == 7
    assert payload["score_scale"] == "0-10"
    assert payload["saved_job_id"] is not None
    assert payload["saved_match_id"] is not None
    assert payload["matched_skills"] == ["Python", "FastAPI"]
    assert payload["missing_skills"] == ["Kubernetes"]
    assert payload["supported_requirements"][0]["confidence"] == 0.9
    assert payload["unsupported_requirements"][0]["requirement"] == "Operate Kubernetes workloads"
    jobs = client.get("/api/v1/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["source_url"] is None
    assert jobs[0]["jobs_cache_id"] is None
    assert jobs[0]["user_edited_job_id"] is not None
    assert jobs[0]["title"] == "Senior API Engineer"
    assert jobs[0]["job_data"]["title"] == "Senior API Engineer"
    assert jobs[0]["job_data"]["required_skills"] == ["PostgreSQL"]
    assert jobs[0]["match_score"] == 7
    assert jobs[0]["matched_resume_source"] == "pasted_text"


def test_bulk_saved_job_match_matches_selected_jobs_with_resume_profile() -> None:
    client = create_test_client()
    profile_response = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Backend Resume",
            "resume_data": {
                "headline": "Backend Engineer",
                "summary": "Built FastAPI services with Python.",
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
    job_payload = {
        "title": "Backend Engineer",
        "company": "Example Co",
        "raw_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        "job_data": {
            "title": "Backend Engineer",
            "company": "Example Co",
            "summary": "Build APIs using PostgreSQL.",
            "responsibilities": ["Build APIs using PostgreSQL."],
            "required_skills": ["PostgreSQL"],
            "preferred_skills": ["Kubernetes"],
            "required_experience": ["Backend API development"],
            "preferred_experience": [],
            "education": [],
            "certifications": [],
            "tools_and_technologies": ["PostgreSQL", "Kubernetes"],
            "keywords": ["API", "PostgreSQL", "Kubernetes"],
            "seniority_level": "",
            "employment_type": "",
            "security_clearance": "",
            "work_location": "",
            "salary_range": "",
            "application_deadline": "",
        },
    }
    first_job = client.post("/api/v1/jobs", json=job_payload)
    second_job = client.post("/api/v1/jobs", json={**job_payload, "title": "API Engineer"})
    assert first_job.status_code == 200
    assert second_job.status_code == 200

    response = client.post(
        "/api/v1/resume-job-matches/saved-jobs",
        json={
            "user_job_ids": [first_job.json()["id"], second_job.json()["id"]],
            "resume_profile_id": profile_response.json()["id"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["failed"] == []
    assert len(payload["matched"]) == 2
    assert payload["matched"][0]["match"]["match_score"] == 7
    assert payload["matched"][0]["match"]["job_saved"] is True
    assert payload["matched"][0]["saved_match_id"] is not None
    jobs = client.get("/api/v1/jobs").json()
    assert {job["match_score"] for job in jobs} == {7}
    first_job_id = first_job.json()["id"]
    history = client.get(f"/api/v1/jobs/{first_job_id}/matches").json()["matches"]
    assert len(history) == 1
    assert history[0]["match_origin"] == "manual_rerun"
    assert client.get("/api/v1/account/usage").json()["entries"] == []
    assert client.get("/api/v1/match-inbox").json()["items"] == []

    revised_resume = profile_response.json()["resume_data"]
    revised_resume["skills"] = ["Python", "FastAPI", "Kubernetes"]
    assert client.patch(
        f"/api/v1/resume-profiles/{profile_response.json()['id']}",
        json={"resume_data": revised_resume},
    ).status_code == 200
    rerun = client.post(
        "/api/v1/resume-job-matches/saved-jobs",
        json={
            "user_job_ids": [first_job_id],
            "resume_profile_id": profile_response.json()["id"],
        },
    )
    assert rerun.status_code == 200
    rerun_history = client.get(f"/api/v1/jobs/{first_job_id}/matches").json()["matches"]
    assert len(rerun_history) == 2
    assert rerun_history[0]["match_origin"] == "manual_rerun"
    assert rerun_history[0]["resume_data_snapshot"]["skills"] == [
        "Python",
        "FastAPI",
        "Kubernetes",
    ]
    assert rerun_history[1]["resume_data_snapshot"]["skills"] == ["Python", "FastAPI"]
    assert client.get("/api/v1/account/usage").json()["entries"] == []
    assert client.get("/api/v1/match-inbox").json()["items"] == []


def test_manual_saved_job_is_user_owned_editable_and_matchable() -> None:
    client = create_test_client()
    profile_response = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Backend Resume",
            "resume_data": {
                "headline": "Backend Engineer",
                "summary": "Built FastAPI services with Python.",
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
        },
    )
    assert profile_response.status_code == 200

    job_payload = {
        "title": "Backend Engineer",
        "company": "Manual Co",
        "raw_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        "job_data": {
            "title": "Backend Engineer",
            "company": "Manual Co",
            "summary": "Build APIs using PostgreSQL.",
            "responsibilities": ["Build APIs using PostgreSQL."],
            "required_skills": ["PostgreSQL"],
            "preferred_skills": ["Kubernetes"],
            "required_experience": ["Backend API development"],
            "preferred_experience": [],
            "education": [],
            "certifications": [],
            "tools_and_technologies": ["PostgreSQL", "Kubernetes"],
            "keywords": ["API", "PostgreSQL", "Kubernetes"],
            "seniority_level": "",
            "employment_type": "",
            "security_clearance": "",
            "work_location": "",
            "salary_range": "",
            "application_deadline": "",
        },
    }
    create_response = client.post("/api/v1/jobs", json=job_payload)
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["jobs_cache_id"] is None
    assert created["user_edited_job_id"] is not None
    assert created["title"] == "Backend Engineer"

    update_response = client.patch(
        f"/api/v1/jobs/{created['id']}",
        json={
            **job_payload,
            "title": "Edited Backend Engineer",
            "notes": "User-specific correction.",
            "job_data": {
                **job_payload["job_data"],
                "title": "Edited Backend Engineer",
                "required_skills": ["PostgreSQL", "FastAPI"],
            },
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["jobs_cache_id"] is None
    assert updated["user_edited_job_id"] == created["user_edited_job_id"]
    assert updated["title"] == "Edited Backend Engineer"
    assert updated["notes"] == "User-specific correction."
    assert updated["job_data"]["required_skills"] == ["PostgreSQL", "FastAPI"]

    match_response = client.post(
        "/api/v1/resume-job-matches/saved-jobs",
        json={
            "user_job_ids": [created["id"]],
            "resume_profile_id": profile_response.json()["id"],
        },
    )
    assert match_response.status_code == 200
    payload = match_response.json()
    assert payload["failed"] == []
    assert payload["matched"][0]["jobs_cache_id"] is None
    assert payload["matched"][0]["title"] == "Edited Backend Engineer"
    assert payload["matched"][0]["match"]["match_score"] == 7


def test_resume_job_match_rejects_empty_inputs() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/resume-job-matches",
        json={"resume_text": "", "job_description_text": ""},
    )

    assert response.status_code == 422


def test_resume_job_match_uses_document_and_job_url(monkeypatch) -> None:
    client, document_id = create_document_test_client()
    monkeypatch.setattr(
        match_router,
        "fetch_job_description_from_url",
        lambda _url: "Build APIs using PostgreSQL and Kubernetes.",
    )

    response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_document_id": document_id,
            "job_url": "https://example.com/jobs/backend-engineer",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_score"] == 7
    assert payload["job_saved"] is True
    assert payload["saved_job_id"] is not None
    assert payload["saved_match_id"] is not None
    jobs = client.get("/api/v1/jobs").json()
    assert jobs[0]["source_url"] == "https://example.com/jobs/backend-engineer"
    assert jobs[0]["match_score"] == 7
    assert jobs[0]["matched_resume_document_id"] == document_id
    assert jobs[0]["matched_resume_source"] == "document"


def test_resume_job_match_uses_saved_resume_profile() -> None:
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
    resume_profile_id = profile_response.json()["id"]

    response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_profile_id": resume_profile_id,
            "job_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_score"] == 7
    jobs = client.get("/api/v1/jobs").json()
    assert jobs[0]["matched_resume_profile_id"] == resume_profile_id
    assert jobs[0]["matched_resume_source"] == "resume_profile"


def test_resume_job_match_reuses_cached_job_url(monkeypatch) -> None:
    client = create_test_client()
    monkeypatch.setattr(
        match_router,
        "fetch_job_description_from_url",
        lambda _url: "Build APIs using PostgreSQL and Kubernetes.",
    )

    first_response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_text": "Built FastAPI services with Python.",
            "job_url": "https://example.com/jobs/backend-engineer",
        },
    )

    assert first_response.status_code == 200
    client.app.dependency_overrides[get_match_job_description_parser] = lambda: FailingJobDescriptionParser()
    monkeypatch.setattr(
        match_router,
        "fetch_job_description_from_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("cached job URL should not be fetched again")),
    )

    second_response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_text": "Built FastAPI services with Python.",
            "job_url": "https://example.com/jobs/backend-engineer",
        },
    )

    assert second_response.status_code == 200
    assert second_response.json()["saved_job_id"] == first_response.json()["saved_job_id"]
    assert len(client.get("/api/v1/jobs").json()) == 1


def test_resume_job_match_low_score_returns_pending_job_without_saving() -> None:
    client = create_test_client()
    client.app.dependency_overrides[get_resume_job_matcher] = lambda: FakeLowScoreMatcher()

    response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_text": "Built static websites with HTML.",
            "job_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_score"] == 3
    assert payload["job_saved"] is False
    assert payload["saved_job_id"] is None
    assert payload["saved_match_id"] is None
    assert payload["pending_job"]["match_score"] == 3
    assert payload["pending_job"]["matched_resume_source"] == "pasted_text"
    assert client.get("/api/v1/jobs").json() == []

    save_response = client.post("/api/v1/resume-job-matches/pending-job", json=payload["pending_job"])

    assert save_response.status_code == 200
    saved_payload = save_response.json()
    assert saved_payload["saved_job_id"] is not None
    assert saved_payload["saved_match_id"] is not None
    saved_jobs = client.get("/api/v1/jobs").json()
    assert len(saved_jobs) == 1
    assert saved_jobs[0]["match_score"] == 3
    assert saved_jobs[0]["matched_resume_source"] == "pasted_text"


def test_resume_job_match_rejects_both_job_sources() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_text": "Built FastAPI services with Python.",
            "job_url": "https://example.com/jobs/backend-engineer",
            "job_description_text": "Build APIs using PostgreSQL.",
        },
    )

    assert response.status_code == 422


def test_job_url_extract_endpoint_returns_scraped_text(monkeypatch) -> None:
    client = create_test_client()
    monkeypatch.setattr(
        match_router,
        "fetch_job_description_from_url",
        lambda _url: "Backend Engineer job text with PostgreSQL.",
    )

    response = client.post(
        "/api/v1/resume-job-matches/job-url-extract",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_url"] == "https://example.com/jobs/backend-engineer"
    assert payload["extracted_text"] == "Backend Engineer job text with PostgreSQL."
    assert payload["character_count"] == len("Backend Engineer job text with PostgreSQL.")


def test_fetch_job_description_uses_rendered_fallback_after_blocked_static_fetch(monkeypatch) -> None:
    def blocked_fetch(_url: str) -> tuple[str, str]:
        raise RenderableFetchError(401, "Unauthorized")

    rendered_html = """
    <html><body>
      <nav>Find salaries Search jobs</nav>
      <div class="jobsearch-RightPane css-6iabie eu4oa1w0">
        <h1>Software Engineer</h1>
        <div id="jobDescriptionText">
          <p>Build backend services with Python, PostgreSQL, and APIs for production systems.</p>
          <p>Design reliable software, collaborate with product teams, and improve operational quality.</p>
          <p>Experience with testing, cloud deployments, and system design is required.</p>
        </div>
      </div>
    </body></html>
    """
    monkeypatch.setattr(job_url_import, "_fetch_url_text", blocked_fetch)
    monkeypatch.setattr(job_url_import, "_fetch_rendered_html", lambda _url: rendered_html)

    text = fetch_job_description_from_url("https://www.indeed.com/viewjob?jk=1cf252337cfd0eae")

    assert "PostgreSQL" in text
    assert "Design reliable software" in text
    assert "Find salaries" not in text


def test_fetch_job_page_text_uses_rendered_fallback_after_blocked_static_fetch(monkeypatch) -> None:
    def blocked_fetch(_url: str) -> tuple[str, str]:
        raise RenderableFetchError(401, "Unauthorized")

    rendered_html = """
    <html><body>
      <div class="jobsearch-RightPane css-6iabie eu4oa1w0">
        <h1>Data Engineer</h1>
        <div id="jobDescriptionText">
          <p>Build data pipelines with Python, SQL, orchestration, and warehouse modeling.</p>
          <p>Partner with analytics, product, and platform teams to deliver reliable datasets.</p>
          <p>Own monitoring, testing, documentation, incident response, and production support.</p>
          <p>Use cloud infrastructure, version control, code review, and deployment automation.</p>
        </div>
      </div>
    </body></html>
    """
    monkeypatch.setattr(job_url_import, "_fetch_url_text", blocked_fetch)
    monkeypatch.setattr(job_url_import, "_fetch_rendered_html", lambda _url: rendered_html)

    text = fetch_job_page_text_from_url("https://www.indeed.com/viewjob?jk=1cf252337cfd0eae")

    assert "Data Engineer" in text
    assert "Build data pipelines" in text
    assert len(text) >= 200


def test_job_page_text_rejects_sign_in_page() -> None:
    html = """
    <html><body>
      <main>
        <h1>Sign in to your Indeed account</h1>
        <p>New to Indeed? Create an account.</p>
        <label>Email address</label>
        <label>Password</label>
        <a>Forgot password?</a>
        <button>Continue</button>
      </main>
    </body></html>
    """

    try:
        extract_job_page_text_from_html(html)
    except Exception as exc:
        assert "sign-in" in str(exc) or "sign-in" in getattr(exc, "detail", "")
    else:
        raise AssertionError("sign-in page should not be accepted as job text")


def test_job_description_rejects_sign_in_page() -> None:
    html = """
    <html><body>
      <main>
        <h1>Create an account or sign in</h1>
        <p>Indeed account authentication is required.</p>
        <label>Email address</label>
        <label>Password</label>
        <a>Forgot password?</a>
      </main>
    </body></html>
    """

    try:
        extract_job_description_from_html(html)
    except Exception as exc:
        assert "sign-in" in str(exc) or "sign-in" in getattr(exc, "detail", "")
    else:
        raise AssertionError("sign-in page should not be accepted as job description")


def test_job_page_text_rejects_security_check_page() -> None:
    html = """
    <html><body>
      <main>
        <h1>Security Check - Indeed.com</h1>
        <a>Find jobs</a>
        <a>Company Reviews</a>
        <a>Find salaries</a>
        <a>Sign in</a>
        <p>Additional Verification Required</p>
        <p>Your Ray ID for this request is a13620124b275806.</p>
        <p>Verification successful. Waiting for security check to complete.</p>
      </main>
    </body></html>
    """

    try:
        extract_job_page_text_from_html(html)
    except Exception as exc:
        assert "sign-in" in str(exc) or "sign-in" in getattr(exc, "detail", "")
    else:
        raise AssertionError("security-check page should not be accepted as job text")


def test_extract_job_description_from_json_ld_jobposting() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@type": "JobPosting",
      "title": "Backend Engineer",
      "hiringOrganization": {"name": "Example Co"},
      "description": "Build Python APIs with PostgreSQL and FastAPI for customer workflows. This role owns backend services, testing, and deployment quality.",
      "skills": ["Python", "PostgreSQL", "FastAPI"]
    }
    </script>
    </head><body>Navigation</body></html>
    """

    text = extract_job_description_from_html(html)

    assert "Backend Engineer" in text
    assert "PostgreSQL" in text
    assert "FastAPI" in text


def test_extract_job_description_strips_html_inside_json_ld_description() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@type": "JobPosting",
      "title": "Data Engineer",
      "description": "<p>Duties</p><ul><li>Build ETL pipelines.</li><li>Use SQL and Python.</li></ul><p>Qualifications</p><p>Cloud experience required.</p>"
    }
    </script>
    </head><body></body></html>
    """

    text = extract_job_description_from_html(html)

    assert "<p>" not in text
    assert "<li>" not in text
    assert "Build ETL pipelines." in text
    assert "Use SQL and Python." in text
    assert "Cloud experience required." in text


def test_extract_job_description_prefers_job_detail_body_over_navigation() -> None:
    html = """
    <html>
      <body>
        <header>
          <a>Home</a>
          <a>Job categories</a>
          <a>Teams</a>
          <a>Locations</a>
        </header>
        <div id="job-detail">
          <div class="apply-header">
            <a>Apply now</a>
            <a>Share this job</a>
          </div>
          <div id="job-detail-body">
            <div class="content">
              <div class="section"><h2>Description</h2>
                <p>Lead a software engineering team building security products for customers.</p>
              </div>
              <div class="section"><h2>Basic Qualifications</h2>
                <p>Experience in engineering team management.</p>
                <p>Experience designing reliable distributed systems.</p>
              </div>
              <div class="section"><h2>Preferred Qualifications</h2>
                <p>Experience with cloud services and operational excellence.</p>
              </div>
            </div>
          </div>
        </div>
        <footer>
          <a>View all jobs</a>
          <a>Privacy notice</a>
        </footer>
      </body>
    </html>
    """

    text = extract_job_description_from_html(html)

    assert "Lead a software engineering team" in text
    assert "Required Qualifications" in text
    assert "Preferred Qualifications" in text
    assert "Job categories" not in text
    assert "Home" not in text
    assert "View all jobs" not in text


def test_extract_job_description_trims_legal_footer_sections() -> None:
    html = """
    <html><body>
      <div id="job-detail-body">
        <div class="content">
          <h2>Description</h2>
          <p>Build backend services for important customer workflows across data ingestion, search, reporting, and internal platform automation.</p>
          <h2>Basic Qualifications</h2>
          <p>Experience with Python, SQL, distributed systems, operational ownership, testing practices, and cross-functional technical communication.</p>
          <p>Our inclusive culture empowers employees to deliver results.</p>
          <p>Learn more about our benefits at example.com/benefits.</p>
        </div>
      </div>
    </body></html>
    """

    text = extract_job_description_from_html(html)

    assert "Build backend services" in text
    assert "Required Qualifications" in text
    assert "Our inclusive culture empowers" not in text
    assert "benefits" not in text


def test_job_extraction_regression_fixtures_preserve_required_sections() -> None:
    amazon = extract_job_result_from_html(
        (JOB_PAGE_FIXTURES / "amazon_job.html").read_text(encoding="utf-8"),
        source_url="https://jobs.example.test/en/jobs/1001/software-development-engineer",
    )
    usajobs = extract_job_result_from_html(
        (JOB_PAGE_FIXTURES / "usajobs_job.html").read_text(encoding="utf-8"),
        source_url="https://www.usajobs.gov/job/1001",
    )

    assert amazon.title == "Software Development Engineer"
    assert "Required Qualifications" in amazon.focused_text
    assert "Job categories" not in amazon.focused_text
    assert usajobs.extraction_method == "json_ld"
    assert "Education" in usajobs.focused_text
    assert "equivalent qualifying experience" in usajobs.focused_text
    assert "Application deadline: 2026-09-03" in usajobs.focused_text


@pytest.mark.parametrize(
    ("adapter_name", "fixture_name", "source_url", "expected_title", "expected_text"),
    [
        (
            "greenhouse",
            "greenhouse_job.html",
            "https://job-boards.greenhouse.io/northstar/jobs/1001",
            "Platform Engineer",
            "Kubernetes",
        ),
        (
            "lever",
            "lever_job.html",
            "https://jobs.lever.co/beacon/lever-1001",
            "Backend Software Engineer",
            "API design",
        ),
        (
            "workday",
            "workday_job.html",
            "https://meridian.wd5.myworkdayjobs.com/jobs/job/security-engineer",
            "Security Automation Engineer",
            "incident response",
        ),
        (
            "smartrecruiters",
            "smartrecruiters_job.html",
            "https://jobs.smartrecruiters.com/AtlasAnalytics/1001-data-pipeline-engineer",
            "Data Pipeline Engineer",
            "cloud data platforms",
        ),
        (
            "ashby",
            "ashby_job.html",
            "https://jobs.ashbyhq.com/harbor/ashby-1001",
            "Product Software Engineer",
            "TypeScript",
        ),
        (
            "icims",
            "icims_job.html",
            "https://careers-summit.icims.com/jobs/1001/cloud-infrastructure-engineer/job",
            "Cloud Infrastructure Engineer",
            "infrastructure as code",
        ),
    ],
)
def test_ats_adapters_return_shared_candidate_contract(
    adapter_name: str,
    fixture_name: str,
    source_url: str,
    expected_title: str,
    expected_text: str,
) -> None:
    html = (JOB_PAGE_FIXTURES / fixture_name).read_text(encoding="utf-8")

    extractions = extract_from_adapters(url=source_url, html=html)
    result = extract_job_result_from_html(html, source_url=source_url)

    assert len(extractions) == 1
    assert isinstance(extractions[0], AdapterExtraction)
    assert extractions[0].adapter_name == adapter_name
    assert result.extraction_method == f"ats_{adapter_name}"
    assert result.title == expected_title
    assert expected_text in result.focused_text
    assert f"source_adapter:{adapter_name}" in result.warnings


def test_ats_adapter_registry_has_unique_names_and_matches_protocol() -> None:
    names = [adapter.name for adapter in REGISTERED_ADAPTERS]

    assert names == ["greenhouse", "lever", "workday", "smartrecruiters", "ashby", "icims"]
    assert len(names) == len(set(names))


def test_failed_ats_adapter_does_not_block_generic_extraction() -> None:
    class FailingAdapter:
        name = "failing"

        def matches(self, url: str, html: str | None) -> bool:
            return True

        def extract(self, *, url: str, html: str, network=None) -> AdapterExtraction | None:
            raise RuntimeError("adapter failed")

    html = (JOB_PAGE_FIXTURES / "usajobs_job.html").read_text(encoding="utf-8")

    assert extract_from_adapters(
        url="https://example.com/jobs/1001",
        html=html,
        adapters=(FailingAdapter(),),
    ) == []
    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/1001")
    assert result.extraction_method == "json_ld"


@pytest.mark.parametrize(
    ("source_name", "fixture_name", "source_url", "required_terms", "excluded_terms", "expected_sections"),
    [
        (
            "amazon_style",
            "amazon_job.html",
            "https://jobs.example.test/en/jobs/1001/software-development-engineer",
            ("distributed systems", "cloud services"),
            ("Job categories", "View all jobs"),
            ("required_qualifications", "preferred_qualifications"),
        ),
        (
            "usajobs_style",
            "usajobs_job.html",
            "https://www.usajobs.gov/job/1001",
            ("data integrations", "equivalent qualifying experience"),
            ("Saved searches",),
            ("responsibilities", "required_qualifications", "education", "application_details"),
        ),
        (
            "greenhouse",
            "greenhouse_job.html",
            "https://job-boards.greenhouse.io/northstar/jobs/1001",
            ("observability", "Kubernetes"),
            ("candidate login",),
            (),
        ),
        (
            "lever",
            "lever_job.html",
            "https://jobs.lever.co/beacon/lever-1001",
            ("operate production services", "API design"),
            ("related jobs",),
            (),
        ),
        (
            "workday",
            "workday_job.html",
            "https://meridian.wd5.myworkdayjobs.com/jobs/job/security-engineer",
            ("security tools", "incident response"),
            ("sign in",),
            (),
        ),
        (
            "smartrecruiters",
            "smartrecruiters_job.html",
            "https://jobs.smartrecruiters.com/AtlasAnalytics/1001-data-pipeline-engineer",
            ("streaming pipelines", "cloud data platforms"),
            ("all company jobs",),
            (),
        ),
        (
            "ashby",
            "ashby_job.html",
            "https://jobs.ashbyhq.com/harbor/ashby-1001",
            ("accessible interfaces", "TypeScript"),
            ("open roles",),
            (),
        ),
        (
            "icims",
            "icims_job.html",
            "https://careers-summit.icims.com/jobs/1001/cloud-infrastructure-engineer/job",
            ("observability", "infrastructure as code"),
            ("join talent community",),
            (),
        ),
    ],
)
def test_fixture_extraction_quality_metrics(
    source_name: str,
    fixture_name: str,
    source_url: str,
    required_terms: tuple[str, ...],
    excluded_terms: tuple[str, ...],
    expected_sections: tuple[str, ...],
) -> None:
    result = extract_job_result_from_html(
        (JOB_PAGE_FIXTURES / fixture_name).read_text(encoding="utf-8"),
        source_url=source_url,
    )

    metrics = measure_extraction_quality(
        result,
        source_name=source_name,
        required_terms=required_terms,
        excluded_terms=excluded_terms,
        expected_sections=expected_sections,
    )

    assert metrics.passed
    assert metrics.confidence >= job_url_import.MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE


def test_job_extraction_logs_safe_versioned_success_diagnostics(monkeypatch, caplog) -> None:
    html = (JOB_PAGE_FIXTURES / "usajobs_job.html").read_text(encoding="utf-8")
    monkeypatch.setattr(job_url_import, "_fetch_url_text", lambda _url: ("text/html", html))
    caplog.set_level(logging.INFO, logger="dalijob.job_extraction")

    result = job_url_import.fetch_job_result_from_url(
        "https://www.usajobs.gov/job/1001?token=do-not-log-this"
    )

    assert result.extractor_version == job_url_import.JOB_EXTRACTOR_VERSION
    assert "extractor_version=2" in caplog.text
    assert "host=www.usajobs.gov" in caplog.text
    assert "outcome=succeeded" in caplog.text
    assert "method=json_ld" in caplog.text
    assert "confidence_band=high" in caplog.text
    assert "path=static" in caplog.text
    assert "failure_category=none" in caplog.text
    assert "do-not-log-this" not in caplog.text
    assert "equivalent qualifying experience" not in caplog.text


def test_job_extraction_logs_normalized_failure_without_error_detail(monkeypatch, caplog) -> None:
    def blocked_fetch(_url: str) -> tuple[str, str]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The page returned a sign-in verification screen containing secret-detail.",
        )

    monkeypatch.setattr(job_url_import, "_fetch_url_text", blocked_fetch)
    caplog.set_level(logging.WARNING, logger="dalijob.job_extraction")

    with pytest.raises(HTTPException):
        job_url_import.fetch_job_result_from_url("https://example.com/jobs/blocked?secret=query-value")

    assert "outcome=failed" in caplog.text
    assert "failure_category=access_gate" in caplog.text
    assert "secret-detail" not in caplog.text
    assert "query-value" not in caplog.text


def test_job_extraction_diagnostics_do_not_mask_invalid_url_failure(monkeypatch, caplog) -> None:
    def rejected_fetch(_url: str) -> tuple[str, str]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job URL host is not allowed.",
        )

    monkeypatch.setattr(job_url_import, "_fetch_url_text", rejected_fetch)
    caplog.set_level(logging.WARNING, logger="dalijob.job_extraction")

    with pytest.raises(HTTPException) as exc_info:
        job_url_import.fetch_job_result_from_url("https://[invalid-host")

    assert exc_info.value.status_code == 400
    assert "host=invalid" in caplog.text
    assert "failure_category=invalid_url_or_network_policy" in caplog.text


def test_job_extraction_separates_focused_text_from_broad_visible_text() -> None:
    html = """
    <html><head><meta property="og:title" content="Platform Engineer"></head><body>
      <nav>Home Teams Locations Candidate login Search all jobs</nav>
      <div id="job-detail-body">
        <h2>Description</h2>
        <p>Build reliable platform services for engineering teams and production workloads.</p>
        <h2>Requirements</h2>
        <p>Experience with Python, Kubernetes, observability, testing, and incident response.</p>
        <h2>Preferred Qualifications</h2>
        <p>Experience designing internal developer platforms and cloud infrastructure.</p>
      </div>
    </body></html>
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/platform-engineer")

    assert "Candidate login" in (result.raw_visible_text or "")
    assert "Candidate login" not in result.focused_text
    assert "Platform Engineer" in result.focused_text
    assert result.confidence >= job_url_import.MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE


def test_fetch_job_description_renders_low_confidence_success_page(monkeypatch) -> None:
    static_html = """
    <html><body><main>
      <h1>Careers</h1>
      <p>Explore teams, offices, employee stories, events, and opportunities across our organization.</p>
      <p>Use search and filters to find openings that fit your interests and preferred location.</p>
      <p>Join our talent community to receive general company news and career updates.</p>
    </main></body></html>
    """
    rendered_html = """
    <html><body><div id="job-detail-body">
      <h1>Backend Engineer</h1>
      <h2>Description</h2>
      <p>Build secure Python APIs and PostgreSQL services for customer workflows.</p>
      <h2>Responsibilities</h2>
      <p>Design, test, deploy, monitor, and maintain reliable distributed systems.</p>
      <h2>Required Qualifications</h2>
      <p>Professional backend engineering experience with cloud infrastructure.</p>
    </div></body></html>
    """
    rendered_calls: list[str] = []
    monkeypatch.setattr(job_url_import, "_fetch_url_text", lambda _url: ("text/html", static_html))
    monkeypatch.setattr(
        job_url_import,
        "_fetch_rendered_html",
        lambda url: rendered_calls.append(url) or rendered_html,
    )

    text = fetch_job_description_from_url("https://example.com/jobs/backend-engineer")

    assert rendered_calls == ["https://example.com/jobs/backend-engineer"]
    assert "PostgreSQL" in text
    assert "talent community" not in text


def test_fetch_job_description_skips_render_for_high_confidence_static_page(monkeypatch) -> None:
    static_html = (JOB_PAGE_FIXTURES / "usajobs_job.html").read_text(encoding="utf-8")
    monkeypatch.setattr(job_url_import, "_fetch_url_text", lambda _url: ("text/html", static_html))

    def unexpected_render(_url: str) -> str:
        raise AssertionError("high-confidence structured data should not invoke Playwright")

    monkeypatch.setattr(job_url_import, "_fetch_rendered_html", unexpected_render)

    text = fetch_job_description_from_url("https://www.usajobs.gov/job/1001")

    assert "Data Solutions Developer" in text
    assert "Education" in text


def test_extract_job_from_microdata() -> None:
    html = """
    <html><body>
      <article itemscope itemtype="https://schema.org/JobPosting">
        <h1 itemprop="title">Security Engineer</h1>
        <span itemprop="hiringOrganization">Example Security</span>
        <span itemprop="jobLocation">Baltimore, Maryland</span>
        <div itemprop="description">
          <p>Protect production services and improve security engineering practices.</p>
        </div>
        <div itemprop="responsibilities">Build detection, response, and vulnerability-management automation.</div>
        <div itemprop="qualifications">Experience with cloud security, Python, and incident response.</div>
      </article>
    </body></html>
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/security-engineer")

    assert result.extraction_method == "microdata"
    assert result.title == "Security Engineer"
    assert result.company == "Example Security"
    assert "vulnerability-management" in result.focused_text


def test_extract_job_from_nested_embedded_application_state() -> None:
    html = """
    <html><head>
      <script id="__NEXT_DATA__" type="application/json">
      {
        "props": {
          "pageProps": {
            "job": {
              "jobId": "ABC-123",
              "jobTitle": "Machine Learning Engineer",
              "companyName": "Example AI",
              "formattedLocation": "Remote, US",
              "jobDescription": "Build and operate production machine-learning services for customer-facing products.",
              "responsibilities": ["Develop model-serving APIs.", "Monitor model and service quality."],
              "requiredQualifications": ["Python experience", "Production ML experience"]
            }
          }
        }
      }
      </script>
    </head><body><div id="application-shell">Loading job details.</div></body></html>
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/ABC-123")

    assert result.extraction_method == "embedded_json"
    assert result.title == "Machine Learning Engineer"
    assert result.company == "Example AI"
    assert "Production ML experience" in result.focused_text


def test_section_aliases_normalize_unconventional_job_headings() -> None:
    sections = normalize_job_sections(
        """
        The Opportunity
        Build software used by customer support teams.
        Your Impact
        Own APIs, testing, deployment, and operational quality.
        What You Bring
        Experience with Python, SQL, and distributed systems.
        Nice to Have
        Experience with Kubernetes and event-driven systems.
        """
    )

    assert sections["summary"] == ["Build software used by customer support teams."]
    assert sections["responsibilities"] == ["Own APIs, testing, deployment, and operational quality."]
    assert "Python" in sections["required_qualifications"][0]
    assert "Kubernetes" in sections["preferred_qualifications"][0]


def test_section_aware_shortening_preserves_late_education_section() -> None:
    oversized_summary = " ".join(["Build reliable software systems for customer workflows."] * 1_200)
    html = f"""
    <html><head><script type="application/ld+json">
    {{
      "@type": "JobPosting",
      "title": "Senior Software Engineer",
      "hiringOrganization": {{"name": "Example Systems"}},
      "description": {json.dumps(oversized_summary)},
      "responsibilities": "Design, test, deploy, and operate distributed services.",
      "qualifications": "Seven years of professional software engineering experience.",
      "educationRequirements": "Bachelor's degree in computer science or equivalent experience."
    }}
    </script></head><body></body></html>
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/senior-engineer")

    assert len(result.focused_text) <= job_url_import.MAX_JOB_TEXT_CHARS
    assert "Education" in result.focused_text
    assert "Bachelor's degree" in result.focused_text
    assert "content_shortened" in result.warnings


def test_malformed_embedded_json_does_not_block_dom_extraction() -> None:
    html = """
    <html><head><script type="application/json">{"broken":</script></head><body>
      <div id="job-detail-body">
        <h2>Description</h2>
        <p>Build backend services and maintain production systems for customer workflows.</p>
        <h2>Responsibilities</h2>
        <p>Design APIs, review code, write tests, and improve operational reliability.</p>
        <h2>Requirements</h2>
        <p>Experience with Python, SQL, cloud infrastructure, and distributed systems.</p>
      </div>
    </body></html>
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/backend")

    assert result.extraction_method == "dom_candidate"
    assert "operational reliability" in result.focused_text


def test_dom_scoring_prefers_job_content_over_link_heavy_generic_container() -> None:
    navigation_links = "".join(
        f'<a href="/jobs/{index}">Requirements and qualifications for related role {index}</a>'
        for index in range(40)
    )
    html = f"""
    <html><body>
      <div class="content search-results">{navigation_links}</div>
      <section class="role-copy">
        <h2>Description</h2>
        <p>Build secure application services for high-volume customer workflows.</p>
        <h2>Responsibilities</h2>
        <p>Design APIs, write tests, deploy changes, and operate production systems.</p>
        <h2>Required Qualifications</h2>
        <p>Experience with Python, PostgreSQL, cloud infrastructure, and distributed systems.</p>
      </section>
    </body></html>
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/application-engineer")

    assert "high-volume customer workflows" in result.focused_text
    assert "related role 39" not in result.focused_text


def test_dom_parser_recovers_malformed_job_html() -> None:
    html = """
    <html><body><main><section class="job-description">
      <h2>Description<p>Build data APIs and reliable ingestion services.
      <h2>Responsibilities<ul><li>Design pipelines<li>Monitor production data quality
      <h2>Requirements<p>Experience with Python, SQL, testing, and cloud services.
    """

    result = extract_job_result_from_html(html, source_url="https://example.com/jobs/data-engineer")

    assert result.extraction_method == "dom_candidate"
    assert "Build data APIs" in result.focused_text
    assert "Monitor production data quality" in result.focused_text


def test_oversized_job_html_is_rejected_before_dom_parsing() -> None:
    html = f"<html><body>{'x' * job_url_import.MAX_RENDERED_HTML_BYTES}</body></html>"

    with pytest.raises(Exception) as exc_info:
        extract_job_result_from_html(html, source_url="https://example.com/jobs/oversized")

    assert getattr(exc_info.value, "status_code", None) == 413


def test_rendered_json_capture_normalizes_job_payload_for_extraction() -> None:
    payload = {
        "data": {
            "job": {
                "jobId": "captured-123",
                "jobTitle": "Site Reliability Engineer",
                "companyName": "Example Reliability",
                "formattedLocation": "Remote, US",
                "jobDescription": "Operate reliable production platforms and improve service availability for customer workloads.",
                "responsibilities": ["Build observability automation", "Improve incident response"],
                "requiredQualifications": ["Python", "Cloud infrastructure", "Distributed systems"],
            }
        }
    }
    response = job_url_import.NetworkResponse(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", "application/json; charset=utf-8"),),
        body=json.dumps(payload).encode("utf-8"),
    )
    budget = job_url_import.RenderedFetchBudget(deadline=10_000)

    job_url_import._capture_job_json_response(response, budget)
    rendered_html = job_url_import._inject_captured_json(
        "<html><body><main>Loading job information.</main></body></html>",
        budget.captured_json_blocks,
    )
    result = extract_job_result_from_html(rendered_html, source_url="https://example.com/jobs/captured-123")

    assert len(budget.captured_json_blocks) == 1
    assert result.extraction_method == "embedded_json"
    assert result.title == "Site Reliability Engineer"
    assert "incident response" in result.focused_text


def test_oversized_rendered_json_response_is_not_captured() -> None:
    response = job_url_import.NetworkResponse(
        status_code=200,
        reason="OK",
        headers=(("Content-Type", "application/json"),),
        body=b'{"jobId":"large","jobDescription":"' + b"x" * job_url_import.MAX_STRUCTURED_JSON_BYTES + b'"}',
    )
    budget = job_url_import.RenderedFetchBudget(deadline=10_000)

    job_url_import._capture_job_json_response(response, budget)

    assert budget.captured_json_blocks == []
    assert budget.captured_json_bytes == 0


def test_rendered_wait_checks_semantic_content_and_dom_stability() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.function_calls: list[tuple[str, int, int]] = []
            self.load_state_calls: list[tuple[str, int]] = []

        def wait_for_function(self, script: str, *, polling: int, timeout: int) -> None:
            self.function_calls.append((script, polling, timeout))

        def wait_for_load_state(self, state: str, *, timeout: int) -> None:
            self.load_state_calls.append((state, timeout))

    class FakeTimeoutError(Exception):
        pass

    page = FakePage()
    job_url_import._wait_for_rendered_job_content(page, FakeTimeoutError, time.monotonic() + 10)

    assert page.function_calls[0][0] == job_url_import.RENDERED_SEMANTIC_READY_SCRIPT
    assert page.function_calls[1][0] == job_url_import.RENDERED_DOM_STABLE_SCRIPT
    assert page.load_state_calls[0][0] == "networkidle"


def test_job_list_discovery_filters_usajobs_navigation_links() -> None:
    html = """
    <html><body>
      <nav>
        <a href="/Applicant/Dashboard/savedsearches">Saved searches</a>
        <a href="/Search/Results?hp=public">Search jobs</a>
      </nav>
      <main>
        <a href="/job/722102800">Cyber Threat Analyst</a>
        <a href="/job/812345600">Software Developer</a>
      </main>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.usajobs.gov/search/results/?k=software", html)

    assert [link.source_url for link in links] == [
        "https://www.usajobs.gov/job/722102800",
        "https://www.usajobs.gov/job/812345600",
    ]


def test_job_list_discovery_accepts_usajobs_result_anchor_shape() -> None:
    html = """
    <html><body>
      <a href="/job/859907200" data-search-result="0" data-document-id="859907200" class="no-underline">Data Solutions Developer</a>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.usajobs.gov/search/results/?k=software", html)

    assert [link.source_url for link in links] == ["https://www.usajobs.gov/job/859907200"]
    assert links[0].title == "Data Solutions Developer"


def test_job_list_discovery_can_build_usajobs_link_from_document_id() -> None:
    html = """
    <html><body>
      <div data-search-result="0" data-document-id="859907200">Data Solutions Developer</div>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.usajobs.gov/search/results/?k=software", html)

    assert [link.source_url for link in links] == ["https://www.usajobs.gov/job/859907200"]


def test_job_list_discovery_prioritizes_amazon_job_detail_links() -> None:
    html = """
    <html><body>
      <header>
        <a href="/en/job-categories/software-development">Software development category</a>
        <a href="/en/search?base_query=Software+Development">Search jobs</a>
      </header>
      <section>
        <a href="/en/jobs/10411163/software-development-manager-ring">Software Development Manager, Ring</a>
        <a href="/en/jobs/2876543/software-development-engineer">Software Development Engineer</a>
      </section>
    </body></html>
    """

    links = extract_job_links_from_html("https://amazon.jobs/en/search?base_query=Software+Development", html)

    assert [link.source_url for link in links] == [
        "https://amazon.jobs/en/jobs/10411163/software-development-manager-ring",
        "https://amazon.jobs/en/jobs/2876543/software-development-engineer",
    ]


def test_job_list_discovery_dedupes_amazon_short_and_long_job_urls() -> None:
    html = """
    <html><body>
      <section>
        <a href="/en/jobs/10421793/software-development-engineer">Software Development Engineer</a>
        <a href="/jobs/10421793"></a>
        <a href="/en/jobs/2876543/software-development-engineer-ii">Software Development Engineer II</a>
        <a href="/jobs/2876543"></a>
      </section>
    </body></html>
    """

    links = extract_job_links_from_html("https://amazon.jobs/en/search?base_query=Software+Development", html)

    assert [link.source_url for link in links] == [
        "https://amazon.jobs/en/jobs/10421793/software-development-engineer",
        "https://amazon.jobs/en/jobs/2876543/software-development-engineer-ii",
    ]
    assert [link.title for link in links] == [
        "Software Development Engineer",
        "Software Development Engineer II",
    ]


def test_job_list_discovery_extracts_indeed_job_links() -> None:
    html = """
    <html><body>
      <a data-jk="31f81fedecec3218" href="/rc/clk?jk=31f81fedecec3218&from=vj">Software Engineer</a>
      <a data-jk="abc123def4567890" href="/viewjob?jk=abc123def4567890">Backend Developer</a>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.indeed.com/jobs?q=software+engineer&l=Maryland", html)

    assert [link.source_url for link in links] == [
        "https://www.indeed.com/rc/clk?jk=31f81fedecec3218&from=vj",
        "https://www.indeed.com/viewjob?jk=abc123def4567890",
    ]
    assert [link.title for link in links] == ["Software Engineer", "Backend Developer"]


def test_job_list_discovery_extracts_indeed_embedded_job_keys() -> None:
    html = r"""
    <html><body>
      <script>
        window.mosaic.providerData = {
          "results": [
            {"jobkey": "31f81fedecec3218"},
            {"vjk": "abc123def4567890"}
          ]
        };
      </script>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.indeed.com/jobs?q=software+engineer&l=Maryland", html)

    assert [link.source_url for link in links] == [
        "https://www.indeed.com/viewjob?jk=31f81fedecec3218",
        "https://www.indeed.com/viewjob?jk=abc123def4567890",
    ]


def test_job_list_discovery_filters_indeed_bot_detection_links() -> None:
    html = r"""
    <html><body>
      <a href="/career/salaries">Find salaries</a>
      <a href="/account/login?from=bot-detection-anonymous&continue2=https://www.indeed.com/jobs?q=software&vjk=31f81fedecec3218">Continue</a>
    </body></html>
    """

    links = extract_job_links_from_html(
        "https://www.indeed.com/jobs?q=software+engineer&l=Maryland&vjk=31f81fedecec3218",
        html,
    )

    assert links == []


def test_job_list_discovery_extracts_links_from_embedded_json_text() -> None:
    html = """
    <html><body>
      <script>
        window.__RESULTS__ = {
          "items": [
            {"url": "/job/722102800"},
            {"PositionURI": "https://www.usajobs.gov/GetJob/ViewDetails/812345600"}
          ]
        };
      </script>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.usajobs.gov/search/results/?k=software", html)

    assert [link.source_url for link in links] == [
        "https://www.usajobs.gov/job/722102800",
        "https://www.usajobs.gov/GetJob/ViewDetails/812345600",
    ]


def test_job_list_discovery_extracts_escaped_embedded_links() -> None:
    html = r"""
    <html><body>
      <script>
        window.__RESULTS__ = {
          "items": [
            {"url": "https:\/\/www.usajobs.gov\/job\/722102800"},
            {"url": "\/job\/812345600"}
          ]
        };
      </script>
    </body></html>
    """

    links = extract_job_links_from_html("https://www.usajobs.gov/search/results/?k=software", html)

    assert [link.source_url for link in links] == [
        "https://www.usajobs.gov/job/722102800",
        "https://www.usajobs.gov/job/812345600",
    ]


def test_job_list_discovery_extracts_locale_prefixed_embedded_job_links() -> None:
    html = r"""
    <html><body>
      <script>
        window.__RESULTS__ = {
          "jobs": [
            {"href": "\/en\/jobs\/10411163\/software-development-manager-ring"},
            {"href": "/en/jobs/2876543/software-development-engineer"}
          ]
        };
      </script>
    </body></html>
    """

    links = extract_job_links_from_html("https://amazon.jobs/en/search?base_query=Software+Development", html)

    assert [link.source_url for link in links] == [
        "https://amazon.jobs/en/jobs/10411163/software-development-manager-ring",
        "https://amazon.jobs/en/jobs/2876543/software-development-engineer",
    ]


def test_job_list_discovery_finds_explicit_next_page_link() -> None:
    html = """
    <html><body>
      <nav class="search-pagination">
        <a href="/search/results/?p=2" rel="next" aria-label="Next page">Next</a>
      </nav>
    </body></html>
    """

    next_page_url, confidence = extract_next_page_url_from_html(
        "https://www.usajobs.gov/search/results/?p=1",
        html,
    )

    assert next_page_url == "https://www.usajobs.gov/search/results/?p=2"
    assert confidence > 0.5


def test_job_list_discovery_builds_synthetic_next_page_from_query() -> None:
    next_page_url, confidence = extract_next_page_url_from_html(
        "https://www.usajobs.gov/search/results/?k=software&p=1&hp=public",
        "<html><body>No pagination links rendered yet.</body></html>",
    )

    assert next_page_url == "https://www.usajobs.gov/search/results/?k=software&p=2&hp=public"
    assert confidence == 0.55


def test_job_url_rejects_private_hosts() -> None:
    try:
        validate_public_job_url("http://127.0.0.1/jobs")
    except Exception as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("private host should be rejected")


def test_match_history_preserves_snapshots_and_detects_resume_staleness() -> None:
    client = create_test_client()
    profile_response = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Backend Resume",
            "resume_data": {
                "headline": "Backend Engineer",
                "summary": "Built FastAPI services with Python.",
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
        },
    )
    profile_id = profile_response.json()["id"]

    match_response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_profile_id": profile_id,
            "job_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        },
    )
    assert match_response.status_code == 200
    job_id = match_response.json()["saved_job_id"]

    history = client.get(f"/api/v1/jobs/{job_id}/matches").json()["matches"]
    assert len(history) == 1
    assert history[0]["resume_data_snapshot"]["skills"] == ["Python", "FastAPI"]
    assert history[0]["match_origin"] == "direct_match"
    assert history[0]["job_data_snapshot"]["required_skills"] == ["PostgreSQL"]
    assert history[0]["is_stale"] is False

    updated_data = profile_response.json()["resume_data"]
    updated_data["skills"] = ["Python", "FastAPI", "Kubernetes"]
    update_response = client.patch(
        f"/api/v1/resume-profiles/{profile_id}",
        json={"resume_data": updated_data},
    )
    assert update_response.status_code == 200

    stale_history = client.get(f"/api/v1/jobs/{job_id}/matches").json()["matches"]
    assert stale_history[0]["resume_is_stale"] is True
    assert stale_history[0]["is_stale"] is True
    assert stale_history[0]["resume_data_snapshot"]["skills"] == ["Python", "FastAPI"]
