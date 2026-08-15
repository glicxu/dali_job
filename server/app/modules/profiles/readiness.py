from __future__ import annotations

import re
from collections.abc import Iterable

from app.modules.profiles.schemas import (
    ProfileReadinessEvidenceSummary,
    ProfileReadinessIssue,
    ProfileReadinessResponse,
    ResumeData,
)

READINESS_VERSION = "profile-readiness-v1"
MINIMUM_SKILLS = 3

_OUTCOME_PATTERN = re.compile(
    r"(?:\b\d+(?:[.,]\d+)?%?\b|\b(?:achieved|built|completed|created|delivered|designed|developed|"
    r"earned|grew|implemented|improved|increased|launched|led|managed|reduced|shipped)\b)",
    re.IGNORECASE,
)


def _usable_items(values: Iterable[str]) -> list[str]:
    usable: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            usable.append(normalized)
            seen.add(key)
    return usable


def _has_meaningful_detail(value: str) -> bool:
    return len(value) >= 20 and len(value.split()) >= 3


def evaluate_profile_readiness(resume_data: ResumeData | dict) -> ProfileReadinessResponse:
    """Evaluate whether career evidence is sufficient for a defensible job match.

    Search preferences such as target roles are intentionally excluded. The
    evaluator is versioned and deterministic so guest and authenticated flows
    can apply the same gate without consuming a provider request.
    """

    profile = resume_data if isinstance(resume_data, ResumeData) else ResumeData.model_validate(resume_data)
    experience = _usable_items(profile.experience)
    projects = _usable_items(profile.projects)
    education = _usable_items(profile.education)
    certifications = _usable_items(profile.certifications)
    volunteer = _usable_items(profile.volunteer)
    skills = _usable_items(profile.skills)
    supporting = [*projects, *education, *certifications, *volunteer]
    evidence = [*experience, *supporting]

    responsibility_items = sum(_has_meaningful_detail(item) for item in evidence)
    if profile.summary and _has_meaningful_detail(profile.summary.strip()):
        responsibility_items += 1
    outcome_items = sum(bool(_OUTCOME_PATTERN.search(item)) for item in [*experience, *projects, *volunteer])

    if experience:
        pathway = "experienced"
    elif supporting:
        pathway = "early_career"
    else:
        pathway = "undetermined"

    missing_requirements: list[ProfileReadinessIssue] = []
    if not evidence:
        missing_requirements.append(
            ProfileReadinessIssue(
                code="experience_context_required",
                message=(
                    "Add a recent role, substantial project, education program, certification, "
                    "or volunteer experience."
                ),
            )
        )
    if responsibility_items == 0:
        missing_requirements.append(
            ProfileReadinessIssue(
                code="experience_detail_required",
                message="Add what you did or learned in at least one experience.",
            )
        )
    if len(skills) < MINIMUM_SKILLS:
        missing_requirements.append(
            ProfileReadinessIssue(
                code="skills_required",
                message="Add at least three skills that you used or demonstrated.",
            )
        )

    warnings: list[ProfileReadinessIssue] = []
    if evidence and outcome_items == 0:
        warnings.append(
            ProfileReadinessIssue(
                code="outcome_detail_recommended",
                message="Add one concrete result or completed outcome to improve match confidence.",
            )
        )

    return ProfileReadinessResponse(
        ready=not missing_requirements,
        readiness_version=READINESS_VERSION,
        pathway=pathway,
        evidence_summary=ProfileReadinessEvidenceSummary(
            experience_items=len(experience),
            supporting_items=len(supporting),
            responsibility_items=responsibility_items,
            outcome_items=outcome_items,
            skill_items=len(skills),
        ),
        missing_requirements=missing_requirements,
        warnings=warnings,
    )
