from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.profiles import repository
from app.modules.profiles.resume_import import (
    OpenAIResumeProfileParser,
    ResumeImportResponse,
    ResumeProfileParser,
    extract_resume_text,
)
from app.modules.profiles.schemas import (
    ResumeData,
    ResumeProfileCreateRequest,
    ResumeProfileListResponse,
    ResumeProfileResponse,
    ResumeProfileUpdateRequest,
)

router = APIRouter(prefix="/profile", tags=["profile"])
resume_profiles_router = APIRouter(prefix="/resume-profiles", tags=["resume-profiles"])


def get_resume_profile_parser(request: Request) -> ResumeProfileParser:
    runtime = request.app.state.runtime
    return OpenAIResumeProfileParser(model=runtime.openai_model)


@router.post("/resume-imports", response_model=ResumeImportResponse)
async def import_resume_pdf(
    file: UploadFile = File(...),
    parser: ResumeProfileParser = Depends(get_resume_profile_parser),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeImportResponse:
    _ = identity
    resume_text = await extract_resume_text(file)
    suggestions = parser.parse(resume_text)
    return ResumeImportResponse(
        file_name=file.filename or "resume.pdf",
        extracted_text_preview=resume_text[:2000],
        suggestions=suggestions,
    )


@router.post("/resume-imports/apply", response_model=ResumeProfileResponse)
def apply_resume_import(
    payload: ResumeData,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeProfileResponse:
    return repository.apply_resume_suggestions(db, payload, identity)


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
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    resume_profile = repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    repository.soft_delete_resume_profile(db, resume_profile)
