from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.core.secrets import get_provider_secret
from app.modules.matching_v2.canonical import EvidenceSpan
from app.modules.matching_v2.prompts import (
    CANDIDATE_EXTRACTION_SYSTEM_PROMPT,
    JOB_EXTRACTION_SYSTEM_PROMPT,
    build_extraction_user_prompt,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY
from app.modules.matching_v2.schemas import (
    CandidateExtractionResponse,
    JobExtractionResponse,
    candidate_response_format,
    job_response_format,
)

MAX_CANDIDATE_MODEL_SPAN_BYTES = 85_000
MAX_JOB_MODEL_SPAN_BYTES = 85_000
JOB_DEDUPLICATION_VERSION = "job-dedup.v1"
_SECTION_PRIORITY = {
    "experience": 0,
    "projects": 1,
    "skills": 2,
    "education": 3,
    "certifications": 4,
    "publications": 5,
    "summary": 6,
    "awards": 7,
    "volunteer": 8,
    "languages": 9,
    "general": 10,
}
_JOB_SECTION_PRIORITY = {
    "requirements": 0,
    "preferred_requirements": 1,
    "responsibilities": 2,
    "compensation": 3,
    "location": 4,
    "general": 5,
    "company": 6,
    "benefits": 7,
}
_BOILERPLATE_MARKERS = (
    "equal opportunity employer",
    "we are an equal opportunity",
    "reasonable accommodation",
    "privacy policy",
    "cookie policy",
    "terms of use",
    "do not sell my personal information",
)


@dataclass(frozen=True)
class CandidateExtractionResult:
    artifact: CandidateExtractionResponse
    model_id: str
    provider_execution_reference: str | None
    omitted_span_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class JobCleanupResult:
    kept_spans: tuple[EvidenceSpan, ...]
    duplicate_spans_removed: int
    boilerplate_spans_ignored: int


@dataclass(frozen=True)
class JobExtractionResult:
    artifact: JobExtractionResponse
    model_id: str
    provider_execution_reference: str | None
    omitted_span_ids: tuple[str, ...] = ()


class CandidateProfileExtractor(Protocol):
    def extract(self, spans: list[EvidenceSpan]) -> CandidateExtractionResult:
        ...


class JobProfileExtractor(Protocol):
    def extract(self, spans: list[EvidenceSpan]) -> JobExtractionResult:
        ...


class OpenAICandidateProfileExtractor:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def extract(self, spans: list[EvidenceSpan]) -> CandidateExtractionResult:
        selected, omitted = select_candidate_model_spans(spans)
        if not selected:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The resume does not contain usable evidence spans.",
            )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": CANDIDATE_EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_extraction_user_prompt(
                        spans=[
                            {
                                "span_id": span.span_id,
                                "section": span.section,
                                "excerpt": span.excerpt,
                            }
                            for span in selected
                        ]
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": candidate_response_format([span.span_id for span in selected]),
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The candidate-profile provider returned an empty response.",
            )
        try:
            artifact = CandidateExtractionResponse.model_validate(json.loads(content))
            artifact = validate_candidate_extraction(artifact, {span.span_id for span in selected})
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The candidate-profile provider returned an invalid response.",
            ) from exc

        if omitted:
            quality = artifact.quality.model_copy(
                update={
                    "warnings": [
                        *artifact.quality.warnings[:19],
                        f"MODEL_INPUT_OMITTED_SPANS:{len(omitted)}",
                    ],
                    "completeness": min(
                        artifact.quality.completeness,
                        len(selected) / (len(selected) + len(omitted)),
                    ),
                }
            )
            artifact = artifact.model_copy(update={"quality": quality})

        return CandidateExtractionResult(
            artifact=artifact,
            model_id=self._model,
            provider_execution_reference=getattr(response, "id", None),
            omitted_span_ids=tuple(span.span_id for span in omitted),
        )


