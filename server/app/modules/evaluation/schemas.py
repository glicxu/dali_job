from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.modules.matching_v2.api_schemas import (
    CandidateProfileView,
    JobProfileView,
    QualificationAssessmentView,
)


class JobSnapshotImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: HttpUrl
    benchmark_release: str = Field(default="matching-benchmark-jobs.v1", min_length=1, max_length=100)
    coverage_slot: str = Field(default="", max_length=160)


class JobSnapshotView(BaseModel):
    public_id: str
    benchmark_release: str
    coverage_slot: str
    source_url: str
    source_hash: str
    user_saved_job_id: int
    title: str
    company: str
    raw_description_text: str
    capture_metadata: dict[str, Any]
    created_at: datetime


class JobSnapshotListResponse(BaseModel):
    snapshots: list[JobSnapshotView]


class EvaluationRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_snapshot_id: str = Field(min_length=1, max_length=64)
    resume_profile_id: int = Field(gt=0)


class EvidenceSpanView(BaseModel):
    span_id: str
    section: str
    start_utf8_byte: int
    end_utf8_byte: int
    excerpt: str


class EvaluationSourceView(BaseModel):
    text: str
    spans: list[EvidenceSpanView]


class EvaluationRunSummary(BaseModel):
    public_id: str
    benchmark_release: str
    job_snapshot_id: str
    resume_profile_id: int | None
    candidate_profile_id: str
    job_profile_id: str
    qualification_assessment_id: str
    created_at: datetime


class EvaluationRunListResponse(BaseModel):
    runs: list[EvaluationRunSummary]


class EvaluationRunDetail(EvaluationRunSummary):
    resume_title: str
    job_title: str
    job_company: str
    source_url: str
    resume_source: EvaluationSourceView
    candidate_profile: CandidateProfileView
    job_source: EvaluationSourceView
    job_profile: JobProfileView
    qualification: QualificationAssessmentView
    run_metadata: dict[str, Any]
