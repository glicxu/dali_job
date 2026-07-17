from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationNote,
    ApplicationStatusHistory,
    ApplicationTask,
    utc_now,
)
from app.modules.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationJobSummary,
    ApplicationNoteCreateRequest,
    ApplicationTaskCreateRequest,
    ApplicationTaskUpdateRequest,
    ApplicationUpdateRequest,
)
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.documents import repository as document_repository
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs import repository as job_repository
from app.modules.profiles.repository import ensure_account_for_identity

ACTIVE_STATUSES = {"interested", "applied", "interviewing", "offer"}
TERMINAL_STATUSES = {"accepted", "rejected", "withdrawn"}
ALLOWED_STATUS_TRANSITIONS = {
    "interested": {"applied", "withdrawn"},
    "applied": {"interviewing", "rejected", "withdrawn"},
    "interviewing": {"offer", "rejected", "withdrawn"},
    "offer": {"accepted", "rejected", "withdrawn"},
    "accepted": set(),
    "rejected": set(),
    "withdrawn": set(),
}


class ApplicationDuplicateError(Exception):
    def __init__(self, existing_application_id: int | None) -> None:
        self.existing_application_id = existing_application_id
        super().__init__("An active application already exists for this saved job.")


class InvalidApplicationTransitionError(Exception):
    def __init__(self, current_status: str, requested_status: str) -> None:
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(f"Cannot change application status from {current_status} to {requested_status}.")


class ApplicationDocumentNotFoundError(Exception):
    pass


class DuplicateApplicationDocumentError(Exception):
    pass


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _source_snapshot(job: dict) -> tuple[str | None, str]:
    source_url = _clean_text(job.get("source_url"))
    if source_url is None:
        return None, "Manual entry"
    host = (urlparse(source_url).hostname or "").lower().removeprefix("www.")
    return source_url, host or "Unknown source"


def _job_summary(db: Session, identity: AuthenticatedIdentity, user_job_id: int | None) -> dict | None:
    if user_job_id is None:
        return None
    user_job = job_repository.get_user_job_for_identity(db, identity, user_job_id)
    if user_job is None:
        return None
    job = job_repository.job_response_for_identity(db, identity, user_job)
    job_data = job.get("job_data") or {}
    return ApplicationJobSummary(
        id=job["id"],
        title=job.get("title") or "",
        company=job.get("company") or "",
        source_url=job.get("source_url"),
        summary=job_data.get("summary") or "",
        work_location=job_data.get("work_location") or "",
        application_deadline=job_data.get("application_deadline") or "",
    ).model_dump()


def _application_response(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    *,
    include_detail: bool = False,
) -> dict:
    payload = {
        "id": application.id,
        "workspace_id": application.workspace_id,
        "user_id": application.user_id,
        "user_job_id": application.user_job_id,
        "status": application.status,
        "stage": application.stage,
        "priority": application.priority,
        "match_score": application.match_score,
        "salary_notes": application.salary_notes,
        "applied_at": application.applied_at,
        "next_action_at": application.next_action_at,
        "next_action_label": application.next_action_label,
        "notes": application.notes,
        "job": _job_summary(db, identity, application.user_job_id),
        "created_at": application.created_at,
        "updated_at": application.updated_at,
        "archived_at": application.archived_at,
        "allowed_status_transitions": (
            [] if application.archived_at is not None else sorted(ALLOWED_STATUS_TRANSITIONS[application.status])
        ),
    }
    if include_detail:
        payload.update(
            {
                "status_history": [
                    _status_history_response(row)
                    for row in db.scalars(
                        select(ApplicationStatusHistory)
                        .where(ApplicationStatusHistory.application_id == application.id)
                        .order_by(desc(ApplicationStatusHistory.created_at))
                    )
                ],
                "events": [
                    _event_response(row)
                    for row in db.scalars(
                        select(ApplicationEvent)
                        .where(ApplicationEvent.application_id == application.id)
                        .order_by(desc(ApplicationEvent.created_at))
                    )
                ],
                "notes_list": [
                    _note_response(row)
                    for row in db.scalars(
                        select(ApplicationNote)
                        .where(ApplicationNote.application_id == application.id)
                        .order_by(desc(ApplicationNote.created_at))
                    )
                ],
                "tasks": [
                    _task_response(row)
                    for row in db.scalars(
                        select(ApplicationTask)
                        .where(ApplicationTask.application_id == application.id)
                        .order_by(ApplicationTask.completed_at.is_(None).desc(), ApplicationTask.due_at, desc(ApplicationTask.created_at))
                    )
                ],
                "documents": [
                    _application_document_response(attachment, document, version)
                    for attachment, document, version in db.execute(
                        select(ApplicationDocument, Document, DocumentVersion)
                        .join(DocumentVersion, DocumentVersion.id == ApplicationDocument.document_version_id)
                        .join(Document, Document.id == DocumentVersion.document_id)
                        .where(
                            ApplicationDocument.application_id == application.id,
                            ApplicationDocument.detached_at.is_(None),
                        )
                        .order_by(desc(ApplicationDocument.created_at))
                    ).all()
                ],
            }
        )
    return payload


