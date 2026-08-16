from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.accounts.models import User
from app.modules.automation.models import NotificationDelivery, NotificationPreference
from app.modules.jobs.models import JobCache, JobMatchFeedback, JobResumeMatch, UserSavedJob
from app.modules.matching_v2.scoring import recommendation_for_score
from app.modules.matching_v2.models import (
    EligibilityAssessment,
    MatchResult,
    PreferenceAssessment,
    QualificationAssessment,
)
from app.modules.profiles.repository import ensure_account_for_identity


def get_or_create_preferences(
    db: Session,
    identity: AuthenticatedIdentity,
) -> NotificationPreference:
    user, workspace = ensure_account_for_identity(db, identity)
    preference = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.deleted_at.is_(None),
        )
    )
    if preference is None:
        preference = NotificationPreference(
            workspace_id=workspace.id,
            user_id=user.id,
            timezone=user.timezone or "UTC",
        )
        db.add(preference)
        db.flush()
    return preference


def update_preferences(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    email_enabled: bool,
    digest_mode: str,
    minimum_match_score: int,
    timezone_name: str,
    quiet_hours_start,
    quiet_hours_end,
) -> NotificationPreference:
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown IANA timezone.") from exc
    preference = get_or_create_preferences(db, identity)
    preference.email_enabled = email_enabled
    preference.digest_mode = digest_mode
    preference.minimum_match_score = minimum_match_score
    preference.timezone = timezone_name
    preference.quiet_hours_start = quiet_hours_start
    preference.quiet_hours_end = quiet_hours_end
    db.flush()
    db.refresh(preference)
    return preference


def create_in_app_delivery(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    schedule_id: int,
    job_resume_match_id: int,
    canonical_job_id: int,
    now: datetime | None = None,
) -> tuple[NotificationDelivery, bool]:
    idempotency_key = f"schedule:{schedule_id}:job:{canonical_job_id}"
    existing = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.user_id == user_id,
            NotificationDelivery.channel == "in_app",
            NotificationDelivery.idempotency_key == idempotency_key,
            NotificationDelivery.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing, False
    sent_at = now or datetime.now(timezone.utc)
    delivery = NotificationDelivery(
        workspace_id=workspace_id,
        user_id=user_id,
        job_resume_match_id=job_resume_match_id,
        search_schedule_id=schedule_id,
        channel="in_app",
        status="sent",
        idempotency_key=idempotency_key,
        sent_at=sent_at,
    )
    db.add(delivery)
    db.flush()
    return delivery, True


