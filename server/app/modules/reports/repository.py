from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.audit.models import AuditEvent
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.profiles.repository import ensure_account_for_identity
from app.modules.reports.models import UserReport
from app.modules.reports.schemas import AdminReportUpdateRequest, UserReportCreateRequest


def create_report(
    db: Session,
    identity: AuthenticatedIdentity,
    payload: UserReportCreateRequest,
) -> UserReport:
    user, workspace = ensure_account_for_identity(db, identity)
    report = UserReport(
        workspace_id=workspace.id,
        user_id=user.id,
        category=payload.category,
        title=payload.title.strip(),
        description=payload.description.strip(),
    )
    db.add(report)
    db.flush()
    return report


def list_reports_for_identity(db: Session, identity: AuthenticatedIdentity) -> list[UserReport]:
    user, workspace = ensure_account_for_identity(db, identity)
    return list(
        db.scalars(
            select(UserReport)
            .where(UserReport.user_id == user.id, UserReport.workspace_id == workspace.id)
            .order_by(desc(UserReport.updated_at), desc(UserReport.id))
        ).all()
    )


def list_admin_reports(db: Session, report_status: str | None = None) -> list[dict]:
    query = (
        select(UserReport, User)
        .join(User, User.id == UserReport.user_id)
        .order_by(desc(UserReport.updated_at), desc(UserReport.id))
    )
    if report_status:
        query = query.where(UserReport.status == report_status)
    return [_admin_report_dict(report, user) for report, user in db.execute(query).all()]


def audit_admin_report_list(
    db: Session,
    identity: AuthenticatedIdentity,
    report_status: str | None,
    result_count: int,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=int(identity.external_user_id),
            event_type="admin.reports.listed",
            subject_type="user_report_queue",
            source="api",
            outcome="success",
            event_data={"status_filter": report_status, "result_count": result_count},
        )
    )


def update_admin_report(
    db: Session,
    identity: AuthenticatedIdentity,
    report_id: int,
    payload: AdminReportUpdateRequest,
) -> dict | None:
    row = db.execute(
        select(UserReport, User)
        .join(User, User.id == UserReport.user_id)
        .where(UserReport.id == report_id)
        .limit(1)
    ).one_or_none()
    if row is None:
        return None

    report, reporter = row
    previous_status = report.status
    notes_changed = False
    fields = payload.model_fields_set
    if "status" in fields and payload.status is not None:
        report.status = payload.status
    if "admin_notes" in fields:
        normalized_notes = payload.admin_notes.strip() if payload.admin_notes else None
        notes_changed = normalized_notes != report.admin_notes
        report.admin_notes = normalized_notes

    if report.status in {"resolved", "closed"}:
        if previous_status not in {"resolved", "closed"} or report.resolved_at is None:
            report.resolved_at = datetime.now(timezone.utc)
        report.resolved_by_user_id = int(identity.external_user_id)
    else:
        report.resolved_at = None
        report.resolved_by_user_id = None

    db.flush()
    db.add(
        AuditEvent(
            workspace_id=report.workspace_id,
            actor_user_id=int(identity.external_user_id),
            event_type="admin.report.updated",
            subject_type="user_report",
            subject_id=str(report.id),
            source="api",
            outcome="success",
            event_data={
                "previous_status": previous_status,
                "new_status": report.status,
                "admin_notes_changed": notes_changed,
            },
        )
    )
    db.flush()
    return _admin_report_dict(report, reporter)


def _admin_report_dict(report: UserReport, user: User) -> dict:
    return {
        "id": report.id,
        "workspace_id": report.workspace_id,
        "user_id": report.user_id,
        "reporter_email": user.email,
        "reporter_display_name": user.display_name,
        "category": report.category,
        "title": report.title,
        "description": report.description,
        "status": report.status,
        "admin_notes": report.admin_notes,
        "resolved_at": report.resolved_at,
        "resolved_by_user_id": report.resolved_by_user_id,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }
