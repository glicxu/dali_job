from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.applications.models import (
    Application,
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
from app.modules.jobs import repository as job_repository
from app.modules.profiles.repository import ensure_account_for_identity


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


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
    return {
        "id": task.id,
        "application_id": task.application_id,
        "title": task.title,
        "due_at": task.due_at,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
    }


def _add_event(db: Session, application_id: int, event_type: str, payload: dict, source: str = "user") -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application_id,
        event_type=event_type,
        source=source,
        payload=payload,
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
        source=source,
    )
    return history


def list_applications(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    status: str | None = None,
) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    query = select(Application).where(
        Application.workspace_id == workspace.id,
        Application.user_id == user.id,
        Application.archived_at.is_(None),
    )
    if status:
        query = query.where(Application.status == status)
    applications = db.scalars(query.order_by(desc(Application.updated_at))).all()
    return [_application_response(db, identity, application) for application in applications]


def get_application_for_identity(
    db: Session,
    identity: AuthenticatedIdentity,
    application_id: int,
) -> Application | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(Application).where(
            Application.id == application_id,
            Application.workspace_id == workspace.id,
            Application.user_id == user.id,
            Application.archived_at.is_(None),
        )
    )


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
    application = Application(
        workspace_id=workspace.id,
        user_id=user.id,
        user_job_id=user_job.id,
        status=payload.status,
        priority=payload.priority,
        match_score=payload.match_score,
        salary_notes=_clean_text(payload.salary_notes),
        applied_at=payload.applied_at,
        next_action_at=payload.next_action_at,
        next_action_label=_clean_text(payload.next_action_label),
        notes=_clean_text(payload.notes),
    )
    db.add(application)
    db.flush()
    _add_status_history(db, application, from_status=None, to_status=application.status, reason="Application created", source="system")
    _add_event(db, application.id, "application_created", {"user_job_id": user_job.id}, source="system")
    db.flush()
    db.refresh(application)
    return _application_response(db, identity, application, include_detail=True)


def update_application(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    payload: ApplicationUpdateRequest,
) -> dict:
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
    _add_event(db, application.id, "application_updated", payload.model_dump(exclude_unset=True, mode="json"))
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
    application.status = status
    application.updated_at = utc_now()
    if status == "applied" and application.applied_at is None:
        application.applied_at = utc_now()
    if status == "archived":
        application.archived_at = utc_now()
    _add_status_history(db, application, from_status=old_status, to_status=status, reason=reason)
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
    _add_event(db, application.id, "note_added", {"body": note.body})
    db.flush()
    db.refresh(note)
    return _note_response(note)


def add_task(
    db: Session,
    identity: AuthenticatedIdentity,
    application: Application,
    payload: ApplicationTaskCreateRequest,
) -> dict:
    task = ApplicationTask(application_id=application.id, title=payload.title.strip(), due_at=payload.due_at)
    db.add(task)
    application.updated_at = utc_now()
    _add_event(db, application.id, "task_created", {"title": task.title, "due_at": task.due_at.isoformat() if task.due_at else None})
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


def update_task(
    db: Session,
    application: Application,
    task: ApplicationTask,
    payload: ApplicationTaskUpdateRequest,
) -> dict:
    if "title" in payload.model_fields_set and payload.title is not None:
        task.title = payload.title.strip()
    if "due_at" in payload.model_fields_set:
        task.due_at = payload.due_at
    if "completed" in payload.model_fields_set and payload.completed is not None:
        task.completed_at = utc_now() if payload.completed else None
    application.updated_at = utc_now()
    _add_event(
        db,
        application.id,
        "task_updated",
        {
            "task_id": task.id,
            "title": task.title,
            "completed": task.completed_at is not None,
        },
    )
    db.flush()
    db.refresh(task)
    return _task_response(task)
