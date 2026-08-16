"""add matching v2 job profile artifacts

Revision ID: 20260815_0040
Revises: 20260815_0039
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0040"
down_revision = "20260815_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_job_profile_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_source_id", sa.Integer(), nullable=False),
        sa.Column("jobs_cache_id", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("response_schema_hash", sa.String(length=71), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=100), nullable=False),
        sa.Column("source_policy_version", sa.String(length=100), nullable=False),
        sa.Column("deduplication_version", sa.String(length=100), nullable=False),
        sa.Column("semantic_validator_version", sa.String(length=100), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("provider_execution_reference", sa.String(length=255), nullable=True),
        sa.Column("artifact", sa.JSON(), nullable=False),
        sa.Column("cleanup", sa.JSON(), nullable=False),
        sa.Column("cache_key", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["canonical_source_id"], ["matching_canonical_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["jobs_cache_id"], ["jobs_cache.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_job_versions_public", "matching_job_profile_versions", ["public_id"], unique=True)
    op.create_index("ix_matching_job_versions_source", "matching_job_profile_versions", ["canonical_source_id"])
    op.create_index("ix_matching_job_versions_cache_job", "matching_job_profile_versions", ["jobs_cache_id"])
    op.create_index("ix_matching_job_versions_cache", "matching_job_profile_versions", ["cache_key"], unique=True)

    op.create_table(
        "matching_job_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.String(length=64), nullable=False),
        sa.Column("local_ref", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("scoring_dimension", sa.String(length=60), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("importance", sa.String(length=30), nullable=False),
        sa.Column("hard_constraint", sa.Boolean(), nullable=False),
        sa.Column("acceptable_evidence_contexts", sa.JSON(), nullable=False),
        sa.Column("minimum_years", sa.Float(), nullable=True),
        sa.Column("explicit_alternatives", sa.JSON(), nullable=False),
        sa.Column("policy_alternative_group", sa.String(length=120), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_profile_version_id"], ["matching_job_profile_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_profile_version_id", "requirement_id", name="uq_matching_job_requirements_id"),
        sa.UniqueConstraint("job_profile_version_id", "local_ref", name="uq_matching_job_requirements_ref"),
    )
    op.create_index("ix_matching_job_requirements_version", "matching_job_requirements", ["job_profile_version_id"])
    op.create_index("ix_matching_job_requirements_id", "matching_job_requirements", ["requirement_id"])
    op.create_index("ix_matching_job_requirements_dimension", "matching_job_requirements", ["scoring_dimension"])


def downgrade() -> None:
    op.drop_index("ix_matching_job_requirements_dimension", table_name="matching_job_requirements")
    op.drop_index("ix_matching_job_requirements_id", table_name="matching_job_requirements")
    op.drop_index("ix_matching_job_requirements_version", table_name="matching_job_requirements")
    op.drop_table("matching_job_requirements")
    op.drop_index("ix_matching_job_versions_cache", table_name="matching_job_profile_versions")
    op.drop_index("ix_matching_job_versions_cache_job", table_name="matching_job_profile_versions")
    op.drop_index("ix_matching_job_versions_source", table_name="matching_job_profile_versions")
    op.drop_index("ix_matching_job_versions_public", table_name="matching_job_profile_versions")
    op.drop_table("matching_job_profile_versions")
