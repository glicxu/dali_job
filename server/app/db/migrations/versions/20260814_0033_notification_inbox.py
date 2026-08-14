"""add notification preferences and match inbox deliveries

Revision ID: 20260814_0033
Revises: 20260814_0032
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0033"
down_revision = "20260814_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        sa.Column("digest_mode", sa.String(length=20), nullable=False),
        sa.Column("minimum_match_score", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "digest_mode IN ('immediate', 'daily')",
            name="ck_notification_preferences_digest",
        ),
        sa.CheckConstraint(
            "minimum_match_score >= 0 AND minimum_match_score <= 10",
            name="ck_notification_preferences_match_score",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_notification_preferences_user"),
    )
    op.create_index(
        "ix_notification_preferences_workspace_id", "notification_preferences", ["workspace_id"]
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_resume_match_id", sa.Integer(), nullable=False),
        sa.Column("search_schedule_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "channel IN ('email', 'in_app')", name="ck_notification_deliveries_channel"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'suppressed', 'read')",
            name="ck_notification_deliveries_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_deliveries_attempt_count"),
        sa.ForeignKeyConstraint(
            ["job_resume_match_id"], ["job_resume_matches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["search_schedule_id"], ["search_schedules.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "channel", "idempotency_key", name="uq_notification_deliveries_idempotency"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_workspace_id", "notification_deliveries", ["workspace_id"]
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index(
        "ix_notification_deliveries_job_resume_match_id",
        "notification_deliveries",
        ["job_resume_match_id"],
    )
    op.create_index(
        "ix_notification_deliveries_search_schedule_id",
        "notification_deliveries",
        ["search_schedule_id"],
    )
    op.create_index("ix_notification_deliveries_channel", "notification_deliveries", ["channel"])
    op.create_index("ix_notification_deliveries_status", "notification_deliveries", ["status"])
    op.create_index(
        "ix_notification_deliveries_next_attempt_at", "notification_deliveries", ["next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_next_attempt_at", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_status", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_channel", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_search_schedule_id", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_job_resume_match_id", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_user_id", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_workspace_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index("ix_notification_preferences_user_id", table_name="notification_preferences")
    op.drop_index("ix_notification_preferences_workspace_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")
