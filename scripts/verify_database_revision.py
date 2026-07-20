from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config, parse_config_args

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"


def expected_head() -> str:
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "app" / "db" / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Expected one Alembic head, found {heads!r}")
    return heads[0]


def main() -> int:
    args = parse_config_args("Verify that the configured DaliJob database is at the expected Alembic head.")
    load_config(args.config)
    schema = get_schema_name()
    expected = expected_head()
    engine = DbMan.get_db_engine(schema=schema)
    with engine.connect() as connection:
        current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if current != expected:
        print(f"Database revision mismatch for {schema}: current={current or 'none'} expected={expected}")
        return 1
    print(f"Database revision ready for {schema}: {current}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
