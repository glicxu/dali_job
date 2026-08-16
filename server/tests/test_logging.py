from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.main import create_app
from app.modules.matching_v2.diagnostics import (
    begin_matching_prompt_trace,
    end_matching_prompt_trace,
    record_model_request,
)


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


def test_full_matching_prompt_debug_is_opt_in_and_trace_scoped(tmp_path: Path) -> None:
    runtime = load_runtime_config()
    runtime = replace(
        runtime,
        log_dir=str(tmp_path),
        matching_v2=replace(runtime.matching_v2, prompt_debug_enabled=True),
    )
    configure_logging(runtime)
    payload = {
        "stage": "qualification",
        "model": "gpt-5.6-luna",
        "system_prompt": "system secret",
        "user_prompt": "candidate and job context",
        "response_format": {"type": "json_schema"},
    }

    record_model_request(**payload)
    token = begin_matching_prompt_trace()
    try:
        record_model_request(**payload)
    finally:
        end_matching_prompt_trace(token)
    for handler in logging.getLogger("dalijob.matching_prompt_debug").handlers:
        handler.flush()

    records = [
        json.loads(line)
        for line in (tmp_path / "matching_prompt_debug.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["messages"][0]["content"] == "system secret"
    assert records[0]["messages"][1]["content"] == "candidate and job context"
