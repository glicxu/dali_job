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
from app.modules.guest_trials.worker import run_available
from app.modules.matching_v2.extraction import OpenAICandidateProfileExtractor
from app.modules.matching_v2.qualification import OpenAIQualificationMatcher


LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the DaliJob guest-match recovery worker.")
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}"[:120])
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.1 or args.poll_seconds > 300:
        raise ValueError("poll_seconds must be between 0.1 and 300")
    runtime = load_runtime_config(args.config)
    configure_logging(runtime)
    factory = sessionmaker(
        bind=DbMan.get_db_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    extractor = OpenAICandidateProfileExtractor(model=runtime.openai_model)
    matcher = OpenAIQualificationMatcher(model=runtime.openai_model)
    stopping = Event()

    def request_stop(signum, _frame) -> None:
        LOGGER.info("Guest match worker shutdown requested signal=%s", signum)
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    LOGGER.info("Guest match worker starting worker_id=%s", args.worker_id)
    while not stopping.is_set():
        count = run_available(
            factory,
            worker_id=args.worker_id,
            model_id=runtime.openai_model,
            candidate_extractor=extractor,
            matcher=matcher,
        )
        if args.once:
            break
        if count == 0:
            stopping.wait(args.poll_seconds)
    LOGGER.info("Guest match worker stopped worker_id=%s", args.worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
