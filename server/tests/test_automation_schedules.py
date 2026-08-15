from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.automation.dispatcher import dispatch_due_schedules
from app.modules.automation.entitlements import EntitlementCatalog, TierEntitlement
from app.modules.automation.models import SearchRun, SearchSchedule, UsageLedger, UserSubscription
from app.modules.operations.models import ManagedOperation


def _catalog(*, free_searches: int = 2, free_criteria: int = 1) -> EntitlementCatalog:
    return EntitlementCatalog(
        version="schedule-tests-v1",
        tiers={
            "free": TierEntitlement(free_searches, free_criteria, 60),
            "starter": TierEntitlement(30, 3, 30),
            "plus": TierEntitlement(90, 10, 15),
        },
    )


def create_test_client(
    *,
    catalog: EntitlementCatalog | None = None,
) -> tuple[TestClient, sessionmaker]:
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
    app.state.tier_entitlements = catalog or _catalog()
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app), session_factory


def _create_resume_and_criterion(client: TestClient, *, keyword: str = "Backend Engineer") -> tuple[int, int]:
    resume = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": f"{keyword} Resume",
            "resume_data": {
                "headline": keyword,
                "skills": ["Python", "FastAPI"],
            },
            "is_default": True,
        },
    )
    assert resume.status_code == 200
    criterion = client.post(
        "/api/v1/job-search/criteria",
        json={
            "resume_profile_id": resume.json()["id"],
            "keyword": keyword,
            "location": "Remote",
        },
    )
    assert criterion.status_code == 200
    return resume.json()["id"], criterion.json()["id"]


def _create_schedule(client: TestClient, resume_id: int, criterion_id: int) -> dict:
    response = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": criterion_id,
            "resume_profile_id": resume_id,
            "interval_minutes": 60,
            "minimum_match_score": 7,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_entitlements_and_schedule_crud() -> None:
    client, _session_factory = create_test_client()
    resume_id, criterion_id = _create_resume_and_criterion(client)

    entitlements = client.get("/api/v1/account/entitlements")
    assert entitlements.status_code == 200
    assert entitlements.json()["tier_code"] == "free"
    assert entitlements.json()["searches_per_period"] == 2
    assert entitlements.json()["searches_available"] == 2
    assert entitlements.json()["minimum_interval_minutes"] == 60

    too_frequent = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": criterion_id,
            "resume_profile_id": resume_id,
            "interval_minutes": 30,
        },
    )
    assert too_frequent.status_code == 409
    assert too_frequent.json()["detail"]["code"] == "interval_below_tier_minimum"

    created = _create_schedule(client, resume_id, criterion_id)
    schedule_id = created["id"]
    assert created["enabled"] is True
    assert created["minimum_match_score"] == 7

    duplicate = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": criterion_id,
            "resume_profile_id": resume_id,
            "interval_minutes": 60,
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "schedule_exists"

    listed = client.get("/api/v1/automation/schedules")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["schedules"]] == [schedule_id]

    updated = client.patch(
        f"/api/v1/automation/schedules/{schedule_id}",
        json={"minimum_match_score": 8, "interval_minutes": 120},
    )
    assert updated.status_code == 200
    assert updated.json()["minimum_match_score"] == 8
    assert updated.json()["interval_minutes"] == 120

    paused = client.post(f"/api/v1/automation/schedules/{schedule_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False
    assert paused.json()["paused_reason"] == "Paused by user"

    resumed = client.post(f"/api/v1/automation/schedules/{schedule_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["enabled"] is True
    assert resumed.json()["paused_reason"] is None

    assert client.get("/api/v1/automation/runs").json() == {"runs": [], "next_cursor": None}
    assert client.delete(f"/api/v1/automation/schedules/{schedule_id}").status_code == 204
    assert client.get("/api/v1/automation/schedules").json() == {"schedules": []}


def test_tier_limits_number_of_active_schedules() -> None:
    client, _session_factory = create_test_client(catalog=_catalog(free_criteria=1))
    first_resume_id, first_criterion_id = _create_resume_and_criterion(client, keyword="Backend Engineer")
    second_resume_id, second_criterion_id = _create_resume_and_criterion(client, keyword="Platform Engineer")
    _create_schedule(client, first_resume_id, first_criterion_id)

    limited = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": second_criterion_id,
            "resume_profile_id": second_resume_id,
            "interval_minutes": 60,
        },
    )
    assert limited.status_code == 409
    assert limited.json()["detail"]["code"] == "active_schedule_limit"


