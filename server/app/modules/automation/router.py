from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.automation import schedules
from app.modules.automation.entitlements import EntitlementCatalog
from app.modules.automation.repository import SubscriptionUnavailable
from app.modules.automation.schemas import (
    AccountUsageResponse,
    EntitlementResponse,
    SearchRunListResponse,
    SearchRunResponse,
    SearchScheduleCreateRequest,
    SearchScheduleListResponse,
    SearchScheduleResponse,
    SearchScheduleUpdateRequest,
)
from app.modules.notifications.service import get_or_create_preferences


router = APIRouter(tags=["automation"])


def _catalog(request: Request) -> EntitlementCatalog:
    return request.app.state.tier_entitlements


def _raise_schedule_error(exc: Exception) -> None:
    if isinstance(exc, schedules.ScheduleValidationError):
        status_code = status.HTTP_404_NOT_FOUND if exc.code.endswith("_not_found") else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    if isinstance(exc, SubscriptionUnavailable):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "subscription_unavailable", "message": str(exc)},
        ) from exc
    raise exc


@router.get("/account/entitlements", response_model=EntitlementResponse)
def get_entitlements(
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EntitlementResponse:
    try:
        return EntitlementResponse.model_validate(
            schedules.entitlement_details(db, identity, _catalog(request))
        )
    except (schedules.ScheduleValidationError, SubscriptionUnavailable) as exc:
        _raise_schedule_error(exc)
        raise AssertionError("unreachable")


@router.get("/account/usage", response_model=AccountUsageResponse)
def get_account_usage(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> AccountUsageResponse:
    try:
        return AccountUsageResponse.model_validate(
            schedules.account_usage_details(
                db,
                identity,
                _catalog(request),
                limit=limit,
                before_id=before_id,
            )
        )
    except SubscriptionUnavailable as exc:
        _raise_schedule_error(exc)
        raise AssertionError("unreachable")


@router.get("/automation/schedules", response_model=SearchScheduleListResponse)
def list_search_schedules(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchScheduleListResponse:
    return SearchScheduleListResponse(
        schedules=[SearchScheduleResponse.model_validate(item) for item in schedules.list_schedules(db, identity)]
    )


@router.post(
    "/automation/schedules",
    response_model=SearchScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_search_schedule(
    payload: SearchScheduleCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchScheduleResponse:
    try:
        values = payload.model_dump()
        if values["minimum_match_score"] is None:
            values["minimum_match_score"] = get_or_create_preferences(
                db, identity
            ).minimum_match_score
        schedule = schedules.create_schedule(
            db,
            identity,
            _catalog(request),
            **values,
        )
        return SearchScheduleResponse.model_validate(schedule)
    except (schedules.ScheduleValidationError, SubscriptionUnavailable) as exc:
        _raise_schedule_error(exc)
        raise AssertionError("unreachable")


@router.patch("/automation/schedules/{schedule_id}", response_model=SearchScheduleResponse)
def update_search_schedule(
    schedule_id: int,
    payload: SearchScheduleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchScheduleResponse:
    schedule = schedules.get_schedule(db, identity, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search schedule not found.")
    values = payload.model_dump(exclude_unset=True)
    values["next_run_at_was_set"] = "next_run_at" in payload.model_fields_set
    try:
        updated = schedules.update_schedule(db, identity, schedule, _catalog(request), **values)
        return SearchScheduleResponse.model_validate(updated)
    except (schedules.ScheduleValidationError, SubscriptionUnavailable) as exc:
        _raise_schedule_error(exc)
        raise AssertionError("unreachable")


@router.post("/automation/schedules/{schedule_id}/pause", response_model=SearchScheduleResponse)
def pause_search_schedule(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchScheduleResponse:
    schedule = schedules.get_schedule(db, identity, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search schedule not found.")
    return SearchScheduleResponse.model_validate(schedules.pause_schedule(db, schedule))


@router.post("/automation/schedules/{schedule_id}/resume", response_model=SearchScheduleResponse)
def resume_search_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchScheduleResponse:
    schedule = schedules.get_schedule(db, identity, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search schedule not found.")
    try:
        return SearchScheduleResponse.model_validate(
            schedules.resume_schedule(db, schedule, _catalog(request))
        )
    except (schedules.ScheduleValidationError, SubscriptionUnavailable) as exc:
        _raise_schedule_error(exc)
        raise AssertionError("unreachable")


@router.delete("/automation/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search_schedule(
    schedule_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    schedule = schedules.get_schedule(db, identity, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search schedule not found.")
    schedules.soft_delete_schedule(db, schedule)


@router.get("/automation/runs", response_model=SearchRunListResponse)
def list_search_runs(
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchRunListResponse:
    runs, next_cursor = schedules.list_runs(
        db,
        identity,
        limit=limit,
        before_id=before_id,
    )
    return SearchRunListResponse(
        runs=[SearchRunResponse.model_validate(item) for item in runs],
        next_cursor=next_cursor,
    )


@router.get("/automation/runs/{run_id}", response_model=SearchRunResponse)
def get_search_run(
    run_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SearchRunResponse:
    run = schedules.get_run(db, identity, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search run not found.")
    return SearchRunResponse.model_validate(run)
