from __future__ import annotations

from datetime import timezone
import logging
import socket
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.accounts.models import User
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.matching_v2.api_schemas import (
    MatchCreateRequest,
    MatchingOperationStageView,
    MatchingOperationView,
    MatchRerunRequest,
    QualificationAssessmentCreateRequest,
)
from app.modules.matching_v2.models import (
    EligibilityAssessment,
    EligibilityRevision,
    MatchResult,
    MatchingOperation,
    JobFamilyPreMatch,
    PreferenceAssessment,
    PreferenceRevision,
    QualificationAssessment,
)
from app.modules.matching_v2.pre_match import (
    create_or_get_job_family_pre_match,
    get_matching_intent,
)
from app.modules.matching_v2.orchestration import (
    IdempotencyKeyReused,
    OperationLeaseUnavailable,
    begin_stage,
    claim_operation,
    complete_operation,
    complete_stage,
    create_or_get_operation,
    fail_stage,
    first_incomplete_stage,
    get_operation,
    get_operation_for_match,
    list_stages,
    queue_retry,
    recover_interrupted_operation,
)
from app.modules.matching_v2.phase5 import create_or_get_match_result, get_match_result
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, content_sha256
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    ArtifactOwnershipError,
    get_candidate_profile_for_owner,
    get_job_profile_by_public_id,
)
from app.modules.matching_v2.router import (
    _match_result_view,
    _require_v2_access,
    create_qualification_assessment,
    get_qualification_matcher,
    get_candidate_profile_extractor,
    get_job_profile_extractor,
)
from app.modules.matching_v2.qualification import QualificationMatcher
from app.modules.matching_v2.extraction import CandidateProfileExtractor, JobProfileExtractor
from app.modules.operations.service import session_factory_for


LOGGER = logging.getLogger(__name__)
router = APIRouter(tags=["matching-v2-orchestration"])


@router.post("/matches", response_model=MatchingOperationView)
def create_match(
    payload: MatchCreateRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    matcher: QualificationMatcher = Depends(get_qualification_matcher),
) -> MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    request_payload = payload.model_dump(mode="json", exclude={"idempotency_key", "mode"})
    request_hash = _request_hash(request, request_payload)
    try:
        operation, created = create_or_get_operation(
            db,
            owner=owner,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            request_payload=request_payload,
            mode=payload.mode,
        )
        if created:
            _validate_inputs(db, owner=owner, payload=request_payload)
        db.commit()
    except IdempotencyKeyReused as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "IDEMPOTENCY_KEY_REUSED", "message": str(exc)},
        ) from exc

    if created and payload.mode == "asynchronous":
        response.status_code = status.HTTP_202_ACCEPTED
        background_tasks.add_task(
            _execute_background,
            session_factory_for(db),
            request,
            operation.id,
        )
    elif created:
        _execute_operation(db, request, identity, operation, matcher)
    if operation.status != "completed":
        response.status_code = status.HTTP_202_ACCEPTED
    db.refresh(operation)
    return _operation_view(db, operation, owner)


@router.get("/matching-operations/{operation_id}", response_model=MatchingOperationView)
def read_matching_operation(
    operation_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    operation = get_operation(db, owner=owner, public_id=operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="Matching operation not found.")
    return _operation_view(db, operation, owner)


@router.post("/matching-operations/{operation_id}/retry", response_model=MatchingOperationView)
def retry_matching_operation(
    operation_id: str,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    matcher: QualificationMatcher = Depends(get_qualification_matcher),
    candidate_extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
    job_extractor: JobProfileExtractor = Depends(get_job_profile_extractor),
) -> MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    operation = get_operation(db, owner=owner, public_id=operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="Matching operation not found.")
    recover_interrupted_operation(db, operation)
    if operation.status == "retryable_failure":
        try:
            queue_retry(db, operation)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    elif operation.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending, interrupted, or retryable matching operations can run.",
        )
    if operation.mode == "asynchronous":
        response.status_code = status.HTTP_202_ACCEPTED
        background_tasks.add_task(
            _execute_background,
            session_factory_for(db),
            request,
            operation.id,
            candidate_extractor,
            job_extractor,
        )
    else:
        _execute_operation(
            db,
            request,
            identity,
            operation,
            matcher,
            candidate_extractor=candidate_extractor,
            job_extractor=job_extractor,
        )
    db.refresh(operation)
    if operation.status != "completed":
        response.status_code = status.HTTP_202_ACCEPTED
    return _operation_view(db, operation, owner)


