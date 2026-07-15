from __future__ import annotations

import json
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.core.secrets import get_provider_secret
from app.modules.jobs.schemas import JobDescriptionData


class JobDescriptionParser(Protocol):
    def parse(self, raw_description_text: str) -> JobDescriptionData:
        ...


JOB_DESCRIPTION_SCHEMA = {
    "name": "dalijob_job_description",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "company": {"type": "string"},
            "summary": {"type": "string"},
            "responsibilities": {"type": "array", "items": {"type": "string"}},
            "required_skills": {"type": "array", "items": {"type": "string"}},
            "preferred_skills": {"type": "array", "items": {"type": "string"}},
            "required_experience": {"type": "array", "items": {"type": "string"}},
            "preferred_experience": {"type": "array", "items": {"type": "string"}},
            "education": {"type": "array", "items": {"type": "string"}},
            "certifications": {"type": "array", "items": {"type": "string"}},
            "tools_and_technologies": {"type": "array", "items": {"type": "string"}},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "seniority_level": {"type": "string"},
            "employment_type": {"type": "string"},
            "security_clearance": {"type": "string"},
            "work_location": {"type": "string"},
            "salary_range": {"type": "string"},
            "application_deadline": {"type": "string"},
        },
        "required": [
            "title",
            "company",
            "summary",
            "responsibilities",
            "required_skills",
            "preferred_skills",
            "required_experience",
            "preferred_experience",
            "education",
            "certifications",
            "tools_and_technologies",
            "keywords",
            "seniority_level",
            "employment_type",
            "security_clearance",
            "work_location",
            "salary_range",
            "application_deadline",
        ],
    },
}

SYSTEM_PROMPT = """You convert job posting text into DaliJob job_description JSON.

Rules:
- Extract facts from the provided job posting only.
- Do not invent requirements, benefits, salary, company name, deadlines, or skills.
- If a field is not present, use an empty string or an empty array.
- Keep responsibilities focused on the actual job duties.
- Put must-have qualifications in required_* fields and nice-to-have qualifications in preferred_* fields.
- Put programming languages, platforms, software, methods, and named tools in tools_and_technologies when applicable.
- keywords should contain concise matching terms useful for resume comparison.
"""


def build_job_parse_prompt(raw_description_text: str) -> str:
    return f"Parse this job posting text into DaliJob job_description JSON:\n\n{raw_description_text}"


class OpenAIJobDescriptionParser:
    def __init__(self, model: str) -> None:
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def parse(self, raw_description_text: str) -> JobDescriptionData:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_job_parse_prompt(raw_description_text)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": JOB_DESCRIPTION_SCHEMA,
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI returned an empty job description response.",
            )
        try:
            payload = json.loads(content)
            return JobDescriptionData.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The job parser returned an invalid response. Retry or use manual job entry.",
            ) from exc
