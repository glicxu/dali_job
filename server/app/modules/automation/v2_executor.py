from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.modules.automation.executor import ExecutedCandidate
from app.modules.automation.worker import ExecutionResult, WorkItem, WorkerExecutionError
from app.modules.jobs.models import JobCache, JobResumeMatch
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.matching_v2.canonical import (
    CANONICALIZATION_VERSION,
    EvidenceSpan,
    build_evidence_spans,
    canonicalize_text,
)
from app.modules.matching_v2.extraction import CandidateProfileExtractor
from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateCareerSelection,
    CandidateProfileVersion,
    EligibilityRevision,
    JobProfileVersion,
    JobRequirement,
    MatchingIntent,
    PreferenceRevision,
)
from app.modules.matching_v2.phase5 import create_or_get_match_result
from app.modules.matching_v2.pre_match import (
    create_matching_intent,
    create_or_get_job_family_pre_match,
)
from app.modules.matching_v2.qualification import (
    QualificationMatcher,
    build_qualification_input,
    validate_qualification_assessment,
)
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    SpanInput,
    create_or_get_candidate_profile,
    create_or_get_canonical_source,
    create_or_get_qualification_assessment,
    find_cached_candidate_profile,
    find_cached_qualification_assessment,
    sync_policy_registry,
)


_WORD_RE = re.compile(r"[a-z0-9+#.]+")


