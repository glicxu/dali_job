from __future__ import annotations

import pytest

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
