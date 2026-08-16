from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateCareerSelection,
    CandidateProfileVersion,
    CanonicalSource,
    JobProfileVersion,
    JobFamilyPreMatch,
    JobRequirement,
    QualificationAssessment,
    RequirementAssessment,
    PromptPolicyRegistryRecord,
    SourceSpan,
)
from app.modules.matching_v2.registry import (
    DEFAULT_REGISTRY,
    ImmutableRegistry,
    canonical_json,
    content_sha256,
)
from app.modules.matching_v2.schemas import (
    CandidateExtractionResponse,
    JobExtractionResponse,
    QualificationAssessmentResponse,
)


class RevisionConflict(ValueError):
    pass


class ArtifactOwnershipError(ValueError):
    pass


def _insert_unique_or_get(db: Session, instance, model, cache_key: str):
    """Insert a cache-keyed parent safely when concurrent workers race."""
    try:
        with db.begin_nested():
            db.add(instance)
            db.flush()
        return instance, True
    except IntegrityError:
        existing = db.scalar(select(model).where(model.cache_key == cache_key))
        if existing is None:
            raise
        return existing, False


@dataclass(frozen=True)
class ArtifactOwner:
    kind: str
    workspace_id: int | None = None
    user_id: int | None = None
    guest_trial_id: int | None = None

    def __post_init__(self) -> None:
        valid = (
            self.kind == "authenticated"
            and self.workspace_id is not None
            and self.user_id is not None
            and self.guest_trial_id is None
        ) or (
            self.kind == "guest"
            and self.workspace_id is None
            and self.user_id is None
            and self.guest_trial_id is not None
        ) or (
            self.kind == "shared"
            and self.workspace_id is None
            and self.user_id is None
            and self.guest_trial_id is None
        )
        if not valid:
            raise ValueError("Artifact owner fields do not match owner kind.")

    @classmethod
    def authenticated(cls, *, workspace_id: int, user_id: int) -> ArtifactOwner:
        return cls(kind="authenticated", workspace_id=workspace_id, user_id=user_id)

    @classmethod
    def guest(cls, *, guest_trial_id: int) -> ArtifactOwner:
        return cls(kind="guest", guest_trial_id=guest_trial_id)

    @classmethod
    def shared(cls) -> ArtifactOwner:
        return cls(kind="shared")

    def cache_value(self) -> dict[str, str | int | None]:
        return {
            "kind": self.kind,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "guest_trial_id": self.guest_trial_id,
        }


@dataclass(frozen=True)
class SpanInput:
    span_id: str
    section: str
    start_utf8_byte: int
    end_utf8_byte: int
    excerpt: str


def create_or_get_canonical_source(
    db: Session,
    *,
    owner: ArtifactOwner,
    source_type: str,
    canonical_text: str,
    text_extraction_version: str,
    canonicalization_version: str,
    spans: list[SpanInput],
    ocr_version: str | None = None,
    language: str = "en",
    resume_profile_id: int | None = None,
    guest_resume_profile_id: int | None = None,
    document_version_id: int | None = None,
) -> CanonicalSource:
    if source_type not in {"resume", "job"}:
        raise ValueError("Unsupported canonical source type.")
    _validate_source_links(
        db,
        owner=owner,
        source_type=source_type,
        resume_profile_id=resume_profile_id,
        guest_resume_profile_id=guest_resume_profile_id,
        document_version_id=document_version_id,
    )
    source_hash = _text_sha256(canonical_text)
    cache_key = content_sha256(
        {
            "owner": owner.cache_value(),
            "source_type": source_type,
            "source_hash": source_hash,
            "text_extraction_version": text_extraction_version,
            "ocr_version": ocr_version,
            "canonicalization_version": canonicalization_version,
        }
    )
    existing = db.scalar(select(CanonicalSource).where(CanonicalSource.cache_key == cache_key))
    if existing is not None:
        return existing

    _validate_spans(canonical_text, spans)
    source = CanonicalSource(
        public_id=f"src_{uuid.uuid4().hex}",
        owner_kind=owner.kind,
        workspace_id=owner.workspace_id,
        user_id=owner.user_id,
        guest_trial_id=owner.guest_trial_id,
        source_type=source_type,
        resume_profile_id=resume_profile_id,
        guest_resume_profile_id=guest_resume_profile_id,
        document_version_id=document_version_id,
        source_hash=source_hash,
        canonical_text=canonical_text,
        text_extraction_version=text_extraction_version,
        ocr_version=ocr_version,
        canonicalization_version=canonicalization_version,
        language=language,
        cache_key=cache_key,
    )
    source, created = _insert_unique_or_get(db, source, CanonicalSource, cache_key)
    if not created:
        return source
    for ordinal, span in enumerate(spans):
        db.add(
            SourceSpan(
                canonical_source_id=source.id,
                span_id=span.span_id,
                section=span.section,
                ordinal=ordinal,
                start_utf8_byte=span.start_utf8_byte,
                end_utf8_byte=span.end_utf8_byte,
                excerpt=span.excerpt,
            )
        )
    db.flush()
    return source