class CachedV2AutomationExecutor:
    """Match a schedule against immutable, active, pre-profiled catalog jobs."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        candidate_extractor: CandidateProfileExtractor,
        matcher: QualificationMatcher,
        model_id: str,
        legacy_adapter_enabled: bool,
        maximum_catalog_profiles: int = 100,
    ) -> None:
        self._session_factory = session_factory
        self._candidate_extractor = candidate_extractor
        self._matcher = matcher
        self._model_id = model_id
        self._legacy_adapter_enabled = legacy_adapter_enabled
        self._maximum_catalog_profiles = maximum_catalog_profiles

    def execute(self, item: WorkItem, heartbeat: Callable[[], None]) -> ExecutionResult:
        heartbeat()
        try:
            with self._session_factory() as db:
                owner = ArtifactOwner.authenticated(
                    workspace_id=item.workspace_id,
                    user_id=item.user_id,
                )
                candidate = self._candidate_profile(db, item, owner)
                intent = _matching_intent(db, item, owner, candidate)
                catalog = _catalog_profiles(
                    db,
                    now=datetime.now(timezone.utc),
                    limit=self._maximum_catalog_profiles,
                )
                if not catalog:
                    raise WorkerExecutionError(
                        "cached_job_catalog_empty",
                        "No active profiled jobs are available for scheduled matching.",
                        retryable=False,
                        quota_chargeable=False,
                    )
                ranked = []
                for job_profile, cache_job in catalog:
                    pre_match = create_or_get_job_family_pre_match(
                        db,
                        owner=owner,
                        candidate_profile=candidate,
                        intent=intent,
                        job_profile=job_profile,
                    )
                    if pre_match.proceed_to_detailed_match:
                        ranked.append((pre_match, job_profile, cache_job))
                db.commit()
                ranked.sort(key=lambda row: _pre_match_rank(*row, item=item))
                discovered = len(catalog)
                if not ranked:
                    return ExecutionResult(
                        jobs_discovered=discovered,
                        result_payload={"warnings": ["No catalog job passed Job Family Pre-Match."]},
                    )

                for pre_match, job_profile, cache_job in ranked:
                    heartbeat()
                    candidate_payload = self._evaluate_pair(
                        db,
                        item=item,
                        owner=owner,
                        candidate=candidate,
                        pre_match=pre_match,
                        job_profile=job_profile,
                        cache_job=cache_job,
                    )
                    db.commit()
                    if candidate_payload is None:
                        continue
                    return ExecutionResult(
                        jobs_discovered=discovered,
                        jobs_matched=1,
                        result_payload={"pipeline": "matching_v2_cached_catalog"},
                        artifacts=(candidate_payload.model_dump(mode="json"),),
                    )
                return ExecutionResult(
                    jobs_discovered=discovered,
                    result_payload={"warnings": ["No new scored catalog match was available."]},
                )
        except WorkerExecutionError:
            raise
        except Exception as exc:
            raise WorkerExecutionError(
                "matching_v2_automation_failed",
                "Scheduled V2 matching could not be completed.",
                retryable=True,
                quota_chargeable=False,
            ) from exc

    def _candidate_profile(
        self,
        db: Session,
        item: WorkItem,
        owner: ArtifactOwner,
    ) -> CandidateProfileVersion:
        canonical_text = canonicalize_text(
            json.dumps(item.resume_data_snapshot, ensure_ascii=False, indent=2, sort_keys=True)
        )
        spans = build_evidence_spans(canonical_text, source_prefix=f"resume_{item.resume_profile_id}")
        if not spans:
            raise WorkerExecutionError(
                "candidate_profile_unavailable",
                "The scheduled resume does not contain usable evidence.",
                retryable=False,
                quota_chargeable=False,
            )
        source = create_or_get_canonical_source(
            db,
            owner=owner,
            source_type="resume",
            canonical_text=canonical_text,
            text_extraction_version="resume-profile-json.v1",
            canonicalization_version=CANONICALIZATION_VERSION,
            resume_profile_id=item.resume_profile_id,
            spans=[_span_input(span) for span in spans],
        )
        sync_policy_registry(db)
        cached = find_cached_candidate_profile(db, source=source, model_id=self._model_id)
        if cached is not None:
            return cached
        extracted = self._candidate_extractor.extract(spans)
        profile = create_or_get_candidate_profile(
            db,
            source=source,
            artifact=extracted.artifact,
            model_id=extracted.model_id,
            provider_execution_reference=extracted.provider_execution_reference,
            resume_profile_id=item.resume_profile_id,
        )
        db.commit()
        return profile

    def _evaluate_pair(
        self,
        db: Session,
        *,
        item: WorkItem,
        owner: ArtifactOwner,
        candidate: CandidateProfileVersion,
        pre_match,
        job_profile: JobProfileVersion,
        cache_job: JobCache,
    ) -> ExecutedCandidate | None:
        qualification = find_cached_qualification_assessment(
            db,
            candidate_profile=candidate,
            selection_revision=None,
            job_family_pre_match=pre_match,
            job_profile=job_profile,
            model_id=self._model_id,
        )
        provider_called = False
        if qualification is None:
            provider_called = True
            selected = (
                db.get(CandidateCareerProfile, pre_match.selected_candidate_career_profile_id)
                if pre_match.selected_candidate_career_profile_id is not None
                else None
            )
            qualification_input = build_qualification_input(
                db,
                candidate_profile=candidate,
                job_profile=job_profile,
                career_context=selected,
            )
            result = self._matcher.assess(qualification_input)
            requirements = list(
                db.scalars(
                    select(JobRequirement).where(
                        JobRequirement.job_profile_version_id == job_profile.id
                    )
                ).all()
            )
            validation = {
                "requirements": requirements,
                "allowed_evidence_refs": qualification_input.allowed_evidence_refs,
                "allowed_alternative_group_refs": qualification_input.allowed_alternative_group_refs,
                "incomplete_evidence_input": bool(qualification_input.omitted_evidence_refs),
            }
            try:
                artifact = validate_qualification_assessment(result.artifact, **validation)
            except ValueError as first_error:
                repair = getattr(self._matcher, "repair", None)
                if repair is None:
                    raise
                result = repair(
                    qualification_input,
                    ({
                        "code": "QUALIFICATION_SEMANTIC_VALIDATION_FAILED",
                        "path": "$",
                        "message": str(first_error),
                    },),
                )
                artifact = validate_qualification_assessment(result.artifact, **validation)
            qualification = create_or_get_qualification_assessment(
                db,
                owner=owner,
                candidate_profile=candidate,
                career_selection=None,
                job_family_pre_match=pre_match,
                selected_career_profile=selected,
                selection_reason_code="job_family_pre_match",
                job_profile=job_profile,
                artifact=artifact,
                input_quality={
                    "warnings": [],
                    "omitted_evidence_count": len(qualification_input.omitted_evidence_refs),
                    "complete": not qualification_input.omitted_evidence_refs,
                    "validation_retry_count": result.retry_count,
                },
                model_id=result.model_id,
                provider_execution_reference=result.provider_execution_reference,
            )

        preference = db.scalar(
            select(PreferenceRevision)
            .where(PreferenceRevision.user_id == item.user_id)
            .order_by(desc(PreferenceRevision.revision))
            .limit(1)
        )
        eligibility = db.scalar(
            select(EligibilityRevision)
            .where(EligibilityRevision.user_id == item.user_id)
            .order_by(desc(EligibilityRevision.revision))
            .limit(1)
        )
        match = create_or_get_match_result(
            db,
            owner=owner,
            qualification_public_id=qualification.public_id,
            preference_revision=preference.revision if preference else None,
            eligibility_revision=eligibility.revision if eligibility else None,
            legacy_adapter_enabled=self._legacy_adapter_enabled,
        )
        projected = db.scalar(
            select(JobResumeMatch.id).where(
                JobResumeMatch.user_id == item.user_id,
                JobResumeMatch.matching_v2_result_id == match.id,
                JobResumeMatch.deleted_at.is_(None),
            )
        )
        if projected is not None:
            return None
        if match.legacy_score is None:
            # Phase 8A first push keeps provisional V2 results persisted but out
            # of the legacy notification projection until the V2 inbox lands.
            return None
        if match.legacy_score < item.minimum_match_score:
            return None
        job_data = JobDescriptionData.model_validate(cache_job.job_data or {})
        job_data = job_data.model_copy(
            update={
                "title": job_data.title or cache_job.title,
                "company": job_data.company or cache_job.company,
                "summary": job_data.summary or cache_job.raw_description_text[:500],
            }
        )
        explanation = dict(match.explanation_artifact or {})
        return ExecutedCandidate(
            source_url=cache_job.source_url or f"cached-job:{cache_job.id}",
            title=job_data.title or "Untitled Job",
            company=job_data.company or "Unknown company",
            raw_description_text=cache_job.raw_description_text,
            job_data=job_data,
            match_score=match.legacy_score,
            match_data={
                **explanation,
                "summary": str(explanation.get("summary") or ""),
                "pipeline": "matching_v2",
                "matching_v2_result_id": match.public_id,
                "qualification_assessment_id": qualification.public_id,
                "provider_called": provider_called,
            },
            model_name=qualification.model_id,
            provider_execution_reference=qualification.provider_execution_reference,
            cached_job_id=cache_job.id,
            matching_v2_result_id=match.id,
        )


def _matching_intent(
    db: Session,
    item: WorkItem,
    owner: ArtifactOwner,
    candidate: CandidateProfileVersion,
) -> MatchingIntent:
    selection = db.scalar(
        select(CandidateCareerSelection)
        .where(CandidateCareerSelection.candidate_profile_version_id == candidate.id)
        .order_by(desc(CandidateCareerSelection.revision))
        .limit(1)
    )
    career = (
        db.get(CandidateCareerProfile, selection.candidate_career_profile_id)
        if selection is not None
        else None
    )
    if career is None:
        raise ValueError("Candidate Profile has no selected career context.")
    existing = db.scalar(
        select(MatchingIntent)
        .where(
            MatchingIntent.workspace_id == item.workspace_id,
            MatchingIntent.user_id == item.user_id,
            MatchingIntent.candidate_profile_version_id == candidate.id,
            MatchingIntent.target_role_text == item.keyword,
            MatchingIntent.job_family == career.role_family,
            MatchingIntent.track == career.track,
        )
        .order_by(desc(MatchingIntent.revision))
        .limit(1)
    )
    if existing is not None:
        return existing
    return create_matching_intent(
        db,
        owner=owner,
        candidate_profile=candidate,
        expected_revision=0,
        target_role_text=item.keyword,
        job_family=career.role_family,
        track=career.track,
        target_level=career.level if career.level != "unknown" else None,
        selected_candidate_career_profile_id=career.career_profile_id,
        source="user_preferred",
    )


def _catalog_profiles(
    db: Session,
    *,
    now: datetime,
    limit: int,
) -> list[tuple[JobProfileVersion, JobCache]]:
    rows = list(
        db.execute(
            select(JobProfileVersion, JobCache)
            .join(JobCache, JobCache.id == JobProfileVersion.jobs_cache_id)
            .where(
                JobProfileVersion.deleted_at.is_(None),
                JobProfileVersion.trial_eligible.is_(True),
                JobCache.deleted_at.is_(None),
                JobCache.lifecycle_state == "active",
                or_(JobCache.expires_at.is_(None), JobCache.expires_at > now),
                JobCache.raw_description_text != "",
            )
            .order_by(JobProfileVersion.created_at.desc(), JobProfileVersion.id.desc())
            .limit(limit * 2)
        ).all()
    )
    latest: dict[int, tuple[JobProfileVersion, JobCache]] = {}
    for profile, job in rows:
        latest.setdefault(job.id, (profile, job))
        if len(latest) >= limit:
            break
    return list(latest.values())


def _pre_match_rank(pre_match, job_profile, cache_job, *, item: WorkItem):
    family = {"exact": 0, "adjacent": 1, "transferable": 2, "unknown": 3}.get(
        pre_match.family_compatibility, 4
    )
    track = {"exact": 0, "compatible": 1, "unknown": 2}.get(
        pre_match.track_compatibility, 3
    )
    level = {
        "within_range": 0,
        "one_level_stretch": 1,
        "overqualified": 2,
        "unknown": 3,
        "multi_level_stretch": 4,
    }.get(pre_match.level_compatibility, 5)
    title_tokens = _tokens(str(job_profile.artifact.get("title") or cache_job.title))
    target_tokens = _tokens(item.keyword)
    location_rank = _location_rank(job_profile.artifact.get("location") or {}, item.location)
    return (
        family,
        track,
        level,
        len(target_tokens - title_tokens),
        location_rank,
        job_profile.trial_priority,
        -job_profile.id,
    )


def _span_input(span: EvidenceSpan) -> SpanInput:
    return SpanInput(
        span_id=span.span_id,
        section=span.section,
        start_utf8_byte=span.start_utf8_byte,
        end_utf8_byte=span.end_utf8_byte,
        excerpt=span.excerpt,
    )


def _tokens(value: str) -> set[str]:
    return set(_WORD_RE.findall(value.lower()))


def _location_rank(location: dict, target: str) -> int:
    normalized_target = target.strip().lower()
    if not normalized_target:
        return 0
    display = str(location.get("display") or "").lower()
    workplace = str(location.get("workplace_type") or "unknown")
    if "remote" in normalized_target:
        return 0 if workplace in {"remote", "hybrid"} or "remote" in display else 2
    if normalized_target in display:
        return 0
    return 1 if not display or workplace == "unknown" else 2
