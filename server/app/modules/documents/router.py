from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents import repository
from app.modules.documents.schemas import DocumentListResponse, DocumentResponse, DocumentTextResponse
from app.modules.documents.storage import (
    extract_redacted_text,
    read_supported_upload,
    safe_file_name,
    sha256_hex,
    write_document_file,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentListResponse)
def list_documents(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentListResponse:
    return DocumentListResponse(documents=repository.list_documents(db, identity))


@router.post("", response_model=DocumentResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    document_type: str = Form(default="resume"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentResponse:
    content = await read_supported_upload(file)
    file_name = safe_file_name(file.filename)
    content_type = file.content_type or "application/octet-stream"
    storage_path = write_document_file(request.app.state.runtime.document_storage_dir, content, file_name)
    extracted_text = extract_redacted_text(content, content_type)
    created = repository.create_document_with_version(
        db,
        identity,
        title=(title or Path(file_name).stem or "Document").strip(),
        document_type=document_type.strip() or "resume",
        file_name=file_name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        storage_path=storage_path,
        extracted_text=extracted_text,
    )
    return DocumentResponse.model_validate(created)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    latest = repository.get_latest_version(db, document)
    return DocumentResponse.model_validate(repository._document_response(document, latest))


@router.get("/{document_id}/text", response_model=DocumentTextResponse)
def get_document_text(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentTextResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    latest = repository.get_latest_version(db, document)
    if latest is None or not latest.extracted_text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No extracted text is available.")
    return DocumentTextResponse(document_id=document.id, version_id=latest.id, extracted_text=latest.extracted_text)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> FileResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    latest = repository.get_latest_version(db, document)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    path = Path(latest.storage_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing.")
    return FileResponse(path, media_type=latest.content_type, filename=latest.file_name)
