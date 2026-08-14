from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.accounts.models import User, Workspace
from app.modules.automation.models import (
    NotificationDelivery,
    SearchRun,
    SearchSchedule,
    UsageLedger,
    UserSubscription,
)
from app.modules.automation.executor import (
    DatabaseAutomationResultPersister,
    ProviderAutomatedSearchExecutor,
)
from app.modules.automation.worker import (
    ExecutionResult,
    LeaseLost,
    WorkItem,
    WorkerExecutionError,
    claim_next_run,
    finalize_success,
    heartbeat_run,
    run_one,
)
from app.modules.job_search.models import JobSearchCriterion
from app.modules.jobs.models import JobCache, JobResumeMatch, UserSavedJob
from app.modules.jobs.schemas import IndeedJobSearchResult, JobDescriptionData
from app.modules.operations.models import ManagedOperation
from app.modules.profiles.models import ResumeProfile
from app.modules.resume_job_match.schemas import ResumeJobMatchResponse


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class SuccessfulExecutor:
    def __init__(self, *, send_heartbeat: bool = False) -> None:
        self.send_heartbeat = send_heartbeat
        self.items: list[WorkItem] = []

    def execute(self, item: WorkItem, heartbeat) -> ExecutionResult:
        self.items.append(item)
        if self.send_heartbeat:
            heartbeat()
        return ExecutionResult(
            jobs_discovered=5,
            jobs_new=3,
            jobs_matched=3,
            matches_notified=2,
            result_payload={"qualifying_match_ids": [101, 102]},
        )


class FailingExecutor:
    def __init__(self, *, retryable: bool, quota_chargeable: bool) -> None:
        self.retryable = retryable
        self.quota_chargeable = quota_chargeable

    def execute(self, item: WorkItem, heartbeat) -> ExecutionResult:
        del item, heartbeat
        raise WorkerExecutionError(
            "provider_unavailable",
            "The provider is temporarily unavailable.",
            retryable=self.retryable,
            quota_chargeable=self.quota_chargeable,
        )


class FakeSearchProvider:
    def search(self, *, keyword: str, location: str, max_results: int) -> list[IndeedJobSearchResult]:
        assert keyword == "Backend Engineer"
        assert location == "Remote"
        assert max_results == 10
        return [
            IndeedJobSearchResult(
                title="Strong Backend Engineer",
                company="Example Co",
                location="Remote",
                source_url="https://example.com/jobs/strong",
                raw_description_text="Python FastAPI backend role.",
            ),
            IndeedJobSearchResult(
                title="Frontend Engineer",
                company="Example Co",
                location="Remote",
                source_url="https://example.com/jobs/frontend",
                raw_description_text="Frontend JavaScript role.",
            ),
        ]


class FakeDescriptionParser:
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        if "FastAPI" in raw_description_text:
            return JobDescriptionData(
                title="Strong Backend Engineer",
                company="Example Co",
                required_skills=["Python", "FastAPI"],
            )
        return JobDescriptionData(
            title="Frontend Engineer",
            company="Example Co",
            required_skills=["JavaScript"],
        )


class FakeResumeMatcher:
    def compare(self, request) -> ResumeJobMatchResponse:
        strong = "FastAPI" in (request.job_description_text or "")
        return ResumeJobMatchResponse(
            match_score=8 if strong else 4,
            summary="Strong match." if strong else "Below threshold.",
            matched_skills=["Python"] if strong else [],
            missing_skills=[] if strong else ["JavaScript"],
            matched_keywords=[],
            missing_keywords=[],
            supported_requirements=[],
            unsupported_requirements=[],
            recommended_resume_updates=[],
            provider_model_name="fake-matcher",
            provider_execution_reference="fake-execution",
        )


