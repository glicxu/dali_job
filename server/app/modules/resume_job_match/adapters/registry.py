from __future__ import annotations

from collections.abc import Iterable

from .ashby import AshbyAdapter
from .base import AdapterExtraction, JobSourceAdapter, SafeJobNetworkClient
from .greenhouse import GreenhouseAdapter
from .icims import IcimsAdapter
from .lever import LeverAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .workday import WorkdayAdapter


REGISTERED_ADAPTERS: tuple[JobSourceAdapter, ...] = (
    GreenhouseAdapter(),
    LeverAdapter(),
    WorkdayAdapter(),
    SmartRecruitersAdapter(),
    AshbyAdapter(),
    IcimsAdapter(),
)


def extract_from_adapters(
    *,
    url: str,
    html: str,
    network: SafeJobNetworkClient | None = None,
    adapters: Iterable[JobSourceAdapter] = REGISTERED_ADAPTERS,
) -> list[AdapterExtraction]:
    extractions: list[AdapterExtraction] = []
    for adapter in adapters:
        try:
            if not adapter.matches(url, html):
                continue
            extraction = adapter.extract(url=url, html=html, network=network)
        except Exception:
            continue
        if extraction is not None:
            extractions.append(extraction)
    return extractions
