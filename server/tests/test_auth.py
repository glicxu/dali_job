from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import API_ROUTERS, create_app
from app.modules.accounts.models import User
from app.modules.auth.models import AuthSession
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import get_auth_db_session
from app.modules.auth.policy import validate_route_authorization
from app.modules.auth.rate_limit import AuthRateLimiter, AuthRateLimitPolicy
from app.modules.auth.security import hash_password, verify_password
from app.modules.jobs import router as jobs_router
from app.modules.jobs.router import get_job_description_parser
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.resume_job_match import router as match_router
from app.modules.resume_job_match.job_url_import import JobLinkCandidate, JobListDiscoveryResult
from app.modules.reports.models import UserReport


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


def create_local_auth_client(tmp_path: Path) -> TestClient:
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
            "email_delivery_mode": "file",
            "email_outbox_dir": str(tmp_path / "outbox"),
            "log_dir": str(tmp_path / "logs"),
        }
    )
    app.state.test_session_factory = session_factory

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
    app.dependency_overrides[get_auth_db_session] = override_db
    app.dependency_overrides[get_job_description_parser] = lambda: FakeJobDescriptionParser()
    return TestClient(app)


def _latest_email_token(client: TestClient) -> str:
    outbox = Path(client.app.state.runtime.email_outbox_dir)
    latest = max(outbox.glob("*.eml"), key=lambda path: path.stat().st_mtime_ns)
    message = BytesParser(policy=policy.default).parsebytes(latest.read_bytes())
    match = re.search(r"token=([A-Za-z0-9_-]+)", message.get_content())
    assert match
    return match.group(1)


def _register(client: TestClient, email: str = "user@example.com") -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "strong-password", "display_name": "Example User"},
    )
    assert response.status_code == 200


def _verify(client: TestClient) -> None:
    response = client.post("/api/v1/auth/verify-email", json={"token": _latest_email_token(client)})
    assert response.status_code == 200


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("dalijob_csrf")
    assert token
    return {"X-CSRF-Token": token}


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_registration_requires_email_verification(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "strong-password"},
    )
    assert login.status_code == 403
    assert "verify" in login.json()["detail"]

    verify = client.post("/api/v1/auth/verify-email", json={"token": _latest_email_token(client)})
    assert verify.status_code == 200
    assert verify.json()["user"]["email"] == "user@example.com"
    assert verify.json()["user"]["role"] == "user"
    assert verify.json()["user"]["tutorial_completed"] is False
    assert "access_token" not in verify.json()
    assert client.cookies.get("dalijob_session")
    assert client.cookies.get("dalijob_csrf")
    assert client.get("/api/v1/me").status_code == 200
    csrf = client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    assert csrf.json()["csrf_token"] == client.cookies.get("dalijob_csrf")

    completed = client.post("/api/v1/me/tutorial/complete", headers=_csrf_headers(client))
    assert completed.status_code == 200
    assert completed.json()["tutorial_completed"] is True
    assert client.get("/api/v1/me").json()["tutorial_completed"] is True


def test_user_reports_and_admin_boundary_are_enforced_and_audited(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)

    created = client.post(
        "/api/v1/reports",
        headers=_csrf_headers(client),
        json={
            "category": "bug",
            "title": "Saved job does not refresh",
            "description": "The saved jobs list remains stale after an import completes.",
        },
    )
    assert created.status_code == 201
    report_id = created.json()["id"]
    assert client.get("/api/v1/reports").json()[0]["status"] == "new"
    assert client.get("/api/v1/admin/reports").status_code == 403

    session_factory = client.app.state.test_session_factory
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == "user@example.com"))
        assert user is not None
        user.role = "admin"
        db.commit()

    current_user = client.get("/api/v1/me")
    assert current_user.status_code == 200
    assert current_user.json()["role"] == "admin"

    admin_list = client.get("/api/v1/admin/reports")
    assert admin_list.status_code == 200
    assert admin_list.json()[0]["reporter_email"] == "user@example.com"

    updated = client.patch(
        f"/api/v1/admin/reports/{report_id}",
        headers=_csrf_headers(client),
        json={"status": "in_review", "admin_notes": "Reproduction requested from engineering."},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_review"

    with session_factory() as db:
        report = db.get(UserReport, report_id)
        event = db.scalar(select(AuditEvent).where(AuditEvent.subject_id == str(report_id)))
        list_event = db.scalar(select(AuditEvent).where(AuditEvent.event_type == "admin.reports.listed"))
        assert report is not None
        assert report.admin_notes == "Reproduction requested from engineering."
        assert event is not None
        assert event.event_type == "admin.report.updated"
        assert list_event is not None
        assert list_event.event_data == {"status_filter": None, "result_count": 1}
        assert event.event_data == {
            "previous_status": "new",
            "new_status": "in_review",
            "admin_notes_changed": True,
        }
        serialized_event = str(event.event_data)
        assert report.description not in serialized_event
        assert report.admin_notes not in serialized_event


def test_verification_token_is_single_use(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    token = _latest_email_token(client)
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


def test_password_reset_is_generic_single_use_and_revokes_sessions(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)

    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
    known = client.post("/api/v1/auth/forgot-password", json={"email": "user@example.com"})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]

    reset_token = _latest_email_token(client)
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "new-strong-password"},
    )
    assert reset.status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    assert client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "another-password"},
    ).status_code == 400
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "new-strong-password"},
    ).status_code == 200


