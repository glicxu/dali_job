from __future__ import annotations

import argparse

from sqlalchemy.orm import sessionmaker
from DaliCommonLib.dali_db_man import DbMan

from app.config import load_runtime_config
from app.core.logging import configure_logging
from app.modules.jobs.catalog_lifecycle import expire_due_jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Expire stale DaliJob cached jobs.")
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args(argv)
    runtime = load_runtime_config(args.config)
    configure_logging(runtime)
    factory = sessionmaker(
        bind=DbMan.get_db_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    while True:
        with factory() as db:
            outcome = expire_due_jobs(db, limit=args.limit)
            db.commit()
        if not outcome.remaining_due:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