class OpenAIJobProfileExtractor:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def extract(self, spans: list[EvidenceSpan]) -> JobExtractionResult:
        cleanup = cleanup_job_spans(spans)
        selected, omitted = select_job_model_spans(list(cleanup.kept_spans))
        if not selected:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The job description does not contain usable evidence spans.",
            )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": JOB_EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_extraction_user_prompt(
                        spans=[
                            {"span_id": span.span_id, "section": span.section, "excerpt": span.excerpt}
                            for span in selected
                        ]
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": job_response_format([span.span_id for span in selected]),
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(status_code=502, detail="The job-profile provider returned an empty response.")
        try:
            artifact = JobExtractionResponse.model_validate(json.loads(content))
            artifact = validate_job_extraction(
                artifact,
                {span.span_id for span in selected},
                duplicate_spans_removed=cleanup.duplicate_spans_removed,
                boilerplate_spans_ignored=cleanup.boilerplate_spans_ignored,
                omitted_span_count=len(omitted),
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="The job-profile provider returned an invalid response.") from exc
        return JobExtractionResult(
            artifact=artifact,
            model_id=self._model,
            provider_execution_reference=getattr(response, "id", None),
            omitted_span_ids=tuple(span.span_id for span in omitted),
        )


def select_candidate_model_spans(
    spans: list[EvidenceSpan],
    *,
    maximum_bytes: int = MAX_CANDIDATE_MODEL_SPAN_BYTES,
) -> tuple[list[EvidenceSpan], list[EvidenceSpan]]:
    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive.")
    indexed = list(enumerate(spans))
    prioritized = sorted(
        indexed,
        key=lambda item: (_SECTION_PRIORITY.get(item[1].section, 11), item[0]),
    )
    selected_indexes: set[int] = set()
    used = 0
    for index, span in prioritized:
        size = len(span.excerpt.encode("utf-8"))
        if used + size <= maximum_bytes:
            selected_indexes.add(index)
            used += size
    selected = [span for index, span in indexed if index in selected_indexes]
    omitted = [span for index, span in indexed if index not in selected_indexes]
    return selected, omitted


def cleanup_job_spans(spans: list[EvidenceSpan]) -> JobCleanupResult:
    kept: list[EvidenceSpan] = []
    seen: set[str] = set()
    duplicate_count = 0
    boilerplate_count = 0
    for span in spans:
        normalized = _normalized_statement(span.excerpt)
        if normalized in seen:
            duplicate_count += 1
            continue
        seen.add(normalized)
        if any(marker in normalized for marker in _BOILERPLATE_MARKERS):
            boilerplate_count += 1
            continue
        kept.append(span)
    return JobCleanupResult(tuple(kept), duplicate_count, boilerplate_count)


def select_job_model_spans(
    spans: list[EvidenceSpan], *, maximum_bytes: int = MAX_JOB_MODEL_SPAN_BYTES
) -> tuple[list[EvidenceSpan], list[EvidenceSpan]]:
    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive.")
    indexed = list(enumerate(spans))
    prioritized = sorted(indexed, key=lambda item: (_JOB_SECTION_PRIORITY.get(item[1].section, 8), item[0]))
    selected_indexes: set[int] = set()
    used = 0
    for index, span in prioritized:
        size = len(span.excerpt.encode("utf-8"))
        if used + size <= maximum_bytes:
            selected_indexes.add(index)
            used += size
    return (
        [span for index, span in indexed if index in selected_indexes],
        [span for index, span in indexed if index not in selected_indexes],
    )


