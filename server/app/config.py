from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from DaliCommonLib.dali_config import ProcessConfig

LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5010
DEFAULT_LOG_LEVEL = "info"
DEFAULT_ENV_NAME = "local"
DEFAULT_CLIENT_ORIGIN = "http://localhost:3000"
DEFAULT_CLIENT_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
CONFIG_ENV_VAR = "DALIJOB_CONFIG"
SERVER_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class RuntimeConfig:
    config_path: Optional[str]
    env_name: str
    host: str
    port: int
    log_level: str
    client_origins: list[str]
    client_origin_regex: str
    openai_model: str
    auth_mode: str


def _load_process_config(config_path: Optional[str]) -> Optional[str]:
    load_dotenv(SERVER_ENV_FILE)

    resolved = config_path or os.getenv(CONFIG_ENV_VAR, "").strip() or None
    if not resolved:
        return None

    expanded = str(Path(resolved).expanduser().resolve())
    ok = ProcessConfig.load_config(expanded)
    if not ok:
        raise RuntimeError(f"Failed to load config: {expanded}")
    return expanded


def read_config_value(section: str, key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        sections = ProcessConfig.sections() or []
        if section not in sections:
            return default
        value = ProcessConfig.get_section_config_with_default(section, key, default)
    except Exception:
        LOGGER.debug("ProcessConfig lookup failed for %s.%s", section, key, exc_info=True)
        return default
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _coerce_int(value: Optional[str], default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid integer value '%s'; using %s", value, default)
        return default


def _split_csv(value: Optional[str], default: list[str]) -> list[str]:
    if not value:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def load_runtime_config(config_path: Optional[str] = None) -> RuntimeConfig:
    loaded_path = _load_process_config(config_path)

    host = (
        os.getenv("DALIJOB_HOST", "").strip()
        or read_config_value("dali_job", "host", DEFAULT_HOST)
        or DEFAULT_HOST
    )
    port_value = (
        os.getenv("DALIJOB_PORT", "").strip()
        or read_config_value("dali_job", "port", str(DEFAULT_PORT))
    )
    log_level = (
        os.getenv("DALIJOB_LOG_LEVEL", "").strip()
        or read_config_value("dali_job", "log_level", DEFAULT_LOG_LEVEL)
        or DEFAULT_LOG_LEVEL
    )
    env_name = (
        os.getenv("DALIJOB_ENV", "").strip()
        or read_config_value("dali_job", "env", DEFAULT_ENV_NAME)
        or DEFAULT_ENV_NAME
    )
    client_origins = _split_csv(
        os.getenv("DALIJOB_CLIENT_ORIGINS", "").strip()
        or read_config_value("dali_job", "client_origins", DEFAULT_CLIENT_ORIGIN),
        [DEFAULT_CLIENT_ORIGIN],
    )
    client_origin_regex = (
        os.getenv("DALIJOB_CLIENT_ORIGIN_REGEX", "").strip()
        or read_config_value("dali_job", "client_origin_regex", DEFAULT_CLIENT_ORIGIN_REGEX)
        or DEFAULT_CLIENT_ORIGIN_REGEX
    )
    openai_model = (
        os.getenv("DALIJOB_OPENAI_MODEL", "").strip()
        or read_config_value("openai", "model", "gpt-4.1-mini")
        or "gpt-4.1-mini"
    )
    auth_mode = (
        os.getenv("DALIJOB_AUTH_MODE", "").strip()
        or read_config_value("dali_job", "auth_mode", "dev")
        or "dev"
    )

    return RuntimeConfig(
        config_path=loaded_path,
        env_name=env_name,
        host=host,
        port=_coerce_int(port_value, DEFAULT_PORT),
        log_level=log_level.lower(),
        client_origins=client_origins,
        client_origin_regex=client_origin_regex,
        openai_model=openai_model,
        auth_mode=auth_mode.lower(),
    )
