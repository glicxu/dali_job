from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
import json
import logging
from typing import Any

from app.core.logging import REQUEST_ID


LOGGER = logging.getLogger("dalijob.matching_prompt_debug")
LOGGER.propagate = False
TRACE_ACTIVE: ContextVar[bool] = ContextVar("matching_prompt_trace_active", default=False)


def begin_matching_prompt_trace() -> Token[bool]:
    return TRACE_ACTIVE.set(True)


def end_matching_prompt_trace(token: Token[bool]) -> None:
    TRACE_ACTIVE.reset(token)


def record_model_request(
    *,
    stage: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_format: dict[str, Any],
) -> None:
    _record({
        "event": "model_request",
        "stage": stage,
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": response_format,
    })


def record_model_response(
    *,
    stage: str,
    model: str,
    provider_response_id: str | None,
    content: str | None,
) -> None:
    _record({
        "event": "model_response",
        "stage": stage,
        "model": model,
        "provider_response_id": provider_response_id,
        "content": content,
    })


def record_model_error(*, stage: str, model: str, error: Exception) -> None:
    _record({
        "event": "model_error",
        "stage": stage,
        "model": model,
        "error_type": type(error).__name__,
        "error": str(error),
    })


def record_validation_error(*, stage: str, model: str, error: Exception) -> None:
    _record({
        "event": "validation_error",
        "stage": stage,
        "model": model,
        "error_type": type(error).__name__,
        "error": str(error),
    })


def _record(payload: dict[str, Any]) -> None:
    if not TRACE_ACTIVE.get() or not LOGGER.handlers or not LOGGER.isEnabledFor(logging.INFO):
        return
    LOGGER.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": REQUEST_ID.get(),
        **payload,
    }, ensure_ascii=False, separators=(",", ":")))
