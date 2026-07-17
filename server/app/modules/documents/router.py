from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents import repository
from app.modules.documents.schemas import (
    DocumentDependencyResponse,
    DocumentDownloadTicketResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentTextResponse,
    DocumentVersionResponse,
)
from app.modules.documents.storage import (
    extract_redacted_text,
    read_supported_upload,
    safe_file_name,
    sha256_hex,
    write_document_file,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/downloads/{token}")
def download_document_with_ticket(
    token: str,
    db: Session = Depends(get_db_session),
) -> FileResponse:
    consumed = repository.consume_download_ticket(db, token)
    if consumed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download ticket is invalid or expired.")
    _ticket, version = consumed
    path = Path(version.storage_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file is missing.")
    db.commit()
    return FileResponse(path, media_type=version.content_type, filename=version.file_name)


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


@router.post("/{document_id}/versions", response_model=DocumentResponse)
async def upload_document_version(
    document_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    content = await read_supported_upload(file)
    file_name = safe_file_name(file.filename)
    content_type = file.content_type or "application/octet-stream"
    storage_path = write_document_file(request.app.state.runtime.document_storage_dir, content, file_name)
    try:
        saved = repository.create_document_version(
            db,
            document,
            file_name=file_name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=sha256_hex(content),
            storage_path=storage_path,
            extracted_text=extract_redacted_text(content, content_type),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DocumentResponse.model_validate(saved)


@router.post("/{document_id}/download-ticket", response_model=DocumentDownloadTicketResponse)
def create_document_download_ticket(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentDownloadTicketResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    version = repository.get_latest_version(db, document)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found.")
    raw_token, ticket = repository.create_download_ticket(db, identity, version)
    return DocumentDownloadTicketResponse(
        download_path=f"/documents/downloads/{raw_token}",
        expires_at=ticket.expires_at,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return DocumentResponse.model_validate(repository.document_response_with_versions(db, document))


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
def list_document_versions(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return repository.document_response_with_versions(db, document)["versions"]


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


@router.get("/{document_id}/dependencies", response_model=DocumentDependencyResponse)
def get_document_dependencies(
    document_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DocumentDependencyResponse:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    dependencies = repository.document_dependencies(db, document)
    return DocumentDependencyResponse(
        can_delete_without_warning=not dependencies,
        dependencies=dependencies,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    force: bool = False,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    document = repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    dependencies = repository.document_dependencies(db, document)
    if dependencies and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This document is in use. Review the dependencies before deleting it.",
                "dependencies": dependencies,
            },
        )
    repository.soft_delete_document(db, document)
    db.commit()
