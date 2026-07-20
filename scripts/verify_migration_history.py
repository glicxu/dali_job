from __future__ import annotations

import argparse
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"


def load_history() -> ScriptDirectory:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "app" / "db" / "migrations"))
    return ScriptDirectory.from_config(config)


def validate_history(expected_head: str | None = None) -> str:
    history = load_history()
    heads = history.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {heads!r}")

    head = heads[0]
    if expected_head and head != expected_head:
        raise RuntimeError(f"Expected Alembic head {expected_head}, found {head}")

    revisions = list(history.walk_revisions(base="base", head="heads"))
    if not revisions:
        raise RuntimeError("Alembic history is empty")
    for revision in revisions:
        if isinstance(revision.down_revision, tuple):
            raise RuntimeError(f"Merge revision is not allowed in the linear release history: {revision.revision}")
    return head


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the DaliJob Alembic revision graph.")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    head = validate_history(args.expected_head)
    print(f"Migration history is linear with head {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