def _status_history_response(history: ApplicationStatusHistory) -> dict:
    return {
        "id": history.id,
        "application_id": history.application_id,
        "from_status": history.from_status,
        "to_status": history.to_status,
        "source": history.source,
        "reason": history.reason,
        "created_at": history.created_at,
    }


def _event_response(event: ApplicationEvent) -> dict:
    return {
        "id": event.id,
        "application_id": event.application_id,
        "event_type": event.event_type,
        "source": event.source,
        "payload": event.payload,
        "created_at": event.created_at,
    }


def _note_response(note: ApplicationNote) -> dict:
    return {
        "id": note.id,
        "application_id": note.application_id,
        "body": note.body,
        "created_at": note.created_at,
    }


def _task_response(task: ApplicationTask) -> dict:
    now = utc_now()
    due_at = _as_utc(task.due_at)
    reminder_at = _as_utc(task.reminder_at)
    return {
        "id": task.id,
        "application_id": task.application_id,
        "title": task.title,
        "task_type": task.task_type,
        "due_at": task.due_at,
        "reminder_at": task.reminder_at,
        "reminder_dismissed_at": task.reminder_dismissed_at,
        "completed_at": task.completed_at,
        "is_overdue": bool(task.completed_at is None and due_at is not None and due_at < now),
        "reminder_due": bool(
            task.completed_at is None
            and task.reminder_dismissed_at is None
            and reminder_at is not None
            and reminder_at <= now
        ),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _application_document_response(
    attachment: ApplicationDocument,
    document: Document,
    version: DocumentVersion,
) -> dict:
    return {
        "id": attachment.id,
        "application_id": attachment.application_id,
        "document_id": document.id,
        "document_version_id": version.id,
        "purpose": attachment.purpose,
        "document_title": document.title,
        "document_type": document.document_type,
        "version_number": version.version_number,
        "file_name": version.file_name,
        "content_type": version.content_type,
        "size_bytes": version.size_bytes,
        "sha256": version.sha256,
        "created_at": attachment.created_at,
    }


def _actor_payload(identity: AuthenticatedIdentity) -> dict:
    return {
        "actor_external_user_id": identity.external_user_id,
        "actor_provider": identity.provider,
    }


def _add_event(
    db: Session,
    application_id: int,
    event_type: str,
    payload: dict,
    *,
    identity: AuthenticatedIdentity,
    source: str = "user",
) -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application_id,
        event_type=event_type,
        source=source,
        payload={**payload, **_actor_payload(identity)},
    )
    db.add(event)
    return event


def _add_status_history(
    db: Session,
    application: Application,
    *,
    from_status: str | None,
    to_status: str,
    reason: str | None = None,
    source: str = "user",
    identity: AuthenticatedIdentity,
) -> ApplicationStatusHistory:
    history = ApplicationStatusHistory(
        application_id=application.id,
        from_status=from_status,
        to_status=to_status,
        source=source,
        reason=_clean_text(reason),
    )
    db.add(history)
    _add_event(
        db,
        application.id,
        "status_changed",
        {"from_status": from_status, "to_status": to_status, "reason": _clean_text(reason)},
        identity=identity,
        source=source,
    )
    return history


