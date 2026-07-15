from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.applications import repository
from app.modules.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationArchiveRequest,
    ApplicationDetailResponse,
    ApplicationEventResponse,
    ApplicationNoteCreateRequest,
    ApplicationNoteResponse,
    ApplicationResponse,
    ApplicationStage,
    ApplicationStatus,
    ApplicationStatusChangeRequest,
    ApplicationTaskCreateRequest,
    ApplicationTaskResponse,
    ApplicationTaskUpdateRequest,
    ApplicationUpdateRequest,
)
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationResponse])
def list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    stage_filter: ApplicationStage | None = Query(default=None, alias="stage"),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    return repository.list_applications(
        db,
        identity,
        status=status_filter,
        stage=stage_filter,
        include_archived=include_archived,
    )


@router.post("", response_model=ApplicationDetailResponse)
def create_application(
    payload: ApplicationCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    try:
        return repository.create_application(db, identity, payload)
    except repository.ApplicationDuplicateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_active_application",
                "message": "An active application already exists for this saved job. Confirm to create another one.",
                "existing_application_id": exc.existing_application_id,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{application_id}", response_model=ApplicationDetailResponse)
def get_application(
    application_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id, include_archived=True)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return repository.application_detail(db, identity, application)


@router.patch("/{application_id}", response_model=ApplicationDetailResponse)
def update_application(
    application_id: int,
    payload: ApplicationUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return repository.update_application(db, identity, application, payload)


@router.post("/{application_id}/status", response_model=ApplicationDetailResponse)
def change_application_status(
    application_id: int,
    payload: ApplicationStatusChangeRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    try:
        return repository.change_status(db, identity, application, status=payload.status, reason=payload.reason)
    except repository.InvalidApplicationTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_application_transition",
                "message": str(exc),
                "current_status": exc.current_status,
                "requested_status": exc.requested_status,
            },
        ) from exc


@router.post("/{application_id}/archive", response_model=ApplicationDetailResponse)
def archive_application(
    application_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id, include_archived=True)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return repository.archive_application(db, identity, application)


@router.post("/{application_id}/restore", response_model=ApplicationDetailResponse)
def restore_application(
    application_id: int,
    payload: ApplicationArchiveRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id, include_archived=True)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    try:
        return repository.restore_application(
            db,
            identity,
            application,
            confirm_duplicate=payload.confirm_duplicate,
        )
    except repository.ApplicationDuplicateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_active_application",
                "message": "Another active application exists for this saved job. Confirm to restore this one too.",
                "existing_application_id": exc.existing_application_id,
            },
        ) from exc


@router.get("/{application_id}/events", response_model=list[ApplicationEventResponse])
def list_application_events(
    application_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    application = repository.get_application_for_identity(db, identity, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return repository.application_detail(db, identity, application)["events"]


@router.post("/{application_id}/notes", response_model=ApplicationNoteResponse)
def add_application_note(
    application_id: int,
    payload: ApplicationNoteCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return repository.add_note(db, identity, application, payload)


@router.post("/{application_id}/tasks", response_model=ApplicationTaskResponse)
def add_application_task(
    application_id: int,
    payload: ApplicationTaskCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return repository.add_task(db, identity, application, payload)


@router.patch("/{application_id}/tasks/{task_id}", response_model=ApplicationTaskResponse)
def update_application_task(
    application_id: int,
    task_id: int,
    payload: ApplicationTaskUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    task = repository.get_task_for_application(db, application, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return repository.update_task(db, identity, application, task, payload)