def create_email_delivery_if_enabled(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    schedule_id: int,
    job_resume_match_id: int,
    canonical_job_id: int,
) -> tuple[NotificationDelivery | None, bool]:
    preference = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.deleted_at.is_(None),
        )
    )
    if preference is None:
        user = db.get(User, user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            return None, False
        preference = NotificationPreference(
            workspace_id=workspace_id,
            user_id=user_id,
            email_enabled=True,
            digest_mode="daily",
            minimum_match_score=0,
            timezone=user.timezone or "UTC",
        )
        db.add(preference)
        db.flush()
    if not preference.email_enabled or preference.digest_mode != "daily":
        return None, False
    idempotency_key = f"schedule:{schedule_id}:job:{canonical_job_id}"
    existing = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.user_id == user_id,
            NotificationDelivery.channel == "email",
            NotificationDelivery.idempotency_key == idempotency_key,
            NotificationDelivery.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing, False
    delivery = NotificationDelivery(
        workspace_id=workspace_id,
        user_id=user_id,
        job_resume_match_id=job_resume_match_id,
        search_schedule_id=schedule_id,
        channel="email",
        status="pending",
        idempotency_key=idempotency_key,
    )
    db.add(delivery)
    db.flush()
    return delivery, True


def list_inbox(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    limit: int,
    before_id: int | None,
) -> tuple[list[dict], int | None]:
    user, workspace = ensure_account_for_identity(db, identity)
    statement = _inbox_statement(user.id, workspace.id).order_by(NotificationDelivery.id.desc())
    if before_id is not None:
        statement = statement.where(NotificationDelivery.id < before_id)
    rows = list(db.execute(statement.limit(limit + 1)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_inbox_response(*row) for row in rows]
    next_cursor = rows[-1][0].id if has_more and rows else None
    return items, next_cursor


def get_inbox_match(
    db: Session,
    identity: AuthenticatedIdentity,
    match_id: int,
) -> dict | None:
    user, workspace = ensure_account_for_identity(db, identity)
    row = db.execute(
        _inbox_statement(user.id, workspace.id).where(JobResumeMatch.id == match_id).limit(1)
    ).first()
    return _inbox_response(*row) if row else None


def mark_inbox_match_read(
    db: Session,
    identity: AuthenticatedIdentity,
    match_id: int,
) -> dict | None:
    item = get_inbox_match(db, identity, match_id)
    if item is None:
        return None
    delivery = db.get(NotificationDelivery, item["delivery_id"])
    if delivery is None or delivery.deleted_at is not None:
        return None
    if delivery.read_at is None:
        delivery.read_at = datetime.now(timezone.utc)
        delivery.status = "read"
        db.flush()
    return get_inbox_match(db, identity, match_id)


def put_match_feedback(
    db: Session,
    identity: AuthenticatedIdentity,
    match_id: int,
    *,
    score: int,
    rationale: str,
) -> dict | None:
    if get_inbox_match(db, identity, match_id) is None:
        return None
    user, workspace = ensure_account_for_identity(db, identity)
    feedback = db.scalar(
        select(JobMatchFeedback).where(
            JobMatchFeedback.user_id == user.id,
            JobMatchFeedback.workspace_id == workspace.id,
            JobMatchFeedback.job_resume_match_id == match_id,
        )
    )
    if feedback is None:
        feedback = JobMatchFeedback(
            workspace_id=workspace.id,
            user_id=user.id,
            job_resume_match_id=match_id,
            score=score,
            rationale=rationale.strip(),
        )
        db.add(feedback)
    else:
        feedback.score = score
        feedback.rationale = rationale.strip()
        feedback.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(feedback)
    return _feedback_response(feedback)


def _inbox_statement(user_id: int, workspace_id: int):
    return (
        select(
            NotificationDelivery,
            JobResumeMatch,
            UserSavedJob,
            JobCache,
            JobMatchFeedback,
            MatchResult,
            QualificationAssessment,
            PreferenceAssessment,
            EligibilityAssessment,
        )
        .join(JobResumeMatch, JobResumeMatch.id == NotificationDelivery.job_resume_match_id)
        .join(UserSavedJob, UserSavedJob.id == JobResumeMatch.user_job_id)
        .outerjoin(JobCache, JobCache.id == UserSavedJob.jobs_cache_id)
        .outerjoin(MatchResult, MatchResult.id == JobResumeMatch.matching_v2_result_id)
        .outerjoin(
            QualificationAssessment,
            QualificationAssessment.id == MatchResult.qualification_assessment_id,
        )
        .outerjoin(
            PreferenceAssessment,
            PreferenceAssessment.id == MatchResult.preference_assessment_id,
        )
        .outerjoin(
            EligibilityAssessment,
            EligibilityAssessment.id == MatchResult.eligibility_assessment_id,
        )
        .outerjoin(
            JobMatchFeedback,
            (JobMatchFeedback.job_resume_match_id == JobResumeMatch.id)
            & (JobMatchFeedback.user_id == user_id)
            & (JobMatchFeedback.workspace_id == workspace_id),
        )
        .where(
            NotificationDelivery.user_id == user_id,
            NotificationDelivery.workspace_id == workspace_id,
            NotificationDelivery.channel == "in_app",
            NotificationDelivery.status.in_(("sent", "read")),
            NotificationDelivery.deleted_at.is_(None),
            JobResumeMatch.deleted_at.is_(None),
            UserSavedJob.deleted_at.is_(None),
        )
    )


def _inbox_response(
    delivery: NotificationDelivery,
    match: JobResumeMatch,
    user_job: UserSavedJob,
    cache: JobCache | None,
    stored_feedback: JobMatchFeedback | None,
    v2_result: MatchResult | None,
    qualification: QualificationAssessment | None,
    preference: PreferenceAssessment | None,
    eligibility: EligibilityAssessment | None,
) -> dict:
    job_data = match.job_data_snapshot or {}
    feedback = _feedback_response(stored_feedback) if stored_feedback is not None else None
    return {
        "match_id": match.id,
        "delivery_id": delivery.id,
        "user_job_id": user_job.id,
        "search_schedule_id": delivery.search_schedule_id,
        "title": (cache.title if cache else None) or job_data.get("title") or "Untitled Job",
        "company": (cache.company if cache else None) or job_data.get("company") or "Unknown company",
        "source_url": cache.source_url if cache else None,
        "match_score": match.match_score,
        "match_data": match.match_data,
        "resume_data": match.resume_data_snapshot or {},
        "job_data": job_data,
        "user_feedback": feedback,
        "matching_v2_result": _v2_result_response(
            v2_result,
            qualification=qualification,
            preference=preference,
            eligibility=eligibility,
        ),
        "status": delivery.status,
        "sent_at": delivery.sent_at,
        "read_at": delivery.read_at,
        "created_at": delivery.created_at,
    }


def _v2_result_response(
    result: MatchResult | None,
    *,
    qualification: QualificationAssessment | None,
    preference: PreferenceAssessment | None,
    eligibility: EligibilityAssessment | None,
) -> dict | None:
    if result is None or qualification is None:
        return None
    return {
        "match_id": result.public_id,
        "qualification_assessment_id": qualification.public_id,
        "preference_assessment_id": preference.public_id if preference is not None else None,
        "eligibility_assessment_id": eligibility.public_id if eligibility is not None else None,
        "scores": result.score_artifact,
        "explanation": result.explanation_artifact,
        "policy": result.policy_versions,
        "legacy_score": result.legacy_score,
        "created_at": result.created_at,
    }


def _feedback_response(feedback: JobMatchFeedback) -> dict:
    return {
        "score": feedback.score,
        "recommendation": recommendation_for_score(feedback.score),
        "rationale": feedback.rationale,
        "created_at": feedback.created_at,
        "updated_at": feedback.updated_at,
    }
