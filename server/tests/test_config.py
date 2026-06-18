from __future__ import annotations

from app.config import SERVER_ENV_FILE, load_runtime_config


def test_server_env_file_points_to_server_directory() -> None:
    assert SERVER_ENV_FILE.name == ".env"
    assert SERVER_ENV_FILE.parent.name == "server"


def test_default_auth_mode_is_dev() -> None:
    runtime = load_runtime_config()

    assert runtime.auth_mode == "dev"
