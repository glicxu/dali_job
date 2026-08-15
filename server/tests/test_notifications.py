from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.accounts.models import User, Workspace
from app.modules.auth.dependencies import get_dev_identity
from app.modules.automation.models import NotificationDelivery, SearchSchedule
from app.modules.job_search.models import JobSearchCriterion
from app.modules.jobs.models import JobCache, JobResumeMatch, UserSavedJob
from app.modules.notifications.digest import send_one_digest
from app.modules.notifications.service import (
    create_email_delivery_if_enabled,
    create_in_app_delivery,
)
from app.modules.profiles.models import ResumeProfile
from app.modules.profiles.repository import ensure_account_for_identity


SEED_TIME = datetime(2026, 8, 15, 7, 0, tzinfo=timezone.utc)


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


def _seed_inbox(session_factory: sessionmaker, *, count: int = 2) -> list[int]:
    match_ids: list[int] = []
    with session_factory() as db:
        user, workspace = ensure_account_for_identity(db, get_dev_identity())
        profile = ResumeProfile(
            workspace_id=workspace.id,
            user_id=user.id,
            title="Backend Resume",
            resume_data={"headline": "Backend Engineer"},
            is_default=True,
        )
        db.add(profile)
        db.flush()
        criterion = JobSearchCriterion(
            workspace_id=workspace.id,
            user_id=user.id,
            resume_profile_id=profile.id,
            keyword="Backend Engineer",
            location="Remote",
            source="custom",
        )
        db.add(criterion)
        db.flush()
        schedule = SearchSchedule(
            workspace_id=workspace.id,
            user_id=user.id,
            criterion_id=criterion.id,
            resume_profile_id=profile.id,
            interval_minutes=60,
            minimum_match_score=7,
            next_run_at=profile.created_at,
        )
        db.add(schedule)
        db.flush()
        for index in range(count):
            cache = JobCache(
                title=f"Backend Engineer {index}",
                company="Example Co",
                source_url=f"https://example.com/jobs/{index}",
                source_url_hash=f"hash-{index}",
                raw_description_text="Python backend role",
                job_data={"title": f"Backend Engineer {index}", "company": "Example Co"},
            )
            db.add(cache)
            db.flush()
            saved_job = UserSavedJob(
                workspace_id=workspace.id,
                user_id=user.id,
                jobs_cache_id=cache.id,
            )
            db.add(saved_job)
            db.flush()
            match = JobResumeMatch(
                workspace_id=workspace.id,
                user_id=user.id,
                user_job_id=saved_job.id,
                jobs_cache_id=cache.id,
                resume_profile_id=profile.id,
                resume_source="resume_profile",
                match_score=8 + index,
                match_data={"summary": "Strong match."},
                resume_data_snapshot={"headline": "Backend Engineer"},
                job_data_snapshot=cache.job_data,
                resume_snapshot_hash="resume-hash",
                job_snapshot_hash=f"job-hash-{index}",
            )
            db.add(match)
            db.flush()
            first, created = create_in_app_delivery(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                schedule_id=schedule.id,
                job_resume_match_id=match.id,
                canonical_job_id=cache.id,
            )
            repeated, repeated_created = create_in_app_delivery(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                schedule_id=schedule.id,
                job_resume_match_id=match.id,
                canonical_job_id=cache.id,
            )
            assert created is True
            assert repeated_created is False
            assert repeated.id == first.id
            first.created_at = SEED_TIME + timedelta(minutes=index)
            email, email_created = create_email_delivery_if_enabled(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                schedule_id=schedule.id,
                job_resume_match_id=match.id,
                canonical_job_id=cache.id,
            )
            assert email_created is True
            assert email is not None
            email.created_at = SEED_TIME + timedelta(minutes=index)
            match_ids.append(match.id)
        db.commit()
    return match_ids


