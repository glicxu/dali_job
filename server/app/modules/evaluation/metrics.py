from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evaluation.models import EvaluationAnnotation, EvaluationRun
from app.modules.evaluation.schemas import (
    ContractMetricView,
    EvaluationAggregateMetricsView,
    EvaluationComparisonView,
    EvaluationMetricsView,
)
from app.modules.matching_v2.models import (
    CandidateProfileVersion,
    CanonicalSource,
    JobProfileVersion,
    JobRequirement,
    QualificationAssessment,
    RequirementAssessment,
    SourceSpan,
)

POSITIVE_STATUSES = {"met", "met_by_alternative", "partially_met"}


def _collect_refs(value: Any, keys: set[str]) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in keys and isinstance(nested, list):
                refs.extend(str(item) for item in nested)
            else:
                refs.extend(_collect_refs(nested, keys))
    elif isinstance(value, list):
        for nested in value:
            refs.extend(_collect_refs(nested, keys))
    return refs


def _contains_score(value: Any) -> bool:
    if isinstance(value, dict):
        return any("score" in key.lower() or _contains_score(nested) for key, nested in value.items())
    if isinstance(value, list):
        return any(_contains_score(item) for item in value)
    return False


def calculate_run_metrics(db: Session, run: EvaluationRun) -> EvaluationMetricsView:
    candidate = db.get(CandidateProfileVersion, run.candidate_profile_version_id)
    job = db.get(JobProfileVersion, run.job_profile_version_id)
    qualification = db.get(QualificationAssessment, run.qualification_assessment_id)
    if candidate is None or job is None or qualification is None:
        raise ValueError("Evaluation artifacts are unavailable.")
    candidate_source = db.get(CanonicalSource, candidate.canonical_source_id)
    job_source = db.get(CanonicalSource, job.canonical_source_id)
    if candidate_source is None or job_source is None:
        raise ValueError("Evaluation sources are unavailable.")
    candidate_span_ids = set(db.scalars(select(SourceSpan.span_id).where(
        SourceSpan.canonical_source_id == candidate_source.id
    )).all())
    job_span_ids = set(db.scalars(select(SourceSpan.span_id).where(
        SourceSpan.canonical_source_id == job_source.id
    )).all())
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job.id
    )).all())
    assessments = list(db.scalars(select(RequirementAssessment).where(
        RequirementAssessment.qualification_assessment_id == qualification.id
    )).all())

    candidate_refs = _collect_refs(candidate.artifact, {"evidence_refs"})
    job_refs = _collect_refs(job.artifact, {"source_refs", "evidence_refs"})
    qualification_refs = [str(ref) for item in assessments for ref in item.evidence_refs]
    invalid_refs = sorted(
        {ref for ref in candidate_refs + qualification_refs if ref not in candidate_span_ids}
        | {ref for ref in job_refs if ref not in job_span_ids}
    )
    expected_ids = {item.requirement_id for item in requirements}
    assessed_ids = {item.requirement_id for item in assessments}
    missing_ids = sorted(expected_ids - assessed_ids)
    extra_ids = sorted(assessed_ids - expected_ids)
    manifest = run.manifest or {}
    required_manifest_keys = {
        "evaluation_run_id", "benchmark_release", "candidate_fixture_release",
        "job_fixture_release", "candidate_prompt_version", "job_prompt_version",
        "qualification_prompt_version", "schema_versions", "taxonomy_version",
        "selection_policy_version", "qualification_policy_version", "model_ids",
        "provider_configuration_hash", "started_at", "completed_at",
    }
    missing_manifest = sorted(key for key in required_manifest_keys if not manifest.get(key))
    score_paths_present = _contains_score(candidate.artifact) or _contains_score(job.artifact) or _contains_score(
        qualification.artifact
    )
    contract_metrics = [
        ContractMetricView(
            name="evidence_reference_validity",
            passed=not invalid_refs,
            numerator=len(candidate_refs) + len(job_refs) + len(qualification_refs) - len(invalid_refs),
            denominator=len(candidate_refs) + len(job_refs) + len(qualification_refs),
            details=invalid_refs,
        ),
        ContractMetricView(
            name="exact_requirement_coverage",
            passed=not missing_ids and not extra_ids,
            numerator=len(expected_ids & assessed_ids),
            denominator=len(expected_ids),
            details=[*(f"missing:{item}" for item in missing_ids), *(f"extra:{item}" for item in extra_ids)],
        ),
        ContractMetricView(
            name="manifest_version_completeness",
            passed=not missing_manifest,
            numerator=len(required_manifest_keys) - len(missing_manifest),
            denominator=len(required_manifest_keys),
            details=missing_manifest,
        ),
        ContractMetricView(
            name="score_separated_from_stage_artifacts",
            passed=not score_paths_present and run.run_metadata.get("score_generated") is True,
            numerator=int(not score_paths_present and run.run_metadata.get("score_generated") is True),
            denominator=1,
            details=[] if not score_paths_present else ["score-like key found in a generated artifact"],
        ),
    ]
    annotations = list(db.scalars(select(EvaluationAnnotation).where(
        EvaluationAnnotation.evaluation_run_id == run.id
    )).all())
    adjudicated = [item for item in annotations if item.review_kind == "adjudication"]
    actual_by_requirement = {item.requirement_id: item.status for item in assessments}
    positive_reviews = [
        item for item in adjudicated
        if actual_by_requirement.get(item.target_ref) in POSITIVE_STATUSES
        and item.evidence_support != "not_reviewed"
    ]
    supported = sum(
        item.evidence_support in {"supported", "partially_supported"} for item in positive_reviews
    )
    status_counts = Counter(item.status for item in assessments)
    confusion: dict[str, Counter] = {}
    for annotation in adjudicated:
        expected_status = (annotation.expected_value or {}).get("status")
        actual_status = actual_by_requirement.get(annotation.target_ref)
        if isinstance(expected_status, str) and actual_status is not None:
            confusion.setdefault(expected_status, Counter())[actual_status] += 1
    return EvaluationMetricsView(
        run_id=run.public_id,
        contract_metrics=contract_metrics,
        qualification_status_counts=dict(sorted(status_counts.items())),
        annotation_count=len(annotations),
        adjudicated_count=len(adjudicated),
        positive_evidence_support_precision=(supported / len(positive_reviews) if positive_reviews else None),
        positive_evidence_support_counts={"supported": supported, "reviewed": len(positive_reviews)},
        qualification_confusion_matrix={
            expected: dict(sorted(actual.items())) for expected, actual in sorted(confusion.items())
        },
    )


