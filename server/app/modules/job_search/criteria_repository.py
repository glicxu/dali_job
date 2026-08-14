from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.job_search.models import JobSearchCriterion, utc_now
from app.modules.profiles.repository import ensure_account_for_identity


def _response(criterion: JobSearchCriterion) -> dict:
    return {
        "id": criterion.id,
        "workspace_id": criterion.workspace_id,
        "user_id": criterion.user_id,
        "resume_profile_id": criterion.resume_profile_id,
        "keyword": criterion.keyword,
        "location": criterion.location,
        "source": criterion.source,
        "is_complete": bool(criterion.location and criterion.location.strip()),
        "last_used_at": criterion.last_used_at,
        "created_at": criterion.created_at,
        "updated_at": criterion.updated_at,
    }


def keyword_from_resume_data(resume_data: dict) -> str | None:
    target_roles = [str(item).strip() for item in resume_data.get("target_roles", []) if str(item).strip()]
    if target_roles:
        return target_roles[0][:255]
    headline = str(resume_data.get("headline") or "").strip()
    if headline:
        return headline[:255]
    skills = [str(item).strip() for item in resume_data.get("skills", []) if str(item).strip()]
    if skills:
        return " ".join(skills[:3])[:255]
    return None


def list_criteria(db: Session, identity: AuthenticatedIdentity) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    criteria = db.scalars(
        select(JobSearchCriterion)
        .where(
            JobSearchCriterion.workspace_id == workspace.id,
            JobSearchCriterion.user_id == user.id,
            JobSearchCriterion.source == "custom",
            JobSearchCriterion.deleted_at.is_(None),
        )
        .order_by(
            JobSearchCriterion.last_used_at.is_(None),
            desc(JobSearchCriterion.last_used_at),
            desc(JobSearchCriterion.updated_at),
            desc(JobSearchCriterion.id),
        )
    ).all()
    return [_response(item) for item in criteria]


def get_criterion(
    db: Session,
    identity: AuthenticatedIdentity,
    criterion_id: int,
) -> JobSearchCriterion | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(JobSearchCriterion).where(
            JobSearchCriterion.id == criterion_id,
            JobSearchCriterion.workspace_id == workspace.id,
            JobSearchCriterion.user_id == user.id,
            JobSearchCriterion.source == "custom",
            JobSearchCriterion.deleted_at.is_(None),
        )
    )


def create_criterion(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    keyword: str,
    location: str,
    resume_profile_id: int | None,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    criterion = JobSearchCriterion(
        workspace_id=workspace.id,
        user_id=user.id,
        resume_profile_id=resume_profile_id,
        keyword=keyword.strip(),
        location=location.strip(),
        source="custom",
    )
    db.add(criterion)
    db.flush()
    db.refresh(criterion)
    return _response(criterion)


def update_criterion(
    db: Session,
    criterion: JobSearchCriterion,
    *,
    keyword: str | None = None,
    location: str | None = None,
) -> dict:
    if keyword is not None:
        criterion.keyword = keyword.strip()
    if location is not None:
        criterion.location = location.strip() or None
    db.flush()
    db.refresh(criterion)
    return _response(criterion)


def mark_criterion_used(
    db: Session,
    criterion: JobSearchCriterion,
    *,
    location: str,
) -> None:
    if not criterion.location:
        criterion.location = location.strip()
    criterion.last_used_at = utc_now()
    db.flush()


def soft_delete_criterion(db: Session, criterion: JobSearchCriterion) -> None:
    criterion.deleted_at = utc_now()
    db.flush()
