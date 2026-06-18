from __future__ import annotations

from sqlalchemy import inspect

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config, parse_config_args

REQUIRED_TABLE_COLUMNS: dict[str, set[str]] = {
    "users": {
        "id",
        "email",
        "display_name",
        "password_hash",
        "auth_provider",
        "is_active",
        "timezone",
        "created_at",
        "updated_at",
        "deleted_at",
    },
    "workspaces": {
        "id",
        "owner_user_id",
        "name",
        "created_at",
        "updated_at",
    },
    "profiles": {
        "id",
        "workspace_id",
        "user_id",
        "resume_data",
        "created_at",
        "updated_at",
    },
    "documents": {
        "id",
        "workspace_id",
        "user_id",
        "title",
        "document_type",
        "created_at",
        "updated_at",
        "deleted_at",
    },
    "document_versions": {
        "id",
        "document_id",
        "version_number",
        "file_name",
        "content_type",
        "size_bytes",
        "sha256",
        "storage_path",
        "extracted_text",
        "created_at",
    },
}


def main() -> int:
    args = parse_config_args("Validate the configured DaliJob database schema.")
    load_config(args.config)
    schema = get_schema_name()

    engine = DbMan.get_db_engine(schema=schema)
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")

    missing = [
        table
        for table in REQUIRED_TABLE_COLUMNS
        if not DbMan.has_table(table, schema=schema)
    ]
    if missing:
        print(f"Missing required tables in {schema}: {', '.join(missing)}")
        return 1

    inspector = inspect(engine)
    missing_columns: list[str] = []
    for table, expected_columns in REQUIRED_TABLE_COLUMNS.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table)}
        for column in sorted(expected_columns - actual_columns):
            missing_columns.append(f"{table}.{column}")

    if missing_columns:
        print(f"Missing required columns in {schema}: {', '.join(missing_columns)}")
        return 1

    print(f"Database validation passed for schema: {schema}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
