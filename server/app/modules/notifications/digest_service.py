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
from app.modules.notifications.digest import (
    DEFAULT_DIGEST_HOUR,
    DEFAULT_LEASE_SECONDS,
    send_one_digest,
)


LOGGER = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send due DaliJob daily email digests.")
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    parser.add_argument("--worker-id", default=_default_worker_id())
    parser.add_argument("--digest-hour", type=int, default=DEFAULT_DIGEST_HOUR)
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--max-digests-per-pass", type=int, default=100)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true", help="Drain one pass and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.poll_seconds < 1 or args.poll_seconds > 3600:
        raise ValueError("poll_seconds must be between 1 and 3600")
    if args.max_digests_per_pass < 1 or args.max_digests_per_pass > 1000:
        raise ValueError("max_digests_per_pass must be between 1 and 1000")
    runtime = load_runtime_config(args.config)
    configure_logging(runtime)
    factory = sessionmaker(
        bind=DbMan.get_db_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    stopping = Event()

    def request_stop(signum, _frame) -> None:
        LOGGER.info("Digest worker shutdown requested signal=%s", signum)
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    LOGGER.info("Digest worker starting worker_id=%s", args.worker_id)
    while not stopping.is_set():
        sent = 0
        for _ in range(args.max_digests_per_pass):
            outcome = send_one_digest(
                factory,
                runtime,
                worker_id=args.worker_id,
                digest_hour=args.digest_hour,
                lease_seconds=args.lease_seconds,
            )
            if not outcome.claimed:
                break
            sent += 1
        if args.once:
            break
        if sent == 0:
            stopping.wait(args.poll_seconds)
    LOGGER.info("Digest worker stopped worker_id=%s", args.worker_id)
    return 0


def _default_worker_id() -> str:
    return f"digest:{socket.gethostname()}:{os.getpid()}"[:120]


if __name__ == "__main__":
    raise SystemExit(main())
