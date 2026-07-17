"""add application materials, reminders, and download tickets

Revision ID: 20260715_0020
Revises: 20260714_0019
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0020"
down_revision = "20260714_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detached_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('resume', 'cover_letter', 'supporting')",
            name="ck_application_documents_purpose",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_documents_application_id",
        "application_documents",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_documents_document_version_id",
        "application_documents",
        ["document_version_id"],
        unique=False,
    )

    op.create_table(
        "document_download_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_document_download_tickets_token_hash"),
    )
    op.create_index(
        "ix_document_download_tickets_application_id",
        "document_download_tickets",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_download_tickets_document_version_id",
        "document_download_tickets",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_download_tickets_expires_at",
        "document_download_tickets",
        ["expires_at"],
        unique=False,
    )
    op.create_index("ix_document_download_tickets_user_id", "document_download_tickets", ["user_id"], unique=False)
    op.create_index(
        "ix_document_download_tickets_workspace_id",
        "document_download_tickets",
        ["workspace_id"],
        unique=False,
    )

    op.add_column(
        "application_tasks",
        sa.Column("task_type", sa.String(length=40), nullable=False, server_default="other"),
    )
    op.add_column("application_tasks", sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "application_tasks",
        sa.Column("reminder_dismissed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "application_tasks",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE application_tasks SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column(
        "application_tasks",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_application_tasks_type",
        "application_tasks",
        "task_type IN ('follow_up', 'interview_prep', 'document', 'deadline', 'other')",
    )
    op.create_index("ix_application_tasks_task_type", "application_tasks", ["task_type"], unique=False)
    op.create_index("ix_application_tasks_reminder_at", "application_tasks", ["reminder_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_application_tasks_reminder_at", table_name="application_tasks")
    op.drop_index("ix_application_tasks_task_type", table_name="application_tasks")
    op.drop_constraint("ck_application_tasks_type", "application_tasks", type_="check")
    op.drop_column("application_tasks", "updated_at")
    op.drop_column("application_tasks", "reminder_dismissed_at")
    op.drop_column("application_tasks", "reminder_at")
    op.drop_column("application_tasks", "task_type")

    op.drop_index("ix_document_download_tickets_workspace_id", table_name="document_download_tickets")
    op.drop_index("ix_document_download_tickets_user_id", table_name="document_download_tickets")
    op.drop_index("ix_document_download_tickets_expires_at", table_name="document_download_tickets")
    op.drop_index("ix_document_download_tickets_document_version_id", table_name="document_download_tickets")
    op.drop_index("ix_document_download_tickets_application_id", table_name="document_download_tickets")
    op.drop_table("document_download_tickets")

    op.drop_index("ix_application_documents_document_version_id", table_name="application_documents")
    op.drop_index("ix_application_documents_application_id", table_name="application_documents")
    op.drop_table("application_documents")