def test_new_schedule_uses_notification_preference_threshold_when_omitted() -> None:
    client, _session_factory = create_test_client()
    updated = client.put(
        "/api/v1/notification-preferences",
        json={
            "email_enabled": False,
            "digest_mode": "immediate",
            "minimum_match_score": 8,
            "timezone": "America/Los_Angeles",
        },
    )
    assert updated.status_code == 200
    resume_id, criterion_id = _create_resume_and_criterion(client)

    created = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": criterion_id,
            "resume_profile_id": resume_id,
            "interval_minutes": 60,
        },
    )
    assert created.status_code == 201
    assert created.json()["minimum_match_score"] == 8


def test_dispatcher_queues_one_idempotent_run_and_reserves_usage() -> None:
    catalog = _catalog(free_searches=2)
    client, session_factory = create_test_client(catalog=catalog)
    resume_id, criterion_id = _create_resume_and_criterion(client)
    created = _create_schedule(client, resume_id, criterion_id)

    with session_factory() as db:
        schedule = db.get(SearchSchedule, created["id"])
        scheduled_for = schedule.next_run_at
        dispatch_time = scheduled_for + timedelta(seconds=1)
        summary = dispatch_due_schedules(db, catalog, now=dispatch_time)
        db.commit()
        assert summary.inspected == 1
        assert summary.queued == 1

    with session_factory() as db:
        run = db.execute(select(SearchRun)).scalar_one()
        operation = db.execute(select(ManagedOperation)).scalar_one()
        ledger = db.execute(select(UsageLedger)).scalar_one()
        schedule = db.get(SearchSchedule, created["id"])
        assert run.status == "queued"
        assert run.managed_operation_id == operation.id
        assert operation.operation_type == "automated_job_search"
        assert operation.request_payload["criterion_id"] == criterion_id
        assert ledger.state == "reserved"
        assert ledger.search_run_id == run.id
        assert schedule.next_run_at > dispatch_time

        # Simulate a dispatcher retry before the schedule advancement was
        # persisted. The occurrence uniqueness check prevents another charge.
        schedule.next_run_at = scheduled_for
        db.commit()
        replay = dispatch_due_schedules(db, catalog, now=dispatch_time)
        db.commit()
        assert replay.skipped_existing == 1
        assert replay.queued == 0
        assert len(db.scalars(select(SearchRun)).all()) == 1
        assert len(db.scalars(select(UsageLedger)).all()) == 1
        assert len(db.scalars(select(ManagedOperation)).all()) == 1

    usage = client.get("/api/v1/account/usage")
    assert usage.status_code == 200
    usage_body = usage.json()
    assert usage_body["searches_per_period"] == 2
    assert usage_body["searches_reserved"] == 1
    assert usage_body["searches_consumed"] == 0
    assert usage_body["searches_available"] == 1
    assert len(usage_body["entries"]) == 1
    assert usage_body["entries"][0]["state"] == "reserved"
    run_id = usage_body["entries"][0]["search_run_id"]

    detail = client.get(f"/api/v1/automation/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "queued"
    assert client.get("/api/v1/automation/runs/999999").status_code == 404

    with session_factory() as db:
        first_run = db.get(SearchRun, run_id)
        second_run = SearchRun(
            workspace_id=first_run.workspace_id,
            user_id=first_run.user_id,
            schedule_id=first_run.schedule_id,
            status="cancelled",
            scheduled_for=first_run.scheduled_for + timedelta(hours=1),
            completed_at=first_run.scheduled_for + timedelta(hours=1),
        )
        db.add(second_run)
        db.commit()

    first_page = client.get("/api/v1/automation/runs?limit=1").json()
    assert len(first_page["runs"]) == 1
    assert first_page["next_cursor"] == first_page["runs"][0]["id"]
    second_page = client.get(
        "/api/v1/automation/runs",
        params={"limit": 1, "before_id": first_page["next_cursor"]},
    ).json()
    assert [item["id"] for item in second_page["runs"]] == [run_id]
    assert second_page["next_cursor"] is None


def test_dispatcher_defers_at_quota_and_delete_releases_queued_usage() -> None:
    catalog = _catalog(free_searches=1)
    client, session_factory = create_test_client(catalog=catalog)
    resume_id, criterion_id = _create_resume_and_criterion(client)
    created = _create_schedule(client, resume_id, criterion_id)

    with session_factory() as db:
        schedule = db.get(SearchSchedule, created["id"])
        first_dispatch = schedule.next_run_at + timedelta(seconds=1)
        first = dispatch_due_schedules(db, catalog, now=first_dispatch)
        db.commit()
        assert first.queued == 1

        schedule = db.get(SearchSchedule, created["id"])
        schedule.next_run_at = first_dispatch
        # Use a different occurrence so this reaches quota enforcement instead
        # of the duplicate-occurrence guard.
        schedule.next_run_at = schedule.next_run_at + timedelta(seconds=1)
        db.commit()
        quota = dispatch_due_schedules(db, catalog, now=first_dispatch + timedelta(seconds=2))
        db.commit()
        assert quota.skipped_quota == 1
        assert schedule.paused_reason == "Search allowance exhausted"

    deleted = client.delete(f"/api/v1/automation/schedules/{created['id']}")
    assert deleted.status_code == 204
    with session_factory() as db:
        run = db.execute(select(SearchRun)).scalar_one()
        ledger = db.execute(select(UsageLedger)).scalar_one()
        operation = db.execute(select(ManagedOperation)).scalar_one()
        assert run.status == "cancelled"
        assert ledger.state == "released"
        assert operation.status == "cancelled"


def test_run_now_requires_super_and_does_not_consume_a_finite_quota() -> None:
    catalog = EntitlementCatalog(
        version="super-tests-v1",
        tiers={
            "free": TierEntitlement(1, 1, 60),
            "starter": TierEntitlement(3, 3, 30),
            "plus": TierEntitlement(5, 10, 15),
            "super": TierEntitlement(None, 100, 1),
        },
    )
    client, session_factory = create_test_client(catalog=catalog)
    resume_id, criterion_id = _create_resume_and_criterion(client)
    created = _create_schedule(client, resume_id, criterion_id)

    forbidden = client.post(f"/api/v1/automation/schedules/{created['id']}/run-now")
    assert forbidden.status_code == 409
    assert forbidden.json()["detail"]["code"] == "super_account_required"

    with session_factory() as db:
        subscription = db.execute(select(UserSubscription)).scalar_one()
        subscription.tier_code = "super"
        db.commit()

    first = client.post(f"/api/v1/automation/schedules/{created['id']}/run-now")
    second = client.post(f"/api/v1/automation/schedules/{created['id']}/run-now")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    usage = client.get("/api/v1/account/usage")
    assert usage.status_code == 200
    assert usage.json()["unlimited_searches"] is True
    assert usage.json()["searches_per_period"] is None
    assert usage.json()["searches_available"] is None
    assert usage.json()["searches_reserved"] == 2

    with session_factory() as db:
        operations = list(db.scalars(select(ManagedOperation).order_by(ManagedOperation.id)))
        assert [item.request_payload["trigger"] for item in operations] == [
            "super_run_now",
            "super_run_now",
        ]


def test_schedule_requires_owned_resume_and_criterion() -> None:
    client, _session_factory = create_test_client()
    resume_id, criterion_id = _create_resume_and_criterion(client)

    missing_resume = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": criterion_id,
            "resume_profile_id": resume_id + 999,
            "interval_minutes": 60,
        },
    )
    assert missing_resume.status_code == 404
    assert missing_resume.json()["detail"]["code"] == "resume_not_found"

    missing_criterion = client.post(
        "/api/v1/automation/schedules",
        json={
            "criterion_id": criterion_id + 999,
            "resume_profile_id": resume_id,
            "interval_minutes": 60,
        },
    )
    assert missing_criterion.status_code == 404
    assert missing_criterion.json()["detail"]["code"] == "criterion_not_found"
