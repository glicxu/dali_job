from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.accounts.models import User
from app.modules.auth.dependencies import (
    AuthenticatedIdentity,
    get_access_ttl_seconds,
    get_auth_secret,
    get_current_identity,
)
from app.modules.auth.security import create_access_token, hash_password, verify_password
from app.modules.profiles.repository import ensure_account_for_identity

router = APIRouter(tags=["auth"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="America/New_York", max_length=64)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class CurrentUserResponse(BaseModel):
    auth_mode: str
    external_user_id: str
    email: str
    display_name: str
    provider: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUserResponse


def _public_user(request: Request, identity: AuthenticatedIdentity) -> CurrentUserResponse:
    runtime = getattr(request.app.state, "runtime", None)
    return CurrentUserResponse(
        auth_mode=str(getattr(runtime, "auth_mode", "dev") if runtime else "dev"),
        external_user_id=identity.external_user_id,
        email=identity.email,
        display_name=identity.display_name,
        provider=identity.provider,
    )


def _token_for(email: str) -> str:
    return create_access_token(email, get_auth_secret(), get_access_ttl_seconds())


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="valid email is required")
    return email


@auth_router.post("/register", response_model=AuthResponse)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthResponse:
    email = _normalize_email(payload.email)
    existing = db.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        auth_provider="dalijob",
        is_active=True,
        timezone=payload.timezone or "America/New_York",
    )
    try:
        db.add(user)
        db.flush()
        identity = AuthenticatedIdentity(
            external_user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            timezone=user.timezone,
            provider=user.auth_provider,
        )
        ensure_account_for_identity(db, identity)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered") from exc

    return AuthResponse(access_token=_token_for(email), user=_public_user(request, identity))


@auth_router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthResponse:
    email = _normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")
    if not bool(user.is_active):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user inactive")

    identity = AuthenticatedIdentity(
        external_user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        provider=user.auth_provider,
    )
    ensure_account_for_identity(db, identity)
    return AuthResponse(access_token=_token_for(email), user=_public_user(request, identity))


@router.get("/me", response_model=CurrentUserResponse)
def get_me(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> CurrentUserResponse:
    return _public_user(request, identity)
