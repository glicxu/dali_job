from __future__ import annotations

import json
import os
from typing import Protocol

from fastapi import HTTPException, status
from openai import OpenAI
from pydantic import ValidationError

from app.modules.resume_job_match.prompts import SYSTEM_PROMPT, build_user_prompt
from app.modules.resume_job_match.schemas import (
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
)


class ResumeJobMatcher(Protocol):
    def compare(self, request: ResumeJobMatchRequest) -> ResumeJobMatchResponse:
        ...


MATCH_RESULT_SCHEMA = {
    "name": "resume_job_match",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": ["string", "null"]},
            "match_score": {"type": "integer", "minimum": 0, "maximum": 10},
            "score_scale": {"type": "string", "enum": ["0-10"]},
            "summary": {"type": "string"},
            "matched_skills": {"type": "array", "items": {"type": "string"}},
            "missing_skills": {"type": "array", "items": {"type": "string"}},
            "matched_keywords": {"type": "array", "items": {"type": "string"}},
            "missing_keywords": {"type": "array", "items": {"type": "string"}},
            "supported_requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "requirement": {"type": "string"},
                        "resume_evidence": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["requirement", "resume_evidence", "confidence"],
                },
            },
            "unsupported_requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "requirement": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["requirement", "reason"],
                },
            },
            "recommended_resume_updates": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "id",
            "match_score",
            "score_scale",
            "summary",
            "matched_skills",
            "missing_skills",
            "matched_keywords",
            "missing_keywords",
            "supported_requirements",
            "unsupported_requirements",
            "recommended_resume_updates",
        ],
    },
}


class OpenAIResumeJobMatcher:
    def __init__(self, model: str) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def compare(self, request: ResumeJobMatchRequest) -> ResumeJobMatchResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        request.resume_text,
                        request.job_description_text,
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": MATCH_RESULT_SCHEMA,
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OpenAI returned an empty comparison response.",
            )
        try:
            payload = json.loads(content)
            return ResumeJobMatchResponse.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"OpenAI returned an invalid comparison response: {exc}",
            ) from exc
