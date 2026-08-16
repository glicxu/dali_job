from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import or_, select

from app.modules.guest_trials.matching import (
    claim_cached_match,
    require_ready_inputs,
    run_cached_profile_match,
)
from app.modules.guest_trials.models import GuestMatchOperation, GuestTrial


def run_available(
    session_factory,
    *,
    worker_id: str,
    model_id: str,
    candidate_extractor,
    matcher,
    max_operations: int = 25,
) -> int:
    completed = 0
    for _ in range(max_operations):
        operation_id = _claim_next(session_factory, worker_id=worker_id)
        if operation_id is None:
            break
        with session_factory() as db:
            operation = db.get(GuestMatchOperation, operation_id)
            trial = db.get(GuestTrial, operation.guest_trial_id) if operation else None
            if operation is None or trial is None:
                continue
            try:
                profile, criterion = require_ready_inputs(db, trial)
                run_cached_profile_match(
                    model_id,
                    db,
                    trial,
                    operation,
                    profile,
                    criterion,
                    candidate_extractor,
                    matcher,
                )
            except Exception:
                db.commit()
            else:
                db.commit()
                completed += 1
    return completed


def _claim_next(session_factory, *, worker_id: str) -> int | None:
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        operation = db.scalar(
            select(GuestMatchOperation)
            .join(GuestTrial, GuestTrial.id == GuestMatchOperation.guest_trial_id)
            .where(
                GuestTrial.status.not_in(("claimed", "expired")),
                or_(
                    GuestMatchOperation.status == "pending",
                    (
                        (GuestMatchOperation.status == "matching")
                        & (GuestMatchOperation.lease_expires_at <= now)
                    ),
                    (
                        (GuestMatchOperation.status == "failed")
                        & (GuestMatchOperation.attempt_count < 3)
                        & (GuestMatchOperation.next_retry_at <= now)
                    ),
                ),
            )
            .order_by(GuestMatchOperation.created_at, GuestMatchOperation.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if operation is None or not claim_cached_match(db, operation, worker_id=worker_id):
            db.commit()
            return None
        operation_id = operation.id
        db.commit()
        return operation_id
