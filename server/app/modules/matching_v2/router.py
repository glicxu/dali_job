from __future__ import annotations

import hashlib
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
    QualificationAssessmentCreateRequest,
    QualificationAssessmentView,
    QualificationCareerContextView,
)
from app.modules.matching_v2.canonical import CANONICALIZATION_VERSION, build_evidence_spans, canonicalize_text
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
    QualificationAssessment,
)
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

router = APIRouter(tags=["candidate-profiles"])


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
    response_model=CandidateProfileView,
)
def create_candidate_profile(
    resume_profile_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
) -> CandidateProfileView:
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


@router.post("/jobs/{job_id}/job-profile", response_model=JobProfileView)
def create_job_profile(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    extractor: JobProfileExtractor = Depends(get_job_profile_extractor),
) -> JobProfileView:
    _require_v2_access(request, db, identity)
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
    existing = find_cached_qualification_assessment(
        db,
        candidate_profile=candidate,
        selection_revision=context.selection.revision,
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
            career_context=context.career_profile,
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
    try:
        artifact = validate_qualification_assessment(
            result.artifact,
            requirements=requirements,
            allowed_evidence_refs=qualification_input.allowed_evidence_refs,
            incomplete_evidence_input=bool(qualification_input.omitted_evidence_refs),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "INVALID_QUALIFICATION_RESPONSE", "message": str(exc)},
        ) from exc
    warnings = []
    if qualification_input.omitted_evidence_refs:
        warnings.append(
            f"NEEDS_MORE_INFORMATION:OMITTED_CANDIDATE_EVIDENCE:{len(qualification_input.omitted_evidence_refs)}"
        )
    assessment = create_or_get_qualification_assessment(
        db,
        owner=owner,
        candidate_profile=candidate,
        career_selection=context.selection,
        selected_career_profile=context.career_profile,
        selection_reason_code=context.reason_code,
        job_profile=job_profile,
        artifact=artifact,
        input_quality={
            "warnings": warnings,
            "omitted_evidence_count": len(qualification_input.omitted_evidence_refs),
            "complete": not qualification_input.omitted_evidence_refs,
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
        return version.extracted_text, "document-extracted-text.v1", version.id
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
        extracted=profile.artifact,
        requirements=[JobRequirementView(
            requirement_id=item.requirement_id,
            local_ref=item.local_ref,
            category=item.category,
            scoring_dimension=item.scoring_dimension,
            statement=item.statement,
            importance=item.importance,
            hard_constraint=item.hard_constraint,
            acceptable_evidence_contexts=item.acceptable_evidence_contexts,
            minimum_years=item.minimum_years,
            explicit_alternatives=item.explicit_alternatives,
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
    return QualificationAssessmentView(
        schema_version=assessment.schema_version,
        qualification_assessment_id=assessment.public_id,
        candidate_profile_id=candidate.public_id,
        job_profile_id=job_profile.public_id,
        career_context=QualificationCareerContextView(
            selection_revision=assessment.candidate_career_selection_revision,
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
