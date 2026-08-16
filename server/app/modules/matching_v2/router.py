from __future__ import annotations

import hashlib
import re
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.provider_ops import GuardedProviderProxy
from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.automation.models import UserSubscription
from app.modules.documents import repository as document_repository
from app.modules.matching_v2.api_schemas import (
    CandidateCareerProfileView,
    CandidateCareerSelectionRequest,
    CandidateCareerSelectionView,
    CandidateProfileSourceResponse,
    CandidateProfileView,
    JobProfileSourceResponse,
    JobProfileView,
    JobRequirementView,
    JobFamilyPreMatchView,
    MatchingIntentView,
    MatchingIntentWrite,
    EligibilityRevisionUpdate,
    EligibilityRevisionView,
    MatchResultCreateRequest,
    MatchResultView,
    PreferenceRevisionUpdate,
    PreferenceRevisionView,
    QualificationAssessmentCreateRequest,
    QualificationAssessmentView,
    QualificationCareerContextView,
    MatchingOperationView,
)
from app.modules.matching_v2.canonical import CANONICALIZATION_VERSION, build_evidence_spans, canonicalize_text
from app.modules.profiles.resume_import import redact_resume_personal_info
from app.modules.matching_v2.extraction import (
    CandidateProfileExtractor,
    JobProfileExtractor,
    OpenAICandidateProfileExtractor,
    OpenAIJobProfileExtractor,
    cleanup_job_spans,
    validate_job_extraction,
)
from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateCareerSelection,
    CandidateProfileVersion,
    CanonicalSource,
    JobProfileVersion,
    JobRequirement,
    JobFamilyPreMatch,
    MatchingIntent,
    QualificationAssessment,
    EligibilityAssessment,
    PreferenceAssessment,
    MatchingOperation,
)
from app.modules.matching_v2.extraction_operations import execute_extraction_operation
from app.modules.matching_v2.orchestration import create_or_get_operation
from app.modules.matching_v2.phase5 import (
    create_eligibility_revision,
    create_or_get_match_result,
    create_preference_revision,
    eligibility_artifact,
    get_match_result,
    latest_eligibility_revision,
    latest_preference_revision,
)
from app.modules.matching_v2.pre_match import create_matching_intent, get_job_family_pre_match, get_matching_intent
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, content_sha256
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    ArtifactOwnershipError,
    RevisionConflict,
    SpanInput,
    create_career_selection,
    create_or_get_candidate_profile,
    create_or_get_canonical_source,
    create_or_get_job_profile,
    find_cached_candidate_profile,
    find_cached_job_profile,
    get_candidate_profile_for_owner,
    get_job_profile_by_public_id,
    create_or_get_qualification_assessment,
    find_cached_qualification_assessment,
    get_qualification_assessment_for_owner,
    sync_policy_registry,
)
from app.modules.matching_v2.qualification import (
    OpenAIQualificationMatcher,
    QualificationMatcher,
    build_qualification_input,
    select_candidate_career_context,
    validate_qualification_assessment,
)
from app.modules.jobs import repository as job_repository
from app.modules.profiles import repository as profile_repository
from app.modules.operations.service import session_factory_for

router = APIRouter(tags=["candidate-profiles"])


def _create_extraction_operation(
    db: Session,
    *,
    owner: ArtifactOwner,
    operation_type: str,
    payload: dict,
) -> MatchingOperation:
    policy_hashes = {
        f"{entry.artifact_type}:{entry.version}": entry.content_hash
        for entry in DEFAULT_REGISTRY.entries()
    }
    request_hash = content_sha256({"operation_type": operation_type, "payload": payload, "policies": policy_hashes})
    operation, _ = create_or_get_operation(
        db,
        owner=owner,
        idempotency_key=f"{operation_type}:{request_hash.removeprefix('sha256:')}",
        request_hash=request_hash,
        request_payload=payload,
        mode="asynchronous",
        operation_type=operation_type,
        stage_definitions=((operation_type, 2),),
    )
    return operation


def _execute_extraction_background(
    session_factory,
    operation_id: int,
    candidate_extractor: CandidateProfileExtractor | None,
    job_extractor: JobProfileExtractor | None,
) -> None:
    with session_factory() as db:
        operation = db.get(MatchingOperation, operation_id)
        if operation is None or operation.status != "pending":
            return
        execute_extraction_operation(
            db,
            operation,
            candidate_extractor=candidate_extractor,
            job_extractor=job_extractor,
        )


def _extraction_operation_view(db: Session, operation: MatchingOperation) -> MatchingOperationView:
    # Local import avoids a router import cycle while keeping one operation response contract.
    from app.modules.matching_v2.orchestration_router import _operation_view

    return _operation_view(
        db,
        operation,
        ArtifactOwner.authenticated(workspace_id=operation.workspace_id, user_id=operation.user_id),
    )


