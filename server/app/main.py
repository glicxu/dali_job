from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import load_runtime_config
from app.core.logging import REQUEST_ID, RequestLoggingMiddleware, configure_logging
from app.core.provider_ops import ProviderRateLimiter
from app.db.session import dispose_db_engines
from app.modules.applications.router import router as applications_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import auth_router, router as auth_base_router
from app.modules.auth.mobile_router import router as mobile_auth_router
from app.modules.auth.policy import validate_route_authorization
from app.modules.auth.rate_limit import AuthRateLimiter, AuthRateLimitPolicy
from app.modules.automation.router import router as automation_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.documents.router import router as documents_router
from app.modules.evaluation.router import router as evaluation_router
from app.modules.health.router import router as health_router
from app.modules.guest_trials.router import router as guest_trials_router
from app.modules.guest_trials.rate_limit import GuestRateLimiter
from app.modules.job_search.router import router as job_search_router
from app.modules.interviews.router import router as interviews_router
from app.modules.jobs.router import router as jobs_router
from app.modules.materials.router import router as materials_router
from app.modules.matching_v2.router import router as matching_v2_router
from app.modules.matching_v2.extraction import JobProfileValidationFailed
from app.modules.notifications.router import router as notifications_router
from app.modules.operations.router import router as operations_router
from app.modules.profiles.router import resume_profiles_router, router as profile_router
from app.modules.reports.router import router as reports_router
from app.modules.resume_job_match.router import router as resume_job_match_router

LOGGER = logging.getLogger(__name__)

API_ROUTERS = (
    auth_base_router,
    auth_router,
    mobile_auth_router,
    automation_router,
    applications_router,
    analytics_router,
    dashboard_router,
    documents_router,
    evaluation_router,
    health_router,
    guest_trials_router,
    job_search_router,
    interviews_router,
    jobs_router,
    materials_router,
    matching_v2_router,
    notifications_router,
    operations_router,
    profile_router,
    resume_profiles_router,
    resume_job_match_router,
    reports_router,
)


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
    configure_logging(runtime)
    validate_route_authorization(API_ROUTERS)

    app = FastAPI(title="DaliJob API", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(JobProfileValidationFailed)
    async def job_profile_validation_failed_handler(
        _request: object, exc: JobProfileValidationFailed
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "error": "JOB_PROFILE_VALIDATION_FAILED",
                "stage": "job_profile_extraction",
                "correlation_id": REQUEST_ID.get(),
                "repair_attempted": exc.repair_attempted,
            },
        )

    app.state.runtime = runtime
    app.state.tier_entitlements = runtime.tier_entitlements
    app.state.provider_rate_limiter = ProviderRateLimiter()
    app.state.guest_rate_limiter = GuestRateLimiter()
    app.state.auth_rate_limiter = AuthRateLimiter(
        AuthRateLimitPolicy(
            login_ip_limit=runtime.auth_login_ip_limit,
            login_account_limit=runtime.auth_login_account_limit,
            login_window_seconds=runtime.auth_login_window_seconds,
            register_ip_limit=runtime.auth_register_ip_limit,
            register_account_limit=runtime.auth_register_account_limit,
            register_window_seconds=runtime.auth_register_window_seconds,
        )
    )

    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.client_origins,
        allow_origin_regex=runtime.client_origin_regex or None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Request-ID"],
    )

    app.include_router(auth_base_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(mobile_auth_router, prefix="/api/v1")
    app.include_router(automation_router, prefix="/api/v1")
    app.include_router(applications_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(evaluation_router, prefix="/api/v1")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(guest_trials_router, prefix="/api/v1")
    app.include_router(job_search_router, prefix="/api/v1")
    app.include_router(interviews_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(materials_router, prefix="/api/v1")
    app.include_router(matching_v2_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(operations_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(resume_profiles_router, prefix="/api/v1")
    app.include_router(resume_job_match_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
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
