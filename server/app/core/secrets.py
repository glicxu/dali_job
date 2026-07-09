from __future__ import annotations

import logging
import os
import json
from functools import lru_cache
from typing import Any

LOGGER = logging.getLogger(__name__)

SECRET_KEY_BY_ENV = {
    "OPENAI_API_KEY": "openai",
    "APIFY_API_TOKEN": "apify",
}


def get_provider_secret(env_name: str) -> str:
    """Resolve provider secrets from DaliSecret first, then environment."""
    db_value = _normalize_secret_value(_get_secret_from_db(SECRET_KEY_BY_ENV.get(env_name, env_name.lower())), env_name)
    if db_value:
        return db_value
    return os.getenv(env_name, "").strip()


@lru_cache(maxsize=16)
def _get_secret_from_db(secret_key: str) -> str:
    try:
        from DaliCommonLib.dali_secret import DaliSecret
    except Exception:
        LOGGER.debug("DaliSecret is unavailable; using environment fallback", exc_info=True)
        return ""

    try:
        value = DaliSecret().get_secret(secret_key, raise_on_missing=False, default="")
    except Exception:
        LOGGER.warning("Could not load secret key '%s' from DaliSecret; using environment fallback", secret_key, exc_info=True)
        return ""
    return str(value or "").strip()


def clear_secret_cache() -> None:
    _get_secret_from_db.cache_clear()


def _normalize_secret_value(value: Any, env_name: str, *, _depth: int = 0) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _depth > 3:
        return text

    if text[0] in {'"', "{", "["}:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(parsed, str):
            return _normalize_secret_value(parsed, env_name, _depth=_depth + 1)
        if isinstance(parsed, dict):
            for key in (env_name, env_name.lower(), "api_key", "token", "credential"):
                candidate = parsed.get(key)
                if candidate:
                    return _normalize_secret_value(candidate, env_name, _depth=_depth + 1)
            if len(parsed) == 1:
                only_value = next(iter(parsed.values()))
                if only_value:
                    return _normalize_secret_value(only_value, env_name, _depth=_depth + 1)
        return ""

    return text
