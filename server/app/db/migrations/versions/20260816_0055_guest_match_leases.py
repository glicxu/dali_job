"""add durable guest match leases and deadlines

Revision ID: 20260816_0055
Revises: 20260816_0054
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0055"
down_revision = "20260816_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("lease_owner", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in columns:
        op.add_column("guest_match_operations", column)
    for column in ("correlation_id", "lease_expires_at", "deadline_at", "next_retry_at"):
        op.create_index(f"ix_guest_match_operations_{column}", "guest_match_operations", [column])


def downgrade() -> None:
    for column in reversed(("correlation_id", "lease_expires_at", "deadline_at", "next_retry_at")):
        op.drop_index(f"ix_guest_match_operations_{column}", table_name="guest_match_operations")
    for column in reversed((
        "idempotency_key",
        "correlation_id",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "deadline_at",
        "next_retry_at",
    )):
        op.drop_column("guest_match_operations", column)
