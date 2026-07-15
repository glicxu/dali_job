from __future__ import annotations

import io
import json
import re
from typing import Protocol

from fastapi import HTTPException, UploadFile, status
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from app.core.secrets import get_provider_secret
from app.modules.profiles.schemas import ResumeData

MAX_RESUME_BYTES = 8 * 1024 * 1024
MAX_RESUME_TEXT_CHARS = 24_000


class ResumeImportResponse(BaseModel):
    file_name: str
    document_id: int
    document_version_id: int
    extracted_text_preview: str
    suggestions: ResumeData
    parse_warning: str | None = None


class ResumeProfileParser(Protocol):
    def parse(self, resume_text: str) -> ResumeData:
        ...


SYSTEM_PROMPT = """
You parse cleaned resume text into a single JSON object for DaliJob's resume_data column.
Extract only facts that are explicitly supported by the resume text. Do not invent employers,
dates, skills, degrees, certifications, projects, metrics, or locations.

Do not extract or return personal identifying contact information. Exclude names, email
addresses, phone numbers, personal websites, social profile URLs, and residential locations.

Generate "headline" and "summary" from the supported resume evidence even when the resume
does not already contain those exact sections. The headline should be a concise professional
title or positioning statement of 12 words or fewer. The summary should be 2-3 short sentences
focused on supported experience, skills, domains, and strengths. Do not include personal
contact details, residential location, or unsupported claims in either field. Use null only
when the resume text does not provide enough evidence to make a useful privacy-safe headline
or summary.

Return exactly this JSON schema:
{
  "headline": string or null,
  "summary": string or null,
  "experience": array of strings,
  "skills": array of strings,
  "education": array of strings,
  "certifications": array of strings,
  "projects": array of strings,
  "awards": array of strings,
  "publications": array of strings,
  "languages": array of strings,
  "volunteer": array of strings,
  "target_roles": array of strings,
  "notes": array of strings
}

Use empty arrays when a section is not present. Put ambiguous or missing items that need
user review in "notes".
""".strip()


RESUME_DATA_SCHEMA = {
    "name": "resume_data",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "headline": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "experience": {"type": "array", "items": {"type": "string"}},
            "skills": {"type": "array", "items": {"type": "string"}},
            "education": {"type": "array", "items": {"type": "string"}},
            "certifications": {"type": "array", "items": {"type": "string"}},
            "projects": {"type": "array", "items": {"type": "string"}},
            "awards": {"type": "array", "items": {"type": "string"}},
            "publications": {"type": "array", "items": {"type": "string"}},
            "languages": {"type": "array", "items": {"type": "string"}},
            "volunteer": {"type": "array", "items": {"type": "string"}},
            "target_roles": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "headline",
            "summary",
            "experience",
            "skills",
            "education",
            "certifications",
            "projects",
            "awards",
            "publications",
            "languages",
            "volunteer",
            "target_roles",
            "notes",
        ],
    },
}


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?1[\s.\-()]*)?(?:\(?\d{3}\)?[\s.\-()]*)\d{3}[\s.\-]*\d{4}(?!\w)"
)
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+\b", re.IGNORECASE)
SOCIAL_RE = re.compile(r"\b(?:linkedin|github|portfolio|website)\b", re.IGNORECASE)
LOCATION_LABEL_RE = re.compile(r"\b(?:address|location|based in|located in)\b", re.IGNORECASE)
CITY_STATE_RE = re.compile(r"^[A-Za-z .'-]+,\s*[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?$")
SECTION_HEADING_RE = re.compile(
    r"^(?:summary|profile|experience|work experience|employment|education|skills|projects|certifications|awards|publications|languages|volunteer)\b",
    re.IGNORECASE,
)


def clean_resume_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    return text.strip()[:MAX_RESUME_TEXT_CHARS]


def redact_resume_personal_info(text: str) -> str:
    """Remove common resume header PII before AI parsing or UI preview."""
    cleaned = clean_resume_text(text)
    lines = cleaned.splitlines()
    redacted: list[str] = []
    found_header_contact = any(
        EMAIL_RE.search(line) or PHONE_RE.search(line) or URL_RE.search(line) or SOCIAL_RE.search(line)
        for line in lines[:8]
    )
    removed_probable_name = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            redacted.append(line)
            continue

        in_header = index < 12
        has_direct_pii = bool(
            EMAIL_RE.search(stripped)
            or PHONE_RE.search(stripped)
            or URL_RE.search(stripped)
            or SOCIAL_RE.search(stripped)
            or LOCATION_LABEL_RE.search(stripped)
        )
        has_header_location = in_header and bool(CITY_STATE_RE.match(stripped))
        likely_name = (
            found_header_contact
            and in_header
            and not removed_probable_name
            and not has_direct_pii
            and not SECTION_HEADING_RE.match(stripped)
            and len(stripped.split()) <= 4
            and not any(char.isdigit() for char in stripped)
        )

        if has_direct_pii or has_header_location or likely_name:
            removed_probable_name = removed_probable_name or likely_name
            continue

        redacted.append(line)

    return clean_resume_text("\n".join(redacted))


def extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF resume: {exc}") from exc

    text = redact_resume_personal_info("\n\n".join(page for page in pages if page.strip()))
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
        api_key = get_provider_secret("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OPENAI_API_KEY is not configured for the server process.",
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def parse(self, resume_text: str) -> ResumeData:
        cleaned_text = redact_resume_personal_info(resume_text)
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
                detail="The resume parser returned an invalid response. Retry or create the profile manually.",
            ) from exc
