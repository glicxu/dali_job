from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsStatusCount(BaseModel):
    status: str
    count: int


class AnalyticsPeriodCount(BaseModel):
    period: str
    count: int


class AnalyticsRate(BaseModel):
    outcome: str
    numerator: int
    denominator: int
    percentage: float | None = None


class AnalyticsDuration(BaseModel):
    metric: str
    sample_size: int
    average_hours: float | None = None
    median_hours: float | None = None


class AnalyticsPerformanceGroup(BaseModel):
    key: str
    label: str
    sample_size: int
    response_rate: float | None = None
    interview_rate: float | None = None
    offer_rate: float | None = None
    rejection_rate: float | None = None
    withdrawal_rate: float | None = None
    small_sample: bool


class AnalyticsDefinition(BaseModel):
    metric: str
    definition: str
    denominator: str


class AnalyticsDataQuality(BaseModel):
    missing_applied_at: int = 0
    missing_source_snapshot: int = 0
    missing_resume_version: int = 0
    resume_attached_after_applied: int = 0
    events_before_applied: int = 0
    warnings: list[str] = Field(default_factory=list)


class AnalyticsSummaryResponse(BaseModel):
    metric_version: str
    timezone: str
    range_start: datetime | None = None
    range_end_exclusive: datetime | None = None
    generated_at: datetime
    application_count: int
    submitted_application_count: int
    status_counts: list[AnalyticsStatusCount]
    application_trend: list[AnalyticsPeriodCount]
    rates: list[AnalyticsRate]
    durations: list[AnalyticsDuration]
    source_performance: list[AnalyticsPerformanceGroup]
    resume_version_performance: list[AnalyticsPerformanceGroup]
    definitions: list[AnalyticsDefinition]
    data_quality: AnalyticsDataQuality
