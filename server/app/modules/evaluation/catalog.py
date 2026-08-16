from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.evaluation.models import EvaluationJobSnapshot
from app.modules.profiles.models import ResumeProfile

_EVALUATION_DIR = Path(__file__).parent
_CANDIDATE_RELEASE_PATH = _EVALUATION_DIR / "candidate_fixtures.v1.json"
_PAIR_RELEASE_PATH = _EVALUATION_DIR / "pair_manifest.v1.json"
_PROFILE_TITLE_PREFIX = "[EVAL synthetic.v1]"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_fixture_catalog(
    resume_profiles: list[ResumeProfile],
    snapshots: list[EvaluationJobSnapshot],
) -> dict[str, Any]:
    candidate_release = _load_json(_CANDIDATE_RELEASE_PATH)
    pair_release = _load_json(_PAIR_RELEASE_PATH)
    profiles_by_fixture_id: dict[str, ResumeProfile] = {}
    for profile in resume_profiles:
        if not profile.title.startswith(f"{_PROFILE_TITLE_PREFIX} "):
            continue
        fixture_id = profile.title.removeprefix(f"{_PROFILE_TITLE_PREFIX} ").split(":", 1)[0].strip()
        profiles_by_fixture_id[fixture_id] = profile

    snapshots_by_slot = {
        snapshot.coverage_slot: snapshot
        for snapshot in snapshots
        if snapshot.benchmark_release == pair_release["benchmark_release"]
        and snapshot.review_status == "accepted"
    }
    candidates = []
    for fixture in candidate_release["fixtures"]:
        profile = profiles_by_fixture_id.get(fixture["fixture_id"])
        candidates.append({
            "fixture_id": fixture["fixture_id"],
            "label": fixture["label"],
            "coverage": fixture["coverage"],
            "intended_failure_modes": fixture["intended_failure_modes"],
            "resume_profile_id": profile.id if profile is not None else None,
            "loaded": profile is not None,
        })

    pairs = []
    for pair in pair_release["pairs"]:
        profile = profiles_by_fixture_id.get(pair["candidate_fixture_id"])
        snapshot = snapshots_by_slot.get(pair["coverage_slot"])
        pairs.append({
            **pair,
            "resume_profile_id": profile.id if profile is not None else None,
            "job_snapshot_id": snapshot.public_id if snapshot is not None else None,
            "available": profile is not None and snapshot is not None,
        })
    return {
        "candidate_fixture_release": candidate_release["fixture_release"],
        "pair_release": pair_release["pair_release"],
        "benchmark_release": pair_release["benchmark_release"],
        "candidates": candidates,
        "pairs": pairs,
    }
