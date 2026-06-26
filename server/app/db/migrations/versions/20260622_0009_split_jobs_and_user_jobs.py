"""split canonical jobs from user saved jobs

Revision ID: 20260622_0009
Revises: 20260622_0008
Create Date: 2026-06-22
"""

revision = "20260622_0009"
down_revision = "20260622_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # jobs_cache and user_saved_jobs are created in their final shape by 20260619_0004.
    pass


def downgrade() -> None:
    pass
