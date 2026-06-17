from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.modules.resume_job_match.schemas import (
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
)
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher

router = APIRouter(prefix="/resume-job-matches", tags=["resume-job-matches"])


def get_resume_job_matcher(request: Request) -> ResumeJobMatcher:
    runtime = request.app.state.runtime
    return OpenAIResumeJobMatcher(model=runtime.openai_model)


@router.post("", response_model=ResumeJobMatchResponse)
def create_resume_job_match(
    payload: ResumeJobMatchRequest,
    matcher: ResumeJobMatcher = Depends(get_resume_job_matcher),
) -> ResumeJobMatchResponse:
    return matcher.compare(payload)
