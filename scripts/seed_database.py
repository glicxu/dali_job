from __future__ import annotations

from db_common import get_schema_name, load_config, parse_config_args


def main() -> int:
    args = parse_config_args("Seed local DaliJob development data.")
    load_config(args.config)
    schema = get_schema_name()

    # Phase 0 has no domain tables yet. Keep the script callable so the setup
    # workflow is stable before seed data exists.
    print(f"No seed data defined yet for schema: {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
