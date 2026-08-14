from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.main import create_app


def test_structured_logs_and_alerts_are_written_to_rotating_files(tmp_path: Path) -> None:
    runtime = replace(load_runtime_config(), log_dir=str(tmp_path), log_max_bytes=4096, log_backup_count=2)
    configure_logging(runtime)

    logging.getLogger("dalijob.test").info("test api record")
    logging.getLogger("dalijob.alerts").warning("test alert record")
    for logger_name in ("", "dalijob.alerts"):
        for handler in logging.getLogger(logger_name).handlers:
            handler.flush()

    api_record = json.loads((tmp_path / "api.log").read_text(encoding="utf-8").splitlines()[-1])
    alert_record = json.loads((tmp_path / "alerts.log").read_text(encoding="utf-8").splitlines()[-1])
    assert api_record["message"] == "test api record"
    assert api_record["request_id"] == "-"
    assert alert_record["message"] == "test alert record"


def test_request_logging_returns_correlation_id() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health", headers={"X-Request-ID": "release-smoke-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "release-smoke-123"


def test_http_transport_debug_logs_are_suppressed(tmp_path: Path) -> None:
    runtime = replace(load_runtime_config(), log_dir=str(tmp_path), log_level="debug")
    configure_logging(runtime)

    logging.getLogger("httpcore.connection").debug("close.started")
    logging.getLogger("httpx").debug("request details")
    logging.getLogger("dalijob.test").debug("application details")
    for handler in logging.getLogger().handlers:
        handler.flush()

    messages = [
        json.loads(line)["message"]
        for line in (tmp_path / "api.log").read_text(encoding="utf-8").splitlines()
    ]
    assert "close.started" not in messages
    assert "request details" not in messages
    assert "application details" in messages
