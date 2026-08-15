from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def import_all_models() -> None:
    # Ensure SQLAlchemy metadata includes all mapped models for scripts and Alembic.
    import app.modules.accounts.models  # noqa: F401
    import app.modules.audit.models  # noqa: F401
    import app.modules.auth.models  # noqa: F401
    import app.modules.automation.models  # noqa: F401
    import app.modules.applications.models  # noqa: F401
    import app.modules.documents.models  # noqa: F401
    import app.modules.guest_trials.models  # noqa: F401
    import app.modules.interviews.models  # noqa: F401
    import app.modules.job_search.models  # noqa: F401
    import app.modules.jobs.models  # noqa: F401
    import app.modules.materials.models  # noqa: F401
    import app.modules.operations.models  # noqa: F401
    import app.modules.profiles.models  # noqa: F401
    import app.modules.reports.models  # noqa: F401


import_all_models()
