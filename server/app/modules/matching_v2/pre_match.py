from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateProfileVersion,
    CanonicalSource,
    JobFamilyPreMatch,
    JobProfileVersion,
    MatchingIntent,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, content_sha256
from app.modules.matching_v2.repositories import ArtifactOwner, ArtifactOwnershipError, RevisionConflict


POLICY_VERSION = "job-family-pre-match.v1"
LEVELS = ("student_or_intern", "entry", "junior", "mid", "senior", "staff", "principal")


def create_matching_intent(
    db: Session,
    *,
    owner: ArtifactOwner,
    candidate_profile: CandidateProfileVersion,
    expected_revision: int,
    target_role_text: str,
    job_family: str,
    track: str,
    target_level: str | None,
    selected_candidate_career_profile_id: str | None,
    source: str,
    public_id: str | None = None,
) -> MatchingIntent:
    workspace_id, user_id = _authenticated(owner)
    if not _candidate_owned(db, candidate_profile, owner):
        raise ArtifactOwnershipError("Candidate Profile does not belong to Matching Intent owner.")
    if source not in {"user_preferred", "user_confirmed", "resume_derived"}:
        raise ValueError("Unsupported Matching Intent source.")
    if public_id is None:
        if expected_revision != 0:
            raise RevisionConflict("A new Matching Intent requires expected revision 0.")
        public_id = f"intent_{uuid.uuid4().hex}"
        current_revision = 0
    else:
        current_revision = db.scalar(
            select(func.max(MatchingIntent.revision)).where(
                MatchingIntent.public_id == public_id,
                MatchingIntent.workspace_id == workspace_id,
                MatchingIntent.user_id == user_id,
            )
        )
        if current_revision is None:
            raise ArtifactOwnershipError("Matching Intent not found.")
        if current_revision != expected_revision:
            raise RevisionConflict(
                f"Expected Matching Intent revision {expected_revision}; current revision is {current_revision}."
            )

    selected = None
    if selected_candidate_career_profile_id is not None:
        selected = db.scalar(
            select(CandidateCareerProfile).where(
                CandidateCareerProfile.candidate_profile_version_id == candidate_profile.id,
                CandidateCareerProfile.career_profile_id == selected_candidate_career_profile_id,
            )
        )
        if selected is None:
            raise ValueError("Selected career profile does not belong to Candidate Profile.")
        if selected.role_family != job_family:
            raise ValueError("Selected career profile must belong to the Matching Intent job family.")

    intent = MatchingIntent(
        public_id=public_id,
        workspace_id=workspace_id,
        user_id=user_id,
        candidate_profile_version_id=candidate_profile.id,
        revision=current_revision + 1,
        target_role_text=target_role_text.strip(),
        job_family=job_family,
        track=track,
        target_level=target_level,
        selected_candidate_career_profile_id=selected.id if selected else None,
        source=source,
    )
    db.add(intent)
    db.flush()
    return intent


def get_matching_intent(
    db: Session,
    *,
    owner: ArtifactOwner,
    public_id: str,
    revision: int | None = None,
) -> MatchingIntent | None:
    workspace_id, user_id = _authenticated(owner)
    statement = select(MatchingIntent).where(
        MatchingIntent.public_id == public_id,
        MatchingIntent.workspace_id == workspace_id,
        MatchingIntent.user_id == user_id,
    )
    if revision is not None:
        statement = statement.where(MatchingIntent.revision == revision)
    else:
        statement = statement.order_by(MatchingIntent.revision.desc())
    return db.scalar(statement)


def create_or_get_job_family_pre_match(
    db: Session,
    *,
    owner: ArtifactOwner,
    candidate_profile: CandidateProfileVersion,
    intent: MatchingIntent,
    job_profile: JobProfileVersion,
) -> JobFamilyPreMatch:
    workspace_id, user_id = _authenticated(owner)
    if not _candidate_owned(db, candidate_profile, owner):
        raise ArtifactOwnershipError("Candidate Profile does not belong to pre-match owner.")
    if intent.workspace_id != workspace_id or intent.user_id != user_id:
        raise ArtifactOwnershipError("Matching Intent does not belong to pre-match owner.")
    if intent.candidate_profile_version_id != candidate_profile.id:
        raise ValueError("Matching Intent belongs to a different Candidate Profile.")

    policy = DEFAULT_REGISTRY.get("job_family_pre_match_policy", POLICY_VERSION)
    cache_key = content_sha256({
        "candidate_profile_id": candidate_profile.public_id,
        "matching_intent_id": intent.public_id,
        "matching_intent_revision": intent.revision,
        "job_profile_id": job_profile.public_id,
        "policy_hash": policy.content_hash,
    })
    existing = db.scalar(select(JobFamilyPreMatch).where(JobFamilyPreMatch.cache_key == cache_key))
    if existing is not None:
        return existing

    careers = list(db.scalars(select(CandidateCareerProfile).where(
        CandidateCareerProfile.candidate_profile_version_id == candidate_profile.id
    )).all())
    selected = _select_career(careers, intent, job_profile, policy.content)
    family = _family_compatibility(selected, job_profile, policy.content)
    track = _track_compatibility(selected, job_profile, policy.content)
    level = _level_compatibility(selected, job_profile)
    reasons = _reason_codes(selected, intent, family, track, level)
    pre_match = JobFamilyPreMatch(
        public_id=f"jfpm_{uuid.uuid4().hex}",
        workspace_id=workspace_id,
        user_id=user_id,
        candidate_profile_version_id=candidate_profile.id,
        matching_intent_id=intent.id,
        matching_intent_revision=intent.revision,
        job_profile_version_id=job_profile.id,
        selected_candidate_career_profile_id=selected.id if selected else None,
        selection_source=intent.source,
        family_compatibility=family,
        track_compatibility=track,
        level_compatibility=level,
        proceed_to_detailed_match=(selected is None or (family != "incompatible" and track != "incompatible")),
        reason_codes=reasons,
        policy_version=POLICY_VERSION,
        policy_hash=policy.content_hash,
        cache_key=cache_key,
    )
    db.add(pre_match)
    db.flush()
    return pre_match


