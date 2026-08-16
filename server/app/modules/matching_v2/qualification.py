from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import get_provider_secret
from app.modules.matching_v2.diagnostics import (
    record_model_error,
    record_model_request,
    record_model_response,
    record_validation_error,
)
from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateCareerSelection,
    CandidateProfileVersion,
    JobProfileVersion,
    JobRequirement,
    SourceSpan,
)
from app.modules.matching_v2.prompts import (
    QUALIFICATION_SYSTEM_PROMPT,
    build_qualification_repair_user_prompt,
    build_qualification_user_prompt,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, canonical_json
from app.modules.matching_v2.schemas import QualificationAssessmentResponse, qualification_response_format

MAX_QUALIFICATION_INPUT_BYTES = 100_000
_POSITIVE_STATUSES = {"met", "met_by_alternative", "partially_met"}
_DIMENSION_SIGNALS = {
    "technical_skill": ("technical_depth",),
    "applied_experience": ("scope_and_complexity", "ownership"),
    "production_delivery": ("production_delivery",),
    "system_design_architecture": ("system_design",),
    "mentoring_leadership": ("mentoring", "ownership"),
    "organizational_influence": ("cross_team_influence",),
    "education_credential": (),
    "domain_knowledge": ("technical_depth",),
}
_DEMONSTRATED_SIGNALS = {"limited", "developing", "demonstrated", "advanced"}


@dataclass(frozen=True)
class CareerContextSelection:
    selection: CandidateCareerSelection
    career_profile: CandidateCareerProfile | None
    reason_code: str


@dataclass(frozen=True)
class QualificationInput:
    candidate_profile: dict
    candidate_evidence: tuple[dict, ...]
    job_requirements: tuple[dict, ...]
    approved_alternatives: tuple[dict, ...]
    allowed_evidence_refs: frozenset[str]
    omitted_evidence_refs: tuple[str, ...]
    selected_career_context: dict | None
    allowed_alternative_group_refs: dict[str, frozenset[str]]


@dataclass(frozen=True)
class QualificationResult:
    artifact: QualificationAssessmentResponse
    model_id: str
    provider_execution_reference: str | None
    retry_count: int = 0


class QualificationMatcher(Protocol):
    def assess(self, qualification_input: QualificationInput) -> QualificationResult:
        ...

    def repair(
        self,
        qualification_input: QualificationInput,
        errors: tuple[dict[str, str], ...],
    ) -> QualificationResult:
        ...


class OpenAIQualificationMatcher:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def assess(self, qualification_input: QualificationInput) -> QualificationResult:
        requirement_ids = [item["requirement_id"] for item in qualification_input.job_requirements]
        if not requirement_ids:
            return QualificationResult(
                artifact=QualificationAssessmentResponse(
                    requirement_assessments=[]
                ),
                model_id=self._model,
                provider_execution_reference=None,
            )
        if not qualification_input.allowed_evidence_refs:
            return QualificationResult(
                artifact=_not_demonstrated_artifact(qualification_input.job_requirements),
                model_id=self._model,
                provider_execution_reference=None,
            )
        user_prompt = build_qualification_user_prompt(
            candidate_profile=qualification_input.candidate_profile,
            candidate_evidence=qualification_input.candidate_evidence,
            job_requirements=qualification_input.job_requirements,
            approved_alternatives=qualification_input.approved_alternatives,
            career_context=qualification_input.selected_career_context,
        )
        response_format = {
            "type": "json_schema",
            "json_schema": qualification_response_format(
                allowed_requirement_ids=requirement_ids,
                allowed_evidence_refs=sorted(qualification_input.allowed_evidence_refs),
            ),
        }
        return self._request(user_prompt=user_prompt, response_format=response_format, retry_count=0)

    def repair(
        self,
        qualification_input: QualificationInput,
        errors: tuple[dict[str, str], ...],
    ) -> QualificationResult:
        requirement_ids = [item["requirement_id"] for item in qualification_input.job_requirements]
        user_prompt = build_qualification_repair_user_prompt(
            candidate_profile=qualification_input.candidate_profile,
            candidate_evidence=qualification_input.candidate_evidence,
            job_requirements=qualification_input.job_requirements,
            approved_alternatives=qualification_input.approved_alternatives,
            career_context=qualification_input.selected_career_context,
            errors=errors,
        )
        response_format = {
            "type": "json_schema",
            "json_schema": qualification_response_format(
                allowed_requirement_ids=requirement_ids,
                allowed_evidence_refs=sorted(qualification_input.allowed_evidence_refs),
            ),
        }
        return self._request(user_prompt=user_prompt, response_format=response_format, retry_count=1)

    def _request(
        self,
        *,
        user_prompt: str,
        response_format: dict,
        retry_count: int,
    ) -> QualificationResult:
        record_model_request(
            stage="qualification",
            model=self._model,
            system_prompt=QUALIFICATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=response_format,
        )
        try:
            response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": QUALIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_format,
            )
        except Exception as exc:
            record_model_error(stage="qualification", model=self._model, error=exc)
            raise
        content = response.choices[0].message.content
        record_model_response(
            stage="qualification",
            model=self._model,
            provider_response_id=getattr(response, "id", None),
            content=content,
        )
        if content is None:
            raise HTTPException(status_code=502, detail="The qualification provider returned an empty response.")
        try:
            artifact = QualificationAssessmentResponse.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            record_validation_error(stage="qualification", model=self._model, error=exc)
            raise HTTPException(status_code=502, detail="The qualification provider returned an invalid response.") from exc
        return QualificationResult(
            artifact=artifact,
            model_id=self._model,
            provider_execution_reference=getattr(response, "id", None),
            retry_count=retry_count,
        )