def get_candidate_profile_extractor(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> CandidateProfileExtractor:
    runtime = request.app.state.runtime
    return cast(
        CandidateProfileExtractor,
        GuardedProviderProxy(
            factory=lambda: OpenAICandidateProfileExtractor(model=runtime.openai_model),
            method_name="extract",
            request=request,
            identity=identity,
            provider="openai",
            feature="candidate_profile_v2_extract",
        ),
    )


def get_job_profile_extractor(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobProfileExtractor:
    runtime = request.app.state.runtime
    return cast(
        JobProfileExtractor,
        GuardedProviderProxy(
            factory=lambda: OpenAIJobProfileExtractor(model=runtime.openai_model),
            method_name="extract",
            request=request,
            identity=identity,
            provider="openai",
            feature="job_profile_v2_extract",
        ),
    )


def get_qualification_matcher(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> QualificationMatcher:
    runtime = request.app.state.runtime
    return cast(
        QualificationMatcher,
        GuardedProviderProxy(
            factory=lambda: OpenAIQualificationMatcher(model=runtime.openai_model),
            method_name="assess",
            request=request,
            identity=identity,
            provider="openai",
            feature="qualification_v2_assess",
        ),
    )


@router.post(
    "/resumes/{resume_profile_id}/candidate-profile",
    response_model=CandidateProfileView | MatchingOperationView,
)
def create_candidate_profile(
    resume_profile_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
) -> CandidateProfileView | MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")

    source_text, extraction_version, document_version_id = _resume_source_text(db, identity, resume_profile)
    canonical_text = canonicalize_text(source_text)
    spans = build_evidence_spans(canonical_text, source_prefix=f"resume_{resume_profile.id}")
    if not spans:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Resume profile does not contain enough text to create evidence spans.",
        )
    source = create_or_get_canonical_source(
        db,
        owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id),
        source_type="resume",
        canonical_text=canonical_text,
        text_extraction_version=extraction_version,
        canonicalization_version=CANONICALIZATION_VERSION,
        resume_profile_id=resume_profile.id,
        document_version_id=document_version_id,
        spans=[
            SpanInput(
                span_id=span.span_id,
                section=span.section,
                start_utf8_byte=span.start_utf8_byte,
                end_utf8_byte=span.end_utf8_byte,
                excerpt=span.excerpt,
            )
            for span in spans
        ],
    )
    sync_policy_registry(db)
    profile = find_cached_candidate_profile(
        db,
        source=source,
        model_id=request.app.state.runtime.openai_model,
    )
    if profile is None:
        if request.url.path.startswith("/api/v1/internal/evaluation/"):
            result = extractor.extract(spans)
            profile = create_or_get_candidate_profile(
                db,
                source=source,
                artifact=result.artifact,
                model_id=result.model_id,
                provider_execution_reference=result.provider_execution_reference,
                resume_profile_id=resume_profile.id,
            )
            return _candidate_profile_view(db, profile, source)
        operation = _create_extraction_operation(
            db,
            owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id),
            operation_type="candidate_profile_extraction",
            payload={
                "canonical_source_id": source.id,
                "resume_profile_id": resume_profile.id,
                "model_id": request.app.state.runtime.openai_model,
            },
        )
        db.commit()
        if operation.status == "pending":
            background_tasks.add_task(
                _execute_extraction_background,
                session_factory_for(db),
                operation.id,
                extractor,
                None,
            )
        response.status_code = status.HTTP_202_ACCEPTED
        return _extraction_operation_view(db, operation)
    return _candidate_profile_view(db, profile, source)


@router.get(
    "/resumes/{resume_profile_id}/candidate-profile",
    response_model=CandidateProfileView | None,
)
def get_latest_candidate_profile_for_resume(
    resume_profile_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> CandidateProfileView | None:
    user, workspace = _require_v2_access(request, db, identity)
    resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    profile = db.scalar(
        select(CandidateProfileVersion)
        .join(CanonicalSource, CandidateProfileVersion.canonical_source_id == CanonicalSource.id)
        .where(
            CandidateProfileVersion.resume_profile_id == resume_profile_id,
            CandidateProfileVersion.deleted_at.is_(None),
            CanonicalSource.workspace_id == workspace.id,
            CanonicalSource.user_id == user.id,
            CanonicalSource.deleted_at.is_(None),
        )
        .order_by(CandidateProfileVersion.created_at.desc())
        .limit(1)
    )
    if profile is None:
        return None
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate Profile source is unavailable.",
        )
    return _candidate_profile_view(db, profile, source)


