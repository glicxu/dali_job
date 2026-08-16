from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.accounts.models import User
from app.modules.evaluation import repository as evaluation_repository
from app.modules.evaluation.benchmark import build_admission_report
from app.modules.evaluation.catalog import build_fixture_catalog
from app.modules.evaluation.job_profile_batch import prepare_evaluation_job
from app.modules.evaluation.models import EvaluationRun
from app.modules.evaluation.router import _source_company, get_job_snapshot_fetcher
from app.modules.matching_v2.extraction import JobExtractionResult as ProfileExtractionResult
from app.modules.matching_v2.router import (
    get_candidate_profile_extractor,
    get_job_profile_extractor,
    get_qualification_matcher,
)
from app.modules.resume_job_match.job_url_import import JobExtractionResult as WebExtractionResult
from tests.test_matching_v2_candidate_profiles import StubCandidateExtractor
from tests.test_matching_v2_qualification import StubQualificationMatcher, _job_artifact


class EvaluationJobExtractor:
    def extract(self, spans):
        return ProfileExtractionResult(
            artifact=_job_artifact(spans[0].span_id),
            model_id="gpt-4.1-mini",
            provider_execution_reference="provider-evaluation-job-test-1",
        )


def test_evaluation_job_sources_supply_employer_when_extractor_omits_it() -> None:
    assert _source_company("https://amazon.jobs/en/jobs/10487991") == "Amazon"
    assert _source_company("https://www.google.com/about/careers/applications/jobs/results/123-role") == "Google"
    assert _source_company("https://jobs.apple.com/en-us/details/123/role") == "Apple"
    assert _source_company("https://apply.careers.microsoft.com/careers/job/123") == "Microsoft"
    assert _source_company("https://nvidia.wd5.myworkdayjobs.com/job/role") == "NVIDIA"
    assert _source_company("https://job-boards.greenhouse.io/cloudflare/jobs/123") == "Cloudflare"
    assert _source_company("https://intel.wd1.myworkdayjobs.com/External/job/role/123") == "Intel"
    assert _source_company("https://jobs.lever.co/palantir/123") == "Palantir"
    assert _source_company("https://job-boards.greenhouse.io/another-company/jobs/123") == ""
    assert _source_company("https://example.com/jobs/123") == ""


