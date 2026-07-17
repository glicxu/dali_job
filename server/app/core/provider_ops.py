from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import HTTPException, Request, status

from app.modules.auth.dependencies import AuthenticatedIdentity

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class ProviderRateLimiter:
    def __init__(self, *, window_seconds: int = 60) -> None:
        self._window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, key: str, limit: int, *, now: float | None = None) -> int:
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - self._window_seconds
        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                retry_after = max(1, int(self._window_seconds - (timestamp - requests[0])))
                return retry_after
            requests.append(timestamp)
        return 0


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limiter(request: Request) -> ProviderRateLimiter:
    limiter = getattr(request.app.state, "provider_rate_limiter", None)
    if limiter is None:
        limiter = ProviderRateLimiter()
        request.app.state.provider_rate_limiter = limiter
    return limiter


def enforce_provider_rate_limit(
    request: Request,
    identity: AuthenticatedIdentity,
    *,
    feature: str,
) -> None:
    runtime = request.app.state.runtime
    limiter = _rate_limiter(request)
    scopes = (
        (f"user:{identity.external_user_id}", runtime.provider_user_limit_per_minute),
        (f"ip:{_client_ip(request)}", runtime.provider_ip_limit_per_minute),
    )
    for scope, limit in scopes:
        retry_after = limiter.consume(scope, limit)
        if retry_after:
            LOGGER.warning(
                "provider_call provider=rate_limit feature=%s user=%s duration_ms=0 outcome=rate_limited usage_units=0",
                feature,
                identity.external_user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Too many provider requests. Wait about {retry_after} seconds and retry, "
                    "or continue with the available manual workflow."
                ),
                headers={"Retry-After": str(retry_after)},
            )


def run_provider_call(
    request: Request,
    identity: AuthenticatedIdentity,
    *,
    provider: str,
    feature: str,
    operation: Callable[[], T],
    usage_units: Callable[[T], int | None] | None = None,
) -> T:
    if not bool(getattr(request.state, "provider_limit_already_enforced", False)):
        enforce_provider_rate_limit(request, identity, feature=feature)
    started = time.monotonic()
    try:
        result = operation()
    except HTTPException as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        LOGGER.warning(
            "provider_call provider=%s feature=%s user=%s duration_ms=%s outcome=http_%s usage_units=unknown",
            provider,
            feature,
            identity.external_user_id,
            duration_ms,
            exc.status_code,
        )
        raise
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        LOGGER.warning(
            "provider_call provider=%s feature=%s user=%s duration_ms=%s outcome=failed usage_units=unknown error_type=%s",
            provider,
            feature,
            identity.external_user_id,
            duration_ms,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The external service is temporarily unavailable. Retry shortly, "
                "or continue with the available manual workflow."
            ),
        ) from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    units = usage_units(result) if usage_units else None
    LOGGER.info(
        "provider_call provider=%s feature=%s user=%s duration_ms=%s outcome=succeeded usage_units=%s",
        provider,
        feature,
        identity.external_user_id,
        duration_ms,
        units if units is not None else "unknown",
    )
    return result


class GuardedProviderProxy:
    def __init__(
        self,
        *,
        factory: Callable[[], Any],
        method_name: str,
        request: Request,
        identity: AuthenticatedIdentity,
        provider: str,
        feature: str,
    ) -> None:
        self._factory = factory
        self._method_name = method_name
        self._request = request
        self._identity = identity
        self._provider = provider
        self._feature = feature
        self._delegate: Any | None = None

    def __getattr__(self, name: str) -> Any:
        if name != self._method_name:
            raise AttributeError(name)

        def guarded(*args: Any, **kwargs: Any) -> Any:
            def invoke() -> Any:
                if self._delegate is None:
                    self._delegate = self._factory()
                return getattr(self._delegate, self._method_name)(*args, **kwargs)

            return run_provider_call(
                self._request,
                self._identity,
                provider=self._provider,
                feature=self._feature,
                operation=invoke,
            )

        return guarded