@router.get(
    "/candidate-profiles/{candidate_profile_id}",
    response_model=CandidateProfileView,
)
def get_candidate_profile(
    candidate_profile_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> CandidateProfileView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    profile = get_candidate_profile_for_owner(
        db,
        public_id=candidate_profile_id,
        owner=owner,
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate Profile not found.")
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Candidate Profile source is unavailable.")
    return _candidate_profile_view(db, profile, source)


@router.post(
    "/candidate-profiles/{candidate_profile_id}/regenerate",
    response_model=CandidateProfileView | MatchingOperationView,
    description=(
        "Rebuild from the Candidate Profile's current resume. A corrected resume creates a new "
        "immutable source/profile version; unchanged versioned inputs return the cached profile."
    ),
)
def regenerate_candidate_profile(
    candidate_profile_id: str,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
) -> CandidateProfileView | MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    profile = get_candidate_profile_for_owner(db, public_id=candidate_profile_id, owner=owner)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate Profile not found.")
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None or source.resume_profile_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate Profile does not have a reusable resume source.",
        )
    return create_candidate_profile(
        resume_profile_id=source.resume_profile_id,
        request=request,
        response=response,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        extractor=extractor,
    )


@router.put(
    "/candidate-profiles/{candidate_profile_id}/primary-career-profile",
    response_model=CandidateProfileView,
)
def update_primary_career_profile(
    candidate_profile_id: str,
    payload: CandidateCareerSelectionRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> CandidateProfileView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    try:
        create_career_selection(
            db,
            candidate_profile_public_id=candidate_profile_id,
            owner=owner,
            expected_revision=payload.expected_revision,
            career_profile_id=payload.primary_career_profile_id,
            selection_source="user_confirmed",
        )
    except RevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CAREER_SELECTION_REVISION_CONFLICT", "message": str(exc)},
        ) from exc
    except ArtifactOwnershipError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate Profile not found.") from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "UNKNOWN_CAREER_PROFILE", "message": str(exc)},
        ) from exc

    profile = get_candidate_profile_for_owner(db, public_id=candidate_profile_id, owner=owner)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate Profile not found.")
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Candidate Profile source is unavailable.")
    return _candidate_profile_view(db, profile, source)


