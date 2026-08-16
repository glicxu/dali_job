from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.auth.service import token_hash
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.guest_trials.models import (
    GuestDocument,
    GuestMatchCandidate,
    GuestMatchOperation,
    GuestMatchResult,
    GuestProviderAttempt,
    GuestResumeProfile,
    GuestSearchCriterion,
    GuestTrial,
)
from app.modules.guest_trials.schemas import GuestCriteriaUpdateRequest, GuestProfileUpdateRequest
from app.modules.profiles.readiness import READINESS_VERSION, evaluate_profile_readiness
from app.modules.profiles.repository import create_resume_profile, ensure_account_for_identity
from app.modules.profiles.schemas import ResumeData, ResumeProfileCreateRequest

ACTIVE_GUEST_LIFETIME = timedelta(hours=24)


@dataclass(frozen=True)
class CreatedGuestTrial:
    trial: GuestTrial
    secret: str

    @property
    def credential(self) -> str:
        return f"{self.trial.public_id}.{self.secret}"


@dataclass(frozen=True)
class GuestPurgeResult:
    eligible: int
    purged: int
    files_deleted: int
    files_missing: int
    failed_trials: int
    dry_run: bool


@dataclass(frozen=True)
class ClaimedGuestTrial:
    resume_profile_id: int
    search_criterion_id: int
    candidate_profile_id: str
    qualification_assessment_id: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def create_guest_trial(db: Session, *, now: datetime | None = None) -> CreatedGuestTrial:
    created_at = now or utc_now()
    secret = secrets.token_urlsafe(48)
    trial = GuestTrial(
        public_id=secrets.token_urlsafe(18),
        secret_hash=token_hash(secret),
        status="active",
        readiness_version=READINESS_VERSION,
        provider_search_state="available",
        created_at=created_at,
        last_used_at=created_at,
        expires_at=created_at + ACTIVE_GUEST_LIFETIME,
    )
    db.add(trial)
    db.flush()
    return CreatedGuestTrial(trial=trial, secret=secret)


def resolve_guest_trial(
    db: Session,
    credential: str,
    *,
    now: datetime | None = None,
) -> GuestTrial | None:
    public_id, separator, secret = credential.partition(".")
    if not separator or not public_id or not secret:
        return None
    trial = db.scalar(select(GuestTrial).where(GuestTrial.public_id == public_id).limit(1))
    if trial is None or trial.deleted_at is not None:
        return None
    if not hmac.compare_digest(trial.secret_hash, token_hash(secret)):
        return None

    current = now or utc_now()
    if trial.status == "expired" or _as_utc(trial.expires_at) <= current:
        trial.status = "expired"
        return None
    if trial.status == "claimed":
        return None

    trial.last_used_at = current
    if trial.status != "claim_pending":
        trial.expires_at = current + ACTIVE_GUEST_LIFETIME
    db.flush()
    return trial


def get_guest_profile(db: Session, trial: GuestTrial) -> GuestResumeProfile | None:
    return db.scalar(select(GuestResumeProfile).where(GuestResumeProfile.guest_trial_id == trial.id).limit(1))


def put_guest_profile(
    db: Session,
    trial: GuestTrial,
    payload: GuestProfileUpdateRequest,
) -> GuestResumeProfile:
    readiness = evaluate_profile_readiness(payload.resume_data)
    profile = get_guest_profile(db, trial)
    if profile is None:
        profile = GuestResumeProfile(guest_trial_id=trial.id)
        db.add(profile)
    document = get_guest_document(db, trial)
    profile.source_guest_document_id = document.id if document else None
    profile.resume_data = payload.resume_data.model_dump()
    profile.readiness_pathway = readiness.pathway
    profile.evidence_summary = readiness.evidence_summary.model_dump()
    db.flush()
    db.refresh(profile)
    return profile