def select_candidate_career_context(
    db: Session,
    *,
    candidate_profile: CandidateProfileVersion,
    job_profile: JobProfileVersion,
    selection_revision: int,
) -> CareerContextSelection:
    selection = db.scalar(select(CandidateCareerSelection).where(
        CandidateCareerSelection.candidate_profile_version_id == candidate_profile.id,
        CandidateCareerSelection.revision == selection_revision,
    ))
    if selection is None:
        raise ValueError("Candidate career selection revision was not found.")
    careers = list(db.scalars(select(CandidateCareerProfile).where(
        CandidateCareerProfile.candidate_profile_version_id == candidate_profile.id
    )).all())
    primary = next(
        (item for item in careers if item.id == selection.candidate_career_profile_id),
        None,
    )
    job_context = job_profile.artifact["career_context"]
    selection_policy = DEFAULT_REGISTRY.get("career_selection_policy", "career-selection-policy.v2").content
    compatible = set(selection_policy["compatible_tracks"].get(job_context["track"], ()))
    approved_adjacent = set(selection_policy["adjacent_role_families"].get(
        job_context["primary_role_family"], ()
    ))
    extracted_adjacent = set(job_context.get("adjacent_role_families", ()))
    adjacent = approved_adjacent & extracted_adjacent
    requirement_dimensions = {
        item.scoring_dimension
        for item in db.scalars(select(JobRequirement).where(
            JobRequirement.job_profile_version_id == job_profile.id
        )).all()
    }

    ranked: list[tuple[int, int, float, str, str, CandidateCareerProfile]] = []
    for career in careers:
        if career.role_family == job_context["primary_role_family"] and career.track == job_context["track"]:
            match_class, reason = 1, "EXACT_ROLE_FAMILY_AND_TRACK"
        elif career.role_family == job_context["primary_role_family"] and career.track in compatible:
            match_class, reason = 2, "EXACT_ROLE_FAMILY_COMPATIBLE_TRACK"
        elif career.role_family in adjacent and career.track == job_context["track"]:
            match_class, reason = 3, "ADJACENT_ROLE_FAMILY_EXACT_TRACK"
        elif career.role_family in adjacent and career.track in compatible:
            match_class, reason = 4, "ADJACENT_ROLE_FAMILY_COMPATIBLE_TRACK"
        elif primary is not None and career.id == primary.id:
            match_class, reason = 5, "PRIMARY_SELECTION_FALLBACK"
        else:
            continue
        coverage = _career_dimension_coverage(career, requirement_dimensions)
        ranked.append((match_class, -coverage, -career.confidence, career.career_profile_id, reason, career))
    if not ranked:
        return CareerContextSelection(selection=selection, career_profile=None, reason_code="NO_RELEVANT_CAREER_CONTEXT")
    chosen = min(ranked)
    return CareerContextSelection(selection=selection, career_profile=chosen[-1], reason_code=chosen[-2])


