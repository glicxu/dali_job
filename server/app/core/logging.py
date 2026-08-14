from __future__ import annotations

import json
import logging
import os
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import RuntimeConfig

REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="-")

NOISY_TRANSPORT_LOGGERS = (
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpx",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": REQUEST_ID.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _file_handler(path: Path, runtime: RuntimeConfig) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=runtime.log_max_bytes,
        backupCount=runtime.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    return handler


def configure_logging(runtime: RuntimeConfig) -> None:
    numeric_level = getattr(logging, runtime.log_level.upper(), logging.INFO)
    log_dir = Path(runtime.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        log_dir.chmod(0o700)
    except OSError:
        pass

    root = logging.getLogger()
    root.setLevel(numeric_level)
    for handler in list(root.handlers):
        if getattr(handler, "_dalijob_handler", False):
            root.removeHandler(handler)
            handler.close()

    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter())
    console._dalijob_handler = True  # type: ignore[attr-defined]
    api_file = _file_handler(log_dir / "api.log", runtime)
    api_file._dalijob_handler = True  # type: ignore[attr-defined]
    root.addHandler(console)
    root.addHandler(api_file)

    # A global DEBUG level is useful for DaliJob, but HTTP clients emit several
    # connection lifecycle records per provider request at that level.
    for logger_name in NOISY_TRANSPORT_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    alerts = logging.getLogger("dalijob.alerts")
    alerts.setLevel(logging.WARNING)
    alerts.propagate = False
    for handler in list(alerts.handlers):
        handler.close()
        alerts.removeHandler(handler)
    alerts.addHandler(_file_handler(log_dir / "alerts.log", runtime))
    try:
        os.chmod(log_dir / "api.log", 0o600)
        os.chmod(log_dir / "alerts.log", 0o600)
    except OSError:
        pass


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "").strip()[:128] or uuid4().hex
        token = REQUEST_ID.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logging.getLogger("dalijob.request").info(
                "request method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            if response.status_code >= 500:
                logging.getLogger("dalijob.alerts").error(
                    "http_5xx method=%s path=%s status=%s duration_ms=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logging.getLogger("dalijob.alerts").exception(
                "unhandled_request_error method=%s path=%s",
                request.method,
                request.url.path,
            )
            raise
        finally:
            REQUEST_ID.reset(token)
