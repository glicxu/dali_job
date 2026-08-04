from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from DaliCommonLib.dali_config import ProcessConfig

LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5010
DEFAULT_LOG_LEVEL = "info"
DEFAULT_ENV_NAME = "local"
DEFAULT_CLIENT_ORIGIN = "http://localhost:3000"
DEFAULT_CLIENT_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
DEFAULT_PROVIDER_USER_LIMIT_PER_MINUTE = 20
DEFAULT_PROVIDER_IP_LIMIT_PER_MINUTE = 60
DEFAULT_AUTH_LOGIN_IP_LIMIT = 30
DEFAULT_AUTH_LOGIN_ACCOUNT_LIMIT = 10
DEFAULT_AUTH_LOGIN_WINDOW_SECONDS = 300
DEFAULT_AUTH_REGISTER_IP_LIMIT = 10
DEFAULT_AUTH_REGISTER_ACCOUNT_LIMIT = 5
DEFAULT_AUTH_REGISTER_WINDOW_SECONDS = 3600
DEFAULT_SESSION_IDLE_SECONDS = 60 * 60 * 12
DEFAULT_SESSION_ABSOLUTE_SECONDS = 60 * 60 * 24 * 7
DEFAULT_EMAIL_ACTION_TTL_SECONDS = 60 * 60
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5
CONFIG_ENV_VAR = "DALIJOB_CONFIG"
SERVER_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
PRODUCTION_ENV_NAMES = {"prod", "production"}
SUPPORTED_AUTH_MODES = {"dev", "disabled", "local"}


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
    ask_scout_model: str
    auth_mode: str
    document_storage_dir: str
    provider_user_limit_per_minute: int
    provider_ip_limit_per_minute: int
    auth_login_ip_limit: int
    auth_login_account_limit: int
    auth_login_window_seconds: int
    auth_register_ip_limit: int
    auth_register_account_limit: int
    auth_register_window_seconds: int
    session_idle_seconds: int
    session_absolute_seconds: int
    email_action_ttl_seconds: int
    public_client_url: str
    email_delivery_mode: str
    email_from_address: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_use_tls: bool
    email_outbox_dir: str
    log_dir: str
    log_max_bytes: int
    log_backup_count: int
    audit_retention_days: int


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


