from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.jobs.models import JobCache


@dataclass(frozen=True)
class ExpirationBatchResult:
    expired: int
    remaining_due: bool


def expire_due_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 500,
) -> ExpirationBatchResult:
    if limit < 1 or limit > 10_000:
        raise ValueError("limit must be between 1 and 10000")
    current = now or datetime.now(timezone.utc)
    jobs = list(
        db.scalars(
            select(JobCache)
            .where(
                JobCache.deleted_at.is_(None),
                JobCache.lifecycle_state == "active",
                JobCache.expires_at.is_not(None),
                JobCache.expires_at <= current,
            )
            .order_by(JobCache.expires_at, JobCache.id)
            .with_for_update(skip_locked=True)
            .limit(limit + 1)
        ).all()
    )
    remaining_due = len(jobs) > limit
    for job in jobs[:limit]:
        job.lifecycle_state = "expired"
        job.expired_at = current
        job.expiration_reason = "time_bound_ttl"
    db.flush()
    return ExpirationBatchResult(expired=min(len(jobs), limit), remaining_due=remaining_due)


def close_job(db: Session, job: JobCache, *, now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    job.lifecycle_state = "closed"
    job.expired_at = current
    job.expiration_reason = "source_confirmed_closed"
    db.flush()
