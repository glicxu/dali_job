from __future__ import annotations

import hashlib
import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.automation.entitlements import EntitlementCatalog, SUPER_TIER_CODE
from app.modules.automation.models import SearchRun, SearchSchedule, UserSubscription
from app.modules.automation.repository import QuotaExceeded, SubscriptionUnavailable, reserve_provider_search
from app.modules.operations.models import ManagedOperation


AUTOMATED_SEARCH_OPERATION = "automated_job_search"


@dataclass
class DispatchSummary:
    inspected: int = 0
    queued_run_ids: list[int] = field(default_factory=list)
    skipped_existing: int = 0
    skipped_quota: int = 0
    paused_subscription: int = 0
    paused_tier_rule: int = 0

    @property
    def queued(self) -> int:
        return len(self.queued_run_ids)


def dispatch_due_schedules(
    db: Session,
    catalog: EntitlementCatalog,
    *,
    now: datetime | None = None,
    limit: int = 100,
    matching_v2_enabled: bool = False,
) -> DispatchSummary:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    current = _utc(now or datetime.now(timezone.utc))
    due = list(
        db.scalars(
            select(SearchSchedule)
            .where(
                SearchSchedule.enabled.is_(True),
                SearchSchedule.deleted_at.is_(None),
                SearchSchedule.next_run_at <= current,
            )
            .order_by(SearchSchedule.next_run_at.asc(), SearchSchedule.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    summary = DispatchSummary(inspected=len(due))
    for schedule in due:
        scheduled_for = _utc(schedule.next_run_at)
        existing = db.scalar(
            select(SearchRun).where(
                SearchRun.schedule_id == schedule.id,
                SearchRun.scheduled_for == scheduled_for,
            )
        )
        if existing is not None:
            schedule.last_claimed_at = current
            schedule.next_run_at = _next_occurrence(schedule, scheduled_for, current)
            summary.skipped_existing += 1
            continue

        subscription = db.scalar(
            select(UserSubscription).where(
                UserSubscription.user_id == schedule.user_id,
                UserSubscription.deleted_at.is_(None),
            )
        )
        if subscription is None or subscription.status != "active":
            schedule.enabled = False
            schedule.paused_reason = "Subscription unavailable"
            summary.paused_subscription += 1
            continue

        entitlement = catalog.for_tier(subscription.tier_code)
        if schedule.interval_minutes < entitlement.minimum_interval_minutes:
            schedule.enabled = False
            schedule.paused_reason = (
                f"Tier requires at least {entitlement.minimum_interval_minutes} minutes between searches"
            )
            summary.paused_tier_rule += 1
            continue

        idempotency_key = _occurrence_key(schedule.id, scheduled_for)
        try:
            ledger, _created = reserve_provider_search(
                db,
                user_id=schedule.user_id,
                idempotency_key=idempotency_key,
                reason=f"Scheduled search {schedule.id}",
                catalog=catalog,
                now=current,
            )
        except QuotaExceeded:
            # reserve_provider_search advances the subscription period before
            # calculating usage, so period_ends_at is the correct retry point.
            schedule.paused_reason = "Search allowance exhausted"
            schedule.next_run_at = _utc(subscription.period_ends_at)
            summary.skipped_quota += 1
            continue
        except SubscriptionUnavailable:
            schedule.enabled = False
            schedule.paused_reason = "Subscription unavailable"
            summary.paused_subscription += 1
            continue

        operation = ManagedOperation(
            workspace_id=schedule.workspace_id,
            user_id=schedule.user_id,
            operation_type=AUTOMATED_SEARCH_OPERATION,
            idempotency_key=idempotency_key,
            status="queued",
            request_payload={
                "schedule_id": schedule.id,
                "criterion_id": schedule.criterion_id,
                "resume_profile_id": schedule.resume_profile_id,
                "minimum_match_score": schedule.minimum_match_score,
                "max_results": 10,
                "scheduled_for": scheduled_for.isoformat(),
            },
            provider="openai" if matching_v2_enabled else "apify+openai",
            prompt_version="qualification-match.v3" if matching_v2_enabled else "resume-job-match-v1",
            progress_message="Waiting for automation worker",
        )
        db.add(operation)
        db.flush()
        run = SearchRun(
            workspace_id=schedule.workspace_id,
            user_id=schedule.user_id,
            schedule_id=schedule.id,
            managed_operation_id=operation.id,
            status="queued",
            scheduled_for=scheduled_for,
            provider="openai" if matching_v2_enabled else "apify+openai",
        )
        db.add(run)
        db.flush()
        ledger.search_run_id = run.id
        schedule.last_claimed_at = current
        schedule.next_run_at = _next_occurrence(schedule, scheduled_for, current)
        schedule.paused_reason = None
        summary.queued_run_ids.append(run.id)

    db.flush()
    return summary


def dispatch_schedule_now(
    db: Session,
    catalog: EntitlementCatalog,
    schedule: SearchSchedule,
    *,
    now: datetime | None = None,
    matching_v2_enabled: bool = False,
) -> SearchRun:
    """Queue an immediate one-off run without moving the recurring schedule."""
    current = _utc(now or datetime.now(timezone.utc))
    subscription = db.scalar(
        select(UserSubscription).where(
            UserSubscription.user_id == schedule.user_id,
            UserSubscription.deleted_at.is_(None),
        )
    )
    if subscription is None or subscription.status != "active":
        raise SubscriptionUnavailable("user has no active subscription")
    if subscription.tier_code != SUPER_TIER_CODE:
        raise PermissionError("Run now is available only to internal super accounts.")
    if schedule.deleted_at is not None:
        raise LookupError("search schedule not found")

    # A timestamp with microsecond precision makes each explicit test run a
    # separate occurrence while retaining ledger idempotency for exact retries.
    scheduled_for = current
    idempotency_key = _occurrence_key(schedule.id, scheduled_for)
    ledger, _created = reserve_provider_search(
        db,
        user_id=schedule.user_id,
        idempotency_key=idempotency_key,
        reason=f"Immediate super-account search {schedule.id}",
        catalog=catalog,
        now=current,
    )
    operation = ManagedOperation(
        workspace_id=schedule.workspace_id,
        user_id=schedule.user_id,
        operation_type=AUTOMATED_SEARCH_OPERATION,
        idempotency_key=idempotency_key,
        status="queued",
        request_payload={
            "schedule_id": schedule.id,
            "criterion_id": schedule.criterion_id,
            "resume_profile_id": schedule.resume_profile_id,
            "minimum_match_score": schedule.minimum_match_score,
            "max_results": 10,
            "scheduled_for": scheduled_for.isoformat(),
            "trigger": "super_run_now",
        },
        provider="openai" if matching_v2_enabled else "apify+openai",
        prompt_version="qualification-match.v3" if matching_v2_enabled else "resume-job-match-v1",
        progress_message="Waiting for automation worker",
    )
    db.add(operation)
    db.flush()
    run = SearchRun(
        workspace_id=schedule.workspace_id,
        user_id=schedule.user_id,
        schedule_id=schedule.id,
        managed_operation_id=operation.id,
        status="queued",
        scheduled_for=scheduled_for,
        provider="openai" if matching_v2_enabled else "apify+openai",
    )
    db.add(run)
    db.flush()
    ledger.search_run_id = run.id
    schedule.last_claimed_at = current
    schedule.paused_reason = None
    db.flush()
    return run


def _occurrence_key(schedule_id: int, scheduled_for: datetime) -> str:
    material = f"automated_job_search:{schedule_id}:{scheduled_for.isoformat()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _next_occurrence(
    schedule: SearchSchedule,
    scheduled_for: datetime,
    current: datetime,
) -> datetime:
    interval = timedelta(minutes=schedule.interval_minutes)
    next_run = scheduled_for + interval
    if next_run <= current:
        next_run = current + interval
    return next_run


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Queue due DaliJob automated searches.")
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    parser.add_argument("--limit", type=int, default=100, help="Maximum due schedules to inspect")
    args = parser.parse_args(argv)

    # Imports stay local so application model imports do not recursively load
    # runtime configuration.
    from DaliCommonLib.dali_db_man import DbMan

    from app.config import load_runtime_config

    runtime = load_runtime_config(args.config)
    with DbMan.session_scope() as db:
        summary = dispatch_due_schedules(
            db,
            runtime.tier_entitlements,
            limit=args.limit,
            matching_v2_enabled=runtime.matching_v2.automation_enabled,
        )
    print(
        json.dumps(
            {
                "inspected": summary.inspected,
                "queued": summary.queued,
                "queued_run_ids": summary.queued_run_ids,
                "skipped_existing": summary.skipped_existing,
                "skipped_quota": summary.skipped_quota,
                "paused_subscription": summary.paused_subscription,
                "paused_tier_rule": summary.paused_tier_rule,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