def create_or_get_candidate_profile(
    db: Session,
    *,
    source: CanonicalSource,
    artifact: CandidateExtractionResponse,
    model_id: str,
    provider_execution_reference: str | None = None,
    resume_profile_id: int | None = None,
    schema_version: str = "candidate-profile.v1",
    response_schema_version: str = "candidate-extract-response.v1",
    prompt_version: str = "candidate-extract.v1",
    taxonomy_version: str = "matching-taxonomy.v1",
    semantic_validator_version: str = "matching-semantic-validator.v1",
) -> CandidateProfileVersion:
    if source.source_type != "resume":
        raise ValueError("Candidate Profiles require a canonical resume source.")
    if resume_profile_id is not None and source.resume_profile_id != resume_profile_id:
        raise ArtifactOwnershipError("Resume profile does not own the canonical source.")
    allowed_refs = set(
        db.scalars(select(SourceSpan.span_id).where(SourceSpan.canonical_source_id == source.id)).all()
    )
    unknown_refs = _collect_reference_values(artifact.model_dump(mode="json"), "evidence_refs") - allowed_refs
    if unknown_refs:
        raise ValueError(f"Candidate Profile contains unknown evidence references: {sorted(unknown_refs)}")
    cache_key, response_schema_hash = candidate_profile_cache_identity(
        source=source,
        model_id=model_id,
        schema_version=schema_version,
        response_schema_version=response_schema_version,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy_version,
        semantic_validator_version=semantic_validator_version,
    )
    existing = db.scalar(
        select(CandidateProfileVersion).where(CandidateProfileVersion.cache_key == cache_key)
    )
    if existing is not None:
        return existing

    profile = CandidateProfileVersion(
        public_id=f"cp_{uuid.uuid4().hex}",
        canonical_source_id=source.id,
        resume_profile_id=resume_profile_id,
        schema_version=schema_version,
        response_schema_hash=response_schema_hash,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy_version,
        semantic_validator_version=semantic_validator_version,
        model_id=model_id,
        provider_execution_reference=provider_execution_reference,
        artifact=artifact.model_dump(mode="json"),
        quality=artifact.quality.model_dump(mode="json"),
        recommended_primary_career_profile_ref=artifact.recommended_primary_career_profile_ref,
        cache_key=cache_key,
    )
    profile, created = _insert_unique_or_get(db, profile, CandidateProfileVersion, cache_key)
    if not created:
        return profile

    rows_by_local_ref: dict[str, CandidateCareerProfile] = {}
    for extracted in artifact.career_profiles:
        row = CandidateCareerProfile(
            candidate_profile_version_id=profile.id,
            career_profile_id=_career_profile_id(profile.public_id, extracted.local_ref),
            local_ref=extracted.local_ref,
            role_family=extracted.role_family,
            track=extracted.track,
            level=extracted.level,
            confidence=extracted.confidence,
            evidence_refs=extracted.evidence_refs,
            dimension_signals=extracted.dimension_signals.model_dump(mode="json"),
        )
        db.add(row)
        rows_by_local_ref[extracted.local_ref] = row
    db.flush()

    recommended = rows_by_local_ref[artifact.recommended_primary_career_profile_ref]
    db.add(
        CandidateCareerSelection(
            candidate_profile_version_id=profile.id,
            revision=1,
            candidate_career_profile_id=recommended.id,
            selection_source="model_default",
        )
    )
    db.flush()
    return profile


