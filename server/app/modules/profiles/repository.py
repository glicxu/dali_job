from __future__ import annotations

from sqlalchemy import select
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
from app.modules.profiles.models import Profile, default_resume_data
from app.modules.profiles.schemas import ResumeData


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


def get_or_create_profile(db: Session, identity: AuthenticatedIdentity | None = None) -> Profile:
    user, workspace = ensure_account_for_identity(db, identity or get_dev_identity())
    profile = db.scalar(
        select(Profile).where(
            Profile.workspace_id == workspace.id,
            Profile.user_id == user.id,
        )
    )
    if profile is None:
        profile = Profile(
            workspace_id=workspace.id,
            user_id=user.id,
            resume_data=default_resume_data(),
        )
        db.add(profile)
        db.flush()
    else:
        profile.resume_data = normalize_resume_data(profile.resume_data)
    return profile


def update_profile_resume_data(
    db: Session,
    resume_data: ResumeData,
    identity: AuthenticatedIdentity | None = None,
) -> Profile:
    profile = get_or_create_profile(db, identity)
    profile.resume_data = resume_data.model_dump()
    db.flush()
    db.refresh(profile)
    return profile


def apply_resume_suggestions(
    db: Session,
    suggestions: ResumeData,
    identity: AuthenticatedIdentity | None = None,
) -> Profile:
    return update_profile_resume_data(db, suggestions, identity)
