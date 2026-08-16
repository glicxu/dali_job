from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import time

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from DaliCommonLib.dali_db_man import DbMan  # noqa: E402

from app.config import load_runtime_config  # noqa: E402
from app.modules.auth.dependencies import AuthenticatedIdentity  # noqa: E402
from app.modules.evaluation.models import EvaluationJobSnapshot  # noqa: E402
from app.modules.evaluation.router import start_evaluation_run  # noqa: E402
from app.modules.evaluation.schemas import EvaluationRunCreateRequest  # noqa: E402
from app.modules.matching_v2.extraction import (  # noqa: E402
    OpenAICandidateProfileExtractor,
    OpenAIJobProfileExtractor,
)
from app.modules.matching_v2.qualification import OpenAIQualificationMatcher  # noqa: E402
from app.modules.profiles.models import ResumeProfile  # noqa: E402
from db_common import get_schema_name  # noqa: E402

EVALUATION_DIR = SERVER / "app" / "modules" / "evaluation"
PAIR_PATH = EVALUATION_DIR / "pair_manifest.v1.json"
SCORE_PATH = EVALUATION_DIR / "expected_score_matrix.v1.json"
PROFILE_PREFIX = "[EVAL synthetic.v1] "


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay the frozen E1 pairs through the current persisted three-stage pipeline."
    )
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pair-id")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.limit > 30:
        raise ValueError("limit must be between 1 and 30")
    runtime = load_runtime_config(args.config)
    runtime = replace(
        runtime,
        matching_v2=replace(runtime.matching_v2, evaluation_enabled=True),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))
    identity = AuthenticatedIdentity(
        external_user_id="1",
        email="job@dalifin.local",
        display_name="Dali Job Evaluation",
        provider="local",
        role="admin",
    )
    engine = DbMan.get_db_engine(schema=get_schema_name())
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    pairs = json.loads(PAIR_PATH.read_text(encoding="utf-8"))
    expected_scores = _expected_scores()
    selected_pairs = [
        item for item in pairs["pairs"] if args.pair_id is None or item["pair_id"] == args.pair_id
    ][:args.limit]
    if not selected_pairs:
        raise ValueError("No matching evaluation pairs were selected.")

    with session_factory() as db:
        profiles = list(db.scalars(select(ResumeProfile).where(
            ResumeProfile.deleted_at.is_(None),
            ResumeProfile.title.startswith(PROFILE_PREFIX),
        )).all())
        snapshots = list(db.scalars(select(EvaluationJobSnapshot).where(
            EvaluationJobSnapshot.benchmark_release == pairs["benchmark_release"],
            EvaluationJobSnapshot.review_status == "accepted",
        )).all())
    profile_ids = {
        item.title.removeprefix(PROFILE_PREFIX).split(":", 1)[0].strip(): item.id
        for item in profiles
    }
    snapshot_ids = {item.coverage_slot: item.public_id for item in snapshots}
    missing_profiles = sorted(
        {item["candidate_fixture_id"] for item in selected_pairs} - set(profile_ids)
    )
    missing_slots = sorted({item["coverage_slot"] for item in selected_pairs} - set(snapshot_ids))
    if missing_profiles or missing_slots:
        raise RuntimeError(
            f"Replay inputs are incomplete; missing_profiles={missing_profiles}, "
            f"missing_slots={missing_slots}"
        )

    output = Path(args.output).expanduser().resolve()
    previous_results = []
    if args.resume and output.exists():
        previous_results = json.loads(output.read_text(encoding="utf-8")).get("results", [])
    completed_ids = {
        item["pair_id"] for item in previous_results if item.get("status") == "succeeded"
    }
    results = list(previous_results)
    candidate_extractor = OpenAICandidateProfileExtractor(runtime.openai_model)
    job_extractor = OpenAIJobProfileExtractor(runtime.openai_model)
    matcher = OpenAIQualificationMatcher(runtime.openai_model)
    for ordinal, pair in enumerate(selected_pairs, start=1):
        if pair["pair_id"] in completed_ids:
            print(f"[{ordinal}/{len(selected_pairs)}] {pair['pair_id']}: already succeeded", flush=True)
            continue
        started = time.monotonic()
        try:
            with session_factory() as db:
                detail = start_evaluation_run(
                    EvaluationRunCreateRequest(
                        job_snapshot_id=snapshot_ids[pair["coverage_slot"]],
                        resume_profile_id=profile_ids[pair["candidate_fixture_id"]],
                        candidate_fixture_release=pairs["candidate_fixture_release"],
                    ),
                    request,
                    db,
                    identity,
                    candidate_extractor,
                    job_extractor,
                    matcher,
                )
                db.commit()
            assessments = detail.qualification.assessment.requirement_assessments
            status_counts: dict[str, int] = {}
            for assessment in assessments:
                status_counts[assessment.status] = status_counts.get(assessment.status, 0) + 1
            row = {
                "pair_id": pair["pair_id"],
                "coverage_slot": pair["coverage_slot"],
                "candidate_fixture_id": pair["candidate_fixture_id"],
                "expectation": pair["expectation"],
                "initial_expected_score": expected_scores[
                    (pair["coverage_slot"], pair["candidate_fixture_id"])
                ],
                "status": "succeeded",
                "evaluation_run_id": detail.public_id,
                "candidate_profile_id": detail.candidate_profile_id,
                "job_profile_id": detail.job_profile_id,
                "qualification_assessment_id": detail.qualification_assessment_id,
                "qualification_input_quality": detail.qualification.input_quality,
                "status_counts": dict(sorted(status_counts.items())),
                "requirement_count": len(assessments),
                "contract_metrics": [
                    metric.model_dump(mode="json") for metric in detail.metrics.contract_metrics
                ],
                "run_metadata": detail.run_metadata,
                "manifest": detail.manifest.model_dump(mode="json"),
                "latency_ms": _latency_ms(started),
            }
        except Exception as exc:
            row = {
                "pair_id": pair["pair_id"],
                "coverage_slot": pair["coverage_slot"],
                "candidate_fixture_id": pair["candidate_fixture_id"],
                "expectation": pair["expectation"],
                "initial_expected_score": expected_scores[
                    (pair["coverage_slot"], pair["candidate_fixture_id"])
                ],
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "error_chain": _error_chain(exc),
                "latency_ms": _latency_ms(started),
            }
        results = [item for item in results if item.get("pair_id") != pair["pair_id"]]
        results.append(row)
        _write_report(output, runtime.openai_model, pairs, results)
        print(f"[{ordinal}/{len(selected_pairs)}] {pair['pair_id']}: {row['status']}", flush=True)

    report = _write_report(output, runtime.openai_model, pairs, results)
    print(
        f"Replay complete: {report['succeeded']}/{report['attempted']} succeeded; "
        f"{report['failed']} failed. Wrote {output}",
        flush=True,
    )
    return 0 if report["failed"] == 0 else 2


