from __future__ import annotations

import logging

from DaliCommonLib.dali_db_man import DbMan

LOGGER = logging.getLogger(__name__)

get_db_session = DbMan.session_dependency()


def dispose_db_engines() -> None:
    dispose_all_engines = getattr(DbMan, "dispose_all_engines", None)
    if callable(dispose_all_engines):
        try:
            dispose_all_engines()
        except Exception:
            LOGGER.exception("DbMan engine disposal failed")