def test_logout_revokes_session_and_requires_csrf(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers=_csrf_headers(client)).status_code == 200
    assert client.get("/api/v1/me").status_code == 401


def test_session_expiry_is_enforced(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    with client.app.state.test_session_factory() as db:
        session = db.execute(select(AuthSession)).scalar_one()
        session.idle_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/me").status_code == 401


def test_account_soft_delete_revokes_every_session(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    response = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers=_csrf_headers(client),
        json={"current_password": "strong-password"},
    )
    assert response.status_code == 204
    with client.app.state.test_session_factory() as db:
        user = db.execute(select(User).where(User.email == "user@example.com")).scalar_one()
        assert not user.is_active
        assert user.deleted_at is not None
    assert client.get("/api/v1/me").status_code == 401


def test_session_cookie_without_csrf_cannot_mutate(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    client.cookies.delete("dalijob_csrf")
    response = client.post(
        "/api/v1/jobs/draft",
        json={"job_description_text": "Build APIs using Python."},
    )
    assert response.status_code == 403


def test_dev_auth_still_works_without_session_cookie() -> None:
    client = TestClient(create_app())
    assert client.get("/api/v1/me").status_code == 200


def test_scraping_helper_routes_require_auth_in_local_mode(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    responses = [
        client.post("/api/v1/jobs/draft", json={"job_description_text": "Build APIs using Python."}),
        client.post("/api/v1/jobs/import-list/discover", json={"list_url": "https://example.com/jobs"}),
        client.post(
            "/api/v1/resume-job-matches/job-url-extract",
            json={"job_url": "https://example.com/jobs/backend-engineer"},
        ),
    ]
    assert [response.status_code for response in responses] == [401, 401, 401]


def test_scraping_helper_routes_accept_valid_local_session(monkeypatch, tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    headers = _csrf_headers(client)
    monkeypatch.setattr(
        jobs_router,
        "discover_job_list_from_url",
        lambda _url, max_results=25: JobListDiscoveryResult(
            links=[JobLinkCandidate(title="Backend Engineer", source_url="https://example.com/jobs/backend-engineer")],
            next_page_url=None,
            next_page_confidence=0,
        ),
    )
    monkeypatch.setattr(
        match_router,
        "fetch_job_description_from_url",
        lambda _url: "Backend Engineer job text with PostgreSQL.",
    )
    assert client.post(
        "/api/v1/jobs/draft",
        json={"job_description_text": "Build APIs using Python."},
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/v1/jobs/import-list/discover",
        json={"list_url": "https://example.com/jobs"},
        headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/v1/resume-job-matches/job-url-extract",
        json={"job_url": "https://example.com/jobs/backend-engineer"},
        headers=headers,
    ).status_code == 200


def test_all_non_public_api_routes_have_identity_dependency() -> None:
    validate_route_authorization(API_ROUTERS)


def _test_rate_policy(**overrides: int) -> AuthRateLimitPolicy:
    values = {
        "login_ip_limit": 20,
        "login_account_limit": 20,
        "login_window_seconds": 60,
        "register_ip_limit": 20,
        "register_account_limit": 20,
        "register_window_seconds": 60,
    }
    values.update(overrides)
    return AuthRateLimitPolicy(**values)


def test_registration_rate_limit_blocks_ip_across_accounts(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    client.app.state.auth_rate_limiter = AuthRateLimiter(_test_rate_policy(register_ip_limit=1))
    first = client.post(
        "/api/v1/auth/register",
        json={"email": "first@example.com", "password": "strong-password", "display_name": "First"},
    )
    blocked = client.post(
        "/api/v1/auth/register",
        json={"email": "second@example.com", "password": "strong-password", "display_name": "Second"},
    )
    assert first.status_code == 200
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_login_rate_limit_normalizes_account_and_logs_no_email(tmp_path: Path, caplog) -> None:
    client = create_local_auth_client(tmp_path)
    client.app.state.auth_rate_limiter = AuthRateLimiter(_test_rate_policy(login_account_limit=1))
    first = client.post(
        "/api/v1/auth/login",
        json={"email": "candidate@example.com", "password": "wrong-password"},
    )
    with caplog.at_level("WARNING"):
        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": " Candidate@Example.COM ", "password": "wrong-password"},
        )
    assert first.status_code == 401
    assert blocked.status_code == 429
    assert "account_hash=" in caplog.text
    assert "candidate@example.com" not in caplog.text.lower()