def find_cached_candidate_profile(
    db: Session,
    *,
    source: CanonicalSource,
    model_id: str,
    schema_version: str = "candidate-profile.v1",
    response_schema_version: str = "candidate-extract-response.v1",
    prompt_version: str = "candidate-extract.v1",
    taxonomy_version: str = "matching-taxonomy.v1",
    semantic_validator_version: str = "matching-semantic-validator.v1",
) -> CandidateProfileVersion | None:
    cache_key, _ = candidate_profile_cache_identity(
        source=source,
        model_id=model_id,
        schema_version=schema_version,
        response_schema_version=response_schema_version,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy_version,
        semantic_validator_version=semantic_validator_version,
    )
    return db.scalar(
        select(CandidateProfileVersion).where(
            CandidateProfileVersion.cache_key == cache_key,
            CandidateProfileVersion.deleted_at.is_(None),
        )
    )


def create_or_get_job_profile(
    db: Session,
    *,
    source: CanonicalSource,
    artifact: JobExtractionResponse,
    model_id: str,
    jobs_cache_id: int,
    provider_execution_reference: str | None = None,
    schema_version: str = "job-profile.v3",
    response_schema_version: str = "job-extract-response.v3",
    prompt_version: str = "job-extract.v3",
    taxonomy_version: str = "matching-taxonomy.v2",
    source_policy_version: str = "cached-job-reuse.v1",
    deduplication_version: str = "job-dedup.v2",
    semantic_validator_version: str = "matching-semantic-validator.v3",
) -> JobProfileVersion:
    from app.modules.jobs.models import JobCache

    if source.source_type != "job" or source.owner_kind != "shared":
        raise ValueError("Job Profiles require a shared canonical job source.")
    cache_job = db.get(JobCache, jobs_cache_id)
    if cache_job is None or cache_job.deleted_at is not None or not cache_job.raw_description_text.strip():
        raise ValueError("An active cached job with usable source text is required.")
    allowed_refs = set(db.scalars(
        select(SourceSpan.span_id).where(SourceSpan.canonical_source_id == source.id)
    ).all())
    refs = _collect_reference_values(artifact.model_dump(mode="json"), "source_refs")
    refs |= _collect_reference_values(artifact.model_dump(mode="json"), "evidence_refs")
    unknown_refs = refs - allowed_refs
    if unknown_refs:
        raise ValueError(f"Job Profile contains unknown source references: {sorted(unknown_refs)}")
    cache_key, response_schema_hash = job_profile_cache_identity(
        source=source,
        model_id=model_id,
        schema_version=schema_version,
        response_schema_version=response_schema_version,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy_version,
        source_policy_version=source_policy_version,
        deduplication_version=deduplication_version,
        semantic_validator_version=semantic_validator_version,
    )
    existing = db.scalar(select(JobProfileVersion).where(JobProfileVersion.cache_key == cache_key))
    if existing is not None:
        return existing
    profile = JobProfileVersion(
        public_id=f"jp_{uuid.uuid4().hex}",
        canonical_source_id=source.id,
        jobs_cache_id=jobs_cache_id,
        schema_version=schema_version,
        response_schema_hash=response_schema_hash,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy_version,
        source_policy_version=source_policy_version,
        deduplication_version=deduplication_version,
        semantic_validator_version=semantic_validator_version,
        model_id=model_id,
        provider_execution_reference=provider_execution_reference,
        artifact=artifact.model_dump(mode="json"),
        cleanup=artifact.cleanup.model_dump(mode="json"),
        cache_key=cache_key,
    )
    profile, created = _insert_unique_or_get(db, profile, JobProfileVersion, cache_key)
    if not created:
        return profile
    for item in artifact.requirements:
        db.add(JobRequirement(
            job_profile_version_id=profile.id,
            requirement_id=_job_requirement_id(profile.public_id, item.local_ref),
            local_ref=item.local_ref,
            category=item.category,
            scoring_dimension=item.scoring_dimension,
            statement=item.statement,
            importance=item.importance,
            # Legacy storage/qualification adapter. Job Profile v3 has no hard constraints.
            hard_constraint=False,
            acceptable_evidence_contexts=item.acceptable_evidence_contexts,
            minimum_years=item.minimum_years,
            explicit_alternatives=[
                " or ".join(group.any_of) for group in item.alternative_groups
            ],
            policy_alternative_group=item.policy_alternative_group,
            source_refs=item.source_refs,
        ))
    db.flush()
    return profile


