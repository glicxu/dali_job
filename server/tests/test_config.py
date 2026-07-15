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


def test_production_local_auth_requires_non_default_secret(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ENV", "production")
    monkeypatch.setenv("DALIJOB_AUTH_MODE", "local")
    monkeypatch.setenv("DALIJOB_JWT_SECRET", "")

    with pytest.raises(RuntimeError, match="DALIJOB_JWT_SECRET"):
        load_runtime_config()


def test_production_accepts_local_auth_with_secret(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ENV", "production")
    monkeypatch.setenv("DALIJOB_AUTH_MODE", "local")
    monkeypatch.setenv("DALIJOB_JWT_SECRET", "production-test-secret-with-at-least-32-characters")

    runtime = load_runtime_config()

    assert runtime.auth_mode == "local"


def test_provider_limits_can_be_configured_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_PROVIDER_USER_LIMIT_PER_MINUTE", "7")
    monkeypatch.setenv("DALIJOB_PROVIDER_IP_LIMIT_PER_MINUTE", "15")

    runtime = load_runtime_config()

    assert runtime.provider_user_limit_per_minute == 7
    assert runtime.provider_ip_limit_per_minute == 15
