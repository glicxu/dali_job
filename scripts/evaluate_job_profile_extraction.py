from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from DaliCommonLib.dali_db_man import DbMan  # noqa: E402

from app.config import load_runtime_config  # noqa: E402
from app.modules.matching_v2.canonical import (  # noqa: E402
    build_evidence_spans,
    canonicalize_text,
)
from app.modules.matching_v2.extraction import (  # noqa: E402
    OpenAIJobProfileExtractor,
    cleanup_job_spans,
)
from db_common import get_schema_name, load_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Job Profile extraction independently on accepted job snapshots."
    )
    parser.add_argument("-c", "--config", required=True, help="ProcessConfig ini path")
    parser.add_argument("--output", required=True, help="JSON report output path")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--benchmark-release", default="matching-benchmark-jobs.v1")
    parser.add_argument("--snapshot-id", help="Evaluate one accepted snapshot by public ID")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.limit > 100:
        raise ValueError("limit must be between 1 and 100")
    load_config(args.config)
    runtime = load_runtime_config(args.config)
    schema = get_schema_name()
    engine = DbMan.get_db_engine(schema=schema)
    with engine.connect() as connection:
        rows = list(connection.execute(
            text(
                """
                SELECT public_id, coverage_slot, source_url, source_hash, title, company,
                       raw_description_text, review_status
                FROM matching_evaluation_job_snapshots
                WHERE benchmark_release = :benchmark_release
                  AND review_status = 'accepted'
                  AND (:snapshot_id IS NULL OR public_id = :snapshot_id)
                ORDER BY id
                LIMIT :limit
                """
            ),
            {
                "benchmark_release": args.benchmark_release,
                "snapshot_id": args.snapshot_id,
                "limit": args.limit,
            },
        ).mappings())
    if not rows:
        raise RuntimeError("No accepted evaluation job snapshots were found.")

    extractor = OpenAIJobProfileExtractor(model=runtime.openai_model)
    results: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        raw_text = str(row["raw_description_text"])
        canonical_text = canonicalize_text(raw_text)
        source_prefix = "job_eval_" + hashlib.sha256(
            canonical_text.encode("utf-8")
        ).hexdigest()[:16]
        spans = build_evidence_spans(canonical_text, source_prefix=source_prefix)
        cleanup = cleanup_job_spans(spans)
        started = time.monotonic()
        try:
            extracted = extractor.extract(list(cleanup.kept_spans))
            artifact = extracted.artifact
            results.append({
                "ordinal": index,
                "snapshot_id": row["public_id"],
                "coverage_slot": row["coverage_slot"],
                "source_url": row["source_url"],
                "source_hash": row["source_hash"],
                "source_title": row["title"],
                "source_company": row["company"],
                "status": "succeeded",
                "model": extracted.model_id,
                "provider_execution_reference": extracted.provider_execution_reference,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "repair_attempted": extracted.repair_attempted,
                "repair_count": extracted.repair_count,
                "omitted_span_ids": list(extracted.omitted_span_ids),
                "source": {
                    "text": canonical_text,
                    "spans": [span.__dict__ for span in spans],
                    "server_cleanup": {
                        "duplicate_spans_removed": cleanup.duplicate_spans_removed,
                        "boilerplate_spans_ignored": cleanup.boilerplate_spans_ignored,
                    },
                },
                "artifact": artifact.model_dump(mode="json"),
                "automated_checks": {
                    "strict_and_semantic_validation": "passed",
                    "requirement_count": len(artifact.requirements),
                    "responsibility_count": len(artifact.responsibilities),
                    "required_count": sum(
                        1 for item in artifact.requirements if item.importance == "required"
                    ),
                    "optional_count": sum(
                        1 for item in artifact.requirements if item.importance == "optional"
                    ),
                    "explicit_alternative_group_count": sum(
                        len(item.alternative_groups) for item in artifact.requirements
                    ),
                    "assigned_policy_count": sum(
                        1
                        for item in artifact.requirements
                        if item.policy_alternative_group is not None
                    ),
                },
            })
        except Exception as exc:
            results.append({
                "ordinal": index,
                "snapshot_id": row["public_id"],
                "coverage_slot": row["coverage_slot"],
                "source_url": row["source_url"],
                "source_hash": row["source_hash"],
                "source_title": row["title"],
                "source_company": row["company"],
                "status": "failed",
                "model": runtime.openai_model,
                "latency_ms": round((time.monotonic() - started) * 1000, 2),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "error_chain": _error_chain(exc),
                "source": {
                    "text": canonical_text,
                    "spans": [span.__dict__ for span in spans],
                },
            })
        print(
            f"[{index}/{len(rows)}] {row['company']} — {row['title']}: {results[-1]['status']}",
            flush=True,
        )

    report = {
        "evaluation_type": "job_profile_extraction_only",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_release": args.benchmark_release,
        "prompt_version": "job-extract.v3",
        "response_schema_version": "job-extract-response.v3",
        "semantic_validator_version": "matching-semantic-validator.v3",
        "model": runtime.openai_model,
        "jobs_requested": args.limit,
        "jobs_evaluated": len(results),
        "succeeded": sum(1 for item in results if item["status"] == "succeeded"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "results": results,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    return 0 if report["failed"] == 0 else 2


def _error_chain(exc: Exception) -> list[dict[str, str]]:
    chain: list[dict[str, str]] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append({"type": type(current).__name__, "message": str(current)})
        current = current.__cause__ or current.__context__
    return chain


if __name__ == "__main__":
    raise SystemExit(main())
