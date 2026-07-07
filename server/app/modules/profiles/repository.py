from __future__ import annotations

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.modules.accounts.dev_identity import (
    DEV_USER_DISPLAY_NAME,
    DEV_USER_EMAIL,
    DEV_USER_ID,
    DEV_WORKSPACE_ID,
    DEV_WORKSPACE_NAME,
)
from app.modules.accounts.models import User, Workspace
from app.modules.auth.dependencies import AuthenticatedIdentity, get_dev_identity
from app.modules.profiles.models import ResumeProfile, default_resume_data
from app.modules.profiles.schemas import ResumeData, ResumeProfileCreateRequest, ResumeProfileUpdateRequest


def ensure_dev_account(db: Session) -> tuple[User, Workspace]:
    user = db.get(User, DEV_USER_ID)
    if user is None:
        user = User(
            id=DEV_USER_ID,
            email=DEV_USER_EMAIL,
            display_name=DEV_USER_DISPLAY_NAME,
            timezone="America/New_York",
        )
        db.add(user)

    workspace = db.get(Workspace, DEV_WORKSPACE_ID)
    if workspace is None:
        workspace = Workspace(
            id=DEV_WORKSPACE_ID,
            owner_user_id=DEV_USER_ID,
            name=DEV_WORKSPACE_NAME,
        )
        db.add(workspace)

    db.flush()
    return user, workspace


def ensure_account_for_identity(db: Session, identity: AuthenticatedIdentity) -> tuple[User, Workspace]:
    if identity.provider == "dev":
        return ensure_dev_account(db)

    email = identity.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email).limit(1))
    if user is None:
        user = User(
            email=email,
            display_name=identity.display_name or email,
            timezone=identity.timezone,
        )
        db.add(user)
        db.flush()
    else:
        user.display_name = identity.display_name or user.display_name
        user.timezone = identity.timezone or user.timezone

    workspace = db.scalar(select(Workspace).where(Workspace.owner_user_id == user.id).limit(1))
    if workspace is None:
        name_base = identity.display_name or email
        workspace = Workspace(owner_user_id=user.id, name=f"{name_base}'s Career Search")
        db.add(workspace)

    db.flush()
    return user, workspace


def normalize_resume_data(value: dict | None) -> dict:
    merged = default_resume_data()
    if value:
        for key in merged:
            if key in value and value[key] is not None:
                merged[key] = value[key]
    return ResumeData.model_validate(merged).model_dump()


def _active_resume_profile_count(db: Session, workspace_id: int, user_id: int) -> int:
    return len(
        db.scalars(
            select(ResumeProfile.id).where(
                ResumeProfile.workspace_id == workspace_id,
                ResumeProfile.user_id == user_id,
                ResumeProfile.deleted_at.is_(None),
            )
        ).all()
    )


def _clear_other_default_profiles(
    db: Session,
    workspace_id: int,
    user_id: int,
    keep_profile_id: int | None = None,
) -> None:
    conditions = [
        ResumeProfile.workspace_id == workspace_id,
        ResumeProfile.user_id == user_id,
        ResumeProfile.deleted_at.is_(None),
    ]
    if keep_profile_id is not None:
        conditions.append(ResumeProfile.id != keep_profile_id)
    db.execute(update(ResumeProfile).where(*conditions).values(is_default=False))


def _ensure_one_default_profile(db: Session, workspace_id: int, user_id: int) -> None:
    default_profile = db.scalar(
        select(ResumeProfile)
        .where(
            ResumeProfile.workspace_id == workspace_id,
            ResumeProfile.user_id == user_id,
            ResumeProfile.is_default.is_(True),
            ResumeProfile.deleted_at.is_(None),
        )
        .order_by(desc(ResumeProfile.updated_at), desc(ResumeProfile.id))
        .limit(1)
    )
    if default_profile is not None:
        _clear_other_default_profiles(db, workspace_id, user_id, default_profile.id)
        return

    fallback_profile = db.scalar(
        select(ResumeProfile)
        .where(
            ResumeProfile.workspace_id == workspace_id,
            ResumeProfile.user_id == user_id,
            ResumeProfile.deleted_at.is_(None),
        )
        .order_by(desc(ResumeProfile.updated_at), desc(ResumeProfile.id))
        .limit(1)
    )
    if fallback_profile is not None:
        fallback_profile.is_default = True


