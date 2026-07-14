from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.applications import repository
from app.modules.applications.schemas import (
    ApplicationCreateRequest,
    ApplicationDetailResponse,
    ApplicationEventResponse,
    ApplicationNoteCreateRequest,
    ApplicationNoteResponse,
    ApplicationResponse,
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
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    return repository.list_applications(db, identity, status=status_filter)


@router.post("", response_model=ApplicationDetailResponse)
def create_application(
    payload: ApplicationCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    try:
        return repository.create_application(db, identity, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{application_id}", response_model=ApplicationDetailResponse)
def get_application(
    application_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    application = repository.get_application_for_identity(db, identity, application_id)
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
    return repository.change_status(db, identity, application, status=payload.status, reason=payload.reason)


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
    return repository.update_task(db, application, task, payload)