def find_cached_job_profile(
    db: Session,
    *,
    source: CanonicalSource,
    model_id: str,
    schema_version: str = "job-profile.v3",
    response_schema_version: str = "job-extract-response.v3",
    prompt_version: str = "job-extract.v3",
    taxonomy_version: str = "matching-taxonomy.v2",
    source_policy_version: str = "cached-job-reuse.v1",
    deduplication_version: str = "job-dedup.v2",
    semantic_validator_version: str = "matching-semantic-validator.v3",
) -> JobProfileVersion | None:
    cache_key, _ = job_profile_cache_identity(
        source=source,
        model_id=model_id,
        schema_version=schema_version,
        response_schema_version=response_schema_version,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy_version,
        source_policy_version=source_policy_version,
        deduplication_version=deduplication_version,
        semantic_validator_version=semantic_validator_version,
    )
    return db.scalar(select(JobProfileVersion).where(
        JobProfileVersion.cache_key == cache_key,
        JobProfileVersion.deleted_at.is_(None),
    ))


def job_profile_cache_identity(
    *,
    source: CanonicalSource,
    model_id: str,
    schema_version: str,
    response_schema_version: str,
    prompt_version: str,
    taxonomy_version: str,
    source_policy_version: str,
    deduplication_version: str,
    semantic_validator_version: str,
) -> tuple[str, str]:
    schema_entry = DEFAULT_REGISTRY.get("response_schema", response_schema_version)
    DEFAULT_REGISTRY.get("prompt", prompt_version)
    DEFAULT_REGISTRY.get("taxonomy", taxonomy_version)
    DEFAULT_REGISTRY.get("source_reuse_policy", source_policy_version)
    DEFAULT_REGISTRY.get("deduplication_policy", deduplication_version)
    DEFAULT_REGISTRY.get("semantic_validator", semantic_validator_version)
    return content_sha256({
        "canonical_source_public_id": source.public_id,
        "schema_version": schema_version,
        "response_schema_hash": schema_entry.content_hash,
        "prompt_version": prompt_version,
        "taxonomy_version": taxonomy_version,
        "source_policy_version": source_policy_version,
        "deduplication_version": deduplication_version,
        "semantic_validator_version": semantic_validator_version,
        "model_id": model_id,
    }), schema_entry.content_hash


def get_job_profile_by_public_id(db: Session, *, public_id: str) -> JobProfileVersion | None:
    from app.modules.jobs.models import JobCache

    return db.scalar(select(JobProfileVersion).join(
        CanonicalSource, CanonicalSource.id == JobProfileVersion.canonical_source_id
    ).join(
        JobCache, JobCache.id == JobProfileVersion.jobs_cache_id
    ).where(
        JobProfileVersion.public_id == public_id,
        JobProfileVersion.deleted_at.is_(None),
        CanonicalSource.owner_kind == "shared",
        CanonicalSource.source_type == "job",
        JobCache.deleted_at.is_(None),
        JobCache.lifecycle_state == "active",
        (JobCache.expires_at.is_(None) | (JobCache.expires_at > func.now())),
        JobCache.raw_description_text != "",
    ))