def list_resume_profiles(
    db: Session,
    identity: AuthenticatedIdentity | None = None,
) -> list[ResumeProfile]:
    user, workspace = ensure_account_for_identity(db, identity or get_dev_identity())
    resume_profiles = db.scalars(
        select(ResumeProfile)
        .where(
            ResumeProfile.workspace_id == workspace.id,
            ResumeProfile.user_id == user.id,
            ResumeProfile.deleted_at.is_(None),
        )
        .order_by(desc(ResumeProfile.is_default), desc(ResumeProfile.updated_at), desc(ResumeProfile.id))
    ).all()
    for resume_profile in resume_profiles:
        resume_profile.resume_data = normalize_resume_data(resume_profile.resume_data)
    return resume_profiles


def get_resume_profile_for_identity(
    db: Session,
    identity: AuthenticatedIdentity,
    resume_profile_id: int,
) -> ResumeProfile | None:
    user, workspace = ensure_account_for_identity(db, identity)
    resume_profile = db.scalar(
        select(ResumeProfile).where(
            ResumeProfile.id == resume_profile_id,
            ResumeProfile.workspace_id == workspace.id,
            ResumeProfile.user_id == user.id,
            ResumeProfile.deleted_at.is_(None),
        )
    )
    if resume_profile is not None:
        resume_profile.resume_data = normalize_resume_data(resume_profile.resume_data)
    return resume_profile


def create_resume_profile(
    db: Session,
    payload: ResumeProfileCreateRequest,
    identity: AuthenticatedIdentity | None = None,
) -> ResumeProfile:
    user, workspace = ensure_account_for_identity(db, identity or get_dev_identity())
    should_be_default = payload.is_default or _active_resume_profile_count(db, workspace.id, user.id) == 0
    if should_be_default:
        _clear_other_default_profiles(db, workspace.id, user.id)
    resume_profile = ResumeProfile(
        workspace_id=workspace.id,
        user_id=user.id,
        title=payload.title.strip(),
        resume_data=payload.resume_data.model_dump(),
        source_document_id=payload.source_document_id,
        source_document_version_id=payload.source_document_version_id,
        is_default=should_be_default,
    )
    db.add(resume_profile)
    db.flush()
    db.refresh(resume_profile)
    return resume_profile


def update_resume_profile(
    db: Session,
    resume_profile: ResumeProfile,
    payload: ResumeProfileUpdateRequest,
) -> ResumeProfile:
    if payload.title is not None:
        resume_profile.title = payload.title.strip()
    if payload.resume_data is not None:
        resume_profile.resume_data = payload.resume_data.model_dump()
    if payload.is_default is True:
        _clear_other_default_profiles(db, resume_profile.workspace_id, resume_profile.user_id, resume_profile.id)
        resume_profile.is_default = True
    elif payload.is_default is False:
        resume_profile.is_default = False
        db.flush()
        _ensure_one_default_profile(db, resume_profile.workspace_id, resume_profile.user_id)
    db.flush()
    db.refresh(resume_profile)
    return resume_profile


def soft_delete_resume_profile(db: Session, resume_profile: ResumeProfile) -> None:
    from app.modules.profiles.models import utc_now

    resume_profile.deleted_at = utc_now()
    resume_profile.is_default = False
    db.flush()
    _ensure_one_default_profile(db, resume_profile.workspace_id, resume_profile.user_id)
    db.flush()


def apply_resume_suggestions(
    db: Session,
    suggestions: ResumeData,
    identity: AuthenticatedIdentity | None = None,
    source_document_id: int | None = None,
    source_document_version_id: int | None = None,
) -> ResumeProfile:
    return create_resume_profile(
        db,
        ResumeProfileCreateRequest(
            title=suggestions.headline or "Imported Resume",
            resume_data=suggestions,
            source_document_id=source_document_id,
            source_document_version_id=source_document_version_id,
            is_default=False,
        ),
        identity,
    )
