from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.profiles import repository
from app.modules.profiles.resume_import import (
    OpenAIResumeProfileParser,
    ResumeImportResponse,
    ResumeProfileParser,
    extract_resume_text,
)
from app.modules.profiles.schemas import ProfileResponse, ProfileUpdateRequest, ResumeData

router = APIRouter(prefix="/profile", tags=["profile"])


def get_resume_profile_parser(request: Request) -> ResumeProfileParser:
    runtime = request.app.state.runtime
    return OpenAIResumeProfileParser(model=runtime.openai_model)


@router.get("", response_model=ProfileResponse)
def get_profile(db: Session = Depends(get_db_session)) -> ProfileResponse:
    return repository.get_or_create_profile(db)


@router.patch("", response_model=ProfileResponse)
def patch_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db_session),
) -> ProfileResponse:
    return repository.update_profile_resume_data(db, payload.resume_data)


@router.post("/resume-imports", response_model=ResumeImportResponse)
async def import_resume_pdf(
    file: UploadFile = File(...),
    parser: ResumeProfileParser = Depends(get_resume_profile_parser),
) -> ResumeImportResponse:
    resume_text = await extract_resume_text(file)
    suggestions = parser.parse(resume_text)
    return ResumeImportResponse(
        file_name=file.filename or "resume.pdf",
        extracted_text_preview=resume_text[:2000],
        suggestions=suggestions,
    )


@router.post("/resume-imports/apply", response_model=ProfileResponse)
def apply_resume_import(
    payload: ResumeData,
    db: Session = Depends(get_db_session),
) -> ProfileResponse:
    return repository.apply_resume_suggestions(db, payload)