def get_guest_criteria(db: Session, trial: GuestTrial) -> GuestSearchCriterion | None:
    return db.scalar(select(GuestSearchCriterion).where(GuestSearchCriterion.guest_trial_id == trial.id).limit(1))


def get_guest_document(db: Session, trial: GuestTrial) -> GuestDocument | None:
    return db.scalar(select(GuestDocument).where(GuestDocument.guest_trial_id == trial.id).limit(1))


def put_guest_document(
    db: Session,
    trial: GuestTrial,
    *,
    file_name: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    storage_path: str,
    extracted_text: str,
) -> tuple[GuestDocument, str | None]:
    document = get_guest_document(db, trial)
    previous_storage_path = document.storage_path if document else None
    if document is None:
        document = GuestDocument(guest_trial_id=trial.id)
        db.add(document)
    document.file_name = file_name
    document.content_type = content_type
    document.size_bytes = size_bytes
    document.sha256 = sha256
    document.storage_path = storage_path
    document.extracted_text = extracted_text
    document.parse_status = "pending"
    document.parse_suggestions = None
    document.parser_provenance = None
    db.flush()
    db.refresh(document)
    return document, previous_storage_path


def record_guest_document_parse(
    db: Session,
    document: GuestDocument,
    *,
    suggestions: dict | None,
    provenance: dict,
) -> GuestDocument:
    document.parse_status = "succeeded" if suggestions is not None else "failed"
    document.parse_suggestions = suggestions
    document.parser_provenance = provenance
    db.flush()
    db.refresh(document)
    return document


def put_guest_criteria(
    db: Session,
    trial: GuestTrial,
    payload: GuestCriteriaUpdateRequest,
) -> GuestSearchCriterion:
    criterion = get_guest_criteria(db, trial)
    if criterion is None:
        criterion = GuestSearchCriterion(guest_trial_id=trial.id)
        db.add(criterion)
    criterion.keyword = payload.keyword
    criterion.location = payload.location
    db.flush()
    db.refresh(criterion)
    return criterion


