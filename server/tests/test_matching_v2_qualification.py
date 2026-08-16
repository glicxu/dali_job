from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.accounts.models import User, Workspace
from app.modules.jobs.models import JobCache
from app.modules.matching_v2.models import JobRequirement, QualificationAssessment, RequirementAssessment
from app.modules.matching_v2.qualification import (
    QualificationInput,
    QualificationResult,
    build_qualification_input,
    select_candidate_career_context,
    validate_qualification_assessment,
)
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    SpanInput,
    create_or_get_candidate_profile,
    create_or_get_canonical_source,
    create_or_get_job_profile,
    get_qualification_assessment_for_owner,
)
from app.modules.matching_v2.router import get_qualification_matcher
from app.modules.matching_v2.schemas import (
    CandidateExtractionResponse,
    JobExtractionResponse,
    QualificationAssessmentResponse,
)
from app.modules.profiles import repository as profile_repository
from app.modules.profiles.schemas import ResumeData, ResumeProfileCreateRequest


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session


def _candidate_artifact(ref: str) -> CandidateExtractionResponse:
    signals = {
        "technical_depth": "demonstrated",
        "production_delivery": "demonstrated",
        "scope_and_complexity": "developing",
        "system_design": "limited",
        "ownership": "developing",
        "mentoring": "not_demonstrated",
        "cross_team_influence": "not_demonstrated",
    }
    return CandidateExtractionResponse.model_validate({
        "skills": [{
            "observed_name": "Python",
            "canonical_name": "Python",
            "evidence_strength": "demonstrated",
            "last_used": None,
            "months_experience": None,
            "evidence_refs": [ref],
        }],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "publications": [],
        "career_profiles": [
            {
                "local_ref": "career_teaching",
                "role_family": "technical_education",
                "track": "technical_education",
                "level": "mid",
                "confidence": 0.95,
                "evidence_refs": [ref],
                "dimension_signals": signals,
            },
            {
                "local_ref": "career_software",
                "role_family": "software_engineering",
                "track": "individual_contributor",
                "level": "senior",
                "confidence": 0.85,
                "evidence_refs": [ref],
                "dimension_signals": signals,
            },
        ],
        "recommended_primary_career_profile_ref": "career_teaching",
        "derived": {"headline": None, "summary": None, "suggested_target_roles": []},
        "quality": {"warnings": [], "completeness": 0.9},
    })


def _job_artifact(ref: str) -> JobExtractionResponse:
    requirement = {
        "category": "skill",
        "scoring_dimension": "technical_skill",
        "importance": "required",
        "acceptable_evidence_contexts": ["professional", "open_source"],
        "minimum_years": None,
        "source_refs": [ref],
    }
    return JobExtractionResponse.model_validate({
        "title": "Senior Software Engineer",
        "company": "Example Co",
        "location": {
            "display": None,
            "country": None,
            "region": None,
            "city": None,
            "workplace_type": "unknown",
            "remote_regions": [],
        },
        "employment_type": "full_time",
        "career_context": {
            "primary_role_family": "software_engineering",
            "adjacent_role_families": ["financial_technology"],
            "track": "individual_contributor",
            "target_level": "senior",
            "acceptable_level_range": {"minimum": "mid", "maximum": "staff"},
            "level_source": "explicit",
            "confidence": 0.95,
            "evidence_refs": [ref],
        },
        "compensation": {
            "currency": None,
            "period": "unknown",
            "minimum": None,
            "maximum": None,
            "is_employer_provided": False,
        },
        "requirements": [
            {
                **requirement,
                "local_ref": "python",
                "statement": "Production Python experience",
                "hard_constraint": False,
                "explicit_alternatives": [],
                "policy_alternative_group": None,
            },
            {
                **requirement,
                "local_ref": "language_alternative",
                "statement": "TypeScript, JavaScript, or a comparable language",
                "hard_constraint": True,
                "explicit_alternatives": ["TypeScript", "JavaScript"],
                "policy_alternative_group": "general-purpose-programming-language.v1",
            },
        ],
        "responsibilities": [],
        "application_constraints": {
            "work_authorization": "unknown",
            "sponsorship_available": "unknown",
            "travel_percent": None,
            "clearance": None,
        },
        "cleanup": {"duplicate_spans_removed": 0, "boilerplate_spans_ignored": 0, "warnings": []},
    })


