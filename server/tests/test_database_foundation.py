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
from app.modules.profiles.schemas import ResumeData


def test_foundation_tables_are_registered_in_metadata() -> None:
    assert {"users", "workspaces", "profiles", "documents", "document_versions", "jobs"}.issubset(
        Base.metadata.tables.keys()
    )
    assert "skills" not in Base.metadata.tables
    assert "experiences" not in Base.metadata.tables

    user_columns = set(Base.metadata.tables["users"].columns.keys())
    workspace_columns = set(Base.metadata.tables["workspaces"].columns.keys())
    profile_columns = set(Base.metadata.tables["profiles"].columns.keys())
    document_columns = set(Base.metadata.tables["documents"].columns.keys())
    document_version_columns = set(Base.metadata.tables["document_versions"].columns.keys())
    job_columns = set(Base.metadata.tables["jobs"].columns.keys())

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
        "resume_data",
        "created_at",
        "updated_at",
    }.issubset(profile_columns)
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
        "workspace_id",
        "user_id",
        "title",
        "company",
        "source_url",
        "raw_description_text",
        "job_data",
        "notes",
        "match_score",
        "matched_resume_document_id",
        "matched_resume_source",
        "created_at",
        "updated_at",
        "deleted_at",
    }.issubset(job_columns)


def test_foundation_metadata_can_create_tables() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert inspector.has_table("users")
    assert inspector.has_table("workspaces")
    assert inspector.has_table("profiles")
    assert inspector.has_table("documents")
    assert inspector.has_table("document_versions")
    assert inspector.has_table("jobs")
    assert not inspector.has_table("skills")
    assert not inspector.has_table("experiences")

    foreign_keys = inspector.get_foreign_keys("workspaces")
    assert foreign_keys[0]["referred_table"] == "users"
    assert foreign_keys[0]["constrained_columns"] == ["owner_user_id"]


def test_alembic_has_initial_schema_revision() -> None:
    server_dir = Path(__file__).resolve().parents[1]
    config = Config(str(server_dir / "alembic.ini"))
    config.set_main_option("script_location", str(server_dir / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "20260619_0006"


def test_profile_repository_creates_local_resume_json() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        profile = repository.get_or_create_profile(session)
        saved = repository.update_profile_resume_data(
            session,
            ResumeData(
                headline="Backend Engineer",
                skills=["Python", "FastAPI"],
                experience=["Backend Engineer at Example Co"],
            ),
        )

        assert profile.workspace_id
        assert "name" not in saved.resume_data
        assert "contact" not in saved.resume_data
        assert saved.resume_data["skills"] == ["Python", "FastAPI"]


def test_resume_suggestions_replace_resume_json() -> None:
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

        profile = repository.get_or_create_profile(session)
        assert saved.id == profile.id
        assert profile.resume_data["headline"] == "Backend Engineer"
        assert profile.resume_data["skills"] == ["Python"]


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
        profile = repository.get_or_create_profile(session, identity)
        user = session.get(User, profile.user_id)
        workspace = session.get(Workspace, profile.workspace_id)

        assert user is not None
        assert workspace is not None
        assert user.email == "sso-user@example.com"
        assert workspace.owner_user_id == profile.user_id
        assert workspace.name == "SSO User's Career Search"
