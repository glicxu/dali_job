"""add mobile automation subscriptions, usage, schedules, and runs

Revision ID: 20260814_0032
Revises: 20260814_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0032"
down_revision = "20260814_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tier_code", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("entitlement_version", sa.String(length=64), nullable=False),
        sa.Column("period_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_customer_reference", sa.String(length=255), nullable=True),
        sa.Column("external_subscription_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("tier_code IN ('free', 'starter', 'plus')", name="ck_user_subscriptions_tier"),
        sa.CheckConstraint(
            "status IN ('active', 'past_due', 'cancelled', 'expired')",
            name="ck_user_subscriptions_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_subscriptions_user"),
    )
    op.create_index("ix_user_subscriptions_workspace_id", "user_subscriptions", ["workspace_id"])
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
    op.create_index("ix_user_subscriptions_tier_code", "user_subscriptions", ["tier_code"])
    op.create_index("ix_user_subscriptions_status", "user_subscriptions", ["status"])
    op.create_index("ix_user_subscriptions_period_ends_at", "user_subscriptions", ["period_ends_at"])

    op.create_table(
        "search_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("criterion_id", sa.Integer(), nullable=False),
        sa.Column("resume_profile_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("minimum_match_score", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False),
        sa.Column("paused_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("interval_minutes >= 1", name="ck_search_schedules_interval"),
        sa.CheckConstraint(
            "minimum_match_score >= 0 AND minimum_match_score <= 10",
            name="ck_search_schedules_match_score",
        ),
        sa.ForeignKeyConstraint(["criterion_id"], ["job_search_criteria.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("criterion_id", name="uq_search_schedules_criterion"),
    )
    op.create_index("ix_search_schedules_workspace_id", "search_schedules", ["workspace_id"])
    op.create_index("ix_search_schedules_user_id", "search_schedules", ["user_id"])
    op.create_index("ix_search_schedules_resume_profile_id", "search_schedules", ["resume_profile_id"])
    op.create_index("ix_search_schedules_enabled", "search_schedules", ["enabled"])
    op.create_index("ix_search_schedules_next_run_at", "search_schedules", ["next_run_at"])

    op.create_table(
        "search_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("managed_operation_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("jobs_discovered", sa.Integer(), nullable=False),
        sa.Column("jobs_new", sa.Integer(), nullable=False),
        sa.Column("jobs_matched", sa.Integer(), nullable=False),
        sa.Column("matches_notified", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_search_runs_status",
        ),
        sa.CheckConstraint("jobs_discovered >= 0", name="ck_search_runs_jobs_discovered"),
        sa.CheckConstraint("jobs_new >= 0", name="ck_search_runs_jobs_new"),
        sa.CheckConstraint("jobs_matched >= 0", name="ck_search_runs_jobs_matched"),
        sa.CheckConstraint("matches_notified >= 0", name="ck_search_runs_matches_notified"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_search_runs_attempt_count"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_search_runs_max_attempts"),
        sa.ForeignKeyConstraint(["managed_operation_id"], ["managed_operations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["schedule_id"], ["search_schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("managed_operation_id", name="uq_search_runs_managed_operation"),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_search_runs_occurrence"),
    )
    op.create_index("ix_search_runs_workspace_id", "search_runs", ["workspace_id"])
    op.create_index("ix_search_runs_user_id", "search_runs", ["user_id"])
    op.create_index("ix_search_runs_schedule_id", "search_runs", ["schedule_id"])
    op.create_index("ix_search_runs_status", "search_runs", ["status"])
    op.create_index("ix_search_runs_lease_owner", "search_runs", ["lease_owner"])
    op.create_index("ix_search_runs_lease_expires_at", "search_runs", ["lease_expires_at"])
    op.create_index("ix_search_runs_scheduled_for", "search_runs", ["scheduled_for"])

    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("search_run_id", sa.Integer(), nullable=True),
        sa.Column("usage_type", sa.String(length=40), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("entitlement_version", sa.String(length=64), nullable=False),
        sa.Column("tier_code_snapshot", sa.String(length=20), nullable=False),
        sa.Column("allowance_snapshot", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("usage_type IN ('provider_search')", name="ck_usage_ledger_type"),
        sa.CheckConstraint("state IN ('reserved', 'consumed', 'released')", name="ck_usage_ledger_state"),
        sa.CheckConstraint("units > 0", name="ck_usage_ledger_units"),
        sa.ForeignKeyConstraint(["search_run_id"], ["search_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["user_subscriptions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("search_run_id", name="uq_usage_ledger_search_run"),
        sa.UniqueConstraint(
            "user_id",
            "usage_type",
            "idempotency_key",
            name="uq_usage_ledger_owner_idempotency",
        ),
    )
    op.create_index("ix_usage_ledger_workspace_id", "usage_ledger", ["workspace_id"])
    op.create_index("ix_usage_ledger_user_id", "usage_ledger", ["user_id"])
    op.create_index("ix_usage_ledger_subscription_id", "usage_ledger", ["subscription_id"])
    op.create_index("ix_usage_ledger_usage_type", "usage_ledger", ["usage_type"])
    op.create_index("ix_usage_ledger_state", "usage_ledger", ["state"])
    op.create_index("ix_usage_ledger_reserved_at", "usage_ledger", ["reserved_at"])

    # Existing users receive a fail-closed Free subscription. The entitlement
    # service advances the zero-length initial period before allowing usage.
    op.execute(
        sa.text(
            """
            INSERT INTO user_subscriptions (
                workspace_id, user_id, tier_code, status, entitlement_version,
                period_started_at, period_ends_at, created_at, updated_at
            )
            SELECT MIN(w.id), u.id, 'free', 'active', 'weekly-searches-v1-2026-08-14',
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM users u
            JOIN workspaces w ON w.owner_user_id = u.id
            WHERE u.deleted_at IS NULL AND w.deleted_at IS NULL
            GROUP BY u.id
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_reserved_at", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_state", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_usage_type", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_subscription_id", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_user_id", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_workspace_id", table_name="usage_ledger")
    op.drop_table("usage_ledger")

    op.drop_index("ix_search_runs_scheduled_for", table_name="search_runs")
    op.drop_index("ix_search_runs_lease_expires_at", table_name="search_runs")
    op.drop_index("ix_search_runs_lease_owner", table_name="search_runs")
    op.drop_index("ix_search_runs_status", table_name="search_runs")
    op.drop_index("ix_search_runs_schedule_id", table_name="search_runs")
    op.drop_index("ix_search_runs_user_id", table_name="search_runs")
    op.drop_index("ix_search_runs_workspace_id", table_name="search_runs")
    op.drop_table("search_runs")

    op.drop_index("ix_search_schedules_next_run_at", table_name="search_schedules")
    op.drop_index("ix_search_schedules_enabled", table_name="search_schedules")
    op.drop_index("ix_search_schedules_resume_profile_id", table_name="search_schedules")
    op.drop_index("ix_search_schedules_user_id", table_name="search_schedules")
    op.drop_index("ix_search_schedules_workspace_id", table_name="search_schedules")
    op.drop_table("search_schedules")

    op.drop_index("ix_user_subscriptions_period_ends_at", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_status", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_tier_code", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_user_id", table_name="user_subscriptions")
    op.drop_index("ix_user_subscriptions_workspace_id", table_name="user_subscriptions")
    op.drop_table("user_subscriptions")
