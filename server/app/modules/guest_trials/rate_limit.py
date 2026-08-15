from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class GuestRateLimitPolicy:
    create_ip_limit: int = 5
    parse_trial_limit: int = 3
    parse_ip_limit: int = 20
    window_seconds: int = 3600


class GuestRateLimiter:
    """Process-local guest abuse control for the current single-instance deployment."""

    def __init__(self, policy: GuestRateLimitPolicy | None = None) -> None:
        self.policy = policy or GuestRateLimitPolicy()
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def enforce_create(self, client_ip: str) -> None:
        self._enforce((("create_ip", client_ip, self.policy.create_ip_limit),))

    def enforce_parse(self, client_ip: str, public_id: str) -> None:
        self._enforce(
            (
                ("parse_ip", client_ip, self.policy.parse_ip_limit),
                ("parse_trial", public_id, self.policy.parse_trial_limit),
            )
        )

    def _enforce(self, rules: tuple[tuple[str, str, int], ...]) -> None:
        now = time.monotonic()
        retry_after = 0
        with self._lock:
            for bucket, key, limit in rules:
                entries = self._requests[(bucket, key)]
                cutoff = now - self.policy.window_seconds
                while entries and entries[0] <= cutoff:
                    entries.popleft()
                if len(entries) >= limit:
                    retry_after = max(retry_after, max(1, math.ceil(entries[0] + self.policy.window_seconds - now)))
            if retry_after == 0:
                for bucket, key, _limit in rules:
                    self._requests[(bucket, key)].append(now)
        if retry_after:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many guest attempts. Wait and try again.",
                headers={"Retry-After": str(retry_after)},
            )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def enforce_guest_creation_limit(request: Request) -> None:
    request.app.state.guest_rate_limiter.enforce_create(_client_ip(request))


def enforce_guest_parse_limit(request: Request, public_id: str) -> None:
    request.app.state.guest_rate_limiter.enforce_parse(_client_ip(request), public_id)
