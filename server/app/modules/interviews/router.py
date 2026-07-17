from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.interviews import repository
from app.modules.interviews.schemas import (
    InterviewCreateRequest,
    InterviewDetailResponse,
    InterviewNoteCreateRequest,
    InterviewNoteResponse,
    InterviewResponse,
    InterviewUpdateRequest,
)

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _owned_interview(db: Session, identity: AuthenticatedIdentity, interview_id: int):
    interview = repository.get_interview_for_identity(db, identity, interview_id)
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found.")
    return interview


@router.get("", response_model=list[InterviewResponse])
def list_interviews(
    application_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    return repository.list_interviews(db, identity, application_id=application_id)


@router.post("", response_model=InterviewDetailResponse, status_code=status.HTTP_201_CREATED)
def create_interview(
    payload: InterviewCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    try:
        result = repository.create_interview(db, identity, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.commit()
    return result


@router.get("/{interview_id}", response_model=InterviewDetailResponse)
def get_interview(
    interview_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    return repository.interview_detail(db, identity, _owned_interview(db, identity, interview_id))


@router.patch("/{interview_id}", response_model=InterviewDetailResponse)
def update_interview(
    interview_id: int,
    payload: InterviewUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    interview = _owned_interview(db, identity, interview_id)
    result = repository.update_interview(db, identity, interview, payload)
    db.commit()
    return result


@router.post(
    "/{interview_id}/notes",
    response_model=InterviewNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_interview_note(
    interview_id: int,
    payload: InterviewNoteCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    interview = _owned_interview(db, identity, interview_id)
    note = repository.add_interview_note(db, interview, payload)
    db.commit()
    db.refresh(note)
    return note
