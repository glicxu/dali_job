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
from app.modules.accounts.models import User, Workspace
from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationTask,
)
from app.modules.auth.models import AuthActionToken, AuthSession, MobileRefreshToken
from app.modules.audit.models import AuditEvent
from app.modules.automation.models import SearchRun, SearchSchedule, UsageLedger, UserSubscription
from app.modules.auth.dependencies import get_auth_db_session
from app.modules.auth.policy import validate_route_authorization
from app.modules.auth.rate_limit import AuthRateLimiter, AuthRateLimitPolicy
from app.modules.auth.security import hash_password, verify_password
from app.modules.jobs import router as jobs_router
from app.modules.documents.models import Document, DocumentDownloadTicket, DocumentVersion
from app.modules.interviews.models import Interview, InterviewNote, InterviewPrepGuide
from app.modules.job_search.models import JobSearchCriterion
from app.modules.jobs.models import JobCache, JobResumeMatch, UserEditedJob, UserSavedJob
from app.modules.jobs.router import get_job_description_parser
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.materials.models import GeneratedApplicationMaterial, GeneratedApplicationMaterialVersion
from app.modules.operations.models import ManagedOperation
from app.modules.profiles.models import ResumeProfile
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

    with client.app.state.test_session_factory() as db:
        subscription = db.execute(select(UserSubscription)).scalar_one()
        assert subscription.tier_code == "free"
        assert subscription.status == "active"

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
    mobile = client.post(
        "/api/v1/auth/mobile/sessions",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "device_label": "Password reset device",
        },
    ).json()

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
    assert client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {mobile['access_token']}"},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/mobile/sessions/refresh",
        json={"refresh_token": mobile["refresh_token"]},
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "another-password"},
    ).status_code == 400
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "new-strong-password"},
    )
    assert login.status_code == 200
    csrf = client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    assert csrf.json()["csrf_token"] == client.cookies.get("dalijob_csrf")


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


def test_mobile_session_rotates_tokens_and_detects_refresh_reuse(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)

    opened = client.post(
        "/api/v1/auth/mobile/sessions",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "device_label": "Pixel test device",
        },
    )
    assert opened.status_code == 201
    first = opened.json()
    first_access = first["access_token"]
    first_refresh = first["refresh_token"]
    assert first["token_type"] == "Bearer"
    assert first["session"]["device_label"] == "Pixel test device"
    first_headers = {"Authorization": f"Bearer {first_access}"}
    assert client.get("/api/v1/me", headers=first_headers).status_code == 200
    assert client.get("/api/v1/me", headers={"Authorization": "Basic invalid"}).status_code == 401
    sessions = client.get("/api/v1/auth/mobile/sessions", headers=first_headers)
    assert sessions.status_code == 200
    assert sessions.json()["sessions"][0]["is_current"] is True

    # Bearer-authenticated writes do not rely on browser CSRF state.
    client.cookies.delete("dalijob_csrf")
    assert client.post("/api/v1/me/tutorial/complete", headers=first_headers).status_code == 200

    rotated = client.post(
        "/api/v1/auth/mobile/sessions/refresh",
        json={"refresh_token": first_refresh},
    )
    assert rotated.status_code == 200
    second = rotated.json()
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}
    assert second["refresh_token"] != first_refresh
    assert client.get("/api/v1/me", headers=first_headers).status_code == 401
    assert client.get("/api/v1/me", headers=second_headers).status_code == 200

    reused = client.post(
        "/api/v1/auth/mobile/sessions/refresh",
        json={"refresh_token": first_refresh},
    )
    assert reused.status_code == 401
    assert "reuse" in reused.json()["detail"]
    assert client.get("/api/v1/me", headers=second_headers).status_code == 401
    assert client.post(
        "/api/v1/auth/mobile/sessions/refresh",
        json={"refresh_token": second["refresh_token"]},
    ).status_code == 401

    with client.app.state.test_session_factory() as db:
        mobile_session = db.scalar(select(AuthSession).where(AuthSession.session_type == "mobile"))
        refresh_tokens = list(db.scalars(select(MobileRefreshToken)).all())
        assert mobile_session is not None
        assert mobile_session.revoked_at is not None
        assert mobile_session.token_hash not in {first_access, second["access_token"]}
        assert len(refresh_tokens) == 2
        assert all(token.token_hash not in {first_refresh, second["refresh_token"]} for token in refresh_tokens)
        assert all(token.revoked_at is not None for token in refresh_tokens)


def test_mobile_session_can_be_revoked_from_browser_device_management(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    opened = client.post(
        "/api/v1/auth/mobile/sessions",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "device_label": "iPhone test device",
        },
    ).json()
    session_id = opened["session"]["id"]

    listed = client.get("/api/v1/auth/mobile/sessions")
    assert listed.status_code == 200
    assert listed.json()["sessions"][0]["is_current"] is False
    revoked = client.delete(
        f"/api/v1/auth/mobile/sessions/{session_id}",
        headers=_csrf_headers(client),
    )
    assert revoked.status_code == 204
    assert client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {opened['access_token']}"},
    ).status_code == 401
    assert client.get("/api/v1/auth/mobile/sessions").json() == {
        "sessions": [],
        "next_cursor": None,
    }


