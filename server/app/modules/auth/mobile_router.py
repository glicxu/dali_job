from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.accounts.models import User
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.auth.mobile_service import (
    MobileTokenPair,
    RefreshTokenInvalid,
    RefreshTokenReuse,
    create_mobile_session,
    current_mobile_session,
    list_mobile_sessions,
    revoke_mobile_session,
    rotate_mobile_session,
)
from app.modules.auth.rate_limit import enforce_auth_rate_limit
from app.modules.auth.router import CurrentUserResponse, _identity, _normalize_email, _public_user, _runtime
from app.modules.auth.security import verify_password
from app.modules.auth.service import token_hash
from app.modules.profiles.repository import ensure_account_for_identity


router = APIRouter(prefix="/auth/mobile", tags=["auth", "mobile"])


class MobileSessionCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)
    device_label: str = Field(min_length=1, max_length=120)

    @field_validator("device_label")
    @classmethod
    def normalize_device_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("device_label must not be blank")
        return normalized


class MobileSessionRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=512)


class MobileSessionResponse(BaseModel):
    id: int
    device_label: str
    created_at: datetime
    last_used_at: datetime
    refresh_expires_at: datetime
    is_current: bool = False


class MobileTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime
    session: MobileSessionResponse
    user: CurrentUserResponse


class MobileSessionListResponse(BaseModel):
    sessions: list[MobileSessionResponse] = Field(default_factory=list)
    next_cursor: int | None = None


@router.post("/sessions", response_model=MobileTokenResponse, status_code=status.HTTP_201_CREATED)
def open_mobile_session(
    payload: MobileSessionCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> MobileTokenResponse:
    enforce_auth_rate_limit(request, "login", payload.email)
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email).limit(1))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user inactive")
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="verify your email before signing in")
    identity = _identity(user)
    ensure_account_for_identity(db, identity)
    pair = create_mobile_session(
        db,
        user,
        _runtime(request),
        device_label=payload.device_label,
    )
    db.commit()
    return _token_response(request, pair)


@router.post("/sessions/refresh", response_model=MobileTokenResponse)
def refresh_mobile_session(
    payload: MobileSessionRefreshRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> MobileTokenResponse:
    enforce_auth_rate_limit(request, "login", token_hash(payload.refresh_token))
    try:
        pair = rotate_mobile_session(db, payload.refresh_token, _runtime(request))
    except RefreshTokenReuse as exc:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except RefreshTokenInvalid as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    db.commit()
    return _token_response(request, pair)


@router.get("/sessions", response_model=MobileSessionListResponse)
def get_mobile_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> MobileSessionListResponse:
    current = current_mobile_session(db, request.headers.get("Authorization"))
    sessions, next_cursor = list_mobile_sessions(
        db,
        int(identity.external_user_id),
        limit=limit,
        before_id=before_id,
    )
    return MobileSessionListResponse(
        sessions=[
            _session_response(item, current_id=current.id if current else None)
            for item in sessions
        ],
        next_cursor=next_cursor,
    )


@router.delete("/sessions/current", status_code=status.HTTP_204_NO_CONTENT)
def close_current_mobile_session(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Response:
    current = current_mobile_session(db, request.headers.get("Authorization"))
    if current is None or current.user_id != int(identity.external_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Current mobile session not found.")
    revoke_mobile_session(db, current.user_id, current.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_mobile_session(
    session_id: int,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Response:
    if not revoke_mobile_session(db, int(identity.external_user_id), session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mobile session not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _token_response(request: Request, pair: MobileTokenPair) -> MobileTokenResponse:
    return MobileTokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
        session=_session_response(pair.session, current_id=pair.session.id),
        user=_public_user(request, _identity(pair.user)),
    )


def _session_response(session, *, current_id: int | None) -> MobileSessionResponse:
    return MobileSessionResponse(
        id=session.id,
        device_label=session.device_label or "Mobile device",
        created_at=session.created_at,
        last_used_at=session.last_seen_at,
        refresh_expires_at=session.refresh_expires_at or datetime.now(timezone.utc),
        is_current=session.id == current_id,
    )
