from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REGISTRY_PATH = Path(__file__).with_name("company_job_sources.json")


@lru_cache(maxsize=1)
def load_company_job_sources() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 2:
        raise ValueError("Unsupported company job source registry schema.")
    return registry


def match_company_source(source_url: str) -> dict[str, Any] | None:
    """Resolve an employer record from an allowlisted employer-controlled job URL."""
    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.lower()
    if not hostname:
        return None
    for company in load_company_job_sources()["companies"]:
        hosts = {str(value).lower() for value in company["expected_detail_hosts"]}
        if hostname not in hosts:
            continue
        prefixes = [str(value).lower() for value in company.get("detail_path_prefixes", [])]
        if prefixes and not any(path.startswith(prefix) for prefix in prefixes):
            continue
        return company
    return None


def source_company(source_url: str) -> str:
    company = match_company_source(source_url)
    return str(company["company_name"]) if company is not None else ""


def enabled_e3_companies() -> list[dict[str, Any]]:
    return [
        company
        for company in load_company_job_sources()["companies"]
        if company.get("e3_enabled") is True
    ]
