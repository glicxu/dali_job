from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.modules.jobs.schemas import IndeedJobSearchResult


@dataclass(frozen=True)
class JobSearchQuery:
    keyword: str
    location: str
    max_results: int


class JobSearchProvider(Protocol):
    """Provider-neutral boundary that returns DaliJob's normalized search result model."""

    def search(self, *, keyword: str, location: str, max_results: int) -> list[IndeedJobSearchResult]:
        ...


def search_jobs(provider: JobSearchProvider, query: JobSearchQuery) -> list[IndeedJobSearchResult]:
    return provider.search(
        keyword=query.keyword,
        location=query.location,
        max_results=query.max_results,
    )
