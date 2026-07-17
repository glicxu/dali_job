from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.core.secrets import get_provider_secret
from app.modules.interviews.schemas import InterviewPrepOutput


INTERVIEW_PREP_SCHEMA = {
    "name": "dalijob_interview_prep",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "overview": {"type": "string"},
            "study_priorities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "topic": {"type": "string"},
                        "reason": {"type": "string"},
                        "source_evidence": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["topic", "reason", "source_evidence"],
                },
            },
            "likely_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question": {"type": "string"},
                        "rationale": {"type": "string"},
                        "preparation_points": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["question", "rationale", "preparation_points"],
                },
            },
            "talking_points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "topic": {"type": "string"},
                        "supported_claim": {"type": "string"},
                        "resume_evidence": {"type": "string"},
                    },
                    "required": ["topic", "supported_claim", "resume_evidence"],
                },
            },
            "skill_gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "skill": {"type": "string"},
                        "gap_evidence": {"type": "string"},
                        "study_action": {"type": "string"},
                    },
                    "required": ["skill", "gap_evidence", "study_action"],
                },
            },
            "questions_to_research": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "overview",
            "study_priorities",
            "likely_questions",
            "talking_points",
            "skill_gaps",
            "questions_to_research",
            "warnings",
        ],
    },
}

SYSTEM_PROMPT = """You create evidence-based interview preparation for DaliJob.

Rules:
- Use only the supplied resume snapshot, job snapshot, and optional company notes.
- Never invent resume experience, skills, employers, dates, metrics, education, or accomplishments.
- Every talking_points.resume_evidence value must be copied exactly from one string in the resume snapshot.
- A supported claim may summarize that exact evidence but must not make it stronger.
- Treat absent company information as unknown and add a warning instead of inventing it.
- Put likely questions and priorities in practical review order.
- Describe skill gaps as preparation needs, not as facts about the candidate beyond the supplied evidence.
"""


@dataclass(frozen=True)
class InterviewPrepGenerationResult:
    output: InterviewPrepOutput
    model_name: str
    provider_execution_reference: str | None = None


class InterviewPrepGenerator(Protocol):
    def generate(
        self,
        resume_snapshot: dict,
        job_snapshot: dict,
        company_notes: str | None,
        source_warnings: list[str],
    ) -> InterviewPrepGenerationResult:
        ...


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def resume_evidence_strings(snapshot: dict) -> set[str]:
    evidence: set[str] = set()

    def collect(value: object) -> None:
        if isinstance(value, str) and value.strip():
            evidence.add(_normalized(value))
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                collect(item)

    collect(snapshot)
    return evidence


def enforce_resume_evidence(
    output: InterviewPrepOutput,
    resume_snapshot: dict,
    source_warnings: list[str],
) -> InterviewPrepOutput:
    evidence = resume_evidence_strings(resume_snapshot)
    supported = [
        point for point in output.talking_points if _normalized(point.resume_evidence) in evidence
    ]
    warnings = list(dict.fromkeys([*source_warnings, *output.warnings]))
    if len(supported) != len(output.talking_points):
        warnings.append(
            "One or more talking points were removed because their resume evidence was not present in the selected resume snapshot."
        )
    return output.model_copy(update={"talking_points": supported, "warnings": list(dict.fromkeys(warnings))})


class OpenAIInterviewPrepGenerator:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(
        self,
        resume_snapshot: dict,
        job_snapshot: dict,
        company_notes: str | None,
        source_warnings: list[str],
    ) -> InterviewPrepGenerationResult:
        inputs = {
            "resume_snapshot": resume_snapshot,
            "job_snapshot": job_snapshot,
            "company_notes": company_notes or "",
            "source_warnings": source_warnings,
        }
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Create an interview preparation guide from these immutable inputs:\n\n"
                    + json.dumps(inputs, ensure_ascii=True),
                },
            ],
            response_format={"type": "json_schema", "json_schema": INTERVIEW_PREP_SCHEMA},
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI returned an empty interview preparation response.",
            )
        try:
            parsed = InterviewPrepOutput.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The interview preparation provider returned an invalid response. Retry the operation.",
            ) from exc
        return InterviewPrepGenerationResult(
            output=enforce_resume_evidence(parsed, resume_snapshot, source_warnings),
            model_name=self._model,
            provider_execution_reference=getattr(response, "id", None),
        )
