from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

import pytest

from app.db.base import Base
from app.modules.accounts.models import User, Workspace
from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateCareerSelection,
    CandidateProfileVersion,
    PromptPolicyRegistryRecord,
    SourceSpan,
)
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    ArtifactOwnershipError,
    RevisionConflict,
    SpanInput,
    create_career_selection,
    create_or_get_candidate_profile,
    create_or_get_canonical_source,
    get_candidate_profile_for_owner,
    sync_policy_registry,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY
from app.modules.matching_v2.schemas import CandidateExtractionResponse
from app.modules.profiles import repository as profile_repository
from app.modules.profiles.schemas import ResumeData, ResumeProfileCreateRequest


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session


def _owner_and_resume(db: Session) -> tuple[ArtifactOwner, int]:
    user, workspace = profile_repository.ensure_dev_account(db)
    profile = profile_repository.create_resume_profile(
        db,
        ResumeProfileCreateRequest(
            title="Evidence Resume",
            resume_data=ResumeData(headline="Software Engineer", skills=["Python"]),
        ),
    )
    return ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id), profile.id


def _candidate_artifact(evidence_ref: str) -> CandidateExtractionResponse:
    return CandidateExtractionResponse.model_validate(
        {
            "skills": [],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
            "publications": [],
            "awards": [],
            "patents": [],
            "languages": [],
            "career_profiles": [
                {
                    "local_ref": "career_software_engineering",
                    "role_family": "software_engineering",
                    "track": "individual_contributor",
                    "level": "entry",
                    "confidence": 0.86,
                    "evidence_refs": [evidence_ref],
                    "dimension_signals": {
                        "technical_depth": "developing",
                        "production_delivery": "not_demonstrated",
                        "scope_and_complexity": "limited",
                        "system_design": "not_demonstrated",
                        "ownership": "developing",
                        "mentoring": "not_demonstrated",
                        "cross_team_influence": "not_demonstrated",
                    },
                }
            ],
            "recommended_primary_career_profile_ref": "career_software_engineering",
            "derived": {
                "headline": "Entry Software Engineer",
                "summary": "Evidence-backed software profile.",
                "suggested_target_roles": ["Software Engineer"],
            },
            "quality": {"warnings": [], "completeness": 0.75},
        }
    )


def _source(db: Session, owner: ArtifactOwner, resume_profile_id: int):
    text = "Summary\nBuilt café systems with Python."
    encoded = text.encode("utf-8")
    span_id = "resume_01:summary:0001"
    source = create_or_get_canonical_source(
        db,
        owner=owner,
        source_type="resume",
        canonical_text=text,
        text_extraction_version="resume-text.v1",
        canonicalization_version="canonical-text.v1",
        resume_profile_id=resume_profile_id,
        spans=[
            SpanInput(
                span_id=span_id,
                section="summary",
                start_utf8_byte=0,
                end_utf8_byte=len(encoded),
                excerpt=text,
            )
        ],
    )
    return source, span_id


def test_canonical_source_is_owner_scoped_and_cacheable(db: Session) -> None:
    owner, resume_profile_id = _owner_and_resume(db)
    first, _ = _source(db, owner, resume_profile_id)
    second, _ = _source(db, owner, resume_profile_id)

    assert second.id == first.id
    assert db.scalar(select(func.count(SourceSpan.id))) == 1
    assert first.source_hash.startswith("sha256:")
    assert first.cache_key.startswith("sha256:")

    other_user = User(email="other@example.com", display_name="Other")
    db.add(other_user)
    db.flush()
    other_workspace = Workspace(owner_user_id=other_user.id, name="Other Workspace")
    db.add(other_workspace)
    db.flush()
    other_owner = ArtifactOwner.authenticated(
        workspace_id=other_workspace.id,
        user_id=other_user.id,
    )
    other = create_or_get_canonical_source(
        db,
        owner=other_owner,
        source_type="resume",
        canonical_text=first.canonical_text,
        text_extraction_version="resume-text.v1",
        canonicalization_version="canonical-text.v1",
        spans=[],
    )

    assert other.id != first.id
    assert other.cache_key != first.cache_key


def test_canonical_source_rejects_cross_owner_resume_profile(db: Session) -> None:
    _, resume_profile_id = _owner_and_resume(db)
    other_user = User(email="second@example.com", display_name="Second")
    db.add(other_user)
    db.flush()
    other_workspace = Workspace(owner_user_id=other_user.id, name="Second Workspace")
    db.add(other_workspace)
    db.flush()

    with pytest.raises(ArtifactOwnershipError, match="does not belong"):
        create_or_get_canonical_source(
            db,
            owner=ArtifactOwner.authenticated(
                workspace_id=other_workspace.id,
                user_id=other_user.id,
            ),
            source_type="resume",
            canonical_text="Private resume",
            text_extraction_version="resume-text.v1",
            canonicalization_version="canonical-text.v1",
            resume_profile_id=resume_profile_id,
            spans=[],
        )


