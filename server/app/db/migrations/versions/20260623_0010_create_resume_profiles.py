"""create resume profiles

Revision ID: 20260623_0010
Revises: 20260622_0009
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260623_0010"
down_revision = "20260622_0009"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _table_exists("resume_profiles"):
        op.create_table(
            "resume_profiles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("resume_data", sa.JSON(), nullable=False),
            sa.Column("source_document_id", sa.Integer(), nullable=True),
            sa.Column("source_document_version_id", sa.Integer(), nullable=True),
            sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_document_version_id"], ["document_versions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, columns in {
        "ix_resume_profiles_workspace_id": ["workspace_id"],
        "ix_resume_profiles_user_id": ["user_id"],
        "ix_resume_profiles_source_document_id": ["source_document_id"],
        "ix_resume_profiles_source_document_version_id": ["source_document_version_id"],
        "ix_resume_profiles_favorite_sort": ["workspace_id", "user_id", "is_favorite", "updated_at"],
    }.items():
        if not _index_exists("resume_profiles", index_name):
            op.create_index(index_name, "resume_profiles", columns, unique=False)

    if _table_exists("job_resume_matches") and not _column_exists("job_resume_matches", "resume_profile_id"):
        op.add_column("job_resume_matches", sa.Column("resume_profile_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_job_resume_matches_resume_profile_id",
            "job_resume_matches",
            "resume_profiles",
            ["resume_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if _table_exists("job_resume_matches") and not _index_exists(
        "job_resume_matches",
        "ix_job_resume_matches_resume_profile_id",
    ):
        op.create_index(
            "ix_job_resume_matches_resume_profile_id",
            "job_resume_matches",
            ["resume_profile_id"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists("job_resume_matches") and _index_exists(
        "job_resume_matches",
        "ix_job_resume_matches_resume_profile_id",
    ):
        op.drop_index("ix_job_resume_matches_resume_profile_id", table_name="job_resume_matches")
    if _table_exists("job_resume_matches") and _column_exists("job_resume_matches", "resume_profile_id"):
        op.drop_constraint("fk_job_resume_matches_resume_profile_id", "job_resume_matches", type_="foreignkey")
        op.drop_column("job_resume_matches", "resume_profile_id")
    if _table_exists("resume_profiles"):
        op.drop_index("ix_resume_profiles_favorite_sort", table_name="resume_profiles")
        op.drop_index("ix_resume_profiles_source_document_version_id", table_name="resume_profiles")
        op.drop_index("ix_resume_profiles_source_document_id", table_name="resume_profiles")
        op.drop_index("ix_resume_profiles_user_id", table_name="resume_profiles")
        op.drop_index("ix_resume_profiles_workspace_id", table_name="resume_profiles")
        op.drop_table("resume_profiles")
