from __future__ import annotations

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config, parse_config_args

REQUIRED_TABLES: tuple[str, ...] = ()


def main() -> int:
    args = parse_config_args("Validate the configured DaliJob database schema.")
    load_config(args.config)
    schema = get_schema_name()

    engine = DbMan.get_db_engine(schema=schema)
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")

    missing = [table for table in REQUIRED_TABLES if not DbMan.has_table(table, schema=schema)]
    if missing:
        print(f"Missing required tables in {schema}: {', '.join(missing)}")
        return 1

    print(f"Database validation passed for schema: {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
