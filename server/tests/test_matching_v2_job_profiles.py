from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.jobs.models import JobCache
from app.modules.jobs.repository import source_url_hash
from app.modules.matching_v2.canonical import EvidenceSpan, build_evidence_spans, canonicalize_text
from app.modules.matching_v2.extraction import (
    JobExtractionResult,
    assign_alternative_policies,
    cleanup_job_spans,
    select_job_model_spans,
    validate_job_extraction,
)
from app.modules.matching_v2.router import get_job_profile_extractor
from app.modules.matching_v2.schemas import JobExtractionResponse


def _artifact(source_ref: str, *, duplicate_requirement: bool = False) -> JobExtractionResponse:
    requirements = [
        {
            "local_ref": "python_required",
            "category": "skill",
            "scoring_dimension": "technical_skill",
            "statement": "Production Python experience",
            "importance": "required",
            "acceptable_evidence_contexts": ["professional", "open_source"],
            "minimum_years": None,
            "alternative_groups": [],
            "policy_alternative_group": None,
            "source_refs": [source_ref],
        }
    ]
    if duplicate_requirement:
        requirements.append({**requirements[0], "local_ref": "python_required_duplicate"})
    return JobExtractionResponse.model_validate(
        {
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
            "employment_type": "unknown",
            "career_context": {
                "primary_role_family": "software_engineering",
                "adjacent_role_families": [],
                "track": "individual_contributor",
                "target_level": "senior",
                "acceptable_level_range": {"minimum": "mid", "maximum": "senior"},
                "level_source": "explicit",
                "confidence": 0.9,
                "evidence_refs": [source_ref],
            },
            "compensation": {
                "currency": None,
                "period": "unknown",
                "minimum": None,
                "maximum": None,
                "is_employer_provided": False,
            },
            "requirements": requirements,
            "responsibilities": [{"statement": "Build APIs", "source_refs": [source_ref]}],
            "application_constraints": {
                "work_authorization": "unknown",
                "sponsorship_available": "unknown",
                "travel_percent": None,
                "clearance": None,
            },
            "cleanup": {
                "duplicate_spans_removed": 99,
                "boilerplate_spans_ignored": 99,
                "warnings": [],
            },
        }
    )


class StubJobExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, spans: list[EvidenceSpan]) -> JobExtractionResult:
        self.calls += 1
        return JobExtractionResult(
            artifact=_artifact(spans[0].span_id, duplicate_requirement=True),
            model_id="gpt-5.6-luna",
            provider_execution_reference="provider-job-test-1",
        )


def test_job_cleanup_removes_exact_duplicate_and_known_boilerplate() -> None:
    canonical = canonicalize_text(
        "Requirements\n- Production Python experience\n- Production Python experience\n\n"
        "We are an equal opportunity employer.\n"
    )
    spans = build_evidence_spans(canonical, source_prefix="job_1")

    cleanup = cleanup_job_spans(spans)

    assert cleanup.duplicate_spans_removed == 1
    assert cleanup.boilerplate_spans_ignored == 1
    assert sum("Production Python" in span.excerpt for span in cleanup.kept_spans) == 1


def test_job_validator_merges_duplicate_requirements_without_extra_weight() -> None:
    artifact = _artifact("job:requirements:1", duplicate_requirement=True)

    validated = validate_job_extraction(artifact, {"job:requirements:1"})

    assert len(validated.requirements) == 1
    assert validated.requirements[0].local_ref == "python_required"
    assert validated.cleanup.duplicate_spans_removed == 0


