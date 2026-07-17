from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    ApplicationStatusHistory,
)
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.documents.models import Document, DocumentVersion
from app.modules.profiles.repository import ensure_account_for_identity

METRIC_VERSION = "outcome-analytics-v1"
LIFECYCLE_STATUSES = [
    "interested",
    "applied",
    "interviewing",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
]
RESPONSE_STATUSES = {"interviewing", "offer", "accepted", "rejected"}
INTERVIEW_STATUSES = {"interviewing", "offer", "accepted"}
OFFER_STATUSES = {"offer", "accepted"}

DEFINITIONS = [
    {
        "metric": "Application count",
        "definition": "Current lifecycle status for applications whose cohort date is in range. Cohort date is applied_at when available, otherwise created_at.",
        "denominator": "All owner-scoped applications in the selected cohort range, including archived records.",
    },
    {
        "metric": "Response rate",
        "definition": "Applications with a post-application status event reaching interviewing, offer, accepted, or rejected.",
        "denominator": "Applications with applied_at in the selected range.",
    },
    {
        "metric": "Interview rate",
        "definition": "Applications with a post-application interviewing/offer/accepted status event or an interview_scheduled application event.",
        "denominator": "Applications with applied_at in the selected range.",
    },
    {
        "metric": "Offer rate",
        "definition": "Applications with a post-application offer or accepted status event.",
        "denominator": "Applications with applied_at in the selected range.",
    },
    {
        "metric": "Rejection rate",
        "definition": "Applications with a post-application rejected status event.",
        "denominator": "Applications with applied_at in the selected range.",
    },
    {
        "metric": "Withdrawal rate",
        "definition": "Applications with a post-application withdrawn status event.",
        "denominator": "Applications with applied_at in the selected range.",
    },
    {
        "metric": "Time to first response",
        "definition": "Elapsed time from applied_at to the first qualifying response status event. Negative durations are excluded.",
        "denominator": "Submitted applications with a qualifying response event.",
    },
    {
        "metric": "Time to first interview",
        "definition": "Elapsed time from applied_at to the first interviewing status or interview_scheduled event. Negative durations are excluded.",
        "denominator": "Submitted applications with a qualifying interview event.",
    },
    {
        "metric": "Source performance",
        "definition": "Outcome rates grouped by the immutable source label captured when the application was created.",
        "denominator": "Submitted applications in each source group.",
    },
    {
        "metric": "Resume-version performance",
        "definition": "Outcome rates grouped by the latest exact resume document version attached at or before applied_at. If none existed then, the earliest later attachment is labeled and used.",
        "denominator": "Submitted applications with an exact attached resume document version.",
    },
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timezone(name: str) -> tuple[ZoneInfo, str, list[str]]:
    try:
        return ZoneInfo(name), name, []
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC"), "UTC", [f"Timezone '{name}' was unavailable; analytics used UTC."]


def _date_bounds(
    start_date: date | None,
    end_date: date | None,
    timezone_name: str,
) -> tuple[datetime | None, datetime | None, str, list[str]]:
    zone, resolved_name, warnings = _timezone(timezone_name)
    start = datetime.combine(start_date, time.min, zone).astimezone(timezone.utc) if start_date else None
    end = (
        datetime.combine(end_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        if end_date
        else None
    )
    return start, end, resolved_name, warnings


def _in_range(value: datetime, start: datetime | None, end: datetime | None) -> bool:
    value = _as_utc(value)
    return (start is None or value >= start) and (end is None or value < end)


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100 / denominator, 1) if denominator else None


def _first_signal(
    application: Application,
    histories: list[ApplicationStatusHistory],
    events: list[ApplicationEvent],
    statuses: set[str],
    event_types: set[str] | None = None,
) -> tuple[datetime | None, int]:
    if application.applied_at is None:
        return None, 0
    applied_at = _as_utc(application.applied_at)
    candidates = [_as_utc(row.created_at) for row in histories if row.to_status in statuses]
    if event_types:
        candidates.extend(_as_utc(row.created_at) for row in events if row.event_type in event_types)
    invalid = sum(1 for value in candidates if value < applied_at)
    valid = [value for value in candidates if value >= applied_at]
    return (min(valid) if valid else None), invalid


def _duration(metric: str, values: list[float]) -> dict:
    return {
        "metric": metric,
        "sample_size": len(values),
        "average_hours": round(sum(values) / len(values), 1) if values else None,
        "median_hours": round(float(median(values)), 1) if values else None,
    }


def _performance_group(key: str, label: str, outcomes: list[dict]) -> dict:
    sample_size = len(outcomes)
    return {
        "key": key,
        "label": label,
        "sample_size": sample_size,
        "response_rate": _percentage(sum(item["response"] for item in outcomes), sample_size),
        "interview_rate": _percentage(sum(item["interview"] for item in outcomes), sample_size),
        "offer_rate": _percentage(sum(item["offer"] for item in outcomes), sample_size),
        "rejection_rate": _percentage(sum(item["rejected"] for item in outcomes), sample_size),
        "withdrawal_rate": _percentage(sum(item["withdrawn"] for item in outcomes), sample_size),
        "small_sample": sample_size < 5,
    }


def analytics_summary(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    range_start, range_end, timezone_name, timezone_warnings = _date_bounds(
        start_date,
        end_date,
        identity.timezone,
    )
    all_applications = list(
        db.scalars(
            select(Application).where(
                Application.workspace_id == workspace.id,
                Application.user_id == user.id,
            )
        )
    )
    status_cohort = [
        application
        for application in all_applications
        if _in_range(application.applied_at or application.created_at, range_start, range_end)
    ]
    submitted = [
        application
        for application in all_applications
        if application.applied_at is not None
        and _in_range(application.applied_at, range_start, range_end)
    ]
    application_ids = [application.id for application in submitted]
    histories_by_application: dict[int, list[ApplicationStatusHistory]] = defaultdict(list)
    events_by_application: dict[int, list[ApplicationEvent]] = defaultdict(list)
    if application_ids:
        for row in db.scalars(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id.in_(application_ids))
            .order_by(ApplicationStatusHistory.created_at)
        ):
            histories_by_application[row.application_id].append(row)
        for row in db.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id.in_(application_ids))
            .order_by(ApplicationEvent.created_at)
        ):
            events_by_application[row.application_id].append(row)

    outcomes: dict[int, dict] = {}
    response_hours: list[float] = []
    interview_hours: list[float] = []
    events_before_applied = 0
    for application in submitted:
        histories = histories_by_application[application.id]
        events = events_by_application[application.id]
        response_at, invalid_response = _first_signal(
            application, histories, events, RESPONSE_STATUSES, {"interview_scheduled"}
        )
        interview_at, invalid_interview = _first_signal(
            application,
            histories,
            events,
            INTERVIEW_STATUSES,
            {"interview_scheduled"},
        )
        offer_at, invalid_offer = _first_signal(application, histories, events, OFFER_STATUSES)
        rejected_at, invalid_rejected = _first_signal(application, histories, events, {"rejected"})
        withdrawn_at, invalid_withdrawn = _first_signal(application, histories, events, {"withdrawn"})
        del invalid_response, invalid_interview, invalid_offer, invalid_rejected, invalid_withdrawn
        applied_at = _as_utc(application.applied_at)
        relevant_statuses = RESPONSE_STATUSES | {"withdrawn"}
        events_before_applied += sum(
            row.to_status in relevant_statuses and _as_utc(row.created_at) < applied_at
            for row in histories
        )
        events_before_applied += sum(
            row.event_type == "interview_scheduled" and _as_utc(row.created_at) < applied_at
            for row in events
        )
        if response_at:
            response_hours.append((response_at - applied_at).total_seconds() / 3600)
        if interview_at:
            interview_hours.append((interview_at - applied_at).total_seconds() / 3600)
        outcomes[application.id] = {
            "response": response_at is not None,
            "interview": interview_at is not None,
            "offer": offer_at is not None,
            "rejected": rejected_at is not None,
            "withdrawn": withdrawn_at is not None,
        }

    denominator = len(submitted)
    rates = [
        {
            "outcome": outcome,
            "numerator": sum(item[outcome] for item in outcomes.values()),
            "denominator": denominator,
            "percentage": _percentage(sum(item[outcome] for item in outcomes.values()), denominator),
        }
        for outcome in ("response", "interview", "offer", "rejected", "withdrawn")
    ]

    source_groups: dict[str, list[dict]] = defaultdict(list)
    for application in submitted:
        source_groups[application.source_label_snapshot or "Unknown / legacy"].append(outcomes[application.id])
    source_performance = [
        _performance_group(key, key, values)
        for key, values in sorted(source_groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    attachments_by_application: dict[int, list[tuple[ApplicationDocument, Document, DocumentVersion]]] = defaultdict(list)
    if application_ids:
        for attachment, document, version in db.execute(
            select(ApplicationDocument, Document, DocumentVersion)
            .join(DocumentVersion, DocumentVersion.id == ApplicationDocument.document_version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                ApplicationDocument.application_id.in_(application_ids),
                ApplicationDocument.purpose == "resume",
            )
            .order_by(ApplicationDocument.created_at)
        ).all():
            attachments_by_application[attachment.application_id].append((attachment, document, version))

    resume_groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    missing_resume_version = 0
    attached_after_applied = 0
    for application in submitted:
        attachments = attachments_by_application[application.id]
        if not attachments:
            missing_resume_version += 1
            continue
        applied_at = _as_utc(application.applied_at)
        before = [row for row in attachments if _as_utc(row[0].created_at) <= applied_at]
        if before:
            chosen = max(before, key=lambda row: _as_utc(row[0].created_at))
        else:
            chosen = min(attachments, key=lambda row: _as_utc(row[0].created_at))
            attached_after_applied += 1
        _, document, version = chosen
        label = f"{document.title} v{version.version_number}"
        resume_groups[(version.id, label)].append(outcomes[application.id])
    resume_performance = [
        _performance_group(str(key[0]), key[1], values)
        for key, values in sorted(resume_groups.items(), key=lambda item: (-len(item[1]), item[0][1]))
    ]

    status_counts = [
        {"status": status, "count": sum(application.status == status for application in status_cohort)}
        for status in LIFECYCLE_STATUSES
    ]
    local_zone = ZoneInfo(timezone_name)
    trend: dict[str, int] = defaultdict(int)
    for application in status_cohort:
        cohort_date = _as_utc(application.applied_at or application.created_at).astimezone(local_zone)
        trend[cohort_date.strftime("%Y-%m")] += 1

    missing_applied_at = sum(
        application.applied_at is None and application.status != "interested"
        for application in all_applications
    )
    missing_source = sum(application.source_label_snapshot is None for application in submitted)
    warnings = list(timezone_warnings)
    if denominator and denominator < 5:
        warnings.append("Outcome rates use fewer than five submitted applications and are descriptive only.")
    if missing_applied_at:
        warnings.append("Some progressed applications have no applied_at timestamp and are excluded from rate denominators.")
    if missing_source:
        warnings.append("Some legacy applications have no immutable source snapshot.")
    if missing_resume_version:
        warnings.append("Some submitted applications have no exact attached resume version and are excluded from resume performance.")
    if attached_after_applied:
        warnings.append("Some resume versions were attached after applied_at; those groups are exact attachments but may not be the submitted file.")
    if events_before_applied:
        warnings.append("Outcome events dated before applied_at were ignored as inconsistent history.")

    return {
        "metric_version": METRIC_VERSION,
        "timezone": timezone_name,
        "range_start": range_start,
        "range_end_exclusive": range_end,
        "generated_at": datetime.now(timezone.utc),
        "application_count": len(status_cohort),
        "submitted_application_count": denominator,
        "status_counts": status_counts,
        "application_trend": [{"period": period, "count": trend[period]} for period in sorted(trend)],
        "rates": rates,
        "durations": [
            _duration("time_to_first_response", response_hours),
            _duration("time_to_first_interview", interview_hours),
        ],
        "source_performance": source_performance,
        "resume_version_performance": resume_performance,
        "definitions": DEFINITIONS,
        "data_quality": {
            "missing_applied_at": missing_applied_at,
            "missing_source_snapshot": missing_source,
            "missing_resume_version": missing_resume_version,
            "resume_attached_after_applied": attached_after_applied,
            "events_before_applied": events_before_applied,
            "warnings": warnings,
        },
    }
