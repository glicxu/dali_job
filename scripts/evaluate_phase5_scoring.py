from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app.modules.evaluation.phase5_evaluation import (  # noqa: E402
    FIXTURE_PATH,
    evaluate_phase5_fixture,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate deterministic Phase 5 scoring, ranking, and calibration."
    )
    parser.add_argument("--fixture", default=str(FIXTURE_PATH))
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = evaluate_phase5_fixture(Path(args.fixture).expanduser().resolve())
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Phase 5 evaluation: {report['case_pass_count']}/{report['case_count']} cases; "
        f"passed={report['passed']}"
    )
    print(f"Wrote {output}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