def claim_guest_trial(
    db: Session,
    *,
    credential: str,
    identity: AuthenticatedIdentity,
) -> ClaimedGuestTrial:
    from app.modules.job_search.models import JobSearchCriterion
    from app.modules.matching_v2.models import (
        CandidateProfileVersion,
        CanonicalSource,
        JobProfileVersion,
        QualificationAssessment,
        SourceSpan,
    )
    from app.modules.matching_v2.qualification import select_candidate_career_context
    from app.modules.matching_v2.repositories import (
        ArtifactOwner,
        SpanInput,
        create_or_get_candidate_profile,
        create_or_get_canonical_source,
        create_or_get_qualification_assessment,
        sync_policy_registry,
    )
    from app.modules.matching_v2.schemas import CandidateExtractionResponse, QualificationAssessmentResponse

    public_id, separator, secret = credential.strip().partition(".")
    if not separator or not public_id or not secret:
        raise ValueError("INVALID_GUEST_CREDENTIAL")
    trial = db.scalar(select(GuestTrial).where(GuestTrial.public_id == public_id).with_for_update())
    if trial is None or trial.deleted_at is not None:
        raise ValueError("INVALID_GUEST_CREDENTIAL")
    if not hmac.compare_digest(trial.secret_hash, token_hash(secret)):
        raise ValueError("INVALID_GUEST_CREDENTIAL")
    if trial.status != "claimed" and (
        trial.status == "expired" or _as_utc(trial.expires_at) <= utc_now()
    ):
        trial.status = "expired"
        raise ValueError("INVALID_GUEST_CREDENTIAL")

    user, workspace = ensure_account_for_identity(db, identity)
    if trial.status == "claimed":
        if trial.claimed_user_id != user.id:
            raise ValueError("GUEST_TRIAL_ALREADY_CLAIMED")
        return _claimed_mapping(db, trial)
    if trial.status != "result_ready":
        raise ValueError("GUEST_RESULT_NOT_READY")

    guest_profile = get_guest_profile(db, trial)
    criterion = get_guest_criteria(db, trial)
    result = get_guest_match_result(db, trial)
    if guest_profile is None or criterion is None or result is None:
        raise ValueError("GUEST_RESULT_NOT_READY")
    original_candidate = db.get(CandidateProfileVersion, result.candidate_profile_version_id)
    original_qualification = db.get(QualificationAssessment, result.qualification_assessment_id)
    if original_candidate is None or original_qualification is None:
        raise ValueError("GUEST_ARTIFACTS_UNAVAILABLE")
    original_source = db.get(CanonicalSource, original_candidate.canonical_source_id)
    job_profile = db.get(JobProfileVersion, original_qualification.job_profile_version_id)
    if original_source is None or job_profile is None:
        raise ValueError("GUEST_ARTIFACTS_UNAVAILABLE")

    resume = create_resume_profile(
        db,
        ResumeProfileCreateRequest(
            title="Saved trial profile",
            resume_data=ResumeData.model_validate(guest_profile.resume_data),
        ),
        identity,
    )
    saved_criterion = JobSearchCriterion(
        workspace_id=workspace.id,
        user_id=user.id,
        resume_profile_id=resume.id,
        keyword=criterion.keyword,
        location=criterion.location,
        source="guest_claim",
        last_used_at=utc_now(),
    )
    db.add(saved_criterion)
    db.flush()

    spans = list(
        db.scalars(
            select(SourceSpan)
            .where(SourceSpan.canonical_source_id == original_source.id)
            .order_by(SourceSpan.ordinal)
        ).all()
    )
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    claimed_source = create_or_get_canonical_source(
        db,
        owner=owner,
        source_type="resume",
        canonical_text=original_source.canonical_text,
        text_extraction_version=original_source.text_extraction_version,
        canonicalization_version=original_source.canonicalization_version,
        ocr_version=original_source.ocr_version,
        language=original_source.language,
        resume_profile_id=resume.id,
        spans=[
            SpanInput(
                span_id=item.span_id,
                section=item.section,
                start_utf8_byte=item.start_utf8_byte,
                end_utf8_byte=item.end_utf8_byte,
                excerpt=item.excerpt,
            )
            for item in spans
        ],
    )
    sync_policy_registry(db)
    claimed_candidate = create_or_get_candidate_profile(
        db,
        source=claimed_source,
        artifact=CandidateExtractionResponse.model_validate(original_candidate.artifact),
        model_id=original_candidate.model_id,
        provider_execution_reference=original_candidate.provider_execution_reference,
        resume_profile_id=resume.id,
        schema_version=original_candidate.schema_version,
        prompt_version=original_candidate.prompt_version,
        taxonomy_version=original_candidate.taxonomy_version,
        semantic_validator_version=original_candidate.semantic_validator_version,
    )
    context = select_candidate_career_context(
        db,
        candidate_profile=claimed_candidate,
        job_profile=job_profile,
        selection_revision=1,
    )
    claimed_qualification = create_or_get_qualification_assessment(
        db,
        owner=owner,
        candidate_profile=claimed_candidate,
        career_selection=context.selection,
        selected_career_profile=context.career_profile,
        selection_reason_code=context.reason_code,
        job_profile=job_profile,
        artifact=QualificationAssessmentResponse.model_validate(original_qualification.artifact),
        input_quality=original_qualification.input_quality,
        model_id=original_qualification.model_id,
        provider_execution_reference=original_qualification.provider_execution_reference,
        schema_version=original_qualification.schema_version,
        prompt_version=original_qualification.prompt_version,
        selection_policy_version=original_qualification.selection_policy_version,
        matching_policy_version=original_qualification.matching_policy_version,
        input_policy_version=original_qualification.input_policy_version,
        semantic_validator_version=original_qualification.semantic_validator_version,
    )

    trial.status = "claimed"
    trial.claimed_user_id = user.id
    trial.claimed_at = utc_now()
    trial.claim_pending_until = None
    trial.claimed_resume_profile_id = resume.id
    trial.claimed_search_criterion_id = saved_criterion.id
    trial.claimed_candidate_profile_id = claimed_candidate.id
    trial.claimed_qualification_assessment_id = claimed_qualification.id
    db.flush()
    return ClaimedGuestTrial(
        resume_profile_id=resume.id,
        search_criterion_id=saved_criterion.id,
        candidate_profile_id=claimed_candidate.public_id,
        qualification_assessment_id=claimed_qualification.public_id,
    )


