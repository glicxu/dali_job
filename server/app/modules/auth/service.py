from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import RuntimeConfig
from app.modules.accounts.models import User
from app.modules.auth.email_delivery import send_account_email
from app.modules.auth.models import AuthActionToken, AuthSession

SESSION_COOKIE_NAME = "dalijob_session"
CSRF_COOKIE_NAME = "dalijob_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _secure_cookie(runtime: RuntimeConfig) -> bool:
    return runtime.env_name.lower() in {"prod", "production"}


def create_session(db: Session, user: User, runtime: RuntimeConfig, response: Response) -> AuthSession:
    now = utc_now()
    raw_token = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_hash=token_hash(raw_csrf),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=now + timedelta(seconds=runtime.session_idle_seconds),
        absolute_expires_at=now + timedelta(seconds=runtime.session_absolute_seconds),
    )
    db.add(session)
    db.flush()
    secure = _secure_cookie(runtime)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_token,
        max_age=runtime.session_absolute_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        raw_csrf,
        max_age=runtime.session_absolute_seconds,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )
    return session


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def resolve_session(db: Session, request: Request, runtime: RuntimeConfig) -> tuple[AuthSession, User]:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token)).limit(1)
    ).scalar_one_or_none()
    now = utc_now()
    if (
        session is None
        or session.revoked_at is not None
        or _as_utc(session.idle_expires_at) <= now
        or _as_utc(session.absolute_expires_at) <= now
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        session.revoked_at = now
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user inactive")
    if user.email_verified_at is None:
        session.revoked_at = now
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="email verification required")

    if request.method.upper() in UNSAFE_METHODS:
        cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME, "")
        header_csrf = request.headers.get(CSRF_HEADER_NAME, "")
        if (
            not cookie_csrf
            or not header_csrf
            or not hmac.compare_digest(cookie_csrf, header_csrf)
            or not hmac.compare_digest(token_hash(header_csrf), session.csrf_hash)
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")

    if (now - _as_utc(session.last_seen_at)).total_seconds() >= 300:
        session.last_seen_at = now
        session.idle_expires_at = min(
            now + timedelta(seconds=runtime.session_idle_seconds),
            _as_utc(session.absolute_expires_at),
        )
    return session, user


def revoke_session_from_request(db: Session, request: Request) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not raw_token:
        return
    db.execute(
        update(AuthSession)
        .where(AuthSession.token_hash == token_hash(raw_token), AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


def revoke_all_sessions(db: Session, user_id: int) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )


def create_action_token(db: Session, user: User, purpose: str, ttl_seconds: int) -> str:
    now = utc_now()
    db.execute(
        update(AuthActionToken)
        .where(
            AuthActionToken.user_id == user.id,
            AuthActionToken.purpose == purpose,
            AuthActionToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    raw_token = secrets.token_urlsafe(48)
    db.add(
        AuthActionToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=token_hash(raw_token),
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    db.flush()
    return raw_token


def consume_action_token(db: Session, raw_token: str, purpose: str) -> User:
    action = db.execute(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == token_hash(raw_token),
            AuthActionToken.purpose == purpose,
        ).limit(1)
    ).scalar_one_or_none()
    now = utc_now()
    if action is None or action.consumed_at is not None or _as_utc(action.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired link")
    user = db.get(User, action.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired link")
    action.consumed_at = now
    return user


def send_verification_email(db: Session, user: User, runtime: RuntimeConfig) -> None:
    token = create_action_token(db, user, "verify_email", runtime.email_action_ttl_seconds)
    url = f"{runtime.public_client_url}/auth?action=verify&token={quote(token)}"
    send_account_email(
        runtime,
        user.email,
        "Verify your DaliJob email",
        f"Verify your email to activate DaliJob:\n\n{url}\n\nThis link expires in one hour.",
    )


def send_password_reset_email(db: Session, user: User, runtime: RuntimeConfig) -> None:
    token = create_action_token(db, user, "password_reset", runtime.email_action_ttl_seconds)
    url = f"{runtime.public_client_url}/auth?action=reset&token={quote(token)}"
    send_account_email(
        runtime,
        user.email,
        "Reset your DaliJob password",
        f"Reset your DaliJob password:\n\n{url}\n\nThis link expires in one hour and can be used once.",
    )