def _foundation(db: Session):
    user, workspace = profile_repository.ensure_dev_account(db)
    resume = profile_repository.create_resume_profile(
        db,
        ResumeProfileCreateRequest(
            title="Qualification Resume",
            resume_data=ResumeData(headline="Software Engineer", skills=["Python"]),
        ),
    )
    owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
    resume_text = "Experience\n- Built and shipped production Python APIs."
    resume_ref = "resume_qualification:experience:0001"
    candidate_source = create_or_get_canonical_source(
        db,
        owner=owner,
        source_type="resume",
        canonical_text=resume_text,
        text_extraction_version="test.v1",
        canonicalization_version="canonical-text.v1",
        resume_profile_id=resume.id,
        spans=[SpanInput(
            span_id=resume_ref,
            section="experience",
            start_utf8_byte=0,
            end_utf8_byte=len(resume_text.encode("utf-8")),
            excerpt=resume_text,
        )],
    )
    candidate = create_or_get_candidate_profile(
        db,
        source=candidate_source,
        artifact=_candidate_artifact(resume_ref),
        model_id="gpt-4.1-mini",
        resume_profile_id=resume.id,
    )

    job_text = "Requirements\n- Production Python experience\n- TypeScript or comparable language"
    job_ref = "job_qualification:requirements:0001"
    cache = JobCache(
        title="Senior Software Engineer",
        company="Example Co",
        source_url="https://example.com/jobs/qualification",
        source_url_hash="qualification-cache-hash",
        raw_description_text=job_text,
        job_data={},
    )
    db.add(cache)
    db.flush()
    job_source = create_or_get_canonical_source(
        db,
        owner=ArtifactOwner.shared(),
        source_type="job",
        canonical_text=job_text,
        text_extraction_version="test.v1",
        canonicalization_version="canonical-text.v1",
        spans=[SpanInput(
            span_id=job_ref,
            section="requirements",
            start_utf8_byte=0,
            end_utf8_byte=len(job_text.encode("utf-8")),
            excerpt=job_text,
        )],
    )
    job = create_or_get_job_profile(
        db,
        source=job_source,
        artifact=_job_artifact(job_ref),
        model_id="gpt-4.1-mini",
        jobs_cache_id=cache.id,
    )
    return owner, candidate, job


def _valid_assessment(requirements: list[JobRequirement], evidence_ref: str):
    normal = next(item for item in requirements if not item.hard_constraint)
    hard = next(item for item in requirements if item.hard_constraint)
    return QualificationAssessmentResponse.model_validate({
        "requirement_assessments": [{
            "requirement_id": normal.requirement_id,
            "status": "met",
            "confidence": 0.92,
            "evidence_refs": [evidence_ref],
            "alternative_policy_ref": None,
            "reason": "Production Python delivery is demonstrated.",
            "missing": [],
        }],
        "hard_constraint_assessments": [{
            "requirement_id": hard.requirement_id,
            "status": "met_by_alternative",
            "confidence": 0.88,
            "evidence_refs": [evidence_ref],
            "alternative_policy_ref": "general-purpose-programming-language.v1",
            "reason": "Python is an approved language alternative.",
            "missing": [],
        }],
    })


def test_career_context_prefers_exact_job_field_over_primary(db: Session) -> None:
    _, candidate, job = _foundation(db)

    context = select_candidate_career_context(
        db, candidate_profile=candidate, job_profile=job, selection_revision=1
    )

    assert context.career_profile is not None
    assert context.career_profile.role_family == "software_engineering"
    assert context.reason_code == "EXACT_ROLE_FAMILY_AND_TRACK"


def test_qualification_input_excludes_derived_candidate_fields(db: Session) -> None:
    _, candidate, job = _foundation(db)
    context = select_candidate_career_context(
        db, candidate_profile=candidate, job_profile=job, selection_revision=1
    )

    qualification_input = build_qualification_input(
        db, candidate_profile=candidate, job_profile=job, career_context=context.career_profile
    )

    assert len(qualification_input.candidate_evidence) == 1
    assert "headline" not in str(qualification_input.candidate_evidence)
    assert len(qualification_input.job_requirements) == 2
    assert qualification_input.approved_alternatives[-1]["policy_hash"].startswith("sha256:")


def test_qualification_validator_enforces_exact_coverage_and_evidence(db: Session) -> None:
    _, candidate, job = _foundation(db)
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job.id
    )).all())
    evidence_ref = next(iter(build_qualification_input(
        db, candidate_profile=candidate, job_profile=job, career_context=None
    ).allowed_evidence_refs))
    valid = _valid_assessment(requirements, evidence_ref)

    assert validate_qualification_assessment(
        valid, requirements=requirements, allowed_evidence_refs={evidence_ref}
    ) == valid
    missing = valid.model_copy(update={"hard_constraint_assessments": []})
    with pytest.raises(ValueError, match="every hard constraint exactly once"):
        validate_qualification_assessment(
            missing, requirements=requirements, allowed_evidence_refs={evidence_ref}
        )
    unsupported = valid.model_copy(update={
        "requirement_assessments": [valid.requirement_assessments[0].model_copy(
            update={"evidence_refs": ["resume:unknown"]}
        )]
    })
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_qualification_assessment(
            unsupported, requirements=requirements, allowed_evidence_refs={evidence_ref}
        )


