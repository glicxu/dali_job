from __future__ import annotations

import os
from dataclasses import dataclass

from DaliCommonLib.dali_db_man import DbMan
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.config import read_config_value
from app.modules.accounts.dev_identity import DEV_USER_DISPLAY_NAME, DEV_USER_EMAIL, DEV_USER_ID
from app.modules.accounts.models import User
from app.modules.auth.security import decode_access_token

DEFAULT_AUTH_SECRET = "change-me-dalijob-auth-local-development-only"
DEFAULT_ACCESS_TTL_SECONDS = 60 * 60 * 24 * 7
INVALID_AUTH_SECRETS = {
    "",
    "change-me",
    "change-me-dalijob-auth-local-development-only",
}

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedIdentity:
    external_user_id: str
    email: str
    display_name: str
    timezone: str = "America/New_York"
    provider: str = "dev"


def get_dev_identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        external_user_id=str(DEV_USER_ID),
        email=DEV_USER_EMAIL,
        display_name=DEV_USER_DISPLAY_NAME,
        provider="dev",
    )


def get_auth_secret() -> str:
    env_secret = os.getenv("DALIJOB_JWT_SECRET", "").strip()
    if env_secret.lower() in INVALID_AUTH_SECRETS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DALIJOB_JWT_SECRET must be configured to a non-default value when local auth is enabled.",
        )
    return env_secret


def get_access_ttl_seconds() -> int:
    raw = read_config_value("dali_job_auth", "access_ttl_seconds", str(DEFAULT_ACCESS_TTL_SECONDS))
    try:
        return int(raw or DEFAULT_ACCESS_TTL_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_ACCESS_TTL_SECONDS


def _auth_mode(request: Request) -> str:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None:
        return str(getattr(runtime, "auth_mode", "dev") or "dev").strip().lower()
    return "dev"


def _identity_from_email(email: str) -> AuthenticatedIdentity:
    with DbMan.session_scope() as session:
        user = session.execute(select(User).where(User.email == email).limit(1)).scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
        if not bool(user.is_active):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user inactive")
        return AuthenticatedIdentity(
            external_user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            timezone=user.timezone,
            provider=user.auth_provider,
        )


def get_current_identity(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthenticatedIdentity:
    mode = _auth_mode(request)
    if mode in {"dev", "disabled"}:
        return get_dev_identity()
    if mode != "local":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="unsupported auth mode")
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    secret = get_auth_secret()
    try:
        payload = decode_access_token(creds.credentials, secret)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc

    email = str(payload.get("sub") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return _identity_from_email(email)