@router.post(
    "/candidate-profiles/{candidate_profile_id}/matching-intents",
    response_model=MatchingIntentView,
)
def post_matching_intent(
    candidate_profile_id: str,
    payload: MatchingIntentWrite,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchingIntentView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    candidate = get_candidate_profile_for_owner(db, public_id=candidate_profile_id, owner=owner)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate Profile not found.")
    try:
        intent = create_matching_intent(db, owner=owner, candidate_profile=candidate, **payload.model_dump())
    except (ValueError, RevisionConflict) as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_MATCHING_INTENT", "message": str(exc)}) from exc
    return _matching_intent_view(db, intent)


@router.get("/matching-intents/{matching_intent_id}", response_model=MatchingIntentView)
def read_matching_intent(
    matching_intent_id: str,
    request: Request,
    revision: int | None = None,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchingIntentView:
    user, workspace = _require_v2_access(request, db, identity)
    intent = get_matching_intent(
        db,
        owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id),
        public_id=matching_intent_id,
        revision=revision,
    )
    if intent is None:
        raise HTTPException(status_code=404, detail="Matching Intent not found.")
    return _matching_intent_view(db, intent)


@router.put("/matching-intents/{matching_intent_id}", response_model=MatchingIntentView)
def put_matching_intent(
    matching_intent_id: str,
    payload: MatchingIntentWrite,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MatchingIntentView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    current = get_matching_intent(db, owner=owner, public_id=matching_intent_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Matching Intent not found.")
    candidate_row = db.get(CandidateProfileVersion, current.candidate_profile_version_id)
    candidate = (
        get_candidate_profile_for_owner(db, public_id=candidate_row.public_id, owner=owner)
        if candidate_row is not None else None
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate Profile not found.")
    try:
        intent = create_matching_intent(
            db, owner=owner, candidate_profile=candidate, public_id=matching_intent_id, **payload.model_dump()
        )
    except RevisionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "MATCHING_INTENT_REVISION_CONFLICT", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "INVALID_MATCHING_INTENT", "message": str(exc)}) from exc
    return _matching_intent_view(db, intent)


@router.get("/job-family-pre-matches/{pre_match_id}", response_model=JobFamilyPreMatchView)
def read_job_family_pre_match(
    pre_match_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobFamilyPreMatchView:
    user, workspace = _require_v2_access(request, db, identity)
    row = get_job_family_pre_match(
        db,
        owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id),
        public_id=pre_match_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Job Family Pre-Match not found.")
    return _job_family_pre_match_view(db, row)


@router.post("/jobs/{job_id}/job-profile", response_model=JobProfileView | MatchingOperationView)
def create_job_profile(
    job_id: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    extractor: JobProfileExtractor = Depends(get_job_profile_extractor),
) -> JobProfileView | MatchingOperationView:
    user, workspace = _require_v2_access(request, db, identity)
    saved_job = job_repository.get_user_job_for_identity(db, identity, job_id)
    if saved_job is None:
        raise HTTPException(status_code=404, detail="Saved job not found.")
    cached_job = job_repository.get_job_cache_for_saved_job(db, saved_job)
    if cached_job is None or cached_job.deleted_at is not None:
        raise HTTPException(
            status_code=422,
            detail="Job Profile extraction currently requires a reusable cached job description.",
        )
    canonical_text = canonicalize_text(cached_job.raw_description_text)
    content_prefix = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()[:16]
    spans = build_evidence_spans(canonical_text, source_prefix=f"job_{content_prefix}")
    if not spans:
        raise HTTPException(status_code=422, detail="Job description does not contain usable evidence spans.")
    source = create_or_get_canonical_source(
        db,
        owner=ArtifactOwner.shared(),
        source_type="job",
        canonical_text=canonical_text,
        text_extraction_version="jobs-cache-raw-description.v1",
        canonicalization_version=CANONICALIZATION_VERSION,
        spans=[SpanInput(
            span_id=span.span_id,
            section=span.section,
            start_utf8_byte=span.start_utf8_byte,
            end_utf8_byte=span.end_utf8_byte,
            excerpt=span.excerpt,
        ) for span in spans],
    )
    sync_policy_registry(db)
    profile = find_cached_job_profile(db, source=source, model_id=request.app.state.runtime.openai_model)
    if profile is None:
        if request.url.path.startswith("/api/v1/internal/evaluation/"):
            cleanup = cleanup_job_spans(spans)
            result = extractor.extract(list(cleanup.kept_spans))
            artifact = validate_job_extraction(
                result.artifact,
                {span.span_id for span in cleanup.kept_spans},
                duplicate_spans_removed=cleanup.duplicate_spans_removed,
                boilerplate_spans_ignored=cleanup.boilerplate_spans_ignored,
                omitted_span_count=len(result.omitted_span_ids),
            )
            profile = create_or_get_job_profile(
                db,
                source=source,
                artifact=artifact,
                model_id=result.model_id,
                jobs_cache_id=cached_job.id,
                provider_execution_reference=result.provider_execution_reference,
            )
            return _job_profile_view(db, profile, source)
        operation = _create_extraction_operation(
            db,
            owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id),
            operation_type="job_profile_extraction",
            payload={
                "canonical_source_id": source.id,
                "jobs_cache_id": cached_job.id,
                "model_id": request.app.state.runtime.openai_model,
            },
        )
        db.commit()
        if operation.status == "pending":
            background_tasks.add_task(
                _execute_extraction_background,
                session_factory_for(db),
                operation.id,
                None,
                extractor,
            )
        response.status_code = status.HTTP_202_ACCEPTED
        return _extraction_operation_view(db, operation)
    return _job_profile_view(db, profile, source)


@router.get("/job-profiles/{job_profile_id}", response_model=JobProfileView)
def get_job_profile(
    job_profile_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobProfileView:
    _require_v2_access(request, db, identity)
    profile = get_job_profile_by_public_id(db, public_id=job_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Job Profile not found.")
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Job Profile source is unavailable.")
    return _job_profile_view(db, profile, source)


@router.post("/qualification-assessments", response_model=QualificationAssessmentView)
def create_qualification_assessment(
    payload: QualificationAssessmentCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    matcher: QualificationMatcher = Depends(get_qualification_matcher),
) -> QualificationAssessmentView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    candidate = get_candidate_profile_for_owner(
        db, public_id=payload.candidate_profile_id, owner=owner
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate Profile not found.")
    job_profile = get_job_profile_by_public_id(db, public_id=payload.job_profile_id)
    if job_profile is None:
        raise HTTPException(status_code=404, detail="Job Profile not found.")
    sync_policy_registry(db)
    pre_match = None
    if payload.job_family_pre_match_id is not None:
        pre_match = get_job_family_pre_match(db, owner=owner, public_id=payload.job_family_pre_match_id)
        if pre_match is None:
            raise HTTPException(status_code=404, detail="Job Family Pre-Match not found.")
        if (
            pre_match.candidate_profile_version_id != candidate.id
            or pre_match.job_profile_version_id != job_profile.id
        ):
            raise HTTPException(
                status_code=422,
                detail={"code": "PRE_MATCH_INPUT_MISMATCH"},
            )
        career_selection = None
        selected_career = (
            db.get(CandidateCareerProfile, pre_match.selected_candidate_career_profile_id)
            if pre_match.selected_candidate_career_profile_id is not None else None
        )
        selection_revision = None
        selection_reason_code = pre_match.reason_codes[0] if pre_match.reason_codes else "JOB_FAMILY_PRE_MATCH"
    else:
        try:
            context = select_candidate_career_context(
                db,
                candidate_profile=candidate,
                job_profile=job_profile,
                selection_revision=payload.candidate_career_selection_revision,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "UNKNOWN_CAREER_SELECTION_REVISION", "message": str(exc)},
            ) from exc
        career_selection = context.selection
        selected_career = context.career_profile
        selection_revision = context.selection.revision
        selection_reason_code = context.reason_code
    existing = find_cached_qualification_assessment(
        db,
        candidate_profile=candidate,
        selection_revision=selection_revision,
        job_family_pre_match=pre_match,
        job_profile=job_profile,
        model_id=request.app.state.runtime.openai_model,
    )
    if existing is not None:
        return _qualification_assessment_view(db, existing)
    try:
        qualification_input = build_qualification_input(
            db,
            candidate_profile=candidate,
            job_profile=job_profile,
            career_context=selected_career,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "QUALIFICATION_INPUT_LIMIT", "message": str(exc)},
        ) from exc
    result = matcher.assess(qualification_input)
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job_profile.id
    )).all())
    validation_arguments = {
        "requirements": requirements,
        "allowed_evidence_refs": qualification_input.allowed_evidence_refs,
        "allowed_alternative_group_refs": qualification_input.allowed_alternative_group_refs,
        "incomplete_evidence_input": bool(qualification_input.omitted_evidence_refs),
    }
    try:
        artifact = validate_qualification_assessment(result.artifact, **validation_arguments)
    except ValueError as first_exc:
        repair = getattr(matcher, "repair", None)
        if repair is None:
            raise HTTPException(
                status_code=502,
                detail={"code": "INVALID_QUALIFICATION_RESPONSE", "message": str(first_exc)},
            ) from first_exc
        result = repair(qualification_input, (_qualification_repair_error(first_exc),))
        try:
            artifact = validate_qualification_assessment(result.artifact, **validation_arguments)
        except ValueError as repair_exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "INVALID_QUALIFICATION_RESPONSE", "message": str(repair_exc)},
            ) from repair_exc
    warnings = []
    if qualification_input.omitted_evidence_refs:
        warnings.append(
            f"NEEDS_MORE_INFORMATION:OMITTED_CANDIDATE_EVIDENCE:{len(qualification_input.omitted_evidence_refs)}"
        )
    assessment = create_or_get_qualification_assessment(
        db,
        owner=owner,
        candidate_profile=candidate,
        career_selection=career_selection,
        job_family_pre_match=pre_match,
        selected_career_profile=selected_career,
        selection_reason_code=selection_reason_code,
        job_profile=job_profile,
        artifact=artifact,
        input_quality={
            "warnings": warnings,
            "omitted_evidence_count": len(qualification_input.omitted_evidence_refs),
            "complete": not qualification_input.omitted_evidence_refs,
            "validation_retry_count": result.retry_count,
        },
        model_id=result.model_id,
        provider_execution_reference=result.provider_execution_reference,
    )
    return _qualification_assessment_view(db, assessment)


