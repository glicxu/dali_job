"""harden application lifecycle and duplicate handling

Revision ID: 20260714_0019
Revises: 20260714_0018
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0019"
down_revision = "20260714_0018"
branch_labels = None
depends_on = None

ACTIVE_STATUSES = ("interested", "applied", "interviewing", "offer")


def upgrade() -> None:
    op.add_column("applications", sa.Column("stage", sa.String(length=40), nullable=True))
    op.add_column("applications", sa.Column("active_duplicate_guard", sa.Integer(), nullable=True))
    op.create_index("ix_applications_stage", "applications", ["stage"], unique=False)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE applications "
            "SET archived_at = COALESCE(archived_at, updated_at), status = 'withdrawn' "
            "WHERE status = 'archived'"
        )
    )
    rows = connection.execute(
        sa.text(
            "SELECT id, workspace_id, user_id, user_job_id, status, archived_at "
            "FROM applications ORDER BY id"
        )
    ).mappings()
    claimed: set[tuple[int, int, int]] = set()
    for row in rows:
        guard = None
        if row["user_job_id"] is not None and row["archived_at"] is None and row["status"] in ACTIVE_STATUSES:
            key = (row["workspace_id"], row["user_id"], row["user_job_id"])
            if key not in claimed:
                claimed.add(key)
                guard = 1
        connection.execute(
            sa.text("UPDATE applications SET active_duplicate_guard = :guard WHERE id = :application_id"),
            {"guard": guard, "application_id": row["id"]},
        )

    op.drop_constraint("ck_applications_status", "applications", type_="check")
    op.create_check_constraint(
        "ck_applications_status",
        "applications",
        "status IN ('interested', 'applied', 'interviewing', 'offer', 'accepted', 'rejected', 'withdrawn')",
    )
    op.create_check_constraint(
        "ck_applications_stage",
        "applications",
        "stage IS NULL OR stage IN ('recruiter_contact', 'assessment', 'phone_screen', 'technical_interview', 'final_interview')",
    )
    op.create_unique_constraint(
        "uq_applications_active_saved_job_guard",
        "applications",
        ["workspace_id", "user_id", "user_job_id", "active_duplicate_guard"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_applications_active_saved_job_guard", "applications", type_="unique")
    op.drop_constraint("ck_applications_stage", "applications", type_="check")
    op.drop_constraint("ck_applications_status", "applications", type_="check")
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE applications SET status = 'offer' WHERE status = 'accepted'"))
    connection.execute(sa.text("UPDATE applications SET status = 'archived' WHERE archived_at IS NOT NULL"))
    op.create_check_constraint(
        "ck_applications_status",
        "applications",
        "status IN ('interested', 'applied', 'interviewing', 'offer', 'rejected', 'withdrawn', 'archived')",
    )
    op.drop_index("ix_applications_stage", table_name="applications")
    op.drop_column("applications", "active_duplicate_guard")
    op.drop_column("applications", "stage")
