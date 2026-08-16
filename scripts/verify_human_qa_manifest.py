from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from DaliCommonLib.dali_db_man import DbMan  # noqa: E402

from app.config import load_runtime_config  # noqa: E402
from app.modules.evaluation.models import EvaluationAnnotation, EvaluationRun  # noqa: E402
from db_common import get_schema_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a human-QA manifest against persisted runs.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    run_ids = [item["evaluation_run_id"] for item in manifest["canonical_runs"]]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Human-QA manifest contains duplicate run IDs.")

    load_runtime_config(args.config)
    engine = DbMan.get_db_engine(schema=get_schema_name())
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with factory() as db:
        runs = list(db.scalars(select(EvaluationRun).where(EvaluationRun.public_id.in_(run_ids))).all())
        annotations = db.scalar(
            select(func.count(EvaluationAnnotation.id)).where(
                EvaluationAnnotation.evaluation_run_id.in_([run.id for run in runs])
            )
        ) or 0

    by_id = {run.public_id: run for run in runs}
    missing = sorted(set(run_ids) - set(by_id))
    wrong_benchmark = sorted(
        run.public_id
        for run in runs
        if run.benchmark_release != manifest["benchmark_release"]
    )
    wrong_prompt = sorted(
        run.public_id
        for run in runs
        if run.manifest.get("qualification_prompt_version")
        != manifest["qualification_prompt_version"]
    )
    report = {
        "review_release": manifest["review_release"],
        "requested_runs": len(run_ids),
        "persisted_runs": len(runs),
        "missing_runs": missing,
        "wrong_benchmark_runs": wrong_benchmark,
        "wrong_prompt_runs": wrong_prompt,
        "existing_annotation_count": annotations,
        "ready": not missing and not wrong_benchmark and not wrong_prompt,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
