from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.automation.models import SearchRun, SearchSchedule, UsageLedger
from app.modules.automation.repository import consume_reservation, release_reservation
from app.modules.job_search.models import JobSearchCriterion
from app.modules.operations.models import ManagedOperation
from app.modules.profiles.models import ResumeProfile


LOGGER = logging.getLogger(__name__)
DEFAULT_LEASE_SECONDS = 5 * 60


@dataclass(frozen=True)
class WorkItem:
    run_id: int
    operation_id: int
    schedule_id: int
    workspace_id: int
    user_id: int
    attempt_count: int
    max_attempts: int
    request_payload: dict
    keyword: str
    location: str
    resume_profile_id: int
    resume_data_snapshot: dict
    minimum_match_score: int
    max_results: int


@dataclass(frozen=True)
class ExecutionResult:
    jobs_discovered: int = 0
    jobs_new: int = 0
    jobs_matched: int = 0
    matches_notified: int = 0
    result_payload: dict = field(default_factory=dict)
    artifacts: tuple[dict, ...] = field(default_factory=tuple, repr=False)

    def __post_init__(self) -> None:
        for value in (
            self.jobs_discovered,
            self.jobs_new,
            self.jobs_matched,
            self.matches_notified,
        ):
            if value < 0:
                raise ValueError("worker result counts cannot be negative")


class AutomatedSearchExecutor(Protocol):
    def execute(
        self,
        item: WorkItem,
        heartbeat: Callable[[], None],
    ) -> ExecutionResult:
        ...


class AutomationResultPersister(Protocol):
    def persist(
        self,
        db: Session,
        item: WorkItem,
        result: ExecutionResult,
    ) -> ExecutionResult:
        ...


class WorkerExecutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        quota_chargeable: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.quota_chargeable = quota_chargeable


class LeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerOutcome:
    claimed: bool
    run_id: int | None = None
    status: str | None = None
    attempt_count: int | None = None


def run_available(
    session_factory: Callable[[], Session],
    executor: AutomatedSearchExecutor,
    *,
    worker_id: str,
    max_runs: int = 100,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    persister: AutomationResultPersister | None = None,
) -> list[WorkerOutcome]:
    if max_runs < 1 or max_runs > 1000:
        raise ValueError("max_runs must be between 1 and 1000")
    outcomes: list[WorkerOutcome] = []
    for _ in range(max_runs):
        outcome = run_one(
            session_factory,
            executor,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            persister=persister,
        )
        if not outcome.claimed:
            break
        outcomes.append(outcome)
    return outcomes


