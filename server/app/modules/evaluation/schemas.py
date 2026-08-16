from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
    level_band: Literal[
        "entry_junior", "mid", "senior", "staff_principal", "management_leadership"
    ] | None = None
    description_quality: Literal["structured_high", "mixed_medium", "sparse_or_noisy"] | None = None


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
    review_status: Literal["draft", "accepted", "rejected"]
    review_notes: str
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    created_at: datetime


class JobSnapshotListResponse(BaseModel):
    snapshots: list[JobSnapshotView]


class JobSnapshotReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal["accepted", "rejected"]
    review_notes: str = Field(default="", max_length=4000)


class CoverageSlotView(BaseModel):
    code: str
    label: str
    status: Literal["filled", "awaiting_review", "missing"]
    accepted_snapshot_ids: list[str]


class BenchmarkAdmissionReportView(BaseModel):
    benchmark_release: str
    ready: bool
    slots: list[CoverageSlotView]
    missing_slots: list[str]
    awaiting_review_slots: list[str]
    accepted_count: int
    draft_count: int
    rejected_count: int
    employer_counts: dict[str, int]
    balance_violations: list[str]
    storage_policy: Literal["deferred_internal_testing"]


class CandidateFixtureCatalogItem(BaseModel):
    fixture_id: str
    label: str
    coverage: dict[str, str]
    intended_failure_modes: list[str]
    resume_profile_id: int | None
    loaded: bool


class EvaluationPairCatalogItem(BaseModel):
    pair_id: str
    coverage_slot: str
    candidate_fixture_id: str
    expectation: Literal["strong", "adjacent_or_incomplete", "mismatch"]
    rationale: str
    resume_profile_id: int | None
    job_snapshot_id: str | None
    available: bool


class EvaluationFixtureCatalogView(BaseModel):
    candidate_fixture_release: str
    pair_release: str
    benchmark_release: str
    candidates: list[CandidateFixtureCatalogItem]
    pairs: list[EvaluationPairCatalogItem]


class EvaluationCandidateSourceItem(BaseModel):
    resume_profile_id: int
    label: str
    fixture_group: Literal["internal", "synthetic", "account"]
    candidate_profile_id: str | None
    profile_created_at: datetime | None


class EvaluationCandidateSourceListResponse(BaseModel):
    candidates: list[EvaluationCandidateSourceItem]


class EvaluationRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_snapshot_id: str = Field(min_length=1, max_length=64)
    resume_profile_id: int = Field(gt=0)
    candidate_fixture_release: str = Field(default="candidate-fixtures.local.v1", min_length=1, max_length=100)


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


class EvaluationAnnotationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["candidate_profile", "job_profile", "qualification"]
    target_ref: str = Field(min_length=1, max_length=160)
    review_kind: Literal["independent", "adjudication"] = "independent"
    verdict: Literal["correct", "partially_correct", "incorrect", "missing", "ambiguous"]
    evidence_support: Literal[
        "supported", "partially_supported", "unsupported", "ambiguous", "not_reviewed"
    ] = "not_reviewed"
    expected_value: dict[str, Any] | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    severity: Literal["none", "minor", "major", "severe"] = "none"
    error_taxonomy_code: str | None = Field(default=None, max_length=100)
    comment: str = Field(default="", max_length=4000)


class EvaluationAnnotationView(EvaluationAnnotationCreateRequest):
    public_id: str
    reviewer_user_id: int
    reviewer_label: str
    created_at: datetime


class EvaluationMatchReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_kind: Literal["independent", "adjudication"] = "independent"
    overall_score: int = Field(ge=0, le=100)
    confidence: float = Field(default=1.0, ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class EvaluationMatchReviewView(EvaluationMatchReviewCreateRequest):
    public_id: str
    reviewer_user_id: int
    reviewer_label: str
    recommendation: Literal[
        "strong_match", "good_match", "consider", "stretch", "unlikely_fit"
    ]
    created_at: datetime


class EvaluationMatchReviewSummaryView(BaseModel):
    state: Literal["review_pending", "adjudication_ready", "adjudicated"]
    independent_reviewer_count: int
    reviews: list[EvaluationMatchReviewView]
    adjudicated_review: EvaluationMatchReviewView | None


class EvaluationArtifactReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: int = Field(ge=0, le=100)
    confidence: float = Field(default=1.0, ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=4000)


class EvaluationArtifactReviewView(EvaluationArtifactReviewCreateRequest):
    public_id: str
    stage: Literal["candidate_profile", "job_profile"]
    artifact_id: str
    reviewer_user_id: int
    reviewer_label: str
    created_at: datetime


class CandidateProfileEvaluationView(BaseModel):
    resume_profile_id: int
    resume_title: str
    resume_source: EvaluationSourceView
    candidate_profile: CandidateProfileView
    annotation_targets: list[EvaluationAnnotationTargetView]
    reviews: list[EvaluationArtifactReviewView]


class JobProfileEvaluationView(BaseModel):
    job_snapshot_id: str
    job_title: str
    job_company: str
    job_source: EvaluationSourceView
    job_profile: JobProfileView
    annotation_targets: list[EvaluationAnnotationTargetView]
    reviews: list[EvaluationArtifactReviewView]


class EvaluationAnnotationTargetView(BaseModel):
    stage: Literal["candidate_profile", "job_profile"]
    target_ref: str
    label: str
    value: Any
    evidence_refs: list[str]


class DisagreementReviewView(BaseModel):
    annotation_id: str
    reviewer_label: str
    verdict: str
    evidence_support: str
    expected_value: dict[str, Any] | None
    severity: str
    comment: str


class DisagreementQueueItemView(BaseModel):
    run_id: str
    stage: str
    target_ref: str
    status: Literal["pending", "resolved"]
    reviews: list[DisagreementReviewView]
    adjudication: DisagreementReviewView | None


class DisagreementQueueView(BaseModel):
    items: list[DisagreementQueueItemView]


class ContractMetricView(BaseModel):
    name: str
    passed: bool
    numerator: int
    denominator: int
    details: list[str] = Field(default_factory=list)


class EvaluationMetricsView(BaseModel):
    run_id: str
    contract_metrics: list[ContractMetricView]
    qualification_status_counts: dict[str, int]
    annotation_count: int
    adjudicated_count: int
    positive_evidence_support_precision: float | None
    positive_evidence_support_counts: dict[str, int]
    qualification_confusion_matrix: dict[str, dict[str, int]]


class EvaluationAggregateMetricsView(BaseModel):
    benchmark_release: str | None
    run_count: int
    contract_pass_counts: dict[str, dict[str, int]]
    qualification_status_counts: dict[str, int]
    annotation_count: int
    adjudicated_count: int
    severe_error_count: int
    positive_evidence_support_precision: float | None
    positive_evidence_support_counts: dict[str, int]


class EvaluationComparisonView(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    comparable: bool
    incompatibilities: list[str]
    manifest_differences: dict[str, dict[str, Any]]
    qualification_changes: list[dict[str, Any]]
    candidate_profile_changed: bool
    job_profile_changed: bool


class EvaluationRunManifestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: str
    benchmark_release: str
    candidate_fixture_release: str
    job_fixture_release: str
    candidate_prompt_version: str
    job_prompt_version: str
    qualification_prompt_version: str
    schema_versions: dict[str, str]
    taxonomy_version: str
    selection_policy_version: str
    qualification_policy_version: str
    model_ids: dict[str, str]
    provider_configuration_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime


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
    manifest: EvaluationRunManifestView
    annotations: list[EvaluationAnnotationView]
    match_review: EvaluationMatchReviewSummaryView
    annotation_targets: list[EvaluationAnnotationTargetView]
    metrics: EvaluationMetricsView
    run_metadata: dict[str, Any]