def create_or_get_qualification_assessment(
    db: Session,
    *,
    owner: ArtifactOwner,
    candidate_profile: CandidateProfileVersion,
    career_selection: CandidateCareerSelection | None,
    selected_career_profile: CandidateCareerProfile | None,
    selection_reason_code: str,
    job_profile: JobProfileVersion,
    artifact: QualificationAssessmentResponse,
    input_quality: dict,
    model_id: str,
    job_family_pre_match: JobFamilyPreMatch | None = None,
    provider_execution_reference: str | None = None,
    schema_version: str = "qualification-assessment.v2",
    response_schema_version: str = "qualification-assessment-response.v2",
    prompt_version: str = "qualification-match.v3",
    selection_policy_version: str = "career-selection-policy.v2",
    matching_policy_version: str = "qualification-policy.v2",
    input_policy_version: str = "qualification-input.v2",
    semantic_validator_version: str = "matching-semantic-validator.v4",
) -> QualificationAssessment:
    if owner.kind == "shared":
        raise ArtifactOwnershipError("Qualification Assessments must have a private owner.")
    if not _candidate_profile_belongs_to_owner(db, candidate_profile, owner):
        raise ArtifactOwnershipError("Candidate Profile does not belong to qualification owner.")
    if career_selection is None and job_family_pre_match is None:
        raise ValueError("Qualification requires a career selection or Job Family Pre-Match.")
    if career_selection is not None and job_family_pre_match is not None:
        raise ValueError("Qualification career context is ambiguous.")
    if career_selection is not None and career_selection.candidate_profile_version_id != candidate_profile.id:
        raise ArtifactOwnershipError("Career selection does not belong to Candidate Profile.")
    if job_family_pre_match is not None and (
        job_family_pre_match.candidate_profile_version_id != candidate_profile.id
        or job_family_pre_match.job_profile_version_id != job_profile.id
        or job_family_pre_match.workspace_id != owner.workspace_id
        or job_family_pre_match.user_id != owner.user_id
    ):
        raise ArtifactOwnershipError("Job Family Pre-Match does not belong to qualification inputs.")
    if selected_career_profile is not None and (
        selected_career_profile.candidate_profile_version_id != candidate_profile.id
    ):
        raise ArtifactOwnershipError("Selected career context does not belong to Candidate Profile.")
    if job_family_pre_match is not None:
        selection_policy_version = job_family_pre_match.policy_version
    source = db.get(CanonicalSource, job_profile.canonical_source_id)
    if source is None or source.owner_kind != "shared" or source.source_type != "job":
        raise ArtifactOwnershipError("Job Profile is not reusable shared data.")
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job_profile.id
    )).all())
    by_public_id = {item.requirement_id: item for item in requirements}
    returned_ids = {item.requirement_id for item in artifact.requirement_assessments}
    if returned_ids != set(by_public_id):
        raise ValueError("Qualification Assessment does not cover the Job Profile requirements.")
    cache_key, response_schema_hash, alternative_hashes = qualification_cache_identity(
        candidate_profile=candidate_profile,
        selection_revision=career_selection.revision if career_selection else None,
        job_family_pre_match=job_family_pre_match,
        job_profile=job_profile,
        requirements=requirements,
        model_id=model_id,
        schema_version=schema_version,
        response_schema_version=response_schema_version,
        prompt_version=prompt_version,
        selection_policy_version=selection_policy_version,
        matching_policy_version=matching_policy_version,
        input_policy_version=input_policy_version,
        semantic_validator_version=semantic_validator_version,
    )
    existing = db.scalar(select(QualificationAssessment).where(
        QualificationAssessment.cache_key == cache_key
    ))
    if existing is not None:
        return existing
    assessment = QualificationAssessment(
        public_id=f"qa_{uuid.uuid4().hex}",
        owner_kind=owner.kind,
        workspace_id=owner.workspace_id,
        user_id=owner.user_id,
        guest_trial_id=owner.guest_trial_id,
        candidate_profile_version_id=candidate_profile.id,
        candidate_career_selection_id=career_selection.id if career_selection else None,
        candidate_career_selection_revision=career_selection.revision if career_selection else None,
        job_family_pre_match_id=job_family_pre_match.id if job_family_pre_match else None,
        selected_candidate_career_profile_id=(
            selected_career_profile.id if selected_career_profile is not None else None
        ),
        selection_reason_code=selection_reason_code,
        job_profile_version_id=job_profile.id,
        schema_version=schema_version,
        response_schema_hash=response_schema_hash,
        prompt_version=prompt_version,
        selection_policy_version=selection_policy_version,
        matching_policy_version=matching_policy_version,
        input_policy_version=input_policy_version,
        semantic_validator_version=semantic_validator_version,
        alternative_policy_hashes=alternative_hashes,
        model_id=model_id,
        provider_execution_reference=provider_execution_reference,
        artifact=artifact.model_dump(mode="json"),
        input_quality=input_quality,
        cache_key=cache_key,
    )
    assessment, created = _insert_unique_or_get(
        db, assessment, QualificationAssessment, cache_key
    )
    if not created:
        return assessment
    for item in artifact.requirement_assessments:
        requirement = by_public_id[item.requirement_id]
        db.add(RequirementAssessment(
            qualification_assessment_id=assessment.id,
            job_requirement_id=requirement.id,
            requirement_id=item.requirement_id,
            collection_kind="normal",
            status=item.status,
            confidence=item.confidence,
            evidence_refs=item.evidence_refs,
            alternative_group_refs=item.alternative_group_refs,
            alternative_policy_ref=item.alternative_policy_ref,
            reason=item.reason,
            missing=item.missing,
        ))
    db.flush()
    return assessment


