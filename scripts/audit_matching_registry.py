from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from DaliCommonLib.dali_db_man import DbMan  # noqa: E402

from app.config import load_runtime_config  # noqa: E402
from app.modules.matching_v2.models import PromptPolicyRegistryRecord  # noqa: E402
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, canonical_json  # noqa: E402
from db_common import get_schema_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare persisted and code matching registries.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    load_runtime_config(args.config)
    engine = DbMan.get_db_engine(schema=get_schema_name())
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    with session_factory() as db:
        persisted = {
            (row.artifact_type, row.version): row
            for row in db.scalars(select(PromptPolicyRegistryRecord)).all()
        }

    results = []
    for entry in DEFAULT_REGISTRY.entries():
        key = (entry.artifact_type, entry.version)
        row = persisted.get(key)
        status = "missing"
        if row is not None:
            metadata = json.loads(canonical_json(entry.metadata))
            status = (
                "match"
                if row.content_hash == entry.content_hash and row.metadata_json == metadata
                else "conflict"
            )
        results.append(
            {
                "artifact_type": entry.artifact_type,
                "version": entry.version,
                "status": status,
                "code_hash": entry.content_hash,
                "persisted_hash": row.content_hash if row is not None else None,
            }
        )

    print(json.dumps({"entries": results}, indent=2))
    return 1 if any(item["status"] == "conflict" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