def calculate_aggregate_metrics(
    db: Session,
    runs: list[EvaluationRun],
    *,
    benchmark_release: str | None,
) -> EvaluationAggregateMetricsView:
    metrics = [calculate_run_metrics(db, run) for run in runs]
    contract_counts: dict[str, dict[str, int]] = {}
    status_counts: Counter = Counter()
    supported = 0
    reviewed = 0
    for item in metrics:
        status_counts.update(item.qualification_status_counts)
        supported += item.positive_evidence_support_counts["supported"]
        reviewed += item.positive_evidence_support_counts["reviewed"]
        for metric in item.contract_metrics:
            counts = contract_counts.setdefault(metric.name, {"passed": 0, "total": 0})
            counts["total"] += 1
            counts["passed"] += int(metric.passed)
    annotations = list(db.scalars(select(EvaluationAnnotation).where(
        EvaluationAnnotation.evaluation_run_id.in_([run.id for run in runs])
    )).all()) if runs else []
    return EvaluationAggregateMetricsView(
        benchmark_release=benchmark_release,
        run_count=len(runs),
        contract_pass_counts=contract_counts,
        qualification_status_counts=dict(sorted(status_counts.items())),
        annotation_count=len(annotations),
        adjudicated_count=sum(item.review_kind == "adjudication" for item in annotations),
        severe_error_count=sum(item.severity == "severe" for item in annotations),
        positive_evidence_support_precision=(supported / reviewed if reviewed else None),
        positive_evidence_support_counts={"supported": supported, "reviewed": reviewed},
    )


def compare_runs(db: Session, baseline: EvaluationRun, candidate: EvaluationRun) -> EvaluationComparisonView:
    base_candidate = db.get(CandidateProfileVersion, baseline.candidate_profile_version_id)
    next_candidate = db.get(CandidateProfileVersion, candidate.candidate_profile_version_id)
    base_job = db.get(JobProfileVersion, baseline.job_profile_version_id)
    next_job = db.get(JobProfileVersion, candidate.job_profile_version_id)
    base_qualification = db.get(QualificationAssessment, baseline.qualification_assessment_id)
    next_qualification = db.get(QualificationAssessment, candidate.qualification_assessment_id)
    if any(item is None for item in (
        base_candidate, next_candidate, base_job, next_job, base_qualification, next_qualification
    )):
        raise ValueError("Comparison artifacts are unavailable.")
    assert base_candidate is not None and next_candidate is not None
    assert base_job is not None and next_job is not None
    assert base_qualification is not None and next_qualification is not None

    incompatibilities: list[str] = []
    if baseline.job_snapshot_id != candidate.job_snapshot_id:
        incompatibilities.append("job_snapshot_changed")
    base_source = db.get(CanonicalSource, base_candidate.canonical_source_id)
    next_source = db.get(CanonicalSource, next_candidate.canonical_source_id)
    if base_source is None or next_source is None or base_source.source_hash != next_source.source_hash:
        incompatibilities.append("candidate_source_changed")
    for key in ("benchmark_release", "candidate_fixture_release", "job_fixture_release"):
        if baseline.manifest.get(key) != candidate.manifest.get(key):
            incompatibilities.append(f"{key}_changed")

    manifest_differences = {}
    for key in sorted(set(baseline.manifest) | set(candidate.manifest)):
        if baseline.manifest.get(key) != candidate.manifest.get(key):
            manifest_differences[key] = {
                "baseline": baseline.manifest.get(key),
                "candidate": candidate.manifest.get(key),
            }
    base_items = {
        item.requirement_id: item for item in db.scalars(select(RequirementAssessment).where(
            RequirementAssessment.qualification_assessment_id == base_qualification.id
        )).all()
    }
    next_items = {
        item.requirement_id: item for item in db.scalars(select(RequirementAssessment).where(
            RequirementAssessment.qualification_assessment_id == next_qualification.id
        )).all()
    }
    changes = []
    for requirement_id in sorted(set(base_items) | set(next_items)):
        before = base_items.get(requirement_id)
        after = next_items.get(requirement_id)
        before_value = None if before is None else {
            "status": before.status, "confidence": before.confidence,
            "evidence_refs": before.evidence_refs, "reason": before.reason, "missing": before.missing,
        }
        after_value = None if after is None else {
            "status": after.status, "confidence": after.confidence,
            "evidence_refs": after.evidence_refs, "reason": after.reason, "missing": after.missing,
        }
        if before_value != after_value:
            changes.append({"requirement_id": requirement_id, "baseline": before_value, "candidate": after_value})
    return EvaluationComparisonView(
        baseline_run_id=baseline.public_id,
        candidate_run_id=candidate.public_id,
        comparable=not incompatibilities,
        incompatibilities=incompatibilities,
        manifest_differences=manifest_differences,
        qualification_changes=changes,
        candidate_profile_changed=base_candidate.artifact != next_candidate.artifact,
        job_profile_changed=base_job.artifact != next_job.artifact,
    )