@router.get("/matches/{match_id}", response_model=MatchingOperationView)
def read_match(
    match_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    result = get_match_result(db, owner=owner, public_id=match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Match Result not found.")
    operation = get_operation_for_match(db, owner=owner, match_result_id=result.id)
    if operation is None:
        raise HTTPException(status_code=404, detail="Matching operation not found.")
    return _operation_view(db, operation, owner)


@router.post("/matches/{match_id}/rerun", response_model=MatchingOperationView)
def rerun_match(
    match_id: str,
    payload: MatchRerunRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    matcher: QualificationMatcher = Depends(get_qualification_matcher),
) -> MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    result = get_match_result(db, owner=owner, public_id=match_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Match Result not found.")
    prior = get_operation_for_match(db, owner=owner, match_result_id=result.id)
    if prior is None:
        raise HTTPException(status_code=409, detail="Original matching operation is unavailable.")
    original = dict(prior.request_payload)
    candidate_id = payload.candidate_profile_id or original["candidate_profile_id"]
    matching_intent_id = payload.matching_intent_id or original["matching_intent_id"]
    matching_intent_revision = payload.matching_intent_revision or original["matching_intent_revision"]
    return create_match(
        MatchCreateRequest(
            candidate_profile_id=candidate_id,
            matching_intent_id=matching_intent_id,
            matching_intent_revision=matching_intent_revision,
            job_profile_id=original["job_profile_id"],
            preference_revision=payload.preference_revision,
            eligibility_revision=payload.eligibility_revision,
            mode=payload.mode,
            idempotency_key=payload.idempotency_key,
        ),
        request,
        response,
        background_tasks,
        db,
        identity,
        matcher,
    )


def _execute_background(
    session_factory,
    request: Request,
    operation_id: int,
    candidate_extractor: CandidateProfileExtractor | None = None,
    job_extractor: JobProfileExtractor | None = None,
) -> None:
    with session_factory() as db:
        operation = db.get(MatchingOperation, operation_id)
        if operation is None or operation.status != "pending":
            return
        user = db.get(User, operation.user_id)
        if user is None or not user.is_active:
            return
        identity = AuthenticatedIdentity(
            external_user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            timezone=user.timezone,
            provider=user.auth_provider,
            role=user.role,
        )
        matcher = get_qualification_matcher(request, identity)
        _execute_operation(
            db,
            request,
            identity,
            operation,
            matcher,
            candidate_extractor=candidate_extractor,
            job_extractor=job_extractor,
        )


def _execute_operation(
    db: Session,
    request: Request,
    identity: AuthenticatedIdentity,
    operation: MatchingOperation,
    matcher: QualificationMatcher,
    *,
    candidate_extractor: CandidateProfileExtractor | None = None,
    job_extractor: JobProfileExtractor | None = None,
) -> None:
    if operation.operation_type in {"candidate_profile_extraction", "job_profile_extraction"}:
        from app.modules.matching_v2.extraction_operations import execute_extraction_operation
        execute_extraction_operation(
            db,
            operation,
            candidate_extractor=(
                candidate_extractor or get_candidate_profile_extractor(request, identity)
                if operation.operation_type == "candidate_profile_extraction" else None
            ),
            job_extractor=(
                job_extractor or get_job_profile_extractor(request, identity)
                if operation.operation_type == "job_profile_extraction" else None
            ),
        )
        return
    lease_owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
    try:
        claim_operation(db, operation, lease_owner=lease_owner)
    except OperationLeaseUnavailable:
        return
    payload = dict(operation.request_payload)
    owner = ArtifactOwner.authenticated(
        workspace_id=operation.workspace_id,
        user_id=operation.user_id,
    )
    while operation.status == "running":
        stage = first_incomplete_stage(db, operation.id)
        if stage is None:
            return
        try:
            if stage.stage == "candidate_profile":
                begin_stage(
                    db,
                    operation,
                    stage,
                    input_artifact_ids={"candidate_profile_id": payload["candidate_profile_id"]},
                )
                candidate = get_candidate_profile_for_owner(db, public_id=payload["candidate_profile_id"], owner=owner)
                if candidate is None:
                    raise ArtifactOwnershipError("Candidate Profile not found.")
                complete_stage(db, operation, stage, output_artifact_id=candidate.public_id, cache_hit=True)
            elif stage.stage == "job_profile":
                begin_stage(
                    db,
                    operation,
                    stage,
                    input_artifact_ids={"job_profile_id": payload["job_profile_id"]},
                )
                job = get_job_profile_by_public_id(db, public_id=payload["job_profile_id"])
                if job is None:
                    raise ArtifactOwnershipError("Job Profile not found.")
                complete_stage(db, operation, stage, output_artifact_id=job.public_id, cache_hit=True)
            elif stage.stage == "job_family_pre_match":
                _run_job_family_pre_match_stage(db, operation, stage, payload, owner)
            elif stage.stage == "qualification":
                _run_qualification_stage(db, request, identity, operation, stage, payload, matcher)
            else:
                _run_deterministic_stage(db, request, operation, stage, payload, owner)
        except Exception as exc:
            db.rollback()
            operation = db.get(MatchingOperation, operation.id)
            stage = first_incomplete_stage(db, operation.id) if operation is not None else None
            if operation is None or stage is None:
                return
            error_code, error_message = _safe_error(stage.stage, exc)
            fail_stage(
                db,
                operation,
                stage,
                error_code=error_code,
                error_message=error_message,
            )
            LOGGER.warning(
                "matching_operation_stage_failed correlation_id=%s operation_id=%s stage=%s "
                "attempt=%s error_code=%s exception_type=%s",
                operation.correlation_id,
                operation.public_id,
                stage.stage,
                stage.attempt_count,
                error_code,
                type(exc).__name__,
            )
            return
        db.refresh(operation)


def _run_qualification_stage(
    db: Session,
    request: Request,
    identity: AuthenticatedIdentity,
    operation: MatchingOperation,
    stage,
    payload: dict,
    matcher: QualificationMatcher,
) -> None:
    pre_match_stage = next(item for item in list_stages(db, operation.id) if item.stage == "job_family_pre_match")
    if pre_match_stage.output_artifact_id is None:
        raise RuntimeError("Job Family Pre-Match dependency is incomplete.")
    begin_stage(
        db,
        operation,
        stage,
        input_artifact_ids={
            "candidate_profile_id": payload["candidate_profile_id"],
            "job_profile_id": payload["job_profile_id"],
            "job_family_pre_match_id": pre_match_stage.output_artifact_id,
        },
    )
    before = (
        db.scalar(select(QualificationAssessment).where(QualificationAssessment.public_id == stage.output_artifact_id))
        if stage.output_artifact_id
        else None
    )
    view = create_qualification_assessment(
        QualificationAssessmentCreateRequest(
            candidate_profile_id=payload["candidate_profile_id"],
            job_profile_id=payload["job_profile_id"],
            job_family_pre_match_id=pre_match_stage.output_artifact_id,
        ),
        request,
        db,
        identity,
        matcher,
    )
    assessment = db.scalar(
        select(QualificationAssessment).where(QualificationAssessment.public_id == view.qualification_assessment_id)
    )
    if assessment is None:
        raise RuntimeError("Qualification Assessment was not persisted.")
    started = stage.started_at
    created = assessment.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    cache_hit = before is not None or (started is not None and created < started)
    complete_stage(
        db,
        operation,
        stage,
        output_artifact_id=assessment.public_id,
        cache_hit=cache_hit,
        provider_usage={"availability": "provider_adapter_does_not_expose_usage"},
        policy_versions={
            "prompt": assessment.prompt_version,
            "matching": assessment.matching_policy_version,
            "selection": assessment.selection_policy_version,
        },
    )


def _run_deterministic_stage(
    db: Session,
    request: Request,
    operation: MatchingOperation,
    stage,
    payload: dict,
    owner: ArtifactOwner,
) -> None:
    qualification_stage = next(item for item in list_stages(db, operation.id) if item.stage == "qualification")
    if qualification_stage.output_artifact_id is None:
        raise RuntimeError("Qualification Assessment dependency is incomplete.")
    begin_stage(
        db,
        operation,
        stage,
        input_artifact_ids={
            "qualification_assessment_id": qualification_stage.output_artifact_id,
            "preference_revision": payload.get("preference_revision"),
            "eligibility_revision": payload.get("eligibility_revision"),
        },
    )
    result = create_or_get_match_result(
        db,
        owner=owner,
        qualification_public_id=qualification_stage.output_artifact_id,
        preference_revision=payload.get("preference_revision"),
        eligibility_revision=payload.get("eligibility_revision"),
        legacy_adapter_enabled=request.app.state.runtime.matching_v2.legacy_adapter_enabled,
    )
    preference = (
        db.get(PreferenceAssessment, result.preference_assessment_id) if result.preference_assessment_id else None
    )
    eligibility = (
        db.get(EligibilityAssessment, result.eligibility_assessment_id) if result.eligibility_assessment_id else None
    )
    output_id = {
        "preference": preference.public_id if preference else "not_configured",
        "eligibility": eligibility.public_id if eligibility else "not_configured",
        "scoring": result.public_id,
    }[stage.stage]
    complete_stage(
        db,
        operation,
        stage,
        output_artifact_id=output_id,
        cache_hit=True,
        policy_versions=result.policy_versions,
    )
    if stage.stage == "scoring":
        complete_operation(db, operation, match_result_id=result.id)


def _run_job_family_pre_match_stage(
    db: Session,
    operation: MatchingOperation,
    stage,
    payload: dict,
    owner: ArtifactOwner,
) -> None:
    begin_stage(
        db,
        operation,
        stage,
        input_artifact_ids={
            "candidate_profile_id": payload["candidate_profile_id"],
            "matching_intent_id": payload["matching_intent_id"],
            "matching_intent_revision": payload["matching_intent_revision"],
            "job_profile_id": payload["job_profile_id"],
        },
    )
    candidate = get_candidate_profile_for_owner(db, public_id=payload["candidate_profile_id"], owner=owner)
    job = get_job_profile_by_public_id(db, public_id=payload["job_profile_id"])
    intent = get_matching_intent(
        db,
        owner=owner,
        public_id=payload["matching_intent_id"],
        revision=payload["matching_intent_revision"],
    )
    if candidate is None or job is None or intent is None:
        raise ArtifactOwnershipError("Job Family Pre-Match input is unavailable.")
    before = db.scalar(select(JobFamilyPreMatch).where(
        JobFamilyPreMatch.candidate_profile_version_id == candidate.id,
        JobFamilyPreMatch.matching_intent_id == intent.id,
        JobFamilyPreMatch.job_profile_version_id == job.id,
    ))
    pre_match = create_or_get_job_family_pre_match(
        db, owner=owner, candidate_profile=candidate, intent=intent, job_profile=job
    )
    complete_stage(
        db,
        operation,
        stage,
        output_artifact_id=pre_match.public_id,
        cache_hit=before is not None,
        policy_versions={"job_family_pre_match": pre_match.policy_version},
    )


def _validate_inputs(db: Session, *, owner: ArtifactOwner, payload: dict) -> None:
    candidate = get_candidate_profile_for_owner(db, public_id=payload["candidate_profile_id"], owner=owner)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate Profile not found.")
    intent = get_matching_intent(
        db,
        owner=owner,
        public_id=payload["matching_intent_id"],
        revision=payload["matching_intent_revision"],
    )
    if intent is None or intent.candidate_profile_version_id != candidate.id:
        raise HTTPException(
            status_code=422,
            detail={"code": "UNKNOWN_MATCHING_INTENT_REVISION"},
        )
    if get_job_profile_by_public_id(db, public_id=payload["job_profile_id"]) is None:
        raise HTTPException(status_code=404, detail="Job Profile not found.")
    workspace_id, user_id = owner.workspace_id, owner.user_id
    for key, model in (
        ("preference_revision", PreferenceRevision),
        ("eligibility_revision", EligibilityRevision),
    ):
        revision = payload.get(key)
        if revision is None:
            continue
        if (
            db.scalar(
                select(model).where(
                    model.workspace_id == workspace_id,
                    model.user_id == user_id,
                    model.revision == revision,
                )
            )
            is None
        ):
            raise HTTPException(status_code=404, detail=f"{key.replace('_', ' ').title()} not found.")


def _request_hash(request: Request, payload: dict) -> str:
    policies = {f"{entry.artifact_type}:{entry.version}": entry.content_hash for entry in DEFAULT_REGISTRY.entries()}
    return content_sha256(
        {
            "inputs": payload,
            "model_id": request.app.state.runtime.openai_model,
            "policies": policies,
        }
    )


def _safe_error(stage: str, exc: Exception) -> tuple[str, str]:
    if isinstance(exc, HTTPException):
        if isinstance(exc.detail, dict) and isinstance(exc.detail.get("code"), str):
            code = exc.detail["code"]
        else:
            code = f"HTTP_{exc.status_code}"
        return code, f"The {stage.replace('_', ' ')} stage could not be completed."
    if isinstance(exc, ArtifactOwnershipError):
        return "ARTIFACT_NOT_FOUND", f"The {stage.replace('_', ' ')} dependency is unavailable."
    return "STAGE_EXECUTION_FAILED", f"The {stage.replace('_', ' ')} stage failed and may be retried."


def _operation_view(
    db: Session,
    operation: MatchingOperation,
    owner: ArtifactOwner,
) -> MatchingOperationView:
    result = db.get(MatchResult, operation.match_result_id) if operation.match_result_id else None
    match_view = _match_result_view(db, result) if result is not None else None
    return MatchingOperationView(
        operation_id=operation.public_id,
        operation_type=operation.operation_type,
        status=operation.status,
        current_stage=operation.current_stage,
        correlation_id=operation.correlation_id,
        mode=operation.mode,
        match=match_view,
        stages=[
            MatchingOperationStageView(
                stage=stage.stage,
                status=stage.status,
                attempt_count=stage.attempt_count,
                max_attempts=stage.max_attempts,
                input_artifact_ids=stage.input_artifact_ids,
                output_artifact_id=stage.output_artifact_id,
                cache_hit=stage.cache_hit,
                provider_usage=stage.provider_usage,
                policy_versions=stage.policy_versions,
                error_code=stage.error_code,
                error_message=stage.error_message,
                started_at=stage.started_at,
                heartbeat_at=stage.heartbeat_at,
                completed_at=stage.completed_at,
            )
            for stage in list_stages(db, operation.id)
        ],
        error_code=operation.error_code,
        error_message=operation.error_message,
        poll_after_seconds=2 if operation.status in {"pending", "running", "retryable_failure"} else None,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )
