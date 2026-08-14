from __future__ import annotations

import pytest

import app.config as config_module
from app.config import SERVER_ENV_FILE, load_runtime_config


def test_server_env_file_points_to_server_directory() -> None:
    assert SERVER_ENV_FILE.name == ".env"
    assert SERVER_ENV_FILE.parent.name == "server"


def test_default_auth_mode_is_dev() -> None:
    runtime = load_runtime_config()

    assert runtime.auth_mode == "dev"


@pytest.mark.parametrize("auth_mode", ["dev", "disabled"])
def test_production_rejects_unsafe_auth_modes(monkeypatch, auth_mode: str) -> None:
    monkeypatch.setenv("DALIJOB_ENV", "production")
    monkeypatch.setenv("DALIJOB_AUTH_MODE", auth_mode)

    with pytest.raises(RuntimeError, match="Production DaliJob must use local authentication"):
        load_runtime_config()


def _configure_production(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ENV", "production")
    monkeypatch.setenv("DALIJOB_AUTH_MODE", "local")
    monkeypatch.setenv("DALIJOB_CLIENT_ORIGINS", "https://jobmatch.dalifin.com")
    monkeypatch.setenv("DALIJOB_PUBLIC_CLIENT_URL", "https://jobmatch.dalifin.com")
    monkeypatch.setenv("DALIJOB_EMAIL_DELIVERY_MODE", "smtp")
    monkeypatch.setenv("DALIJOB_EMAIL_FROM", "no-reply@dalifin.com")
    monkeypatch.setenv("DALIJOB_SMTP_HOST", "smtp.example.com")


def test_production_local_auth_requires_smtp(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ENV", "production")
    monkeypatch.setenv("DALIJOB_AUTH_MODE", "local")
    monkeypatch.setenv("DALIJOB_CLIENT_ORIGINS", "https://jobmatch.dalifin.com")
    monkeypatch.setenv("DALIJOB_PUBLIC_CLIENT_URL", "https://jobmatch.dalifin.com")
    monkeypatch.setenv("DALIJOB_EMAIL_DELIVERY_MODE", "file")

    with pytest.raises(RuntimeError, match="SMTP"):
        load_runtime_config()


def test_production_accepts_local_auth_with_email_delivery(monkeypatch) -> None:
    _configure_production(monkeypatch)

    runtime = load_runtime_config()

    assert runtime.auth_mode == "local"
    assert runtime.client_origin_regex == ""


def test_production_rejects_localhost_client_origin(monkeypatch) -> None:
    _configure_production(monkeypatch)
    monkeypatch.setenv("DALIJOB_CLIENT_ORIGINS", "http://localhost:3000")

    with pytest.raises(RuntimeError, match="exact public HTTPS origins"):
        load_runtime_config()


def test_provider_limits_can_be_configured_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_PROVIDER_USER_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("DALIJOB_PROVIDER_IP_LIMIT_PER_MINUTE", "15")

    runtime = load_runtime_config()

    assert runtime.provider_user_limit_per_minute == 7
    assert runtime.provider_ip_limit_per_minute == 15


def test_ask_scout_model_has_an_independent_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_OPENAI_MODEL", "general-model")
    monkeypatch.setenv("DALIJOB_ASK_SCOUT_MODEL", "scout-model")

    runtime = load_runtime_config()

    assert runtime.openai_model == "general-model"
    assert runtime.ask_scout_model == "scout-model"


def test_auth_limits_can_be_configured_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_AUTH_LOGIN_IP_LIMIT", "12")
    monkeypatch.setenv("DALIJOB_AUTH_LOGIN_ACCOUNT_LIMIT", "4")
    monkeypatch.setenv("DALIJOB_AUTH_LOGIN_WINDOW_SECONDS", "90")
    monkeypatch.setenv("DALIJOB_AUTH_REGISTER_IP_LIMIT", "6")
    monkeypatch.setenv("DALIJOB_AUTH_REGISTER_ACCOUNT_LIMIT", "2")
    monkeypatch.setenv("DALIJOB_AUTH_REGISTER_WINDOW_SECONDS", "600")

    runtime = load_runtime_config()

    assert runtime.auth_login_ip_limit == 12
    assert runtime.auth_login_account_limit == 4
    assert runtime.auth_login_window_seconds == 90
    assert runtime.auth_register_ip_limit == 6
    assert runtime.auth_register_account_limit == 2
    assert runtime.auth_register_window_seconds == 600


def test_imported_shared_smtp_config_enables_email_delivery(monkeypatch) -> None:
    shared_values = {
        ("smtp", "smtp_server"): "dalifin-com-smtp.dynu.com",
        ("smtp", "port"): "587",
        ("smtp", "sender_email"): "report@dalifin.com",
        ("smtp", "login"): "shared-login",
        ("smtp", "password"): "shared-password",
    }
    monkeypatch.setattr(
        config_module,
        "read_config_value",
        lambda section, key, default=None: shared_values.get((section, key), default),
    )
    for key in (
        "DALIJOB_EMAIL_DELIVERY_MODE",
        "DALIJOB_EMAIL_FROM",
        "DALIJOB_SMTP_HOST",
        "DALIJOB_SMTP_PORT",
        "DALIJOB_SMTP_USERNAME",
        "DALIJOB_SMTP_PASSWORD",
        "DALIJOB_SMTP_USE_TLS",
    ):
        monkeypatch.delenv(key, raising=False)

    runtime = load_runtime_config()

    assert runtime.email_delivery_mode == "smtp"
    assert runtime.email_from_address == "report@dalifin.com"
    assert runtime.smtp_host == "dalifin-com-smtp.dynu.com"
    assert runtime.smtp_port == 587
    assert runtime.smtp_username == "shared-login"
    assert runtime.smtp_password == "shared-password"
    assert runtime.smtp_use_tls is True


def test_dalijob_email_environment_overrides_shared_smtp(monkeypatch) -> None:
    shared_values = {
        ("smtp", "smtp_server"): "shared.example.com",
        ("smtp", "port"): "587",
        ("smtp", "sender_email"): "shared@example.com",
        ("smtp", "login"): "shared-login",
        ("smtp", "password"): "shared-password",
    }
    monkeypatch.setattr(
        config_module,
        "read_config_value",
        lambda section, key, default=None: shared_values.get((section, key), default),
    )
    monkeypatch.setenv("DALIJOB_EMAIL_DELIVERY_MODE", "smtp")
    monkeypatch.setenv("DALIJOB_EMAIL_FROM", "DaliJob <no-reply@dalifin.com>")
    monkeypatch.setenv("DALIJOB_SMTP_HOST", "override.example.com")
    monkeypatch.setenv("DALIJOB_SMTP_PORT", "2587")
    monkeypatch.setenv("DALIJOB_SMTP_USERNAME", "override-login")
    monkeypatch.setenv("DALIJOB_SMTP_PASSWORD", "override-password")
    monkeypatch.setenv("DALIJOB_SMTP_USE_TLS", "false")

    runtime = load_runtime_config()

    assert runtime.email_from_address == "DaliJob <no-reply@dalifin.com>"
    assert runtime.smtp_host == "override.example.com"
    assert runtime.smtp_port == 2587
    assert runtime.smtp_username == "override-login"
    assert runtime.smtp_password == "override-password"
    assert runtime.smtp_use_tls is False


def test_plural_dalijob_sections_remain_compatible(monkeypatch) -> None:
    config_values = {
        ("dali_jobs", "env"): "local",
        ("dali_jobs", "host"): "0.0.0.0",
        ("dali_jobs", "port"): "5011",
        ("dali_jobs", "client_origin"): "http://127.0.0.1:3000",
        ("dali_jobs", "auth_mode"): "local",
        ("dali_jobs_auth", "session_idle_seconds"): "7200",
    }
    monkeypatch.setattr(
        config_module,
        "read_config_value",
        lambda section, key, default=None: config_values.get((section, key), default),
    )

    runtime = load_runtime_config()

    assert runtime.env_name == "local"
    assert runtime.host == "0.0.0.0"
    assert runtime.port == 5011
    assert runtime.client_origins == ["http://127.0.0.1:3000"]
    assert runtime.auth_mode == "local"
    assert runtime.session_idle_seconds == 7200
