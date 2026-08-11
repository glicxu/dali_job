from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Generator

from DaliCommonLib.dali_db_man import DbMan
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.modules.accounts.dev_identity import DEV_USER_DISPLAY_NAME, DEV_USER_EMAIL, DEV_USER_ID
from app.modules.auth.service import resolve_session


@dataclass(frozen=True)
class AuthenticatedIdentity:
    external_user_id: str
    email: str
    display_name: str
    timezone: str = "America/New_York"
    provider: str = "dev"
    role: str = "user"
    tutorial_completed: bool = True


def get_dev_identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        external_user_id=str(DEV_USER_ID),
        email=DEV_USER_EMAIL,
        display_name=DEV_USER_DISPLAY_NAME,
        provider="dev",
        role="admin",
    )


def _auth_mode(request: Request) -> str:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None:
        return str(getattr(runtime, "auth_mode", "dev") or "dev").strip().lower()
    return "dev"


def get_auth_db_session(request: Request) -> Generator[Session | None, None, None]:
    if _auth_mode(request) in {"dev", "disabled"}:
        yield None
        return
    with DbMan.session_scope() as session:
        yield session


def get_current_identity(
    request: Request,
    db: Session | None = Depends(get_auth_db_session),
) -> AuthenticatedIdentity:
    mode = _auth_mode(request)
    if mode in {"dev", "disabled"}:
        return get_dev_identity()
    if mode != "local":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="unsupported auth mode")
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="runtime unavailable")
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable")
    _session, user = resolve_session(db, request, runtime)
    return AuthenticatedIdentity(
        external_user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        provider=user.auth_provider,
        role=user.role,
        tutorial_completed=user.tutorial_completed_at is not None,
    )


def require_admin(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> AuthenticatedIdentity:
    if identity.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    return identity
