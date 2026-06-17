from __future__ import annotations

import sqlalchemy
from sqlalchemy import text

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config, parse_config_args


def main() -> int:
    args = parse_config_args("Create the configured DaliJob database schema.")
    load_config(args.config)
    schema = get_schema_name()

    engine = sqlalchemy.create_engine(DbMan.get_connect_str(), future=True)
    with engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{schema}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        connection.commit()

    print(f"Schema ready: {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
