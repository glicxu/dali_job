from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import get_provider_secret
from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateCareerSelection,
    CandidateProfileVersion,
    JobProfileVersion,
    JobRequirement,
    SourceSpan,
)
from app.modules.matching_v2.prompts import QUALIFICATION_SYSTEM_PROMPT, build_qualification_user_prompt
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
    candidate_evidence: tuple[dict, ...]
    job_requirements: tuple[dict, ...]
    approved_alternatives: tuple[dict, ...]
    allowed_evidence_refs: frozenset[str]
    omitted_evidence_refs: tuple[str, ...]
    selected_career_context: dict | None


@dataclass(frozen=True)
class QualificationResult:
    artifact: QualificationAssessmentResponse
    model_id: str
    provider_execution_reference: str | None


class QualificationMatcher(Protocol):
    def assess(self, qualification_input: QualificationInput) -> QualificationResult:
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
                    requirement_assessments=[], hard_constraint_assessments=[]
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
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": QUALIFICATION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_qualification_user_prompt(
                        candidate_evidence=qualification_input.candidate_evidence,
                        job_requirements=qualification_input.job_requirements,
                        approved_alternatives=qualification_input.approved_alternatives,
                        career_context=qualification_input.selected_career_context,
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": qualification_response_format(
                    allowed_requirement_ids=requirement_ids,
                    allowed_evidence_refs=sorted(qualification_input.allowed_evidence_refs),
                ),
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(status_code=502, detail="The qualification provider returned an empty response.")
        try:
            artifact = QualificationAssessmentResponse.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=502, detail="The qualification provider returned an invalid response.") from exc
        return QualificationResult(
            artifact=artifact,
            model_id=self._model,
            provider_execution_reference=getattr(response, "id", None),
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
    selection_policy = DEFAULT_REGISTRY.get("career_selection_policy", "career-selection-policy.v1").content
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
    job_items = tuple({
        "requirement_id": item.requirement_id,
        "statement": item.statement,
        "importance": item.importance,
        "hard_constraint": item.hard_constraint,
        "scoring_dimension": item.scoring_dimension,
        "acceptable_evidence_contexts": item.acceptable_evidence_contexts,
        "minimum_years": item.minimum_years,
        "explicit_alternatives": item.explicit_alternatives,
        "policy_alternative_group": item.policy_alternative_group,
    } for item in requirements)
    alternatives: list[dict] = []
    for item in requirements:
        if item.explicit_alternatives:
            alternatives.append({
                "requirement_id": item.requirement_id,
                "kind": "explicit_job_wording",
                "values": item.explicit_alternatives,
            })
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
    base_bytes = len(build_qualification_user_prompt(
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
        candidate_evidence=tuple(evidence),
        job_requirements=job_items,
        approved_alternatives=tuple(alternatives),
        allowed_evidence_refs=frozenset(item["span_id"] for item in evidence),
        omitted_evidence_refs=tuple(omitted),
        selected_career_context=selected,
    )


def validate_qualification_assessment(
    artifact: QualificationAssessmentResponse,
    *,
    requirements: list[JobRequirement],
    allowed_evidence_refs: set[str] | frozenset[str],
    incomplete_evidence_input: bool = False,
) -> QualificationAssessmentResponse:
    by_id = {item.requirement_id: item for item in requirements}
    normal_ids = {item.requirement_id for item in requirements if not item.hard_constraint}
    hard_ids = {item.requirement_id for item in requirements if item.hard_constraint}
    normal_returned = [item.requirement_id for item in artifact.requirement_assessments]
    hard_returned = [item.requirement_id for item in artifact.hard_constraint_assessments]
    if len(normal_returned) != len(set(normal_returned)) or set(normal_returned) != normal_ids:
        raise ValueError("Qualification response must assess every normal requirement exactly once.")
    if len(hard_returned) != len(set(hard_returned)) or set(hard_returned) != hard_ids:
        raise ValueError("Qualification response must assess every hard constraint exactly once.")
    if set(normal_returned) & set(hard_returned):
        raise ValueError("A requirement cannot appear in both qualification collections.")

    def normalize(items, expected_ids):
        items_by_id = {item.requirement_id: item for item in items}
        normalized = []
        for requirement_id in [item.requirement_id for item in requirements if item.requirement_id in expected_ids]:
            item = items_by_id[requirement_id]
            requirement = by_id[requirement_id]
            unknown_refs = set(item.evidence_refs) - set(allowed_evidence_refs)
            if unknown_refs:
                raise ValueError(f"Qualification contains unknown evidence references: {sorted(unknown_refs)}")
            if item.status in _POSITIVE_STATUSES | {"not_met"} and not item.evidence_refs:
                raise ValueError(f"Qualification status {item.status} requires candidate evidence.")
            if item.status == "not_demonstrated" and item.evidence_refs:
                raise ValueError("not_demonstrated cannot cite evidence as support.")
            if item.status == "not_applicable":
                raise ValueError("not_applicable is not enabled by qualification-policy.v1.")
            if item.status == "met_by_alternative":
                explicit = bool(requirement.explicit_alternatives)
                policy_ok = bool(
                    item.alternative_policy_ref
                    and item.alternative_policy_ref == requirement.policy_alternative_group
                    and _registered_alternative(item.alternative_policy_ref)
                )
                if not (explicit if item.alternative_policy_ref is None else policy_ok):
                    raise ValueError("met_by_alternative requires an explicit or approved alternative.")
            elif item.alternative_policy_ref is not None:
                raise ValueError("Alternative policy references are valid only for met_by_alternative.")
            if item.confidence < 0.60 and item.status != "not_demonstrated":
                item = item.model_copy(update={
                    "status": "needs_clarification",
                    "alternative_policy_ref": None,
                    "reason": "Provider confidence was below qualification-policy.v1 threshold.",
                    "missing": list(dict.fromkeys([*item.missing, "Higher-confidence evidence assessment"])),
                })
            if item.status == "needs_clarification" and not item.evidence_refs:
                if incomplete_evidence_input:
                    item = item.model_copy(update={
                        "reason": "Candidate evidence was omitted by the bounded-input policy.",
                        "missing": list(dict.fromkeys([*item.missing, "Review omitted candidate evidence"])),
                    })
                else:
                    item = item.model_copy(update={
                        "status": "not_demonstrated",
                        "reason": "No supporting candidate evidence was present.",
                        "missing": list(dict.fromkeys([*item.missing, "Supporting candidate evidence"])),
                    })
            if item.status == "partially_met" and not item.missing:
                raise ValueError("partially_met must identify material missing evidence.")
            if item.status in {"met", "met_by_alternative"} and item.missing:
                raise ValueError(f"{item.status} cannot report missing qualification evidence.")
            item = item.model_copy(update={"evidence_refs": list(dict.fromkeys(item.evidence_refs))})
            normalized.append(item)
        return normalized

    return QualificationAssessmentResponse(
        requirement_assessments=normalize(artifact.requirement_assessments, normal_ids),
        hard_constraint_assessments=normalize(artifact.hard_constraint_assessments, hard_ids),
    )


def _candidate_non_derived_refs(artifact: dict) -> set[str]:
    refs: set[str] = set()
    for key in ("skills", "experience", "projects", "education", "certifications", "publications"):
        for item in artifact.get(key, []):
            refs.update(ref for ref in item.get("evidence_refs", []) if isinstance(ref, str))
    return refs


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
    normal = []
    hard = []
    for requirement in job_requirements:
        item = {
            "requirement_id": requirement["requirement_id"],
            "status": "not_demonstrated",
            "confidence": 1.0,
            "evidence_refs": [],
            "alternative_policy_ref": None,
            "reason": "No supporting candidate evidence was present.",
            "missing": ["Supporting candidate evidence"],
        }
        (hard if requirement["hard_constraint"] else normal).append(item)
    return QualificationAssessmentResponse(
        requirement_assessments=normal,
        hard_constraint_assessments=hard,
    )
