from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def import_all_models() -> None:
    # Ensure SQLAlchemy metadata includes all mapped models for scripts and Alembic.
    import app.modules.accounts.models  # noqa: F401
    import app.modules.applications.models  # noqa: F401
    import app.modules.documents.models  # noqa: F401
    import app.modules.interviews.models  # noqa: F401
    import app.modules.jobs.models  # noqa: F401
    import app.modules.operations.models  # noqa: F401
    import app.modules.profiles.models  # noqa: F401


import_all_models()