@pytest.fixture
def session_factory() -> sessionmaker:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _queued_run(session_factory: sessionmaker, *, max_attempts: int = 3) -> tuple[int, int, int, int]:
    with session_factory() as db:
        user = User(email="worker@example.com", display_name="Worker User")
        db.add(user)
        db.flush()
        workspace = Workspace(owner_user_id=user.id, name="Worker Search")
        db.add(workspace)
        db.flush()
        subscription = UserSubscription(
            workspace_id=workspace.id,
            user_id=user.id,
            tier_code="free",
            status="active",
            entitlement_version="worker-tests-v1",
            period_started_at=NOW,
            period_ends_at=NOW + timedelta(days=7),
        )
        profile = ResumeProfile(
            workspace_id=workspace.id,
            user_id=user.id,
            title="Backend Resume",
            resume_data={"headline": "Backend Engineer", "skills": ["Python"]},
            is_default=True,
        )
        db.add_all([subscription, profile])
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
            next_run_at=NOW + timedelta(hours=1),
            last_claimed_at=NOW,
        )
        operation = ManagedOperation(
            workspace_id=workspace.id,
            user_id=user.id,
            operation_type="automated_job_search",
            idempotency_key="worker-run-operation",
            status="queued",
            request_payload={
                "schedule_id": 1,
                "criterion_id": criterion.id,
                "resume_profile_id": profile.id,
                "minimum_match_score": 7,
            },
        )
        db.add_all([schedule, operation])
        db.flush()
        run = SearchRun(
            workspace_id=workspace.id,
            user_id=user.id,
            schedule_id=schedule.id,
            managed_operation_id=operation.id,
            status="queued",
            max_attempts=max_attempts,
            scheduled_for=NOW,
        )
        db.add(run)
        db.flush()
        ledger = UsageLedger(
            workspace_id=workspace.id,
            user_id=user.id,
            subscription_id=subscription.id,
            search_run_id=run.id,
            usage_type="provider_search",
            units=1,
            state="reserved",
            idempotency_key="worker-run-usage",
            entitlement_version="worker-tests-v1",
            tier_code_snapshot="free",
            allowance_snapshot=4,
            reserved_at=NOW,
        )
        db.add(ledger)
        db.commit()
        return run.id, operation.id, ledger.id, schedule.id


def test_worker_success_finalizes_run_operation_quota_and_schedule(session_factory: sessionmaker) -> None:
    run_id, operation_id, ledger_id, schedule_id = _queued_run(session_factory)
    executor = SuccessfulExecutor()

    outcome = run_one(
        session_factory,
        executor,
        worker_id="worker-a",
        lease_seconds=60,
        now=NOW,
    )

    assert outcome.claimed is True
    assert outcome.run_id == run_id
    assert outcome.status == "succeeded"
    assert executor.items[0].request_payload["minimum_match_score"] == 7
    with session_factory() as db:
        run = db.get(SearchRun, run_id)
        operation = db.get(ManagedOperation, operation_id)
        ledger = db.get(UsageLedger, ledger_id)
        schedule = db.get(SearchSchedule, schedule_id)
        assert run.status == "succeeded"
        assert run.attempt_count == 1
        assert run.jobs_discovered == 5
        assert run.jobs_new == 3
        assert run.jobs_matched == 3
        assert run.matches_notified == 2
        assert run.lease_owner is None
        assert operation.status == "succeeded"
        assert operation.request_payload == {}
        assert operation.result_payload == {"qualifying_match_ids": [101, 102]}
        assert operation.usage["jobs_discovered"] == 5
        assert ledger.state == "consumed"
        assert schedule.consecutive_failure_count == 0
        assert schedule.last_completed_at is not None


