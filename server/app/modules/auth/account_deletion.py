from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.accounts.models import User, Workspace
from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationTask,
)
from app.modules.auth.models import AuthActionToken
from app.modules.auth.security import hash_password
from app.modules.auth.service import revoke_all_sessions
from app.modules.documents.models import Document, DocumentDownloadTicket, DocumentVersion
from app.modules.interviews.models import Interview, InterviewNote, InterviewPrepGuide
from app.modules.job_search.models import JobSearchCriterion
from app.modules.jobs.models import JobResumeMatch, UserEditedJob, UserSavedJob
from app.modules.materials.models import GeneratedApplicationMaterial, GeneratedApplicationMaterialVersion
from app.modules.operations.models import ManagedOperation
from app.modules.profiles.models import ResumeProfile
from app.modules.reports.models import UserReport


def soft_delete_account(db: Session, user: User, *, deleted_at: datetime | None = None) -> datetime:
    """Anonymize an account and soft-delete every user-owned aggregate in one transaction."""
    now = deleted_at or datetime.now(timezone.utc)
    user_id = user.id

    document_ids = select(Document.id).where(Document.user_id == user_id)
    application_ids = select(Application.id).where(Application.user_id == user_id)
    interview_ids = select(Interview.id).where(Interview.user_id == user_id)
    material_ids = select(GeneratedApplicationMaterial.id).where(
        GeneratedApplicationMaterial.user_id == user_id
    )

    _mark_deleted(db, Workspace, Workspace.owner_user_id == user_id, now)

    _mark_deleted(db, Document, Document.user_id == user_id, now)
    _mark_deleted(db, DocumentVersion, DocumentVersion.document_id.in_(document_ids), now)
    db.execute(
        update(DocumentDownloadTicket)
        .where(DocumentDownloadTicket.user_id == user_id)
        .values(consumed_at=now, deleted_at=now)
    )
    _mark_deleted(db, ResumeProfile, ResumeProfile.user_id == user_id, now)

    _mark_deleted(db, UserEditedJob, UserEditedJob.user_id == user_id, now)
    _mark_deleted(db, UserSavedJob, UserSavedJob.user_id == user_id, now)
    _mark_deleted(db, JobResumeMatch, JobResumeMatch.user_id == user_id, now)
    _mark_deleted(db, JobSearchCriterion, JobSearchCriterion.user_id == user_id, now)

    _mark_deleted(
        db,
        ApplicationStatusHistory,
        ApplicationStatusHistory.application_id.in_(application_ids),
        now,
    )
    _mark_deleted(db, ApplicationEvent, ApplicationEvent.application_id.in_(application_ids), now)
    _mark_deleted(db, ApplicationNote, ApplicationNote.application_id.in_(application_ids), now)
    db.execute(
        update(ApplicationDocument)
        .where(ApplicationDocument.application_id.in_(application_ids))
        .values(detached_at=now, deleted_at=now)
    )
    db.execute(
        update(ApplicationTask)
        .where(ApplicationTask.application_id.in_(application_ids))
        .values(reminder_dismissed_at=now, deleted_at=now)
    )
    db.execute(
        update(Application)
        .where(Application.user_id == user_id)
        .values(active_duplicate_guard=None, archived_at=now, deleted_at=now)
    )

    _mark_deleted(db, InterviewNote, InterviewNote.interview_id.in_(interview_ids), now)
    _mark_deleted(db, InterviewPrepGuide, InterviewPrepGuide.user_id == user_id, now)
    _mark_deleted(db, Interview, Interview.user_id == user_id, now)

    _mark_deleted(
        db,
        GeneratedApplicationMaterialVersion,
        GeneratedApplicationMaterialVersion.material_id.in_(material_ids),
        now,
    )
    _mark_deleted(
        db,
        GeneratedApplicationMaterial,
        GeneratedApplicationMaterial.user_id == user_id,
        now,
    )

    db.execute(
        update(ManagedOperation)
        .where(
            ManagedOperation.user_id == user_id,
            ManagedOperation.status.in_(("queued", "running")),
        )
        .values(
            status="cancelled",
            cancel_requested_at=now,
            completed_at=now,
            progress_message="Cancelled because the account was deleted.",
        )
    )
    _mark_deleted(db, ManagedOperation, ManagedOperation.user_id == user_id, now)
    _mark_deleted(db, UserReport, UserReport.user_id == user_id, now)

    db.execute(
        update(AuthActionToken)
        .where(AuthActionToken.user_id == user_id, AuthActionToken.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    revoke_all_sessions(db, user_id)

    user.email = _deleted_email(user_id)
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.email_verified_at = None
    user.password_changed_at = now
    user.is_active = False
    user.deleted_at = now
    db.flush()
    return now


def _mark_deleted(db: Session, model: type, ownership_filter, deleted_at: datetime) -> None:
    db.execute(update(model).where(ownership_filter).values(deleted_at=deleted_at))


def _deleted_email(user_id: int) -> str:
    return f"deleted-{user_id}-{secrets.token_hex(16)}@deleted.invalid"