def _expected_scores() -> dict[tuple[str, str], int]:
    matrix = json.loads(SCORE_PATH.read_text(encoding="utf-8"))
    fixture_by_code = {item["code"]: item["fixture_id"] for item in matrix["candidates"]}
    return {
        (job["coverage_slot"], fixture_by_code[code]): int(score)
        for job in matrix["jobs"]
        for code, score in job["initial_scores"].items()
    }


def _write_report(path: Path, model: str, pair_release: dict, results: list[dict]) -> dict:
    ordered = sorted(results, key=lambda item: item["pair_id"])
    report = {
        "replay_release": "matching-evaluation-replay.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_release": pair_release["benchmark_release"],
        "pair_release": pair_release["pair_release"],
        "candidate_fixture_release": pair_release["candidate_fixture_release"],
        "model": model,
        "attempted": len(ordered),
        "succeeded": sum(item["status"] == "succeeded" for item in ordered),
        "failed": sum(item["status"] == "failed" for item in ordered),
        "results": ordered,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _latency_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 2)


def _error_chain(exc: Exception) -> list[dict[str, str]]:
    chain = []
    current: BaseException | None = exc
    seen = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append({"type": type(current).__name__, "message": str(current)})
        current = current.__cause__ or current.__context__
    return chain


if __name__ == "__main__":
    raise SystemExit(main())