def validate_job_extraction(
    artifact: JobExtractionResponse,
    allowed_source_refs: set[str],
    *,
    duplicate_spans_removed: int = 0,
    boilerplate_spans_ignored: int = 0,
    omitted_span_count: int = 0,
) -> JobExtractionResponse:
    unknown = _collect_source_refs(artifact.model_dump(mode="json")) - allowed_source_refs
    if unknown:
        raise ValueError(f"Unknown job source references: {sorted(unknown)}")
    level_range = artifact.career_context.acceptable_level_range
    if level_range is not None:
        order = {name: index for index, name in enumerate(
            ("student_or_intern", "entry", "junior", "mid", "senior", "staff", "principal")
        )}
        if level_range.minimum == "unknown" or level_range.maximum == "unknown":
            raise ValueError("Job level range cannot contain unknown endpoints.")
        if order[level_range.minimum] > order[level_range.maximum]:
            raise ValueError("Job level range minimum cannot exceed maximum.")

    requirements = []
    positions: dict[str, int] = {}
    for requirement in artifact.requirements:
        key = _normalized_statement(requirement.statement)
        if requirement.policy_alternative_group is not None:
            try:
                DEFAULT_REGISTRY.get("alternative_policy", requirement.policy_alternative_group)
            except KeyError as exc:
                raise ValueError(
                    f"Unknown job alternative policy: {requirement.policy_alternative_group}"
                ) from exc
        if requirement.hard_constraint and _duplicates_application_constraint(artifact, key):
            raise ValueError(
                f"Hard requirement duplicates an application constraint: {requirement.local_ref}"
            )
        prior_index = positions.get(key)
        if prior_index is None:
            positions[key] = len(requirements)
            requirements.append(requirement)
            continue
        prior = requirements[prior_index]
        conflict_fields = ("category", "scoring_dimension", "importance", "hard_constraint", "minimum_years")
        if any(getattr(prior, field) != getattr(requirement, field) for field in conflict_fields):
            raise ValueError(f"Duplicate job requirements conflict: {prior.local_ref}, {requirement.local_ref}")
        requirements[prior_index] = prior.model_copy(
            update={
                "acceptable_evidence_contexts": list(dict.fromkeys([
                    *prior.acceptable_evidence_contexts, *requirement.acceptable_evidence_contexts
                ])),
                "explicit_alternatives": list(dict.fromkeys([
                    *prior.explicit_alternatives, *requirement.explicit_alternatives
                ])),
                "source_refs": list(dict.fromkeys([*prior.source_refs, *requirement.source_refs])),
            }
        )
    warnings = list(artifact.cleanup.warnings)
    if omitted_span_count:
        warnings.append(f"NEEDS_MORE_INFORMATION:MODEL_INPUT_OMITTED_SPANS:{omitted_span_count}")
    cleanup = artifact.cleanup.model_copy(update={
        "duplicate_spans_removed": duplicate_spans_removed,
        "boilerplate_spans_ignored": boilerplate_spans_ignored,
        "warnings": list(dict.fromkeys(warnings))[:20],
    })
    return artifact.model_copy(update={"requirements": requirements, "cleanup": cleanup})


def validate_candidate_extraction(
    artifact: CandidateExtractionResponse,
    allowed_evidence_refs: set[str],
) -> CandidateExtractionResponse:
    unknown = _collect_refs(artifact.model_dump(mode="json")) - allowed_evidence_refs
    if unknown:
        raise ValueError(f"Unknown candidate evidence references: {sorted(unknown)}")

    normalized_profiles = []
    for profile in artifact.career_profiles:
        if profile.confidence < 0.70 and profile.level != "unknown":
            profile = profile.model_copy(update={"level": "unknown"})
        normalized_profiles.append(profile)
    return artifact.model_copy(update={"career_profiles": normalized_profiles})


def _collect_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "evidence_refs" and isinstance(nested, list):
                refs.update(item for item in nested if isinstance(item, str))
            else:
                refs.update(_collect_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            refs.update(_collect_refs(nested))
    return refs


def _collect_source_refs(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"source_refs", "evidence_refs"} and isinstance(nested, list):
                refs.update(item for item in nested if isinstance(item, str))
            else:
                refs.update(_collect_source_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            refs.update(_collect_source_refs(nested))
    return refs


def _normalized_statement(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _duplicates_application_constraint(artifact: JobExtractionResponse, statement: str) -> bool:
    constraints = artifact.application_constraints
    rules = (
        (
            constraints.work_authorization != "unknown",
            ("work authorization", "authorized to work", "right to work"),
        ),
        (
            constraints.sponsorship_available != "unknown",
            ("sponsorship", "sponsor", "visa"),
        ),
        (constraints.travel_percent is not None, ("travel",)),
        (constraints.clearance is not None, ("clearance",)),
    )
    return any(active and any(marker in statement for marker in markers) for active, markers in rules)