def build_qualification_input(
    db: Session,
    *,
    candidate_profile: CandidateProfileVersion,
    job_profile: JobProfileVersion,
    career_context: CandidateCareerProfile | None,
    maximum_bytes: int = MAX_QUALIFICATION_INPUT_BYTES,
) -> QualificationInput:
    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive.")
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job_profile.id
    ).order_by(JobRequirement.id)).all())
    profile_requirements = {
        str(item.get("local_ref")): item
        for item in job_profile.artifact.get("requirements", [])
        if isinstance(item, dict)
    }
    alternative_refs: dict[str, frozenset[str]] = {}
    job_items_list = []
    for item in requirements:
        profile_item = profile_requirements.get(item.local_ref, {})
        groups = _job_alternative_groups(profile_item, item.explicit_alternatives, item.source_refs)
        alternative_refs[item.requirement_id] = frozenset(
            str(group["local_ref"]) for group in groups
        )
        job_items_list.append({
            "requirement_id": item.requirement_id,
            "statement": item.statement,
            "importance": "required" if item.importance == "required" else "optional",
            "scoring_dimension": item.scoring_dimension,
            "acceptable_evidence_contexts": item.acceptable_evidence_contexts,
            "minimum_years": item.minimum_years,
            "alternative_groups": groups,
            "policy_alternative_group": item.policy_alternative_group,
        })
    job_items = tuple(job_items_list)
    alternatives: list[dict] = []
    for item in requirements:
        if item.policy_alternative_group:
            policy = DEFAULT_REGISTRY.get("alternative_policy", item.policy_alternative_group)
            alternatives.append({
                "requirement_id": item.requirement_id,
                "kind": "approved_policy",
                "policy_ref": policy.version,
                "policy_hash": policy.content_hash,
                "policy": json.loads(canonical_json(policy.content)),
            })
    selected = None if career_context is None else {
        "career_profile_id": career_context.career_profile_id,
        "role_family": career_context.role_family,
        "track": career_context.track,
        "level": career_context.level,
    }
    candidate_artifact = _candidate_qualification_profile(candidate_profile.artifact)
    base_bytes = len(build_qualification_user_prompt(
        candidate_profile=candidate_artifact,
        candidate_evidence=[],
        job_requirements=job_items,
        approved_alternatives=alternatives,
        career_context=selected,
    ).encode("utf-8"))
    if base_bytes > maximum_bytes:
        raise ValueError("Job requirements exceed the qualification input limit.")

    supported_refs = _candidate_non_derived_refs(candidate_profile.artifact)
    source_spans = list(db.scalars(select(SourceSpan).where(
        SourceSpan.canonical_source_id == candidate_profile.canonical_source_id,
        SourceSpan.span_id.in_(supported_refs),
    ).order_by(SourceSpan.ordinal)).all()) if supported_refs else []
    evidence: list[dict] = []
    omitted: list[str] = []
    for span in source_spans:
        item = {"span_id": span.span_id, "section": span.section, "excerpt": span.excerpt}
        prospective_size = len(build_qualification_user_prompt(
            candidate_profile=candidate_artifact,
            candidate_evidence=[*evidence, item],
            job_requirements=job_items,
            approved_alternatives=alternatives,
            career_context=selected,
        ).encode("utf-8"))
        if prospective_size <= maximum_bytes:
            evidence.append(item)
        else:
            omitted.append(span.span_id)
    return QualificationInput(
        candidate_profile=candidate_artifact,
        candidate_evidence=tuple(evidence),
        job_requirements=job_items,
        approved_alternatives=tuple(alternatives),
        allowed_evidence_refs=frozenset(item["span_id"] for item in evidence),
        omitted_evidence_refs=tuple(omitted),
        selected_career_context=selected,
        allowed_alternative_group_refs=alternative_refs,
    )