def _coerce_bool(value: Optional[str], default: bool) -> bool:
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: Optional[str], default: list[str]) -> list[str]:
    if not value:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def _validate_runtime_config(runtime: RuntimeConfig) -> None:
    if runtime.auth_mode not in SUPPORTED_AUTH_MODES:
        raise RuntimeError(f"Unsupported DaliJob auth mode: {runtime.auth_mode}")
    if runtime.env_name.lower() not in PRODUCTION_ENV_NAMES:
        return
    if runtime.auth_mode in {"dev", "disabled"}:
        raise RuntimeError("Production DaliJob must use local authentication; dev and disabled auth are not allowed.")
    if runtime.client_origin_regex:
        raise RuntimeError("Production DaliJob must not enable a client origin regex.")
    for origin in runtime.client_origins:
        parsed = urlparse(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
        ):
            raise RuntimeError("Production DaliJob client origins must be exact public HTTPS origins.")
    if runtime.email_delivery_mode != "smtp" or not runtime.smtp_host or not runtime.email_from_address:
        raise RuntimeError("Production DaliJob requires configured SMTP email delivery and a from address.")
    public_url = urlparse(runtime.public_client_url)
    if public_url.scheme != "https" or not public_url.hostname:
        raise RuntimeError("Production DaliJob requires a public HTTPS client URL for account emails.")
    if runtime.session_idle_seconds > runtime.session_absolute_seconds:
        raise RuntimeError("Session idle lifetime cannot exceed its absolute lifetime.")


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
    if env_name.lower() in PRODUCTION_ENV_NAMES:
        client_origin_regex = ""
    openai_model = (
        os.getenv("DALIJOB_OPENAI_MODEL", "").strip()
        or read_config_value("openai", "model", "gpt-4.1-mini")
        or "gpt-4.1-mini"
    )
    ask_scout_model = (
        os.getenv("DALIJOB_ASK_SCOUT_MODEL", "").strip()
        or read_config_value("ask_scout", "model", "gpt-5.6-luna")
        or "gpt-5.6-luna"
    )
    auth_mode = (
        os.getenv("DALIJOB_AUTH_MODE", "").strip()
        or read_config_value("dali_job", "auth_mode", "dev")
        or "dev"
    )
    document_storage_dir = (
        os.getenv("DALIJOB_DOCUMENT_STORAGE_DIR", "").strip()
        or read_config_value("documents", "storage_dir", "")
        or str(Path(__file__).resolve().parents[1] / "storage" / "documents")
    )
    provider_user_limit = _coerce_int(
        os.getenv("DALIJOB_PROVIDER_USER_LIMIT_PER_MINUTE", "").strip()
        or read_config_value(
            "provider_limits",
            "user_per_minute",
            str(DEFAULT_PROVIDER_USER_LIMIT_PER_MINUTE),
        ),
        DEFAULT_PROVIDER_USER_LIMIT_PER_MINUTE,
    )
    provider_ip_limit = _coerce_int(
        os.getenv("DALIJOB_PROVIDER_IP_LIMIT_PER_MINUTE", "").strip()
        or read_config_value(
            "provider_limits",
            "ip_per_minute",
            str(DEFAULT_PROVIDER_IP_LIMIT_PER_MINUTE),
        ),
        DEFAULT_PROVIDER_IP_LIMIT_PER_MINUTE,
    )
    auth_login_ip_limit = _coerce_int(
        os.getenv("DALIJOB_AUTH_LOGIN_IP_LIMIT", "").strip()
        or read_config_value("auth_limits", "login_ip", str(DEFAULT_AUTH_LOGIN_IP_LIMIT)),
        DEFAULT_AUTH_LOGIN_IP_LIMIT,
    )
    auth_login_account_limit = _coerce_int(
        os.getenv("DALIJOB_AUTH_LOGIN_ACCOUNT_LIMIT", "").strip()
        or read_config_value("auth_limits", "login_account", str(DEFAULT_AUTH_LOGIN_ACCOUNT_LIMIT)),
        DEFAULT_AUTH_LOGIN_ACCOUNT_LIMIT,
    )
    auth_login_window_seconds = _coerce_int(
        os.getenv("DALIJOB_AUTH_LOGIN_WINDOW_SECONDS", "").strip()
        or read_config_value("auth_limits", "login_window_seconds", str(DEFAULT_AUTH_LOGIN_WINDOW_SECONDS)),
        DEFAULT_AUTH_LOGIN_WINDOW_SECONDS,
    )
    auth_register_ip_limit = _coerce_int(
        os.getenv("DALIJOB_AUTH_REGISTER_IP_LIMIT", "").strip()
        or read_config_value("auth_limits", "register_ip", str(DEFAULT_AUTH_REGISTER_IP_LIMIT)),
        DEFAULT_AUTH_REGISTER_IP_LIMIT,
    )
    auth_register_account_limit = _coerce_int(
        os.getenv("DALIJOB_AUTH_REGISTER_ACCOUNT_LIMIT", "").strip()
        or read_config_value("auth_limits", "register_account", str(DEFAULT_AUTH_REGISTER_ACCOUNT_LIMIT)),
        DEFAULT_AUTH_REGISTER_ACCOUNT_LIMIT,
    )
    auth_register_window_seconds = _coerce_int(
        os.getenv("DALIJOB_AUTH_REGISTER_WINDOW_SECONDS", "").strip()
        or read_config_value(
            "auth_limits",
            "register_window_seconds",
            str(DEFAULT_AUTH_REGISTER_WINDOW_SECONDS),
        ),
        DEFAULT_AUTH_REGISTER_WINDOW_SECONDS,
    )
    session_idle_seconds = _coerce_int(
        read_config_value("dali_job_auth", "session_idle_seconds", str(DEFAULT_SESSION_IDLE_SECONDS)),
        DEFAULT_SESSION_IDLE_SECONDS,
    )
    session_absolute_seconds = _coerce_int(
        read_config_value("dali_job_auth", "session_absolute_seconds", str(DEFAULT_SESSION_ABSOLUTE_SECONDS)),
        DEFAULT_SESSION_ABSOLUTE_SECONDS,
    )
    email_action_ttl_seconds = _coerce_int(
        read_config_value("dali_job_auth", "email_action_ttl_seconds", str(DEFAULT_EMAIL_ACTION_TTL_SECONDS)),
        DEFAULT_EMAIL_ACTION_TTL_SECONDS,
    )
    public_client_url = (
        os.getenv("DALIJOB_PUBLIC_CLIENT_URL", "").strip()
        or read_config_value("dali_job", "public_client_url", client_origins[0])
        or client_origins[0]
    ).rstrip("/")
    email_delivery_mode = (
        os.getenv("DALIJOB_EMAIL_DELIVERY_MODE", "").strip()
        or read_config_value("email", "delivery_mode", "file")
        or "file"
    ).lower()
    email_from_address = (
        os.getenv("DALIJOB_EMAIL_FROM", "").strip()
        or read_config_value("email", "from_address", "no-reply@dalijob.local")
        or "no-reply@dalijob.local"
    )
    smtp_host = os.getenv("DALIJOB_SMTP_HOST", "").strip() or read_config_value("email", "smtp_host", "") or ""
    smtp_port = _coerce_int(
        os.getenv("DALIJOB_SMTP_PORT", "").strip() or read_config_value("email", "smtp_port", "587"),
        587,
    )
    smtp_username = (
        os.getenv("DALIJOB_SMTP_USERNAME", "").strip()
        or read_config_value("email", "smtp_username", "")
        or ""
    )
    smtp_use_tls = _coerce_bool(read_config_value("email", "smtp_use_tls", "true"), True)
    email_outbox_dir = (
        read_config_value("email", "outbox_dir", "")
        or str(Path(__file__).resolve().parents[1] / "storage" / "email_outbox")
    )
    log_dir = read_config_value("logging", "directory", "") or str(Path(__file__).resolve().parents[1] / "logs")
    log_max_bytes = _coerce_int(
        read_config_value("logging", "max_bytes", str(DEFAULT_LOG_MAX_BYTES)),
        DEFAULT_LOG_MAX_BYTES,
    )
    log_backup_count = _coerce_int(
        read_config_value("logging", "backup_count", str(DEFAULT_LOG_BACKUP_COUNT)),
        DEFAULT_LOG_BACKUP_COUNT,
    )
    audit_retention_days = _coerce_int(read_config_value("audit", "retention_days", "365"), 365)

    runtime = RuntimeConfig(
        config_path=loaded_path,
        env_name=env_name,
        host=host,
        port=_coerce_int(port_value, DEFAULT_PORT),
        log_level=log_level.lower(),
        client_origins=client_origins,
        client_origin_regex=client_origin_regex,
        openai_model=openai_model,
        ask_scout_model=ask_scout_model,
        auth_mode=auth_mode.lower(),
        document_storage_dir=str(Path(document_storage_dir).expanduser().resolve()),
        provider_user_limit_per_minute=max(provider_user_limit, 1),
        provider_ip_limit_per_minute=max(provider_ip_limit, 1),
        auth_login_ip_limit=max(auth_login_ip_limit, 1),
        auth_login_account_limit=max(auth_login_account_limit, 1),
        auth_login_window_seconds=max(auth_login_window_seconds, 1),
        auth_register_ip_limit=max(auth_register_ip_limit, 1),
        auth_register_account_limit=max(auth_register_account_limit, 1),
        auth_register_window_seconds=max(auth_register_window_seconds, 1),
        session_idle_seconds=max(session_idle_seconds, 60),
        session_absolute_seconds=max(session_absolute_seconds, 300),
        email_action_ttl_seconds=max(email_action_ttl_seconds, 300),
        public_client_url=public_client_url,
        email_delivery_mode=email_delivery_mode,
        email_from_address=email_from_address,
        smtp_host=smtp_host,
        smtp_port=max(smtp_port, 1),
        smtp_username=smtp_username,
        smtp_use_tls=smtp_use_tls,
        email_outbox_dir=str(Path(email_outbox_dir).expanduser().resolve()),
        log_dir=str(Path(log_dir).expanduser().resolve()),
        log_max_bytes=max(log_max_bytes, 1024),
        log_backup_count=max(log_backup_count, 1),
        audit_retention_days=max(audit_retention_days, 1),
    )
    _validate_runtime_config(runtime)
    return runtime
