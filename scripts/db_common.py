from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

from DaliCommonLib.dali_config import ProcessConfig
from DaliCommonLib.dali_db_man import DbMan

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def parse_config_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("-c", "--config", required=True, help="Path to ProcessConfig ini file")
    return parser.parse_args()


def load_config(config_path: str) -> str:
    resolved = str(Path(config_path).expanduser().resolve())
    ok = ProcessConfig.load_config(resolved)
    if not ok:
        raise RuntimeError(f"Failed to load config: {resolved}")
    return resolved


def get_schema_name() -> str:
    schema = DbMan.get_active_db()
    if not schema:
        raise RuntimeError("No active schema configured. Set [mysql].active_db_schema.")
    validate_identifier(schema, "schema")
    return schema


def validate_identifier(value: str, label: str) -> None:
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {label} identifier: {value!r}")


def get_mysql_config_value(name: str, default: Optional[str] = None) -> Optional[str]:
    value = ProcessConfig.get_section_config_with_default("mysql", name, default)
    if value is None:
        return default
    text = str(value).strip()
    return text or default
