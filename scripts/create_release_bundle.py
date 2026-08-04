from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT_DIR = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", "node_modules", ".git"}


def _add_tree(archive: ZipFile, root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        archive.write(path, path.relative_to(ROOT_DIR).as_posix())


def create_bundle(output: Path) -> None:
    required = [
        ROOT_DIR / "server" / "app",
        ROOT_DIR / "server" / "alembic.ini",
        ROOT_DIR / "server" / "config.example.ini",
        ROOT_DIR / "client" / ".next",
        ROOT_DIR / "client" / "package.json",
        ROOT_DIR / "client" / "package-lock.json",
        ROOT_DIR / "requirements-runtime.txt",
        ROOT_DIR / "release" / "release-manifest.json",
        ROOT_DIR / "release" / "python-sbom.json",
        ROOT_DIR / "release" / "node-sbom.json",
    ]
    missing = [str(path.relative_to(ROOT_DIR)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Release inputs are missing: {', '.join(missing)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in required:
            if path.is_dir():
                _add_tree(archive, path)
            else:
                archive.write(path, path.relative_to(ROOT_DIR).as_posix())
        _add_tree(archive, ROOT_DIR / "client" / "public")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a versioned DaliJob deployment archive.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = (ROOT_DIR / args.output).resolve()
    create_bundle(output)
    print(f"Release bundle written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
