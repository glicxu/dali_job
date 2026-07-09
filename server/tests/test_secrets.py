from __future__ import annotations

import sys
import types

from app.core import secrets


def _install_fake_dali_secret(monkeypatch, value: str | None = None, error: Exception | None = None) -> None:
    class FakeDaliSecret:
        def get_secret(self, key, *, raise_on_missing=True, default=None):
            if error is not None:
                raise error
            return value if value is not None else default

    fake_module = types.ModuleType("DaliCommonLib.dali_secret")
    fake_module.DaliSecret = FakeDaliSecret
    package = types.ModuleType("DaliCommonLib")
    monkeypatch.setitem(sys.modules, "DaliCommonLib", package)
    monkeypatch.setitem(sys.modules, "DaliCommonLib.dali_secret", fake_module)
    secrets.clear_secret_cache()


def test_provider_secret_prefers_database(monkeypatch):
    _install_fake_dali_secret(monkeypatch, "db-openai")
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")

    assert secrets.get_provider_secret("OPENAI_API_KEY") == "db-openai"


def test_provider_secret_unwraps_json_string_from_database(monkeypatch):
    _install_fake_dali_secret(monkeypatch, '"apify_api_test"')
    monkeypatch.setenv("APIFY_API_TOKEN", "env-apify")

    assert secrets.get_provider_secret("APIFY_API_TOKEN") == "apify_api_test"


def test_provider_secret_unwraps_nested_json_string_from_database(monkeypatch):
    _install_fake_dali_secret(monkeypatch, '"{\\"OPENAI_API_KEY\\":\\"sk-test\\"}"')
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")

    assert secrets.get_provider_secret("OPENAI_API_KEY") == "sk-test"


def test_provider_secret_extracts_token_from_json_object(monkeypatch):
    _install_fake_dali_secret(monkeypatch, '{"token":"apify_api_test"}')
    monkeypatch.setenv("APIFY_API_TOKEN", "env-apify")

    assert secrets.get_provider_secret("APIFY_API_TOKEN") == "apify_api_test"


def test_provider_secret_falls_back_to_environment_when_missing(monkeypatch):
    _install_fake_dali_secret(monkeypatch, "")
    monkeypatch.setenv("APIFY_API_TOKEN", "env-apify")

    assert secrets.get_provider_secret("APIFY_API_TOKEN") == "env-apify"


def test_provider_secret_falls_back_to_environment_on_db_error(monkeypatch):
    _install_fake_dali_secret(monkeypatch, error=RuntimeError("db unavailable"))
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")

    assert secrets.get_provider_secret("OPENAI_API_KEY") == "env-openai"