def test_candidate_profile_persists_career_context_and_initial_selection(db: Session) -> None:
    owner, resume_profile_id = _owner_and_resume(db)
    source, span_id = _source(db, owner, resume_profile_id)
    artifact = _candidate_artifact(span_id)

    first = create_or_get_candidate_profile(
        db,
        source=source,
        artifact=artifact,
        model_id="test-model",
        resume_profile_id=resume_profile_id,
    )
    second = create_or_get_candidate_profile(
        db,
        source=source,
        artifact=artifact,
        model_id="test-model",
        resume_profile_id=resume_profile_id,
    )

    assert second.id == first.id
    assert first.response_schema_hash.startswith("sha256:")
    career = db.scalar(
        select(CandidateCareerProfile).where(
            CandidateCareerProfile.candidate_profile_version_id == first.id
        )
    )
    assert career is not None
    assert career.career_profile_id.startswith("career_")
    assert career.role_family == "software_engineering"
    initial = db.scalar(
        select(CandidateCareerSelection).where(
            CandidateCareerSelection.candidate_profile_version_id == first.id
        )
    )
    assert initial is not None
    assert initial.revision == 1
    assert initial.candidate_career_profile_id == career.id
    assert initial.selection_source == "model_default"

    selected = create_career_selection(
        db,
        candidate_profile_public_id=first.public_id,
        owner=owner,
        expected_revision=1,
        career_profile_id=career.career_profile_id,
        selection_source="user_confirmed",
    )
    assert selected.revision == 2

    with pytest.raises(RevisionConflict, match="current revision is 2"):
        create_career_selection(
            db,
            candidate_profile_public_id=first.public_id,
            owner=owner,
            expected_revision=1,
            career_profile_id=career.career_profile_id,
            selection_source="user_confirmed",
        )


def test_candidate_profile_read_is_owner_scoped(db: Session) -> None:
    owner, resume_profile_id = _owner_and_resume(db)
    source, span_id = _source(db, owner, resume_profile_id)
    profile = create_or_get_candidate_profile(
        db,
        source=source,
        artifact=_candidate_artifact(span_id),
        model_id="test-model",
        resume_profile_id=resume_profile_id,
    )

    assert get_candidate_profile_for_owner(db, public_id=profile.public_id, owner=owner) is not None
    assert (
        get_candidate_profile_for_owner(
            db,
            public_id=profile.public_id,
            owner=ArtifactOwner.shared(),
        )
        is None
    )


def test_candidate_profile_rejects_unknown_evidence_reference(db: Session) -> None:
    owner, resume_profile_id = _owner_and_resume(db)
    source, _ = _source(db, owner, resume_profile_id)

    with pytest.raises(ValueError, match="unknown evidence references"):
        create_or_get_candidate_profile(
            db,
            source=source,
            artifact=_candidate_artifact("resume_01:summary:missing"),
            model_id="test-model",
            resume_profile_id=resume_profile_id,
        )


def test_policy_registry_sync_is_idempotent(db: Session) -> None:
    first = sync_policy_registry(db)
    second = sync_policy_registry(db)

    assert len(first) == len(DEFAULT_REGISTRY.entries())
    assert [item.id for item in second] == [item.id for item in first]
    assert db.scalar(select(func.count(PromptPolicyRegistryRecord.id))) == len(
        DEFAULT_REGISTRY.entries()
    )
    assert db.scalar(select(func.count(CandidateProfileVersion.id))) == 0


def test_candidate_foundation_migration_upgrades_existing_schema() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    matching_tables = {
        "matching_canonical_sources",
        "matching_source_spans",
        "matching_candidate_profile_versions",
        "matching_candidate_career_profiles",
        "matching_candidate_career_selections",
        "matching_policy_registry",
        "matching_job_profile_versions",
        "matching_job_requirements",
        "matching_qualification_assessments",
        "matching_requirement_assessments",
    }
    Base.metadata.create_all(
        bind=engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name not in matching_tables],
    )
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "db"
        / "migrations"
        / "versions"
        / "20260815_0039_matching_v2_candidate_foundation.py"
    )
    spec = importlib.util.spec_from_file_location("matching_v2_candidate_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

    inspector = inspect(engine)
    later_tables = {
        "matching_job_profile_versions",
        "matching_job_requirements",
        "matching_qualification_assessments",
        "matching_requirement_assessments",
    }
    assert matching_tables - later_tables <= set(inspector.get_table_names())
    source_indexes = {item["name"]: item for item in inspector.get_indexes("matching_canonical_sources")}
    assert source_indexes["ix_matching_sources_cache_key"]["unique"] == 1


def test_job_profile_migration_upgrades_candidate_foundation_schema() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    job_profile_tables = {"matching_job_profile_versions", "matching_job_requirements"}
    qualification_tables = {
        "matching_qualification_assessments",
        "matching_requirement_assessments",
    }
    Base.metadata.create_all(
        bind=engine,
        tables=[
            table
            for table in Base.metadata.sorted_tables
            if table.name not in job_profile_tables | qualification_tables
        ],
    )
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "db"
        / "migrations"
        / "versions"
        / "20260815_0040_matching_v2_job_profiles.py"
    )
    spec = importlib.util.spec_from_file_location("matching_v2_job_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

    inspector = inspect(engine)
    assert job_profile_tables <= set(inspector.get_table_names())
    indexes = {item["name"]: item for item in inspector.get_indexes("matching_job_profile_versions")}
    assert indexes["ix_matching_job_versions_cache"]["unique"] == 1


def test_qualification_migration_upgrades_job_profile_schema() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    qualification_tables = {
        "matching_qualification_assessments",
        "matching_requirement_assessments",
    }
    Base.metadata.create_all(
        bind=engine,
        tables=[
            table for table in Base.metadata.sorted_tables if table.name not in qualification_tables
        ],
    )
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "db"
        / "migrations"
        / "versions"
        / "20260815_0041_matching_v2_qualification_assessments.py"
    )
    spec = importlib.util.spec_from_file_location("matching_v2_qualification_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

    inspector = inspect(engine)
    assert qualification_tables <= set(inspector.get_table_names())
    indexes = {
        item["name"]: item
        for item in inspector.get_indexes("matching_qualification_assessments")
    }
    assert indexes["ix_matching_qualifications_cache"]["unique"] == 1
