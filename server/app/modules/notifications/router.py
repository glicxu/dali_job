from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    MatchInboxItemResponse,
    MatchInboxListResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdateRequest,
)


router = APIRouter(tags=["notifications"])


@router.get("/notification-preferences", response_model=NotificationPreferenceResponse)
def get_notification_preferences(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> NotificationPreferenceResponse:
    return NotificationPreferenceResponse.model_validate(service.get_or_create_preferences(db, identity))


@router.put("/notification-preferences", response_model=NotificationPreferenceResponse)
def put_notification_preferences(
    payload: NotificationPreferenceUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> NotificationPreferenceResponse:
    try:
        preference = service.update_preferences(
            db,
            identity,
            email_enabled=payload.email_enabled,
            digest_mode=payload.digest_mode,
            minimum_match_score=payload.minimum_match_score,
            timezone_name=payload.timezone,
            quiet_hours_start=payload.quiet_hours_start,
            quiet_hours_end=payload.quiet_hours_end,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return NotificationPreferenceResponse.model_validate(preference)


@router.get("/match-inbox", response_model=MatchInboxListResponse)
def list_match_inbox(
    limit: int = Query(default=20, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchInboxListResponse:
    items, next_cursor = service.list_inbox(db, identity, limit=limit, before_id=before_id)
    return MatchInboxListResponse(items=items, next_cursor=next_cursor)


@router.get("/match-inbox/{match_id}", response_model=MatchInboxItemResponse)
def get_match_inbox_item(
    match_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchInboxItemResponse:
    item = service.get_inbox_match(db, identity, match_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match inbox item not found.")
    return MatchInboxItemResponse.model_validate(item)


@router.post("/match-inbox/{match_id}/read", response_model=MatchInboxItemResponse)
def mark_match_inbox_item_read(
    match_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchInboxItemResponse:
    item = service.mark_inbox_match_read(db, identity, match_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match inbox item not found.")
    return MatchInboxItemResponse.model_validate(item)