@router.get(
    "/qualification-assessments/{qualification_assessment_id}",
    response_model=QualificationAssessmentView,
)
def get_qualification_assessment(
    qualification_assessment_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> QualificationAssessmentView:
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    assessment = get_qualification_assessment_for_owner(
        db, public_id=qualification_assessment_id, owner=owner
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Qualification Assessment not found.")
    return _qualification_assessment_view(db, assessment)


def _require_v2_access(request: Request, db: Session, identity: AuthenticatedIdentity):
    flags = request.app.state.runtime.matching_v2
    if not (flags.internal_super_enabled or flags.shadow_enabled or flags.evaluation_enabled):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    user, workspace = profile_repository.ensure_account_for_identity(db, identity)
    subscription = db.scalar(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.deleted_at.is_(None),
        )
    )
    internal_user = identity.role == "admin" or (
        flags.internal_super_enabled and subscription is not None and subscription.tier_code == "super"
    )
    if not internal_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return user, workspace


def _resume_source_text(db: Session, identity: AuthenticatedIdentity, resume_profile):
    if resume_profile.source_document_version_id is not None:
        version = document_repository.get_version_for_identity(
            db,
            identity,
            resume_profile.source_document_version_id,
        )
        if version is None or not version.extracted_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The resume source document does not contain extracted text.",
            )
        return redact_resume_personal_info(version.extracted_text), "document-extracted-text.v2", version.id
    return _render_resume_data(resume_profile.resume_data), "resume-profile-json.v1", None


def _render_resume_data(resume_data: dict) -> str:
    labels = (
        ("summary", "Summary"),
        ("experience", "Experience"),
        ("projects", "Projects"),
        ("skills", "Skills"),
        ("education", "Education"),
        ("certifications", "Certifications"),
        ("publications", "Publications"),
        ("awards", "Awards"),
        ("languages", "Languages"),
        ("volunteer", "Volunteer"),
    )
    lines: list[str] = []
    headline = resume_data.get("headline")
    if isinstance(headline, str) and headline.strip():
        lines.extend(["Profile", headline.strip(), ""])
    for key, label in labels:
        value = resume_data.get(key)
        if isinstance(value, str) and value.strip():
            lines.extend([label, value.strip(), ""])
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                lines.append(label)
                lines.extend(f"- {item}" for item in items)
                lines.append("")
    return "\n".join(lines).strip()


