from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, str | None]:
    runtime = request.app.state.runtime
    return {
        "status": "ok",
        "service": "dalijob-api",
        "env": runtime.env_name,
        "config_path": runtime.config_path,
    }


@router.get("/health/db")
def database_health() -> dict[str, str]:
    # Phase 0 keeps this light so the server can boot before local DB config exists.
    return {"status": "not_checked"}
