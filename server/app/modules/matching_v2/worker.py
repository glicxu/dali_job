from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Callable

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.matching_v2.models import MatchingOperation
from app.modules.matching_v2.orchestration import (
    first_incomplete_stage,
    queue_retry,
    recover_interrupted_operation,
)
from app.modules.matching_v2.orchestration_router import _execute_background


def run_available(
    session_factory: Callable[[], Session],
    *,
    app: Any,
    worker_id: str,
    matcher,
    candidate_extractor,
    job_extractor,
    max_operations: int = 25,
    now: datetime | None = None,
) -> int:
    if not worker_id.strip() or len(worker_id) > 120:
        raise ValueError("worker_id must contain 1 to 120 characters")
    if max_operations < 1 or max_operations > 1000:
        raise ValueError("max_operations must be between 1 and 1000")
    processed = 0
    request = _worker_request(app)
    for _ in range(max_operations):
        operation_id = claim_next_available(session_factory, now=now)
        if operation_id is None:
            break
        _execute_background(
            session_factory,
            request,
            operation_id,
            candidate_extractor,
            job_extractor,
            matcher,
        )
        processed += 1
    return processed


def claim_next_available(
    session_factory: Callable[[], Session],
    *,
    now: datetime | None = None,
) -> int | None:
    current = _utc(now or datetime.now(timezone.utc))
    with session_factory() as db:
        candidates = list(
            db.scalars(
                select(MatchingOperation)
                .where(
                    or_(
                        MatchingOperation.status == "pending",
                        (
                            (MatchingOperation.status == "running")
                            & MatchingOperation.lease_expires_at.is_not(None)
                            & (MatchingOperation.lease_expires_at <= current)
                        ),
                        MatchingOperation.status == "retryable_failure",
                    )
                )
                .order_by(MatchingOperation.created_at, MatchingOperation.id)
                .with_for_update(skip_locked=True)
                .limit(25)
            )
        )
        for operation in candidates:
            if operation.status == "running":
                if not recover_interrupted_operation(db, operation):
                    continue
            if operation.status == "retryable_failure":
                stage = first_incomplete_stage(db, operation.id)
                if stage is None or stage.completed_at is None:
                    continue
                not_before = _utc(stage.completed_at) + timedelta(
                    seconds=retry_delay_seconds(operation.id, stage.attempt_count)
                )
                if not_before > current:
                    continue
                queue_retry(db, operation)
            if operation.status == "pending":
                operation_id = operation.id
                db.commit()
                return operation_id
        db.commit()
        return None


def retry_delay_seconds(operation_id: int, attempt_count: int) -> float:
    base = min(300.0, 5.0 * (2 ** max(0, attempt_count - 1)))
    digest = hashlib.sha256(f"{operation_id}:{attempt_count}".encode()).digest()
    jitter = int.from_bytes(digest[:2], "big") / 65535 * 0.25
    return base * (1 + jitter)


def _worker_request(app: Any) -> Request:
    request = Request(
        {
            "type": "http",
            "app": app,
            "client": ("matching-v2-worker", 0),
            "headers": [],
            "method": "POST",
            "path": "/internal/matching-v2-worker",
        }
    )
    request.state.provider_limit_already_enforced = True
    return request


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