def _candidate_profile_view(
    db: Session,
    profile: CandidateProfileVersion,
    source: CanonicalSource,
) -> CandidateProfileView:
    careers = db.scalars(
        select(CandidateCareerProfile)
        .where(CandidateCareerProfile.candidate_profile_version_id == profile.id)
        .order_by(CandidateCareerProfile.id)
    ).all()
    latest = db.scalar(
        select(CandidateCareerSelection)
        .where(CandidateCareerSelection.candidate_profile_version_id == profile.id)
        .order_by(desc(CandidateCareerSelection.revision))
        .limit(1)
    )
    if latest is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Candidate Profile selection is unavailable.")
    selected = next(
        (item.career_profile_id for item in careers if item.id == latest.candidate_career_profile_id),
        None,
    )
    return CandidateProfileView(
        schema_version=profile.schema_version,
        candidate_profile_id=profile.public_id,
        resume_profile_id=profile.resume_profile_id,
        source=CandidateProfileSourceResponse(
            source_id=source.public_id,
            source_hash=source.source_hash,
            text_extraction_version=source.text_extraction_version,
            canonicalization_version=source.canonicalization_version,
            language=source.language,
        ),
        extracted=profile.artifact,
        career_profiles=[
            CandidateCareerProfileView(
                career_profile_id=item.career_profile_id,
                local_ref=item.local_ref,
                role_family=item.role_family,
                track=item.track,
                level=item.level,
                confidence=item.confidence,
                evidence_refs=item.evidence_refs,
                dimension_signals=item.dimension_signals,
            )
            for item in careers
        ],
        selection=CandidateCareerSelectionView(
            revision=latest.revision,
            primary_career_profile_id=selected,
            selection_source=latest.selection_source,
        ),
        generation={
            "model": profile.model_id,
            "prompt_version": profile.prompt_version,
            "taxonomy_version": profile.taxonomy_version,
            "semantic_validator_version": profile.semantic_validator_version,
            "provider_execution_reference": profile.provider_execution_reference,
        },
        created_at=profile.created_at,
    )


def _job_profile_view(db: Session, profile: JobProfileVersion, source: CanonicalSource) -> JobProfileView:
    requirements = db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == profile.id
    ).order_by(JobRequirement.id)).all()
    return JobProfileView(
        schema_version=profile.schema_version,
        job_profile_id=profile.public_id,
        jobs_cache_id=profile.jobs_cache_id,
        source=JobProfileSourceResponse(
            source_id=source.public_id,
            source_hash=source.source_hash,
            text_extraction_version=source.text_extraction_version,
            canonicalization_version=source.canonicalization_version,
            language=source.language,
        ),
        extracted=_normalize_job_profile_artifact(profile.artifact),
        requirements=[JobRequirementView(
            requirement_id=item.requirement_id,
            local_ref=item.local_ref,
            category=item.category,
            scoring_dimension=item.scoring_dimension,
            statement=item.statement,
            importance="required" if item.importance == "required" else "optional",
            acceptable_evidence_contexts=item.acceptable_evidence_contexts,
            minimum_years=item.minimum_years,
            alternative_groups=_legacy_alternative_groups(
                item.local_ref, item.explicit_alternatives, item.source_refs
            ),
            policy_alternative_group=item.policy_alternative_group,
            source_refs=item.source_refs,
        ) for item in requirements],
        generation={
            "model": profile.model_id,
            "prompt_version": profile.prompt_version,
            "taxonomy_version": profile.taxonomy_version,
            "source_policy_version": profile.source_policy_version,
            "deduplication_version": profile.deduplication_version,
            "semantic_validator_version": profile.semantic_validator_version,
            "provider_execution_reference": profile.provider_execution_reference,
        },
        created_at=profile.created_at,
    )


def _legacy_alternative_groups(
    local_ref: str, alternatives: list[str], source_refs: list[str]
) -> list[dict[str, object]]:
    if not alternatives:
        return []
    members = alternatives if len(alternatives) > 1 else [
        part.strip() for part in re.split(r"\s*(?:\bor\b|/|,)\s*", alternatives[0], flags=re.I)
        if part.strip()
    ]
    members = list(dict.fromkeys(members))
    if len(members) < 2:
        return []
    return [{
        "local_ref": f"{local_ref}_alternatives",
        "any_of": members,
        "source_refs": source_refs,
    }]


