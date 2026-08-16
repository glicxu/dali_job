from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
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
from app.modules.evaluation.job_profile_batch import (  # noqa: E402
    extract_and_persist_job_profile,
    prepare_evaluation_job,
)
from app.modules.evaluation.models import EvaluationJobSnapshot  # noqa: E402
from app.modules.matching_v2.extraction import OpenAIJobProfileExtractor  # noqa: E402
from db_common import get_schema_name, load_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and persist reusable Job Profiles for accepted evaluation jobs."
    )
    parser.add_argument("-c", "--config", required=True, help="ProcessConfig ini path")
    parser.add_argument("--output", required=True, help="JSON batch report output path")
    parser.add_argument("--benchmark-release", default="matching-benchmark-jobs.e3.v1")
    parser.add_argument("--snapshot-id", help="Process one accepted snapshot by public ID")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate selection and source text without a provider call or database write.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.limit > 100:
        raise ValueError("limit must be between 1 and 100")
    load_config(args.config)
    runtime = load_runtime_config(args.config)
    engine = DbMan.get_db_engine(schema=get_schema_name())
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    extractor = None if args.dry_run else OpenAIJobProfileExtractor(model=runtime.openai_model)

    with session_factory() as db:
        snapshots = list(db.scalars(
            select(EvaluationJobSnapshot).where(
                EvaluationJobSnapshot.benchmark_release == args.benchmark_release,
                EvaluationJobSnapshot.review_status == "accepted",
                *(
                    (EvaluationJobSnapshot.public_id == args.snapshot_id,)
                    if args.snapshot_id
                    else ()
                ),
            ).order_by(EvaluationJobSnapshot.id).limit(args.limit)
        ).all())
    if not snapshots:
        raise RuntimeError("No accepted evaluation job snapshots were found.")

    results: list[dict[str, object]] = []
    for ordinal, detached_snapshot in enumerate(snapshots, start=1):
        started = time.monotonic()
        base = {
            "ordinal": ordinal,
            "snapshot_id": detached_snapshot.public_id,
            "source_url": detached_snapshot.source_url,
            "company": detached_snapshot.company,
            "title": detached_snapshot.title,
        }
        try:
            with session_factory() as db:
                snapshot = db.merge(detached_snapshot, load=True)
                prepared = prepare_evaluation_job(db, snapshot)
                if args.dry_run:
                    outcome: dict[str, object] = {
                        "status": "ready",
                        "canonical_text_sha256": _sha256(prepared.canonical_text),
                        "evidence_span_count": len(prepared.spans),
                    }
                    db.rollback()
                else:
                    assert extractor is not None
                    outcome = extract_and_persist_job_profile(
                        db,
                        prepared,
                        extractor=extractor,
                        model_id=runtime.openai_model,
                    )
                    db.commit()
            results.append({**base, **outcome, "latency_ms": _latency_ms(started)})
        except Exception as exc:
            results.append({
                **base,
                "status": "failed",
                "latency_ms": _latency_ms(started),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
        print(
            f"[{ordinal}/{len(snapshots)}] {detached_snapshot.company} - "
            f"{detached_snapshot.title}: {results[-1]['status']}",
            flush=True,
        )

    report = {
        "process": "evaluation_job_profile_persistence",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_release": args.benchmark_release,
        "dry_run": args.dry_run,
        "model": runtime.openai_model,
        "prompt_version": "job-extract.v3",
        "response_schema_version": "job-extract-response.v3",
        "semantic_validator_version": "matching-semantic-validator.v3",
        "selected": len(results),
        "created": sum(item["status"] == "created" for item in results),
        "cached": sum(item["status"] == "cached" for item in results),
        "ready": sum(item["status"] == "ready" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "results": results,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    return 0 if report["failed"] == 0 else 2


def _sha256(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _latency_ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 2)


if __name__ == "__main__":
    raise SystemExit(main())
