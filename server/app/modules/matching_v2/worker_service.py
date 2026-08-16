from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
from threading import Event

from DaliCommonLib.dali_db_man import DbMan
from sqlalchemy.orm import sessionmaker

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.main import create_app
from app.modules.matching_v2.extraction import OpenAICandidateProfileExtractor, OpenAIJobProfileExtractor
from app.modules.matching_v2.qualification import OpenAIQualificationMatcher
from app.modules.matching_v2.worker import run_available


LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the durable Matching V2 operation worker.")
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}:{os.getpid()}"[:120])
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.1 or args.poll_seconds > 300:
        raise ValueError("poll_seconds must be between 0.1 and 300")

    runtime = load_runtime_config(args.config)
    configure_logging(runtime)
    app = create_app(args.config)
    factory = sessionmaker(
        bind=DbMan.get_db_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    candidate_extractor = OpenAICandidateProfileExtractor(model=runtime.openai_model)
    job_extractor = OpenAIJobProfileExtractor(model=runtime.openai_model)
    matcher = OpenAIQualificationMatcher(model=runtime.openai_model)
    stopping = Event()

    def request_stop(signum, _frame) -> None:
        LOGGER.info("Matching V2 worker shutdown requested signal=%s", signum)
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    LOGGER.info("Matching V2 worker starting worker_id=%s", args.worker_id)
    while not stopping.is_set():
        count = run_available(
            factory,
            app=app,
            worker_id=args.worker_id,
            matcher=matcher,
            candidate_extractor=candidate_extractor,
            job_extractor=job_extractor,
        )
        if args.once:
            break
        if count == 0:
            stopping.wait(args.poll_seconds)
    LOGGER.info("Matching V2 worker stopped worker_id=%s", args.worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