def test_server_assigns_only_registered_explicit_alternative_policies() -> None:
    language_artifact = _artifact("job:requirements:1")
    language_requirement = language_artifact.requirements[0].model_copy(
        update={"alternative_groups": [{
            "local_ref": "language_options",
            "any_of": ["Python", "Java"],
            "source_refs": ["job:requirements:1"],
        }]}
    )
    language_artifact = language_artifact.model_copy(
        update={"requirements": [language_requirement]}
    )
    degree_artifact = _artifact("job:requirements:1")
    degree_requirement = degree_artifact.requirements[0].model_copy(
        update={"alternative_groups": [{
            "local_ref": "degree_options",
            "any_of": ["degree", "equivalent experience"],
            "source_refs": ["job:requirements:1"],
        }]}
    )
    degree_artifact = degree_artifact.model_copy(update={"requirements": [degree_requirement]})

    assigned_language = assign_alternative_policies(language_artifact)
    assigned_degree = assign_alternative_policies(degree_artifact)

    assert (
        assigned_language.requirements[0].policy_alternative_group
        == "general-purpose-programming-language.v2"
    )
    assert assigned_degree.requirements[0].policy_alternative_group is None


def test_job_input_limit_is_explicitly_reported() -> None:
    spans = [
        EvidenceSpan("job:requirements:1", "requirements", 0, 2, "aa"),
        EvidenceSpan("job:general:1", "general", 2, 4, "bb"),
    ]
    selected, omitted = select_job_model_spans(spans, maximum_bytes=2)
    artifact = _artifact(selected[0].span_id)

    validated = validate_job_extraction(
        artifact,
        {selected[0].span_id},
        omitted_span_count=len(omitted),
    )

    assert validated.cleanup.warnings == ["NEEDS_MORE_INFORMATION:MODEL_INPUT_OMITTED_SPANS:1"]


def test_job_profile_api_creates_reuses_and_reads_shared_profile() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    raw_text = (
        "Senior Software Engineer\n\nRequirements\n- Production Python experience\n"
        "- Production Python experience\n\nResponsibilities\n- Build APIs\n\n"
        "We are an equal opportunity employer."
    )
    source_url = "https://example.com/jobs/123"
    second_source_url = "https://careers.example.com/jobs/duplicate-123"
    with session_factory.begin() as session:
        for cached_source_url in (source_url, second_source_url):
            session.add(JobCache(
                title="Senior Software Engineer",
                company="Example Co",
                source_url=cached_source_url,
                source_url_hash=source_url_hash(cached_source_url),
                raw_description_text=raw_text,
                job_data={},
            ))

    def override_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    extractor = StubJobExtractor()
    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, shadow_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_job_profile_extractor] = lambda: extractor
    client = TestClient(app)
    saved = client.post("/api/v1/jobs", json={
        "title": "Senior Software Engineer",
        "company": "Example Co",
        "source_url": source_url,
        "raw_description_text": raw_text,
        "job_data": {},
    })
    assert saved.status_code == 200

    first = client.post(f"/api/v1/jobs/{saved.json()['id']}/job-profile")
    second = client.post(f"/api/v1/jobs/{saved.json()['id']}/job-profile")

    assert first.status_code == 202, first.text
    assert second.status_code == 200
    assert extractor.calls == 1
    operation = client.get(f"/api/v1/matching-operations/{first.json()['operation_id']}")
    assert operation.json()["status"] == "completed"
    assert operation.json()["operation_type"] == "job_profile_extraction"
    body = second.json()
    assert body["job_profile_id"].startswith("jp_")
    assert body["source"]["source_hash"].startswith("sha256:")
    assert len(body["requirements"]) == 1
    assert body["requirements"][0]["requirement_id"].startswith("req_")
    assert body["extracted"]["cleanup"]["duplicate_spans_removed"] == 1
    assert body["extracted"]["cleanup"]["boilerplate_spans_ignored"] == 1
    assert body["extracted"]["application_constraints"]["work_authorization"] == "unknown"

    fetched = client.get(f"/api/v1/job-profiles/{body['job_profile_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["job_profile_id"] == body["job_profile_id"]

    duplicate_saved = client.post("/api/v1/jobs", json={
        "title": "Senior Software Engineer",
        "company": "Example Co",
        "source_url": second_source_url,
        "raw_description_text": raw_text,
        "job_data": {},
    })
    duplicate_profile = client.post(
        f"/api/v1/jobs/{duplicate_saved.json()['id']}/job-profile"
    )
    assert duplicate_profile.status_code == 200
    assert duplicate_profile.json()["job_profile_id"] == body["job_profile_id"]
    assert extractor.calls == 1
