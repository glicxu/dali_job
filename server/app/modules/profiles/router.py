from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.core.provider_ops import GuardedProviderProxy
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents import repository as document_repository
from app.modules.documents.storage import (
    extract_redacted_text,
    read_supported_upload,
    safe_file_name,
    sha256_hex,
    write_document_file,
)
from app.modules.profiles import repository
from app.modules.profiles.resume_import import (
    OpenAIResumeProfileParser,
    ResumeImportResponse,
    ResumeProfileParser,
)
from app.modules.profiles.schemas import (
    ResumeData,
    ResumeImportApplyRequest,
    ResumeProfileCreateRequest,
    ResumeProfileListResponse,
    ResumeProfileResponse,
    ResumeProfileDependencyResponse,
    ResumeProfileUpdateRequest,
)

router = APIRouter(prefix="/profile", tags=["profile"])
resume_profiles_router = APIRouter(prefix="/resume-profiles", tags=["resume-profiles"])


def get_resume_profile_parser(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileParser:
    runtime = request.app.state.runtime
    return cast(
        ResumeProfileParser,
        GuardedProviderProxy(
            factory=lambda: OpenAIResumeProfileParser(model=runtime.openai_model),
            method_name="parse",
            request=request,
            identity=identity,
            provider="openai",
            feature="resume_profile_parse",
        ),
    )


def _parse_resume_or_fallback(parser: ResumeProfileParser, resume_text: str) -> tuple[ResumeData, str | None]:
    try:
        return parser.parse(resume_text), None
    except HTTPException as exc:
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            warning = str(exc.detail)
        else:
            warning = "Resume parsing is temporarily unavailable. Retry parsing or create the profile manually."
        return ResumeData(), warning


@router.post("/resume-imports", response_model=ResumeImportResponse)
async def import_resume_pdf(
    request: Request,
    file: UploadFile = File(...),
    parser: ResumeProfileParser = Depends(get_resume_profile_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeImportResponse:
    content = await read_supported_upload(file)
    file_name = safe_file_name(file.filename)
    content_type = file.content_type or "application/octet-stream"
    resume_text = extract_redacted_text(content, content_type)
    if not resume_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No resume text could be extracted.")
    storage_path = write_document_file(request.app.state.runtime.document_storage_dir, content, file_name)
    created_document = document_repository.create_document_with_version(
        db,
        identity,
        title=Path(file_name).stem or "Resume",
        document_type="resume",
        file_name=file_name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        storage_path=storage_path,
        extracted_text=resume_text,
    )
    suggestions, parse_warning = _parse_resume_or_fallback(parser, resume_text)
    return ResumeImportResponse(
        file_name=file_name,
        document_id=created_document["id"],
        document_version_id=created_document["latest_version"]["id"],
        extracted_text_preview=resume_text[:2000],
        suggestions=suggestions,
        parse_warning=parse_warning,
    )


@router.post("/resume-imports/{document_id}/retry", response_model=ResumeImportResponse)
def retry_resume_import(
    document_id: int,
    parser: ResumeProfileParser = Depends(get_resume_profile_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeImportResponse:
    document = document_repository.get_document_for_identity(db, identity, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume document not found.")
    latest = document_repository.get_latest_version(db, document)
    if latest is None or not latest.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Resume document does not have extracted text available for retry.",
        )
    suggestions, parse_warning = _parse_resume_or_fallback(parser, latest.extracted_text)
    return ResumeImportResponse(
        file_name=latest.file_name,
        document_id=document.id,
        document_version_id=latest.id,
        extracted_text_preview=latest.extracted_text[:2000],
        suggestions=suggestions,
        parse_warning=parse_warning,
    )


@router.post("/resume-imports/apply", response_model=ResumeProfileResponse)
def apply_resume_import(
    payload: ResumeImportApplyRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileResponse:
    return repository.apply_resume_suggestions(
        db,
        payload.resume_data,
        identity,
        source_document_id=payload.source_document_id,
        source_document_version_id=payload.source_document_version_id,
    )


@resume_profiles_router.get("", response_model=ResumeProfileListResponse)
def list_resume_profiles(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileListResponse:
    return ResumeProfileListResponse(resume_profiles=repository.list_resume_profiles(db, identity))


@resume_profiles_router.post("", response_model=ResumeProfileResponse)
def create_resume_profile(
    payload: ResumeProfileCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileResponse:
    return repository.create_resume_profile(db, payload, identity)


@resume_profiles_router.get("/{resume_profile_id}", response_model=ResumeProfileResponse)
def get_resume_profile(
    resume_profile_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileResponse:
    resume_profile = repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    return resume_profile


@resume_profiles_router.patch("/{resume_profile_id}", response_model=ResumeProfileResponse)
def update_resume_profile(
    resume_profile_id: int,
    payload: ResumeProfileUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileResponse:
    resume_profile = repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    return repository.update_resume_profile(db, resume_profile, payload)


@resume_profiles_router.delete("/{resume_profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume_profile(
    resume_profile_id: int,
    force: bool = False,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    resume_profile = repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    dependencies = repository.resume_profile_dependencies(db, resume_profile)
    if dependencies and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This resume profile is in use. Review the dependencies before deleting it.",
                "dependencies": dependencies,
            },
        )
    repository.soft_delete_resume_profile(db, resume_profile)


@resume_profiles_router.get(
    "/{resume_profile_id}/dependencies",
    response_model=ResumeProfileDependencyResponse,
)
def get_resume_profile_dependencies(
    resume_profile_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileDependencyResponse:
    resume_profile = repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    dependencies = repository.resume_profile_dependencies(db, resume_profile)
    return ResumeProfileDependencyResponse(
        can_delete_without_warning=not dependencies,
        dependencies=dependencies,
    )
