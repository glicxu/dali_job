from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from app.modules.matching_v2.schemas import (
    CandidateExtractionResponse,
    JobExtractionProviderResponse,
    QualificationAssessmentResponse,
    normalized_json_schema,
)
from app.modules.matching_v2.prompts import (
    CANDIDATE_EXTRACTION_SYSTEM_PROMPT,
    JOB_EXTRACTION_SYSTEM_PROMPT,
    JOB_EXTRACTION_SYSTEM_PROMPT_V1,
    JOB_EXTRACTION_SYSTEM_PROMPT_V2,
    QUALIFICATION_SYSTEM_PROMPT,
    QUALIFICATION_SYSTEM_PROMPT_V1,
)


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_value(nested) for nested in value]
    return value


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(nested) for key, nested in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(nested) for nested in value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_plain_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RegistryEntry:
    artifact_type: str
    version: str
    content: Any
    content_hash: str = field(init=False)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_hash", content_sha256(self.content))
        object.__setattr__(self, "content", _freeze_value(self.content))
        object.__setattr__(self, "metadata", _freeze_value(dict(self.metadata)))


class ImmutableRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], RegistryEntry] = {}

    def register(self, entry: RegistryEntry) -> RegistryEntry:
        key = (entry.artifact_type, entry.version)
        existing = self._entries.get(key)
        if existing is not None:
            if existing.content_hash != entry.content_hash or dict(existing.metadata) != dict(entry.metadata):
                raise ValueError(f"Registry version already exists with different content: {key}")
            return existing
        self._entries[key] = entry
        return entry

    def get(self, artifact_type: str, version: str) -> RegistryEntry:
        try:
            return self._entries[(artifact_type, version)]
        except KeyError as exc:
            raise KeyError(f"Unknown registry entry: {(artifact_type, version)}") from exc

    def entries(self) -> tuple[RegistryEntry, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))


SOFTWARE_IC_MULTIPLIERS = {
    "entry": {
        "technical_skill": 1.25,
        "applied_experience": 0.75,
        "production_delivery": 0.75,
        "system_design_architecture": 0.50,
        "mentoring_leadership": 0.25,
        "organizational_influence": 0.25,
        "education_credential": 1.00,
        "domain_knowledge": 0.75,
    },
    "junior": {
        "technical_skill": 1.15,
        "applied_experience": 1.00,
        "production_delivery": 1.00,
        "system_design_architecture": 0.75,
        "mentoring_leadership": 0.50,
        "organizational_influence": 0.25,
        "education_credential": 0.75,
        "domain_knowledge": 0.75,
    },
    "mid": {
        "technical_skill": 1.00,
        "applied_experience": 1.10,
        "production_delivery": 1.20,
        "system_design_architecture": 1.00,
        "mentoring_leadership": 0.75,
        "organizational_influence": 0.50,
        "education_credential": 0.50,
        "domain_knowledge": 1.00,
    },
    "senior": {
        "technical_skill": 0.75,
        "applied_experience": 1.25,
        "production_delivery": 1.30,
        "system_design_architecture": 1.25,
        "mentoring_leadership": 1.20,
        "organizational_influence": 0.90,
        "education_credential": 0.25,
        "domain_knowledge": 1.00,
    },
    "staff": {
        "technical_skill": 0.60,
        "applied_experience": 1.25,
        "production_delivery": 1.35,
        "system_design_architecture": 1.50,
        "mentoring_leadership": 1.40,
        "organizational_influence": 1.40,
        "education_credential": 0.10,
        "domain_knowledge": 1.10,
    },
    "principal": {
        "technical_skill": 0.50,
        "applied_experience": 1.20,
        "production_delivery": 1.30,
        "system_design_architecture": 1.60,
        "mentoring_leadership": 1.50,
        "organizational_influence": 1.60,
        "education_credential": 0.10,
        "domain_knowledge": 1.10,
    },
}


class RoleTrackPolicyRegistry:
    def __init__(self, policies: Mapping[tuple[str, str], RegistryEntry]) -> None:
        self._policies = MappingProxyType(dict(policies))

    def resolve_public(self, role_family: str, track: str) -> RegistryEntry | None:
        policy = self._policies.get((role_family, track))
        if policy is None or not bool(policy.metadata.get("approved_for_public")):
            return None
        return policy


DEFAULT_REGISTRY = ImmutableRegistry()