def list_applications(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    status: str | None = None,
    stage: str | None = None,
    include_archived: bool = False,
) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    query = select(Application).where(
        Application.workspace_id == workspace.id,
        Application.user_id == user.id,
    )
    if not include_archived:
        query = query.where(Application.archived_at.is_(None))
    if status:
        query = query.where(Application.status == status)
    if stage:
        query = query.where(Application.stage == stage)
    applications = db.scalars(query.order_by(desc(Application.updated_at))).all()
    return [_application_response(db, identity, application) for application in applications]


def get_application_for_identity(
    db: Session,
    identity: AuthenticatedIdentity,
    application_id: int,
    *,
    include_archived: bool = False,
) -> Application | None:
    user, workspace = ensure_account_for_identity(db, identity)
    query = select(Application).where(
            Application.id == application_id,
            Application.workspace_id == workspace.id,
            Application.user_id == user.id,
        )
    if not include_archived:
        query = query.where(Application.archived_at.is_(None))
    return db.scalar(query)


def _active_application_for_saved_job(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    user_job_id: int,
    exclude_application_id: int | None = None,
) -> Application | None:
    query = select(Application).where(
        Application.workspace_id == workspace_id,
        Application.user_id == user_id,
        Application.user_job_id == user_job_id,
        Application.archived_at.is_(None),
        Application.status.in_(ACTIVE_STATUSES),
    )
    if exclude_application_id is not None:
        query = query.where(Application.id != exclude_application_id)
    return db.scalar(query.order_by(Application.id).limit(1))


def application_detail(db: Session, identity: AuthenticatedIdentity, application: Application) -> dict:
    return _application_response(db, identity, application, include_detail=True)


