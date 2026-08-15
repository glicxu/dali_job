from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config


TIER_CODES = ("free", "starter", "plus", "super")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assign a DaliJob subscription tier. Super is for internal testing only."
    )
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    parser.add_argument("--email", required=True, help="Existing DaliJob account email")
    parser.add_argument("--tier", choices=TIER_CODES, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_config(args.config)
    schema = get_schema_name()
    email = args.email.strip().lower()
    engine = DbMan.get_db_engine(schema=schema)

    with engine.begin() as connection:
        row = connection.execute(
            text(
                """
                SELECT u.id AS user_id, s.workspace_id, s.id AS subscription_id, s.tier_code
                FROM users u
                LEFT JOIN user_subscriptions s ON s.user_id = u.id AND s.deleted_at IS NULL
                WHERE LOWER(u.email) = :email AND u.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"email": email},
        ).mappings().one_or_none()
        if row is None:
            print(f"No active DaliJob account found for {email}.")
            return 1
        if row["subscription_id"] is None:
            print(f"{email} has no subscription record; sign in once before assigning a tier.")
            return 1

        previous_tier = str(row["tier_code"])
        if previous_tier == args.tier:
            print(f"{email} already has tier={args.tier}.")
            return 0
        connection.execute(
            text(
                """
                UPDATE user_subscriptions
                SET tier_code = :tier, status = 'active', updated_at = UTC_TIMESTAMP(6)
                WHERE id = :subscription_id
                """
            ),
            {"tier": args.tier, "subscription_id": row["subscription_id"]},
        )
        connection.execute(
            text(
                """
                INSERT INTO audit_events (
                    workspace_id, actor_user_id, event_type, subject_type, subject_id,
                    source, outcome, event_data, created_at
                ) VALUES (
                    :workspace_id, NULL, 'subscription.tier.changed', 'user', :subject_id,
                    'cli', 'success', :event_data, UTC_TIMESTAMP(6)
                )
                """
            ),
            {
                "workspace_id": row["workspace_id"],
                "subject_id": str(row["user_id"]),
                "event_data": json.dumps(
                    {"previous_tier": previous_tier, "new_tier": args.tier}
                ),
            },
        )

    print(f"Updated {email} from tier={previous_tier} to tier={args.tier} in schema={schema}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