def _normalize_job_profile_artifact(value: dict[str, object]) -> dict[str, object]:
    """Keep persisted v1/v2 Job Profiles readable through the v3 API contract."""

    artifact = dict(value)
    career = dict(artifact.get("career_context") or {})
    primary = career.get("primary_role_family")
    career["adjacent_role_families"] = [
        item for item in career.get("adjacent_role_families", [])
        if item not in {primary, "unknown"}
    ]
    artifact["career_context"] = career
    normalized = []
    for raw in artifact.get("requirements", []):
        requirement = dict(raw)
        requirement["importance"] = (
            "required" if requirement.get("importance") == "required" else "optional"
        )
        requirement.pop("hard_constraint", None)
        alternatives = requirement.pop("explicit_alternatives", [])
        requirement.setdefault(
            "alternative_groups",
            _legacy_alternative_groups(
                str(requirement.get("local_ref", "requirement")),
                alternatives,
                list(requirement.get("source_refs", [])),
            ),
        )
        normalized.append(requirement)
    artifact["requirements"] = normalized
    return artifact


def _qualification_assessment_view(
    db: Session, assessment: QualificationAssessment
) -> QualificationAssessmentView:
    candidate = db.get(CandidateProfileVersion, assessment.candidate_profile_version_id)
    job_profile = db.get(JobProfileVersion, assessment.job_profile_version_id)
    selected = (
        db.get(CandidateCareerProfile, assessment.selected_candidate_career_profile_id)
        if assessment.selected_candidate_career_profile_id is not None
        else None
    )
    if candidate is None or job_profile is None:
        raise HTTPException(status_code=409, detail="Qualification Assessment inputs are unavailable.")
    pre_match = (
        db.get(JobFamilyPreMatch, assessment.job_family_pre_match_id)
        if assessment.job_family_pre_match_id is not None else None
    )
    return QualificationAssessmentView(
        schema_version=assessment.schema_version,
        qualification_assessment_id=assessment.public_id,
        candidate_profile_id=candidate.public_id,
        job_profile_id=job_profile.public_id,
        career_context=QualificationCareerContextView(
            selection_revision=assessment.candidate_career_selection_revision,
            job_family_pre_match_id=pre_match.public_id if pre_match is not None else None,
            selected_career_profile_id=(selected.career_profile_id if selected is not None else None),
            selection_policy_version=assessment.selection_policy_version,
            selection_reason_code=assessment.selection_reason_code,
        ),
        assessment=assessment.artifact,
        input_quality=assessment.input_quality,
        generation={
            "model": assessment.model_id,
            "prompt_version": assessment.prompt_version,
            "matching_policy_version": assessment.matching_policy_version,
            "input_policy_version": assessment.input_policy_version,
            "semantic_validator_version": assessment.semantic_validator_version,
            "alternative_policy_hashes": assessment.alternative_policy_hashes,
            "provider_execution_reference": assessment.provider_execution_reference,
        },
        created_at=assessment.created_at,
    )


def _matching_intent_view(db: Session, intent: MatchingIntent) -> MatchingIntentView:
    candidate = db.get(CandidateProfileVersion, intent.candidate_profile_version_id)
    selected = (
        db.get(CandidateCareerProfile, intent.selected_candidate_career_profile_id)
        if intent.selected_candidate_career_profile_id is not None else None
    )
    if candidate is None:
        raise HTTPException(status_code=409, detail="Matching Intent candidate is unavailable.")
    return MatchingIntentView(
        matching_intent_id=intent.public_id,
        candidate_profile_id=candidate.public_id,
        revision=intent.revision,
        target_role_text=intent.target_role_text,
        job_family=intent.job_family,
        track=intent.track,
        target_level=intent.target_level,
        selected_candidate_career_profile_id=selected.career_profile_id if selected else None,
        source=intent.source,
        created_at=intent.created_at,
    )


def _job_family_pre_match_view(db: Session, row: JobFamilyPreMatch) -> JobFamilyPreMatchView:
    candidate = db.get(CandidateProfileVersion, row.candidate_profile_version_id)
    intent = db.get(MatchingIntent, row.matching_intent_id)
    job = db.get(JobProfileVersion, row.job_profile_version_id)
    selected = (
        db.get(CandidateCareerProfile, row.selected_candidate_career_profile_id)
        if row.selected_candidate_career_profile_id is not None else None
    )
    if candidate is None or intent is None or job is None:
        raise HTTPException(status_code=409, detail="Job Family Pre-Match inputs are unavailable.")
    return JobFamilyPreMatchView(
        job_family_pre_match_id=row.public_id,
        matching_intent_id=intent.public_id,
        matching_intent_revision=row.matching_intent_revision,
        candidate_profile_id=candidate.public_id,
        job_profile_id=job.public_id,
        selected_candidate_career_profile_id=selected.career_profile_id if selected else None,
        selection_source=row.selection_source,
        family_compatibility=row.family_compatibility,
        track_compatibility=row.track_compatibility,
        level_compatibility=row.level_compatibility,
        proceed_to_detailed_match=row.proceed_to_detailed_match,
        reason_codes=list(row.reason_codes),
        policy_version=row.policy_version,
        created_at=row.created_at,
    )


@router.get("/users/me/matching-preferences", response_model=PreferenceRevisionView | None)
def get_matching_preferences(request: Request, db: Session = Depends(get_db_session), identity: AuthenticatedIdentity = Depends(get_current_identity)):
    user, workspace = _require_v2_access(request, db, identity)
    row = latest_preference_revision(db, owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id))
    return None if row is None else PreferenceRevisionView(revision=row.revision, preferences=row.artifact, created_at=row.created_at)


