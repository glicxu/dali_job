from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.config import RuntimeConfig
from app.modules.accounts.models import User
from app.modules.auth.email_delivery import send_account_email
from app.modules.automation.models import NotificationDelivery, NotificationPreference
from app.modules.jobs.models import JobCache, JobResumeMatch, UserSavedJob


LOGGER = logging.getLogger(__name__)
DEFAULT_DIGEST_HOUR = 8
DEFAULT_LEASE_SECONDS = 300
MAX_DIGEST_ITEMS = 50
MAX_ATTEMPTS = 5


class DigestSender(Protocol):
    def __call__(self, recipient: str, subject: str, body: str) -> None: ...


@dataclass(frozen=True)
class DigestItem:
    delivery_id: int
    match_id: int
    title: str
    company: str
    source_url: str | None
    match_score: int
    summary: str


@dataclass(frozen=True)
class DigestWorkItem:
    user_id: int
    recipient: str
    timezone_name: str
    local_date: str
    delivery_ids: tuple[int, ...]
    items: tuple[DigestItem, ...]


@dataclass(frozen=True)
class DigestOutcome:
    claimed: bool
    status: str | None = None
    delivery_count: int = 0


def send_one_digest(
    session_factory: Callable[[], Session],
    runtime: RuntimeConfig,
    *,
    worker_id: str,
    digest_hour: int = DEFAULT_DIGEST_HOUR,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
    sender: DigestSender | None = None,
) -> DigestOutcome:
    _validate_options(worker_id, digest_hour, lease_seconds)
    current = _utc(now or datetime.now(timezone.utc))
    with session_factory() as db:
        work = claim_digest(
            db,
            worker_id=worker_id,
            digest_hour=digest_hour,
            lease_seconds=lease_seconds,
            now=current,
        )
        db.commit()
    if work is None:
        return DigestOutcome(claimed=False)

    subject, body = render_digest(work, runtime.public_client_url)
    resolved_sender = sender or (
        lambda recipient, email_subject, email_body: send_account_email(
            runtime, recipient, email_subject, email_body
        )
    )
    try:
        resolved_sender(work.recipient, subject, body)
    except Exception as exc:
        LOGGER.error(
            "notification_digest_send_failed user_id=%s delivery_count=%s exception_type=%s",
            work.user_id,
            len(work.delivery_ids),
            type(exc).__name__,
        )
        status = finalize_digest_failure(
            session_factory,
            work,
            worker_id=worker_id,
            now=current,
        )
        return DigestOutcome(claimed=True, status=status, delivery_count=len(work.delivery_ids))

    finalize_digest_success(
        session_factory,
        work,
        worker_id=worker_id,
        now=current,
    )
    return DigestOutcome(claimed=True, status="sent", delivery_count=len(work.delivery_ids))


