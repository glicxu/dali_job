from __future__ import annotations

import pytest

from app.modules.matching_v2.canonical import EvidenceSpan, canonicalize_text
from app.modules.matching_v2.extraction import (
    assign_alternative_policies,
    cleanup_job_spans,
    validate_job_extraction,
)
from app.modules.matching_v2.schemas import JobExtractionResponse, job_response_format


def _artifact(*, importance: str = "required") -> JobExtractionResponse:
    return JobExtractionResponse.model_validate({
        "title": "Software Engineer",
        "company": "Example",
        "location": {"display": None, "country": None, "region": None, "city": None,
                     "workplace_type": "unknown", "remote_regions": []},
        "employment_type": "unknown",
        "career_context": {
            "primary_role_family": "machine_learning_engineering",
            "adjacent_role_families": ["software_engineering"],
            "track": "individual_contributor", "target_level": "senior",
            "acceptable_level_range": None, "level_source": "inferred_from_requirements",
            "confidence": 0.8, "evidence_refs": ["job:requirements:1"],
        },
        "compensation": {"currency": None, "period": "unknown", "minimum": None,
                         "maximum": None, "is_employer_provided": False},
        "requirements": [{
            "local_ref": "languages", "category": "skill",
            "scoring_dimension": "technical_skill", "statement": "Python or Java",
            "importance": importance, "acceptable_evidence_contexts": ["professional"],
            "minimum_years": None,
            "alternative_groups": [{"local_ref": "language_options",
                                    "any_of": ["Python", "Java"],
                                    "source_refs": ["job:requirements:1"]}],
            "policy_alternative_group": None, "source_refs": ["job:requirements:1"],
        }],
        "responsibilities": [],
        "application_constraints": {"work_authorization": "unknown",
                                    "sponsorship_available": "unknown",
                                    "travel_percent": None, "clearance": None},
        "cleanup": {"duplicate_spans_removed": 0, "boilerplate_spans_ignored": 0,
                    "warnings": []},
    })


def test_v3_provider_schema_has_only_required_optional_and_server_owned_compensation() -> None:
    schema = job_response_format(["job:requirements:1"])["schema"]["$defs"]
    requirement = schema["JobRequirementProviderResponse"]["properties"]
    compensation = schema["JobCompensationProviderResponse"]["properties"]
    assert requirement["importance"]["enum"] == ["required", "optional"]
    assert "hard_constraint" not in requirement
    assert "explicit_alternatives" not in requirement
    assert compensation["currency"]["type"] == "null"
    assert compensation["period"]["const"] == "unknown"


def test_v3_assigns_language_policy_from_structured_group() -> None:
    artifact = assign_alternative_policies(_artifact())
    assert artifact.requirements[0].policy_alternative_group == \
        "general-purpose-programming-language.v2"


def test_v3_requires_optional_section_coverage() -> None:
    spans = [
        EvidenceSpan("job:requirements:1", "requirements", 0, 14, "Python or Java"),
        EvidenceSpan("job:preferred:1", "preferred_requirements", 15, 25, "Kubernetes"),
    ]
    with pytest.raises(ValueError, match="Missing optional-section coverage"):
        validate_job_extraction(
            _artifact(), {span.span_id for span in spans}, source_spans=spans
        )


def test_cleanup_keeps_substantive_span_with_trailing_boilerplate() -> None:
    span = EvidenceSpan(
        "job:responsibilities:1", "responsibilities", 0, 100,
        "Design distributed systems. We are an equal opportunity employer.",
    )
    cleanup = cleanup_job_spans([span])
    assert cleanup.kept_spans == (span,)
    assert cleanup.boilerplate_spans_ignored == 0


def test_canonicalization_repairs_known_mojibake() -> None:
    assert canonicalize_text("Engineerâ€™s role â€” platform") == "Engineer’s role — platform"


def test_employment_type_accepts_explicit_machine_readable_source_value() -> None:
    artifact = _artifact().model_copy(update={"employment_type": "full_time"})
    span = EvidenceSpan(
        "job:requirements:1", "requirements", 0, 50, "employment type: FULL_TIME; Python or Java"
    )
    validated = validate_job_extraction(
        artifact, {span.span_id}, source_spans=[span]
    )
    assert validated.employment_type == "full_time"


def test_requirement_cannot_leak_from_summary_when_qualification_sections_exist() -> None:
    artifact = _artifact()
    leaked = artifact.requirements[0].model_copy(update={
        "local_ref": "innovation",
        "statement": "Innovation",
        "alternative_groups": [],
        "source_refs": ["job:summary:1"],
    })
    artifact = artifact.model_copy(update={"requirements": [artifact.requirements[0], leaked]})
    spans = [
        EvidenceSpan("job:summary:1", "summary", 0, 20, "We value innovation"),
        EvidenceSpan("job:requirements:1", "requirements", 21, 40, "Python or Java"),
    ]
    with pytest.raises(ValueError, match="not owned by a qualification section"):
        validate_job_extraction(
            artifact, {span.span_id for span in spans}, source_spans=spans
        )