@router.put("/users/me/matching-preferences", response_model=PreferenceRevisionView)
def put_matching_preferences(payload: PreferenceRevisionUpdate, request: Request, db: Session = Depends(get_db_session), identity: AuthenticatedIdentity = Depends(get_current_identity)):
    user, workspace = _require_v2_access(request, db, identity)
    try:
        row = create_preference_revision(db, owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id), expected_revision=payload.expected_revision, artifact=payload.preferences)
        db.commit()
    except RevisionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PreferenceRevisionView(revision=row.revision, preferences=row.artifact, created_at=row.created_at)


@router.get("/users/me/eligibility-facts", response_model=EligibilityRevisionView | None)
def get_eligibility_facts(request: Request, db: Session = Depends(get_db_session), identity: AuthenticatedIdentity = Depends(get_current_identity)):
    user, workspace = _require_v2_access(request, db, identity)
    row = latest_eligibility_revision(db, owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id))
    return None if row is None else EligibilityRevisionView(revision=row.revision, facts=eligibility_artifact(row), created_at=row.created_at)


@router.put("/users/me/eligibility-facts", response_model=EligibilityRevisionView)
def put_eligibility_facts(payload: EligibilityRevisionUpdate, request: Request, db: Session = Depends(get_db_session), identity: AuthenticatedIdentity = Depends(get_current_identity)):
    user, workspace = _require_v2_access(request, db, identity)
    try:
        row = create_eligibility_revision(db, owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id), expected_revision=payload.expected_revision, artifact=payload.facts)
        db.commit()
    except RevisionConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return EligibilityRevisionView(revision=row.revision, facts=eligibility_artifact(row), created_at=row.created_at)


@router.post("/matching-v2/results", response_model=MatchResultView)
def create_match_result(payload: MatchResultCreateRequest, request: Request, db: Session = Depends(get_db_session), identity: AuthenticatedIdentity = Depends(get_current_identity)):
    user, workspace = _require_v2_access(request, db, identity)
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    try:
        row = create_or_get_match_result(db, owner=owner, qualification_public_id=payload.qualification_assessment_id, preference_revision=payload.preference_revision, eligibility_revision=payload.eligibility_revision, legacy_adapter_enabled=request.app.state.runtime.matching_v2.legacy_adapter_enabled)
        db.commit()
    except ArtifactOwnershipError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _match_result_view(db, row)


@router.get("/matching-v2/results/{match_id}", response_model=MatchResultView)
def read_match_result(match_id: str, request: Request, db: Session = Depends(get_db_session), identity: AuthenticatedIdentity = Depends(get_current_identity)):
    user, workspace = _require_v2_access(request, db, identity)
    row = get_match_result(db, owner=ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id), public_id=match_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Match Result not found.")
    return _match_result_view(db, row)


def _match_result_view(db: Session, row) -> MatchResultView:
    qualification = db.get(QualificationAssessment, row.qualification_assessment_id)
    preference = db.get(PreferenceAssessment, row.preference_assessment_id) if row.preference_assessment_id else None
    eligibility = db.get(EligibilityAssessment, row.eligibility_assessment_id) if row.eligibility_assessment_id else None
    if qualification is None:
        raise HTTPException(status_code=409, detail="Qualification Assessment is unavailable.")
    return MatchResultView(match_id=row.public_id, qualification_assessment_id=qualification.public_id, preference_assessment_id=preference.public_id if preference else None, eligibility_assessment_id=eligibility.public_id if eligibility else None, scores=row.score_artifact, explanation=row.explanation_artifact, policy=row.policy_versions, legacy_score=row.legacy_score, created_at=row.created_at)


def _qualification_repair_error(error: ValueError) -> dict[str, str]:
    message = str(error)
    known_errors = (
        (
            "met_by_alternative requires",
            "ALTERNATIVE_NOT_ALLOWED",
            "met_by_alternative requires a supplied alternative group or approved policy",
        ),
        (
            "not_demonstrated cannot cite evidence",
            "NOT_DEMONSTRATED_HAS_EVIDENCE",
            "not_demonstrated must not cite candidate evidence",
        ),
        (
            "Alternative references are valid only",
            "ALTERNATIVE_REFERENCE_STATUS_MISMATCH",
            "alternative references are valid only for met_by_alternative",
        ),
    )
    for fragment, code, safe_message in known_errors:
        if fragment in message:
            return {
                "code": code,
                "path": "$.requirement_assessments",
                "message": safe_message,
            }
    return {
        "code": "QUALIFICATION_SEMANTIC_VALIDATION_FAILED",
        "path": "$.requirement_assessments",
        "message": "the complete qualification assessment must satisfy all semantic rules",
    }
