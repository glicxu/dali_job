from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.operations.models import ManagedOperation, utc_now
from app.modules.profiles.repository import ensure_account_for_identity


def create_operation(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    operation_type: str,
    idempotency_key: str,
    request_payload: dict,
    provider: str | None = None,
    model_or_actor: str | None = None,
    prompt_version: str | None = None,
    progress_total: int | None = None,
) -> tuple[ManagedOperation, bool]:
    user, workspace = ensure_account_for_identity(db, identity)
    existing = db.scalar(
        select(ManagedOperation).where(
            ManagedOperation.workspace_id == workspace.id,
            ManagedOperation.user_id == user.id,
            ManagedOperation.operation_type == operation_type,
            ManagedOperation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing, False

    operation = ManagedOperation(
        workspace_id=workspace.id,
        user_id=user.id,
        operation_type=operation_type,
        idempotency_key=idempotency_key,
        request_payload=request_payload,
        provider=provider,
        model_or_actor=model_or_actor,
        prompt_version=prompt_version,
        progress_total=progress_total,
        progress_message="Waiting to start",
    )
    db.add(operation)
    db.flush()
    return operation, True


def _owned_query(identity_ids: tuple[int, int]) -> Select[tuple[ManagedOperation]]:
    workspace_id, user_id = identity_ids
    return select(ManagedOperation).where(
        ManagedOperation.workspace_id == workspace_id,
        ManagedOperation.user_id == user_id,
    )


def owner_ids(db: Session, identity: AuthenticatedIdentity) -> tuple[int, int]:
    user, workspace = ensure_account_for_identity(db, identity)
    return workspace.id, user.id


def get_operation_for_identity(
    db: Session,
    identity: AuthenticatedIdentity,
    operation_id: int,
) -> ManagedOperation | None:
    expire_stale_operations(db, identity)
    return db.scalar(_owned_query(owner_ids(db, identity)).where(ManagedOperation.id == operation_id))


def list_operations(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    operation_status: str | None = None,
    operation_type: str | None = None,
    limit: int = 50,
) -> list[ManagedOperation]:
    expire_stale_operations(db, identity)
    query = _owned_query(owner_ids(db, identity))
    if operation_status:
        query = query.where(ManagedOperation.status == operation_status)
    if operation_type:
        query = query.where(ManagedOperation.operation_type == operation_type)
    return list(db.scalars(query.order_by(ManagedOperation.created_at.desc()).limit(limit)))


def expire_stale_operations(db: Session, identity: AuthenticatedIdentity) -> None:
    now = utc_now()
    queued_cutoff = now - timedelta(minutes=10)
    running_cutoff = now - timedelta(hours=1)
    for operation in db.scalars(
        _owned_query(owner_ids(db, identity)).where(
            ManagedOperation.status.in_(("queued", "running"))
        )
    ):
        updated_at = _utc(operation.updated_at)
        started_at = _utc(operation.started_at) if operation.started_at else updated_at
        stale = (
            operation.status == "queued" and updated_at < queued_cutoff
        ) or (
            operation.status == "running"
            and started_at < running_cutoff
        )
        if not stale:
            continue
        operation.status = "failed"
        operation.error_code = "execution_interrupted"
        operation.error_message = "The server stopped tracking this operation. Retry it to continue safely."
        operation.progress_message = "Interrupted"
        operation.completed_at = now

    retry_payload_cutoff = now - timedelta(days=7)
    for operation in db.scalars(
        _owned_query(owner_ids(db, identity)).where(
            ManagedOperation.status.in_(("failed", "cancelled"))
        )
    ):
        completed_at = _utc(operation.completed_at) if operation.completed_at else _utc(operation.updated_at)
        if completed_at >= retry_payload_cutoff or not operation.request_payload:
            continue
        operation.request_payload = {}
        operation.max_attempts = operation.attempt_count
        operation.error_message = "This operation's retry window expired. Start a new operation."
    db.flush()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def summarize_operations(db: Session, identity: AuthenticatedIdentity) -> dict:
    operations = list_operations(db, identity, limit=250)
    statuses = Counter(operation.status for operation in operations)
    provider_failures = Counter(
        operation.provider or "internal"
        for operation in operations
        if operation.status == "failed"
    )
    return {
        "queued": statuses["queued"],
        "running": statuses["running"],
        "succeeded": statuses["succeeded"],
        "failed": statuses["failed"],
        "cancelled": statuses["cancelled"],
        "provider_failures": dict(provider_failures),
    }


def request_cancel(operation: ManagedOperation) -> None:
    now = utc_now()
    operation.cancel_requested_at = now
    if operation.status == "queued":
        operation.status = "cancelled"
        operation.progress_message = "Cancelled before execution"
        operation.completed_at = now


def queue_retry(operation: ManagedOperation) -> None:
    operation.status = "queued"
    operation.progress_current = 0
    operation.progress_message = "Waiting to retry"
    operation.result_payload = None
    operation.error_code = None
    operation.error_message = None
    operation.cancel_requested_at = None
    operation.started_at = None
    operation.completed_at = None
