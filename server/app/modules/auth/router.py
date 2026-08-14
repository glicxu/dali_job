from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.accounts.models import User
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.auth.rate_limit import enforce_auth_rate_limit
from app.modules.auth.security import hash_password, verify_password
from app.modules.auth.service import (
    CSRF_COOKIE_NAME,
    clear_session_cookies,
    consume_action_token,
    create_session,
    revoke_all_sessions,
    revoke_session_from_request,
    send_password_reset_email,
    send_verification_email,
)
from app.modules.auth.account_deletion import soft_delete_account
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


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class PasswordResetRequest(TokenRequest):
    new_password: str = Field(min_length=8, max_length=256)


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)


class CurrentUserResponse(BaseModel):
    auth_mode: str
    external_user_id: str
    email: str
    display_name: str
    provider: str
    role: str
    tutorial_completed: bool


class AuthResponse(BaseModel):
    user: CurrentUserResponse


class MessageResponse(BaseModel):
    message: str


class CsrfResponse(BaseModel):
    csrf_token: str


def _runtime(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="runtime unavailable")
    return runtime


def _public_user(request: Request, identity: AuthenticatedIdentity) -> CurrentUserResponse:
    runtime = _runtime(request)
    return CurrentUserResponse(
        auth_mode=str(runtime.auth_mode),
        external_user_id=identity.external_user_id,
        email=identity.email,
        display_name=identity.display_name,
        provider=identity.provider,
        role=identity.role,
        tutorial_completed=identity.tutorial_completed,
    )


def _identity(user: User) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        external_user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        provider=user.auth_provider,
        role=user.role,
        tutorial_completed=user.tutorial_completed_at is not None,
    )


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="valid email is required")
    return email


@auth_router.post("/register", response_model=MessageResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db_session)) -> MessageResponse:
    enforce_auth_rate_limit(request, "register", payload.email)
    email = _normalize_email(payload.email)
    existing = db.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        auth_provider="dalijob",
        role="user",
        is_active=True,
        timezone=payload.timezone or "America/New_York",
        email_verified_at=None,
    )
    try:
        db.add(user)
        db.flush()
        ensure_account_for_identity(db, _identity(user))
        send_verification_email(db, user, _runtime(request))
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered") from exc
    return MessageResponse(message="Check your email to verify your account before signing in.")


@auth_router.post("/verify-email", response_model=AuthResponse)
def verify_email(
    payload: TokenRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> AuthResponse:
    enforce_auth_rate_limit(request, "login", payload.token)
    user = consume_action_token(db, payload.token, "verify_email")
    user.email_verified_at = datetime.now(timezone.utc)
    user.is_active = True
    identity = _identity(user)
    ensure_account_for_identity(db, identity)
    create_session(db, user, _runtime(request), response)
    # The browser validates the new session immediately through /auth/csrf.
    # Commit before returning so that request cannot race dependency cleanup.
    db.commit()
    return AuthResponse(user=_public_user(request, identity))


@auth_router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    payload: EmailRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    enforce_auth_rate_limit(request, "register", payload.email)
    email = _normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
    if user is not None and user.deleted_at is None and user.email_verified_at is None:
        send_verification_email(db, user, _runtime(request))
    return MessageResponse(message="If that account needs verification, a new link has been sent.")


@auth_router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db_session),
) -> AuthResponse:
    enforce_auth_rate_limit(request, "login", payload.email)
    email = _normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user inactive")
    if user.email_verified_at is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="verify your email before signing in")

    identity = _identity(user)
    ensure_account_for_identity(db, identity)
    create_session(db, user, _runtime(request), response)
    # Make the cookie-backed session visible before the immediate CSRF request.
    db.commit()
    return AuthResponse(user=_public_user(request, identity))


@auth_router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: EmailRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    enforce_auth_rate_limit(request, "login", payload.email)
    email = _normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
    if user is not None and user.is_active and user.deleted_at is None and user.email_verified_at is not None:
        send_password_reset_email(db, user, _runtime(request))
    return MessageResponse(message="If an active account exists for that email, a reset link has been sent.")


@auth_router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    enforce_auth_rate_limit(request, "login", payload.token)
    user = consume_action_token(db, payload.token, "password_reset")
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    revoke_all_sessions(db, user.id)
    return MessageResponse(message="Password changed. Sign in with your new password.")


@auth_router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    _identity_value: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> MessageResponse:
    revoke_session_from_request(db, request)
    clear_session_cookies(response)
    return MessageResponse(message="Signed out.")


@auth_router.get("/csrf", response_model=CsrfResponse)
def get_csrf_token(
    request: Request,
    _identity_value: AuthenticatedIdentity = Depends(get_current_identity),
) -> CsrfResponse:
    token = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session CSRF token unavailable")
    return CsrfResponse(csrf_token=token)


@auth_router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> Response:
    user = db.get(User, int(identity.external_user_id))
    if user is None or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="current password is incorrect")
    soft_delete_account(db, user)
    # The client redirects immediately after this response, so make deletion
    # durable before it starts a new anonymous session check.
    db.commit()
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=CurrentUserResponse)
def get_me(request: Request, identity: AuthenticatedIdentity = Depends(get_current_identity)) -> CurrentUserResponse:
    return _public_user(request, identity)


@router.post("/me/tutorial/complete", response_model=CurrentUserResponse)
def complete_tutorial(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> CurrentUserResponse:
    user, _workspace = ensure_account_for_identity(db, identity)
    if user.tutorial_completed_at is None:
        user.tutorial_completed_at = datetime.now(timezone.utc)
        db.flush()
    return _public_user(request, _identity(user))
