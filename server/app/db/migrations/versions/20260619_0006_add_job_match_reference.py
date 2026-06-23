"""add job match reference columns

Revision ID: 20260619_0006
Revises: 20260619_0005
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260619_0006"
down_revision = "20260619_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Match metadata now lives in job_resume_matches, created in 20260622_0007.
    pass


def downgrade() -> None:
    pass
