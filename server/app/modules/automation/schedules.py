from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.automation.entitlements import EntitlementCatalog, TierEntitlement
from app.modules.automation.models import SearchRun, SearchSchedule, UsageLedger, UserSubscription
from app.modules.automation.repository import (
    SubscriptionUnavailable,
    ensure_free_subscription,
    release_reservation,
    usage_summary,
)
from app.modules.job_search.criteria_repository import get_criterion
from app.modules.profiles.repository import ensure_account_for_identity, get_resume_profile_for_identity
from app.modules.operations.models import ManagedOperation


class ScheduleValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def entitlement_details(
    db: Session,
    identity: AuthenticatedIdentity,
    catalog: EntitlementCatalog,
    *,
    now: datetime | None = None,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    subscription = ensure_free_subscription(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        catalog=catalog,
        now=now,
    )
    summary = usage_summary(db, user_id=user.id, catalog=catalog, now=now)
    entitlement = catalog.for_tier(subscription.tier_code)
    return {
        "tier_code": subscription.tier_code,
        "status": subscription.status,
        "entitlement_version": summary.entitlement_version,
        "period_started_at": summary.period_started_at,
        "period_ends_at": summary.period_ends_at,
        "searches_per_period": summary.allowance,
        "searches_reserved": summary.reserved,
        "searches_consumed": summary.consumed,
        "searches_available": summary.available,
        "unlimited_searches": summary.allowance is None,
        "maximum_active_criteria": entitlement.maximum_active_criteria,
        "minimum_interval_minutes": entitlement.minimum_interval_minutes,
    }


def list_schedules(
    db: Session,
    identity: AuthenticatedIdentity,
) -> list[SearchSchedule]:
    user, workspace = ensure_account_for_identity(db, identity)
    return list(
        db.scalars(
            select(SearchSchedule)
            .where(
                SearchSchedule.workspace_id == workspace.id,
                SearchSchedule.user_id == user.id,
                SearchSchedule.deleted_at.is_(None),
            )
            .order_by(SearchSchedule.created_at.desc(), SearchSchedule.id.desc())
        )
    )


def get_schedule(
    db: Session,
    identity: AuthenticatedIdentity,
    schedule_id: int,
) -> SearchSchedule | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(SearchSchedule).where(
            SearchSchedule.id == schedule_id,
            SearchSchedule.workspace_id == workspace.id,
            SearchSchedule.user_id == user.id,
            SearchSchedule.deleted_at.is_(None),
        )
    )


def create_schedule(
    db: Session,
    identity: AuthenticatedIdentity,
    catalog: EntitlementCatalog,
    *,
    criterion_id: int,
    resume_profile_id: int,
    interval_minutes: int,
    minimum_match_score: int,
    enabled: bool,
    next_run_at: datetime | None,
) -> SearchSchedule:
    user, workspace = ensure_account_for_identity(db, identity)
    subscription, entitlement = _subscription_entitlement(db, user.id, catalog)
    criterion = get_criterion(db, identity, criterion_id)
    if criterion is None:
        raise ScheduleValidationError("criterion_not_found", "Saved search criterion not found.")
    profile = get_resume_profile_for_identity(db, identity, resume_profile_id)
    if profile is None:
        raise ScheduleValidationError("resume_not_found", "Resume profile not found.")
    if criterion.resume_profile_id is not None and criterion.resume_profile_id != profile.id:
        raise ScheduleValidationError(
            "resume_mismatch",
            "The saved search criterion belongs to a different resume profile.",
        )
    _validate_interval(interval_minutes, entitlement)

    existing = db.scalar(
        select(SearchSchedule).where(SearchSchedule.criterion_id == criterion.id)
    )
    if existing is not None and existing.deleted_at is None:
        raise ScheduleValidationError("schedule_exists", "A schedule already exists for this criterion.")
    if enabled:
        _enforce_active_limit(db, user.id, entitlement)
    current = _utc(datetime.now(timezone.utc))
    if existing is not None:
        if existing.user_id != user.id or existing.workspace_id != workspace.id:
            raise ScheduleValidationError("criterion_in_use", "Saved search criterion is already scheduled.")
        schedule = existing
        schedule.deleted_at = None
    else:
        schedule = SearchSchedule(
            workspace_id=workspace.id,
            user_id=user.id,
            criterion_id=criterion.id,
            resume_profile_id=profile.id,
            interval_minutes=interval_minutes,
            minimum_match_score=minimum_match_score,
            next_run_at=_utc(next_run_at or current),
        )
        db.add(schedule)

    schedule.resume_profile_id = profile.id
    schedule.interval_minutes = interval_minutes
    schedule.minimum_match_score = minimum_match_score
    schedule.enabled = enabled
    schedule.next_run_at = _utc(next_run_at or current)
    schedule.paused_reason = None if enabled else "Paused by user"
    subscription.entitlement_version = catalog.version
    db.flush()
    db.refresh(schedule)
    return schedule


