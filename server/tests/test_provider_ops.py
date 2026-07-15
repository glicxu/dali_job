from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from app.core.provider_ops import ProviderRateLimiter, run_provider_call
from app.modules.auth.dependencies import AuthenticatedIdentity


def make_request(*, user_limit: int = 20, ip_limit: int = 60) -> Request:
    app = SimpleNamespace(
        state=SimpleNamespace(
            runtime=SimpleNamespace(
                provider_user_limit_per_minute=user_limit,
                provider_ip_limit_per_minute=ip_limit,
            ),
            provider_rate_limiter=ProviderRateLimiter(),
        )
    )
    return Request({"type": "http", "app": app, "client": ("127.0.0.1", 12345), "headers": []})


IDENTITY = AuthenticatedIdentity(
    external_user_id="provider-test-user",
    email="provider@example.com",
    display_name="Provider Test",
)


def test_provider_call_logs_structured_success_record(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.core.provider_ops")

    result = run_provider_call(
        make_request(),
        IDENTITY,
        provider="apify",
        feature="job_search",
        operation=lambda: ["one", "two"],
        usage_units=len,
    )

    assert result == ["one", "two"]
    assert "provider=apify" in caplog.text
    assert "feature=job_search" in caplog.text
    assert "outcome=succeeded" in caplog.text
    assert "usage_units=2" in caplog.text


def test_provider_call_enforces_user_limit_with_manual_fallback() -> None:
    request = make_request(user_limit=1)
    run_provider_call(
        request,
        IDENTITY,
        provider="openai",
        feature="resume_profile_parse",
        operation=lambda: "ok",
    )

    with pytest.raises(HTTPException) as exc_info:
        run_provider_call(
            request,
            IDENTITY,
            provider="openai",
            feature="resume_profile_parse",
            operation=lambda: "blocked",
        )

    assert exc_info.value.status_code == 429
    assert "manual workflow" in str(exc_info.value.detail)
    assert exc_info.value.headers and "Retry-After" in exc_info.value.headers


def test_provider_call_maps_unexpected_failure_without_exposing_message(caplog) -> None:
    caplog.set_level(logging.WARNING, logger="app.core.provider_ops")

    with pytest.raises(HTTPException) as exc_info:
        run_provider_call(
            make_request(),
            IDENTITY,
            provider="openai",
            feature="resume_job_match",
            operation=lambda: (_ for _ in ()).throw(RuntimeError("secret provider response")),
        )

    assert exc_info.value.status_code == 502
    assert "secret provider response" not in str(exc_info.value.detail)
    assert "secret provider response" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
