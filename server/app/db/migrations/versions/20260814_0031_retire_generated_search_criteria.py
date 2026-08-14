"""retire automatically generated resume search criteria

Revision ID: 20260814_0031
Revises: 20260814_0030
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0031"
down_revision = "20260814_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    criteria = sa.table(
        "job_search_criteria",
        sa.column("source", sa.String(length=32)),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        criteria.update()
        .where(criteria.c.source == "resume_generated")
        .where(criteria.c.deleted_at.is_(None))
        .values(deleted_at=sa.func.current_timestamp())
    )


def downgrade() -> None:
    # Retired generated searches are intentionally not restored. A downgrade
    # cannot distinguish this cleanup from rows users had already deleted.
    pass
