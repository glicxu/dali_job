from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assign or remove a DaliJob administrator role.")
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    parser.add_argument("--email", required=True, help="Existing DaliJob account email")
    parser.add_argument("--role", choices=("user", "admin"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_config(args.config)
    schema = get_schema_name()
    email = args.email.strip().lower()
    engine = DbMan.get_db_engine(schema=schema)

    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT id, role FROM users WHERE LOWER(email) = :email AND deleted_at IS NULL LIMIT 1"),
            {"email": email},
        ).mappings().one_or_none()
        if row is None:
            print(f"No active DaliJob account found for {email}.")
            return 1

        previous_role = str(row["role"])
        if previous_role == args.role:
            print(f"{email} already has role={args.role}.")
            return 0

        connection.execute(
            text("UPDATE users SET role = :role, updated_at = UTC_TIMESTAMP(6) WHERE id = :user_id"),
            {"role": args.role, "user_id": row["id"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO audit_events (
                    workspace_id, actor_user_id, event_type, subject_type, subject_id,
                    source, outcome, event_data, created_at
                ) VALUES (
                    NULL, NULL, 'admin.role.changed', 'user', :subject_id,
                    'cli', 'success', :event_data, UTC_TIMESTAMP(6)
                )
                """
            ),
            {
                "subject_id": str(row["id"]),
                "event_data": json.dumps({"previous_role": previous_role, "new_role": args.role}),
            },
        )

    print(f"Updated {email} from role={previous_role} to role={args.role} in schema={schema}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
