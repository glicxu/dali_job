"""add immutable application source snapshots

Revision ID: 20260715_0023
Revises: 20260715_0022
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0023"
down_revision = "20260715_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("source_url_snapshot", sa.String(length=2048), nullable=True))
    op.add_column("applications", sa.Column("source_label_snapshot", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_applications_source_label_snapshot",
        "applications",
        ["source_label_snapshot"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_applications_source_label_snapshot", table_name="applications")
    op.drop_column("applications", "source_label_snapshot")
    op.drop_column("applications", "source_url_snapshot")
