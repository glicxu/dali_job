from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.modules.profiles.resume_import import MAX_RESUME_BYTES, extract_pdf_text, redact_resume_personal_info
from app.modules.profiles.resume_import import validate_pdf_signature

SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "text/plain",
}


def safe_file_name(file_name: str | None) -> str:
    raw_name = (file_name or "document").replace("\\", "/")
    name = raw_name.rsplit("/", 1)[-1]
    name = "".join(character for character in name if ord(character) >= 32 and ord(character) != 127).strip()
    if name in {"", ".", ".."}:
        return "document"
    return name[:255]


def normalized_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _validate_plain_text(content: bytes) -> None:
    if content.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF content was declared as plain text.")
    if any(byte < 32 and byte not in {9, 10, 13} for byte in content):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plain text upload contains binary data.")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plain text documents must use UTF-8 encoding.",
        ) from exc


def validate_upload_content(content: bytes, content_type: str) -> None:
    if content_type in {"application/pdf", "application/x-pdf"}:
        validate_pdf_signature(content)
        return
    if content_type == "text/plain":
        _validate_plain_text(content)
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Only PDF and plain text document uploads are supported right now.",
    )


async def read_supported_upload(file: UploadFile) -> bytes:
    content_type = normalized_content_type(file.content_type)
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and plain text document uploads are supported right now.",
        )
    content = await file.read(MAX_RESUME_BYTES + 1)
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Document is larger than 8 MB.")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document upload is empty.")
    validate_upload_content(content, content_type)
    return content


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_redacted_text(content: bytes, content_type: str) -> str | None:
    if content_type in {"application/pdf", "application/x-pdf"}:
        return extract_pdf_text(content)
    if content_type == "text/plain":
        text = content.decode("utf-8")
        return redact_resume_personal_info(text)
    return None


def write_document_file(storage_root: str, content: bytes, original_file_name: str) -> str:
    root = Path(storage_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    suffix = Path(safe_file_name(original_file_name)).suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        suffix = ""
    target = root / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)