def find_cached_qualification_assessment(
    db: Session,
    *,
    candidate_profile: CandidateProfileVersion,
    selection_revision: int | None,
    job_profile: JobProfileVersion,
    model_id: str,
    job_family_pre_match: JobFamilyPreMatch | None = None,
    schema_version: str = "qualification-assessment.v2",
    response_schema_version: str = "qualification-assessment-response.v2",
    prompt_version: str = "qualification-match.v3",
    selection_policy_version: str = "career-selection-policy.v2",
    matching_policy_version: str = "qualification-policy.v2",
    input_policy_version: str = "qualification-input.v2",
    semantic_validator_version: str = "matching-semantic-validator.v4",
) -> QualificationAssessment | None:
    if job_family_pre_match is not None:
        selection_policy_version = job_family_pre_match.policy_version
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job_profile.id
    )).all())
    cache_key, _, _ = qualification_cache_identity(
        candidate_profile=candidate_profile,
        selection_revision=selection_revision,
        job_family_pre_match=job_family_pre_match,
        job_profile=job_profile,
        requirements=requirements,
        model_id=model_id,
        schema_version=schema_version,
        response_schema_version=response_schema_version,
        prompt_version=prompt_version,
        selection_policy_version=selection_policy_version,
        matching_policy_version=matching_policy_version,
        input_policy_version=input_policy_version,
        semantic_validator_version=semantic_validator_version,
    )
    return db.scalar(select(QualificationAssessment).where(
        QualificationAssessment.cache_key == cache_key,
        QualificationAssessment.deleted_at.is_(None),
    ))


def qualification_cache_identity(
    *,
    candidate_profile: CandidateProfileVersion,
    selection_revision: int | None,
    job_profile: JobProfileVersion,
    requirements: list[JobRequirement],
    model_id: str,
    schema_version: str,
    response_schema_version: str,
    prompt_version: str,
    selection_policy_version: str,
    matching_policy_version: str,
    input_policy_version: str,
    semantic_validator_version: str,
    job_family_pre_match: JobFamilyPreMatch | None = None,
) -> tuple[str, str, dict[str, str]]:
    schema = DEFAULT_REGISTRY.get("response_schema", response_schema_version)
    prompt = DEFAULT_REGISTRY.get("prompt", prompt_version)
    selection = (
        DEFAULT_REGISTRY.get("job_family_pre_match_policy", selection_policy_version)
        if job_family_pre_match is not None
        else DEFAULT_REGISTRY.get("career_selection_policy", selection_policy_version)
    )
    matching = DEFAULT_REGISTRY.get("qualification_policy", matching_policy_version)
    input_policy = DEFAULT_REGISTRY.get("input_policy", input_policy_version)
    semantic = DEFAULT_REGISTRY.get("semantic_validator", semantic_validator_version)
    alternative_hashes = {
        version: DEFAULT_REGISTRY.get("alternative_policy", version).content_hash
        for version in sorted({
            item.policy_alternative_group
            for item in requirements
            if item.policy_alternative_group is not None
        })
    }
    return (
        content_sha256({
            "candidate_profile_id": candidate_profile.public_id,
            "candidate_career_selection_revision": selection_revision,
            "job_family_pre_match_id": job_family_pre_match.public_id if job_family_pre_match else None,
            "job_family_pre_match_policy_hash": job_family_pre_match.policy_hash if job_family_pre_match else None,
            "job_profile_id": job_profile.public_id,
            "schema_version": schema_version,
            "response_schema_hash": schema.content_hash,
            "prompt_hash": prompt.content_hash,
            "selection_policy_hash": selection.content_hash,
            "matching_policy_hash": matching.content_hash,
            "input_policy_hash": input_policy.content_hash,
            "semantic_validator_hash": semantic.content_hash,
            "alternative_policy_hashes": alternative_hashes,
            "model_id": model_id,
        }),
        schema.content_hash,
        alternative_hashes,
    )


def get_qualification_assessment_for_owner(
    db: Session, *, public_id: str, owner: ArtifactOwner
) -> QualificationAssessment | None:
    return db.scalar(select(QualificationAssessment).where(
        QualificationAssessment.public_id == public_id,
        QualificationAssessment.deleted_at.is_(None),
        QualificationAssessment.owner_kind == owner.kind,
        QualificationAssessment.workspace_id.is_(owner.workspace_id)
        if owner.workspace_id is None
        else QualificationAssessment.workspace_id == owner.workspace_id,
        QualificationAssessment.user_id.is_(owner.user_id)
        if owner.user_id is None
        else QualificationAssessment.user_id == owner.user_id,
        QualificationAssessment.guest_trial_id.is_(owner.guest_trial_id)
        if owner.guest_trial_id is None
        else QualificationAssessment.guest_trial_id == owner.guest_trial_id,
    ))