def test_retry_keeps_quota_reserved_then_second_attempt_succeeds(session_factory: sessionmaker) -> None:
    run_id, operation_id, ledger_id, _schedule_id = _queued_run(session_factory, max_attempts=2)

    first = run_one(
        session_factory,
        FailingExecutor(retryable=True, quota_chargeable=False),
        worker_id="worker-a",
        lease_seconds=60,
        now=NOW,
    )
    assert first.status == "queued"
    with session_factory() as db:
        assert db.get(SearchRun, run_id).status == "queued"
        assert db.get(SearchRun, run_id).attempt_count == 1
        assert db.get(ManagedOperation, operation_id).status == "queued"
        assert db.get(UsageLedger, ledger_id).state == "reserved"

    second = run_one(
        session_factory,
        SuccessfulExecutor(),
        worker_id="worker-b",
        lease_seconds=60,
        now=NOW + timedelta(minutes=1),
    )
    assert second.status == "succeeded"
    assert second.attempt_count == 2
    with session_factory() as db:
        assert db.get(SearchRun, run_id).attempt_count == 2
        assert db.get(UsageLedger, ledger_id).state == "consumed"


def test_terminal_failed_provider_request_releases_quota(session_factory: sessionmaker) -> None:
    run_id, operation_id, ledger_id, schedule_id = _queued_run(session_factory, max_attempts=1)

    outcome = run_one(
        session_factory,
        FailingExecutor(retryable=True, quota_chargeable=False),
        worker_id="worker-a",
        lease_seconds=60,
        now=NOW,
    )

    assert outcome.status == "failed"
    with session_factory() as db:
        assert db.get(SearchRun, run_id).status == "failed"
        assert db.get(ManagedOperation, operation_id).status == "failed"
        assert db.get(UsageLedger, ledger_id).state == "released"
        assert db.get(SearchSchedule, schedule_id).consecutive_failure_count == 1


def test_terminal_downstream_failure_consumes_quota_after_usable_provider_response(
    session_factory: sessionmaker,
) -> None:
    run_id, _operation_id, ledger_id, _schedule_id = _queued_run(session_factory, max_attempts=1)

    outcome = run_one(
        session_factory,
        FailingExecutor(retryable=False, quota_chargeable=True),
        worker_id="worker-a",
        lease_seconds=60,
        now=NOW,
    )

    assert outcome.run_id == run_id
    assert outcome.status == "failed"
    with session_factory() as db:
        assert db.get(UsageLedger, ledger_id).state == "consumed"