def update_schedule(
    db: Session,
    identity: AuthenticatedIdentity,
    schedule: SearchSchedule,
    catalog: EntitlementCatalog,
    *,
    resume_profile_id: int | None = None,
    interval_minutes: int | None = None,
    minimum_match_score: int | None = None,
    enabled: bool | None = None,
    next_run_at: datetime | None = None,
    next_run_at_was_set: bool = False,
) -> SearchSchedule:
    subscription, entitlement = _subscription_entitlement(db, schedule.user_id, catalog)
    if resume_profile_id is not None:
        profile = get_resume_profile_for_identity(db, identity, resume_profile_id)
        if profile is None:
            raise ScheduleValidationError("resume_not_found", "Resume profile not found.")
        criterion = get_criterion(db, identity, schedule.criterion_id)
        if criterion is None:
            raise ScheduleValidationError("criterion_not_found", "Saved search criterion not found.")
        if criterion.resume_profile_id is not None and criterion.resume_profile_id != profile.id:
            raise ScheduleValidationError(
                "resume_mismatch",
                "The saved search criterion belongs to a different resume profile.",
            )
        schedule.resume_profile_id = profile.id
    if interval_minutes is not None:
        _validate_interval(interval_minutes, entitlement)
        schedule.interval_minutes = interval_minutes
    if minimum_match_score is not None:
        schedule.minimum_match_score = minimum_match_score
    if enabled is True and not schedule.enabled:
        _enforce_active_limit(db, schedule.user_id, entitlement, excluding_schedule_id=schedule.id)
        schedule.enabled = True
        schedule.paused_reason = None
        if _utc(schedule.next_run_at) < datetime.now(timezone.utc):
            schedule.next_run_at = datetime.now(timezone.utc)
    elif enabled is False:
        schedule.enabled = False
        schedule.paused_reason = "Paused by user"
    if next_run_at_was_set:
        if next_run_at is None:
            raise ScheduleValidationError("next_run_required", "next_run_at cannot be null.")
        schedule.next_run_at = _utc(next_run_at)
    subscription.entitlement_version = catalog.version
    db.flush()
    db.refresh(schedule)
    return schedule


def pause_schedule(db: Session, schedule: SearchSchedule) -> SearchSchedule:
    schedule.enabled = False
    schedule.paused_reason = "Paused by user"
    db.flush()
    db.refresh(schedule)
    return schedule


def resume_schedule(
    db: Session,
    schedule: SearchSchedule,
    catalog: EntitlementCatalog,
) -> SearchSchedule:
    _subscription, entitlement = _subscription_entitlement(db, schedule.user_id, catalog)
    _validate_interval(schedule.interval_minutes, entitlement)
    _enforce_active_limit(db, schedule.user_id, entitlement, excluding_schedule_id=schedule.id)
    schedule.enabled = True
    schedule.paused_reason = None
    now = datetime.now(timezone.utc)
    if _utc(schedule.next_run_at) < now:
        schedule.next_run_at = now
    db.flush()
    db.refresh(schedule)
    return schedule


def soft_delete_schedule(db: Session, schedule: SearchSchedule) -> None:
    now = datetime.now(timezone.utc)
    schedule.enabled = False
    schedule.paused_reason = "Deleted by user"
    schedule.deleted_at = now
    for run in db.scalars(
        select(SearchRun).where(
            SearchRun.schedule_id == schedule.id,
            SearchRun.status == "queued",
            SearchRun.deleted_at.is_(None),
        )
    ):
        run.status = "cancelled"
        run.error_code = "schedule_deleted"
        run.error_message = "Cancelled because the schedule was deleted."
        run.completed_at = now
        ledger = db.scalar(
            select(UsageLedger).where(
                UsageLedger.search_run_id == run.id,
                UsageLedger.state == "reserved",
            )
        )
        if ledger is not None:
            release_reservation(
                db,
                ledger_id=ledger.id,
                reason="Schedule deleted before provider execution",
                now=now,
            )
        if run.managed_operation_id is not None:
            operation = db.get(ManagedOperation, run.managed_operation_id)
            if operation is not None and operation.status == "queued":
                operation.status = "cancelled"
                operation.cancel_requested_at = now
                operation.completed_at = now
                operation.progress_message = "Cancelled because the schedule was deleted"
    db.flush()


