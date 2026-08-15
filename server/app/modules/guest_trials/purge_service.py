from __future__ import annotations

import argparse
import json
import logging

from DaliCommonLib.dali_db_man import DbMan

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.modules.guest_trials.service import purge_expired_guest_trial_batch

LOGGER = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Purge expired DaliJob guest trials and transient files.")
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    parser.add_argument("--limit", type=int, default=100, help="Maximum expired trials to inspect")
    parser.add_argument("--dry-run", action="store_true", help="Report eligible trials without deleting data")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit < 1 or args.limit > 10_000:
        raise ValueError("limit must be between 1 and 10000")
    runtime = load_runtime_config(args.config)
    configure_logging(runtime)
    with DbMan.session_scope() as db:
        result = purge_expired_guest_trial_batch(
            db,
            storage_root=runtime.document_storage_dir,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    payload = {
        "eligible": result.eligible,
        "purged": result.purged,
        "files_deleted": result.files_deleted,
        "files_missing": result.files_missing,
        "failed_trials": result.failed_trials,
        "dry_run": result.dry_run,
    }
    print(json.dumps(payload, indent=2))
    if result.failed_trials:
        LOGGER.error("Guest purge completed with failed_trials=%s", result.failed_trials)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
