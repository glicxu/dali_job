from __future__ import annotations

import argparse
import json
from urllib.request import Request, urlopen


def read_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "DaliJob-release-readiness/1.0"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - operator-supplied release target
        return json.loads(response.read(64 * 1024).decode("utf-8"))


def check_url(url: str) -> int:
    request = Request(url, headers={"User-Agent": "DaliJob-release-readiness/1.0"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - operator-supplied release target
        return response.status


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify DaliJob API/database and client readiness.")
    parser.add_argument("--api-url", required=True, help="API base ending in /api/v1")
    parser.add_argument("--client-url", required=True)
    args = parser.parse_args()

    health = read_json(f"{args.api_url.rstrip('/')}/health/db")
    client_status = check_url(args.client_url)
    if not health.get("database_ready") or health.get("current_revision") != health.get("expected_revision"):
        raise RuntimeError(f"Database is not release-ready: {health}")
    if client_status != 200:
        raise RuntimeError(f"Client readiness returned HTTP {client_status}")
    print(json.dumps({"database": health, "client_status": client_status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