def test_active_lease_prevents_duplicate_worker_and_expired_lease_is_reclaimed(
    session_factory: sessionmaker,
) -> None:
    run_id, _operation_id, _ledger_id, _schedule_id = _queued_run(session_factory)
    with session_factory() as db:
        first_item = claim_next_run(
            db,
            worker_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        db.commit()
    assert first_item is not None
    assert first_item.attempt_count == 1

    blocked = run_one(
        session_factory,
        SuccessfulExecutor(),
        worker_id="worker-b",
        lease_seconds=60,
        now=NOW + timedelta(seconds=30),
    )
    assert blocked.claimed is False

    reclaimed = run_one(
        session_factory,
        SuccessfulExecutor(),
        worker_id="worker-b",
        lease_seconds=60,
        now=NOW + timedelta(seconds=61),
    )
    assert reclaimed.claimed is True
    assert reclaimed.run_id == run_id
    assert reclaimed.attempt_count == 2

    with pytest.raises(LeaseLost):
        finalize_success(
            session_factory,
            item=first_item,
            worker_id="worker-a",
            result=ExecutionResult(),
            now=NOW + timedelta(seconds=62),
        )


def test_heartbeat_extends_worker_lease(session_factory: sessionmaker) -> None:
    run_id, _operation_id, _ledger_id, _schedule_id = _queued_run(session_factory)
    with session_factory() as db:
        item = claim_next_run(
            db,
            worker_id="worker-a",
            lease_seconds=60,
            now=NOW,
        )
        db.commit()
    assert item is not None

    heartbeat_run(
        session_factory,
        run_id=run_id,
        worker_id="worker-a",
        lease_seconds=60,
        now=NOW + timedelta(seconds=40),
    )
    blocked = run_one(
        session_factory,
        SuccessfulExecutor(),
        worker_id="worker-b",
        lease_seconds=60,
        now=NOW + timedelta(seconds=70),
    )
    assert blocked.claimed is False

    reclaimed = run_one(
        session_factory,
        SuccessfulExecutor(),
        worker_id="worker-b",
        lease_seconds=60,
        now=NOW + timedelta(seconds=101),
    )
    assert reclaimed.claimed is True


def test_provider_executor_persists_deduplicated_jobs_and_only_qualifying_matches(
    session_factory: sessionmaker,
) -> None:
    run_id, operation_id, ledger_id, _schedule_id = _queued_run(session_factory)
    executor = ProviderAutomatedSearchExecutor(
        search_provider=FakeSearchProvider(),
        parser=FakeDescriptionParser(),
        matcher=FakeResumeMatcher(),
    )

    outcome = run_one(
        session_factory,
        executor,
        worker_id="provider-worker",
        lease_seconds=60,
        now=NOW,
        persister=DatabaseAutomationResultPersister(),
    )

    assert outcome.status == "succeeded"
    with session_factory() as db:
        run = db.get(SearchRun, run_id)
        operation = db.get(ManagedOperation, operation_id)
        ledger = db.get(UsageLedger, ledger_id)
        caches = db.query(JobCache).order_by(JobCache.id).all()
        saved_jobs = db.query(UserSavedJob).all()
        matches = db.query(JobResumeMatch).all()
        assert run.jobs_discovered == 2
        assert run.jobs_new == 1
        assert run.jobs_matched == 1
        assert run.matches_notified == 1
        assert len(caches) == 1
        assert len(saved_jobs) == 1
        assert saved_jobs[0].jobs_cache_id == caches[0].id
        assert len(matches) == 1
        assert db.query(NotificationDelivery).count() == 2
        assert matches[0].match_score == 8
        assert matches[0].match_origin == "automated_search"
        assert matches[0].resume_data_snapshot["headline"] == "Backend Engineer"
        assert operation.result_payload["qualifying_job_ids"] == [saved_jobs[0].id]
        assert operation.result_payload["qualifying_match_ids"] == [matches[0].id]
        assert ledger.state == "consumed"

        second_operation = ManagedOperation(
            workspace_id=run.workspace_id,
            user_id=run.user_id,
            operation_type="automated_job_search",
            idempotency_key="worker-run-operation-2",
            status="queued",
            request_payload={
                "schedule_id": run.schedule_id,
                "criterion_id": operation.result_payload.get("criterion_id", 1),
                "resume_profile_id": matches[0].resume_profile_id,
                "minimum_match_score": 7,
                "max_results": 10,
            },
        )
        db.add(second_operation)
        db.flush()
        second_run = SearchRun(
            workspace_id=run.workspace_id,
            user_id=run.user_id,
            schedule_id=run.schedule_id,
            managed_operation_id=second_operation.id,
            status="queued",
            scheduled_for=NOW + timedelta(hours=1),
        )
        db.add(second_run)
        db.flush()
        second_ledger = UsageLedger(
            workspace_id=run.workspace_id,
            user_id=run.user_id,
            subscription_id=ledger.subscription_id,
            search_run_id=second_run.id,
            usage_type="provider_search",
            units=1,
            state="reserved",
            idempotency_key="worker-run-usage-2",
            entitlement_version="worker-tests-v1",
            tier_code_snapshot="free",
            allowance_snapshot=4,
            reserved_at=NOW + timedelta(hours=1),
        )
        db.add(second_ledger)
        db.commit()

    repeated = run_one(
        session_factory,
        executor,
        worker_id="provider-worker",
        lease_seconds=60,
        now=NOW + timedelta(hours=1),
        persister=DatabaseAutomationResultPersister(),
    )
    assert repeated.status == "succeeded"
    with session_factory() as db:
        second_run = db.get(SearchRun, repeated.run_id)
        assert second_run.jobs_new == 0
        assert second_run.matches_notified == 0
        assert db.query(JobCache).count() == 1
        assert db.query(UserSavedJob).count() == 1
        assert db.query(JobResumeMatch).count() == 1
        assert db.query(NotificationDelivery).count() == 2
