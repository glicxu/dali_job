from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.automation.executor import DatabaseAutomationResultPersister
from app.modules.automation.models import NotificationDelivery, SearchRun, UsageLedger
from app.modules.automation.v2_executor import CachedV2AutomationExecutor
from app.modules.automation.worker import WorkItem, run_one
from app.modules.jobs.models import JobCache, JobResumeMatch
from app.modules.matching_v2.extraction import CandidateExtractionResult
from app.modules.matching_v2.models import JobProfileVersion, MatchResult, QualificationAssessment
from app.modules.matching_v2.qualification import QualificationResult
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    SpanInput,
    create_or_get_canonical_source,
    create_or_get_job_profile,
)
from app.modules.matching_v2.schemas import QualificationAssessmentResponse
from tests.test_automation_worker import NOW, _queued_run
from tests.test_matching_v2_qualification import _candidate_artifact, _job_artifact


class CandidateExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, spans):
        self.calls += 1
        artifact = _candidate_artifact(spans[0].span_id).model_copy(
            update={"recommended_primary_career_profile_ref": "career_software"}
        )
        return CandidateExtractionResult(
            artifact=artifact,
            model_id="gpt-5.6-luna",
            provider_execution_reference="candidate-v2-test",
        )


class QualificationMatcher:
    def __init__(self) -> None:
        self.calls = 0

    def assess(self, qualification_input):
        self.calls += 1
        evidence_ref = next(iter(qualification_input.allowed_evidence_refs))
        return QualificationResult(
            artifact=QualificationAssessmentResponse.model_validate({
                "requirement_assessments": [
                    {
                        "requirement_id": requirement["requirement_id"],
                        "status": "met",
                        "confidence": 0.95,
                        "evidence_refs": [evidence_ref],
                        "alternative_group_refs": [],
                        "alternative_policy_ref": None,
                        "reason": "Candidate evidence supports this requirement.",
                        "missing": [],
                    }
                    for requirement in qualification_input.job_requirements
                ]
            }),
            model_id="gpt-5.6-luna",
            provider_execution_reference="qualification-v2-test",
        )


def _factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _catalog_job(factory) -> int:
    text = "Requirements\n- Production Python experience\n- TypeScript or comparable language"
    source_ref = "scheduled_catalog:requirements:0001"
    with factory() as db:
        cache = JobCache(
            title="Senior Software Engineer",
            company="Catalog Co",
            source_url="https://example.com/jobs/scheduled-v2",
            source_url_hash="scheduled-v2-cache-hash",
            raw_description_text=text,
            job_data={
                "title": "Senior Software Engineer",
                "company": "Catalog Co",
                "summary": "Build production Python services.",
            },
            lifecycle_state="active",
            last_seen_at=NOW,
            expires_at=NOW + timedelta(days=30),
        )
        db.add(cache)
        db.flush()
        source = create_or_get_canonical_source(
            db,
            owner=ArtifactOwner.shared(),
            source_type="job",
            canonical_text=text,
            text_extraction_version="test.v1",
            canonicalization_version="canonical-text.v1",
            spans=[SpanInput(
                span_id=source_ref,
                section="requirements",
                start_utf8_byte=0,
                end_utf8_byte=len(text.encode("utf-8")),
                excerpt=text,
            )],
        )
        profile = create_or_get_job_profile(
            db,
            source=source,
            artifact=_job_artifact(source_ref),
            model_id="gpt-5.6-luna",
            jobs_cache_id=cache.id,
        )
        profile.trial_eligible = True
        profile.quality_tier = "curated_evaluation"
        db.commit()
        return cache.id


def test_v2_automation_uses_active_profiled_catalog_and_projects_notification() -> None:
    factory = _factory()
    run_id, _operation_id, ledger_id, _schedule_id = _queued_run(factory)
    cache_id = _catalog_job(factory)
    candidate_extractor = CandidateExtractor()
    matcher = QualificationMatcher()
    executor = CachedV2AutomationExecutor(
        session_factory=factory,
        candidate_extractor=candidate_extractor,
        matcher=matcher,
        model_id="gpt-5.6-luna",
        legacy_adapter_enabled=True,
    )

    outcome = run_one(
        factory,
        executor,
        worker_id="v2-automation-worker",
        lease_seconds=60,
        now=NOW,
        persister=DatabaseAutomationResultPersister(),
    )

    assert outcome.status == "succeeded"
    assert candidate_extractor.calls == 1
    assert matcher.calls == 1
    with factory() as db:
        run = db.get(SearchRun, run_id)
        projection = db.query(JobResumeMatch).one()
        assert run.jobs_discovered == 1
        assert run.jobs_new == 0
        assert run.jobs_matched == 1
        assert run.matches_notified == 1
        assert projection.jobs_cache_id == cache_id
        assert projection.matching_v2_result_id is not None
        assert projection.match_data["pipeline"] == "matching_v2"
        assert db.get(MatchResult, projection.matching_v2_result_id) is not None
        assert db.query(QualificationAssessment).count() == 1
        assert db.query(JobProfileVersion).count() == 1
        assert db.query(NotificationDelivery).count() == 2
        ledger = db.get(UsageLedger, ledger_id)
        assert ledger.state == "consumed"
        repeated_item = WorkItem(
            run_id=999,
            operation_id=999,
            schedule_id=run.schedule_id,
            workspace_id=run.workspace_id,
            user_id=run.user_id,
            attempt_count=1,
            max_attempts=3,
            request_payload={},
            keyword="Backend Engineer",
            location="Remote",
            resume_profile_id=projection.resume_profile_id,
            resume_data_snapshot=projection.resume_data_snapshot,
            minimum_match_score=7,
            max_results=10,
        )

    repeated = executor.execute(repeated_item, lambda: None)
    assert repeated.artifacts == ()
    assert matcher.calls == 1


def test_v2_automation_excludes_expired_catalog_jobs() -> None:
    factory = _factory()
    _run_id, _operation_id, ledger_id, _schedule_id = _queued_run(factory, max_attempts=1)
    cache_id = _catalog_job(factory)
    with factory() as db:
        cache = db.get(JobCache, cache_id)
        cache.lifecycle_state = "expired"
        cache.expires_at = NOW - timedelta(seconds=1)
        db.commit()
    executor = CachedV2AutomationExecutor(
        session_factory=factory,
        candidate_extractor=CandidateExtractor(),
        matcher=QualificationMatcher(),
        model_id="gpt-5.6-luna",
        legacy_adapter_enabled=True,
    )

    outcome = run_one(
        factory,
        executor,
        worker_id="v2-automation-worker",
        lease_seconds=60,
        now=NOW,
        persister=DatabaseAutomationResultPersister(),
    )

    assert outcome.status == "failed"
    with factory() as db:
        ledger = db.get(UsageLedger, ledger_id)
        assert ledger.state == "released"
        assert db.query(JobResumeMatch).count() == 0
