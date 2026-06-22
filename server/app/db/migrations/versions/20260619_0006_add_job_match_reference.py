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
    op.add_column("jobs", sa.Column("match_score", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("matched_resume_document_id", sa.String(length=36), nullable=True))
    op.add_column("jobs", sa.Column("matched_resume_source", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_jobs_matched_resume_document_id_documents",
        "jobs",
        "documents",
        ["matched_resume_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_matched_resume_document_id", "jobs", ["matched_resume_document_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_jobs_matched_resume_document_id", table_name="jobs")
    op.drop_constraint("fk_jobs_matched_resume_document_id_documents", "jobs", type_="foreignkey")
    op.drop_column("jobs", "matched_resume_source")
    op.drop_column("jobs", "matched_resume_document_id")
    op.drop_column("jobs", "match_score")
