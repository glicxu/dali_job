from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.guest_trials.models import GuestTrial
from app.modules.guest_trials.service import resolve_guest_trial


def get_current_guest_trial(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db_session),
) -> GuestTrial:
    scheme, separator, credential = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "guest":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid guest credential required",
            headers={"WWW-Authenticate": "Guest"},
        )
    trial = resolve_guest_trial(db, credential.strip())
    if trial is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="valid guest credential required",
            headers={"WWW-Authenticate": "Guest"},
        )
    return trial
