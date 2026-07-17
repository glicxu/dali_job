from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.accounts.models import User, Workspace
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.profiles import repository
from app.modules.profiles.schemas import ResumeData, ResumeProfileCreateRequest, ResumeProfileUpdateRequest


def test_foundation_tables_are_registered_in_metadata() -> None:
    assert {
        "users",
        "workspaces",
        "resume_profiles",
        "documents",
        "document_versions",
        "jobs_cache",
        "user_saved_jobs",
        "job_resume_matches",
        "applications",
        "application_status_history",
        "application_events",
        "application_notes",
        "application_tasks",
        "application_documents",
        "document_download_tickets",
        "managed_operations",
        "interviews",
        "interview_notes",
        "interview_prep_guides",
    }.issubset(Base.metadata.tables.keys())
    assert "skills" not in Base.metadata.tables
    assert "experiences" not in Base.metadata.tables
    assert "profiles" not in Base.metadata.tables

    user_columns = set(Base.metadata.tables["users"].columns.keys())
    workspace_columns = set(Base.metadata.tables["workspaces"].columns.keys())
    resume_profile_columns = set(Base.metadata.tables["resume_profiles"].columns.keys())
    document_columns = set(Base.metadata.tables["documents"].columns.keys())
    document_version_columns = set(Base.metadata.tables["document_versions"].columns.keys())
    job_cache_columns = set(Base.metadata.tables["jobs_cache"].columns.keys())
    user_saved_job_columns = set(Base.metadata.tables["user_saved_jobs"].columns.keys())
    job_resume_match_columns = set(Base.metadata.tables["job_resume_matches"].columns.keys())
    application_columns = set(Base.metadata.tables["applications"].columns.keys())
    application_task_columns = set(Base.metadata.tables["application_tasks"].columns.keys())
    application_document_columns = set(Base.metadata.tables["application_documents"].columns.keys())

    assert {
        "id",
        "email",
        "display_name",
        "password_hash",
        "auth_provider",
        "is_active",
        "timezone",
        "created_at",
        "updated_at",
        "deleted_at",
    }.issubset(user_columns)
    assert {
        "id",
        "owner_user_id",
        "name",
        "created_at",
        "updated_at",
    }.issubset(workspace_columns)
    assert {
        "id",
        "workspace_id",
        "user_id",
        "title",
        "resume_data",
        "source_document_id",
        "source_document_version_id",
        "is_default",
        "created_at",
        "updated_at",
        "deleted_at",
    }.issubset(resume_profile_columns)
    assert {
        "id",
        "workspace_id",
        "user_id",
        "title",
        "document_type",
        "created_at",
        "updated_at",
        "deleted_at",
    }.issubset(document_columns)
    assert {
        "id",
        "document_id",
        "version_number",
        "file_name",
        "content_type",
        "size_bytes",
        "sha256",
        "storage_path",
        "extracted_text",
        "created_at",
    }.issubset(document_version_columns)
    assert {
        "id",
        "title",
        "company",
        "source_url",
        "source_url_hash",
        "raw_description_text",
        "job_data",
        "created_at",
        "updated_at",
        "deleted_at",
    }.issubset(job_cache_columns)
    assert {
        "id",
        "workspace_id",
        "user_id",
        "jobs_cache_id",
        "notes",
        "created_at",
        "updated_at",
        "archived_at",
        "deleted_at",
    }.issubset(user_saved_job_columns)
    assert "title" not in user_saved_job_columns
    assert "company" not in user_saved_job_columns
    assert "source_url" not in user_saved_job_columns
    assert "raw_description_text" not in user_saved_job_columns
    assert "job_data" not in user_saved_job_columns
    assert "saved_at" not in user_saved_job_columns
    assert "workspace_id" not in job_cache_columns
    assert "user_id" not in job_cache_columns
    assert "notes" not in job_cache_columns
    assert {
        "id",
        "workspace_id",
        "user_id",
        "user_job_id",
        "jobs_cache_id",
        "resume_profile_id",
        "resume_document_id",
        "resume_source",
        "match_score",
        "match_data",
        "resume_data_snapshot",
        "job_data_snapshot",
        "resume_snapshot_hash",
        "job_snapshot_hash",
        "provider",
        "model_name",
        "prompt_version",
        "schema_version",
        "provider_execution_reference",
        "created_at",
    }.issubset(job_resume_match_columns)
    assert "match_score" not in job_cache_columns
    assert "matched_resume_document_id" not in job_cache_columns
    assert "matched_resume_source" not in job_cache_columns
    assert Base.metadata.tables["jobs_cache"].columns["job_data"].nullable is True
    assert {
        "id",
        "workspace_id",
        "user_id",
        "user_job_id",
        "source_url_snapshot",
        "source_label_snapshot",
        "status",
        "stage",
        "active_duplicate_guard",
        "priority",
        "match_score",
        "salary_notes",
        "applied_at",
        "next_action_at",
        "next_action_label",
        "notes",
        "created_at",
        "updated_at",
        "archived_at",
    }.issubset(application_columns)
    application_constraints = {
        constraint.name for constraint in Base.metadata.tables["applications"].constraints
    }
    assert "uq_applications_active_saved_job_guard" in application_constraints
    assert {
        "id",
        "application_id",
        "title",
        "task_type",
        "due_at",
        "reminder_at",
        "reminder_dismissed_at",
        "completed_at",
        "created_at",
        "updated_at",
    }.issubset(application_task_columns)
    assert {
        "id",
        "application_id",
        "document_version_id",
        "purpose",
        "created_at",
        "detached_at",
    }.issubset(application_document_columns)