def run_one(
    session_factory: Callable[[], Session],
    executor: AutomatedSearchExecutor,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
    persister: AutomationResultPersister | None = None,
) -> WorkerOutcome:
    current = _utc(now or datetime.now(timezone.utc))
    with session_factory() as db:
        item = claim_next_run(
            db,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            now=current,
        )
        db.commit()
    if item is None:
        return WorkerOutcome(claimed=False)

    def heartbeat() -> None:
        heartbeat_run(
            session_factory,
            run_id=item.run_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    try:
        # No database session is open while the executor performs provider work.
        result = executor.execute(item, heartbeat)
    except WorkerExecutionError as exc:
        try:
            status = finalize_failure(
                session_factory,
                item=item,
                worker_id=worker_id,
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
                quota_chargeable=exc.quota_chargeable,
                now=now,
            )
        except LeaseLost:
            status = "lease_lost"
    except Exception as exc:
        LOGGER.error(
            "automated_search_worker_failed run_id=%s attempt=%s exception_type=%s",
            item.run_id,
            item.attempt_count,
            type(exc).__name__,
        )
        try:
            status = finalize_failure(
                session_factory,
                item=item,
                worker_id=worker_id,
                code="unexpected_worker_error",
                message="Automated search failed unexpectedly.",
                retryable=True,
                quota_chargeable=False,
                now=now,
            )
        except LeaseLost:
            status = "lease_lost"
    else:
        try:
            finalize_success(
                session_factory,
                item=item,
                worker_id=worker_id,
                result=result,
                persister=persister,
                now=now,
            )
        except LeaseLost:
            status = "lease_lost"
        except Exception as exc:
            LOGGER.error(
                "automated_search_persistence_failed run_id=%s exception_type=%s",
                item.run_id,
                type(exc).__name__,
            )
            try:
                status = finalize_failure(
                    session_factory,
                    item=item,
                    worker_id=worker_id,
                    code="result_persistence_failed",
                    message="Automated search results could not be saved.",
                    retryable=True,
                    quota_chargeable=True,
                    now=now,
                )
            except LeaseLost:
                status = "lease_lost"
        else:
            status = "succeeded"
    return WorkerOutcome(
        claimed=True,
        run_id=item.run_id,
        status=status,
        attempt_count=item.attempt_count,
    )


def claim_next_run(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> WorkItem | None:
    _validate_worker(worker_id, lease_seconds)
    current = _utc(now or datetime.now(timezone.utc))
    candidates = list(
        db.scalars(
            select(SearchRun)
            .where(
                SearchRun.deleted_at.is_(None),
                or_(
                    SearchRun.status == "queued",
                    (SearchRun.status == "running")
                    & (SearchRun.lease_expires_at.is_not(None))
                    & (SearchRun.lease_expires_at <= current),
                ),
            )
            .order_by(SearchRun.scheduled_for.asc(), SearchRun.id.asc())
            .limit(20)
            .with_for_update(skip_locked=True)
        )
    )
    for run in candidates:
        operation = db.get(ManagedOperation, run.managed_operation_id)
        if operation is None:
            _fail_unclaimable_run(db, run, current, "missing_operation")
            continue
        if run.attempt_count >= run.max_attempts:
            _fail_unclaimable_run(db, run, current, "attempts_exhausted")
            continue
        schedule = db.get(SearchSchedule, run.schedule_id)
        if schedule is None or schedule.deleted_at is not None or not schedule.enabled:
            _cancel_unclaimable_run(db, run, operation, current, "schedule_inactive")
            continue
        criterion = db.get(JobSearchCriterion, schedule.criterion_id)
        profile = db.get(ResumeProfile, schedule.resume_profile_id)
        if (
            criterion is None
            or criterion.deleted_at is not None
            or criterion.user_id != run.user_id
            or criterion.workspace_id != run.workspace_id
            or not criterion.keyword.strip()
            or not (criterion.location or "").strip()
            or profile is None
            or profile.deleted_at is not None
            or profile.user_id != run.user_id
            or profile.workspace_id != run.workspace_id
        ):
            _fail_unclaimable_run(db, run, current, "invalid_schedule_context")
            continue

        run.status = "running"
        run.attempt_count += 1
        run.lease_owner = worker_id
        run.heartbeat_at = current
        run.lease_expires_at = current + timedelta(seconds=lease_seconds)
        run.started_at = run.started_at or current
        run.error_code = None
        run.error_message = None
        operation.status = "running"
        operation.attempt_count = run.attempt_count
        operation.started_at = operation.started_at or current
        operation.progress_message = "Automation worker is running"
        operation.error_code = None
        operation.error_message = None
        db.flush()
        return WorkItem(
            run_id=run.id,
            operation_id=operation.id,
            schedule_id=run.schedule_id,
            workspace_id=run.workspace_id,
            user_id=run.user_id,
            attempt_count=run.attempt_count,
            max_attempts=run.max_attempts,
            request_payload=dict(operation.request_payload or {}),
            keyword=criterion.keyword.strip(),
            location=(criterion.location or "").strip(),
            resume_profile_id=profile.id,
            resume_data_snapshot=dict(profile.resume_data or {}),
            minimum_match_score=schedule.minimum_match_score,
            max_results=max(1, min(int((operation.request_payload or {}).get("max_results", 10)), 10)),
        )
    db.flush()
    return None


def heartbeat_run(
    session_factory: Callable[[], Session],
    *,
    run_id: int,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> None:
    _validate_worker(worker_id, lease_seconds)
    current = _utc(now or datetime.now(timezone.utc))
    with session_factory() as db:
        run = db.scalar(
            select(SearchRun).where(SearchRun.id == run_id).with_for_update()
        )
        if run is None or run.status != "running" or run.lease_owner != worker_id:
            raise LeaseLost("worker no longer owns this search run")
        run.heartbeat_at = current
        run.lease_expires_at = current + timedelta(seconds=lease_seconds)
        db.commit()


def finalize_success(
    session_factory: Callable[[], Session],
    *,
    item: WorkItem,
    worker_id: str,
    result: ExecutionResult,
    persister: AutomationResultPersister | None = None,
    now: datetime | None = None,
) -> None:
    current = _utc(now or datetime.now(timezone.utc))
    with session_factory() as db:
        run = _owned_running_run(db, item.run_id, worker_id)
        operation = db.get(ManagedOperation, item.operation_id)
        if operation is None:
            raise RuntimeError("managed operation is missing during success finalization")
        if persister is not None:
            result = persister.persist(db, item, result)
        ledger = _run_ledger(db, run.id)
        consume_reservation(db, ledger_id=ledger.id, now=current)

        run.status = "succeeded"
        run.jobs_discovered = result.jobs_discovered
        run.jobs_new = result.jobs_new
        run.jobs_matched = result.jobs_matched
        run.matches_notified = result.matches_notified
        run.completed_at = current
        run.error_code = None
        run.error_message = None
        _clear_lease(run)

        operation.status = "succeeded"
        operation.result_payload = dict(result.result_payload)
        operation.request_payload = {}
        operation.progress_current = 1
        operation.progress_total = 1
        operation.progress_message = "Completed"
        operation.completed_at = current
        operation.error_code = None
        operation.error_message = None
        operation.usage = {
            **dict(operation.usage or {}),
            "jobs_discovered": result.jobs_discovered,
            "jobs_new": result.jobs_new,
            "jobs_matched": result.jobs_matched,
            "matches_notified": result.matches_notified,
        }
        schedule = db.get(SearchSchedule, run.schedule_id)
        if schedule is not None:
            schedule.last_completed_at = current
            schedule.consecutive_failure_count = 0
        db.commit()


def finalize_failure(
    session_factory: Callable[[], Session],
    *,
    item: WorkItem,
    worker_id: str,
    code: str,
    message: str,
    retryable: bool,
    quota_chargeable: bool,
    now: datetime | None = None,
) -> str:
    current = _utc(now or datetime.now(timezone.utc))
    safe_code = (code.strip() or "worker_failed")[:80]
    safe_message = (message.strip() or "Automated search failed.")[:2000]
    with session_factory() as db:
        run = _owned_running_run(db, item.run_id, worker_id)
        operation = db.get(ManagedOperation, item.operation_id)
        if operation is None:
            raise RuntimeError("managed operation is missing during failure finalization")
        can_retry = retryable and run.attempt_count < run.max_attempts
        run.error_code = safe_code
        run.error_message = safe_message
        operation.error_code = safe_code
        operation.error_message = safe_message
        _clear_lease(run)
        if can_retry:
            run.status = "queued"
            operation.status = "queued"
            operation.progress_message = "Waiting to retry"
            db.commit()
            return "queued"

        run.status = "failed"
        run.completed_at = current
        operation.status = "failed"
        operation.progress_message = "Failed"
        operation.completed_at = current
        ledger = _run_ledger(db, run.id)
        if quota_chargeable:
            consume_reservation(db, ledger_id=ledger.id, now=current)
        else:
            release_reservation(
                db,
                ledger_id=ledger.id,
                reason=f"{safe_code}: failed request was not charged",
                now=current,
            )
        schedule = db.get(SearchSchedule, run.schedule_id)
        if schedule is not None:
            schedule.last_completed_at = current
            schedule.consecutive_failure_count += 1
        db.commit()
        return "failed"


def _owned_running_run(db: Session, run_id: int, worker_id: str) -> SearchRun:
    run = db.scalar(
        select(SearchRun).where(SearchRun.id == run_id).with_for_update()
    )
    if run is None or run.status != "running" or run.lease_owner != worker_id:
        raise LeaseLost("worker no longer owns this search run")
    return run


def _run_ledger(db: Session, run_id: int) -> UsageLedger:
    ledger = db.scalar(
        select(UsageLedger).where(UsageLedger.search_run_id == run_id).with_for_update()
    )
    if ledger is None:
        raise RuntimeError("search run has no usage reservation")
    return ledger


def _fail_unclaimable_run(
    db: Session,
    run: SearchRun,
    current: datetime,
    code: str,
) -> None:
    run.status = "failed"
    run.error_code = code
    run.error_message = "Search run cannot be claimed."
    run.completed_at = current
    _clear_lease(run)
    operation = db.get(ManagedOperation, run.managed_operation_id)
    if operation is not None:
        operation.status = "failed"
        operation.error_code = code
        operation.error_message = run.error_message
        operation.progress_message = "Failed"
        operation.completed_at = current
    ledger = db.scalar(
        select(UsageLedger).where(UsageLedger.search_run_id == run.id)
    )
    if ledger is not None and ledger.state == "reserved" and code in {
        "missing_operation",
        "invalid_schedule_context",
    }:
        release_reservation(
            db,
            ledger_id=ledger.id,
            reason=f"{code}: provider was not called",
            now=current,
        )
    elif ledger is not None and ledger.state == "reserved":
        # An expired final lease may have reached the provider. Consume the
        # reservation conservatively instead of under-reporting provider cost.
        consume_reservation(db, ledger_id=ledger.id, now=current)


def _cancel_unclaimable_run(
    db: Session,
    run: SearchRun,
    operation: ManagedOperation,
    current: datetime,
    code: str,
) -> None:
    run.status = "cancelled"
    run.error_code = code
    run.error_message = "Search run was cancelled before provider execution."
    run.completed_at = current
    _clear_lease(run)
    operation.status = "cancelled"
    operation.error_code = code
    operation.error_message = run.error_message
    operation.progress_message = "Cancelled"
    operation.completed_at = current
    ledger = db.scalar(select(UsageLedger).where(UsageLedger.search_run_id == run.id))
    if ledger is not None and ledger.state == "reserved":
        release_reservation(
            db,
            ledger_id=ledger.id,
            reason=f"{code}: provider was not called",
            now=current,
        )


def _clear_lease(run: SearchRun) -> None:
    run.lease_owner = None
    run.lease_expires_at = None
    run.heartbeat_at = None


def _validate_worker(worker_id: str, lease_seconds: int) -> None:
    if not worker_id.strip() or len(worker_id) > 120:
        raise ValueError("worker_id must contain 1 to 120 characters")
    if lease_seconds < 30 or lease_seconds > 3600:
        raise ValueError("lease_seconds must be between 30 and 3600")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
