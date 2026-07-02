from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.db.session import dispose_db_engines
from app.modules.auth.router import auth_router, router as auth_base_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.documents.router import router as documents_router
from app.modules.health.router import router as health_router
from app.modules.job_search.router import router as job_search_router
from app.modules.jobs.router import router as jobs_router
from app.modules.profiles.router import resume_profiles_router, router as profile_router
from app.modules.resume_job_match.router import router as resume_job_match_router

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = getattr(app.state, "runtime", None)
    if runtime is not None:
        LOGGER.info(
            "DaliJob server starting env=%s host=%s port=%s",
            runtime.env_name,
            runtime.host,
            runtime.port,
        )
    try:
        yield
    finally:
        dispose_db_engines()
        LOGGER.info("DaliJob server shutdown complete")


def create_app(config_path: Optional[str] = None) -> FastAPI:
    runtime = load_runtime_config(config_path)
    configure_logging(runtime.log_level)

    app = FastAPI(title="DaliJob API", version="0.1.0", lifespan=lifespan)
    app.state.runtime = runtime

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.client_origins,
        allow_origin_regex=runtime.client_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(auth_base_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(job_search_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(resume_profiles_router, prefix="/api/v1")
    app.include_router(resume_job_match_router, prefix="/api/v1")
    return app


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DaliJob API Server")
    parser.add_argument("-c", "--config", help="Path to ProcessConfig ini file", required=False)
    parser.add_argument("--host", help="Override bind host", required=False)
    parser.add_argument("--port", type=int, help="Override bind port", required=False)
    parser.add_argument("--log-level", help="Override log level", required=False)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    app = create_app(args.config)
    runtime = app.state.runtime

    host = args.host or runtime.host
    port = args.port or runtime.port
    log_level = (args.log_level or runtime.log_level).lower()

    uvicorn.run(app, host=host, port=port, log_level=log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
