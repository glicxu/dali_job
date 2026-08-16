from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.evaluation import repository
from app.modules.evaluation.metrics import calculate_run_metrics
from app.modules.evaluation.models import EvaluationJobSnapshot, EvaluationRun
from app.modules.evaluation.privacy import redact_candidate_text, redact_value, sensitive_categories
from app.modules.matching_v2.models import (
    CandidateProfileVersion,
    CanonicalSource,
    JobProfileVersion,
    QualificationAssessment,
)


def build_corpus_export(db: Session, runs: list[EvaluationRun], *, benchmark_release: str | None) -> dict:
    exported_runs = []
    for run in runs:
        snapshot = db.get(EvaluationJobSnapshot, run.job_snapshot_id)
        candidate = db.get(CandidateProfileVersion, run.candidate_profile_version_id)
        job = db.get(JobProfileVersion, run.job_profile_version_id)
        qualification = db.get(QualificationAssessment, run.qualification_assessment_id)
        if snapshot is None or candidate is None or job is None or qualification is None:
            continue
        candidate_source = db.get(CanonicalSource, candidate.canonical_source_id)
        job_source = db.get(CanonicalSource, job.canonical_source_id)
        if candidate_source is None or job_source is None:
            continue
        redacted_source = redact_candidate_text(candidate_source.canonical_text)
        leaked = sensitive_categories(redacted_source)
        if leaked:
            raise ValueError(f"Candidate export redaction failed: {','.join(leaked)}")
        exported_runs.append({
            "run_id": run.public_id,
            "manifest": run.manifest,
            "job_snapshot": {
                "public_id": snapshot.public_id,
                "coverage_slot": snapshot.coverage_slot,
                "source_url": snapshot.source_url,
                "source_hash": snapshot.source_hash,
                "title": snapshot.title,
                "company": snapshot.company,
                "source_text": job_source.canonical_text,
            },
            "candidate_fixture": {
                "source_hash": candidate_source.source_hash,
                "source_text_redacted": redacted_source,
                "profile": redact_value(candidate.artifact),
            },
            "job_profile": job.artifact,
            "qualification": qualification.artifact,
            "annotations": [redact_value({
                "stage": item.stage,
                "target_ref": item.target_ref,
                "review_kind": item.review_kind,
                "verdict": item.verdict,
                "evidence_support": item.evidence_support,
                "expected_value": item.expected_value,
                "severity": item.severity,
                "error_taxonomy_code": item.error_taxonomy_code,
                "comment": item.comment,
            }) for item in repository.list_annotations(db, run_id=run.id)],
            "metrics": calculate_run_metrics(db, run).model_dump(mode="json"),
        })
    return {
        "schema_version": "matching-evaluation-corpus.v1",
        "benchmark_release": benchmark_release,
        "privacy": {
            "candidate_source_redacted": True,
            "redaction_version": "evaluation-redaction.v1",
            "complete_job_text_internal_only": True,
        },
        "run_count": len(exported_runs),
        "runs": exported_runs,
    }


def corpus_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Matching Evaluation Corpus Export",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Benchmark release: `{payload['benchmark_release'] or 'all'}`",
        f"- Runs: {payload['run_count']}",
        "- Candidate source text: redacted",
        "- Job source text: complete internal-testing snapshot",
    ]
    for run in payload["runs"]:
        lines.extend([
            "",
            f"## Run `{run['run_id']}`",
            "",
            f"- Job: {run['job_snapshot']['company']} — {run['job_snapshot']['title']}",
            f"- Coverage slot: `{run['job_snapshot']['coverage_slot']}`",
            f"- Candidate source hash: `{run['candidate_fixture']['source_hash']}`",
            f"- Reviews: {len(run['annotations'])}",
            "",
            "### Contract metrics",
            "",
        ])
        for metric in run["metrics"]["contract_metrics"]:
            lines.append(
                f"- {'PASS' if metric['passed'] else 'FAIL'} — {metric['name']}: "
                f"{metric['numerator']}/{metric['denominator']}"
            )
    return "\n".join(lines) + "\n"
