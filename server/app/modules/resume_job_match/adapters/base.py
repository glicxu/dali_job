from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from lxml import etree
from lxml import html as lxml_html


_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class AdapterExtraction:
    adapter_name: str
    mapping: dict[str, Any]
    canonical_url: str | None = None
    warnings: tuple[str, ...] = ()


@runtime_checkable
class SafeJobNetworkClient(Protocol):
    """Restricted network boundary available to future structured-endpoint adapters."""

    def get_json(self, url: str) -> Any | None: ...


@runtime_checkable
class JobSourceAdapter(Protocol):
    name: str

    def matches(self, url: str, html: str | None) -> bool: ...

    def extract(
        self,
        *,
        url: str,
        html: str,
        network: SafeJobNetworkClient | None = None,
    ) -> AdapterExtraction | None: ...


@dataclass(frozen=True)
class AdapterSelectors:
    title: tuple[str, ...]
    company: tuple[str, ...]
    location: tuple[str, ...]
    description: tuple[str, ...]
    responsibilities: tuple[str, ...] = ()
    required_qualifications: tuple[str, ...] = ()
    preferred_qualifications: tuple[str, ...] = ()


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _node_text(node: object) -> str:
    if isinstance(node, etree._Element):
        return _clean_text(" ".join(node.itertext()))
    return _clean_text(str(node))


def _first_text(tree: etree._Element, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        for node in tree.xpath(selector):
            value = _node_text(node)
            if value:
                return value
    return None


def _all_text(tree: etree._Element, selectors: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for selector in selectors:
        for node in tree.xpath(selector):
            value = _node_text(node)
            if value and value not in values:
                values.append(value)
    return values


class SelectorJobSourceAdapter:
    name = ""
    host_suffixes: tuple[str, ...] = ()
    html_fingerprints: tuple[str, ...] = ()
    selectors = AdapterSelectors((), (), (), ())

    def matches(self, url: str, html: str | None) -> bool:
        hostname = (urlparse(url).hostname or "").lower()
        if any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in self.host_suffixes):
            return True
        lowered_html = (html or "").lower()
        return bool(lowered_html) and any(marker in lowered_html for marker in self.html_fingerprints)

    def extract(
        self,
        *,
        url: str,
        html: str,
        network: SafeJobNetworkClient | None = None,
    ) -> AdapterExtraction | None:
        del network
        try:
            tree = lxml_html.fromstring(html)
        except (etree.ParserError, ValueError):
            return None

        description = _first_text(tree, self.selectors.description)
        if not description or len(description) < 80:
            return None
        mapping: dict[str, Any] = {
            "title": _first_text(tree, self.selectors.title),
            "companyName": _first_text(tree, self.selectors.company),
            "formattedLocation": _first_text(tree, self.selectors.location),
            "jobDescription": description,
            "responsibilities": _all_text(tree, self.selectors.responsibilities),
            "requiredQualifications": _all_text(tree, self.selectors.required_qualifications),
            "preferredQualifications": _all_text(tree, self.selectors.preferred_qualifications),
        }
        return AdapterExtraction(
            adapter_name=self.name,
            mapping={key: value for key, value in mapping.items() if value},
            warnings=("ats_html_extraction",),
        )
