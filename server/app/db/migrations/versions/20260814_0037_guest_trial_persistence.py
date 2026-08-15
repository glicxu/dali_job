"""add guest trial persistence

Revision ID: 20260814_0037
Revises: 20260814_0036
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0037"
down_revision = "20260814_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guest_trials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("readiness_version", sa.String(length=64), nullable=False),
        sa.Column("provider_search_state", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_pending_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_user_id", sa.Integer(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'matching', 'result_ready', 'claim_pending', 'claimed', 'expired')",
            name="ck_guest_trials_status",
        ),
        sa.CheckConstraint(
            "provider_search_state IN ('available', 'reserved', 'consumed', 'released')",
            name="ck_guest_trials_provider_search_state",
        ),
        sa.ForeignKeyConstraint(["claimed_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_guest_trials_public_id"),
    )
    op.create_index("ix_guest_trials_public_id", "guest_trials", ["public_id"])
    op.create_index("ix_guest_trials_status", "guest_trials", ["status"])
    op.create_index("ix_guest_trials_expires_at", "guest_trials", ["expires_at"])
    op.create_index("ix_guest_trials_claimed_user_id", "guest_trials", ["claimed_user_id"])

    op.create_table(
        "guest_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=20), nullable=False),
        sa.Column("parse_suggestions", sa.JSON(), nullable=True),
        sa.Column("parser_provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'succeeded', 'failed')",
            name="ck_guest_documents_parse_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_trial_id", name="uq_guest_documents_trial"),
    )
    op.create_index("ix_guest_documents_guest_trial_id", "guest_documents", ["guest_trial_id"])

    op.create_table(
        "guest_resume_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("source_guest_document_id", sa.Integer(), nullable=True),
        sa.Column("resume_data", sa.JSON(), nullable=False),
        sa.Column("readiness_pathway", sa.String(length=32), nullable=False),
        sa.Column("evidence_summary", sa.JSON(), nullable=False),
        sa.Column("parser_provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_guest_document_id"], ["guest_documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_trial_id", name="uq_guest_resume_profiles_trial"),
    )
    op.create_index("ix_guest_resume_profiles_guest_trial_id", "guest_resume_profiles", ["guest_trial_id"])
    op.create_index(
        "ix_guest_resume_profiles_source_guest_document_id",
        "guest_resume_profiles",
        ["source_guest_document_id"],
    )

    op.create_table(
        "guest_search_criteria",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_trial_id", name="uq_guest_search_criteria_trial"),
    )
    op.create_index("ix_guest_search_criteria_guest_trial_id", "guest_search_criteria", ["guest_trial_id"])

    op.create_table(
        "guest_match_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'searching', 'matching', 'result_ready', 'failed')",
            name="ck_guest_match_operations_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_guest_match_operations_attempt_count"),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_trial_id", name="uq_guest_match_operations_trial"),
    )
    op.create_index("ix_guest_match_operations_guest_trial_id", "guest_match_operations", ["guest_trial_id"])
    op.create_index("ix_guest_match_operations_status", "guest_match_operations", ["status"])

    op.create_table(
        "guest_provider_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("provider_feature", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("safe_outcome", sa.String(length=80), nullable=True),
        sa.Column("failure_category", sa.String(length=80), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('reserved', 'consumed', 'released')",
            name="ck_guest_provider_attempts_state",
        ),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "guest_trial_id", "idempotency_key", name="uq_guest_provider_attempts_trial_key"
        ),
    )
    op.create_index("ix_guest_provider_attempts_guest_trial_id", "guest_provider_attempts", ["guest_trial_id"])
    op.create_index("ix_guest_provider_attempts_state", "guest_provider_attempts", ["state"])

    op.create_table(
        "guest_match_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("provider_rank", sa.Integer(), nullable=False),
        sa.Column("job_snapshot", sa.JSON(), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("match_data", sa.JSON(), nullable=True),
        sa.Column("matcher_provenance", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider_rank >= 1", name="ck_guest_match_candidates_rank"),
        sa.CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 10)",
            name="ck_guest_match_candidates_score",
        ),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["guest_match_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id", "provider_rank", name="uq_guest_match_candidates_operation_rank"
        ),
    )
    op.create_index("ix_guest_match_candidates_guest_trial_id", "guest_match_candidates", ["guest_trial_id"])
    op.create_index("ix_guest_match_candidates_operation_id", "guest_match_candidates", ["operation_id"])

    op.create_table(
        "guest_match_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_trial_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("job_snapshot", sa.JSON(), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("match_data", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "match_score >= 0 AND match_score <= 10", name="ck_guest_match_results_score"
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["guest_match_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["guest_trial_id"], ["guest_trials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["guest_match_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_trial_id", name="uq_guest_match_results_trial"),
    )
    op.create_index("ix_guest_match_results_guest_trial_id", "guest_match_results", ["guest_trial_id"])


def downgrade() -> None:
    op.drop_index("ix_guest_match_results_guest_trial_id", table_name="guest_match_results")
    op.drop_table("guest_match_results")
    op.drop_index("ix_guest_match_candidates_operation_id", table_name="guest_match_candidates")
    op.drop_index("ix_guest_match_candidates_guest_trial_id", table_name="guest_match_candidates")
    op.drop_table("guest_match_candidates")
    op.drop_index("ix_guest_provider_attempts_state", table_name="guest_provider_attempts")
    op.drop_index("ix_guest_provider_attempts_guest_trial_id", table_name="guest_provider_attempts")
    op.drop_table("guest_provider_attempts")
    op.drop_index("ix_guest_match_operations_status", table_name="guest_match_operations")
    op.drop_index("ix_guest_match_operations_guest_trial_id", table_name="guest_match_operations")
    op.drop_table("guest_match_operations")
    op.drop_index("ix_guest_search_criteria_guest_trial_id", table_name="guest_search_criteria")
    op.drop_table("guest_search_criteria")
    op.drop_index("ix_guest_resume_profiles_source_guest_document_id", table_name="guest_resume_profiles")
    op.drop_index("ix_guest_resume_profiles_guest_trial_id", table_name="guest_resume_profiles")
    op.drop_table("guest_resume_profiles")
    op.drop_index("ix_guest_documents_guest_trial_id", table_name="guest_documents")
    op.drop_table("guest_documents")
    op.drop_index("ix_guest_trials_claimed_user_id", table_name="guest_trials")
    op.drop_index("ix_guest_trials_expires_at", table_name="guest_trials")
    op.drop_index("ix_guest_trials_status", table_name="guest_trials")
    op.drop_index("ix_guest_trials_public_id", table_name="guest_trials")
    op.drop_table("guest_trials")
