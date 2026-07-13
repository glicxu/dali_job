from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth import dependencies as auth_dependencies
from app.modules.auth.dependencies import AuthenticatedIdentity, DEFAULT_AUTH_SECRET, get_auth_secret
from app.modules.auth.security import hash_password, verify_password
from app.modules.jobs import router as jobs_router
from app.modules.jobs.router import get_job_description_parser
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.resume_job_match import router as match_router
from app.modules.resume_job_match.job_url_import import JobLinkCandidate, JobListDiscoveryResult


class FakeJobDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        return JobDescriptionData(
            title="Backend Engineer",
            company="Example Co",
            summary="Build APIs.",
            responsibilities=["Build APIs."],
            required_skills=["Python"],
            preferred_skills=[],
            required_experience=[],
            preferred_experience=[],
            education=[],
            certifications=[],
            tools_and_technologies=["Python"],
            keywords=["backend"],
            seniority_level="",
            employment_type="",
            security_clearance="",
            work_location="",
            salary_range="",
            application_deadline="",
        )


def create_local_auth_client(
    monkeypatch: pytest.MonkeyPatch,
    secret: str | None = "test-local-secret-with-at-least-32-characters",
) -> TestClient:
    if secret is None:
        monkeypatch.setenv("DALIJOB_JWT_SECRET", "")
    else:
        monkeypatch.setenv("DALIJOB_JWT_SECRET", secret)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    app = create_app()
    app.state.runtime = app.state.runtime.__class__(
        **{
            **app.state.runtime.__dict__,
            "auth_mode": "local",
        }
    )

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

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_job_description_parser] = lambda: FakeJobDescriptionParser()
    return TestClient(app)


def register_and_token(client: TestClient, email: str = "user@example.com") -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "strong-password",
            "display_name": "Example User",
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_auth_secret_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_JWT_SECRET", "env-secret")

    assert get_auth_secret() == "env-secret"


def test_auth_secret_requires_environment(monkeypatch) -> None:
    monkeypatch.delenv("DALIJOB_JWT_SECRET", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        get_auth_secret()

    assert exc_info.value.status_code == 500
    assert "DALIJOB_JWT_SECRET" in str(exc_info.value.detail)


def test_auth_secret_rejects_default_secret(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_JWT_SECRET", DEFAULT_AUTH_SECRET)

    with pytest.raises(HTTPException) as exc_info:
        get_auth_secret()

    assert exc_info.value.status_code == 500


def test_register_and_login_issue_dalijob_token(monkeypatch) -> None:
    client = create_local_auth_client(monkeypatch)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "display_name": "Example User",
        },
    )

    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["token_type"] == "bearer"
    assert register_payload["user"]["email"] == "user@example.com"
    assert register_payload["user"]["provider"] == "dalijob"
    assert register_payload["access_token"]

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "strong-password"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


def test_local_auth_without_jwt_secret_fails_closed(monkeypatch) -> None:
    client = create_local_auth_client(monkeypatch, secret=None)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "display_name": "Example User",
        },
    )

    assert response.status_code == 500
    assert "DALIJOB_JWT_SECRET" in response.json()["detail"]


def test_local_auth_rejects_default_jwt_secret(monkeypatch) -> None:
    client = create_local_auth_client(monkeypatch, secret=DEFAULT_AUTH_SECRET)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "display_name": "Example User",
        },
    )

    assert response.status_code == 500
    assert "DALIJOB_JWT_SECRET" in response.json()["detail"]


def test_dev_auth_still_works_without_jwt_secret(monkeypatch) -> None:
    monkeypatch.delenv("DALIJOB_JWT_SECRET", raising=False)
    client = TestClient(create_app())

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json()["provider"] == "dev"


def test_scraping_helper_routes_require_auth_in_local_mode(monkeypatch) -> None:
    client = create_local_auth_client(monkeypatch)

    responses = [
        client.post("/api/v1/jobs/draft", json={"job_description_text": "Build APIs using Python."}),
        client.post("/api/v1/jobs/import-list/discover", json={"list_url": "https://example.com/jobs"}),
        client.post(
            "/api/v1/resume-job-matches/job-url-extract",
            json={"job_url": "https://example.com/jobs/backend-engineer"},
        ),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]


def test_scraping_helper_routes_accept_valid_local_token(monkeypatch) -> None:
    client = create_local_auth_client(monkeypatch)
    token = register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(
        auth_dependencies,
        "_identity_from_email",
        lambda email: AuthenticatedIdentity(
            external_user_id="1",
            email=email,
            display_name="Example User",
            provider="dalijob",
        ),
    )
    monkeypatch.setattr(
        jobs_router,
        "discover_job_list_from_url",
        lambda _url, max_results=25: JobListDiscoveryResult(
            links=[
                JobLinkCandidate(
                    title="Backend Engineer",
                    source_url="https://example.com/jobs/backend-engineer",
                )
            ],
            next_page_url=None,
            next_page_confidence=0,
        ),
    )
    monkeypatch.setattr(
        match_router,
        "fetch_job_description_from_url",
        lambda _url: "Backend Engineer job text with PostgreSQL.",
    )

    draft_response = client.post(
        "/api/v1/jobs/draft",
        json={"job_description_text": "Build APIs using Python."},
        headers=headers,
    )
    discover_response = client.post(
        "/api/v1/jobs/import-list/discover",
        json={"list_url": "https://example.com/jobs"},
        headers=headers,
    )
    extract_response = client.post(
        "/api/v1/resume-job-matches/job-url-extract",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
        headers=headers,
    )

    assert draft_response.status_code == 200
    assert discover_response.status_code == 200
    assert extract_response.status_code == 200
