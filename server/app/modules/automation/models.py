from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        CheckConstraint("tier_code IN ('free', 'starter', 'plus')", name="ck_user_subscriptions_tier"),
        CheckConstraint(
            "status IN ('active', 'past_due', 'cancelled', 'expired')",
            name="ck_user_subscriptions_status",
        ),
        UniqueConstraint("user_id", name="uq_user_subscriptions_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tier_code: Mapped[str] = mapped_column(String(20), nullable=False, default="free", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    entitlement_version: Mapped[str] = mapped_column(String(64), nullable=False)
    period_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    external_customer_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_subscription_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SearchSchedule(Base):
    __tablename__ = "search_schedules"
    __table_args__ = (
        CheckConstraint("interval_minutes >= 1", name="ck_search_schedules_interval"),
        CheckConstraint(
            "minimum_match_score >= 0 AND minimum_match_score <= 10",
            name="ck_search_schedules_match_score",
        ),
        UniqueConstraint("criterion_id", name="uq_search_schedules_criterion"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("job_search_criteria.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("resume_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paused_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SearchRun(Base):
    __tablename__ = "search_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_search_runs_status",
        ),
        CheckConstraint("jobs_discovered >= 0", name="ck_search_runs_jobs_discovered"),
        CheckConstraint("jobs_new >= 0", name="ck_search_runs_jobs_new"),
        CheckConstraint("jobs_matched >= 0", name="ck_search_runs_jobs_matched"),
        CheckConstraint("matches_notified >= 0", name="ck_search_runs_matches_notified"),
        CheckConstraint("attempt_count >= 0", name="ck_search_runs_attempt_count"),
        CheckConstraint("max_attempts >= 1", name="ck_search_runs_max_attempts"),
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_search_runs_occurrence"),
        UniqueConstraint("managed_operation_id", name="uq_search_runs_managed_operation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("search_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    managed_operation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("managed_operations.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    jobs_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_notified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        CheckConstraint("usage_type IN ('provider_search')", name="ck_usage_ledger_type"),
        CheckConstraint("state IN ('reserved', 'consumed', 'released')", name="ck_usage_ledger_state"),
        CheckConstraint("units > 0", name="ck_usage_ledger_units"),
        UniqueConstraint(
            "user_id",
            "usage_type",
            "idempotency_key",
            name="uq_usage_ledger_owner_idempotency",
        ),
        UniqueConstraint("search_run_id", name="uq_usage_ledger_search_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    search_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("search_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    usage_type: Mapped[str] = mapped_column(String(40), nullable=False, default="provider_search", index=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    entitlement_version: Mapped[str] = mapped_column(String(64), nullable=False)
    tier_code_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    allowance_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        CheckConstraint("digest_mode IN ('immediate', 'daily')", name="ck_notification_preferences_digest"),
        CheckConstraint(
            "minimum_match_score >= 0 AND minimum_match_score <= 10",
            name="ck_notification_preferences_match_score",
        ),
        UniqueConstraint("user_id", name="uq_notification_preferences_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    digest_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")
    minimum_match_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    quiet_hours_start: Mapped[time | None] = mapped_column(Time(), nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'in_app')", name="ck_notification_deliveries_channel"),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'suppressed', 'read')",
            name="ck_notification_deliveries_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_notification_deliveries_attempt_count"),
        UniqueConstraint(
            "user_id", "channel", "idempotency_key", name="uq_notification_deliveries_idempotency"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_resume_match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_resume_matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    search_schedule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("search_schedules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