def create_application(
    db: Session,
    identity: AuthenticatedIdentity,
    payload: ApplicationCreateRequest,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    user_job = job_repository.get_user_job_for_identity(db, identity, payload.user_job_id)
    if user_job is None:
        raise ValueError("Saved job not found.")
    existing = _active_application_for_saved_job(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        user_job_id=user_job.id,
    )
    if existing is not None and not payload.confirm_duplicate:
        raise ApplicationDuplicateError(existing.id)
    active_guard = 1 if payload.status in ACTIVE_STATUSES and not payload.confirm_duplicate else None
    effective_job = job_repository.job_response_for_identity(db, identity, user_job)
    source_url_snapshot, source_label_snapshot = _source_snapshot(effective_job)
    application = Application(
        workspace_id=workspace.id,
        user_id=user.id,
        user_job_id=user_job.id,
        source_url_snapshot=source_url_snapshot,
        source_label_snapshot=source_label_snapshot,
        status=payload.status,
        stage=payload.stage if payload.status not in TERMINAL_STATUSES else None,
        active_duplicate_guard=active_guard,
        priority=payload.priority,
        match_score=payload.match_score,
        salary_notes=_clean_text(payload.salary_notes),
        applied_at=payload.applied_at,
        next_action_at=payload.next_action_at,
        next_action_label=_clean_text(payload.next_action_label),
        notes=_clean_text(payload.notes),
    )
    try:
        with db.begin_nested():
            db.add(application)
            db.flush()
    except IntegrityError as exc:
        existing = _active_application_for_saved_job(
            db,
            workspace_id=workspace.id,
            user_id=user.id,
            user_job_id=user_job.id,
        )
        raise ApplicationDuplicateError(existing.id if existing else None) from exc
    _add_status_history(
        db,
        application,
        from_status=None,
        to_status=application.status,
        reason="Application created",
        source="system",
        identity=identity,
    )
    _add_event(
        db,
        application.id,
        "application_created",
        {
            "user_job_id": user_job.id,
            "stage": application.stage,
            "source_label_snapshot": application.source_label_snapshot,
        },
        identity=identity,
        source="system",
    )
    db.flush()
    db.refresh(application)
    return _application_response(db, identity, application, include_detail=True)


def update_application(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    payload: ApplicationUpdateRequest,
) -> dict:
    old_stage = application.stage
    if "stage" in payload.model_fields_set:
        application.stage = payload.stage
    if "priority" in payload.model_fields_set and payload.priority is not None:
        application.priority = payload.priority
    if "match_score" in payload.model_fields_set:
        application.match_score = payload.match_score
    if "salary_notes" in payload.model_fields_set:
        application.salary_notes = _clean_text(payload.salary_notes)
    if "applied_at" in payload.model_fields_set:
        application.applied_at = payload.applied_at
    if "next_action_at" in payload.model_fields_set:
        application.next_action_at = payload.next_action_at
    if "next_action_label" in payload.model_fields_set:
        application.next_action_label = _clean_text(payload.next_action_label)
    if "notes" in payload.model_fields_set:
        application.notes = _clean_text(payload.notes)
    application.updated_at = utc_now()
    if old_stage != application.stage:
        _add_event(
            db,
            application.id,
            "stage_changed",
            {"from_stage": old_stage, "to_stage": application.stage},
            identity=identity,
        )
    _add_event(
        db,
        application.id,
        "application_updated",
        payload.model_dump(exclude_unset=True, mode="json"),
        identity=identity,
    )
    db.flush()
    db.refresh(application)
    return _application_response(db, identity, application, include_detail=True)


def change_status(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    *,
    status: str,
    reason: str | None = None,
) -> dict:
    old_status = application.status
    if status not in ALLOWED_STATUS_TRANSITIONS[old_status]:
        raise InvalidApplicationTransitionError(old_status, status)
    application.status = status
    application.updated_at = utc_now()
    if status == "applied" and application.applied_at is None:
        application.applied_at = utc_now()
    if status in TERMINAL_STATUSES:
        application.stage = None
        application.active_duplicate_guard = None
    _add_status_history(
        db,
        application,
        from_status=old_status,
        to_status=status,
        reason=reason,
        identity=identity,
    )
    db.flush()
    db.refresh(application)
    return _application_response(db, identity, application, include_detail=True)


def add_note(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    payload: ApplicationNoteCreateRequest,
) -> dict:
    note = ApplicationNote(application_id=application.id, body=payload.body.strip())
    db.add(note)
    application.updated_at = utc_now()
    _add_event(db, application.id, "note_added", {"body": note.body}, identity=identity)
    db.flush()
    db.refresh(note)
    return _note_response(note)


def add_task(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    payload: ApplicationTaskCreateRequest,
) -> dict:
    task = ApplicationTask(
        application_id=application.id,
        title=payload.title.strip(),
        task_type=payload.task_type,
        due_at=payload.due_at,
        reminder_at=payload.reminder_at,
    )
    db.add(task)
    application.updated_at = utc_now()
    _add_event(
        db,
        application.id,
        "task_created",
        {
            "title": task.title,
            "task_type": task.task_type,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "reminder_at": task.reminder_at.isoformat() if task.reminder_at else None,
        },
        identity=identity,
    )
    db.flush()
    db.refresh(task)
    return _task_response(task)


def get_task_for_application(db: Session, application: Application, task_id: int) -> ApplicationTask | None:
    return db.scalar(
        select(ApplicationTask).where(
            ApplicationTask.id == task_id,
            ApplicationTask.application_id == application.id,
        )
    )


def list_tasks(
    db: Session,
    application: Application,
    *,
    task_type: str | None = None,
    task_status: str | None = None,
) -> list[dict]:
    query = select(ApplicationTask).where(ApplicationTask.application_id == application.id)
    if task_type:
        query = query.where(ApplicationTask.task_type == task_type)
    if task_status == "open":
        query = query.where(ApplicationTask.completed_at.is_(None))
    elif task_status == "completed":
        query = query.where(ApplicationTask.completed_at.is_not(None))
    tasks = db.scalars(query.order_by(ApplicationTask.completed_at.is_(None).desc(), ApplicationTask.due_at)).all()
    return [_task_response(task) for task in tasks]


def update_task(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    task: ApplicationTask,
    payload: ApplicationTaskUpdateRequest,
) -> dict:
    if "title" in payload.model_fields_set and payload.title is not None:
        task.title = payload.title.strip()
    if "task_type" in payload.model_fields_set and payload.task_type is not None:
        task.task_type = payload.task_type
    if "due_at" in payload.model_fields_set:
        task.due_at = payload.due_at
    if "reminder_at" in payload.model_fields_set:
        task.reminder_at = payload.reminder_at
        task.reminder_dismissed_at = None
    if "dismiss_reminder" in payload.model_fields_set and payload.dismiss_reminder is not None:
        task.reminder_dismissed_at = utc_now() if payload.dismiss_reminder else None
    if "completed" in payload.model_fields_set and payload.completed is not None:
        task.completed_at = utc_now() if payload.completed else None
    task.updated_at = utc_now()
    application.updated_at = utc_now()
    _add_event(
        db,
        application.id,
        "task_updated",
        {
            "task_id": task.id,
            "title": task.title,
            "task_type": task.task_type,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "reminder_at": task.reminder_at.isoformat() if task.reminder_at else None,
            "completed": task.completed_at is not None,
            "reminder_dismissed": task.reminder_dismissed_at is not None,
        },
        identity=identity,
    )
    db.flush()
    db.refresh(task)
    return _task_response(task)


def attach_document(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    *,
    document_version_id: int,
    purpose: str,
) -> dict:
    version = document_repository.get_version_for_identity(db, identity, document_version_id)
    if version is None:
        raise ApplicationDocumentNotFoundError("Document version not found.")
    existing = db.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.application_id == application.id,
            ApplicationDocument.document_version_id == version.id,
            ApplicationDocument.purpose == purpose,
            ApplicationDocument.detached_at.is_(None),
        )
    )
    if existing is not None:
        raise DuplicateApplicationDocumentError("This exact document version is already attached for that purpose.")
    attachment = ApplicationDocument(
        application_id=application.id,
        document_version_id=version.id,
        purpose=purpose,
    )
    db.add(attachment)
    application.updated_at = utc_now()
    _add_event(
        db,
        application.id,
        "document_attached",
        {"document_version_id": version.id, "purpose": purpose},
        identity=identity,
    )
    db.flush()
    document = db.get(Document, version.document_id)
    if document is None:
        raise ApplicationDocumentNotFoundError("Document not found.")
    return _application_document_response(attachment, document, version)


