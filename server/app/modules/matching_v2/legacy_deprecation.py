from __future__ import annotations

from fastapi import Response


LEGACY_MATCH_WARNING = (
    '299 DaliJob "Legacy raw-text matching is deprecated; cache and profile the job, then use /api/v1/matches."'
)
LEGACY_MATCH_SUNSET = "Sun, 01 Nov 2026 00:00:00 GMT"


def add_legacy_match_deprecation_headers(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = LEGACY_MATCH_SUNSET
    response.headers["Warning"] = LEGACY_MATCH_WARNING
    response.headers["Link"] = '</api/v1/matches>; rel="successor-version"'
