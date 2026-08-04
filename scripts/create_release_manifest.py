from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from verify_migration_history import validate_history

ROOT_DIR = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_manifest(dali_common_ref: str) -> dict:
    dependency_files = (
        ROOT_DIR / "requirements-runtime.txt",
        ROOT_DIR / "requirements-test.txt",
        ROOT_DIR / "client" / "package-lock.json",
    )
    build_id_path = ROOT_DIR / "client" / ".next" / "BUILD_ID"
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dalijob_commit": _git("rev-parse", "HEAD"),
        "worktree_clean": not bool(_git("status", "--porcelain")),
        "dali_common_lib_ref": dali_common_ref,
        "expected_alembic_head": validate_history(),
        "client_build_id": build_id_path.read_text(encoding="utf-8").strip() if build_id_path.exists() else None,
        "dependency_file_sha256": {
            str(path.relative_to(ROOT_DIR)).replace("\\", "/"): _sha256(path) for path in dependency_files
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create DaliJob release provenance metadata.")
    parser.add_argument(
        "--dali-common-ref",
        default=os.getenv("DALI_COMMON_LIB_REF", "").strip() or "unmanaged-local-dependency",
        help="Pinned DaliCommonLib commit or version.",
    )
    parser.add_argument("--output", default="release/release-manifest.json")
    args = parser.parse_args()
    output = (ROOT_DIR / args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_manifest(args.dali_common_ref), indent=2) + "\n", encoding="utf-8")
    print(f"Release manifest written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
