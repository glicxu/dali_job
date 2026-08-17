from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.core.secrets import get_provider_secret
from app.modules.matching_v2.diagnostics import (
    record_model_error,
    record_model_request,
    record_model_response,
    record_validation_error,
)
from app.modules.matching_v2.canonical import EvidenceSpan
from app.modules.matching_v2.prompts import (
    CANDIDATE_EXTRACTION_SYSTEM_PROMPT,
    JOB_EXTRACTION_SYSTEM_PROMPT,
    build_extraction_user_prompt,
    build_job_repair_user_prompt,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, match_explicit_alternative_policy
from app.modules.matching_v2.schemas import (
    CandidateExtractionResponse,
    JobExtractionResponse,
    JobExtractionProviderResponse,
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
    repair_attempted: bool = False
    repair_count: int = 0


class JobProfileValidationFailed(HTTPException):
    """Privacy-safe public failure for an invalid provider extraction."""

    def __init__(self, *, repair_attempted: bool) -> None:
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail="Job Profile validation failed.")
        self.repair_attempted = repair_attempted


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
        user_prompt = build_extraction_user_prompt(
            spans=[
                {
                    "span_id": span.span_id,
                    "section": span.section,
                    "excerpt": span.excerpt,
                }
                for span in selected
            ]
        )
        response_format = {
            "type": "json_schema",
            "json_schema": candidate_response_format([span.span_id for span in selected]),
        }
        record_model_request(
            stage="candidate_profile",
            model=self._model,
            system_prompt=CANDIDATE_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=response_format,
        )
        try:
            response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": CANDIDATE_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_format,
            )
        except Exception as exc:
            record_model_error(stage="candidate_profile", model=self._model, error=exc)
            raise
        content = response.choices[0].message.content
        record_model_response(
            stage="candidate_profile",
            model=self._model,
            provider_response_id=getattr(response, "id", None),
            content=content,
        )
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The candidate-profile provider returned an empty response.",
            )
        try:
            artifact = CandidateExtractionResponse.model_validate(json.loads(content))
            artifact = validate_candidate_extraction(
                artifact,
                {span.span_id for span in selected},
                evidence_by_ref={span.span_id: span.excerpt for span in selected},
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            record_validation_error(stage="candidate_profile", model=self._model, error=exc)
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
        span_payload = [
            {"span_id": span.span_id, "section": span.section, "excerpt": span.excerpt}
            for span in selected
        ]
        user_prompt = build_extraction_user_prompt(spans=span_payload)
        allowed_refs = {span.span_id for span in selected}
        response_format = {
            "type": "json_schema",
            "json_schema": job_response_format(sorted(allowed_refs)),
        }
        response, content = self._request(
            stage="job_profile",
            user_prompt=user_prompt,
            response_format=response_format,
        )
        if content is None:
            raise JobProfileValidationFailed(repair_attempted=False)
        provider_reference = getattr(response, "id", None)
        repair_attempted = False
        try:
            artifact = self._decode_and_validate(
                content,
                allowed_refs=allowed_refs,
                source_spans=selected,
                cleanup=cleanup,
                omitted_span_count=len(omitted),
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            record_validation_error(stage="job_profile", model=self._model, error=exc)
            repair_attempted = True
            repair_prompt = build_job_repair_user_prompt(
                spans=span_payload,
                errors=job_validation_feedback(exc),
            )
            repair_response, repair_content = self._request(
                stage="job_profile_repair",
                user_prompt=repair_prompt,
                response_format=response_format,
            )
            provider_reference = getattr(repair_response, "id", None)
            if repair_content is None:
                raise JobProfileValidationFailed(repair_attempted=True) from exc
            try:
                artifact = self._decode_and_validate(
                    repair_content,
                    allowed_refs=allowed_refs,
                    source_spans=selected,
                    cleanup=cleanup,
                    omitted_span_count=len(omitted),
                )
            except (json.JSONDecodeError, ValidationError, ValueError) as repair_exc:
                record_validation_error(stage="job_profile_repair", model=self._model, error=repair_exc)
                raise JobProfileValidationFailed(repair_attempted=True) from repair_exc

        artifact = assign_alternative_policies(artifact)
        try:
            artifact = validate_job_extraction(
                artifact,
                allowed_refs,
                source_spans=selected,
                duplicate_spans_removed=cleanup.duplicate_spans_removed,
                boilerplate_spans_ignored=cleanup.boilerplate_spans_ignored,
                omitted_span_count=len(omitted),
            )
        except (ValidationError, ValueError) as exc:
            record_validation_error(stage="job_profile_policy_assignment", model=self._model, error=exc)
            raise JobProfileValidationFailed(repair_attempted=repair_attempted) from exc

        return JobExtractionResult(
            artifact=artifact,
            model_id=self._model,
            provider_execution_reference=provider_reference,
            omitted_span_ids=tuple(span.span_id for span in omitted),
            repair_attempted=repair_attempted,
            repair_count=1 if repair_attempted else 0,
        )

    def _request(
        self,
        *,
        stage: str,
        user_prompt: str,
        response_format: dict[str, object],
    ) -> tuple[object, str | None]:
        record_model_request(
            stage=stage,
            model=self._model,
            system_prompt=JOB_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=response_format,
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": JOB_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=response_format,
            )
        except Exception as exc:
            record_model_error(stage=stage, model=self._model, error=exc)
            raise
        content = response.choices[0].message.content
        record_model_response(
            stage=stage,
            model=self._model,
            provider_response_id=getattr(response, "id", None),
            content=content,
        )
        return response, content

    @staticmethod
    def _decode_and_validate(
        content: str,
        *,
        allowed_refs: set[str],
        source_spans: list[EvidenceSpan],
        cleanup: JobCleanupResult,
        omitted_span_count: int,
    ) -> JobExtractionResponse:
        provider_artifact = JobExtractionProviderResponse.model_validate(json.loads(content))
        artifact = JobExtractionResponse.model_validate(provider_artifact.model_dump(mode="json"))
        return validate_job_extraction(
            artifact,
            allowed_refs,
            source_spans=source_spans,
            duplicate_spans_removed=cleanup.duplicate_spans_removed,
            boilerplate_spans_ignored=cleanup.boilerplate_spans_ignored,
            omitted_span_count=omitted_span_count,
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
        # Evidence spans may contain a valid section followed by a legal/footer fragment.
        # Drop only spans that are themselves boilerplate, not mixed substantive spans.
        if any(normalized.startswith(marker) for marker in _BOILERPLATE_MARKERS):
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


def assign_alternative_policies(artifact: JobExtractionResponse) -> JobExtractionResponse:
    """Assign registry IDs from normalized employer alternatives; the model never owns them."""

    requirements = [
        requirement.model_copy(update={
            "policy_alternative_group": match_explicit_alternative_policy(
                [" or ".join(_alternative_members(group)) for group in requirement.alternative_groups]
            )
        })
        for requirement in artifact.requirements
    ]
    return artifact.model_copy(update={"requirements": requirements})


def job_validation_feedback(exc: Exception) -> list[dict[str, str]]:
    """Convert detailed local failures into bounded, value-free repair feedback."""

    if isinstance(exc, ValidationError):
        feedback: list[dict[str, str]] = []
        for error in exc.errors(include_url=False, include_context=False, include_input=False)[:10]:
            feedback.append({
                "code": "SCHEMA_VALIDATION_FAILED",
                "path": _json_path(error.get("loc", ())),
                "message": "the value does not satisfy the required output schema",
            })
        return feedback or [{
            "code": "SCHEMA_VALIDATION_FAILED",
            "path": "$",
            "message": "the response does not satisfy the required output schema",
        }]

    message = str(exc)
    rules = (
        ("Unknown job source references", "UNKNOWN_SOURCE_REFERENCE", "$", "all source references must use supplied span IDs"),
        ("level range cannot contain unknown", "INVALID_LEVEL_ENDPOINT", "$.career_context.acceptable_level_range", "level range endpoints must be concrete permitted levels"),
        ("level range minimum cannot exceed", "LEVEL_RANGE_REVERSED", "$.career_context.acceptable_level_range", "minimum level must not exceed maximum level"),
        ("Compensation minimum cannot exceed", "COMPENSATION_RANGE_REVERSED", "$.compensation", "compensation minimum must not exceed maximum"),
        ("duplicates an application constraint", "DUPLICATE_APPLICATION_CONSTRAINT", "$.requirements", "a represented application constraint must not also be a requirement"),
        ("primary role family cannot be adjacent", "DUPLICATE_ADJACENT_ROLE", "$.career_context.adjacent_role_families", "the primary role family must not appear as adjacent"),
        ("unknown cannot be an adjacent", "UNKNOWN_ADJACENT_ROLE", "$.career_context.adjacent_role_families", "unknown is not an adjacent role family"),
        ("Missing required-section coverage", "MISSING_REQUIRED_SECTION_COVERAGE", "$.requirements", "extract all substantive required qualifications"),
        ("Missing optional-section coverage", "MISSING_OPTIONAL_SECTION_COVERAGE", "$.requirements", "extract all substantive optional qualifications"),
        ("Missing responsibility-section coverage", "MISSING_RESPONSIBILITY_SECTION_COVERAGE", "$.responsibilities", "extract all substantive responsibilities"),
        ("Requirement is not owned by a qualification section", "REQUIREMENT_SECTION_OWNERSHIP", "$.requirements", "when qualification sections exist, every requirement must cite one of them"),
        ("Unsupported employment type", "UNSUPPORTED_EMPLOYMENT_TYPE", "$.employment_type", "use unknown unless the source explicitly states an employment type"),
        ("Duplicate job requirements conflict", "DUPLICATE_REQUIREMENT_CONFLICT", "$.requirements", "duplicate requirements must be merged without conflicting metadata"),
        ("Duplicate alternative-group references conflict", "DUPLICATE_ALTERNATIVE_GROUP_REFERENCE", "$.requirements", "alternative-group references must be unique within a merged requirement"),
        ("local_ref values must be unique", "DUPLICATE_REQUIREMENT_REFERENCE", "$.requirements", "each requirement local_ref must be unique"),
    )
    for marker, code, path, safe_message in rules:
        if marker.casefold() in message.casefold():
            return [{"code": code, "path": path, "message": safe_message}]
    return [{
        "code": "JOB_PROFILE_SEMANTIC_INVALID",
        "path": "$",
        "message": "the complete Job Profile must satisfy all semantic validation rules",
    }]


def _json_path(location: object) -> str:
    path = "$"
    if not isinstance(location, (tuple, list)):
        return path
    for part in location:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def validate_job_extraction(
    artifact: JobExtractionResponse,
    allowed_source_refs: set[str],
    *,
    source_spans: list[EvidenceSpan] | None = None,
    duplicate_spans_removed: int = 0,
    boilerplate_spans_ignored: int = 0,
    omitted_span_count: int = 0,
) -> JobExtractionResponse:
    unknown = _collect_source_refs(artifact.model_dump(mode="json")) - allowed_source_refs
    if unknown:
        raise ValueError(f"Unknown job source references: {sorted(unknown)}")
    career = artifact.career_context
    if career.primary_role_family in career.adjacent_role_families:
        raise ValueError("Primary role family cannot be adjacent.")
    if "unknown" in career.adjacent_role_families:
        raise ValueError("Unknown cannot be an adjacent role family.")
    level_range = artifact.career_context.acceptable_level_range
    if level_range is not None:
        order = {name: index for index, name in enumerate(
            ("student_or_intern", "entry", "junior", "mid", "senior", "staff", "principal")
        )}
        if level_range.minimum == "unknown" or level_range.maximum == "unknown":
            raise ValueError("Job level range cannot contain unknown endpoints.")
        if order[level_range.minimum] > order[level_range.maximum]:
            raise ValueError("Job level range minimum cannot exceed maximum.")

    location, location_warning = _normalize_location_placeholders(artifact.location)
    artifact = artifact.model_copy(update={"location": location})

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
        if _duplicates_application_constraint(artifact, key):
            raise ValueError(
                f"Requirement duplicates an application constraint: {requirement.local_ref}"
            )
        prior_index = positions.get(key)
        if prior_index is None:
            positions[key] = len(requirements)
            requirements.append(requirement)
            continue
        prior = requirements[prior_index]
        conflict_fields = ("category", "scoring_dimension", "importance", "minimum_years")
        if any(getattr(prior, field) != getattr(requirement, field) for field in conflict_fields):
            raise ValueError(f"Duplicate job requirements conflict: {prior.local_ref}, {requirement.local_ref}")
        requirements[prior_index] = prior.model_copy(
            update={
                "acceptable_evidence_contexts": list(dict.fromkeys([
                    *prior.acceptable_evidence_contexts, *requirement.acceptable_evidence_contexts
                ])),
                "alternative_groups": _merge_alternative_groups(
                    prior.alternative_groups, requirement.alternative_groups
                ),
                "source_refs": list(dict.fromkeys([*prior.source_refs, *requirement.source_refs])),
            }
        )
    warnings = list(artifact.cleanup.warnings)
    if source_spans:
        qualification_refs = _qualification_section_refs(source_spans)
        if qualification_refs:
            filtered_requirements = [
                requirement
                for requirement in requirements
                if qualification_refs.intersection(requirement.source_refs)
            ]
            removed_count = len(requirements) - len(filtered_requirements)
            if removed_count:
                warnings.append(
                    f"NON_QUALIFICATION_REQUIREMENTS_REMOVED:{removed_count}"
                )
            requirements = filtered_requirements
    artifact = artifact.model_copy(update={"requirements": requirements})
    if source_spans:
        _validate_section_coverage(artifact, source_spans)
        _validate_requirement_section_ownership(artifact, source_spans)
        _validate_employment_type(artifact, source_spans)
    if location_warning:
        warnings.append(location_warning)
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
    *,
    evidence_by_ref: dict[str, str] | None = None,
) -> CandidateExtractionResponse:
    unknown = _collect_refs(artifact.model_dump(mode="json")) - allowed_evidence_refs
    if unknown:
        raise ValueError(f"Unknown candidate evidence references: {sorted(unknown)}")

    if evidence_by_ref is not None:
        for publication in artifact.publications:
            evidence = " ".join(evidence_by_ref[ref] for ref in publication.evidence_refs)
            if _evidence_text(publication.title) not in _evidence_text(evidence):
                raise ValueError("Candidate publication title is not explicitly supported by its evidence.")
        for patent in artifact.patents:
            evidence = " ".join(evidence_by_ref[ref] for ref in patent.evidence_refs)
            if _evidence_text(patent.title) not in _evidence_text(evidence):
                raise ValueError("Candidate patent title is not explicitly supported by its evidence.")

    normalization_warnings: list[str] = []
    normalized_experience = []
    for experience in artifact.experience:
        if experience.is_current and experience.end_date is not None:
            experience = experience.model_copy(update={"end_date": None})
            normalization_warnings.append("CURRENT_EXPERIENCE_END_DATE_CLEARED")
        normalized_experience.append(experience)

    normalized_profiles = []
    for profile in artifact.career_profiles:
        if profile.confidence < 0.70 and profile.level != "unknown":
            profile = profile.model_copy(update={"level": "unknown"})
        normalized_profiles.append(profile)
    quality = artifact.quality
    if normalization_warnings:
        quality = quality.model_copy(update={
            "warnings": list(dict.fromkeys([
                *quality.warnings,
                *normalization_warnings,
            ]))[:20]
        })
    return artifact.model_copy(update={
        "experience": normalized_experience,
        "career_profiles": normalized_profiles,
        "quality": quality,
    })


def _evidence_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


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


def _normalize_location_placeholders(location):
    marker = re.compile(r"(?:[,;]\s*)?\+\d+\s+more\b", flags=re.I)
    display = marker.sub("", location.display).strip(" ,;") if location.display else None
    regions = [item for item in location.remote_regions if not marker.fullmatch(item.strip())]
    changed = display != location.display or regions != location.remote_regions
    return location.model_copy(update={"display": display or None, "remote_regions": regions}), (
        "SOURCE_LOCATION_PLACEHOLDER_REMOVED" if changed else None
    )


_SECTION_HEADINGS = {
    "requirements",
    "required qualifications",
    "minimum qualifications",
    "basic qualifications",
    "preferred qualifications",
    "responsibilities",
    "what you'll do",
    "what you will do",
}


def _substantive_section_refs(spans: list[EvidenceSpan], section: str) -> set[str]:
    refs: set[str] = set()
    for span in spans:
        if span.section != section:
            continue
        normalized = _normalized_statement(span.excerpt).strip(":")
        if normalized and normalized not in _SECTION_HEADINGS:
            refs.add(span.span_id)
    return refs


def _validate_section_coverage(artifact: JobExtractionResponse, spans: list[EvidenceSpan]) -> None:
    required_refs = _substantive_section_refs(spans, "requirements")
    optional_refs = _substantive_section_refs(spans, "preferred_requirements")
    responsibility_refs = _substantive_section_refs(spans, "responsibilities")
    if required_refs and not any(
        item.importance == "required" and required_refs.intersection(item.source_refs)
        for item in artifact.requirements
    ):
        raise ValueError("Missing required-section coverage.")
    if optional_refs and not any(
        item.importance == "optional" and optional_refs.intersection(item.source_refs)
        for item in artifact.requirements
    ):
        raise ValueError("Missing optional-section coverage.")
    if responsibility_refs and not any(
        responsibility_refs.intersection(item.source_refs) for item in artifact.responsibilities
    ):
        raise ValueError("Missing responsibility-section coverage.")


def _validate_requirement_section_ownership(
    artifact: JobExtractionResponse, spans: list[EvidenceSpan]
) -> None:
    qualification_refs = _qualification_section_refs(spans)
    if not qualification_refs:
        return
    for requirement in artifact.requirements:
        if not qualification_refs.intersection(requirement.source_refs):
            raise ValueError("Requirement is not owned by a qualification section.")


def _qualification_section_refs(spans: list[EvidenceSpan]) -> set[str]:
    return {
        span.span_id for span in spans
        if span.section in {"requirements", "preferred_requirements"}
        and _normalized_statement(span.excerpt).strip(":") not in _SECTION_HEADINGS
    }


def _validate_employment_type(artifact: JobExtractionResponse, spans: list[EvidenceSpan]) -> None:
    if artifact.employment_type == "unknown":
        return
    markers = {
        "full_time": ("full time", "full-time", "full_time"),
        "part_time": ("part time", "part-time", "part_time"),
        "contract": ("contract", "contractor"),
        "temporary": ("temporary", "temp position"),
        "internship": ("internship", "intern position"),
    }[artifact.employment_type]
    source = " ".join(_normalized_statement(span.excerpt) for span in spans)
    if not any(marker in source for marker in markers):
        raise ValueError("Unsupported employment type.")


def _merge_alternative_groups(first: list, second: list) -> list:
    merged = []
    positions: dict[tuple[str, ...], int] = {}
    refs: dict[str, tuple[str, ...]] = {}
    for group in [*first, *second]:
        key = tuple(sorted(_normalized_statement(item) for item in group.any_of))
        prior_key = refs.get(group.local_ref)
        if prior_key is not None and prior_key != key:
            raise ValueError("Duplicate alternative-group references conflict.")
        refs[group.local_ref] = key
        position = positions.get(key)
        if position is None:
            positions[key] = len(merged)
            merged.append(group)
        else:
            prior = merged[position]
            merged[position] = prior.model_copy(update={
                "source_refs": list(dict.fromkeys([*prior.source_refs, *group.source_refs]))
            })
    return merged


def _alternative_members(group) -> list[str]:
    return list(group["any_of"] if isinstance(group, dict) else group.any_of)


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
