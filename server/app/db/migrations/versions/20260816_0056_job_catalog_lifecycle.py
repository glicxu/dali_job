"""add cached job catalog lifecycle

Revision ID: 20260816_0056
Revises: 20260816_0055
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0056"
down_revision = "20260816_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs_cache",
        sa.Column("lifecycle_state", sa.String(20), nullable=False, server_default="active"),
    )
    op.add_column(
        "jobs_cache",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("jobs_cache", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs_cache", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs_cache", sa.Column("expiration_reason", sa.String(80), nullable=True))
    op.create_check_constraint(
        "ck_jobs_cache_lifecycle_state",
        "jobs_cache",
        "lifecycle_state IN ('active', 'expired', 'closed')",
    )
    op.create_index("ix_jobs_cache_lifecycle_state", "jobs_cache", ["lifecycle_state"])
    op.create_index("ix_jobs_cache_expires_at", "jobs_cache", ["expires_at"])
    op.create_index(
        "ix_jobs_cache_lifecycle_expiry",
        "jobs_cache",
        ["lifecycle_state", "expires_at"],
    )
    op.execute(
        "UPDATE jobs_cache SET last_seen_at = updated_at, "
        "expires_at = DATE_ADD(updated_at, INTERVAL 30 DAY)"
    )
    op.alter_column("jobs_cache", "lifecycle_state", server_default=None)
    op.alter_column("jobs_cache", "last_seen_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_jobs_cache_lifecycle_expiry", table_name="jobs_cache")
    op.drop_index("ix_jobs_cache_expires_at", table_name="jobs_cache")
    op.drop_index("ix_jobs_cache_lifecycle_state", table_name="jobs_cache")
    op.drop_constraint("ck_jobs_cache_lifecycle_state", "jobs_cache", type_="check")
    op.drop_column("jobs_cache", "expiration_reason")
    op.drop_column("jobs_cache", "expired_at")
    op.drop_column("jobs_cache", "expires_at")
    op.drop_column("jobs_cache", "last_seen_at")
    op.drop_column("jobs_cache", "lifecycle_state")