def test_account_soft_delete_revokes_every_session(tmp_path: Path) -> None:
    client = create_local_auth_client(tmp_path)
    _register(client)
    _verify(client)
    session_factory = client.app.state.test_session_factory
    with session_factory() as db:
        user = db.execute(select(User).where(User.email == "user@example.com")).scalar_one()
        workspace = db.execute(select(Workspace).where(Workspace.owner_user_id == user.id)).scalar_one()
        subscription = db.execute(
            select(UserSubscription).where(UserSubscription.user_id == user.id)
        ).scalar_one()
        original_user_id = user.id

        document = Document(workspace_id=workspace.id, user_id=user.id, title="Private resume")
        db.add(document)
        db.flush()
        document_version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            file_name="resume.txt",
            content_type="text/plain",
            size_bytes=14,
            sha256="a" * 64,
            storage_path="documents/private-resume.txt",
            extracted_text="Private resume",
        )
        db.add(document_version)
        db.flush()
        download_ticket = DocumentDownloadTicket(
            workspace_id=workspace.id,
            user_id=user.id,
            document_version_id=document_version.id,
            token_hash="b" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        profile = ResumeProfile(
            workspace_id=workspace.id,
            user_id=user.id,
            title="Private profile",
            resume_data={"headline": "Engineer", "skills": ["Python"]},
            source_document_id=document.id,
            source_document_version_id=document_version.id,
            is_default=True,
        )
        cache = JobCache(
            title="Shared role",
            company="Example Co",
            source_url="https://example.com/jobs/shared-role",
            source_url_hash="c" * 64,
            raw_description_text="Build APIs.",
            job_data={"title": "Shared role", "company": "Example Co"},
        )
        edited_job = UserEditedJob(
            workspace_id=workspace.id,
            user_id=user.id,
            title="Private edit",
            company="Example Co",
            raw_description_text="Private edited job.",
            job_data={"title": "Private edit"},
        )
        db.add_all([download_ticket, profile, cache, edited_job])
        db.flush()
        saved_job = UserSavedJob(
            workspace_id=workspace.id,
            user_id=user.id,
            jobs_cache_id=cache.id,
            notes="Private job note",
        )
        db.add(saved_job)
        db.flush()
        match = JobResumeMatch(
            workspace_id=workspace.id,
            user_id=user.id,
            user_job_id=saved_job.id,
            jobs_cache_id=cache.id,
            resume_profile_id=profile.id,
            resume_document_id=document.id,
            resume_source="profile",
            match_score=7,
            match_data={"match_score": 7},
            resume_data_snapshot={"skills": ["Python"]},
            job_data_snapshot={"required_skills": ["Python"]},
        )
        criterion = JobSearchCriterion(
            workspace_id=workspace.id,
            user_id=user.id,
            resume_profile_id=profile.id,
            keyword="backend engineer",
            location="Maryland",
        )
        application = Application(
            workspace_id=workspace.id,
            user_id=user.id,
            user_job_id=saved_job.id,
            status="applied",
            priority="normal",
            active_duplicate_guard=1,
        )
        operation = ManagedOperation(
            workspace_id=workspace.id,
            user_id=user.id,
            operation_type="test_operation",
            idempotency_key="account-delete-operation",
            status="queued",
            request_payload={"private": True},
        )
        report = UserReport(
            workspace_id=workspace.id,
            user_id=user.id,
            category="account",
            title="Private report",
            description="Private report details.",
        )
        db.add_all([match, criterion, application, operation, report])
        db.flush()
        schedule = SearchSchedule(
            workspace_id=workspace.id,
            user_id=user.id,
            criterion_id=criterion.id,
            resume_profile_id=profile.id,
            interval_minutes=10_080,
            minimum_match_score=5,
            next_run_at=datetime.now(timezone.utc),
        )
        db.add(schedule)
        db.flush()
        search_run = SearchRun(
            workspace_id=workspace.id,
            user_id=user.id,
            schedule_id=schedule.id,
            managed_operation_id=operation.id,
            scheduled_for=datetime.now(timezone.utc),
        )
        db.add(search_run)
        db.flush()
        usage = UsageLedger(
            workspace_id=workspace.id,
            user_id=user.id,
            subscription_id=subscription.id,
            search_run_id=search_run.id,
            idempotency_key="account-delete-usage",
            entitlement_version="test-v1",
            tier_code_snapshot="free",
            allowance_snapshot=4,
        )
        db.add(usage)
        status_history = ApplicationStatusHistory(
            application_id=application.id,
            from_status=None,
            to_status="applied",
        )
        application_event = ApplicationEvent(
            application_id=application.id,
            event_type="application.created",
            payload={"private": True},
        )
        application_note = ApplicationNote(application_id=application.id, body="Private application note")
        application_document = ApplicationDocument(
            application_id=application.id,
            document_version_id=document_version.id,
            purpose="resume",
        )
        application_task = ApplicationTask(application_id=application.id, title="Follow up")
        interview = Interview(
            workspace_id=workspace.id,
            user_id=user.id,
            application_id=application.id,
            interview_type="technical",
            status="scheduled",
            stage="technical_interview",
        )
        material = GeneratedApplicationMaterial(
            workspace_id=workspace.id,
            user_id=user.id,
            application_id=application.id,
            material_type="tailored_resume",
        )
        db.add_all([
            status_history,
            application_event,
            application_note,
            application_document,
            application_task,
            interview,
            material,
        ])
        db.flush()
        interview_note = InterviewNote(interview_id=interview.id, body="Private interview note")
        prep_guide = InterviewPrepGuide(
            workspace_id=workspace.id,
            user_id=user.id,
            interview_id=interview.id,
            operation_id=operation.id,
            resume_profile_id=profile.id,
            resume_data_snapshot={"skills": ["Python"]},
            job_data_snapshot={"required_skills": ["Python"]},
        )
        material_version = GeneratedApplicationMaterialVersion(
            material_id=material.id,
            version_number=1,
            operation_id=None,
            source_document_version_id=document_version.id,
            source_resume_snapshot={"skills": ["Python"]},
            job_snapshot={"required_skills": ["Python"]},
            content_data={"sections": []},
            version_source="ai",
            prompt_version="test-v1",
            schema_version="test-v1",
        )
        audit_event = AuditEvent(
            workspace_id=workspace.id,
            actor_user_id=user.id,
            event_type="test.retained",
            event_data={},
        )
        db.add_all([interview_note, prep_guide, material_version, audit_event])
        db.commit()

        owned_records = [
            workspace,
            document,
            document_version,
            download_ticket,
            profile,
            edited_job,
            saved_job,
            match,
            criterion,
            application,
            status_history,
            application_event,
            application_note,
            application_document,
            application_task,
            interview,
            interview_note,
            prep_guide,
            operation,
            material,
            material_version,
            report,
            subscription,
            schedule,
            search_run,
            usage,
        ]
        owned_record_ids = [(type(record), record.id) for record in owned_records]
        cache_id = cache.id
        audit_event_id = audit_event.id
        download_ticket_id = download_ticket.id
        application_document_id = application_document.id
        application_task_id = application_task.id
        operation_id = operation.id
        subscription_id = subscription.id
        schedule_id = schedule.id
        search_run_id = search_run.id

    assert client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "user@example.com"},
    ).status_code == 200
    response = client.request(
        "DELETE",
        "/api/v1/auth/account",
        headers=_csrf_headers(client),
        json={"current_password": "strong-password"},
    )
    assert response.status_code == 204
    with session_factory() as db:
        deleted_user = db.get(User, original_user_id)
        assert deleted_user is not None
        assert not deleted_user.is_active
        assert deleted_user.deleted_at is not None
        assert deleted_user.email != "user@example.com"
        assert deleted_user.email.startswith(f"deleted-{original_user_id}-")
        assert deleted_user.email.endswith("@deleted.invalid")
        for model, record_id in owned_record_ids:
            record = db.get(model, record_id)
            assert record is not None
            assert record.deleted_at is not None, model.__tablename__
        assert db.get(DocumentDownloadTicket, download_ticket_id).consumed_at is not None
        assert db.get(ApplicationDocument, application_document_id).detached_at is not None
        assert db.get(ApplicationTask, application_task_id).reminder_dismissed_at is not None
        assert db.get(ManagedOperation, operation_id).status == "cancelled"
        assert db.get(UserSubscription, subscription_id).status == "cancelled"
        assert db.get(SearchSchedule, schedule_id).enabled is False
        assert db.get(SearchRun, search_run_id).status == "cancelled"
        assert db.get(JobCache, cache_id).deleted_at is None
        assert db.get(AuditEvent, audit_event_id) is not None
        assert all(session.revoked_at is not None for session in db.scalars(select(AuthSession)).all())
        assert all(token.consumed_at is not None for token in db.scalars(select(AuthActionToken)).all())
    assert client.get("/api/v1/me").status_code == 401

    _register(client, email="user@example.com")
    _verify(client)
    with session_factory() as db:
        replacement = db.execute(select(User).where(User.email == "user@example.com")).scalar_one()
        assert replacement.id != original_user_id
        assert replacement.display_name == "Example User"
    assert client.get("/api/v1/documents").json()["documents"] == []
    assert client.get("/api/v1/resume-profiles").json()["resume_profiles"] == []
    assert client.get("/api/v1/jobs").json() == []
    assert client.get("/api/v1/applications").json() == []
    assert client.get("/api/v1/reports").json() == []


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
