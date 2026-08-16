from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.matching_v2.models import MatchingOperation, MatchingOperationStage
from app.modules.matching_v2.repositories import ArtifactOwner


STAGE_DEFINITIONS = (
    ("candidate_profile", 3),
    ("job_profile", 3),
    ("qualification", 2),
    ("preference", 1),
    ("eligibility", 1),
    ("scoring", 3),
)


class IdempotencyKeyReused(RuntimeError):
    pass


class OperationLeaseUnavailable(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_or_get_operation(
    db: Session,
    *,
    owner: ArtifactOwner,
    idempotency_key: str,
    request_hash: str,
    request_payload: dict,
    mode: str,
) -> tuple[MatchingOperation, bool]:
    workspace_id, user_id = _authenticated(owner)
    existing = db.scalar(
        select(MatchingOperation).where(
            MatchingOperation.workspace_id == workspace_id,
            MatchingOperation.user_id == user_id,
            MatchingOperation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise IdempotencyKeyReused("The idempotency key was already used with different inputs.")
        return existing, False

    operation = MatchingOperation(
        public_id=f"mop_{uuid.uuid4().hex}",
        workspace_id=workspace_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        request_payload=request_payload,
        mode=mode,
        status="pending",
        correlation_id=f"match_{uuid.uuid4().hex}",
    )
    db.add(operation)
    db.flush()
    for ordinal, (stage_name, max_attempts) in enumerate(STAGE_DEFINITIONS, start=1):
        db.add(
            MatchingOperationStage(
                matching_operation_id=operation.id,
                stage=stage_name,
                ordinal=ordinal,
                status="pending",
                max_attempts=max_attempts,
                input_artifact_ids={},
                provider_usage={},
                policy_versions={},
            )
        )
    db.flush()
    return operation, True


def get_operation(
    db: Session,
    *,
    owner: ArtifactOwner,
    public_id: str,
) -> MatchingOperation | None:
    workspace_id, user_id = _authenticated(owner)
    return db.scalar(
        select(MatchingOperation).where(
            MatchingOperation.public_id == public_id,
            MatchingOperation.workspace_id == workspace_id,
            MatchingOperation.user_id == user_id,
        )
    )


def get_operation_for_match(
    db: Session,
    *,
    owner: ArtifactOwner,
    match_result_id: int,
) -> MatchingOperation | None:
    workspace_id, user_id = _authenticated(owner)
    return db.scalar(
        select(MatchingOperation)
        .where(
            MatchingOperation.match_result_id == match_result_id,
            MatchingOperation.workspace_id == workspace_id,
            MatchingOperation.user_id == user_id,
        )
        .order_by(MatchingOperation.created_at.desc())
    )


def list_stages(db: Session, operation_id: int) -> list[MatchingOperationStage]:
    return list(
        db.scalars(
            select(MatchingOperationStage)
            .where(MatchingOperationStage.matching_operation_id == operation_id)
            .order_by(MatchingOperationStage.ordinal)
        )
    )


def first_incomplete_stage(db: Session, operation_id: int) -> MatchingOperationStage | None:
    return db.scalar(
        select(MatchingOperationStage)
        .where(
            MatchingOperationStage.matching_operation_id == operation_id,
            MatchingOperationStage.status != "completed",
        )
        .order_by(MatchingOperationStage.ordinal)
        .limit(1)
    )


def claim_operation(
    db: Session,
    operation: MatchingOperation,
    *,
    lease_owner: str,
    lease_seconds: int = 120,
) -> None:
    now = utc_now()
    lease_expiry = _utc(operation.lease_expires_at)
    if operation.lease_owner and operation.lease_owner != lease_owner and lease_expiry and lease_expiry > now:
        raise OperationLeaseUnavailable("Matching operation is already being processed.")
    operation.lease_owner = lease_owner
    operation.lease_expires_at = now + timedelta(seconds=lease_seconds)
    operation.heartbeat_at = now
    operation.status = "running"
    operation.started_at = operation.started_at or now
    operation.error_code = None
    operation.error_message = None
    db.commit()


def begin_stage(
    db: Session,
    operation: MatchingOperation,
    stage: MatchingOperationStage,
    *,
    input_artifact_ids: dict,
) -> None:
    now = utc_now()
    if stage.attempt_count >= stage.max_attempts:
        stage.status = "terminal_failure"
        operation.status = "terminal_failure"
        operation.error_code = "STAGE_RETRY_LIMIT_REACHED"
        operation.error_message = "This matching stage reached its retry limit."
        operation.completed_at = now
        db.commit()
        raise RuntimeError("Matching stage retry limit reached.")
    stage.status = "running"
    stage.attempt_count += 1
    stage.input_artifact_ids = input_artifact_ids
    stage.started_at = now
    stage.heartbeat_at = now
    stage.error_code = None
    stage.error_message = None
    operation.current_stage = stage.stage
    operation.heartbeat_at = now
    operation.lease_expires_at = now + timedelta(seconds=120)
    db.commit()


def complete_stage(
    db: Session,
    operation: MatchingOperation,
    stage: MatchingOperationStage,
    *,
    output_artifact_id: str | None,
    cache_hit: bool,
    provider_usage: dict | None = None,
    policy_versions: dict | None = None,
) -> None:
    now = utc_now()
    stage.status = "completed"
    stage.output_artifact_id = output_artifact_id
    stage.cache_hit = cache_hit
    stage.provider_usage = provider_usage or {}
    stage.policy_versions = policy_versions or {}
    stage.heartbeat_at = now
    stage.completed_at = now
    operation.heartbeat_at = now
    operation.lease_expires_at = now + timedelta(seconds=120)
    db.commit()


def fail_stage(
    db: Session,
    operation: MatchingOperation,
    stage: MatchingOperationStage,
    *,
    error_code: str,
    error_message: str,
) -> None:
    now = utc_now()
    retryable = stage.attempt_count < stage.max_attempts
    stage.status = "retryable_failure" if retryable else "terminal_failure"
    stage.error_code = error_code
    stage.error_message = error_message[:500]
    stage.heartbeat_at = now
    stage.completed_at = now
    operation.status = "retryable_failure" if retryable else "terminal_failure"
    operation.error_code = error_code
    operation.error_message = error_message[:500]
    operation.lease_owner = None
    operation.lease_expires_at = None
    operation.heartbeat_at = now
    operation.completed_at = None if retryable else now
    db.commit()


def complete_operation(
    db: Session,
    operation: MatchingOperation,
    *,
    match_result_id: int,
) -> None:
    now = utc_now()
    operation.match_result_id = match_result_id
    operation.status = "completed"
    operation.current_stage = None
    operation.lease_owner = None
    operation.lease_expires_at = None
    operation.heartbeat_at = now
    operation.completed_at = now
    operation.error_code = None
    operation.error_message = None
    db.commit()


def queue_retry(db: Session, operation: MatchingOperation) -> None:
    if operation.status != "retryable_failure":
        raise ValueError("Only a retryable matching operation can retry.")
    stage = first_incomplete_stage(db, operation.id)
    if stage is None or stage.status != "retryable_failure":
        raise ValueError("The failed matching stage is unavailable.")
    stage.status = "pending"
    stage.error_code = None
    stage.error_message = None
    operation.status = "pending"
    operation.error_code = None
    operation.error_message = None
    operation.lease_owner = None
    operation.lease_expires_at = None
    db.commit()


def recover_interrupted_operation(db: Session, operation: MatchingOperation) -> bool:
    now = utc_now()
    if operation.status != "running":
        return False
    lease_expiry = _utc(operation.lease_expires_at)
    if lease_expiry is not None and lease_expiry > now:
        return False
    stage = first_incomplete_stage(db, operation.id)
    if stage is None or stage.status != "running":
        return False
    stage.status = "retryable_failure"
    stage.error_code = "PROCESS_INTERRUPTED"
    stage.error_message = "Processing stopped before this stage completed."
    operation.status = "retryable_failure"
    operation.error_code = stage.error_code
    operation.error_message = stage.error_message
    operation.lease_owner = None
    operation.lease_expires_at = None
    db.commit()
    return True


def _authenticated(owner: ArtifactOwner) -> tuple[int, int]:
    if owner.kind != "authenticated" or owner.workspace_id is None or owner.user_id is None:
        raise ValueError("Matching operations require an authenticated owner.")
    return owner.workspace_id, owner.user_id


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
