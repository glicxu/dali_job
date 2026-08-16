from __future__ import annotations

import sys
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.modules.jobs.catalog_lifecycle_service import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
