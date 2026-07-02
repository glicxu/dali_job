"""make jobs_cache job_data nullable for lazy parsing

Revision ID: 20260630_0013
Revises: 20260626_0012
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa

revision = "20260630_0013"
down_revision = "20260626_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "jobs_cache",
        "job_data",
        existing_type=sa.JSON(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE jobs_cache SET job_data = JSON_OBJECT() WHERE job_data IS NULL")
    op.alter_column(
        "jobs_cache",
        "job_data",
        existing_type=sa.JSON(),
        nullable=False,
    )