def test_foundation_metadata_can_create_tables() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert inspector.has_table("users")
    assert inspector.has_table("workspaces")
    assert inspector.has_table("resume_profiles")
    assert inspector.has_table("documents")
    assert inspector.has_table("document_versions")
    assert inspector.has_table("jobs_cache")
    assert inspector.has_table("user_saved_jobs")
    assert inspector.has_table("job_resume_matches")
    assert inspector.has_table("applications")
    assert inspector.has_table("application_status_history")
    assert inspector.has_table("application_events")
    assert inspector.has_table("application_notes")
    assert inspector.has_table("application_tasks")
    assert inspector.has_table("application_documents")
    assert inspector.has_table("document_download_tickets")
    assert inspector.has_table("managed_operations")
    assert inspector.has_table("interviews")
    assert inspector.has_table("interview_notes")
    assert inspector.has_table("interview_prep_guides")
    assert not inspector.has_table("skills")
    assert not inspector.has_table("experiences")
    assert not inspector.has_table("profiles")

    foreign_keys = inspector.get_foreign_keys("workspaces")
    assert foreign_keys[0]["referred_table"] == "users"
    assert foreign_keys[0]["constrained_columns"] == ["owner_user_id"]


def test_alembic_has_initial_schema_revision() -> None:
    server_dir = Path(__file__).resolve().parents[1]
    config = Config(str(server_dir / "alembic.ini"))
    config.set_main_option("script_location", str(server_dir / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "20260715_0023"


def test_phase3_migration_does_not_recreate_existing_document_version_constraint() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "db"
        / "migrations"
        / "versions"
        / "20260715_0020_application_materials_and_reminders.py"
    )
    migration_text = migration_path.read_text(encoding="utf-8")

    assert "create_unique_constraint(\n        \"uq_document_versions_document_version\"" not in migration_text
    assert "drop_constraint(\"uq_document_versions_document_version\"" not in migration_text


def test_jobs_cache_source_url_hash_is_unique_in_metadata() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    Base.metadata.create_all(bind=engine)

    indexes = {index["name"]: index for index in inspect(engine).get_indexes("jobs_cache")}
    assert bool(indexes["ix_jobs_cache_source_url_hash"]["unique"]) is True


def test_resume_profile_repository_creates_local_resume_json() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        saved = repository.create_resume_profile(
            session,
            ResumeProfileCreateRequest(
                title="Backend Resume",
                resume_data=ResumeData(
                    headline="Backend Engineer",
                    skills=["Python", "FastAPI"],
                    experience=["Backend Engineer at Example Co"],
                ),
            ),
        )

        assert "name" not in saved.resume_data
        assert "contact" not in saved.resume_data
        assert saved.resume_data["skills"] == ["Python", "FastAPI"]


def test_resume_suggestions_create_resume_profile() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        saved = repository.apply_resume_suggestions(
            session,
            ResumeData(
                headline="Backend Engineer",
                summary="Builds Python services.",
                skills=["Python"],
                experience=["Software Engineer at Example Co"],
            ),
        )

        assert saved.title == "Backend Engineer"
        assert saved.resume_data["headline"] == "Backend Engineer"
        assert saved.resume_data["skills"] == ["Python"]


def test_resume_profiles_allow_one_default_profile() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        first = repository.apply_resume_suggestions(
            session,
            ResumeData(headline="Backend Resume", skills=["Python"]),
        )
        assert first.is_default is True
        second = repository.apply_resume_suggestions(
            session,
            ResumeData(headline="Data Resume", skills=["SQL"]),
        )
        assert second.is_default is False
        repository.update_resume_profile(
            session,
            second,
            ResumeProfileUpdateRequest(is_default=True),
        )

        profiles = repository.list_resume_profiles(session)
        assert profiles[0].id == second.id
        assert profiles[0].is_default is True
        assert profiles[1].is_default is False
        assert {profile.id for profile in profiles} == {first.id, second.id}


def test_profile_repository_maps_sso_identity_to_private_workspace() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    identity = AuthenticatedIdentity(
        external_user_id="sso-user@example.com",
        email="sso-user@example.com",
        display_name="SSO User",
        provider="dalijob",
    )

    with session_factory() as session:
        user, workspace = repository.ensure_account_for_identity(session, identity)

        assert user is not None
        assert workspace is not None
        assert user.email == "sso-user@example.com"
        assert workspace.owner_user_id == user.id
        assert workspace.name == "SSO User's Career Search"
