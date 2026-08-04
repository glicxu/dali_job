from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthRateLimitPolicy:
    login_ip_limit: int
    login_account_limit: int
    login_window_seconds: int
    register_ip_limit: int
    register_account_limit: int
    register_window_seconds: int


@dataclass(frozen=True)
class _RateRule:
    bucket: str
    key: str
    limit: int
    window_seconds: int


class AuthRateLimiter:
    """Process-local abuse control for the current single-instance deployment."""

    def __init__(self, policy: AuthRateLimitPolicy) -> None:
        self._policy = policy
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def enforce(self, action: str, client_ip: str, account_key: str) -> None:
        rules = self._rules(action, client_ip, account_key)
        now = time.monotonic()
        blocked_rule: _RateRule | None = None
        retry_after = 1
        with self._lock:
            for rule in rules:
                entries = self._requests[(rule.bucket, rule.key)]
                cutoff = now - rule.window_seconds
                while entries and entries[0] <= cutoff:
                    entries.popleft()
                if len(entries) >= rule.limit:
                    candidate_retry = max(1, math.ceil(entries[0] + rule.window_seconds - now))
                    if blocked_rule is None or candidate_retry > retry_after:
                        blocked_rule = rule
                        retry_after = candidate_retry
            if blocked_rule is None:
                for rule in rules:
                    self._requests[(rule.bucket, rule.key)].append(now)

        if blocked_rule is None:
            return

        account_hash = hashlib.sha256(account_key.encode("utf-8")).hexdigest()[:12]
        LOGGER.warning(
            "auth_rate_limit outcome=blocked action=%s bucket=%s client_ip=%s account_hash=%s retry_after=%s",
            action,
            blocked_rule.bucket,
            client_ip,
            account_hash,
            retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    def _rules(self, action: str, client_ip: str, account_key: str) -> tuple[_RateRule, _RateRule]:
        if action == "login":
            return (
                _RateRule("login_ip", client_ip, self._policy.login_ip_limit, self._policy.login_window_seconds),
                _RateRule(
                    "login_account",
                    account_key,
                    self._policy.login_account_limit,
                    self._policy.login_window_seconds,
                ),
            )
        if action == "register":
            return (
                _RateRule(
                    "register_ip",
                    client_ip,
                    self._policy.register_ip_limit,
                    self._policy.register_window_seconds,
                ),
                _RateRule(
                    "register_account",
                    account_key,
                    self._policy.register_account_limit,
                    self._policy.register_window_seconds,
                ),
            )
        raise ValueError(f"Unsupported authentication rate-limit action: {action}")


def normalized_account_key(email: str) -> str:
    return email.strip().lower()


def request_client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def enforce_auth_rate_limit(request: Request, action: str, email: str) -> None:
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if limiter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication protection is unavailable.",
        )
    limiter.enforce(action, request_client_ip(request), normalized_account_key(email))