def test_company_job_source_registry_is_machine_readable_and_excludes_aggregators() -> None:
    registry_path = (
        Path(__file__).parents[1]
        / "app"
        / "modules"
        / "evaluation"
        / "company_job_sources.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["schema_version"] == 2
    assert registry["policy"]["aggregators_allowed"] is False
    assert {item["index_id"] for item in registry["index_sources"]} == {
        "sp_500", "nasdaq_100",
    }
    assert len(registry["companies"]) >= 20
    assert len({item["company_id"] for item in registry["companies"]}) == len(
        registry["companies"]
    )
    assert all(item["discovery_urls"] for item in registry["companies"])
    assert all(item["expected_detail_hosts"] for item in registry["companies"])
    assert all(item["ats_family"] for item in registry["companies"])
    assert sum(item["e3_enabled"] is True for item in registry["companies"]) >= 20
    assert {
        "workday", "custom", "phenom", "eightfold", "greenhouse", "lever"
    } <= {item["ats_family"] for item in registry["companies"]}
    serialized = json.dumps(registry).lower()
    assert "indeed.com" not in serialized
    assert "linkedin.com" not in serialized
    assert "glassdoor.com" not in serialized


def test_e3_collection_manifest_has_balanced_one_hundred_job_targets() -> None:
    manifest_path = (
        Path(__file__).parents[1]
        / "app"
        / "modules"
        / "evaluation"
        / "e3_collection_manifest.v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["benchmark_release"] == "matching-benchmark-jobs.e3.v1"
    assert manifest["target_job_count"] == 100
    assert sum(manifest["role_family_targets"].values()) == 100
    assert sum(manifest["level_targets"].values()) == 100
    assert sum(manifest["description_quality_targets"].values()) == 100
    assert manifest["employer_coverage"]["minimum_distinct_employers"] >= 20
    assert manifest["employer_coverage"]["maximum_jobs_per_employer"] <= 6
    assert manifest["ats_coverage"]["minimum_distinct_families"] >= 6
    assert manifest["admission"]["official_employer_or_employer_controlled_ats_only"] is True


def test_e3_job_profile_batch_prepares_only_accepted_unchanged_snapshots() -> None:
    raw_text = "Requirements\n- Five years building Python services.\nResponsibilities\n- Ship APIs."
    snapshot = SimpleNamespace(
        review_status="accepted",
        jobs_cache_id=17,
        raw_description_text=raw_text,
    )
    cached_job = SimpleNamespace(deleted_at=None, raw_description_text=raw_text)
    db = Mock()
    db.get.return_value = cached_job

    prepared = prepare_evaluation_job(db, snapshot)
    assert prepared.canonical_text == raw_text
    assert len(prepared.spans) >= 2

    snapshot.review_status = "draft"
    try:
        prepare_evaluation_job(db, snapshot)
    except ValueError as exc:
        assert "accepted" in str(exc)
    else:
        raise AssertionError("A draft snapshot must not enter Job Profile extraction.")


def test_e3_admission_report_enforces_manifest_slices() -> None:
    evaluation_dir = Path(__file__).parents[1] / "app" / "modules" / "evaluation"
    manifest = json.loads(
        (evaluation_dir / "e3_collection_manifest.v1.json").read_text(encoding="utf-8")
    )
    roles = [
        code
        for code, count in manifest["role_family_targets"].items()
        for _ in range(count)
    ]
    levels = [
        code for code, count in manifest["level_targets"].items() for _ in range(count)
    ]
    qualities = [
        code
        for code, count in manifest["description_quality_targets"].items()
        for _ in range(count)
    ]
    ats_families = manifest["ats_coverage"]["families_available"]
    snapshots = [
        SimpleNamespace(
            public_id=f"ejs_e3_{index:03d}",
            benchmark_release=manifest["benchmark_release"],
            review_status="accepted",
            coverage_slot=roles[index],
            company=f"Employer {index % 20:02d}",
            capture_metadata={
                "ats_family": ats_families[index % len(ats_families)],
                "level_band": levels[index],
                "description_quality": qualities[index],
            },
        )
        for index in range(100)
    ]
    report = build_admission_report(
        snapshots,
        benchmark_release=manifest["benchmark_release"],
    )
    assert report["ready"] is True
    assert report["accepted_count"] == 100
    assert not report["missing_slots"]
    assert not report["balance_violations"]


def test_synthetic_candidate_fixture_release_has_required_coverage_and_no_contact_channels() -> None:
    fixture_path = (
        Path(__file__).parents[1]
        / "app"
        / "modules"
        / "evaluation"
        / "candidate_fixtures.v1.json"
    )
    release = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixtures = release["fixtures"]
    assert release["fixture_release"] == "candidate-fixtures.synthetic.v1"
    assert release["contains_personal_data"] is False
    assert 8 <= len(fixtures) <= 12
    assert len({item["fixture_id"] for item in fixtures}) == len(fixtures)
    stages = {item["coverage"]["career_stage"] for item in fixtures}
    assert {"entry", "mid", "senior", "manager", "principal"} <= stages
    serialized = json.dumps(release).lower()
    assert "@" not in serialized
    assert "linkedin" not in serialized


def test_pair_manifest_has_three_pre_labeled_pairs_for_every_pilot_slot() -> None:
    evaluation_dir = Path(__file__).parents[1] / "app" / "modules" / "evaluation"
    release = json.loads((evaluation_dir / "candidate_fixtures.v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((evaluation_dir / "pair_manifest.v1.json").read_text(encoding="utf-8"))
    fixture_ids = {item["fixture_id"] for item in release["fixtures"]}
    expected_slots = {
        "software_backend", "software_infrastructure", "software_mobile", "ml_data",
        "hardware_design", "embedded_firmware", "product_management", "technical_program",
        "engineering_management", "principal_architecture",
    }
    assert manifest["benchmark_release"] == "matching-benchmark-jobs.v1"
    assert manifest["candidate_fixture_release"] == release["fixture_release"]
    assert len(manifest["pairs"]) == 30
    assert len({item["pair_id"] for item in manifest["pairs"]}) == 30
    assert {item["coverage_slot"] for item in manifest["pairs"]} == expected_slots
    assert {item["candidate_fixture_id"] for item in manifest["pairs"]} <= fixture_ids
    for slot in expected_slots:
        pairs = [item for item in manifest["pairs"] if item["coverage_slot"] == slot]
        assert {item["expectation"] for item in pairs} == {
            "strong", "adjacent_or_incomplete", "mismatch",
        }


def test_fixture_catalog_resolves_manual_candidate_and_job_selection() -> None:
    profile = SimpleNamespace(
        id=42,
        title="[EVAL synthetic.v1] cand_backend_mid_01: Backend candidate",
    )
    snapshot = SimpleNamespace(
        public_id="ejs_backend",
        benchmark_release="matching-benchmark-jobs.v1",
        coverage_slot="software_backend",
        review_status="accepted",
    )
    catalog = build_fixture_catalog([profile], [snapshot])
    candidate = next(
        item for item in catalog["candidates"] if item["fixture_id"] == "cand_backend_mid_01"
    )
    assert candidate["resume_profile_id"] == 42
    assert candidate["loaded"] is True
    backend_pairs = [
        item for item in catalog["pairs"] if item["coverage_slot"] == "software_backend"
    ]
    assert len(backend_pairs) == 3
    assert {item["job_snapshot_id"] for item in backend_pairs} == {"ejs_backend"}
    assert next(item for item in backend_pairs if item["candidate_fixture_id"] == "cand_backend_mid_01")[
        "available"
    ] is True


def test_initial_expected_score_matrix_is_complete_and_consistent_with_pair_labels() -> None:
    evaluation_dir = Path(__file__).parents[1] / "app" / "modules" / "evaluation"
    fixtures = json.loads((evaluation_dir / "candidate_fixtures.v1.json").read_text(encoding="utf-8"))
    pairs = json.loads((evaluation_dir / "pair_manifest.v1.json").read_text(encoding="utf-8"))
    matrix = json.loads(
        (evaluation_dir / "expected_score_matrix.v1.json").read_text(encoding="utf-8")
    )
    fixture_ids = {item["fixture_id"] for item in fixtures["fixtures"]}
    candidate_codes = {item["code"]: item["fixture_id"] for item in matrix["candidates"]}
    assert set(candidate_codes.values()) == fixture_ids
    assert len(matrix["jobs"]) == 10
    assert sum(len(job["initial_scores"]) for job in matrix["jobs"]) == 110
    jobs_by_slot = {job["coverage_slot"]: job for job in matrix["jobs"]}
    assert len(jobs_by_slot) == 10
    scores_by_pair: dict[tuple[str, str], int] = {}
    for job in matrix["jobs"]:
        assert set(job["initial_scores"]) == set(candidate_codes)
        assert set(job["expected_ranges"]) == set(candidate_codes)
        for code, score in job["initial_scores"].items():
            expected_min, expected_max = job["expected_ranges"][code]
            assert 0 <= expected_min <= score <= expected_max <= 100
            scores_by_pair[(job["coverage_slot"], candidate_codes[code])] = score
    for pair in pairs["pairs"]:
        score = scores_by_pair[(pair["coverage_slot"], pair["candidate_fixture_id"])]
        if pair["expectation"] == "strong":
            assert score >= 80
        elif pair["expectation"] == "mismatch":
            assert score <= 35


def test_agent_score_sample_has_two_pairs_per_band_and_results_for_every_attempt() -> None:
    evaluation_dir = Path(__file__).parents[1] / "app" / "modules" / "evaluation"
    sample = json.loads(
        (evaluation_dir / "agent_score_sample.v1.json").read_text(encoding="utf-8")
    )
    results = json.loads(
        (evaluation_dir / "agent_score_sample_results.v1.json").read_text(encoding="utf-8")
    )
    band_counts: dict[str, int] = {}
    for pair in sample["pairs"]:
        band_counts[pair["band"]] = band_counts.get(pair["band"], 0) + 1
    assert len(band_counts) == 5
    assert set(band_counts.values()) == {2}
    sample_ids = {item["sample_id"] for item in sample["pairs"]}
    result_ids = {item["sample_id"] for item in results["results"]}
    assert result_ids == sample_ids
    assert results["summary"] == {
        "attempted": 10,
        "completed": 2,
        "failed_validation": 8,
        "numeric_agent_scores_returned": 0,
    }
    assert all(item["agent_score"] is None for item in results["results"])


def _fetched_job(_: str) -> WebExtractionResult:
    return WebExtractionResult(
        source_url="https://example.com/jobs/quality-1",
        canonical_url="https://example.com/jobs/quality-1",
        title="Senior Software Engineer",
        company="Tier One Co",
        location="Seattle, WA",
        sections={"requirements": ["Production Python experience"]},
        focused_text=(
            "Senior Software Engineer\n\nRequirements\nProduction Python experience\n"
            "TypeScript, JavaScript, or a comparable language"
        ),
        raw_visible_text=None,
        extraction_method="test-fixture",
        confidence=0.99,
        warnings=[],
        extractor_version="test.v1",
    )


def test_admin_can_capture_and_inspect_a_repeatable_three_stage_run(caplog) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
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

    app = create_app()
    app.state.runtime = replace(
        app.state.runtime,
        matching_v2=replace(app.state.runtime.matching_v2, evaluation_enabled=True),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_job_snapshot_fetcher] = lambda: _fetched_job
    app.dependency_overrides[get_candidate_profile_extractor] = lambda: StubCandidateExtractor()
    app.dependency_overrides[get_job_profile_extractor] = lambda: EvaluationJobExtractor()
    app.dependency_overrides[get_qualification_matcher] = lambda: StubQualificationMatcher()
    client = TestClient(app)

    resume = client.post("/api/v1/resume-profiles", json={
        "title": "Evaluation Candidate",
        "resume_data": {
            "headline": "Software Engineer",
            "summary": "Contact job@candidate.example or 415-555-1212. Builds production Python services.",
            "experience": ["Delivered APIs used by customers."],
            "skills": ["Python"],
        },
    })
    assert resume.status_code == 200

    captured = client.post("/api/v1/internal/evaluation/job-snapshots/import", json={
        "source_url": "https://example.com/jobs/quality-1",
        "benchmark_release": "matching-benchmark-jobs.v1",
        "coverage_slot": "software_backend",
    })
    assert captured.status_code == 200
    assert captured.json()["source_hash"].startswith("sha256:")
    assert captured.json()["review_status"] == "draft"
    admission_before = client.get("/api/v1/internal/evaluation/admission-report")
    assert "software_backend" in admission_before.json()["awaiting_review_slots"]

    accepted = client.post(
        f"/api/v1/internal/evaluation/job-snapshots/{captured.json()['public_id']}/review",
        json={"review_status": "accepted", "review_notes": "Official and complete test fixture."},
    )
    assert accepted.status_code == 200
    assert accepted.json()["review_status"] == "accepted"
    admission_after = client.get("/api/v1/internal/evaluation/admission-report")
    assert admission_after.status_code == 200
    assert admission_after.json()["slots"][0]["status"] == "filled"

    candidate_sources = client.get("/api/v1/internal/evaluation/candidate-sources")
    assert candidate_sources.status_code == 200
    assert candidate_sources.json()["candidates"] == [{
        "resume_profile_id": resume.json()["id"],
        "label": "Evaluation Candidate",
        "fixture_group": "account",
        "candidate_profile_id": None,
        "profile_created_at": None,
    }]
    candidate_stage = client.post(
        f"/api/v1/internal/evaluation/candidate-sources/{resume.json()['id']}/profile"
    )
    assert candidate_stage.status_code == 200, candidate_stage.text
    candidate_stage_body = candidate_stage.json()
    assert candidate_stage_body["resume_title"] == "Evaluation Candidate"
    assert candidate_stage_body["resume_source"]["spans"]
    assert candidate_stage_body["candidate_profile"]["candidate_profile_id"].startswith("cp_")
    assert candidate_stage_body["annotation_targets"]
    assert candidate_stage_body["reviews"] == []
    candidate_profile_id = candidate_stage_body["candidate_profile"]["candidate_profile_id"]
    candidate_review = client.post(
        f"/api/v1/internal/evaluation/candidate-profiles/{candidate_profile_id}/reviews",
        json={
            "overall_score": 88,
            "confidence": 0.9,
            "rationale": "Accurate profile with a small date-normalization issue.",
        },
    )
    assert candidate_review.status_code == 200, candidate_review.text
    assert candidate_review.json()["stage"] == "candidate_profile"
    assert candidate_review.json()["artifact_id"] == candidate_profile_id
    candidate_stage_reloaded = client.post(
        f"/api/v1/internal/evaluation/candidate-sources/{resume.json()['id']}/profile"
    )
    assert [item["overall_score"] for item in candidate_stage_reloaded.json()["reviews"]] == [88]

    job_stage = client.post(
        f"/api/v1/internal/evaluation/job-snapshots/{captured.json()['public_id']}/profile"
    )
    assert job_stage.status_code == 200, job_stage.text
    job_stage_body = job_stage.json()
    assert job_stage_body["job_source"]["spans"]
    assert job_stage_body["job_profile"]["job_profile_id"].startswith("jp_")
    assert job_stage_body["annotation_targets"]
    assert job_stage_body["reviews"] == []
    job_profile_id = job_stage_body["job_profile"]["job_profile_id"]
    job_review = client.post(
        f"/api/v1/internal/evaluation/job-profiles/{job_profile_id}/reviews",
        json={
            "overall_score": 92,
            "confidence": 1,
            "rationale": "Requirements and job context are faithfully extracted.",
        },
    )
    assert job_review.status_code == 200, job_review.text
    assert job_review.json()["stage"] == "job_profile"
    assert job_review.json()["artifact_id"] == job_profile_id
    job_stage_reloaded = client.post(
        f"/api/v1/internal/evaluation/job-snapshots/{captured.json()['public_id']}/profile"
    )
    assert [item["overall_score"] for item in job_stage_reloaded.json()["reviews"]] == [92]

    run = client.post("/api/v1/internal/evaluation/runs", json={
        "job_snapshot_id": captured.json()["public_id"],
        "resume_profile_id": resume.json()["id"],
    })
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["run_metadata"]["score_generated"] is False
    assert body["manifest"]["evaluation_run_id"] == body["public_id"]
    assert body["manifest"]["candidate_fixture_release"] == "candidate-fixtures.local.v1"
    assert all(metric["passed"] for metric in body["metrics"]["contract_metrics"])
    assert body["resume_source"]["spans"]
    assert body["job_source"]["spans"]
    assert body["candidate_profile"]["candidate_profile_id"].startswith("cp_")
    assert body["job_profile"]["job_profile_id"].startswith("jp_")
    assert len(body["qualification"]["assessment"]["requirement_assessments"]) == 2
    assert "hard_constraint_assessments" not in body["qualification"]["assessment"]
    assert any(target["stage"] == "candidate_profile" for target in body["annotation_targets"])
    assert any(target["stage"] == "job_profile" for target in body["annotation_targets"])
    assert body["match_review"] == {
        "state": "review_pending",
        "independent_reviewer_count": 0,
        "reviews": [],
        "adjudicated_review": None,
    }

    fetched = client.get(f"/api/v1/internal/evaluation/runs/{body['public_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body
    assert len(client.get("/api/v1/internal/evaluation/job-snapshots").json()["snapshots"]) == 1
    assert len(client.get("/api/v1/internal/evaluation/runs").json()["runs"]) == 1

    requirement_id = body["qualification"]["assessment"]["requirement_assessments"][0]["requirement_id"]
    review = client.post(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}/annotations",
        json={
            "stage": "qualification",
            "target_ref": requirement_id,
            "review_kind": "adjudication",
            "verdict": "correct",
            "evidence_support": "supported",
            "expected_value": {"status": "met"},
            "confidence": 1.0,
            "severity": "none",
            "comment": "The cited Python evidence supports the requirement.",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["public_id"].startswith("eva_")

    match_review = client.post(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}/match-reviews",
        json={
            "review_kind": "independent",
            "overall_score": 82,
            "confidence": 0.75,
            "rationale": "Strong direct experience with one material scope gap.",
        },
    )
    assert match_review.status_code == 200, match_review.text
    assert match_review.json()["public_id"].startswith("evm_")
    assert match_review.json()["recommendation"] == "good_match"
    premature_adjudication = client.post(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}/match-reviews",
        json={
            "review_kind": "adjudication",
            "overall_score": 80,
            "confidence": 1,
            "rationale": "Golden score.",
        },
    )
    assert premature_adjudication.status_code == 409

    metrics = client.get(f"/api/v1/internal/evaluation/runs/{body['public_id']}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["adjudicated_count"] == 1
    assert metrics.json()["positive_evidence_support_precision"] == 1.0
    assert metrics.json()["qualification_confusion_matrix"] == {"met": {"met": 1}}

    aggregate = client.get("/api/v1/internal/evaluation/metrics")
    assert aggregate.status_code == 200
    assert aggregate.json()["run_count"] == 1
    assert aggregate.json()["contract_pass_counts"]["exact_requirement_coverage"] == {
        "passed": 1,
        "total": 1,
    }

    repeated = client.post("/api/v1/internal/evaluation/runs", json={
        "job_snapshot_id": captured.json()["public_id"],
        "resume_profile_id": resume.json()["id"],
    })
    assert repeated.status_code == 200
    comparison = client.get("/api/v1/internal/evaluation/comparisons", params={
        "baseline_run_id": body["public_id"],
        "candidate_run_id": repeated.json()["public_id"],
    })
    assert comparison.status_code == 200
    assert comparison.json()["comparable"] is True
    assert comparison.json()["qualification_changes"] == []

    invalid_target = client.post(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}/annotations",
        json={
            "stage": "qualification",
            "target_ref": "unknown-requirement",
            "verdict": "incorrect",
        },
    )
    assert invalid_target.status_code == 422

    candidate_target = next(
        target for target in body["annotation_targets"] if target["stage"] == "candidate_profile"
    )
    candidate_review = client.post(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}/annotations",
        json={
            "stage": "candidate_profile",
            "target_ref": candidate_target["target_ref"],
            "verdict": "correct",
            "evidence_support": "supported",
        },
    )
    assert candidate_review.status_code == 200

    corpus_json = client.get("/api/v1/internal/evaluation/exports/corpus?format=json")
    assert corpus_json.status_code == 200
    assert corpus_json.json()["privacy"]["candidate_source_redacted"] is True
    exported_text = corpus_json.text
    assert "job@candidate.example" not in exported_text
    assert "415-555-1212" not in exported_text
    assert "[REDACTED_EMAIL]" in exported_text
    corpus_markdown = client.get("/api/v1/internal/evaluation/exports/corpus?format=markdown")
    assert corpus_markdown.status_code == 200
    assert "Matching Evaluation Corpus Export" in corpus_markdown.text
    with session_factory.begin() as session:
        persisted_run = session.scalar(select(EvaluationRun).where(EvaluationRun.public_id == body["public_id"]))
        assert persisted_run is not None
        second_reviewer = User(
            email="second-reviewer@dalifin.local",
            display_name="Second Reviewer",
            role="admin",
            auth_provider="dalijob",
        )
        session.add(second_reviewer)
        session.flush()
        evaluation_repository.create_annotation(
            session,
            run=persisted_run,
            reviewer_user_id=second_reviewer.id,
            stage="candidate_profile",
            target_ref=candidate_target["target_ref"],
            review_kind="independent",
            verdict="incorrect",
            evidence_support="unsupported",
            expected_value=None,
            confidence=0.9,
            severity="major",
            error_taxonomy_code="candidate.unsupported_fact",
            comment="The source does not support this fact.",
        )
        evaluation_repository.create_match_review(
            session,
            run=persisted_run,
            reviewer_user_id=second_reviewer.id,
            review_kind="independent",
            overall_score=76,
            confidence=0.9,
            rationale="Good match with meaningful missing evidence.",
        )
        adjudicator = User(
            email="match-adjudicator@dalifin.local",
            display_name="Match Adjudicator",
            role="admin",
            auth_provider="dalijob",
        )
        session.add(adjudicator)
        session.flush()
        evaluation_repository.create_match_review(
            session,
            run=persisted_run,
            reviewer_user_id=adjudicator.id,
            review_kind="adjudication",
            overall_score=79,
            confidence=1,
            rationale="Adjudicated from both independent reviews.",
        )
    queue = client.get("/api/v1/internal/evaluation/adjudication-queue")
    assert queue.status_code == 200
    assert queue.json()["items"][0]["status"] == "pending"

    adjudicated = client.post(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}/annotations",
        json={
            "stage": "candidate_profile",
            "target_ref": candidate_target["target_ref"],
            "review_kind": "adjudication",
            "verdict": "correct",
            "evidence_support": "supported",
            "expected_value": {"verdict": "correct"},
        },
    )
    assert adjudicated.status_code == 200
    assert client.get("/api/v1/internal/evaluation/adjudication-queue").json()["items"][0]["status"] == "resolved"
    reviewed_run = client.get(f"/api/v1/internal/evaluation/runs/{body['public_id']}").json()
    assert reviewed_run["match_review"]["state"] == "adjudicated"
    assert reviewed_run["match_review"]["independent_reviewer_count"] == 2
    assert reviewed_run["match_review"]["adjudicated_review"]["overall_score"] == 79
    blind_run = client.get(
        f"/api/v1/internal/evaluation/runs/{body['public_id']}?blind=true"
    ).json()
    assert len(blind_run["annotations"]) < len(reviewed_run["annotations"])
    assert blind_run["match_review"]["independent_reviewer_count"] == 1
    assert all(
        item["reviewer_label"] != "second-reviewer@dalifin.local"
        for item in blind_run["match_review"]["reviews"]
    )
    assert "job@candidate.example" not in caplog.text
    assert "415-555-1212" not in caplog.text
    assert "TypeScript, JavaScript, or a comparable language" not in caplog.text


def test_evaluation_routes_are_hidden_by_default() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, future=True)

    def override_db():
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    response = client.get("/api/v1/internal/evaluation/job-snapshots")

    assert response.status_code == 404
