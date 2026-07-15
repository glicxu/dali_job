from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db_session

router = APIRouter(tags=["health"])
EXPECTED_ALEMBIC_HEAD = "20260714_0019"


@router.get("/health")
def health(request: Request) -> dict[str, str | None]:
    runtime = request.app.state.runtime
    return {
        "status": "ok",
        "service": "dalijob-api",
        "env": runtime.env_name,
        "config_path": runtime.config_path,
    }


@router.get("/health/db", response_model=None)
def database_health(
    db: Session = Depends(get_db_session),
) -> dict[str, str | bool | None] | JSONResponse:
    current_revision: str | None = None
    try:
        current_revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database_ready": False,
                "current_revision": None,
                "expected_revision": EXPECTED_ALEMBIC_HEAD,
            },
        )

    is_ready = current_revision == EXPECTED_ALEMBIC_HEAD
    payload = {
        "status": "ok" if is_ready else "not_ready",
        "database_ready": is_ready,
        "current_revision": current_revision,
        "expected_revision": EXPECTED_ALEMBIC_HEAD,
    }
    if not is_ready:
        return JSONResponse(status_code=503, content=payload)
    return payload
