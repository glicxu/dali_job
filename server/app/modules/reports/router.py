from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity, require_admin
from app.modules.reports import repository
from app.modules.reports.schemas import (
    AdminReportResponse,
    AdminReportUpdateRequest,
    ReportStatus,
    UserReportCreateRequest,
    UserReportResponse,
)

router = APIRouter(tags=["reports"])


@router.post("/reports", response_model=UserReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: UserReportCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> UserReportResponse:
    report = repository.create_report(db, identity, payload)
    db.commit()
    db.refresh(report)
    return UserReportResponse.model_validate(report)


@router.get("/reports", response_model=list[UserReportResponse])
def list_reports(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[UserReportResponse]:
    return [UserReportResponse.model_validate(report) for report in repository.list_reports_for_identity(db, identity)]


@router.get("/admin/reports", response_model=list[AdminReportResponse])
def list_reports_for_admin(
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(require_admin),
) -> list[AdminReportResponse]:
    items = repository.list_admin_reports(db, report_status)
    repository.audit_admin_report_list(db, identity, report_status, len(items))
    db.commit()
    return [AdminReportResponse.model_validate(item) for item in items]


@router.patch("/admin/reports/{report_id}", response_model=AdminReportResponse)
def update_report_as_admin(
    report_id: int,
    payload: AdminReportUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(require_admin),
) -> AdminReportResponse:
    report = repository.update_admin_report(db, identity, report_id, payload)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    db.commit()
    return AdminReportResponse.model_validate(report)
