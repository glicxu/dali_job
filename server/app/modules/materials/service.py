from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.core.secrets import get_provider_secret
from app.modules.materials.schemas import CoverLetterOutput, TailoredResumeOutput

PROMPT_VERSION = "application-materials-v1"
SCHEMA_VERSION = "application-materials-v1"

EVIDENCE_ITEM = {
    "type": "object", "additionalProperties": False,
    "properties": {"text": {"type": "string"}, "source_evidence": {"type": "string"}},
    "required": ["text", "source_evidence"],
}
TAILORED_RESUME_SCHEMA = {
    "name": "dalijob_tailored_resume", "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "headline": {"anyOf": [EVIDENCE_ITEM, {"type": "null"}]},
            **{name: {"type": "array", "items": EVIDENCE_ITEM} for name in ("summary", "skills", "experience", "education", "certifications", "projects")},
            "unsupported_requirements": {"type": "array", "items": {"type": "string"}},
            "tailoring_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["headline", "summary", "skills", "experience", "education", "certifications", "projects", "unsupported_requirements", "tailoring_notes"],
    },
}
COVER_LETTER_SCHEMA = {
    "name": "dalijob_cover_letter", "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "salutation": {"type": "string"},
            "paragraphs": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "resume_evidence": {"type": "array", "items": {"type": "string"}},
                    "job_evidence": {"type": "array", "items": {"type": "string"}},
                }, "required": ["text", "resume_evidence", "job_evidence"],
            }},
            "closing": {"type": "string"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["salutation", "paragraphs", "closing", "warnings"],
    },
}

SYSTEM_PROMPT = """You create application materials for DaliJob from immutable source snapshots.
Never invent or strengthen experience, skills, employers, dates, metrics, education, certifications, or accomplishments.
For resume output, every source_evidence must be copied exactly from the resume source text.
For cover letters, every resume_evidence and job_evidence value must be copied exactly from its respective snapshot.
Omit unsupported claims. Preserve facts while adapting emphasis and wording to the job. Do not include private contact data.
Use 'Dear Hiring Team,' when a recipient is unknown and do not invent a candidate name.
"""


@dataclass(frozen=True)
class MaterialGenerationResult:
    output: TailoredResumeOutput | CoverLetterOutput
    model_name: str
    provider_execution_reference: str | None = None
    warnings: list[str] | None = None


class MaterialGenerator(Protocol):
    def generate(self, material_type: str, resume_snapshot: dict, job_snapshot: dict, notes: str | None, source_material: dict | None = None) -> MaterialGenerationResult: ...


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _corpus(value: object) -> list[str]:
    items: list[str] = []
    def collect(current: object) -> None:
        if isinstance(current, str) and current.strip():
            items.append(_normalized(current))
        elif isinstance(current, list):
            for item in current:
                collect(item)
        elif isinstance(current, dict):
            for item in current.values():
                collect(item)
    collect(value)
    return items


def _is_supported(citation: str, corpus: list[str]) -> bool:
    normalized = _normalized(citation)
    return bool(normalized) and any(normalized in candidate for candidate in corpus)


def enforce_material_evidence(material_type: str, output: TailoredResumeOutput | CoverLetterOutput, resume_snapshot: dict, job_snapshot: dict) -> tuple[TailoredResumeOutput | CoverLetterOutput, list[str]]:
    resume_evidence = _corpus(resume_snapshot)
    job_evidence = _corpus(job_snapshot)
    warnings: list[str] = []
    if material_type == "tailored_resume":
        assert isinstance(output, TailoredResumeOutput)
        updates: dict = {}
        removed = 0
        for field in ("summary", "skills", "experience", "education", "certifications", "projects"):
            supported = [item for item in getattr(output, field) if _is_supported(item.source_evidence, resume_evidence)]
            removed += len(getattr(output, field)) - len(supported)
            updates[field] = supported
        headline = output.headline if output.headline and _is_supported(output.headline.source_evidence, resume_evidence) else None
        removed += int(output.headline is not None and headline is None)
        if removed:
            warnings.append(f"Removed {removed} tailored resume item(s) whose cited evidence was absent from the selected resume version.")
        return output.model_copy(update={**updates, "headline": headline}), warnings
    assert isinstance(output, CoverLetterOutput)
    supported_paragraphs = []
    for paragraph in output.paragraphs:
        resume_ok = all(_is_supported(item, resume_evidence) for item in paragraph.resume_evidence)
        job_ok = all(_is_supported(item, job_evidence) for item in paragraph.job_evidence)
        if (paragraph.resume_evidence or paragraph.job_evidence) and resume_ok and job_ok:
            supported_paragraphs.append(paragraph)
    if len(supported_paragraphs) != len(output.paragraphs):
        warnings.append("Removed one or more cover-letter paragraphs because their cited evidence was absent from the immutable inputs.")
    checked = output.model_copy(update={"paragraphs": supported_paragraphs, "warnings": list(dict.fromkeys([*output.warnings, *warnings]))})
    return checked, warnings


class OpenAIMaterialGenerator:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OPENAI_API_KEY is not configured for the server process.")
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(self, material_type: str, resume_snapshot: dict, job_snapshot: dict, notes: str | None, source_material: dict | None = None) -> MaterialGenerationResult:
        schema = TAILORED_RESUME_SCHEMA if material_type == "tailored_resume" else COVER_LETTER_SCHEMA
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Create a {material_type.replace('_', ' ')} from these inputs:\n\n" + json.dumps({"resume_snapshot": resume_snapshot, "job_snapshot": job_snapshot, "target_notes": notes or "", "source_tailored_resume": source_material or {}}, ensure_ascii=True)},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OpenAI returned an empty application-material response.")
        try:
            parsed_json = json.loads(content)
            output = TailoredResumeOutput.model_validate(parsed_json) if material_type == "tailored_resume" else CoverLetterOutput.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The application-material provider returned an invalid response. Retry the operation.") from exc
        checked, warnings = enforce_material_evidence(material_type, output, resume_snapshot, job_snapshot)
        return MaterialGenerationResult(
            output=checked,
            model_name=self._model,
            provider_execution_reference=getattr(response, "id", None),
            warnings=warnings,
        )
