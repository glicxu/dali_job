from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import RuntimeConfig
from app.modules.accounts.models import User
from app.modules.auth.models import AuthSession, MobileRefreshToken
from app.modules.auth.service import token_hash


class RefreshTokenInvalid(ValueError):
    pass


class RefreshTokenReuse(RefreshTokenInvalid):
    pass


@dataclass(frozen=True)
class MobileTokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    session: AuthSession
    user: User


def create_mobile_session(
    db: Session,
    user: User,
    runtime: RuntimeConfig,
    *,
    device_label: str,
    now: datetime | None = None,
) -> MobileTokenPair:
    issued_at = now or datetime.now(timezone.utc)
    raw_access = secrets.token_urlsafe(48)
    raw_refresh = secrets.token_urlsafe(64)
    access_expires_at = issued_at + timedelta(seconds=runtime.mobile_access_token_seconds)
    refresh_expires_at = issued_at + timedelta(seconds=runtime.mobile_refresh_token_seconds)
    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(raw_access),
        csrf_hash="",
        session_type="mobile",
        token_family_id=uuid.uuid4().hex,
        device_label=device_label.strip(),
        created_at=issued_at,
        last_seen_at=issued_at,
        idle_expires_at=access_expires_at,
        absolute_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
    )
    db.add(session)
    db.flush()
    db.add(
        MobileRefreshToken(
            session_id=session.id,
            token_hash=token_hash(raw_refresh),
            created_at=issued_at,
            expires_at=refresh_expires_at,
        )
    )
    db.flush()
    return MobileTokenPair(
        access_token=raw_access,
        refresh_token=raw_refresh,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        session=session,
        user=user,
    )


def rotate_mobile_session(
    db: Session,
    raw_refresh_token: str,
    runtime: RuntimeConfig,
    *,
    now: datetime | None = None,
) -> MobileTokenPair:
    rotated_at = now or datetime.now(timezone.utc)
    refresh = db.scalar(
        select(MobileRefreshToken)
        .where(MobileRefreshToken.token_hash == token_hash(raw_refresh_token))
        .with_for_update()
    )
    if refresh is None:
        raise RefreshTokenInvalid("invalid refresh token")
    session = db.get(AuthSession, refresh.session_id)
    if session is None or session.session_type != "mobile":
        raise RefreshTokenInvalid("invalid refresh token")
    if refresh.consumed_at is not None or refresh.revoked_at is not None:
        _revoke_family(db, session, rotated_at)
        raise RefreshTokenReuse("refresh token reuse detected")
    if (
        _as_utc(refresh.expires_at) <= rotated_at
        or session.refresh_expires_at is None
        or _as_utc(session.refresh_expires_at) <= rotated_at
        or session.revoked_at is not None
    ):
        raise RefreshTokenInvalid("refresh token expired")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active or user.deleted_at is not None or user.email_verified_at is None:
        _revoke_family(db, session, rotated_at)
        raise RefreshTokenInvalid("mobile session unavailable")

    raw_access = secrets.token_urlsafe(48)
    raw_refresh = secrets.token_urlsafe(64)
    access_expires_at = min(
        rotated_at + timedelta(seconds=runtime.mobile_access_token_seconds),
        _as_utc(session.refresh_expires_at),
    )
    replacement = MobileRefreshToken(
        session_id=session.id,
        token_hash=token_hash(raw_refresh),
        created_at=rotated_at,
        expires_at=_as_utc(session.refresh_expires_at),
    )
    db.add(replacement)
    db.flush()
    refresh.consumed_at = rotated_at
    refresh.replacement_token_id = replacement.id
    session.token_hash = token_hash(raw_access)
    session.last_seen_at = rotated_at
    session.idle_expires_at = access_expires_at
    session.absolute_expires_at = access_expires_at
    db.flush()
    return MobileTokenPair(
        access_token=raw_access,
        refresh_token=raw_refresh,
        access_expires_at=access_expires_at,
        refresh_expires_at=_as_utc(session.refresh_expires_at),
        session=session,
        user=user,
    )


def list_mobile_sessions(
    db: Session,
    user_id: int,
    *,
    limit: int,
    before_id: int | None,
) -> tuple[list[AuthSession], int | None]:
    statement = select(AuthSession).where(
        AuthSession.user_id == user_id,
        AuthSession.session_type == "mobile",
        AuthSession.revoked_at.is_(None),
    )
    if before_id is not None:
        statement = statement.where(AuthSession.id < before_id)
    sessions = list(
        db.scalars(
            statement.order_by(AuthSession.id.desc()).limit(limit + 1)
        )
    )
    has_more = len(sessions) > limit
    sessions = sessions[:limit]
    return sessions, sessions[-1].id if has_more and sessions else None


def revoke_mobile_session(db: Session, user_id: int, session_id: int) -> bool:
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.session_type == "mobile",
            AuthSession.revoked_at.is_(None),
        )
    )
    if session is None:
        return False
    _revoke_family(db, session, datetime.now(timezone.utc))
    return True


def current_mobile_session(db: Session, authorization: str | None) -> AuthSession | None:
    raw_access = _bearer_token(authorization)
    if raw_access is None:
        return None
    return db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash(raw_access),
            AuthSession.session_type == "mobile",
            AuthSession.revoked_at.is_(None),
        )
    )


def _revoke_family(db: Session, session: AuthSession, revoked_at: datetime) -> None:
    if session.revoked_at is None:
        session.revoked_at = revoked_at
    db.execute(
        update(MobileRefreshToken)
        .where(MobileRefreshToken.session_id == session.id, MobileRefreshToken.revoked_at.is_(None))
        .values(revoked_at=revoked_at)
    )


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
