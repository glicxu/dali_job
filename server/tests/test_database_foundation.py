from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.profiles import repository
from app.modules.profiles.schemas import ResumeData


def test_foundation_tables_are_registered_in_metadata() -> None:
    assert {"users", "workspaces", "profiles"}.issubset(Base.metadata.tables.keys())
    assert "skills" not in Base.metadata.tables
    assert "experiences" not in Base.metadata.tables

    user_columns = set(Base.metadata.tables["users"].columns.keys())
    workspace_columns = set(Base.metadata.tables["workspaces"].columns.keys())
    profile_columns = set(Base.metadata.tables["profiles"].columns.keys())

    assert {
        "id",
        "email",
        "display_name",
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


def test_foundation_metadata_can_create_tables() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    assert inspector.has_table("users")
    assert inspector.has_table("workspaces")
    assert inspector.has_table("profiles")
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

    assert script.get_current_head() == "20260617_0001"


def test_profile_repository_creates_local_resume_json() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        profile = repository.get_or_create_profile(session)
        saved = repository.update_profile_resume_data(
            session,
            ResumeData(
                name="Example User",
                headline="Backend Engineer",
                skills=["Python", "FastAPI"],
                experience=["Backend Engineer at Example Co"],
            ),
        )

        assert profile.workspace_id
        assert saved.resume_data["name"] == "Example User"
        assert saved.resume_data["skills"] == ["Python", "FastAPI"]


def test_resume_suggestions_replace_resume_json() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with session_factory() as session:
        saved = repository.apply_resume_suggestions(
            session,
            ResumeData(
                name="Example User",
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