def validate_qualification_assessment(
    artifact: QualificationAssessmentResponse,
    *,
    requirements: list[JobRequirement],
    allowed_evidence_refs: set[str] | frozenset[str],
    incomplete_evidence_input: bool = False,
    allowed_alternative_group_refs: dict[str, frozenset[str]] | None = None,
) -> QualificationAssessmentResponse:
    by_id = {item.requirement_id: item for item in requirements}
    expected_ids = set(by_id)
    returned = [item.requirement_id for item in artifact.requirement_assessments]
    if len(returned) != len(set(returned)) or set(returned) != expected_ids:
        raise ValueError("Qualification response must assess every requirement exactly once.")
    group_refs = allowed_alternative_group_refs or {
        item.requirement_id: frozenset() for item in requirements
    }
    items_by_id = {item.requirement_id: item for item in artifact.requirement_assessments}
    normalized = []
    for requirement in requirements:
        item = items_by_id[requirement.requirement_id]
        allowed_groups = group_refs.get(item.requirement_id, frozenset())
        unknown_refs = set(item.evidence_refs) - set(allowed_evidence_refs)
        if unknown_refs:
            raise ValueError(f"Qualification contains unknown evidence references: {sorted(unknown_refs)}")
        if item.status in _POSITIVE_STATUSES and not item.evidence_refs:
            raise ValueError(f"Qualification status {item.status} requires candidate evidence.")
        if item.status == "not_demonstrated" and item.evidence_refs:
            raise ValueError("not_demonstrated cannot cite evidence as support.")
        if item.status == "met" and allowed_groups:
            item = item.model_copy(update={
                "status": "met_by_alternative",
                "alternative_group_refs": sorted(allowed_groups),
            })
        if item.status == "met_by_alternative":
            returned_groups = set(item.alternative_group_refs)
            group_ok = bool(returned_groups) and returned_groups <= set(allowed_groups)
            policy_ok = bool(
                item.alternative_policy_ref
                and item.alternative_policy_ref == requirement.policy_alternative_group
                and _registered_alternative(item.alternative_policy_ref)
            )
            if not (group_ok or policy_ok):
                raise ValueError("met_by_alternative requires a supplied group or approved policy.")
        elif item.alternative_group_refs or item.alternative_policy_ref is not None:
            raise ValueError("Alternative references are valid only for met_by_alternative.")
        if item.status == "partially_met" and not item.missing:
            raise ValueError("partially_met must identify material missing evidence.")
        if item.status in {"met", "met_by_alternative"} and item.missing:
            raise ValueError(f"{item.status} cannot report missing qualification evidence.")
        if item.status == "not_demonstrated" and not item.missing:
            raise ValueError("not_demonstrated must identify evidence needed to demonstrate the requirement.")
        if incomplete_evidence_input and item.status == "not_demonstrated":
            item = item.model_copy(update={
                "reason": "Available candidate evidence did not demonstrate the requirement; some evidence was omitted.",
                "missing": list(dict.fromkeys([*item.missing, "Review omitted candidate evidence"])),
            })
        normalized.append(item.model_copy(update={
            "evidence_refs": list(dict.fromkeys(item.evidence_refs)),
            "alternative_group_refs": list(dict.fromkeys(item.alternative_group_refs)),
            "missing": list(dict.fromkeys(item.missing)),
        }))
    return QualificationAssessmentResponse(requirement_assessments=normalized)


def _candidate_non_derived_refs(artifact: dict) -> set[str]:
    refs: set[str] = set()
    for key in (
        "skills", "experience", "projects", "education", "certifications", "publications",
        "awards", "patents", "languages",
    ):
        for item in artifact.get(key, []):
            refs.update(ref for ref in item.get("evidence_refs", []) if isinstance(ref, str))
    return refs


def _candidate_qualification_profile(artifact: dict) -> dict:
    """Return only evidence-bearing Candidate Profile collections; derived text stays excluded."""

    return {
        key: artifact.get(key, [])
        for key in (
            "skills", "experience", "projects", "education", "certifications", "publications",
            "awards", "patents", "languages",
        )
    }


def _job_alternative_groups(
    profile_requirement: dict, legacy_alternatives: list[str], source_refs: list[str]
) -> list[dict]:
    groups = profile_requirement.get("alternative_groups")
    if isinstance(groups, list):
        return [dict(group) for group in groups if isinstance(group, dict)]
    if not legacy_alternatives:
        return []
    members = legacy_alternatives if len(legacy_alternatives) > 1 else [
        part.strip()
        for part in re.split(r"\s*(?:\bor\b|/|,)\s*", legacy_alternatives[0], flags=re.I)
        if part.strip()
    ]
    members = list(dict.fromkeys(members))
    if len(members) < 2:
        return []
    local_ref = str(profile_requirement.get("local_ref") or "requirement")
    return [{
        "local_ref": f"{local_ref}_alternatives",
        "any_of": members,
        "source_refs": source_refs,
    }]


def _career_dimension_coverage(career: CandidateCareerProfile, dimensions: set[str]) -> int:
    return sum(
        any(career.dimension_signals.get(signal) in _DEMONSTRATED_SIGNALS for signal in _DIMENSION_SIGNALS[dimension])
        for dimension in dimensions
    )


def _registered_alternative(version: str) -> bool:
    try:
        DEFAULT_REGISTRY.get("alternative_policy", version)
    except KeyError:
        return False
    return True


def _not_demonstrated_artifact(job_requirements: tuple[dict, ...]) -> QualificationAssessmentResponse:
    assessments = []
    for requirement in job_requirements:
        item = {
            "requirement_id": requirement["requirement_id"],
            "status": "not_demonstrated",
            "confidence": 1.0,
            "evidence_refs": [],
            "alternative_group_refs": [],
            "alternative_policy_ref": None,
            "reason": "No supporting candidate evidence was present.",
            "missing": ["Supporting candidate evidence"],
        }
        assessments.append(item)
    return QualificationAssessmentResponse(requirement_assessments=assessments)