def get_attachment_for_application(
    db: Session,
    application: Application,
    attachment_id: int,
) -> ApplicationDocument | None:
    return db.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.id == attachment_id,
            ApplicationDocument.application_id == application.id,
            ApplicationDocument.detached_at.is_(None),
        )
    )


def detach_document(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    attachment: ApplicationDocument,
) -> None:
    attachment.detached_at = utc_now()
    application.updated_at = utc_now()
    _add_event(
        db,
        application.id,
        "document_detached",
        {"document_version_id": attachment.document_version_id, "purpose": attachment.purpose},
        identity=identity,
    )
    db.flush()


def create_attachment_download_ticket(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    attachment: ApplicationDocument,
):
    version = document_repository.get_version_for_identity(
        db,
        identity,
        attachment.document_version_id,
        include_deleted_document=True,
    )
    if version is None:
        raise ValueError("Document version not found.")
    raw_token, ticket = document_repository.create_download_ticket(
        db,
        identity,
        version,
        application_id=application.id,
    )
    _add_event(
        db,
        application.id,
        "document_download_authorized",
        {
            "application_document_id": attachment.id,
            "document_version_id": version.id,
            "download_ticket_id": ticket.id,
        },
        identity=identity,
    )
    db.flush()
    return raw_token, ticket


def archive_application(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
) -> dict:
    if application.archived_at is None:
        application.archived_at = utc_now()
        application.active_duplicate_guard = None
        application.updated_at = utc_now()
        _add_event(db, application.id, "application_archived", {}, identity=identity)
        db.flush()
        db.refresh(application)
    return _application_response(db, identity, application, include_detail=True)


def restore_application(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    *,
    confirm_duplicate: bool = False,
) -> dict:
    if application.archived_at is None:
        return _application_response(db, identity, application, include_detail=True)
    existing = None
    if application.status in ACTIVE_STATUSES and application.user_job_id is not None:
        existing = _active_application_for_saved_job(
            db,
            workspace_id=application.workspace_id,
            user_id=application.user_id,
            user_job_id=application.user_job_id,
            exclude_application_id=application.id,
        )
        if existing is not None and not confirm_duplicate:
            raise ApplicationDuplicateError(existing.id)
    application.archived_at = None
    application.active_duplicate_guard = (
        1 if application.status in ACTIVE_STATUSES and not confirm_duplicate else None
    )
    application.updated_at = utc_now()
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        raise ApplicationDuplicateError(existing.id if existing else None) from exc
    _add_event(db, application.id, "application_restored", {}, identity=identity)
    db.flush()
    db.refresh(application)
    return _application_response(db, identity, application, include_detail=True)
