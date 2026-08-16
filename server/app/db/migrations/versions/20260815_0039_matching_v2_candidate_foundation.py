"""add matching v2 candidate artifact foundation

Revision ID: 20260815_0039
Revises: 20260815_0038
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0039"
down_revision = "20260815_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_canonical_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("owner_kind", sa.String(length=20), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("guest_trial_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("resume_profile_id", sa.Integer(), nullable=True),
        sa.Column("guest_resume_profile_id", sa.Integer(), nullable=True),
        sa.Column("document_version_id", sa.Integer(), nullable=True),
        sa.Column("source_hash", sa.String(length=71), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("text_extraction_version", sa.String(length=100), nullable=False),
        sa.Column("ocr_version", sa.String(length=100), nullable=True),
        sa.Column("canonicalization_version", sa.String(length=100), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("cache_key", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(owner_kind = 'authenticated' AND workspace_id IS NOT NULL AND user_id IS NOT NULL "
            "AND guest_trial_id IS NULL) OR "
            "(owner_kind = 'guest' AND workspace_id IS NULL AND user_id IS NULL "
            "AND guest_trial_id IS NOT NULL) OR "
            "(owner_kind = 'shared' AND workspace_id IS NULL AND user_id IS NULL "
            "AND guest_trial_id IS NULL)",
            name="ck_matching_sources_owner",
        ),
        sa.CheckConstraint("source_type IN ('resume', 'job')", name="ck_matching_sources_type"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["guest_resume_profile_id"], ["guest_resume_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_sources_public_id", "matching_canonical_sources", ["public_id"], unique=True)
    op.create_index("ix_matching_sources_workspace", "matching_canonical_sources", ["workspace_id"])
    op.create_index("ix_matching_sources_user", "matching_canonical_sources", ["user_id"])
    op.create_index("ix_matching_sources_guest", "matching_canonical_sources", ["guest_trial_id"])
    op.create_index("ix_matching_sources_resume", "matching_canonical_sources", ["resume_profile_id"])
    op.create_index("ix_matching_sources_guest_resume", "matching_canonical_sources", ["guest_resume_profile_id"])
    op.create_index("ix_matching_sources_document_version", "matching_canonical_sources", ["document_version_id"])
    op.create_index("ix_matching_sources_hash", "matching_canonical_sources", ["source_hash"])
    op.create_index("ix_matching_sources_cache_key", "matching_canonical_sources", ["cache_key"], unique=True)

    op.create_table(
        "matching_source_spans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_source_id", sa.Integer(), nullable=False),
        sa.Column("span_id", sa.String(length=180), nullable=False),
        sa.Column("section", sa.String(length=100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_utf8_byte", sa.Integer(), nullable=False),
        sa.Column("end_utf8_byte", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("start_utf8_byte >= 0", name="ck_matching_spans_start_nonnegative"),
        sa.CheckConstraint("end_utf8_byte > start_utf8_byte", name="ck_matching_spans_valid_range"),
        sa.ForeignKeyConstraint(["canonical_source_id"], ["matching_canonical_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_source_id", "span_id", name="uq_matching_source_spans_source_span"),
    )
    op.create_index("ix_matching_spans_source", "matching_source_spans", ["canonical_source_id"])
    op.create_index("ix_matching_spans_span_id", "matching_source_spans", ["span_id"])

    op.create_table(
        "matching_candidate_profile_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_source_id", sa.Integer(), nullable=False),
        sa.Column("resume_profile_id", sa.Integer(), nullable=True),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("response_schema_hash", sa.String(length=71), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=100), nullable=False),
        sa.Column("semantic_validator_version", sa.String(length=100), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("provider_execution_reference", sa.String(length=255), nullable=True),
        sa.Column("artifact", sa.JSON(), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=False),
        sa.Column("recommended_primary_career_profile_ref", sa.String(length=100), nullable=False),
        sa.Column("cache_key", sa.String(length=71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["canonical_source_id"], ["matching_canonical_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_candidate_versions_public", "matching_candidate_profile_versions", ["public_id"], unique=True)
    op.create_index("ix_matching_candidate_versions_source", "matching_candidate_profile_versions", ["canonical_source_id"])
    op.create_index("ix_matching_candidate_versions_resume", "matching_candidate_profile_versions", ["resume_profile_id"])
    op.create_index("ix_matching_candidate_versions_cache", "matching_candidate_profile_versions", ["cache_key"], unique=True)

    op.create_table(
        "matching_candidate_career_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("career_profile_id", sa.String(length=64), nullable=False),
        sa.Column("local_ref", sa.String(length=100), nullable=False),
        sa.Column("role_family", sa.String(length=100), nullable=False),
        sa.Column("track", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("dimension_signals", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_profile_version_id"],
            ["matching_candidate_profile_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_profile_version_id",
            "career_profile_id",
            name="uq_matching_career_profiles_durable_id",
        ),
        sa.UniqueConstraint(
            "candidate_profile_version_id",
            "local_ref",
            name="uq_matching_career_profiles_local_ref",
        ),
    )
    op.create_index("ix_matching_career_profiles_version", "matching_candidate_career_profiles", ["candidate_profile_version_id"])
    op.create_index("ix_matching_career_profiles_id", "matching_candidate_career_profiles", ["career_profile_id"])
    op.create_index("ix_matching_career_profiles_role", "matching_candidate_career_profiles", ["role_family"])
    op.create_index("ix_matching_career_profiles_track", "matching_candidate_career_profiles", ["track"])

    op.create_table(
        "matching_candidate_career_selections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("candidate_career_profile_id", sa.Integer(), nullable=True),
        sa.Column("selection_source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "selection_source IN ('model_default', 'user_confirmed', 'operator_corrected')",
            name="ck_matching_career_selections_source",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_career_profile_id"],
            ["matching_candidate_career_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_profile_version_id"],
            ["matching_candidate_profile_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_profile_version_id",
            "revision",
            name="uq_matching_career_selections_revision",
        ),
    )
    op.create_index("ix_matching_career_selections_version", "matching_candidate_career_selections", ["candidate_profile_version_id"])
    op.create_index("ix_matching_career_selections_profile", "matching_candidate_career_selections", ["candidate_career_profile_id"])

    op.create_table(
        "matching_policy_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("artifact_type", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=120), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_type", "version", name="uq_matching_policy_registry_type_version"),
    )
    op.create_index("ix_matching_policy_registry_type", "matching_policy_registry", ["artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_matching_policy_registry_type", table_name="matching_policy_registry")
    op.drop_table("matching_policy_registry")
    op.drop_index("ix_matching_career_selections_profile", table_name="matching_candidate_career_selections")
    op.drop_index("ix_matching_career_selections_version", table_name="matching_candidate_career_selections")
    op.drop_table("matching_candidate_career_selections")
    op.drop_index("ix_matching_career_profiles_track", table_name="matching_candidate_career_profiles")
    op.drop_index("ix_matching_career_profiles_role", table_name="matching_candidate_career_profiles")
    op.drop_index("ix_matching_career_profiles_id", table_name="matching_candidate_career_profiles")
    op.drop_index("ix_matching_career_profiles_version", table_name="matching_candidate_career_profiles")
    op.drop_table("matching_candidate_career_profiles")
    op.drop_index("ix_matching_candidate_versions_cache", table_name="matching_candidate_profile_versions")
    op.drop_index("ix_matching_candidate_versions_resume", table_name="matching_candidate_profile_versions")
    op.drop_index("ix_matching_candidate_versions_source", table_name="matching_candidate_profile_versions")
    op.drop_index("ix_matching_candidate_versions_public", table_name="matching_candidate_profile_versions")
    op.drop_table("matching_candidate_profile_versions")
    op.drop_index("ix_matching_spans_span_id", table_name="matching_source_spans")
    op.drop_index("ix_matching_spans_source", table_name="matching_source_spans")
    op.drop_table("matching_source_spans")
    op.drop_index("ix_matching_sources_cache_key", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_hash", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_document_version", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_guest_resume", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_resume", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_guest", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_user", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_workspace", table_name="matching_canonical_sources")
    op.drop_index("ix_matching_sources_public_id", table_name="matching_canonical_sources")
    op.drop_table("matching_canonical_sources")
