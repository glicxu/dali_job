from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
from threading import Event

from sqlalchemy.orm import sessionmaker

from DaliCommonLib.dali_db_man import DbMan

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.modules.automation.executor import DatabaseAutomationResultPersister, build_default_executor
from app.modules.automation.v2_executor import CachedV2AutomationExecutor
from app.modules.automation.worker import DEFAULT_LEASE_SECONDS, run_available
from app.modules.matching_v2.extraction import OpenAICandidateProfileExtractor
from app.modules.matching_v2.qualification import OpenAIQualificationMatcher


LOGGER = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DaliJob automated-search worker.")
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    parser.add_argument("--worker-id", default=_default_worker_id())
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--max-runs-per-pass", type=int, default=25)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true", help="Drain one pass and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.poll_seconds < 0.1 or args.poll_seconds > 300:
        raise ValueError("poll_seconds must be between 0.1 and 300")
    runtime = load_runtime_config(args.config)
    configure_logging(runtime)
    engine = DbMan.get_db_engine()
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    executor = (
        CachedV2AutomationExecutor(
            session_factory=factory,
            candidate_extractor=OpenAICandidateProfileExtractor(model=runtime.openai_model),
            matcher=OpenAIQualificationMatcher(model=runtime.openai_model),
            model_id=runtime.openai_model,
            legacy_adapter_enabled=runtime.matching_v2.legacy_adapter_enabled,
        )
        if runtime.matching_v2.automation_enabled
        else build_default_executor(runtime)
    )
    persister = DatabaseAutomationResultPersister()
    stopping = Event()

    def request_stop(signum, _frame) -> None:
        LOGGER.info("Automation worker shutdown requested signal=%s", signum)
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    LOGGER.info("Automation worker starting worker_id=%s", args.worker_id)
    while not stopping.is_set():
        outcomes = run_available(
            factory,
            executor,
            worker_id=args.worker_id,
            max_runs=args.max_runs_per_pass,
            lease_seconds=args.lease_seconds,
            persister=persister,
        )
        if args.once:
            break
        if not outcomes:
            stopping.wait(args.poll_seconds)
    LOGGER.info("Automation worker stopped worker_id=%s", args.worker_id)
    return 0


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:120]


if __name__ == "__main__":
    raise SystemExit(main())