def get_job_family_pre_match(
    db: Session, *, owner: ArtifactOwner, public_id: str
) -> JobFamilyPreMatch | None:
    workspace_id, user_id = _authenticated(owner)
    return db.scalar(select(JobFamilyPreMatch).where(
        JobFamilyPreMatch.public_id == public_id,
        JobFamilyPreMatch.workspace_id == workspace_id,
        JobFamilyPreMatch.user_id == user_id,
    ))


def _select_career(careers, intent: MatchingIntent, job: JobProfileVersion, policy):
    explicit = next((item for item in careers if item.id == intent.selected_candidate_career_profile_id), None)
    if explicit is not None:
        return explicit
    compatible_tracks = set(policy["compatible_tracks"].get(intent.track, ()))
    allowed_tracks = {intent.track, *compatible_tracks}
    eligible = [item for item in careers if item.role_family == intent.job_family and item.track in allowed_tracks]
    if not eligible:
        return None
    job_context = job.artifact["career_context"]
    def rank(item):
        job_track = job_context.get("track", "unknown")
        track_rank = 0 if item.track == job_track else 1 if item.track in set(policy["compatible_tracks"].get(job_track, ())) else 2
        coverage = sum(
            1 for signal in item.dimension_signals.values()
            if signal in {"limited", "developing", "demonstrated", "advanced"}
        )
        return (track_rank, _level_distance(item.level, intent.target_level), -coverage, -item.confidence, item.career_profile_id)
    return min(eligible, key=rank)


def _family_compatibility(selected, job, policy) -> str:
    if selected is None:
        return "unknown"
    family = job.artifact["career_context"].get("primary_role_family", "unknown")
    if family == "unknown" or selected.role_family == "unknown":
        return "unknown"
    if selected.role_family == family:
        return "exact"
    if selected.role_family in set(policy["adjacent_role_families"].get(family, ())):
        return "adjacent"
    if selected.role_family in set(policy["transferable_role_families"].get(family, ())):
        return "transferable"
    return "incompatible"


def _track_compatibility(selected, job, policy) -> str:
    if selected is None:
        return "unknown"
    track = job.artifact["career_context"].get("track", "unknown")
    if track == "unknown" or selected.track == "unknown":
        return "unknown"
    if selected.track == track:
        return "exact"
    if selected.track in set(policy["compatible_tracks"].get(track, ())):
        return "compatible"
    return "incompatible"


def _level_compatibility(selected, job) -> str:
    if selected is None or selected.level == "unknown":
        return "unknown"
    level_range = job.artifact["career_context"].get("acceptable_level_range")
    if not level_range:
        target = job.artifact["career_context"].get("target_level", "unknown")
        if target == "unknown":
            return "unknown"
        level_range = {"minimum": target, "maximum": target}
    try:
        candidate = LEVELS.index(selected.level)
        minimum = LEVELS.index(level_range["minimum"])
        maximum = LEVELS.index(level_range["maximum"])
    except (ValueError, KeyError):
        return "unknown"
    if minimum <= candidate <= maximum:
        return "within_range"
    if candidate > maximum:
        return "overqualified"
    return "one_level_stretch" if minimum - candidate == 1 else "multi_level_stretch"


def _reason_codes(selected, intent, family: str, track: str, level: str) -> list[str]:
    if selected is None:
        return ["NO_INTENT_COMPATIBLE_CAREER_PROFILE"]
    reasons = [f"FAMILY_{family.upper()}", f"TRACK_{track.upper()}", f"LEVEL_{level.upper()}"]
    if intent.selected_candidate_career_profile_id == selected.id:
        reasons.insert(0, "INTENT_SELECTED_CAREER_PROFILE")
    elif family == "exact" and track == "exact":
        reasons.insert(0, "INTENT_AND_JOB_FAMILY_EXACT")
    return reasons


def _level_distance(left: str, right: str | None) -> int:
    if right is None or left not in LEVELS or right not in LEVELS:
        return len(LEVELS)
    return abs(LEVELS.index(left) - LEVELS.index(right))


def _candidate_owned(db: Session, candidate: CandidateProfileVersion, owner: ArtifactOwner) -> bool:
    source = db.get(CanonicalSource, candidate.canonical_source_id)
    return bool(
        owner.kind == "authenticated"
        and candidate.deleted_at is None
        and source is not None
        and source.owner_kind == "authenticated"
        and source.workspace_id == owner.workspace_id
        and source.user_id == owner.user_id
    )


def _authenticated(owner: ArtifactOwner) -> tuple[int, int]:
    if owner.kind != "authenticated" or owner.workspace_id is None or owner.user_id is None:
        raise ArtifactOwnershipError("Matching Intent requires an authenticated owner.")
    return owner.workspace_id, owner.user_id