def get_guest_match_result(db: Session, trial: GuestTrial):
    from app.modules.guest_trials.models import GuestMatchResult

    return db.scalar(
        select(GuestMatchResult).where(GuestMatchResult.guest_trial_id == trial.id).limit(1)
    )


def _claimed_mapping(db: Session, trial: GuestTrial) -> ClaimedGuestTrial:
    from app.modules.matching_v2.models import CandidateProfileVersion, QualificationAssessment

    candidate = db.get(CandidateProfileVersion, trial.claimed_candidate_profile_id)
    qualification = db.get(QualificationAssessment, trial.claimed_qualification_assessment_id)
    if (
        trial.claimed_resume_profile_id is None
        or trial.claimed_search_criterion_id is None
        or candidate is None
        or qualification is None
    ):
        raise ValueError("GUEST_CLAIM_MAPPING_UNAVAILABLE")
    return ClaimedGuestTrial(
        resume_profile_id=trial.claimed_resume_profile_id,
        search_criterion_id=trial.claimed_search_criterion_id,
        candidate_profile_id=candidate.public_id,
        qualification_assessment_id=qualification.public_id,
    )


def delete_guest_trial(db: Session, trial: GuestTrial, *, storage_root: str | None = None) -> bool:
    from app.modules.guest_trials.storage import delete_guest_document_file

    documents = list(db.scalars(select(GuestDocument).where(GuestDocument.guest_trial_id == trial.id)).all())
    if storage_root:
        for document in documents:
            outcome = delete_guest_document_file(storage_root, document.storage_path)
            if outcome == "outside_guest_root":
                return False
    db.execute(delete(GuestResumeProfile).where(GuestResumeProfile.guest_trial_id == trial.id))
    db.execute(delete(GuestSearchCriterion).where(GuestSearchCriterion.guest_trial_id == trial.id))
    db.execute(delete(GuestDocument).where(GuestDocument.guest_trial_id == trial.id))
    db.execute(delete(GuestMatchResult).where(GuestMatchResult.guest_trial_id == trial.id))
    db.execute(delete(GuestMatchCandidate).where(GuestMatchCandidate.guest_trial_id == trial.id))
    db.execute(delete(GuestProviderAttempt).where(GuestProviderAttempt.guest_trial_id == trial.id))
    db.execute(delete(GuestMatchOperation).where(GuestMatchOperation.guest_trial_id == trial.id))
    _delete_guest_v2_artifacts(db, trial.id)
    db.delete(trial)
    db.flush()
    return True


def purge_expired_guest_trials(
    db: Session,
    *,
    now: datetime | None = None,
    storage_root: str | None = None,
) -> int:
    return purge_expired_guest_trial_batch(
        db,
        now=now,
        storage_root=storage_root,
        limit=10_000,
    ).purged


