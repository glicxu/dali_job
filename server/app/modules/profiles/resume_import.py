from __future__ import annotations

import io
import json
import os
import re
from typing import Protocol

from fastapi import HTTPException, UploadFile, status
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from app.modules.profiles.schemas import ResumeData

MAX_RESUME_BYTES = 8 * 1024 * 1024
MAX_RESUME_TEXT_CHARS = 24_000


class ResumeImportResponse(BaseModel):
    file_name: str
    extracted_text_preview: str
    suggestions: ResumeData


class ResumeProfileParser(Protocol):
    def parse(self, resume_text: str) -> ResumeData:
        ...


SYSTEM_PROMPT = """
You parse cleaned resume text into a single JSON object for DaliJob's resume_data column.
Extract only facts that are explicitly supported by the resume text. Do not invent employers,
dates, skills, degrees, certifications, projects, links, metrics, or locations.

Return exactly this JSON schema:
{
  "name": string or null,
  "headline": string or null,
  "summary": string or null,
  "contact": object with string values,
  "experience": array of strings,
  "skills": array of strings,
  "education": array of strings,
  "certifications": array of strings,
  "projects": array of strings,
  "awards": array of strings,
  "publications": array of strings,
  "links": array of strings,
  "languages": array of strings,
  "volunteer": array of strings,
  "target_roles": array of strings,
  "target_locations": array of strings,
  "notes": array of strings
}

Use empty arrays or empty objects when a section is not present. Put ambiguous or missing
items that need user review in "notes".
""".strip()


RESUME_DATA_SCHEMA = {
    "name": "resume_data",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": ["string", "null"]},
            "headline": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "contact": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "email": {"type": ["string", "null"]},
                    "phone": {"type": ["string", "null"]},
                    "location": {"type": ["string", "null"]},
                    "website": {"type": ["string", "null"]},
                    "linkedin": {"type": ["string", "null"]},
                    "github": {"type": ["string", "null"]},
                },
                "required": ["email", "phone", "location", "website", "linkedin", "github"],
            },
            "experience": {"type": "array", "items": {"type": "string"}},
            "skills": {"type": "array", "items": {"type": "string"}},
            "education": {"type": "array", "items": {"type": "string"}},
            "certifications": {"type": "array", "items": {"type": "string"}},
            "projects": {"type": "array", "items": {"type": "string"}},
            "awards": {"type": "array", "items": {"type": "string"}},
            "publications": {"type": "array", "items": {"type": "string"}},
            "links": {"type": "array", "items": {"type": "string"}},
            "languages": {"type": "array", "items": {"type": "string"}},
            "volunteer": {"type": "array", "items": {"type": "string"}},
            "target_roles": {"type": "array", "items": {"type": "string"}},
            "target_locations": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "name",
            "headline",
            "summary",
            "contact",
            "experience",
            "skills",
            "education",
            "certifications",
            "projects",
            "awards",
            "publications",
            "links",
            "languages",
            "volunteer",
            "target_roles",
            "target_locations",
            "notes",
        ],
    },
}


def clean_resume_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()[:MAX_RESUME_TEXT_CHARS]


def extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF resume: {exc}") from exc

    text = clean_resume_text("\n\n".join(page for page in pages if page.strip()))
    if not text:
        raise HTTPException(status_code=400, detail="No selectable text was found in the PDF.")
    return text


async def extract_resume_text(file: UploadFile) -> str:
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=400, detail="Only PDF resume uploads are supported right now.")

    content = await file.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume PDF is larger than 8 MB.")
    return extract_pdf_text(content)


class OpenAIResumeProfileParser:
    def __init__(self, model: str) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def parse(self, resume_text: str) -> ResumeData:
        cleaned_text = clean_resume_text(resume_text)
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Parse this cleaned resume text into DaliJob resume_data JSON:\n\n{cleaned_text}",
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": RESUME_DATA_SCHEMA,
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise HTTPException(status_code=502, detail="OpenAI returned an empty resume parse response.")
        try:
            payload = json.loads(content)
            return ResumeData.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI returned an invalid resume parse response: {exc}",
            ) from exc
