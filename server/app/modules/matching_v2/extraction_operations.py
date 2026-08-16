from __future__ import annotations

import socket
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.matching_v2.canonical import EvidenceSpan
from app.modules.matching_v2.extraction import (
    CandidateProfileExtractor,
    JobProfileExtractor,
    cleanup_job_spans,
    validate_job_extraction,
)
from app.modules.matching_v2.models import CanonicalSource, MatchingOperation, SourceSpan
from app.modules.matching_v2.orchestration import (
    OperationLeaseUnavailable,
    begin_stage,
    claim_operation,
    complete_operation,
    complete_stage,
    fail_stage,
    first_incomplete_stage,
)
from app.modules.matching_v2.repositories import (
    create_or_get_candidate_profile,
    create_or_get_job_profile,
    find_cached_candidate_profile,
    find_cached_job_profile,
)


def execute_extraction_operation(
    db: Session,
    operation: MatchingOperation,
    *,
    candidate_extractor: CandidateProfileExtractor | None = None,
    job_extractor: JobProfileExtractor | None = None,
) -> None:
    lease_owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
    try:
        claim_operation(db, operation, lease_owner=lease_owner)
    except OperationLeaseUnavailable:
        return
    stage = first_incomplete_stage(db, operation.id)
    if stage is None:
        return
    payload = dict(operation.request_payload)
    try:
        begin_stage(
            db,
            operation,
            stage,
            input_artifact_ids={"canonical_source_id": payload["canonical_source_id"]},
        )
        source = db.get(CanonicalSource, payload["canonical_source_id"])
        if source is None:
            raise ValueError("Canonical source is unavailable.")
        spans = _spans(db, source.id)
        if operation.operation_type == "candidate_profile_extraction":
            if candidate_extractor is None:
                raise RuntimeError("Candidate Profile extractor is unavailable.")
            profile = find_cached_candidate_profile(db, source=source, model_id=payload["model_id"])
            cache_hit = profile is not None
            if profile is None:
                result = candidate_extractor.extract(spans)
                profile = create_or_get_candidate_profile(
                    db,
                    source=source,
                    artifact=result.artifact,
                    model_id=result.model_id,
                    provider_execution_reference=result.provider_execution_reference,
                    resume_profile_id=payload["resume_profile_id"],
                )
            output_id = profile.public_id
            policies = {"prompt": profile.prompt_version, "schema": profile.schema_version}
        elif operation.operation_type == "job_profile_extraction":
            if job_extractor is None:
                raise RuntimeError("Job Profile extractor is unavailable.")
            profile = find_cached_job_profile(db, source=source, model_id=payload["model_id"])
            cache_hit = profile is not None
            if profile is None:
                cleanup = cleanup_job_spans(spans)
                result = job_extractor.extract(list(cleanup.kept_spans))
                artifact = validate_job_extraction(
                    result.artifact,
                    {item.span_id for item in cleanup.kept_spans},
                    duplicate_spans_removed=cleanup.duplicate_spans_removed,
                    boilerplate_spans_ignored=cleanup.boilerplate_spans_ignored,
                    omitted_span_count=len(result.omitted_span_ids),
                )
                profile = create_or_get_job_profile(
                    db,
                    source=source,
                    artifact=artifact,
                    model_id=result.model_id,
                    jobs_cache_id=payload["jobs_cache_id"],
                    provider_execution_reference=result.provider_execution_reference,
                )
            output_id = profile.public_id
            policies = {"prompt": profile.prompt_version, "schema": profile.schema_version}
        else:
            raise ValueError("Unsupported extraction operation type.")
        complete_stage(
            db,
            operation,
            stage,
            output_artifact_id=output_id,
            cache_hit=cache_hit,
            provider_usage={"availability": "provider_adapter_does_not_expose_usage"},
            policy_versions=policies,
        )
        complete_operation(db, operation)
    except Exception:
        db.rollback()
        operation = db.get(MatchingOperation, operation.id)
        stage = first_incomplete_stage(db, operation.id) if operation is not None else None
        if operation is not None and stage is not None:
            fail_stage(
                db,
                operation,
                stage,
                error_code="EXTRACTION_FAILED",
                error_message="Profile extraction failed and may be retried.",
            )


def _spans(db: Session, source_id: int) -> list[EvidenceSpan]:
    rows = list(db.scalars(select(SourceSpan).where(
        SourceSpan.canonical_source_id == source_id
    ).order_by(SourceSpan.ordinal)).all())
    return [EvidenceSpan(
        span_id=row.span_id,
        section=row.section,
        start_utf8_byte=row.start_utf8_byte,
        end_utf8_byte=row.end_utf8_byte,
        excerpt=row.excerpt,
    ) for row in rows]
