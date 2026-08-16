from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.matching_v2.eligibility import CandidateEligibilityFacts, evaluate_eligibility
from app.modules.matching_v2.explanations import render_match_explanation
from app.modules.matching_v2.models import (
    EligibilityAssessment,
    EligibilityRevision,
    JobProfileVersion,
    JobRequirement,
    MatchResult,
    PreferenceAssessment,
    PreferenceRevision,
    QualificationAssessment,
)
from app.modules.matching_v2.preferences import (
    JobPreferenceFacts,
    PreferenceAssessmentItem,
    UserPreferences,
    evaluate_preferences,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, content_sha256
from app.modules.matching_v2.repositories import ArtifactOwner, ArtifactOwnershipError, RevisionConflict
from app.modules.matching_v2.scoring import GateResult, QualificationScoreItem, score_match
from app.modules.matching_v2.schemas import JobApplicationConstraintsResponse, QualificationAssessmentResponse
from app.modules.matching_v2.sensitive import (
    ENCRYPTION_VERSION,
    decrypt_eligibility_payload,
    eligibility_payload_hash,
    encrypt_eligibility_payload,
)


def _authenticated(owner: ArtifactOwner) -> tuple[int, int]:
    if owner.kind != "authenticated" or owner.workspace_id is None or owner.user_id is None:
        raise ArtifactOwnershipError("Phase 5 revisions require an authenticated owner.")
    return owner.workspace_id, owner.user_id


def create_preference_revision(db: Session, *, owner: ArtifactOwner, expected_revision: int, artifact: UserPreferences) -> PreferenceRevision:
    workspace_id, user_id = _authenticated(owner)
    current = db.scalar(select(func.max(PreferenceRevision.revision)).where(PreferenceRevision.user_id == user_id)) or 0
    if current != expected_revision:
        raise RevisionConflict(f"Expected preference revision {expected_revision}; current revision is {current}.")
    payload = artifact.model_dump(mode="json")
    row = PreferenceRevision(public_id=f"pref_{uuid.uuid4().hex}", workspace_id=workspace_id, user_id=user_id, revision=current + 1, schema_version="user-preferences.v1", artifact=payload, content_hash=content_sha256(payload))
    db.add(row)
    db.flush()
    return row


def create_eligibility_revision(db: Session, *, owner: ArtifactOwner, expected_revision: int, artifact: CandidateEligibilityFacts) -> EligibilityRevision:
    workspace_id, user_id = _authenticated(owner)
    current = db.scalar(select(func.max(EligibilityRevision.revision)).where(EligibilityRevision.user_id == user_id)) or 0
    if current != expected_revision:
        raise RevisionConflict(f"Expected eligibility revision {expected_revision}; current revision is {current}.")
    payload = artifact.model_dump(mode="json")
    row = EligibilityRevision(public_id=f"elig_{uuid.uuid4().hex}", workspace_id=workspace_id, user_id=user_id, revision=current + 1, schema_version="candidate-eligibility-facts.v1", encrypted_artifact=encrypt_eligibility_payload(payload), encryption_version=ENCRYPTION_VERSION, content_hash=eligibility_payload_hash(payload))
    db.add(row)
    db.flush()
    return row


def latest_preference_revision(db: Session, *, owner: ArtifactOwner) -> PreferenceRevision | None:
    workspace_id, user_id = _authenticated(owner)
    return db.scalar(select(PreferenceRevision).where(PreferenceRevision.workspace_id == workspace_id, PreferenceRevision.user_id == user_id).order_by(PreferenceRevision.revision.desc()))


def latest_eligibility_revision(db: Session, *, owner: ArtifactOwner) -> EligibilityRevision | None:
    workspace_id, user_id = _authenticated(owner)
    return db.scalar(select(EligibilityRevision).where(EligibilityRevision.workspace_id == workspace_id, EligibilityRevision.user_id == user_id).order_by(EligibilityRevision.revision.desc()))


def eligibility_artifact(row: EligibilityRevision) -> CandidateEligibilityFacts:
    return CandidateEligibilityFacts.model_validate(decrypt_eligibility_payload(row.encrypted_artifact))


def _revision(db: Session, model, *, owner: ArtifactOwner, revision: int):
    workspace_id, user_id = _authenticated(owner)
    row = db.scalar(select(model).where(model.workspace_id == workspace_id, model.user_id == user_id, model.revision == revision))
    if row is None:
        raise ArtifactOwnershipError("Requested revision was not found for owner.")
    return row


def _job_facts(job: dict) -> JobPreferenceFacts:
    career = job.get("career_context") or {}
    location = job.get("location") or {}
    compensation = job.get("compensation") or {}
    requirements = job.get("requirements") or []
    return JobPreferenceFacts(
        role_family=str(career.get("primary_role_family", "unknown")), title=str(job.get("title", "unknown")),
        canonical_location=location.get("display"), workplace_type=location.get("workplace_type", "unknown"), remote_regions=location.get("remote_regions", []),
        compensation_currency=compensation.get("currency"), compensation_period=compensation.get("period"), compensation_minimum=compensation.get("minimum"), compensation_maximum=compensation.get("maximum"),
        employment_type=str(job.get("employment_type", "unknown")), skills=[str(item.get("statement", "")) for item in requirements], industry=job.get("industry"),
        relevant_skills_complete=not any("OMITTED" in str(warning) for warning in (job.get("cleanup") or {}).get("warnings", [])),
    )


def _preference_assessment(db: Session, *, owner: ArtifactOwner, job: JobProfileVersion, revision: PreferenceRevision) -> PreferenceAssessment:
    workspace_id, user_id = _authenticated(owner)
    policy = DEFAULT_REGISTRY.get("deterministic_policy", "preference-policy.v1")
    selection_policy = DEFAULT_REGISTRY.get("career_selection_policy", "career-selection-policy.v2")
    taxonomy = DEFAULT_REGISTRY.get("taxonomy", "matching-taxonomy.v2")
    alternative_policy = DEFAULT_REGISTRY.get("alternative_policy", "general-purpose-programming-language.v2")
    cache_key = content_sha256({"job": job.cache_key, "revision": revision.content_hash, "policy": policy.content_hash, "role_relationships": selection_policy.content_hash, "taxonomy": taxonomy.content_hash, "skill_relationships": alternative_policy.content_hash})
    existing = db.scalar(select(PreferenceAssessment).where(PreferenceAssessment.cache_key == cache_key))
    if existing is not None:
        return existing
    adjacent_roles = {
        (role, adjacent)
        for role, values in selection_policy.content["adjacent_role_families"].items()
        for adjacent in values
    }
    language_members = list(alternative_policy.content["members"])
    related_skills = {
        (left, right)
        for left in language_members
        for right in language_members
        if left != right
    }
    artifact = evaluate_preferences(
        UserPreferences.model_validate(revision.artifact),
        _job_facts(job.artifact),
        adjacent_role_families=adjacent_roles,
        related_skills=related_skills,
    )
    row = PreferenceAssessment(public_id=f"pa_{uuid.uuid4().hex}", workspace_id=workspace_id, user_id=user_id, job_profile_version_id=job.id, preference_revision_id=revision.id, policy_version=policy.version, policy_hash=policy.content_hash, artifact=artifact.model_dump(mode="json"), cache_key=cache_key)
    db.add(row)
    db.flush()
    return row


def _eligibility_assessment(db: Session, *, owner: ArtifactOwner, job: JobProfileVersion, revision: EligibilityRevision | None) -> EligibilityAssessment:
    workspace_id, user_id = _authenticated(owner)
    policy = DEFAULT_REGISTRY.get("deterministic_policy", "eligibility-policy.v1")
    cache_key = content_sha256({"owner": owner.cache_value(), "job": job.cache_key, "revision": revision.content_hash if revision else "not_configured", "policy": policy.content_hash})
    existing = db.scalar(select(EligibilityAssessment).where(EligibilityAssessment.cache_key == cache_key))
    if existing is not None:
        return existing
    artifact = evaluate_eligibility(JobApplicationConstraintsResponse.model_validate(job.artifact["application_constraints"]), eligibility_artifact(revision) if revision else None, job_country=(job.artifact.get("location") or {}).get("country"))
    row = EligibilityAssessment(public_id=f"ea_{uuid.uuid4().hex}", workspace_id=workspace_id, user_id=user_id, job_profile_version_id=job.id, eligibility_revision_id=revision.id if revision else None, policy_version=policy.version, policy_hash=policy.content_hash, artifact=artifact.model_dump(mode="json"), cache_key=cache_key)
    db.add(row)
    db.flush()
    return row


def create_or_get_match_result(db: Session, *, owner: ArtifactOwner, qualification_public_id: str, preference_revision: int | None, eligibility_revision: int | None, legacy_adapter_enabled: bool) -> MatchResult:
    workspace_id, user_id = _authenticated(owner)
    qualification = db.scalar(select(QualificationAssessment).where(QualificationAssessment.public_id == qualification_public_id, QualificationAssessment.workspace_id == workspace_id, QualificationAssessment.user_id == user_id, QualificationAssessment.deleted_at.is_(None)))
    if qualification is None:
        raise ArtifactOwnershipError("Qualification Assessment not found for owner.")
    job = db.get(JobProfileVersion, qualification.job_profile_version_id)
    if job is None:
        raise ValueError("Job Profile is unavailable.")
    pref_revision = _revision(db, PreferenceRevision, owner=owner, revision=preference_revision) if preference_revision is not None else None
    elig_revision = _revision(db, EligibilityRevision, owner=owner, revision=eligibility_revision) if eligibility_revision is not None else None
    pref_assessment = _preference_assessment(db, owner=owner, job=job, revision=pref_revision) if pref_revision else None
    elig_assessment = _eligibility_assessment(db, owner=owner, job=job, revision=elig_revision)
    requirements = list(db.scalars(select(JobRequirement).where(JobRequirement.job_profile_version_id == job.id)).all())
    by_id = {item.requirement_id: item for item in requirements}
    qa = QualificationAssessmentResponse.model_validate(qualification.artifact)
    qualification_items = [QualificationScoreItem(requirement_id=item.requirement_id, importance=by_id[item.requirement_id].importance, scoring_dimension=by_id[item.requirement_id].scoring_dimension, status=item.status) for item in qa.requirement_assessments]
    pref_artifact = pref_assessment.artifact if pref_assessment else {"items": [], "hard_constraint_results": []}
    preference_items = [PreferenceAssessmentItem.model_validate(item) for item in pref_artifact.get("items", [])]
    gates = [GateResult.model_validate(item) for item in [*pref_artifact.get("hard_constraint_results", []), *elig_assessment.artifact.get("items", [])]]
    career = job.artifact["career_context"]
    score = score_match(role_family=career["primary_role_family"], track=career["track"], target_level=career["target_level"], level_confidence=career["confidence"], qualification_items=qualification_items, preference_items=preference_items, gates=gates)
    explanation = render_match_explanation(qualification_items=qa.requirement_assessments, requirement_statements={item.requirement_id: item.statement for item in requirements}, preference_items=preference_items, gates=score.gates, score=score)
    policies = {"qualification": qualification.matching_policy_version, "preference": "preference-policy.v1", "eligibility": "eligibility-policy.v1", "role_track": score.role_track_policy_version, "scoring": score.scoring_policy_version, "explanation": explanation.renderer_version}
    cache_key = content_sha256({"qualification": qualification.cache_key, "preference": pref_assessment.cache_key if pref_assessment else "not_configured", "eligibility": elig_assessment.cache_key, "policies": policies})
    existing = db.scalar(select(MatchResult).where(MatchResult.cache_key == cache_key))
    if existing is not None:
        return existing
    legacy_score = max(0, min(10, int((score.overall_score + 5) // 10))) if legacy_adapter_enabled and score.overall_score is not None else None
    result = MatchResult(public_id=f"match_{uuid.uuid4().hex}", workspace_id=workspace_id, user_id=user_id, qualification_assessment_id=qualification.id, preference_assessment_id=pref_assessment.id if pref_assessment else None, eligibility_assessment_id=elig_assessment.id, score_artifact=score.model_dump(mode="json"), explanation_artifact=explanation.model_dump(mode="json"), policy_versions=policies, legacy_score=legacy_score, cache_key=cache_key)
    db.add(result)
    db.flush()
    return result


def get_match_result(db: Session, *, owner: ArtifactOwner, public_id: str) -> MatchResult | None:
    workspace_id, user_id = _authenticated(owner)
    return db.scalar(select(MatchResult).where(MatchResult.public_id == public_id, MatchResult.workspace_id == workspace_id, MatchResult.user_id == user_id))
