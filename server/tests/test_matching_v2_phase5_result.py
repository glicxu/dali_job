from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.core.secrets import clear_secret_cache
from app.modules.matching_v2.eligibility import CandidateEligibilityFacts
from app.modules.matching_v2.models import (
    CanonicalSource,
    JobProfileVersion,
    JobRequirement,
    QualificationAssessment,
)
from app.modules.matching_v2.phase5 import (
    create_eligibility_revision,
    create_or_get_match_result,
    create_preference_revision,
)
from app.modules.matching_v2.preferences import DesiredValue, UserPreferences
from app.modules.matching_v2.repositories import ArtifactOwner
from app.modules.profiles import repository as profile_repository


def test_match_result_is_deterministic_cached_and_legacy_adapted(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_ELIGIBILITY_ENCRYPTION_KEY", "phase5-result-test-key")
    clear_secret_cache()
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        user, workspace = profile_repository.ensure_dev_account(db)
        owner = ArtifactOwner.authenticated(workspace_id=workspace.id, user_id=user.id)
        job_source = CanonicalSource(
            public_id="src_job_phase5",
            owner_kind="shared",
            source_type="job",
            source_hash="sha256:job",
            canonical_text="Senior software engineer. Python required.",
            text_extraction_version="job-import.v1",
            canonicalization_version="canonical-text.v1",
            language="en",
            cache_key="sha256:job-source",
        )
        db.add(job_source)
        db.flush()
        job = JobProfileVersion(
            public_id="jp_phase5",
            canonical_source_id=job_source.id,
            schema_version="job-profile.v3",
            response_schema_hash="sha256:schema",
            prompt_version="job-extract.v3",
            taxonomy_version="matching-taxonomy.v2",
            source_policy_version="cached-job-reuse.v1",
            deduplication_version="job-deduplication.v1",
            semantic_validator_version="job-semantic-validator.v3",
            model_id="test",
            artifact={
                "title": "Senior Software Engineer",
                "company": "Example",
                "location": {"display": "Remote-US", "country": "US", "region": None, "city": None, "workplace_type": "remote", "remote_regions": ["Remote-US"]},
                "employment_type": "full_time",
                "career_context": {"primary_role_family": "software_engineering", "adjacent_role_families": [], "track": "individual_contributor", "target_level": "senior", "acceptable_level_range": None, "level_source": "explicit", "confidence": 0.95, "evidence_refs": ["job:1"]},
                "compensation": {"currency": None, "period": "unknown", "minimum": None, "maximum": None, "is_employer_provided": False},
                "requirements": [{"local_ref": "python", "category": "skill", "scoring_dimension": "technical_skill", "statement": "Python", "importance": "required", "acceptable_evidence_contexts": ["professional"], "minimum_years": None, "alternative_groups": [], "policy_alternative_group": None, "source_refs": ["job:1"]}],
                "responsibilities": [],
                "application_constraints": {"work_authorization": "unknown", "sponsorship_available": "unknown", "travel_percent": None, "clearance": None},
                "cleanup": {"duplicate_spans_removed": 0, "boilerplate_spans_ignored": 0, "warnings": []},
            },
            cleanup={},
            cache_key="sha256:job-profile",
        )
        db.add(job)
        db.flush()
        requirement = JobRequirement(
            job_profile_version_id=job.id, requirement_id="req_python", local_ref="python", category="skill", scoring_dimension="technical_skill", statement="Python", importance="required", hard_constraint=False, acceptable_evidence_contexts=["professional"], minimum_years=None, explicit_alternatives=[], policy_alternative_group=None, source_refs=["job:1"]
        )
        db.add(requirement)
        db.flush()
        qualification = QualificationAssessment(
            public_id="qa_phase5", owner_kind="authenticated", workspace_id=workspace.id, user_id=user.id,
            candidate_profile_version_id=1, candidate_career_selection_id=1, candidate_career_selection_revision=1, selection_reason_code="EXACT_ROLE_TRACK", job_profile_version_id=job.id,
            schema_version="qualification-assessment.v2", response_schema_hash="sha256:qa-schema", prompt_version="qualification-match.v2", selection_policy_version="career-selection-policy.v2", matching_policy_version="qualification-policy.v2", input_policy_version="qualification-input.v2", semantic_validator_version="matching-semantic-validator.v4", alternative_policy_hashes={}, model_id="test",
            artifact={"requirement_assessments": [{"requirement_id": "req_python", "status": "met", "confidence": 0.99, "evidence_refs": ["resume:1"], "alternative_group_refs": [], "alternative_policy_ref": None, "reason": "Python is demonstrated.", "missing": []}]},
            input_quality={}, cache_key="sha256:qualification",
        )
        db.add(qualification)
        db.flush()

        create_preference_revision(
            db,
            owner=owner,
            expected_revision=0,
            artifact=UserPreferences(
                desired_skills=[DesiredValue(value="Python", importance="high")]
            ),
        )
        create_eligibility_revision(
            db,
            owner=owner,
            expected_revision=0,
            artifact=CandidateEligibilityFacts(),
        )

        first = create_or_get_match_result(db, owner=owner, qualification_public_id="qa_phase5", preference_revision=1, eligibility_revision=1, legacy_adapter_enabled=True)
        second = create_or_get_match_result(db, owner=owner, qualification_public_id="qa_phase5", preference_revision=1, eligibility_revision=1, legacy_adapter_enabled=True)

        assert second.id == first.id
        assert first.score_artifact["qualification_score"] == 100
        assert first.score_artifact["overall_score"] == 100
        assert first.score_artifact["preference_score"] == 100
        assert first.score_artifact["recommendation"] == "strong_match"
        assert first.legacy_score == 10
        assert first.explanation_artifact["strengths"][0]["key"] == "req_python"