def candidate_profile_cache_identity(
    *,
    source: CanonicalSource,
    model_id: str,
    schema_version: str,
    response_schema_version: str,
    prompt_version: str,
    taxonomy_version: str,
    semantic_validator_version: str,
) -> tuple[str, str]:
    schema_entry = DEFAULT_REGISTRY.get("response_schema", response_schema_version)
    DEFAULT_REGISTRY.get("prompt", prompt_version)
    DEFAULT_REGISTRY.get("taxonomy", taxonomy_version)
    DEFAULT_REGISTRY.get("semantic_validator", semantic_validator_version)
    return (
        content_sha256(
            {
                "canonical_source_public_id": source.public_id,
                "schema_version": schema_version,
                "response_schema_hash": schema_entry.content_hash,
                "prompt_version": prompt_version,
                "taxonomy_version": taxonomy_version,
                "semantic_validator_version": semantic_validator_version,
                "model_id": model_id,
            }
        ),
        schema_entry.content_hash,
    )


def get_candidate_profile_for_owner(
    db: Session,
    *,
    public_id: str,
    owner: ArtifactOwner,
) -> CandidateProfileVersion | None:
    return db.scalar(
        select(CandidateProfileVersion)
        .join(CanonicalSource, CanonicalSource.id == CandidateProfileVersion.canonical_source_id)
        .where(
            CandidateProfileVersion.public_id == public_id,
            CandidateProfileVersion.deleted_at.is_(None),
            *_owner_conditions(owner),
        )
    )


def create_career_selection(
    db: Session,
    *,
    candidate_profile_public_id: str,
    owner: ArtifactOwner,
    expected_revision: int,
    career_profile_id: str | None,
    selection_source: str,
) -> CandidateCareerSelection:
    if selection_source not in {"model_default", "user_confirmed", "operator_corrected"}:
        raise ValueError("Unsupported career selection source.")
    profile = get_candidate_profile_for_owner(
        db,
        public_id=candidate_profile_public_id,
        owner=owner,
    )
    if profile is None:
        raise ArtifactOwnershipError("Candidate Profile not found for owner.")
    current_revision = db.scalar(
        select(func.max(CandidateCareerSelection.revision)).where(
            CandidateCareerSelection.candidate_profile_version_id == profile.id
        )
    ) or 0
    if current_revision != expected_revision:
        raise RevisionConflict(
            f"Expected career selection revision {expected_revision}; current revision is {current_revision}."
        )

    selected_row_id: int | None = None
    if career_profile_id is not None:
        career = db.scalar(
            select(CandidateCareerProfile).where(
                CandidateCareerProfile.candidate_profile_version_id == profile.id,
                CandidateCareerProfile.career_profile_id == career_profile_id,
            )
        )
        if career is None:
            raise ValueError("Career profile does not belong to Candidate Profile.")
        selected_row_id = career.id

    selection = CandidateCareerSelection(
        candidate_profile_version_id=profile.id,
        revision=current_revision + 1,
        candidate_career_profile_id=selected_row_id,
        selection_source=selection_source,
    )
    db.add(selection)
    db.flush()
    return selection


def sync_policy_registry(
    db: Session,
    registry: ImmutableRegistry = DEFAULT_REGISTRY,
) -> list[PromptPolicyRegistryRecord]:
    records: list[PromptPolicyRegistryRecord] = []
    for entry in registry.entries():
        existing = db.scalar(
            select(PromptPolicyRegistryRecord).where(
                PromptPolicyRegistryRecord.artifact_type == entry.artifact_type,
                PromptPolicyRegistryRecord.version == entry.version,
            )
        )
        metadata = json.loads(canonical_json(entry.metadata))
        if existing is not None:
            if existing.content_hash != entry.content_hash or existing.metadata_json != metadata:
                raise ValueError(
                    f"Persisted registry version differs from code: {(entry.artifact_type, entry.version)}"
                )
            records.append(existing)
            continue
        record = PromptPolicyRegistryRecord(
            artifact_type=entry.artifact_type,
            version=entry.version,
            content_hash=entry.content_hash,
            content=json.loads(canonical_json(entry.content)),
            metadata_json=metadata,
        )
        db.add(record)
        records.append(record)
    db.flush()
    return records


