from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.modules.profiles.resume_import import MAX_RESUME_BYTES, extract_pdf_text, redact_resume_personal_info

SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "text/plain",
}


def safe_file_name(file_name: str | None) -> str:
    name = Path(file_name or "document").name.strip()
    return name or "document"


async def read_supported_upload(file: UploadFile) -> bytes:
    if file.content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and plain text document uploads are supported right now.",
        )
    content = await file.read()
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Document is larger than 8 MB.")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document upload is empty.")
    return content


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_redacted_text(content: bytes, content_type: str) -> str | None:
    if content_type in {"application/pdf", "application/x-pdf"}:
        return extract_pdf_text(content)
    if content_type == "text/plain":
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="ignore")
        return redact_resume_personal_info(text)
    return None


def write_document_file(storage_root: str, content: bytes, original_file_name: str) -> str:
    root = Path(storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_file_name).suffix
    target = root / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)
