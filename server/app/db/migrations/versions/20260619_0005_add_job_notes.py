"""add job notes

Revision ID: 20260619_0005
Revises: 20260619_0004
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260619_0005"
down_revision = "20260619_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Notes now live on user_jobs, created in 20260619_0004.
    pass


def downgrade() -> None:
    pass
