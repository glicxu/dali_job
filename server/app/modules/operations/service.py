from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.accounts.models import User
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.operations.models import ManagedOperation, utc_now

LOGGER = logging.getLogger(__name__)


class OperationCancelled(RuntimeError):
    pass


class OperationHandler(Protocol):
    def __call__(
        self,
        db: Session,
        identity: AuthenticatedIdentity,
        payload: dict,
        context: "OperationContext",
    ) -> dict | list:
        ...


@dataclass
class OperationContext:
    db: Session
    operation: ManagedOperation

    def update(
        self,
        current: int,
        *,
        total: int | None = None,
        message: str | None = None,
        usage: dict | None = None,
    ) -> None:
        self.db.refresh(self.operation)
        if self.operation.cancel_requested_at is not None:
            raise OperationCancelled("Operation cancelled by the user.")
        self.operation.progress_current = max(current, 0)
        if total is not None:
            self.operation.progress_total = max(total, 0)
        if message is not None:
            self.operation.progress_message = message[:255]
        if usage is not None:
            self.operation.usage = usage
        self.db.commit()

    def check_cancelled(self) -> None:
        self.update(self.operation.progress_current)


def session_factory_for(db: Session) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def _identity_for_operation(db: Session, operation: ManagedOperation) -> AuthenticatedIdentity:
    user = db.scalar(select(User).where(User.id == operation.user_id))
    if user is None or not user.is_active:
        raise RuntimeError("The operation owner is unavailable.")
    return AuthenticatedIdentity(
        external_user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        provider=user.auth_provider,
    )


def _safe_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str) and detail.strip():
            return f"http_{exc.status_code}", detail[:2000]
        return f"http_{exc.status_code}", "The operation could not be completed."
    if isinstance(exc, OperationCancelled):
        return "cancelled", str(exc)
    return "operation_failed", "The operation failed. Retry it, or use the available manual workflow."


def execute_operation(
    session_factory: Callable[[], Session],
    operation_id: int,
    handlers: dict[str, OperationHandler],
) -> None:
    with session_factory() as db:
        operation = db.scalar(
            select(ManagedOperation).where(ManagedOperation.id == operation_id).with_for_update()
        )
        if operation is None or operation.status != "queued":
            return
        if operation.attempt_count >= operation.max_attempts:
            operation.status = "failed"
            operation.error_code = "retry_limit_reached"
            operation.error_message = "This operation reached its retry limit. Start a new operation."
            operation.completed_at = utc_now()
            db.commit()
            return
        if operation.cancel_requested_at is not None:
            operation.status = "cancelled"
            operation.completed_at = utc_now()
            db.commit()
            return

        handler = handlers.get(operation.operation_type)
        if handler is None:
            operation.status = "failed"
            operation.error_code = "unsupported_operation"
            operation.error_message = "This operation type is no longer supported."
            operation.completed_at = utc_now()
            db.commit()
            return

        operation.status = "running"
        operation.attempt_count += 1
        operation.started_at = utc_now()
        operation.progress_message = "Running"
        db.commit()

        context = OperationContext(db=db, operation=operation)
        started_monotonic = time.monotonic()
        try:
            identity = _identity_for_operation(db, operation)
            result = handler(db, identity, dict(operation.request_payload or {}), context)
            db.refresh(operation)
            if operation.cancel_requested_at is not None:
                raise OperationCancelled("Operation cancelled by the user.")
            operation.result_payload = result
            operation.request_payload = {}
            operation.status = "succeeded"
            if operation.progress_total is not None:
                operation.progress_current = operation.progress_total
            elif operation.progress_current == 0:
                operation.progress_current = 1
                operation.progress_total = 1
            operation.progress_message = "Completed"
            operation.completed_at = utc_now()
            operation.error_code = None
            operation.error_message = None
            operation.usage = {
                **dict(operation.usage or {}),
                "duration_ms": round((time.monotonic() - started_monotonic) * 1000),
            }
            db.commit()
        except Exception as exc:
            db.rollback()
            operation = db.get(ManagedOperation, operation_id)
            if operation is None:
                return
            error_code, error_message = _safe_error(exc)
            operation.status = "cancelled" if isinstance(exc, OperationCancelled) else "failed"
            operation.error_code = error_code
            operation.error_message = error_message
            operation.progress_message = "Cancelled" if isinstance(exc, OperationCancelled) else "Failed"
            operation.completed_at = utc_now()
            operation.usage = {
                **dict(operation.usage or {}),
                "duration_ms": round((time.monotonic() - started_monotonic) * 1000),
            }
            db.commit()
            if not isinstance(exc, OperationCancelled):
                LOGGER.error(
                    "managed_operation_failed id=%s type=%s attempt=%s exception_type=%s",
                    operation.id,
                    operation.operation_type,
                    operation.attempt_count,
                    type(exc).__name__,
                )
