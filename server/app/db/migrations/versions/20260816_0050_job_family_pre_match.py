"""add matching intents and deterministic job family pre-match

Revision ID: 20260816_0050
Revises: 20260816_0049
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0050"
down_revision = "20260816_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_intents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("target_role_text", sa.String(300), nullable=False),
        sa.Column("job_family", sa.String(100), nullable=False),
        sa.Column("track", sa.String(100), nullable=False),
        sa.Column("target_level", sa.String(40), nullable=True),
        sa.Column("selected_candidate_career_profile_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('user_preferred', 'user_confirmed', 'resume_derived')",
            name="ck_matching_intents_source",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_profile_version_id"], ["matching_candidate_profile_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selected_candidate_career_profile_id"], ["matching_candidate_career_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", "public_id", "revision", name="uq_matching_intents_revision"),
    )
    op.create_index("ix_matching_intents_public", "matching_intents", ["public_id"])
    op.create_index("ix_matching_intents_owner", "matching_intents", ["workspace_id", "user_id"])
    op.create_index("ix_matching_intents_candidate", "matching_intents", ["candidate_profile_version_id"])

    op.create_table(
        "matching_job_family_pre_matches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("matching_intent_id", sa.Integer(), nullable=False),
        sa.Column("matching_intent_revision", sa.Integer(), nullable=False),
        sa.Column("job_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("selected_candidate_career_profile_id", sa.Integer(), nullable=True),
        sa.Column("selection_source", sa.String(30), nullable=False),
        sa.Column("family_compatibility", sa.String(30), nullable=False),
        sa.Column("track_compatibility", sa.String(30), nullable=False),
        sa.Column("level_compatibility", sa.String(30), nullable=False),
        sa.Column("proceed_to_detailed_match", sa.Boolean(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("policy_hash", sa.String(71), nullable=False),
        sa.Column("cache_key", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_profile_version_id"], ["matching_candidate_profile_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["matching_intent_id"], ["matching_intents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["job_profile_version_id"], ["matching_job_profile_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["selected_candidate_career_profile_id"], ["matching_candidate_career_profiles.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_job_family_pre_matches_public", "matching_job_family_pre_matches", ["public_id"], unique=True)
    op.create_index("ix_matching_job_family_pre_matches_owner", "matching_job_family_pre_matches", ["workspace_id", "user_id"])
    op.create_index("ix_matching_job_family_pre_matches_cache", "matching_job_family_pre_matches", ["cache_key"], unique=True)

    with op.batch_alter_table("matching_qualification_assessments") as batch:
        batch.alter_column("candidate_career_selection_id", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("candidate_career_selection_revision", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("job_family_pre_match_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_matching_qualifications_pre_match",
            "matching_job_family_pre_matches",
            ["job_family_pre_match_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_matching_qualifications_pre_match", ["job_family_pre_match_id"])


def downgrade() -> None:
    with op.batch_alter_table("matching_qualification_assessments") as batch:
        batch.drop_index("ix_matching_qualifications_pre_match")
        batch.drop_constraint("fk_matching_qualifications_pre_match", type_="foreignkey")
        batch.drop_column("job_family_pre_match_id")
        batch.alter_column("candidate_career_selection_revision", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("candidate_career_selection_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_matching_job_family_pre_matches_cache", table_name="matching_job_family_pre_matches")
    op.drop_index("ix_matching_job_family_pre_matches_owner", table_name="matching_job_family_pre_matches")
    op.drop_index("ix_matching_job_family_pre_matches_public", table_name="matching_job_family_pre_matches")
    op.drop_table("matching_job_family_pre_matches")
    op.drop_index("ix_matching_intents_candidate", table_name="matching_intents")
    op.drop_index("ix_matching_intents_owner", table_name="matching_intents")
    op.drop_index("ix_matching_intents_public", table_name="matching_intents")
    op.drop_table("matching_intents")
