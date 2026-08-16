from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.modules.documents.storage import safe_file_name

GUEST_STORAGE_DIRECTORY = "guest_trials"


def write_guest_document(
    storage_root: str,
    public_id: str,
    content: bytes,
    original_file_name: str,
) -> str:
    guest_root = (Path(storage_root).expanduser().resolve() / GUEST_STORAGE_DIRECTORY).resolve()
    trial_root = (guest_root / public_id).resolve()
    trial_root.relative_to(guest_root)
    trial_root.mkdir(parents=True, exist_ok=True)
    suffix = Path(safe_file_name(original_file_name)).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        suffix = ""
    target = trial_root / f"{uuid4()}{suffix}"
    target.write_bytes(content)
    return str(target)


GuestFileDeleteOutcome = Literal["deleted", "missing", "outside_guest_root"]


def delete_guest_document_file(storage_root: str, storage_path: str) -> GuestFileDeleteOutcome:
    guest_root = (Path(storage_root).expanduser().resolve() / GUEST_STORAGE_DIRECTORY).resolve()
    target = Path(storage_path).expanduser().resolve()
    try:
        target.relative_to(guest_root)
    except ValueError:
        return "outside_guest_root"
    if not target.is_file():
        return "missing"
    target.unlink()
    try:
        target.parent.rmdir()
    except OSError:
        pass
    return "deleted"
