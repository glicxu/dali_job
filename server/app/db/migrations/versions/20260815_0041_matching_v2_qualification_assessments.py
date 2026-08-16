"""add matching v2 qualification assessments

Revision ID: 20260815_0041
Revises: 20260815_0040
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0041"
down_revision = "20260815_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_qualification_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("owner_kind", sa.String(length=20), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_trial_id", sa.Integer(), nullable=True),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("candidate_career_selection_id", sa.Integer(), nullable=False),
        sa.Column("candidate_career_selection_revision", sa.Integer(), nullable=False),
        sa.Column("selected_candidate_career_profile_id", sa.Integer(), nullable=True),
        sa.Column("selection_reason_code", sa.String(length=80), nullable=False),
        sa.Column("job_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("response_schema_hash", sa.String(length=71), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("selection_policy_version", sa.String(length=100), nullable=False),
        sa.Column("matching_policy_version", sa.String(length=100), nullable=False),
        sa.Column("input_policy_version", sa.String(length=100), nullable=False),
        sa.Column("semantic_validator_version", sa.String(length=100), nullable=False),
        sa.Column("alternative_policy_hashes", sa.JSON(), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("provider_execution_reference", sa.String(length=255), nullable=True),
        sa.Column("artifact", sa.JSON(), nullable=False),
        sa.Column("input_quality", sa.JSON(), nullable=False),
        sa.Column("cache_key", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(owner_kind = 'authenticated' AND workspace_id IS NOT NULL AND user_id IS NOT NULL "
            "AND guest_trial_id IS NULL) OR "
            "(owner_kind = 'guest' AND workspace_id IS NULL AND user_id IS NULL "
            "AND guest_trial_id IS NOT NULL)",
            name="ck_matching_qualifications_owner",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_profile_version_id"], ["matching_candidate_profile_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_career_selection_id"], ["matching_candidate_career_selections.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selected_candidate_career_profile_id"],
            ["matching_candidate_career_profiles.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_profile_version_id"], ["matching_job_profile_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_qualifications_public", "matching_qualification_assessments", ["public_id"], unique=True)
    op.create_index("ix_matching_qualifications_candidate", "matching_qualification_assessments", ["candidate_profile_version_id"])
    op.create_index("ix_matching_qualifications_job", "matching_qualification_assessments", ["job_profile_version_id"])
    op.create_index("ix_matching_qualifications_workspace", "matching_qualification_assessments", ["workspace_id"])
    op.create_index("ix_matching_qualifications_user", "matching_qualification_assessments", ["user_id"])
    op.create_index("ix_matching_qualifications_guest", "matching_qualification_assessments", ["guest_trial_id"])
    op.create_index("ix_matching_qualifications_cache", "matching_qualification_assessments", ["cache_key"], unique=True)

    op.create_table(
        "matching_requirement_assessments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("qualification_assessment_id", sa.Integer(), nullable=False),
        sa.Column("job_requirement_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.String(length=64), nullable=False),
        sa.Column("collection_kind", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("alternative_policy_ref", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "collection_kind IN ('normal', 'hard_constraint')",
            name="ck_matching_requirement_assessments_collection",
        ),
        sa.ForeignKeyConstraint(
            ["qualification_assessment_id"], ["matching_qualification_assessments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["job_requirement_id"], ["matching_job_requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "qualification_assessment_id", "requirement_id", name="uq_matching_requirement_assessments_item"
        ),
    )
    op.create_index(
        "ix_matching_requirement_assessments_qualification",
        "matching_requirement_assessments",
        ["qualification_assessment_id"],
    )
    op.create_index(
        "ix_matching_requirement_assessments_requirement",
        "matching_requirement_assessments",
        ["job_requirement_id"],
    )
    op.create_index(
        "ix_matching_requirement_assessments_status",
        "matching_requirement_assessments",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_matching_requirement_assessments_status", table_name="matching_requirement_assessments")
    op.drop_index("ix_matching_requirement_assessments_requirement", table_name="matching_requirement_assessments")
    op.drop_index("ix_matching_requirement_assessments_qualification", table_name="matching_requirement_assessments")
    op.drop_table("matching_requirement_assessments")
    op.drop_index("ix_matching_qualifications_cache", table_name="matching_qualification_assessments")
    op.drop_index("ix_matching_qualifications_guest", table_name="matching_qualification_assessments")
    op.drop_index("ix_matching_qualifications_user", table_name="matching_qualification_assessments")
    op.drop_index("ix_matching_qualifications_workspace", table_name="matching_qualification_assessments")
    op.drop_index("ix_matching_qualifications_job", table_name="matching_qualification_assessments")
    op.drop_index("ix_matching_qualifications_candidate", table_name="matching_qualification_assessments")
    op.drop_index("ix_matching_qualifications_public", table_name="matching_qualification_assessments")
    op.drop_table("matching_qualification_assessments")