def claim_digest(
    db: Session,
    *,
    worker_id: str,
    digest_hour: int,
    lease_seconds: int,
    now: datetime,
) -> DigestWorkItem | None:
    current = _utc(now)
    db.execute(
        update(NotificationDelivery)
        .where(
            NotificationDelivery.channel == "email",
            NotificationDelivery.status == "sending",
            NotificationDelivery.lease_expires_at <= current,
            NotificationDelivery.deleted_at.is_(None),
        )
        .values(status="pending", lease_owner=None, lease_expires_at=None)
    )
    candidates = db.execute(
        select(NotificationDelivery, NotificationPreference, User)
        .join(
            NotificationPreference,
            NotificationPreference.user_id == NotificationDelivery.user_id,
        )
        .join(User, User.id == NotificationDelivery.user_id)
        .where(
            NotificationDelivery.channel == "email",
            NotificationDelivery.status == "pending",
            or_(
                NotificationDelivery.next_attempt_at.is_(None),
                NotificationDelivery.next_attempt_at <= current,
            ),
            NotificationDelivery.deleted_at.is_(None),
            NotificationPreference.email_enabled.is_(True),
            NotificationPreference.digest_mode == "daily",
            NotificationPreference.deleted_at.is_(None),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(NotificationDelivery.id)
        .with_for_update(skip_locked=True)
        .limit(100)
    ).all()
    selected = None
    cutoff = None
    local_date = None
    for delivery, preference, user in candidates:
        resolved = _digest_cutoff(preference, current, digest_hour)
        if resolved is None or _utc(delivery.created_at) > resolved[0]:
            continue
        selected = (delivery, preference, user)
        cutoff, local_date = resolved
        break
    if selected is None or cutoff is None or local_date is None:
        return None

    first, preference, user = selected
    rows = db.execute(
        select(NotificationDelivery, JobResumeMatch, UserSavedJob, JobCache)
        .join(JobResumeMatch, JobResumeMatch.id == NotificationDelivery.job_resume_match_id)
        .join(UserSavedJob, UserSavedJob.id == JobResumeMatch.user_job_id)
        .outerjoin(JobCache, JobCache.id == UserSavedJob.jobs_cache_id)
        .where(
            NotificationDelivery.user_id == first.user_id,
            NotificationDelivery.channel == "email",
            NotificationDelivery.status == "pending",
            NotificationDelivery.created_at <= cutoff,
            or_(
                NotificationDelivery.next_attempt_at.is_(None),
                NotificationDelivery.next_attempt_at <= current,
            ),
            NotificationDelivery.deleted_at.is_(None),
            JobResumeMatch.deleted_at.is_(None),
            UserSavedJob.deleted_at.is_(None),
        )
        .order_by(NotificationDelivery.id)
        .with_for_update(skip_locked=True)
        .limit(MAX_DIGEST_ITEMS)
    ).all()
    if not rows:
        return None
    lease_expires_at = current + timedelta(seconds=lease_seconds)
    items: list[DigestItem] = []
    delivery_ids: list[int] = []
    for delivery, match, _user_job, cache in rows:
        delivery.status = "sending"
        delivery.lease_owner = worker_id
        delivery.lease_expires_at = lease_expires_at
        delivery.attempt_count += 1
        delivery_ids.append(delivery.id)
        job_data = match.job_data_snapshot or {}
        items.append(
            DigestItem(
                delivery_id=delivery.id,
                match_id=match.id,
                title=(cache.title if cache else None) or job_data.get("title") or "Untitled Job",
                company=(cache.company if cache else None)
                or job_data.get("company")
                or "Unknown company",
                source_url=cache.source_url if cache else None,
                match_score=match.match_score,
                summary=str((match.match_data or {}).get("summary") or "")[:240],
            )
        )
    db.flush()
    return DigestWorkItem(
        user_id=user.id,
        recipient=user.email,
        timezone_name=preference.timezone,
        local_date=local_date,
        delivery_ids=tuple(delivery_ids),
        items=tuple(items),
    )


def finalize_digest_success(
    session_factory: Callable[[], Session],
    work: DigestWorkItem,
    *,
    worker_id: str,
    now: datetime,
) -> None:
    current = _utc(now)
    reference = _digest_reference(work)
    with session_factory() as db:
        deliveries = _owned_deliveries(db, work.delivery_ids, worker_id)
        for delivery in deliveries:
            delivery.status = "sent"
            delivery.sent_at = current
            delivery.provider_reference = reference
            delivery.error_code = None
            delivery.error_message = None
            delivery.next_attempt_at = None
            delivery.lease_owner = None
            delivery.lease_expires_at = None
        db.commit()


def finalize_digest_failure(
    session_factory: Callable[[], Session],
    work: DigestWorkItem,
    *,
    worker_id: str,
    now: datetime,
) -> str:
    current = _utc(now)
    terminal = False
    with session_factory() as db:
        deliveries = _owned_deliveries(db, work.delivery_ids, worker_id)
        for delivery in deliveries:
            if delivery.attempt_count >= MAX_ATTEMPTS:
                delivery.status = "failed"
                delivery.next_attempt_at = None
                terminal = True
            else:
                delivery.status = "pending"
                delay_minutes = min(5 * (2 ** max(delivery.attempt_count - 1, 0)), 360)
                delivery.next_attempt_at = current + timedelta(minutes=delay_minutes)
            delivery.error_code = "email_delivery_failed"
            delivery.error_message = "The daily digest could not be delivered."
            delivery.lease_owner = None
            delivery.lease_expires_at = None
        db.commit()
    return "failed" if terminal else "pending"


def render_digest(work: DigestWorkItem, public_client_url: str) -> tuple[str, str]:
    count = len(work.items)
    lines = [
        f"You have {count} new DaliJob match{'es' if count != 1 else ''}.",
        "",
    ]
    base_url = public_client_url.rstrip("/")
    for index, item in enumerate(work.items, start=1):
        lines.extend(
            [
                f"{index}. {item.title} — {item.company}",
                f"Match score: {item.match_score}/10",
            ]
        )
        if item.summary:
            lines.append(item.summary)
        lines.append(f"View match: {base_url}/match-inbox/{item.match_id}")
        if item.source_url:
            lines.append(f"Job posting: {item.source_url}")
        lines.append("")
    lines.append("This digest does not include your resume contents.")
    return f"Your DaliJob daily digest ({count})", "\n".join(lines)


def _digest_cutoff(
    preference: NotificationPreference,
    current: datetime,
    digest_hour: int,
) -> tuple[datetime, str] | None:
    zone = ZoneInfo(preference.timezone)
    local_now = current.astimezone(zone)
    if _in_quiet_hours(local_now.timetz().replace(tzinfo=None), preference):
        return None
    scheduled = local_now.replace(hour=digest_hour, minute=0, second=0, microsecond=0)
    if local_now < scheduled:
        return None
    return scheduled.astimezone(timezone.utc), local_now.date().isoformat()


def _in_quiet_hours(local_time: time, preference: NotificationPreference) -> bool:
    start = preference.quiet_hours_start
    end = preference.quiet_hours_end
    if start is None or end is None or start == end:
        return False
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def _owned_deliveries(
    db: Session,
    delivery_ids: tuple[int, ...],
    worker_id: str,
) -> list[NotificationDelivery]:
    deliveries = list(
        db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.id.in_(delivery_ids),
                NotificationDelivery.status == "sending",
                NotificationDelivery.lease_owner == worker_id,
            )
            .with_for_update()
        )
    )
    if len(deliveries) != len(delivery_ids):
        raise RuntimeError("daily digest delivery lease was lost")
    return deliveries


def _digest_reference(work: DigestWorkItem) -> str:
    key = f"{work.user_id}:{work.local_date}:{','.join(map(str, work.delivery_ids))}"
    return f"digest-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"


def _validate_options(worker_id: str, digest_hour: int, lease_seconds: int) -> None:
    if not worker_id.strip() or len(worker_id) > 120:
        raise ValueError("worker_id must contain 1 to 120 characters")
    if digest_hour < 0 or digest_hour > 23:
        raise ValueError("digest_hour must be between 0 and 23")
    if lease_seconds < 30 or lease_seconds > 3600:
        raise ValueError("lease_seconds must be between 30 and 3600")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
