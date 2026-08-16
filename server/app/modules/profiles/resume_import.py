from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Protocol

from fastapi import HTTPException, UploadFile, status
from lxml import etree
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from app.core.secrets import get_provider_secret
from app.modules.profiles.schemas import ResumeData

MAX_RESUME_BYTES = 8 * 1024 * 1024
MAX_RESUME_TEXT_CHARS = 24_000
MAX_PDF_PAGES = 50
MAX_PDF_EXTRACTED_CHARS = 200_000
PDF_SIGNATURE = b"%PDF-"
DOCX_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_XML_BYTES = 10 * 1024 * 1024
MAX_DOCX_EXTRACTED_CHARS = 200_000
WORDPROCESSINGML_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


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

Generate 3-5 realistic "target_roles" as common job titles that fit the supported experience,
skills, education, and accomplishments. Treat these as recommendations, not extracted facts.
Do not recommend unsupported seniority, management responsibility, licenses, or specialties.
Prefer specific recognizable titles over broad categories, order them from strongest to weakest
fit, and avoid near-duplicates. Return an empty array only when the evidence is too thin to make
a responsible recommendation.

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

Use empty arrays when an extracted section is not present. Put ambiguous or missing items that
need user review in "notes".
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


def validate_pdf_signature(content: bytes) -> None:
    if not content.startswith(PDF_SIGNATURE):
        raise HTTPException(status_code=400, detail="Uploaded PDF content does not have a valid PDF signature.")


def validate_docx_signature(content: bytes) -> None:
    if not content.startswith(DOCX_SIGNATURES):
        raise HTTPException(status_code=400, detail="Uploaded DOCX content is not a valid Word package.")


def extract_pdf_text(content: bytes) -> str:
    validate_pdf_signature(content)
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise HTTPException(status_code=400, detail="Encrypted PDF documents are not supported.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise HTTPException(
                status_code=400,
                detail=f"PDF documents may contain at most {MAX_PDF_PAGES} pages.",
            )
        pages: list[str] = []
        extracted_chars = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            extracted_chars += len(page_text)
            if extracted_chars > MAX_PDF_EXTRACTED_CHARS:
                raise HTTPException(status_code=400, detail="PDF extracted text exceeds the processing limit.")
            pages.append(page_text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not safely read the uploaded PDF.") from exc

    text = redact_resume_personal_info("\n\n".join(page for page in pages if page.strip()))
    if not text:
        raise HTTPException(status_code=400, detail="No selectable text was found in the PDF.")
    return text


def extract_docx_text(content: bytes) -> str:
    validate_docx_signature(content)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            entries = package.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) > MAX_DOCX_ENTRIES:
                raise HTTPException(status_code=400, detail="DOCX package contains too many entries.")
            if sum(entry.file_size for entry in entries) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise HTTPException(status_code=400, detail="DOCX expanded content exceeds the processing limit.")
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise HTTPException(status_code=400, detail="Uploaded DOCX content is missing required Word parts.")

            header_parts = sorted(name for name in names if re.fullmatch(r"word/header\d+\.xml", name))
            footer_parts = sorted(name for name in names if re.fullmatch(r"word/footer\d+\.xml", name))
            optional_parts = [name for name in ("word/footnotes.xml", "word/endnotes.xml") if name in names]
            parts = [*header_parts, "word/document.xml", *optional_parts, *footer_parts]
            paragraphs: list[str] = []
            extracted_chars = 0
            parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=False)
            word = f"{{{WORDPROCESSINGML_NAMESPACE}}}"

            for part_name in parts:
                info = package.getinfo(part_name)
                if info.file_size > MAX_DOCX_XML_BYTES:
                    raise HTTPException(status_code=400, detail="A DOCX XML part exceeds the processing limit.")
                root = etree.fromstring(package.read(part_name), parser=parser)
                if root.getroottree().docinfo.doctype:
                    raise HTTPException(status_code=400, detail="DOCX XML document types are not supported.")
                for paragraph in root.iter(f"{word}p"):
                    chunks: list[str] = []
                    for element in paragraph.iter():
                        if element.tag == f"{word}t" and element.text:
                            chunks.append(element.text)
                        elif element.tag == f"{word}tab":
                            chunks.append("\t")
                        elif element.tag in {f"{word}br", f"{word}cr"}:
                            chunks.append("\n")
                    line = "".join(chunks).strip()
                    if line:
                        extracted_chars += len(line)
                        if extracted_chars > MAX_DOCX_EXTRACTED_CHARS:
                            raise HTTPException(status_code=400, detail="DOCX extracted text exceeds the processing limit.")
                        paragraphs.append(line)
    except HTTPException:
        raise
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Could not safely read the uploaded DOCX document.") from exc

    text = redact_resume_personal_info("\n".join(paragraphs))
    if not text:
        raise HTTPException(status_code=400, detail="No readable text was found in the DOCX document.")
    return text


async def extract_resume_text(file: UploadFile) -> str:
    if file.content_type not in {"application/pdf", "application/x-pdf", DOCX_CONTENT_TYPE}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX resume uploads are supported right now.")

    content = await file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Resume document is larger than 8 MB.")
    if file.content_type == DOCX_CONTENT_TYPE:
        return extract_docx_text(content)
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
            raise HTTPException(status_code=502, detail="OpenAI returned an empty resume analysis response.")
        try:
            payload = json.loads(content)
            return ResumeData.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=502,
                detail="The resume analysis service returned an invalid response. Retry or create the profile manually.",
            ) from exc
