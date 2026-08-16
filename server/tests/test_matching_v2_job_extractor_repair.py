from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.matching_v2.canonical import EvidenceSpan
from app.modules.matching_v2.extraction import JobProfileValidationFailed, OpenAIJobProfileExtractor


def _payload(source_ref: str, *, provider_policy: str | None) -> dict[str, object]:
    return {
        "title": "Software Engineer",
        "company": "Example Co",
        "location": {
            "display": None,
            "country": None,
            "region": None,
            "city": None,
            "workplace_type": "unknown",
            "remote_regions": [],
        },
        "employment_type": "unknown",
        "career_context": {
            "primary_role_family": "software_engineering",
            "adjacent_role_families": [],
            "track": "individual_contributor",
            "target_level": "mid",
            "acceptable_level_range": None,
            "level_source": "inferred_from_requirements",
            "confidence": 0.8,
            "evidence_refs": [source_ref],
        },
        "compensation": {
            "currency": None,
            "period": "unknown",
            "minimum": None,
            "maximum": None,
            "is_employer_provided": False,
        },
        "requirements": [{
            "local_ref": "language_requirement",
            "category": "skill",
            "scoring_dimension": "technical_skill",
            "statement": "Experience with Python or Java",
            "importance": "required",
            "acceptable_evidence_contexts": ["professional"],
            "minimum_years": None,
            "alternative_groups": [{
                "local_ref": "language_options",
                "any_of": ["Python", "Java"],
                "source_refs": [source_ref],
            }],
            "policy_alternative_group": provider_policy,
            "source_refs": [source_ref],
        }],
        "responsibilities": [],
        "application_constraints": {
            "work_authorization": "unknown",
            "sponsorship_available": "unknown",
            "travel_percent": None,
            "clearance": None,
        },
        "cleanup": {
            "duplicate_spans_removed": 0,
            "boilerplate_spans_ignored": 0,
            "warnings": [],
        },
    }


def test_job_extractor_repairs_with_complete_replacement_and_assigns_policy() -> None:
    source_ref = "job_1:requirements:0001"
    contents = [
        json.dumps(_payload(source_ref, provider_policy="degree_or_equivalent")),
        json.dumps(_payload(source_ref, provider_policy=None)),
    ]
    requests: list[dict[str, object]] = []

    def create(**kwargs: object) -> object:
        requests.append(kwargs)
        content = contents[len(requests) - 1]
        return SimpleNamespace(
            id=f"response-{len(requests)}",
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        )

    extractor = OpenAIJobProfileExtractor.__new__(OpenAIJobProfileExtractor)
    extractor._model = "gpt-5.6-luna"
    extractor._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result = extractor.extract([
        EvidenceSpan(source_ref, "requirements", 0, 30, "Experience with Python or Java")
    ])

    assert len(requests) == 2
    repair_prompt = requests[1]["messages"][1]["content"]
    assert "Return a complete replacement Job Profile, not a partial patch." in repair_prompt
    assert "SCHEMA_VALIDATION_FAILED" in repair_prompt
    assert result.provider_execution_reference == "response-2"
    assert (
        result.artifact.requirements[0].policy_alternative_group
        == "general-purpose-programming-language.v2"
    )


def test_job_validation_failure_response_is_structured_and_privacy_safe() -> None:
    app = create_app()

    @app.get("/_test/job-profile-validation-failure")
    def fail() -> None:
        raise JobProfileValidationFailed(repair_attempted=True)

    response = TestClient(app).get(
        "/_test/job-profile-validation-failure",
        headers={"X-Request-ID": "match_test_123"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": "JOB_PROFILE_VALIDATION_FAILED",
        "stage": "job_profile_extraction",
        "correlation_id": "match_test_123",
        "repair_attempted": True,
    }