def test_notification_preferences_are_created_and_validated() -> None:
    client, session_factory = create_test_client()

    initial = client.get("/api/v1/notification-preferences")
    assert initial.status_code == 200
    assert initial.json()["email_enabled"] is True
    assert initial.json()["digest_mode"] == "daily"
    assert initial.json()["minimum_match_score"] == 0

    updated = client.put(
        "/api/v1/notification-preferences",
        json={
            "email_enabled": True,
            "digest_mode": "daily",
            "minimum_match_score": 8,
            "timezone": "America/Los_Angeles",
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "07:00:00",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["minimum_match_score"] == 8
    assert updated.json()["timezone"] == "America/Los_Angeles"

    invalid = client.put(
        "/api/v1/notification-preferences",
        json={"timezone": "Mars/Olympus_Mons"},
    )
    assert invalid.status_code == 422
    with session_factory() as db:
        assert db.scalar(select(User)).email == "local.user@dalijob.dev"
        assert db.scalar(select(Workspace)) is not None


def test_match_inbox_paginates_returns_details_and_marks_read() -> None:
    client, session_factory = create_test_client()
    match_ids = _seed_inbox(session_factory)

    first_page = client.get("/api/v1/match-inbox?limit=1")
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 1
    assert first_body["next_cursor"] is not None
    assert first_body["items"][0]["match_id"] == match_ids[-1]

    second_page = client.get(
        "/api/v1/match-inbox",
        params={"limit": 1, "before_id": first_body["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["match_id"] == match_ids[0]

    detail = client.get(f"/api/v1/match-inbox/{match_ids[-1]}")
    assert detail.status_code == 200
    assert detail.json()["match_data"]["summary"] == "Strong match."
    assert detail.json()["status"] == "sent"

    marked = client.post(f"/api/v1/match-inbox/{match_ids[-1]}/read")
    assert marked.status_code == 200
    assert marked.json()["status"] == "read"
    assert marked.json()["read_at"] is not None
    with session_factory() as db:
        assert db.query(NotificationDelivery).count() == 4


def test_daily_digest_respects_timezone_quiet_hours_and_sends_once() -> None:
    client, session_factory = create_test_client()
    configured = client.put(
        "/api/v1/notification-preferences",
        json={
            "email_enabled": True,
            "digest_mode": "daily",
            "minimum_match_score": 0,
            "timezone": "UTC",
            "quiet_hours_start": "08:00:00",
            "quiet_hours_end": "10:00:00",
        },
    )
    assert configured.status_code == 200
    _seed_inbox(session_factory, count=2)
    sent: list[tuple[str, str, str]] = []

    quiet = send_one_digest(
        session_factory,
        client.app.state.runtime,
        worker_id="digest-test",
        now=datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc),
        sender=lambda recipient, subject, body: sent.append((recipient, subject, body)),
    )
    assert quiet.claimed is False

    outcome = send_one_digest(
        session_factory,
        client.app.state.runtime,
        worker_id="digest-test",
        now=datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc),
        sender=lambda recipient, subject, body: sent.append((recipient, subject, body)),
    )
    assert outcome.status == "sent"
    assert outcome.delivery_count == 2
    assert len(sent) == 1
    assert sent[0][0] == "local.user@dalijob.dev"
    assert "2 new DaliJob matches" in sent[0][2]
    assert "Backend Engineer 0" in sent[0][2]
    assert "resume contents" in sent[0][2]
    assert send_one_digest(
        session_factory,
        client.app.state.runtime,
        worker_id="digest-test",
        now=datetime(2026, 8, 15, 10, 1, tzinfo=timezone.utc),
        sender=lambda recipient, subject, body: sent.append((recipient, subject, body)),
    ).claimed is False
    with session_factory() as db:
        email_deliveries = list(
            db.scalars(
                select(NotificationDelivery).where(NotificationDelivery.channel == "email")
            )
        )
        assert all(item.status == "sent" for item in email_deliveries)
        assert all(item.attempt_count == 1 for item in email_deliveries)


def test_daily_digest_failure_retries_without_exposing_exception_details() -> None:
    client, session_factory = create_test_client()
    _seed_inbox(session_factory, count=1)
    failed_at = datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc)

    def fail_sender(_recipient: str, _subject: str, _body: str) -> None:
        raise RuntimeError("smtp-password-should-not-be-stored")

    failed = send_one_digest(
        session_factory,
        client.app.state.runtime,
        worker_id="digest-retry",
        now=failed_at,
        sender=fail_sender,
    )
    assert failed.status == "pending"
    with session_factory() as db:
        delivery = db.scalar(
            select(NotificationDelivery).where(NotificationDelivery.channel == "email")
        )
        assert delivery.status == "pending"
        assert delivery.attempt_count == 1
        assert delivery.next_attempt_at is not None
        assert delivery.error_code == "email_delivery_failed"
        assert "smtp-password" not in (delivery.error_message or "")

    sent: list[str] = []
    retry = send_one_digest(
        session_factory,
        client.app.state.runtime,
        worker_id="digest-retry",
        now=failed_at + timedelta(minutes=6),
        sender=lambda _recipient, _subject, body: sent.append(body),
    )
    assert retry.status == "sent"
    assert len(sent) == 1
