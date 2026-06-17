from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.main import create_app  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the DaliJob OpenAPI contract.")
    parser.add_argument("-c", "--config", required=False, help="Path to ProcessConfig ini file")
    parser.add_argument(
        "-o",
        "--output",
        default="docs/openapi.json",
        help="Output path for generated OpenAPI JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"OpenAPI contract written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
