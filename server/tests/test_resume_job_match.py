from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.resume_job_match import router as match_router
from app.modules.resume_job_match.job_url_import import extract_job_description_from_html, validate_public_job_url
from app.modules.resume_job_match.router import get_match_job_description_parser, get_resume_job_matcher
from app.modules.resume_job_match.schemas import (
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
    SupportedRequirement,
    UnsupportedRequirement,
)


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
    assert jobs[0]["job_data"]["required_skills"] == ["PostgreSQL"]
    assert jobs[0]["match_score"] == 7
    assert jobs[0]["matched_resume_source"] == "pasted_text"


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
        "fetch_job_page_text_from_url",
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
            "is_favorite": True,
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
        "fetch_job_page_text_from_url",
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
        "fetch_job_page_text_from_url",
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
    assert "Basic Qualifications" in text
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
    assert "Basic Qualifications" in text
    assert "Our inclusive culture empowers" not in text
    assert "benefits" not in text


def test_job_url_rejects_private_hosts() -> None:
    try:
        validate_public_job_url("http://127.0.0.1/jobs")
    except Exception as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("private host should be rejected")