def _owner_conditions(owner: ArtifactOwner) -> tuple:
    return (
        CanonicalSource.owner_kind == owner.kind,
        CanonicalSource.workspace_id.is_(owner.workspace_id)
        if owner.workspace_id is None
        else CanonicalSource.workspace_id == owner.workspace_id,
        CanonicalSource.user_id.is_(owner.user_id)
        if owner.user_id is None
        else CanonicalSource.user_id == owner.user_id,
        CanonicalSource.guest_trial_id.is_(owner.guest_trial_id)
        if owner.guest_trial_id is None
        else CanonicalSource.guest_trial_id == owner.guest_trial_id,
    )


def _candidate_profile_belongs_to_owner(
    db: Session, candidate_profile: CandidateProfileVersion, owner: ArtifactOwner
) -> bool:
    return db.scalar(select(CandidateProfileVersion.id).join(
        CanonicalSource, CanonicalSource.id == CandidateProfileVersion.canonical_source_id
    ).where(
        CandidateProfileVersion.id == candidate_profile.id,
        *_owner_conditions(owner),
    )) is not None


def _validate_source_links(
    db: Session,
    *,
    owner: ArtifactOwner,
    source_type: str,
    resume_profile_id: int | None,
    guest_resume_profile_id: int | None,
    document_version_id: int | None,
) -> None:
    from app.modules.guest_trials.models import GuestResumeProfile
    from app.modules.profiles.models import ResumeProfile

    if source_type == "job" and (resume_profile_id is not None or guest_resume_profile_id is not None):
        raise ArtifactOwnershipError("A job source cannot reference a resume profile.")
    if resume_profile_id is not None:
        profile = db.get(ResumeProfile, resume_profile_id)
        if (
            profile is None
            or owner.kind != "authenticated"
            or profile.workspace_id != owner.workspace_id
            or profile.user_id != owner.user_id
            or profile.deleted_at is not None
        ):
            raise ArtifactOwnershipError("Resume profile does not belong to the artifact owner.")
        if document_version_id is not None and profile.source_document_version_id != document_version_id:
            raise ArtifactOwnershipError("Document version does not belong to the resume profile.")
    if guest_resume_profile_id is not None:
        guest_profile = db.get(GuestResumeProfile, guest_resume_profile_id)
        if (
            guest_profile is None
            or owner.kind != "guest"
            or guest_profile.guest_trial_id != owner.guest_trial_id
        ):
            raise ArtifactOwnershipError("Guest resume profile does not belong to the artifact owner.")


def _collect_reference_values(value: object, key: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for nested_key, nested in value.items():
            if nested_key == key and isinstance(nested, list):
                found.update(item for item in nested if isinstance(item, str))
            else:
                found.update(_collect_reference_values(nested, key))
    elif isinstance(value, list):
        for nested in value:
            found.update(_collect_reference_values(nested, key))
    return found


def _validate_spans(canonical_text: str, spans: list[SpanInput]) -> None:
    source_bytes = canonical_text.encode("utf-8")
    seen: set[str] = set()
    for span in spans:
        if span.span_id in seen:
            raise ValueError(f"Duplicate source span ID: {span.span_id}")
        seen.add(span.span_id)
        if span.start_utf8_byte < 0 or span.end_utf8_byte <= span.start_utf8_byte:
            raise ValueError(f"Invalid source span range: {span.span_id}")
        if span.end_utf8_byte > len(source_bytes):
            raise ValueError(f"Source span exceeds canonical text: {span.span_id}")
        try:
            excerpt = source_bytes[span.start_utf8_byte : span.end_utf8_byte].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Source span splits a UTF-8 code point: {span.span_id}") from exc
        if excerpt != span.excerpt:
            raise ValueError(f"Source span excerpt does not match canonical text: {span.span_id}")


def _text_sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _career_profile_id(candidate_profile_public_id: str, local_ref: str) -> str:
    digest = hashlib.sha256(f"{candidate_profile_public_id}:{local_ref}".encode("utf-8")).hexdigest()[:24]
    return f"career_{digest}"


def _job_requirement_id(job_profile_public_id: str, local_ref: str) -> str:
    digest = hashlib.sha256(f"{job_profile_public_id}:{local_ref}".encode("utf-8")).hexdigest()[:24]
    return f"req_{digest}"
