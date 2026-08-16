"""add matching v2 deterministic result artifacts

Revision ID: 20260815_0046
Revises: 20260815_0045
"""

from alembic import op
import sqlalchemy as sa

revision = "20260815_0046"
down_revision = "20260815_0045"
branch_labels = None
depends_on = None


def _revision_table(name: str, *, encrypted: bool) -> None:
    columns = [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
    ]
    if encrypted:
        columns.extend([sa.Column("encrypted_artifact", sa.Text(), nullable=False), sa.Column("encryption_version", sa.String(40), nullable=False)])
    else:
        columns.append(sa.Column("artifact", sa.JSON(), nullable=False))
    columns.extend([
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "revision", name=f"uq_matching_{name}_revision"),
    ])
    table = f"matching_{name}_revisions"
    op.create_table(table, *columns)
    op.create_index(f"ix_matching_{name}_public", table, ["public_id"], unique=True)
    op.create_index(f"ix_matching_{name}_owner", table, ["workspace_id", "user_id"])


def _assessment_table(name: str, *, nullable_revision: bool) -> None:
    table = f"matching_{name}_assessments"
    revision_table = f"matching_{name}_revisions"
    revision_column = f"{name}_revision_id"
    op.create_table(
        table,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_profile_version_id", sa.Integer(), nullable=False),
        sa.Column(revision_column, sa.Integer(), nullable=nullable_revision),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("policy_hash", sa.String(71), nullable=False),
        sa.Column("artifact", sa.JSON(), nullable=False),
        sa.Column("cache_key", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_profile_version_id"], ["matching_job_profile_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint([revision_column], [f"{revision_table}.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(f"ix_matching_{name}_assessment_public", table, ["public_id"], unique=True)
    op.create_index(f"ix_matching_{name}_assessment_cache", table, ["cache_key"], unique=True)
    op.create_index(f"ix_matching_{name}_assessment_owner", table, ["workspace_id", "user_id"])


def upgrade() -> None:
    _revision_table("preference", encrypted=False)
    _revision_table("eligibility", encrypted=True)
    _assessment_table("preference", nullable_revision=False)
    _assessment_table("eligibility", nullable_revision=True)
    op.create_table(
        "matching_match_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("qualification_assessment_id", sa.Integer(), nullable=False),
        sa.Column("preference_assessment_id", sa.Integer(), nullable=True),
        sa.Column("eligibility_assessment_id", sa.Integer(), nullable=True),
        sa.Column("score_artifact", sa.JSON(), nullable=False),
        sa.Column("explanation_artifact", sa.JSON(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("legacy_score", sa.Integer(), nullable=True),
        sa.Column("cache_key", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["qualification_assessment_id"], ["matching_qualification_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["preference_assessment_id"], ["matching_preference_assessments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["eligibility_assessment_id"], ["matching_eligibility_assessments.id"], ondelete="SET NULL"),
        sa.CheckConstraint("legacy_score IS NULL OR (legacy_score >= 0 AND legacy_score <= 10)", name="ck_matching_result_legacy_score"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_result_public", "matching_match_results", ["public_id"], unique=True)
    op.create_index("ix_matching_result_cache", "matching_match_results", ["cache_key"], unique=True)
    op.create_index("ix_matching_result_owner", "matching_match_results", ["workspace_id", "user_id"])
    op.create_index("ix_matching_result_qualification", "matching_match_results", ["qualification_assessment_id"])


def downgrade() -> None:
    op.drop_table("matching_match_results")
    op.drop_table("matching_eligibility_assessments")
    op.drop_table("matching_preference_assessments")
    op.drop_table("matching_eligibility_revisions")
    op.drop_table("matching_preference_revisions")