def test_low_confidence_and_absent_evidence_are_normalized(db: Session) -> None:
    _, candidate, job = _foundation(db)
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job.id
    )).all())
    evidence_ref = next(iter(build_qualification_input(
        db, candidate_profile=candidate, job_profile=job, career_context=None
    ).allowed_evidence_refs))
    artifact = _valid_assessment(requirements, evidence_ref)
    normal = artifact.requirement_assessments[0].model_copy(update={
        "status": "needs_clarification",
        "confidence": 0.5,
        "evidence_refs": [],
        "reason": "No evidence.",
        "missing": [],
    })
    artifact = artifact.model_copy(update={"requirement_assessments": [normal]})

    validated = validate_qualification_assessment(
        artifact, requirements=requirements, allowed_evidence_refs={evidence_ref}
    )

    assert validated.requirement_assessments[0].status == "not_demonstrated"


class StubQualificationMatcher:
    def __init__(self) -> None:
        self.calls = 0

    def assess(self, qualification_input: QualificationInput) -> QualificationResult:
        self.calls += 1
        evidence_ref = next(iter(qualification_input.allowed_evidence_refs))
        normal = next(item for item in qualification_input.job_requirements if not item["hard_constraint"])
        hard = next(item for item in qualification_input.job_requirements if item["hard_constraint"])
        return QualificationResult(
            artifact=QualificationAssessmentResponse.model_validate({
                "requirement_assessments": [{
                    "requirement_id": normal["requirement_id"],
                    "status": "met",
                    "confidence": 0.9,
                    "evidence_refs": [evidence_ref],
                    "alternative_policy_ref": None,
                    "reason": "Direct evidence.",
                    "missing": [],
                }],
                "hard_constraint_assessments": [{
                    "requirement_id": hard["requirement_id"],
                    "status": "met_by_alternative",
                    "confidence": 0.9,
                    "evidence_refs": [evidence_ref],
                    "alternative_policy_ref": "general-purpose-programming-language.v1",
                    "reason": "Approved alternative.",
                    "missing": [],
                }],
            }),
            model_id="gpt-4.1-mini",
            provider_execution_reference="provider-qualification-test-1",
        )


def test_qualification_api_creates_caches_and_reads_private_assessment() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory.begin() as db:
        _, candidate, job = _foundation(db)
        candidate_id = candidate.public_id
        job_id = job.public_id

    def override_db():
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    matcher = StubQualificationMatcher()
    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, shadow_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_qualification_matcher] = lambda: matcher
    client = TestClient(app)
    payload = {
        "candidate_profile_id": candidate_id,
        "candidate_career_selection_revision": 1,
        "job_profile_id": job_id,
    }

    first = client.post("/api/v1/qualification-assessments", json=payload)
    second = client.post("/api/v1/qualification-assessments", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert matcher.calls == 1
    body = first.json()
    assert body["qualification_assessment_id"].startswith("qa_")
    assert body["career_context"]["selection_reason_code"] == "EXACT_ROLE_FAMILY_AND_TRACK"
    assert body["assessment"]["requirement_assessments"][0]["status"] == "met"
    assert "score" not in body
    fetched = client.get(
        f"/api/v1/qualification-assessments/{body['qualification_assessment_id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["qualification_assessment_id"] == body["qualification_assessment_id"]

    with factory.begin() as db:
        persisted = db.scalar(select(QualificationAssessment).where(
            QualificationAssessment.public_id == body["qualification_assessment_id"]
        ))
        assert persisted is not None
        assert len(db.scalars(select(RequirementAssessment).where(
            RequirementAssessment.qualification_assessment_id == persisted.id
        )).all()) == 2
        other_user = User(email="qualification-other@example.com", display_name="Other")
        db.add(other_user)
        db.flush()
        other_workspace = Workspace(owner_user_id=other_user.id, name="Other Workspace")
        db.add(other_workspace)
        db.flush()
        assert get_qualification_assessment_for_owner(
            db,
            public_id=persisted.public_id,
            owner=ArtifactOwner.authenticated(
                workspace_id=other_workspace.id,
                user_id=other_user.id,
            ),
        ) is None
