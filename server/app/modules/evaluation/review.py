from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import User
from app.modules.evaluation.models import EvaluationAnnotation, EvaluationRun
from app.modules.matching_v2.models import CandidateProfileVersion, JobProfileVersion, JobRequirement


def artifact_annotation_targets(
    db: Session,
    *,
    candidate: CandidateProfileVersion | None = None,
    job_profile: JobProfileVersion | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    if candidate is not None:
        candidate_artifact = candidate.artifact
        candidate_labels = {
            "skills": "Skill",
            "experience": "Experience",
            "projects": "Project",
            "education": "Education",
            "certifications": "Certification",
            "publications": "Publication",
            "career_profiles": "Career profile",
        }
        for collection, label in candidate_labels.items():
            values = candidate_artifact.get(collection, [])
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                refs = value.get("evidence_refs", []) if isinstance(value, dict) else []
                targets.append({
                    "stage": "candidate_profile",
                    "target_ref": f"candidate_profile:{collection}:{index}",
                    "label": f"{label} {index + 1}",
                    "value": value,
                    "evidence_refs": refs,
                })
        targets.append({
            "stage": "candidate_profile",
            "target_ref": "candidate_profile:derived",
            "label": "Derived summary and target roles",
            "value": candidate_artifact.get("derived", {}),
            "evidence_refs": [],
        })

    if job_profile is None:
        return targets
    requirements = list(db.scalars(select(JobRequirement).where(
        JobRequirement.job_profile_version_id == job_profile.id
    ).order_by(JobRequirement.id)).all())
    for requirement in requirements:
        targets.append({
            "stage": "job_profile",
            "target_ref": f"job_profile:requirement:{requirement.requirement_id}",
            "label": requirement.statement,
            "value": {
                "importance": requirement.importance,
                "scoring_dimension": requirement.scoring_dimension,
                "hard_constraint": requirement.hard_constraint,
                "minimum_years": requirement.minimum_years,
                "explicit_alternatives": requirement.explicit_alternatives,
            },
            "evidence_refs": requirement.source_refs,
        })
    job_artifact = job_profile.artifact
    for key, label in (
        ("career_context", "Job career context"),
        ("location", "Job location"),
        ("compensation", "Compensation"),
        ("application_constraints", "Application constraints"),
    ):
        value = job_artifact.get(key, {})
        refs = value.get("evidence_refs", []) if isinstance(value, dict) else []
        targets.append({
            "stage": "job_profile",
            "target_ref": f"job_profile:{key}",
            "label": label,
            "value": value,
            "evidence_refs": refs,
        })
    for index, value in enumerate(job_artifact.get("responsibilities", [])):
        targets.append({
            "stage": "job_profile",
            "target_ref": f"job_profile:responsibility:{index}",
            "label": f"Responsibility {index + 1}",
            "value": value,
            "evidence_refs": value.get("source_refs", []),
        })
    return targets


def build_disagreement_queue(db: Session, *, workspace_id: int) -> list[dict[str, Any]]:
    runs = list(db.scalars(select(EvaluationRun).where(
        EvaluationRun.workspace_id == workspace_id
    )).all())
    if not runs:
        return []
    annotations = list(db.scalars(select(EvaluationAnnotation).where(
        EvaluationAnnotation.evaluation_run_id.in_([run.id for run in runs])
    ).order_by(EvaluationAnnotation.created_at, EvaluationAnnotation.id)).all())
    run_by_id = {run.id: run for run in runs}
    latest_independent: dict[tuple[int, str, str, int], EvaluationAnnotation] = {}
    adjudications: dict[tuple[int, str, str], EvaluationAnnotation] = {}
    for item in annotations:
        target_key = (item.evaluation_run_id, item.stage, item.target_ref)
        if item.review_kind == "adjudication":
            adjudications[target_key] = item
        else:
            latest_independent[(*target_key, item.reviewer_user_id)] = item
    grouped: dict[tuple[int, str, str], list[EvaluationAnnotation]] = defaultdict(list)
    for key, item in latest_independent.items():
        grouped[key[:3]].append(item)
    queue = []
    for key, reviews in grouped.items():
        if len(reviews) < 2:
            continue
        decisions = {
            (item.verdict, item.evidence_support, str(item.expected_value)) for item in reviews
        }
        if len(decisions) < 2:
            continue
        run = run_by_id[key[0]]
        adjudication = adjudications.get(key)
        queue.append({
            "run_id": run.public_id,
            "stage": key[1],
            "target_ref": key[2],
            "status": "resolved" if adjudication is not None else "pending",
            "reviews": [_review_summary(db, item) for item in reviews],
            "adjudication": _review_summary(db, adjudication) if adjudication is not None else None,
        })
    return sorted(queue, key=lambda item: (item["status"], item["run_id"], item["stage"], item["target_ref"]))


def _review_summary(db: Session, annotation: EvaluationAnnotation) -> dict[str, Any]:
    reviewer = db.get(User, annotation.reviewer_user_id)
    return {
        "annotation_id": annotation.public_id,
        "reviewer_label": reviewer.email if reviewer is not None else f"user:{annotation.reviewer_user_id}",
        "verdict": annotation.verdict,
        "evidence_support": annotation.evidence_support,
        "expected_value": annotation.expected_value,
        "severity": annotation.severity,
        "comment": annotation.comment,
    }
