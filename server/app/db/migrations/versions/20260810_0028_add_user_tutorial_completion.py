"""add user tutorial completion

Revision ID: 20260810_0028
Revises: 20260804_0027
Create Date: 2026-08-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260810_0028"
down_revision = "20260804_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tutorial_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing accounts should opt into replay instead of being forced through first-run onboarding.
    op.execute(
        sa.text(
            "UPDATE users SET tutorial_completed_at = CURRENT_TIMESTAMP "
            "WHERE tutorial_completed_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("users", "tutorial_completed_at")
