from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.matching_v2.canonical import EvidenceSpan, build_evidence_spans, canonicalize_text
from app.modules.matching_v2.extraction import (
    CandidateExtractionResult,
    select_candidate_model_spans,
    validate_candidate_extraction,
)
from app.modules.matching_v2.router import get_candidate_profile_extractor
from app.modules.matching_v2.schemas import CandidateExtractionResponse


def _artifact(evidence_ref: str, *, confidence: float = 0.86, level: str = "entry"):
    return CandidateExtractionResponse.model_validate(
        {
            "skills": [
                {
                    "observed_name": "Python",
                    "canonical_name": "Python",
                    "evidence_strength": "demonstrated",
                    "last_used": None,
                    "months_experience": None,
                    "evidence_refs": [evidence_ref],
                }
            ],
            "experience": [],
            "projects": [],
            "education": [],
            "certifications": [],
            "publications": [],
            "career_profiles": [
                {
                    "local_ref": "career_software_engineering",
                    "role_family": "software_engineering",
                    "track": "individual_contributor",
                    "level": level,
                    "confidence": confidence,
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
            "quality": {"warnings": [], "completeness": 0.8},
        }
    )


class StubCandidateExtractor:
    def __init__(self) -> None:
        self.calls = 0
        self.last_spans: list[EvidenceSpan] = []

    def extract(self, spans: list[EvidenceSpan]) -> CandidateExtractionResult:
        self.calls += 1
        self.last_spans = spans
        return CandidateExtractionResult(
            artifact=_artifact(spans[-1].span_id),
            model_id="gpt-5.6-luna",
            provider_execution_reference="provider-test-1",
        )


def test_canonicalization_and_spans_preserve_utf8_offsets() -> None:
    canonical = canonicalize_text("SUMMARY\r\nBuilt cafe\u0301 systems.\x00\r\n\r\nSKILLS\r- Python\r")
    spans = build_evidence_spans(canonical, source_prefix="Resume 42")

    assert canonical == "SUMMARY\nBuilt café systems.\n\nSKILLS\n- Python\n"
    assert [span.section for span in spans] == ["summary", "summary", "skills", "skills"]
    assert spans[-1].span_id == "resume_42:skills:0002"
    encoded = canonical.encode("utf-8")
    for span in spans:
        assert encoded[span.start_utf8_byte : span.end_utf8_byte].decode("utf-8") == span.excerpt


def test_span_builder_bounds_long_paragraphs_without_changing_excerpts() -> None:
    canonical = canonicalize_text("Summary\n" + ("evidence " * 80).strip())
    spans = build_evidence_spans(canonical, source_prefix="resume", max_span_chars=120)

    assert len(spans) > 2
    assert all(len(span.excerpt) <= 120 for span in spans)
    assert all(span.excerpt == span.excerpt.strip() for span in spans)


def test_model_span_selection_prioritizes_qualification_sections() -> None:
    spans = [
        EvidenceSpan("r:general:1", "general", 0, 10, "g" * 10),
        EvidenceSpan("r:experience:1", "experience", 10, 20, "e" * 10),
        EvidenceSpan("r:skills:1", "skills", 20, 30, "s" * 10),
    ]

    selected, omitted = select_candidate_model_spans(spans, maximum_bytes=20)

    assert [span.section for span in selected] == ["experience", "skills"]
    assert [span.section for span in omitted] == ["general"]


def test_low_confidence_candidate_level_becomes_unknown() -> None:
    artifact = _artifact("resume:experience:1", confidence=0.69, level="senior")

    validated = validate_candidate_extraction(artifact, {"resume:experience:1"})

    assert validated.career_profiles[0].level == "unknown"
    assert validated.career_profiles[0].confidence == 0.69


def test_candidate_profile_api_creates_caches_reads_and_revises_selection() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

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

    extractor = StubCandidateExtractor()
    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, shadow_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_candidate_profile_extractor] = lambda: extractor
    client = TestClient(app)

    resume = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Candidate Resume",
            "is_default": True,
            "resume_data": {
                "headline": "Software Engineer",
                "summary": "Builds Python services.",
                "experience": ["Delivered a production API."],
                "skills": ["Python"],
                "target_roles": ["Software Engineer"],
            },
        },
    )
    assert resume.status_code == 200
    resume_id = resume.json()["id"]

    first = client.post(f"/api/v1/resumes/{resume_id}/candidate-profile")
    second = client.post(f"/api/v1/resumes/{resume_id}/candidate-profile")

    assert first.status_code == 202
    assert second.status_code == 200
    assert extractor.calls == 1
    operation = client.get(f"/api/v1/matching-operations/{first.json()['operation_id']}")
    assert operation.json()["status"] == "completed"
    assert operation.json()["operation_type"] == "candidate_profile_extraction"
    body = second.json()
    assert body["candidate_profile_id"].startswith("cp_")
    assert body["source"]["source_hash"].startswith("sha256:")
    assert body["extracted"]["skills"][0]["observed_name"] == "Python"
    assert body["selection"]["revision"] == 1
    assert body["generation"]["provider_execution_reference"] == "provider-test-1"
    candidate_profile_id = body["candidate_profile_id"]
    career_profile_id = body["career_profiles"][0]["career_profile_id"]

    fetched = client.get(f"/api/v1/candidate-profiles/{candidate_profile_id}")
    assert fetched.status_code == 200
    assert fetched.json()["candidate_profile_id"] == candidate_profile_id

    unchanged = client.post(
        f"/api/v1/candidate-profiles/{candidate_profile_id}/regenerate"
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["candidate_profile_id"] == candidate_profile_id

    corrected_resume = client.patch(
        f"/api/v1/resume-profiles/{resume_id}",
        json={
            "resume_data": {
                "headline": "Software Engineer",
                "summary": "Builds Python services and reliable distributed systems.",
                "experience": ["Delivered a production API and led its reliability improvements."],
                "skills": ["Python", "Distributed Systems"],
                "target_roles": ["Software Engineer"],
            }
        },
    )
    assert corrected_resume.status_code == 200
    regenerated = client.post(
        f"/api/v1/candidate-profiles/{candidate_profile_id}/regenerate"
    )
    assert regenerated.status_code == 202
    regenerated_view = client.post(
        f"/api/v1/candidate-profiles/{candidate_profile_id}/regenerate"
    )
    assert regenerated_view.status_code == 200
    assert regenerated_view.json()["candidate_profile_id"] != candidate_profile_id
    assert extractor.calls == 2

    selected = client.put(
        f"/api/v1/candidate-profiles/{candidate_profile_id}/primary-career-profile",
        json={
            "expected_revision": 1,
            "primary_career_profile_id": career_profile_id,
        },
    )
    assert selected.status_code == 200
    assert selected.json()["selection"] == {
        "revision": 2,
        "primary_career_profile_id": career_profile_id,
        "selection_source": "user_confirmed",
    }

    stale = client.put(
        f"/api/v1/candidate-profiles/{candidate_profile_id}/primary-career-profile",
        json={
            "expected_revision": 1,
            "primary_career_profile_id": career_profile_id,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "CAREER_SELECTION_REVISION_CONFLICT"


def test_candidate_profile_api_is_hidden_when_v2_flags_are_disabled() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        with session_factory() as session:
            yield session

    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(
            app.state.runtime.matching_v2,
            shadow_enabled=False,
            internal_super_enabled=False,
        ),
    )
    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    response = client.post("/api/v1/resumes/1/candidate-profile")

    assert response.status_code == 404


def test_candidate_extraction_operation_retries_without_exposing_provider_error() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_db():
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    extractor = StubCandidateExtractor()
    original_extract = extractor.extract

    def fail_once(spans):
        if extractor.calls == 0:
            extractor.calls += 1
            raise TimeoutError("private provider timeout payload")
        return original_extract(spans)

    extractor.extract = fail_once
    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, shadow_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_candidate_profile_extractor] = lambda: extractor
    client = TestClient(app)
    resume = client.post("/api/v1/resume-profiles", json={
        "title": "Retry Resume",
        "is_default": True,
        "resume_data": {"headline": "Software Engineer", "skills": ["Python"]},
    })

    queued = client.post(f"/api/v1/resumes/{resume.json()['id']}/candidate-profile")
    failed = client.get(f"/api/v1/matching-operations/{queued.json()['operation_id']}")
    retried = client.post(f"/api/v1/matching-operations/{queued.json()['operation_id']}/retry")
    completed = client.get(f"/api/v1/matching-operations/{queued.json()['operation_id']}")

    assert queued.status_code == 202
    assert failed.json()["status"] == "retryable_failure"
    assert "private provider" not in failed.text
    assert retried.status_code == 202
    assert completed.json()["status"] == "completed"
    assert completed.json()["stages"][0]["attempt_count"] == 2
