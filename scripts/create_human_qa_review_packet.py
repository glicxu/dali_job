from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def _ordered(items: list[dict], reviewer: str) -> list[dict]:
    return sorted(
        items,
        key=lambda item: hashlib.sha256(
            f"{reviewer}:{item['evaluation_run_id']}".encode()
        ).hexdigest(),
    )


def _packet_markdown(*, reviewer: str, items: list[dict], base_url: str) -> str:
    lines = [
        f"# Matching human QA packet: {reviewer}",
        "",
        "Use a reviewer account assigned only to you. Do not open the diagnostic fixture catalog,",
        "expected-score matrix, other reviewer packet, aggregate metrics, or adjudication queue.",
        "",
        "For each run, independently review Candidate Profile facts, Job Profile facts, and every",
        "Qualification Assessment row. Save an annotation for each material target. Mark uncertain",
        "items ambiguous rather than consulting another reviewer.",
        "",
        "| Item | Blind review link |",
        "| --- | --- |",
    ]
    for ordinal, item in enumerate(items, start=1):
        run_id = item["evaluation_run_id"]
        url = f"{base_url.rstrip('/')}/evaluation?review=blind&run_id={run_id}"
        lines.append(f"| QA-{ordinal:03d} | [{run_id}]({url}) |")
    lines.extend([
        "",
        "After both independent packets are complete, an assigned adjudicator uses the normal",
        "workbench adjudication queue. Reviewers must not adjudicate their own disagreements.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create blind human-QA packets from a replay report.")
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-url", default="https://jobmatch.dalifin.com")
    args = parser.parse_args()

    replay = json.loads(Path(args.replay).read_text(encoding="utf-8"))
    successful = [item for item in replay["results"] if item["status"] == "succeeded"]
    failed = [item for item in replay["results"] if item["status"] == "failed"]
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    canonical = sorted(
        ({"evaluation_run_id": item["evaluation_run_id"]} for item in successful),
        key=lambda item: item["evaluation_run_id"],
    )
    manifest = {
        "review_release": "matching-human-qa.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_replay_release": replay["replay_release"],
        "benchmark_release": replay["benchmark_release"],
        "pair_release": replay["pair_release"],
        "candidate_fixture_release": replay["candidate_fixture_release"],
        "model": replay["model"],
        "qualification_prompt_version": "qualification-match.v3",
        "state": "review_pending",
        "successful_run_count": len(canonical),
        "excluded_execution_failure_count": len(failed),
        "canonical_runs": canonical,
        "reviewers": [
            {"packet": "reviewer-a.md", "account": None, "state": "assignment_pending"},
            {"packet": "reviewer-b.md", "account": None, "state": "assignment_pending"},
        ],
        "adjudicator": {"account": None, "state": "assignment_pending"},
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for reviewer in ("reviewer-a", "reviewer-b"):
        (output_dir / f"{reviewer}.md").write_text(
            _packet_markdown(
                reviewer=reviewer,
                items=_ordered(canonical, reviewer),
                base_url=args.base_url,
            ),
            encoding="utf-8",
        )
    print(
        f"Created two blind packets for {len(canonical)} runs; "
        f"excluded {len(failed)} execution failures in {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
