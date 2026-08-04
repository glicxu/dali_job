from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit


MAX_PREFILL_TEXT = 200
MAX_PREFILL_URL = 2048
MAX_JOB_IDS = 50


@dataclass(frozen=True)
class ScoutActionDefinition:
    action_id: str
    label: str
    path: str
    description: str
    allowed_parameters: tuple[str, ...] = ()


ACTION_CATALOG: dict[str, ScoutActionDefinition] = {
    item.action_id: item
    for item in (
        ScoutActionDefinition("open_home", "Open Home", "/", "Review setup alerts, recent jobs, and best matches."),
        ScoutActionDefinition("open_resume_profiles", "Open Resume Profiles", "/profile", "Upload, parse, and manage resume profiles."),
        ScoutActionDefinition("open_match", "Open Match", "/match", "Compare a resume profile with one or more jobs.", ("job_url", "job_ids", "resume_profile_id")),
        ScoutActionDefinition("open_saved_jobs", "Open Saved Jobs", "/jobs", "Review saved jobs and their match data.", ("job_id", "view")),
        ScoutActionDefinition("open_job_import", "Open Import Job", "/jobs/import-url", "Import one job posting from a URL.", ("job_url",)),
        ScoutActionDefinition("open_manual_job", "Create Job Manually", "/jobs/manual", "Create a job record by entering its details manually."),
        ScoutActionDefinition("open_job_list_import", "Open Import Job List", "/jobs/import", "Discover jobs from a job-list URL.", ("list_url",)),
        ScoutActionDefinition("open_job_search", "Open Job Search", "/jobs/search", "Search for jobs by keyword and location.", ("keyword", "location")),
        ScoutActionDefinition("open_applications", "Open Applications", "/applications", "Review or create tracked applications.", ("application_id",)),
        ScoutActionDefinition("open_application_detail", "View Application", "/applications/{application_id}", "Review and edit one tracked application.", ("application_id",)),
        ScoutActionDefinition("open_materials", "Open Application Materials", "/materials", "Create tailored resumes and cover letters.", ("application_id",)),
        ScoutActionDefinition("open_interviews", "Open Interviews", "/interviews", "Add interviews and prepare for them.", ("application_id", "interview_id")),
        ScoutActionDefinition("open_documents", "Open Documents", "/documents", "Review uploaded and generated documents."),
        ScoutActionDefinition("open_analytics", "Open Analytics", "/analytics", "Review application and job-search analytics."),
        ScoutActionDefinition("open_account", "Open Account", "/auth", "Manage account settings and administrative tools."),
        ScoutActionDefinition("open_operations", "Open Operations", "/operations", "Review background operation progress and failures."),
    )
}

KNOWN_CLIENT_PATHS = {
    "/", "/profile", "/match", "/jobs", "/jobs/import-url", "/jobs/manual",
    "/jobs/import", "/jobs/search", "/applications", "/materials", "/interviews",
    "/documents", "/analytics", "/auth", "/operations", "/ask-scout",
}


def is_safe_current_path(value: str | None) -> bool:
    if not value:
        return True
    if len(value) > 255 or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return False
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return False
    path = parsed.path.rstrip("/") or "/"
    if path in KNOWN_CLIENT_PATHS:
        return True
    return path.startswith("/applications/") and path.removeprefix("/applications/").isdigit()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _safe_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_PREFILL_URL:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split()).strip()
    return value[:MAX_PREFILL_TEXT] if value else None


def sanitize_action_parameters(
    action_id: str,
    raw: dict[str, Any] | None,
    *,
    trusted_context: dict[str, int | None] | None = None,
    extracted_url: str | None = None,
) -> dict[str, str | int]:
    definition = ACTION_CATALOG.get(action_id)
    if definition is None:
        return {}
    raw = raw or {}
    trusted_context = trusted_context or {}
    clean: dict[str, str | int] = {}
    for key in definition.allowed_parameters:
        if key in {"job_url", "list_url"}:
            value = _safe_url(extracted_url)
        elif key in {"keyword", "location"}:
            value = _safe_text(raw.get(key))
        elif key == "view":
            value = "match" if raw.get(key) == "match" else None
        elif key == "job_ids":
            candidate = trusted_context.get("job_id")
            value = str(candidate) if _positive_int(candidate) else None
        elif key in {"job_id", "application_id", "interview_id", "resume_profile_id"}:
            value = _positive_int(trusted_context.get(key))
        else:
            value = None
        if value is not None:
            clean[key] = value
    return clean


def build_action(action_id: str, parameters: dict[str, str | int] | None = None) -> dict[str, str] | None:
    definition = ACTION_CATALOG.get(action_id)
    if definition is None:
        return None
    parameters = dict(parameters or {})
    path = definition.path
    if "{application_id}" in path:
        application_id = _positive_int(parameters.pop("application_id", None))
        if application_id is None:
            return None
        path = path.replace("{application_id}", str(application_id))
    query = [(key, value) for key, value in parameters.items() if key in definition.allowed_parameters]
    href = f"{path}?{urlencode(query)}" if query else path
    return {"action_id": action_id, "label": definition.label, "href": href}


def prompt_catalog() -> list[dict[str, Any]]:
    return [
        {
            "action_id": item.action_id,
            "label": item.label,
            "description": item.description,
            "allowed_parameters": list(item.allowed_parameters),
        }
        for item in ACTION_CATALOG.values()
    ]