def purge_expired_guest_trial_batch(
    db: Session,
    *,
    storage_root: str | None,
    limit: int = 100,
    now: datetime | None = None,
    dry_run: bool = False,
) -> GuestPurgeResult:
    from app.modules.guest_trials.storage import delete_guest_document_file

    if limit < 1 or limit > 10_000:
        raise ValueError("limit must be between 1 and 10000")
    current = now or utc_now()
    candidate_ids = list(
        db.scalars(
            select(GuestTrial.id)
            .where(
                (GuestTrial.expires_at <= current)
                | (GuestTrial.status == "expired")
                | (GuestTrial.deleted_at.is_not(None))
            )
            .order_by(GuestTrial.expires_at, GuestTrial.id)
            .limit(limit)
        ).all()
    )
    if dry_run or not candidate_ids:
        return GuestPurgeResult(
            eligible=len(candidate_ids),
            purged=0,
            files_deleted=0,
            files_missing=0,
            failed_trials=0,
            dry_run=dry_run,
        )

    purged = 0
    files_deleted = 0
    files_missing = 0
    failed_trials = 0
    for trial_id in candidate_ids:
        documents = list(
            db.scalars(select(GuestDocument).where(GuestDocument.guest_trial_id == trial_id)).all()
        )
        if documents and not storage_root:
            failed_trials += 1
            continue
        try:
            outcomes = [delete_guest_document_file(storage_root, item.storage_path) for item in documents]
        except OSError:
            failed_trials += 1
            continue
        if "outside_guest_root" in outcomes:
            failed_trials += 1
            continue
        files_deleted += outcomes.count("deleted")
        files_missing += outcomes.count("missing")
        db.execute(delete(GuestResumeProfile).where(GuestResumeProfile.guest_trial_id == trial_id))
        db.execute(delete(GuestSearchCriterion).where(GuestSearchCriterion.guest_trial_id == trial_id))
        db.execute(delete(GuestDocument).where(GuestDocument.guest_trial_id == trial_id))
        db.execute(delete(GuestMatchResult).where(GuestMatchResult.guest_trial_id == trial_id))
        db.execute(delete(GuestMatchCandidate).where(GuestMatchCandidate.guest_trial_id == trial_id))
        db.execute(delete(GuestProviderAttempt).where(GuestProviderAttempt.guest_trial_id == trial_id))
        db.execute(delete(GuestMatchOperation).where(GuestMatchOperation.guest_trial_id == trial_id))
        _delete_guest_v2_artifacts(db, trial_id)
        db.execute(delete(GuestTrial).where(GuestTrial.id == trial_id))
        purged += 1

    return GuestPurgeResult(
        eligible=len(candidate_ids),
        purged=purged,
        files_deleted=files_deleted,
        files_missing=files_missing,
        failed_trials=failed_trials,
        dry_run=False,
    )


def _delete_guest_v2_artifacts(db: Session, trial_id: int) -> None:
    from app.modules.matching_v2.models import (
        CandidateCareerProfile,
        CandidateCareerSelection,
        CandidateProfileVersion,
        CanonicalSource,
        QualificationAssessment,
        RequirementAssessment,
        SourceSpan,
    )

    qualification_ids = select(QualificationAssessment.id).where(
        QualificationAssessment.guest_trial_id == trial_id
    )
    db.execute(
        delete(RequirementAssessment).where(
            RequirementAssessment.qualification_assessment_id.in_(qualification_ids)
        )
    )
    db.execute(
        delete(QualificationAssessment).where(QualificationAssessment.guest_trial_id == trial_id)
    )
    source_ids = select(CanonicalSource.id).where(CanonicalSource.guest_trial_id == trial_id)
    candidate_ids = select(CandidateProfileVersion.id).where(
        CandidateProfileVersion.canonical_source_id.in_(source_ids)
    )
    db.execute(
        delete(CandidateCareerSelection).where(
            CandidateCareerSelection.candidate_profile_version_id.in_(candidate_ids)
        )
    )
    db.execute(
        delete(CandidateCareerProfile).where(
            CandidateCareerProfile.candidate_profile_version_id.in_(candidate_ids)
        )
    )
    db.execute(
        delete(CandidateProfileVersion).where(CandidateProfileVersion.id.in_(candidate_ids))
    )
    db.execute(delete(SourceSpan).where(SourceSpan.canonical_source_id.in_(source_ids)))
    db.execute(delete(CanonicalSource).where(CanonicalSource.guest_trial_id == trial_id))