# Register only active schemas. Historical schema rows remain immutable in the
# database; rebuilding them from legacy models can change their hashes when a
# shared nested model evolves.
for model, version in (
    (CandidateExtractionResponse, "candidate-extract-response.v1"),
    (JobExtractionProviderResponse, "job-extract-response.v3"),
    (QualificationAssessmentResponse, "qualification-assessment-response.v2"),
):
    DEFAULT_REGISTRY.register(
        RegistryEntry(
            artifact_type="response_schema",
            version=version,
            content=normalized_json_schema(model),
        )
    )

for version, content in (
    (
        "candidate-extract.v1",
        {
            "system": CANDIDATE_EXTRACTION_SYSTEM_PROMPT,
            "user_template": "json-envelope.allowed_source_spans.v1",
        },
    ),
    (
        "job-extract.v1",
        {
            "system": JOB_EXTRACTION_SYSTEM_PROMPT_V1,
            "user_template": "json-envelope.allowed_source_spans.v1",
        },
    ),
    (
        "job-extract.v2",
        {
            "system": JOB_EXTRACTION_SYSTEM_PROMPT_V2,
            "user_template": "json-envelope.allowed_source_spans.with-full-replacement-repair.v2",
        },
    ),
    (
        "job-extract.v3",
        {
            "system": JOB_EXTRACTION_SYSTEM_PROMPT,
            "user_template": "json-envelope.allowed_source_spans.with-full-replacement-repair.v3",
        },
    ),
    (
        "qualification-match.v1",
        {
            "system": QUALIFICATION_SYSTEM_PROMPT_V1,
            "user_template": "json-envelope.candidate_evidence_job_requirements_alternatives.v1",
        },
    ),
    (
        "qualification-match.v2",
        {
            "system": QUALIFICATION_SYSTEM_PROMPT,
            "user_template": "json-envelope.candidate_profile_evidence_job_requirements_alternatives.v2",
        },
    ),
    (
        "qualification-match.v3",
        {
            "system": QUALIFICATION_SYSTEM_PROMPT,
            "user_template": (
                "json-envelope.candidate_profile_evidence_job_requirements_alternatives."
                "with-full-replacement-repair.v3"
            ),
        },
    ),
):
    DEFAULT_REGISTRY.register(RegistryEntry(artifact_type="prompt", version=version, content=content))

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="taxonomy",
        version="matching-taxonomy.v1",
        content={
            "role_families": [
                "software_engineering",
                "data_science",
                "financial_technology",
                "technical_education",
                "product_management",
                "unknown",
            ],
            "tracks": [
                "individual_contributor",
                "architect",
                "engineering_management",
                "research",
                "technical_program",
                "technical_education",
                "unknown",
            ],
            "levels": [
                "unknown",
                "student_or_intern",
                "entry",
                "junior",
                "mid",
                "senior",
                "staff",
                "principal",
            ],
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="taxonomy",
        version="matching-taxonomy.v2",
        content={
            "role_families": [
                "software_engineering", "data_science", "financial_technology",
                "technical_education", "product_management",
                "machine_learning_engineering", "hardware_engineering",
                "embedded_systems", "technical_program_management", "unknown",
            ],
            "tracks": [
                "individual_contributor", "architect", "engineering_management", "research",
                "technical_program", "technical_education", "product", "program", "unknown",
            ],
            "levels": [
                "unknown", "student_or_intern", "entry", "junior", "mid", "senior",
                "staff", "principal",
            ],
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="semantic_validator",
        version="matching-semantic-validator.v1",
        content={
            "rules": [
                "source_reference_membership",
                "unique_local_references",
                "primary_reference_membership",
                "exact_requirement_coverage",
                "positive_status_requires_evidence",
                "approved_alternative_required",
                "hard_constraint_single_owner",
            ]
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="semantic_validator",
        version="matching-semantic-validator.v3",
        content={
            "rules": [
                "source_reference_membership", "unique_local_references",
                "required_optional_only", "application_constraint_single_owner",
                "structured_explicit_alternatives", "provider_policy_field_must_be_null",
                "deterministic_alternative_policy_assignment", "career_adjacency_consistency",
                "explicit_employment_type", "qualification_section_coverage",
                "responsibility_section_coverage", "one_full_replacement_repair_attempt",
                "compensation_excluded_from_model_ownership",
            ]
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="semantic_validator",
        version="matching-semantic-validator.v2",
        content={
            "rules": [
                "source_reference_membership",
                "unique_local_references",
                "primary_reference_membership",
                "exact_requirement_coverage",
                "positive_status_requires_evidence",
                "approved_alternative_required",
                "hard_constraint_single_owner",
                "provider_policy_field_must_be_null",
                "deterministic_alternative_policy_assignment",
                "one_full_replacement_repair_attempt",
            ]
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="deduplication_policy",
        version="job-dedup.v2",
        content={
            "span_rule": "casefolded_whitespace_exact_match_first_occurrence_wins",
            "requirement_rule": "casefolded_whitespace_exact_match_merge_or_reject_conflict",
            "boilerplate_rule": "drop_only_spans_beginning_with_known_boilerplate_marker",
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="deduplication_policy",
        version="job-dedup.v1",
        content={
            "span_rule": "casefolded_whitespace_exact_match_first_occurrence_wins",
            "requirement_rule": "casefolded_whitespace_exact_match_merge_or_reject_conflict",
            "boilerplate_rule": "conservative_known_marker_filter",
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="source_reuse_policy",
        version="cached-job-reuse.v1",
        content={
            "eligible_source": "active jobs_cache record with non-empty imported raw description",
            "retention": "inherits jobs_cache lifecycle and deletion state",
            "candidate_data_allowed": False,
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="career_selection_policy",
        version="career-selection-policy.v1",
        content={
            "compatible_tracks": {
                "individual_contributor": ["architect", "research"],
                "architect": ["individual_contributor"],
                "engineering_management": ["technical_program"],
                "research": ["individual_contributor"],
                "technical_program": ["engineering_management"],
                "technical_education": ["individual_contributor"],
            },
            "adjacent_role_families": {
                "software_engineering": ["financial_technology", "data_science"],
                "data_science": ["software_engineering", "financial_technology"],
                "financial_technology": ["software_engineering", "data_science"],
                "technical_education": ["software_engineering"],
                "product_management": ["software_engineering"],
            },
            "order": [
                "exact_role_exact_track",
                "exact_role_compatible_track",
                "adjacent_role_exact_track",
                "adjacent_role_compatible_track",
                "primary_selection",
                "evidence_coverage",
                "confidence",
                "durable_id",
            ],
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="career_selection_policy",
        version="career-selection-policy.v2",
        content={
            "compatible_tracks": {
                "individual_contributor": ["architect", "research"],
                "architect": ["individual_contributor"],
                "engineering_management": ["technical_program", "program"],
                "research": ["individual_contributor"],
                "technical_program": ["engineering_management", "program"],
                "technical_education": ["individual_contributor"],
                "product": ["program", "technical_program"],
                "program": ["product", "technical_program", "engineering_management"],
            },
            "adjacent_role_families": {
                "software_engineering": ["financial_technology", "data_science"],
                "data_science": ["software_engineering", "financial_technology", "machine_learning_engineering"],
                "machine_learning_engineering": ["data_science", "software_engineering"],
                "hardware_engineering": ["software_engineering", "embedded_systems"],
                "embedded_systems": ["hardware_engineering", "software_engineering"],
                "financial_technology": ["software_engineering", "data_science"],
                "technical_education": ["software_engineering"],
                "product_management": ["software_engineering", "technical_program_management"],
                "technical_program_management": ["product_management", "software_engineering"],
            },
            "order": [
                "exact_role_exact_track", "exact_role_compatible_track",
                "adjacent_role_exact_track", "adjacent_role_compatible_track",
                "primary_selection", "evidence_coverage", "confidence", "durable_id",
            ],
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="qualification_policy",
        version="qualification-policy.v1",
        content={
            "positive_statuses": ["met", "met_by_alternative", "partially_met"],
            "contradiction_status": "not_met",
            "missing_evidence_status": "not_demonstrated",
            "low_confidence_threshold": 0.60,
            "low_confidence_status": "needs_clarification",
            "not_applicable_enabled": False,
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="qualification_policy",
        version="qualification-policy.v2",
        content={
            "statuses": ["met", "met_by_alternative", "partially_met", "not_demonstrated"],
            "required_optional_same_evidence_semantics": True,
            "positive_statuses_require_evidence": True,
            "not_demonstrated_has_no_evidence_refs": True,
            "alternative_refs_only_for_met_by_alternative": True,
            "scores_and_recommendations_allowed": False,
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="input_policy",
        version="qualification-input.v1",
        content={
            "maximum_utf8_bytes": 100000,
            "requirements_are_never_omitted": True,
            "candidate_evidence_order": "canonical_source_span_ordinal",
            "derived_candidate_fields_allowed": False,
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="input_policy",
        version="qualification-input.v2",
        content={
            "maximum_utf8_bytes": 100000,
            "requirements_are_never_omitted": True,
            "candidate_profile_non_derived_collections_included": True,
            "candidate_evidence_order": "canonical_source_span_ordinal",
            "derived_candidate_fields_allowed": False,
            "job_alternatives": "structured_groups_with_legacy_adapter",
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="semantic_validator",
        version="matching-semantic-validator.v4",
        content={
            "rules": [
                "exact_single_collection_requirement_coverage",
                "candidate_evidence_reference_membership",
                "positive_status_requires_evidence",
                "not_demonstrated_has_no_evidence_refs",
                "partial_status_requires_missing_items",
                "complete_status_has_no_missing_items",
                "alternative_group_reference_membership",
                "approved_alternative_policy_membership",
                "alternative_references_only_for_met_by_alternative",
                "no_score_weight_rank_eligibility_or_recommendation",
            ]
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="alternative_policy",
        version="general-purpose-programming-language.v1",
        content={
            "status": "approved",
            "approval": "explicit-members-only",
            "members": [
                "C",
                "C++",
                "C#",
                "Go",
                "Java",
                "JavaScript",
                "Kotlin",
                "Python",
                "Rust",
                "Swift",
                "TypeScript",
            ],
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="alternative_policy",
        version="general-purpose-programming-language.v2",
        content={
            "status": "approved",
            "approval": "explicit-members-only",
            "matching_rule": "exact_normalized_members_joined_by_or_slash_or_comma",
            "minimum_distinct_members": 2,
            "members": [
                "C",
                "C++",
                "C#",
                "Go",
                "Java",
                "JavaScript",
                "Kotlin",
                "Python",
                "Rust",
                "Swift",
                "TypeScript",
            ],
        },
    )
)


def match_explicit_alternative_policy(explicit_alternatives: list[str]) -> str | None:
    """Return a policy only for an exact, explicit disjunction of registered members."""

    version = "general-purpose-programming-language.v2"
    entry = DEFAULT_REGISTRY.get("alternative_policy", version)
    members = {str(member).casefold(): str(member) for member in entry.content["members"]}
    for alternative in explicit_alternatives:
        parts = [
            part.strip().strip(".;:()[]{}\"").casefold()
            for part in re.split(r"\s*(?:\bor\b|/|,)\s*", alternative, flags=re.IGNORECASE)
            if part.strip()
        ]
        resolved = {members[part] for part in parts if part in members}
        if len(parts) >= 2 and len(resolved) >= 2 and len(resolved) == len(parts):
            return version
    return None

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="deterministic_policy",
        version="preference-policy.v2",
        content={
            "architecture_section": "10",
            "status_values": {"met": 1.0, "partially_met": 0.5, "conflict": 0.0},
            "importance_weights": {"low": 1, "medium": 2, "high": 3},
            "minimum_coverage_for_overall_score": 0.60,
            "dependencies": [
                "matching-taxonomy.v2",
                "career-selection-policy.v2",
                "general-purpose-programming-language.v2",
            ],
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="deterministic_policy",
        version="eligibility-policy.v2",
        content={
            "architecture_section": "8.2",
            "statuses": ["satisfied", "violated", "unknown", "not_applicable"],
            "missing_fact_status": "unknown",
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="deterministic_policy",
        version="score.v1",
        content={
            "architecture_section": "11",
            "qualification_status_values": {
                "met": 1.0,
                "met_by_alternative": 0.9,
                "partially_met": 0.5,
                "not_demonstrated": 0.0,
                "not_met": 0.0,
            },
            "qualification_importance_weights": {"required": 3, "optional": 1},
            "minimum_qualification_coverage": 0.80,
            "qualification_overall_weight": 0.70,
            "preference_overall_weight": 0.30,
            "rounding": "decimal_half_up",
            "recommendation_thresholds": {
                "strong_match": 85,
                "good_match": 70,
                "consider": 55,
                "stretch": 40,
                "unlikely_fit": 0,
            },
        },
    )
)

DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="deterministic_policy",
        version="match-explanation.v1",
        content={
            "architecture_section": "12",
            "source": "validated_assessments_and_score_only",
            "language_model_required": False,
        },
    )
)

SOFTWARE_IC_POLICY = DEFAULT_REGISTRY.register(
    RegistryEntry(
        artifact_type="role_track_scoring_policy",
        version="software-ic-score.v1",
        content={"role_family": "software_engineering", "track": "individual_contributor", "multipliers": SOFTWARE_IC_MULTIPLIERS},
        metadata={"approved_for_public": True},
    )
)

ROLE_TRACK_POLICIES = RoleTrackPolicyRegistry(
    {("software_engineering", "individual_contributor"): SOFTWARE_IC_POLICY}
)
