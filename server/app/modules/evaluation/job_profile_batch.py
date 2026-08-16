from __future__ import annotations

from dataclasses import dataclass
import hashlib

from sqlalchemy.orm import Session

from app.modules.evaluation.models import EvaluationJobSnapshot
from app.modules.jobs.models import JobCache
from app.modules.matching_v2.canonical import (
    CANONICALIZATION_VERSION,
    EvidenceSpan,
    build_evidence_spans,
    canonicalize_text,
)
from app.modules.matching_v2.extraction import (
    JobProfileExtractor,
    cleanup_job_spans,
    validate_job_extraction,
)
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    SpanInput,
    create_or_get_canonical_source,
    create_or_get_job_profile,
    find_cached_job_profile,
    sync_policy_registry,
)


@dataclass(frozen=True)
class PreparedEvaluationJob:
    snapshot: EvaluationJobSnapshot
    cached_job: JobCache
    canonical_text: str
    spans: tuple[EvidenceSpan, ...]


def prepare_evaluation_job(db: Session, snapshot: EvaluationJobSnapshot) -> PreparedEvaluationJob:
    if snapshot.review_status != "accepted":
        raise ValueError("Only accepted evaluation snapshots can produce Job Profiles.")
    cached_job = db.get(JobCache, snapshot.jobs_cache_id)
    if cached_job is None or cached_job.deleted_at is not None:
        raise ValueError("The evaluation snapshot's cached job is unavailable.")
    canonical_text = canonicalize_text(snapshot.raw_description_text)
    if canonical_text != canonicalize_text(cached_job.raw_description_text):
        raise ValueError("The frozen snapshot and cached job descriptions differ.")
    content_prefix = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()[:16]
    spans = tuple(build_evidence_spans(canonical_text, source_prefix=f"job_{content_prefix}"))
    if not spans:
        raise ValueError("The job description does not contain usable evidence spans.")
    return PreparedEvaluationJob(
        snapshot=snapshot,
        cached_job=cached_job,
        canonical_text=canonical_text,
        spans=spans,
    )


def extract_and_persist_job_profile(
    db: Session,
    prepared: PreparedEvaluationJob,
    *,
    extractor: JobProfileExtractor,
    model_id: str,
) -> dict[str, object]:
    source = create_or_get_canonical_source(
        db,
        owner=ArtifactOwner.shared(),
        source_type="job",
        canonical_text=prepared.canonical_text,
        text_extraction_version="jobs-cache-raw-description.v1",
        canonicalization_version=CANONICALIZATION_VERSION,
        spans=[
            SpanInput(
                span_id=span.span_id,
                section=span.section,
                start_utf8_byte=span.start_utf8_byte,
                end_utf8_byte=span.end_utf8_byte,
                excerpt=span.excerpt,
            )
            for span in prepared.spans
        ],
    )
    sync_policy_registry(db)
    profile = find_cached_job_profile(db, source=source, model_id=model_id)
    if profile is not None:
        profile.trial_eligible = True
        profile.quality_tier = "curated_evaluation"
        return {
            "status": "cached",
            "job_profile_id": profile.public_id,
            "canonical_source_id": source.public_id,
            "model": profile.model_id,
        }

    cleanup = cleanup_job_spans(list(prepared.spans))
    result = extractor.extract(list(cleanup.kept_spans))
    artifact = validate_job_extraction(
        result.artifact,
        {span.span_id for span in cleanup.kept_spans},
        duplicate_spans_removed=cleanup.duplicate_spans_removed,
        boilerplate_spans_ignored=cleanup.boilerplate_spans_ignored,
        omitted_span_count=len(result.omitted_span_ids),
    )
    profile = create_or_get_job_profile(
        db,
        source=source,
        artifact=artifact,
        model_id=result.model_id,
        jobs_cache_id=prepared.cached_job.id,
        provider_execution_reference=result.provider_execution_reference,
    )
    profile.trial_eligible = True
    profile.quality_tier = "curated_evaluation"
    return {
        "status": "created",
        "job_profile_id": profile.public_id,
        "canonical_source_id": source.public_id,
        "model": profile.model_id,
        "provider_execution_reference": result.provider_execution_reference,
        "repair_attempted": result.repair_attempted,
        "repair_count": result.repair_count,
        "requirement_count": len(artifact.requirements),
        "responsibility_count": len(artifact.responsibilities),
    }
