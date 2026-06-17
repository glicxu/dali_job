from __future__ import annotations

import sys
from pathlib import Path

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config, parse_config_args

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.db.base import Base  # noqa: E402


def main() -> int:
    args = parse_config_args("Create DaliJob tables in the configured schema.")
    load_config(args.config)
    schema = get_schema_name()
    DbMan.create_all(Base, schema=schema)
    print(f"Tables ready in schema: {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
