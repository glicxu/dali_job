from __future__ import annotations

import sys
from pathlib import Path

from DaliCommonLib.dali_db_man import DbMan

from db_common import get_schema_name, load_config, parse_config_args

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.modules.accounts.dev_identity import (  # noqa: E402
    DEV_USER_DISPLAY_NAME,
    DEV_USER_EMAIL,
    DEV_USER_ID,
    DEV_WORKSPACE_ID,
    DEV_WORKSPACE_NAME,
)

DEV_PROFILE_ID = "00000000-0000-4000-8000-000000000201"


def main() -> int:
    args = parse_config_args("Seed local DaliJob development data.")
    load_config(args.config)
    schema = get_schema_name()

    DbMan.write(
        """
        INSERT INTO users (
            id,
            email,
            display_name,
            timezone,
            created_at,
            updated_at
        )
        VALUES (
            :id,
            :email,
            :display_name,
            :timezone,
            UTC_TIMESTAMP(6),
            UTC_TIMESTAMP(6)
        )
        ON DUPLICATE KEY UPDATE
            display_name = VALUES(display_name),
            timezone = VALUES(timezone),
            updated_at = UTC_TIMESTAMP(6)
        """,
        {
            "id": DEV_USER_ID,
            "email": DEV_USER_EMAIL,
            "display_name": DEV_USER_DISPLAY_NAME,
            "timezone": "America/New_York",
        },
        db=schema,
    )
    DbMan.write(
        """
        INSERT INTO workspaces (
            id,
            owner_user_id,
            name,
            created_at,
            updated_at
        )
        VALUES (
            :id,
            :owner_user_id,
            :name,
            UTC_TIMESTAMP(6),
            UTC_TIMESTAMP(6)
        )
        ON DUPLICATE KEY UPDATE
            owner_user_id = VALUES(owner_user_id),
            name = VALUES(name),
            updated_at = UTC_TIMESTAMP(6)
        """,
        {
            "id": DEV_WORKSPACE_ID,
            "owner_user_id": DEV_USER_ID,
            "name": DEV_WORKSPACE_NAME,
        },
        db=schema,
    )
    DbMan.write(
        """
        INSERT INTO profiles (
            id,
            workspace_id,
            user_id,
            resume_data,
            created_at,
            updated_at
        )
        VALUES (
            :id,
            :workspace_id,
            :user_id,
            JSON_OBJECT(
                'name', NULL,
                'headline', 'DaliJob local profile',
                'summary', 'Seed profile for local development before authentication is implemented.',
                'contact', JSON_OBJECT(),
                'experience', JSON_ARRAY(),
                'skills', JSON_ARRAY(),
                'education', JSON_ARRAY(),
                'certifications', JSON_ARRAY(),
                'projects', JSON_ARRAY(),
                'awards', JSON_ARRAY(),
                'publications', JSON_ARRAY(),
                'links', JSON_ARRAY(),
                'languages', JSON_ARRAY(),
                'volunteer', JSON_ARRAY(),
                'target_roles', JSON_ARRAY(),
                'target_locations', JSON_ARRAY(),
                'notes', JSON_ARRAY()
            ),
            UTC_TIMESTAMP(6),
            UTC_TIMESTAMP(6)
        )
        ON DUPLICATE KEY UPDATE
            resume_data = VALUES(resume_data),
            updated_at = UTC_TIMESTAMP(6)
        """,
        {
            "id": DEV_PROFILE_ID,
            "workspace_id": DEV_WORKSPACE_ID,
            "user_id": DEV_USER_ID,
        },
        db=schema,
    )

    print(
        "Seeded local development data "
        f"for schema={schema} user={DEV_USER_EMAIL} workspace={DEV_WORKSPACE_NAME}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