def list_runs(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    limit: int = 50,
    before_id: int | None = None,
) -> tuple[list[SearchRun], int | None]:
    user, workspace = ensure_account_for_identity(db, identity)
    statement = select(SearchRun).where(
        SearchRun.workspace_id == workspace.id,
        SearchRun.user_id == user.id,
        SearchRun.deleted_at.is_(None),
    )
    if before_id is not None:
        statement = statement.where(SearchRun.id < before_id)
    rows = list(
        db.scalars(
            statement.order_by(SearchRun.id.desc()).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return rows, rows[-1].id if has_more and rows else None


def get_run(
    db: Session,
    identity: AuthenticatedIdentity,
    run_id: int,
) -> SearchRun | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(SearchRun).where(
            SearchRun.id == run_id,
            SearchRun.workspace_id == workspace.id,
            SearchRun.user_id == user.id,
            SearchRun.deleted_at.is_(None),
        )
    )


def run_schedule_now(
    db: Session,
    identity: AuthenticatedIdentity,
    schedule: SearchSchedule,
    catalog: EntitlementCatalog,
) -> SearchRun:
    # Identity ownership has already been established by get_schedule. Keep
    # dispatching in the durable automation queue so the normal worker,
    # provider-failure accounting, and match persistence paths are reused.
    from app.modules.automation.dispatcher import dispatch_schedule_now

    user, _workspace = ensure_account_for_identity(db, identity)
    if user.id != schedule.user_id:
        raise ScheduleValidationError("schedule_not_found", "Search schedule not found.")
    try:
        return dispatch_schedule_now(db, catalog, schedule)
    except PermissionError as exc:
        raise ScheduleValidationError("super_account_required", str(exc)) from exc


def account_usage_details(
    db: Session,
    identity: AuthenticatedIdentity,
    catalog: EntitlementCatalog,
    *,
    limit: int,
    before_id: int | None,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    summary = usage_summary(db, user_id=user.id, catalog=catalog)
    statement = select(UsageLedger).where(
        UsageLedger.workspace_id == workspace.id,
        UsageLedger.user_id == user.id,
        UsageLedger.reserved_at >= summary.period_started_at,
        UsageLedger.reserved_at < summary.period_ends_at,
        UsageLedger.deleted_at.is_(None),
    )
    if before_id is not None:
        statement = statement.where(UsageLedger.id < before_id)
    entries = list(db.scalars(statement.order_by(UsageLedger.id.desc()).limit(limit + 1)))
    has_more = len(entries) > limit
    entries = entries[:limit]
    return {
        "tier_code": summary.tier_code,
        "entitlement_version": summary.entitlement_version,
        "period_started_at": summary.period_started_at,
        "period_ends_at": summary.period_ends_at,
        "searches_per_period": summary.allowance,
        "searches_reserved": summary.reserved,
        "searches_consumed": summary.consumed,
        "searches_available": summary.available,
        "unlimited_searches": summary.allowance is None,
        "entries": entries,
        "next_cursor": entries[-1].id if has_more and entries else None,
    }


def _subscription_entitlement(
    db: Session,
    user_id: int,
    catalog: EntitlementCatalog,
) -> tuple[UserSubscription, TierEntitlement]:
    subscription = db.scalar(
        select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.deleted_at.is_(None),
        )
    )
    if subscription is None:
        raise SubscriptionUnavailable("user has no active subscription")
    if subscription.status != "active":
        raise SubscriptionUnavailable(f"subscription is {subscription.status}")
    return subscription, catalog.for_tier(subscription.tier_code)


def _enforce_active_limit(
    db: Session,
    user_id: int,
    entitlement: TierEntitlement,
    *,
    excluding_schedule_id: int | None = None,
) -> None:
    query = select(func.count(SearchSchedule.id)).where(
        SearchSchedule.user_id == user_id,
        SearchSchedule.enabled.is_(True),
        SearchSchedule.deleted_at.is_(None),
    )
    if excluding_schedule_id is not None:
        query = query.where(SearchSchedule.id != excluding_schedule_id)
    active_count = int(db.scalar(query) or 0)
    if active_count >= entitlement.maximum_active_criteria:
        raise ScheduleValidationError(
            "active_schedule_limit",
            "The current tier does not allow another active search criterion.",
        )


def _validate_interval(interval_minutes: int, entitlement: TierEntitlement) -> None:
    if interval_minutes < entitlement.minimum_interval_minutes:
        raise ScheduleValidationError(
            "interval_below_tier_minimum",
            f"The current tier requires at least {entitlement.minimum_interval_minutes} minutes between searches.",
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
