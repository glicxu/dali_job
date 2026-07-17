from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.applications.schemas import ApplicationJobSummary

InterviewType = Literal[
    "recruiter_screen",
    "phone",
    "technical",
    "behavioral",
    "hiring_manager",
    "panel",
    "final",
    "other",
]
InterviewStatus = Literal["scheduled", "completed", "cancelled"]
InterviewStage = Literal[
    "recruiter_contact",
    "assessment",
    "phone_screen",
    "technical_interview",
    "final_interview",
    "other",
]
InterviewOutcome = Literal["advanced", "rejected", "offer", "withdrawn", "no_decision"]


class InterviewCreateRequest(BaseModel):
    application_id: int = Field(..., gt=0)
    interview_type: InterviewType = "other"
    stage: InterviewStage = "other"
    scheduled_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=80)
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    location_or_url: str | None = Field(default=None, max_length=2048)
    private_notes: str | None = Field(default=None, max_length=20_000)


class InterviewUpdateRequest(BaseModel):
    interview_type: InterviewType | None = None
    status: InterviewStatus | None = None
    stage: InterviewStage | None = None
    scheduled_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=80)
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    location_or_url: str | None = Field(default=None, max_length=2048)
    outcome: InterviewOutcome | None = None
    private_notes: str | None = Field(default=None, max_length=20_000)


class InterviewNoteCreateRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=20_000)


class InterviewNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    interview_id: int
    body: str
    created_at: datetime


class InterviewPrepRequest(BaseModel):
    interview_id: int = Field(..., gt=0)
    resume_profile_id: int = Field(..., gt=0)
    company_notes: str | None = Field(default=None, max_length=30_000)


class PrepStudyPriority(BaseModel):
    topic: str
    reason: str
    source_evidence: list[str] = Field(default_factory=list)


class PrepLikelyQuestion(BaseModel):
    question: str
    rationale: str
    preparation_points: list[str] = Field(default_factory=list)


class PrepTalkingPoint(BaseModel):
    topic: str
    supported_claim: str
    resume_evidence: str


class PrepSkillGap(BaseModel):
    skill: str
    gap_evidence: str
    study_action: str


class InterviewPrepOutput(BaseModel):
    overview: str
    study_priorities: list[PrepStudyPriority] = Field(default_factory=list)
    likely_questions: list[PrepLikelyQuestion] = Field(default_factory=list)
    talking_points: list[PrepTalkingPoint] = Field(default_factory=list)
    skill_gaps: list[PrepSkillGap] = Field(default_factory=list)
    questions_to_research: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InterviewPrepGuideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    interview_id: int
    operation_id: int | None = None
    resume_profile_id: int | None = None
    source_warnings: list[str] = Field(default_factory=list)
    output_data: InterviewPrepOutput | None = None
    provider: str
    model_name: str | None = None
    prompt_version: str
    schema_version: str
    provider_execution_reference: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class InterviewResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    application_id: int
    interview_type: InterviewType
    status: InterviewStatus
    stage: InterviewStage
    scheduled_at: datetime | None = None
    timezone: str
    duration_minutes: int | None = None
    location_or_url: str | None = None
    outcome: InterviewOutcome | None = None
    private_notes: str | None = None
    job: ApplicationJobSummary | None = None
    created_at: datetime
    updated_at: datetime


class InterviewDetailResponse(InterviewResponse):
    notes: list[InterviewNoteResponse] = Field(default_factory=list)
    prep_guides: list[InterviewPrepGuideResponse] = Field(default_factory=list)
