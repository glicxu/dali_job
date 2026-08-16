from __future__ import annotations

import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\w)")
URL_RE = re.compile(r"\bhttps?://[^\s<>]+", re.IGNORECASE)


def sensitive_categories(text: str) -> list[str]:
    categories = []
    if EMAIL_RE.search(text):
        categories.append("email")
    if PHONE_RE.search(text):
        categories.append("phone")
    if URL_RE.search(text):
        categories.append("url")
    return categories


def redact_candidate_text(text: str) -> str:
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    return URL_RE.sub("[REDACTED_URL]", redacted)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_candidate_text(value)
    if isinstance(value, dict):
        return {key: redact_value(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value
