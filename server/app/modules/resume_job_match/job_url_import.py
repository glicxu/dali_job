from __future__ import annotations

import html
import http.client
import ipaddress
import json
import logging
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, unquote, urldefrag, urljoin, urlunparse
from urllib.parse import urlparse

from fastapi import HTTPException, status
from lxml import etree
from lxml import html as lxml_html

from .adapters import extract_from_adapters


LOGGER = logging.getLogger("dalijob.job_extraction")
JOB_EXTRACTOR_VERSION = "2"


class RenderableFetchError(Exception):
    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


MAX_JOB_PAGE_BYTES = 2 * 1024 * 1024
MAX_STATIC_TOTAL_BYTES = MAX_JOB_PAGE_BYTES
MAX_JOB_TEXT_CHARS = 30_000
FETCH_TIMEOUT_SECONDS = 12
STATIC_FETCH_TOTAL_TIMEOUT_SECONDS = 24
MAX_REDIRECTS = 5
MAX_URL_LENGTH = 4096
RENDERED_FETCH_TIMEOUT_MS = 20_000
RENDERED_SELECTOR_TIMEOUT_MS = 6_000
RENDERED_SETTLE_TIMEOUT_MS = 2_000
RENDERED_FETCH_TOTAL_TIMEOUT_SECONDS = 30
MAX_RENDERED_SUBREQUESTS = 80
MAX_RENDERED_TOTAL_BYTES = 8 * 1024 * 1024
MAX_RENDERED_HTML_BYTES = 2 * 1024 * 1024
MAX_STRUCTURED_JSON_BYTES = 1024 * 1024
MAX_STRUCTURED_JSON_DEPTH = 12
MAX_STRUCTURED_JSON_OBJECTS = 2_000
MAX_DOM_CANDIDATES = 500
MAX_RENDERED_JSON_RESPONSES = 20
MAX_RENDERED_JSON_OBJECTS = 4_000
MAX_RENDERED_CAPTURED_JSON_BYTES = 2 * 1024 * 1024
MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE = 0.60
REVIEW_EXTRACTION_CONFIDENCE = 0.80
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
ALLOWED_URL_PORTS = {"http": 80, "https": 443}
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
RENDERED_SEMANTIC_READY_SCRIPT = r"""
() => {
  const selectors = [
    '[itemtype*="JobPosting"]',
    '#jobDescriptionText',
    '[class*="job-description"]',
    '[class*="jobDescription"]',
    '[data-testid*="description"]',
    '[data-automation-id*="jobPostingDescription"]',
    'main article'
  ];
  const structured = Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
    .some((node) => /jobposting/i.test(node.textContent || ''));
  if (structured) return true;
  if (selectors.some((selector) => Array.from(document.querySelectorAll(selector))
    .some((node) => (node.innerText || '').trim().length >= 180))) return true;
  const text = (document.body?.innerText || '').replace(/\s+/g, ' ');
  return text.length >= 500 && /(responsibilities|qualifications|requirements|what you.ll do)/i.test(text);
}
"""
RENDERED_DOM_STABLE_SCRIPT = r"""
() => {
  const body = document.body;
  if (!body) return false;
  const signature = `${body.innerText.length}:${body.querySelectorAll('*').length}`;
  const now = Date.now();
  const previous = window.__dalijobDomStability;
  if (!previous || previous.signature !== signature) {
    window.__dalijobDomStability = { signature, changedAt: now };
    return false;
  }
  return now - previous.changedAt >= 350;
}
"""
BLOCK_TAGS = {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4"}
CONTAINER_TAGS = {"main", "article", "section", "div"}
CONTAINER_ATTR_KEYWORDS = (
    "job-detail-body",
    "job-description",
    "job_description",
    "jobdescription",
    "job-details",
    "job_detail",
    "job-detail",
    "job-posting",
    "jobposting",
    "jobsearch-rightpane",
    "jobdescriptiontext",
    "posting",
    "description",
    "content",
    "rightpane",
)
SECTION_MARKERS = (
    "description",
    "job description",
    "duties",
    "responsibilities",
    "what you'll do",
    "what you will do",
    "basic qualifications",
    "minimum qualifications",
    "required qualifications",
    "preferred qualifications",
    "requirements",
    "qualifications",
    "about the team",
)
SECTION_HEADING_ALIASES = {
    "summary": (
        "about the role",
        "about this role",
        "description",
        "full job description",
        "job description",
        "overview",
        "position summary",
        "role overview",
        "the opportunity",
    ),
    "responsibilities": (
        "duties",
        "key responsibilities",
        "responsibilities",
        "what you will do",
        "what you'll do",
        "your impact",
    ),
    "required_qualifications": (
        "basic qualifications",
        "minimum qualifications",
        "minimum requirements",
        "must have",
        "required qualifications",
        "required skills",
        "requirements",
        "what you bring",
        "who you are",
    ),
    "preferred_qualifications": (
        "desired qualifications",
        "nice to have",
        "preferred qualifications",
        "preferred skills",
    ),
    "experience": (
        "experience",
        "experience requirements",
        "required experience",
    ),
    "education": (
        "education",
        "education requirements",
        "training and education",
    ),
    "skills": (
        "key skills",
        "skills",
        "skills and abilities",
    ),
    "tools_and_technologies": (
        "technologies",
        "technology stack",
        "tools and technologies",
    ),
    "certifications": (
        "certifications",
        "licenses and certifications",
    ),
    "compensation": (
        "compensation",
        "pay range",
        "salary",
        "salary range",
    ),
    "benefits": (
        "benefits",
        "perks and benefits",
        "what we offer",
    ),
    "location_and_work_arrangement": (
        "location",
        "remote work",
        "work arrangement",
        "work location",
        "workplace type",
    ),
    "application_details": (
        "application deadline",
        "application details",
        "how to apply",
    ),
}
SECTION_DISPLAY_NAMES = {
    "summary": "Summary",
    "responsibilities": "Responsibilities",
    "required_qualifications": "Required Qualifications",
    "preferred_qualifications": "Preferred Qualifications",
    "experience": "Experience",
    "education": "Education",
    "skills": "Skills",
    "tools_and_technologies": "Tools and Technologies",
    "certifications": "Certifications",
    "compensation": "Compensation",
    "benefits": "Benefits",
    "location_and_work_arrangement": "Location and Work Arrangement",
    "application_details": "Application Details",
    "other": "Other",
}
SECTION_PRIORITY_WEIGHTS = {
    "summary": 2.0,
    "responsibilities": 3.0,
    "required_qualifications": 3.0,
    "preferred_qualifications": 2.0,
    "experience": 2.0,
    "education": 1.5,
    "skills": 1.5,
    "tools_and_technologies": 1.2,
    "certifications": 1.0,
    "compensation": 0.8,
    "benefits": 0.6,
    "location_and_work_arrangement": 1.0,
    "application_details": 0.8,
    "other": 0.5,
}
FOOTER_MARKERS = (
    "apply now",
    "share this job",
    "related jobs",
    "similar jobs",
    "job categories",
    "view all jobs",
    "privacy notice",
    "equal opportunity employer",
    "our inclusive culture empowers",
    "if you have a disability",
    "reasonable accommodation",
    "request an accommodation",
    "the base salary range",
    "learn more about our benefits",
    "eeo is the law",
)
ACCESS_GATE_MARKERS = (
    "additional verification required",
    "authenticating",
    "bot-detection",
    "create an account",
    "email address",
    "forgot password",
    "indeed account",
    "new to indeed",
    "password",
    "ray id",
    "security check",
    "sign in",
    "sign-in",
    "two-step verification",
    "verification successful",
    "waiting for security",
)
JOB_CONTENT_MARKERS = (
    "basic qualifications",
    "benefits",
    "employment type",
    "full job description",
    "job description",
    "preferred qualifications",
    "qualifications",
    "requirements",
    "responsibilities",
)
JOB_LINK_PATH_MARKERS = (
    "/getjob/viewdetails/",
    "/job/",
    "/jobs/",
    "/careers/",
    "/career/",
    "/position/",
    "/positions/",
    "/opening/",
    "/openings/",
    "jobid=",
    "job_id=",
    "requisition",
    "reqid",
)
NON_JOB_LINK_PATH_MARKERS = (
    "/account",
    "/account/login",
    "/applicant/",
    "/application",
    "/benefit",
    "/category",
    "/categories",
    "/career/salaries",
    "/dashboard",
    "/help",
    "/location",
    "/locations",
    "/login",
    "/profile",
    "/saved",
    "/search/",
    "/search?",
    "/search/results",
    "/settings",
    "/team",
    "/teams",
    "/user",
    "bot-detection",
    "continue2=",
    "savedsearch",
)
JOB_DETAIL_PATTERNS = (
    re.compile(r"/getjob/viewdetails/\d+(?:[/?#]|$)", re.IGNORECASE),
    re.compile(r"/job/\d+(?:[/?#]|$)", re.IGNORECASE),
    re.compile(r"/jobs/\d+(?:[/?#]|$)", re.IGNORECASE),
    re.compile(r"/jobs/[a-z0-9-]*\d[a-z0-9-]*(?:[/?#]|$)", re.IGNORECASE),
    re.compile(r"/viewjob\?(?:[^#]*&)?jk=[^&]+", re.IGNORECASE),
    re.compile(r"/rc/clk\?(?:[^#]*&)?jk=[^&]+", re.IGNORECASE),
    re.compile(r"[?&](?:jk|jobid|job_id|jobkey|reqid|requisitionid|requisition_id)=[^&]+", re.IGNORECASE),
)
JOB_TITLE_WORDS = (
    "administrator",
    "analyst",
    "architect",
    "associate",
    "consultant",
    "developer",
    "engineer",
    "manager",
    "officer",
    "programmer",
    "scientist",
    "specialist",
    "technician",
)
PAGINATION_ATTR_MARKERS = (
    "pagination",
    "pager",
    "page-nav",
    "page_nav",
    "page-navigation",
    "results-pagination",
    "search-pagination",
)
NEXT_TEXT_VALUES = {
    ">",
    "next",
    "next page",
    "show more",
    "load more",
    "more results",
}
NEXT_QUERY_PARAMS = {"p", "page", "pg", "pageNumber", "page_number"}
OFFSET_QUERY_PARAMS = {"start", "offset", "from", "first", "skip"}


@dataclass(frozen=True)
class ValidatedDestination:
    url: str
    scheme: str
    hostname: str
    port: int
    addresses: tuple[str, ...]
    request_target: str


@dataclass(frozen=True)
class NetworkResponse:
    status_code: int
    reason: str
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str, default: str = "") -> str:
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return default


@dataclass
class RenderedFetchBudget:
    deadline: float
    requests: int = 0
    response_bytes: int = 0
    captured_json_bytes: int = 0
    captured_json_objects: int = 0
    captured_json_blocks: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    blocked_status_code: int = status.HTTP_400_BAD_REQUEST


@dataclass
class CandidateBlock:
    tag: str
    attr_text: str
    depth: int = 1
    parts: list[str] = field(default_factory=list)


@dataclass
class MicrodataCapture:
    itemprop: str
    depth: int = 1
    parts: list[str] = field(default_factory=list)


@dataclass
class JobExtractionCandidate:
    method: str
    source_url: str = ""
    canonical_url: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    sections: dict[str, list[str]] = field(default_factory=dict)
    focused_text: str = ""
    raw_visible_text: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class JobExtractionResult:
    source_url: str
    canonical_url: str | None
    title: str | None
    company: str | None
    location: str | None
    sections: dict[str, list[str]]
    focused_text: str
    raw_visible_text: str | None
    extraction_method: str
    confidence: float
    warnings: list[str]
    extractor_version: str


def _is_public_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return ip.is_global


def _resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    try:
        addresses = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job URL host could not be resolved.",
        ) from exc

    resolved: list[str] = []
    for item in addresses:
        ip_text = item[4][0]
        if not _is_public_ip(ip_text):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host is not allowed.")
        if ip_text not in resolved:
            resolved.append(ip_text)
    if not resolved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host could not be resolved.")
    return tuple(resolved)


def _validate_public_destination(url: str) -> ValidatedDestination:
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL is required.")
    value = url.strip()
    if len(value) > MAX_URL_LENGTH or any(ord(character) < 32 for character in value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL is malformed or too long.")

    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_URL_PORTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL must use http or https.")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job URL must not contain embedded credentials.",
        )
    if not parsed.hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host is required.")
    try:
        port = parsed.port or ALLOWED_URL_PORTS[scheme]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL port is invalid.") from exc
    if port != ALLOWED_URL_PORTS[scheme]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job URL uses a nonstandard port that is not allowed.",
        )

    raw_hostname = parsed.hostname.rstrip(".")
    if not raw_hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host is invalid.")
    try:
        hostname = raw_hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host is invalid.") from exc
    addresses = _resolve_public_addresses(hostname, port)
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    path = parsed.path or "/"
    normalized_url = urlunparse((scheme, host_for_url, path, parsed.params, parsed.query, ""))
    request_target = urlunparse(("", "", path, parsed.params, parsed.query, ""))
    return ValidatedDestination(
        url=normalized_url,
        scheme=scheme,
        hostname=hostname,
        port=port,
        addresses=addresses,
        request_target=request_target,
    )


def validate_public_job_url(url: str) -> str:
    return _validate_public_destination(url).url


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, port: int, address: str, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._validated_address = address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, port: int, address: str, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._validated_address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Job URL fetch timed out.")
    return max(0.1, min(float(FETCH_TIMEOUT_SECONDS), remaining))


def _read_response_body(
    response: http.client.HTTPResponse,
    *,
    max_bytes: int,
    deadline: float,
) -> bytes:
    declared_length = response.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Job page is too large to import.",
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    while True:
        _remaining_timeout(deadline)
        chunk = response.read(min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Job page is too large to import.",
            )
    return b"".join(chunks)


def _request_validated_destination(
    destination: ValidatedDestination,
    *,
    method: str,
    headers: dict[str, str],
    max_bytes: int,
    deadline: float,
) -> NetworkResponse:
    last_error: Exception | None = None
    for address in destination.addresses:
        connection: http.client.HTTPConnection
        timeout = _remaining_timeout(deadline)
        if destination.scheme == "https":
            connection = _PinnedHTTPSConnection(destination.hostname, destination.port, address, timeout)
        else:
            connection = _PinnedHTTPConnection(destination.hostname, destination.port, address, timeout)
        try:
            connection.request(method, destination.request_target, headers=headers)
            response = connection.getresponse()
            body = b"" if method == "HEAD" else _read_response_body(response, max_bytes=max_bytes, deadline=deadline)
            response_headers = tuple(
                (key, value)
                for key, value in response.getheaders()
                if key.lower() not in HOP_BY_HOP_HEADERS
            )
            return NetworkResponse(
                status_code=response.status,
                reason=response.reason or "",
                headers=response_headers,
                body=body,
            )
        except HTTPException:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            connection.close()
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="The job URL is temporarily unreachable. Retry or paste the job description manually.",
    ) from last_error


def _fetch_single_response(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str],
    max_bytes: int,
    deadline: float,
) -> tuple[ValidatedDestination, NetworkResponse]:
    destination = _validate_public_destination(url)
    host_header = f"[{destination.hostname}]" if ":" in destination.hostname else destination.hostname
    safe_headers = {
        "Host": host_header,
        "User-Agent": headers.get("User-Agent", BROWSER_USER_AGENT),
        "Accept": headers.get("Accept", "*/*"),
        "Accept-Language": headers.get("Accept-Language", "en-US,en;q=0.9"),
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    for name in ("Cookie", "Referer", "Origin"):
        if headers.get(name):
            safe_headers[name] = headers[name]
    return destination, _request_validated_destination(
        destination,
        method=method,
        headers=safe_headers,
        max_bytes=max_bytes,
        deadline=deadline,
    )


class JobHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._script_type: str | None = None
        self._script_buffer: list[str] = []
        self._script_chars = 0
        self._title_depth = 0
        self._title_parts: list[str] = []
        self.visible_parts: list[str] = []
        self.json_ld_blocks: list[str] = []
        self.embedded_json_blocks: list[str] = []
        self.metadata: dict[str, str] = {}
        self.canonical_url: str | None = None
        self.microdata_values: dict[str, list[str]] = {}
        self._active_microdata: list[MicrodataCapture] = []
        self._active_candidates: list[CandidateBlock] = []
        self.candidate_blocks: list[CandidateBlock] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        attr_text = " ".join(
            value for key, value in attrs if key and key.lower() in {"id", "class", "role", "itemprop"} and value
        ).lower()

        if tag in {"style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "script":
            script_type = attrs_dict.get("type", "").lower()
            if "ld+json" in script_type:
                self._script_type = "ld+json"
                self._script_buffer = []
                self._script_chars = 0
            elif "json" in script_type or attrs_dict.get("id", "").lower() in {"__next_data__", "__nuxt_data__"}:
                self._script_type = "embedded-json"
                self._script_buffer = []
                self._script_chars = 0
            else:
                self._skip_depth += 1
            return

        if tag == "meta":
            name = (attrs_dict.get("property") or attrs_dict.get("name") or attrs_dict.get("itemprop") or "").lower()
            content = attrs_dict.get("content", "").strip()
            if name and content and len(content) <= MAX_STRUCTURED_JSON_BYTES:
                self.metadata.setdefault(name, content)
        elif tag == "link" and "canonical" in attrs_dict.get("rel", "").lower():
            href = attrs_dict.get("href", "").strip()
            if href:
                self.canonical_url = href
        elif tag == "title":
            self._title_depth = 1

        for capture in self._active_microdata:
            capture.depth += 1

        for candidate in self._active_candidates:
            candidate.depth += 1

        itemprops = attrs_dict.get("itemprop", "").split()
        if self._skip_depth == 0 and self._script_type is None and itemprops:
            immediate_value = (
                attrs_dict.get("content")
                or attrs_dict.get("datetime")
                or attrs_dict.get("href")
                or ""
            ).strip()
            for itemprop in itemprops:
                normalized_itemprop = itemprop.lower()
                if immediate_value:
                    self.microdata_values.setdefault(normalized_itemprop, []).append(immediate_value)
                elif tag not in {"meta", "link", "img", "input", "br", "hr"}:
                    self._active_microdata.append(MicrodataCapture(itemprop=normalized_itemprop))

        if self._skip_depth == 0 and self._script_type is None and tag in CONTAINER_TAGS:
            if tag in {"main", "article"} or any(keyword in attr_text for keyword in CONTAINER_ATTR_KEYWORDS):
                self._active_candidates.append(CandidateBlock(tag=tag, attr_text=attr_text))
        if tag in BLOCK_TAGS:
            self.visible_parts.append("\n")
            for candidate in self._active_candidates:
                candidate.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._script_type in {"ld+json", "embedded-json"}:
            block = "".join(self._script_buffer)
            if self._script_type == "ld+json":
                self.json_ld_blocks.append(block)
            else:
                self.embedded_json_blocks.append(block)
            self._script_type = None
            self._script_buffer = []
            self._script_chars = 0
            return
        if tag in {"style", "noscript", "svg", "script"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth = 0
            title = " ".join(part.strip() for part in self._title_parts if part.strip()).strip()
            if title:
                self.metadata.setdefault("title", title)
            self._title_parts = []
        if tag in BLOCK_TAGS:
            self.visible_parts.append("\n")
            for candidate in self._active_candidates:
                candidate.parts.append("\n")

        remaining_microdata: list[MicrodataCapture] = []
        for capture in self._active_microdata:
            capture.depth -= 1
            if capture.depth <= 0:
                value = " ".join(part.strip() for part in capture.parts if part.strip()).strip()
                if value:
                    self.microdata_values.setdefault(capture.itemprop, []).append(value)
            else:
                remaining_microdata.append(capture)
        self._active_microdata = remaining_microdata

        remaining: list[CandidateBlock] = []
        for candidate in self._active_candidates:
            candidate.depth -= 1
            if candidate.depth <= 0:
                self.candidate_blocks.append(candidate)
            else:
                remaining.append(candidate)
        self._active_candidates = remaining

    def handle_data(self, data: str) -> None:
        if self._script_type in {"ld+json", "embedded-json"}:
            remaining = MAX_STRUCTURED_JSON_BYTES - self._script_chars
            if remaining > 0:
                fragment = data.encode("utf-8", errors="ignore")[:remaining].decode("utf-8", errors="ignore")
                self._script_buffer.append(fragment)
                self._script_chars += len(fragment.encode("utf-8", errors="ignore"))
            return
        if self._skip_depth == 0:
            if self._title_depth:
                self._title_parts.append(data)
            self.visible_parts.append(data)
            for candidate in self._active_candidates:
                candidate.parts.append(data)
            for capture in self._active_microdata:
                capture.parts.append(data)


@dataclass
class JobLinkCandidate:
    source_url: str
    title: str = ""


@dataclass
class PaginationCandidate:
    source_url: str
    text: str = ""
    attr_text: str = ""
    rel: str = ""


@dataclass
class JobListDiscoveryResult:
    links: list[JobLinkCandidate]
    next_page_url: str | None = None
    next_page_confidence: float = 0.0


@dataclass
class _AnchorCandidate:
    href: str
    text_parts: list[str] = field(default_factory=list)
    attr_text: str = ""
    rel: str = ""


class JobListLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._active_anchor: _AnchorCandidate | None = None
        self.links: list[JobLinkCandidate] = []
        self.pagination_links: list[PaginationCandidate] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        document_id = attrs_dict.get("data-document-id", "").strip()
        job_id = (
            attrs_dict.get("data-job-id", "").strip()
            or attrs_dict.get("data-jobid", "").strip()
            or attrs_dict.get("data-requisition-id", "").strip()
            or attrs_dict.get("data-requisitionid", "").strip()
        )
        job_key = (
            attrs_dict.get("data-jk", "").strip()
            or attrs_dict.get("data-vjk", "").strip()
            or attrs_dict.get("data-jobkey", "").strip()
            or attrs_dict.get("data-job-key", "").strip()
        )
        href = attrs_dict.get("href", "").strip()
        if document_id.isdigit() and not href:
            self.links.append(JobLinkCandidate(source_url=f"/job/{document_id}", title=""))
        if job_id.isdigit() and not href:
            title = attrs_dict.get("data-job-title", "").strip() or attrs_dict.get("aria-label", "").strip()
            self.links.append(JobLinkCandidate(source_url=f"/jobs/{job_id}", title=title))
        if job_key and not href:
            title = attrs_dict.get("data-job-title", "").strip() or attrs_dict.get("aria-label", "").strip()
            self.links.append(JobLinkCandidate(source_url=f"/viewjob?jk={job_key}", title=title))
        if tag == "a":
            if href:
                aria_label = attrs_dict.get("aria-label", "").strip()
                title = attrs_dict.get("title", "").strip()
                attr_text = " ".join(
                    value
                    for key, value in attrs
                    if key and key.lower() in {"id", "class", "data-test-id", "data-testid", "data-cy"} and value
                ).lower()
                self._active_anchor = _AnchorCandidate(
                    href=href,
                    text_parts=[aria_label, title],
                    attr_text=attr_text,
                    rel=attrs_dict.get("rel", "").lower(),
                )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "a" and self._active_anchor is not None:
            title = clean_job_text(" ".join(part for part in self._active_anchor.text_parts if part))
            self.links.append(
                JobLinkCandidate(
                    source_url=self._active_anchor.href,
                    title=title,
                )
            )
            self.pagination_links.append(
                PaginationCandidate(
                    source_url=self._active_anchor.href,
                    text=title,
                    attr_text=self._active_anchor.attr_text,
                    rel=self._active_anchor.rel,
                )
            )
            self._active_anchor = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._active_anchor is not None:
            text = data.strip()
            if text:
                self._active_anchor.text_parts.append(text)


def _normalize_job_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_at_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    suffix = "\n[Content shortened]"
    cutoff = max(1, limit - len(suffix))
    shortened = text[:cutoff]
    boundary = max(shortened.rfind("\n"), shortened.rfind(". "), shortened.rfind(" "))
    if boundary >= cutoff // 2:
        shortened = shortened[:boundary]
    return f"{shortened.rstrip()}{suffix}"[:limit]


def clean_job_text(text: str) -> str:
    return _truncate_at_boundary(_normalize_job_text(text), MAX_JOB_TEXT_CHARS)


def _is_access_gate_text(text: str) -> bool:
    text_lower = re.sub(r"\s+", " ", text.lower())
    access_hits = sum(1 for marker in ACCESS_GATE_MARKERS if marker in text_lower)
    job_hits = sum(1 for marker in JOB_CONTENT_MARKERS if marker in text_lower)
    return access_hits >= 3 and job_hits == 0


def _raise_if_access_gate_text(text: str) -> None:
    if _is_access_gate_text(text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The job URL returned a sign-in, verification, or bot-detection page instead of a job posting. "
                "Use the pasted job description fallback for this posting."
            ),
        )


def _visible_text_from_html(content: str) -> str:
    parser = JobHtmlParser()
    parser.feed(content)
    return clean_job_text("\n".join(parser.visible_parts))


def _normalize_discovered_url(base_url: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urljoin(base_url, href)
    absolute, _fragment = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    list_host = urlparse(base_url).hostname
    if list_host and parsed.hostname.lower() != list_host.lower():
        return None
    return absolute


def _job_key_url(base_url: str, job_key: str) -> str:
    parsed = urlparse(base_url)
    return urlunparse((parsed.scheme, parsed.netloc, "/viewjob", "", urlencode({"jk": job_key}), ""))


def _job_detail_link_score(url: str, title: str) -> int:
    parsed = urlparse(url)
    searchable = f"{parsed.path.lower()}?{parsed.query.lower()}"
    if any(marker in searchable for marker in NON_JOB_LINK_PATH_MARKERS):
        return 0
    score = 0
    if any(pattern.search(searchable) for pattern in JOB_DETAIL_PATTERNS):
        score += 100
    elif any(marker in searchable for marker in JOB_LINK_PATH_MARKERS):
        score += 45
    if parsed.path.lower().rstrip("/").endswith(("/jobs", "/job", "/careers", "/career")):
        score -= 40
    title_lower = title.lower()
    if any(word in title_lower for word in JOB_TITLE_WORDS):
        score += 20
    if 8 <= len(title_lower) <= 140 and " " in title_lower:
        score += 10
    if title_lower in {"jobs", "job search", "search jobs", "view jobs", "saved searches"}:
        score -= 60
    return max(score, 0)


def _job_identity_key(url: str) -> str:
    parsed = urlparse(url)
    searchable = parsed.path.lower()
    patterns = (
        r"/getjob/viewdetails/(\d+)(?:[/?#]|$)",
        r"/job/(\d+)(?:[/?#]|$)",
        r"/(?:[a-z]{2}(?:-[a-z]{2})?/)?jobs/([a-z0-9-]*\d[a-z0-9-]*)(?:[/?#]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, searchable, re.IGNORECASE)
        if match:
            return f"{parsed.hostname or ''}:job:{match.group(1)}"
    query = _query_dict(url)
    for key in ("jk", "vjk", "jobid", "job_id", "jobkey", "reqid", "requisitionid", "requisition_id"):
        value = query.get(key)
        if value:
            normalized_key = "jk" if key == "vjk" else key
            return f"{parsed.hostname or ''}:job:{normalized_key}:{value.lower()}"
    return url


def _candidate_preference_score(url: str, title: str) -> int:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    segments = [segment for segment in path.split("/") if segment]
    score = _job_detail_link_score(url, title)
    if title:
        score += 20
    if len(segments) >= 3:
        score += 12
    if len(path) > 20:
        score += min(len(path) // 12, 12)
    return score


def _query_dict(url: str) -> dict[str, str]:
    return dict(parse_qsl(urlparse(url).query, keep_blank_values=True))


def _score_next_page_candidate(base_url: str, candidate: PaginationCandidate) -> tuple[int, str | None]:
    normalized_url = _normalize_discovered_url(base_url, candidate.source_url)
    if not normalized_url or normalized_url == base_url:
        return 0, None
    if _job_detail_link_score(normalized_url, candidate.text) >= 50:
        return 0, None
    parsed = urlparse(normalized_url)
    searchable = f"{parsed.path.lower()}?{parsed.query.lower()}"
    if any(marker in searchable for marker in NON_JOB_LINK_PATH_MARKERS if marker not in {"/search/", "/search?"}):
        return 0, None

    score = 0
    rel = candidate.rel.lower()
    text = re.sub(r"\s+", " ", candidate.text.lower()).strip()
    attr_text = candidate.attr_text.lower()
    if "next" in rel:
        score += 100
    if text in NEXT_TEXT_VALUES or text in {"›", "»"}:
        score += 80
    if "next" in text:
        score += 60
    if "next" in attr_text:
        score += 55
    if any(marker in attr_text for marker in PAGINATION_ATTR_MARKERS):
        score += 20

    base_query = _query_dict(base_url)
    next_query = _query_dict(normalized_url)
    for key in NEXT_QUERY_PARAMS:
        if key in base_query and key in next_query:
            try:
                if int(next_query[key]) == int(base_query[key]) + 1:
                    score += 70
            except ValueError:
                pass
    for key in OFFSET_QUERY_PARAMS:
        if key in base_query and key in next_query:
            try:
                if int(next_query[key]) > int(base_query[key]):
                    score += 45
            except ValueError:
                pass

    return max(score, 0), normalized_url


def _synthetic_next_page_url(base_url: str) -> str | None:
    parsed = urlparse(base_url)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    for index, (key, value) in enumerate(query_items):
        if key in NEXT_QUERY_PARAMS:
            try:
                current = int(value)
            except ValueError:
                continue
            next_items = list(query_items)
            next_items[index] = (key, str(current + 1))
            return urlunparse(parsed._replace(query=urlencode(next_items, doseq=True)))
    return None


def extract_next_page_url_from_html(base_url: str, content: str) -> tuple[str | None, float]:
    parser = JobListLinkParser()
    parser.feed(content)
    best_score = 0
    best_url: str | None = None
    for candidate in parser.pagination_links:
        score, normalized_url = _score_next_page_candidate(base_url, candidate)
        if normalized_url and score > best_score:
            best_score = score
            best_url = normalized_url
    if best_url and best_score >= 60:
        return best_url, min(best_score / 120, 1.0)

    synthetic_url = _synthetic_next_page_url(base_url)
    if synthetic_url and synthetic_url != base_url:
        return synthetic_url, 0.55
    return None, 0.0


def _extract_job_link_candidates_from_text(base_url: str, content: str) -> list[JobLinkCandidate]:
    candidates: list[JobLinkCandidate] = []
    seen: set[str] = set()
    searchable_content = html.unescape(content)
    searchable_content = searchable_content.replace("\\/", "/")
    searchable_content = searchable_content.replace("\\u002F", "/").replace("\\u002f", "/")
    searchable_content = unquote(searchable_content)
    patterns = (
        r"https?://[^\s\"'<>]+",
        r"(?<![A-Za-z0-9])/GetJob/ViewDetails/\d+[^\s\"'<>]*",
        r"(?<![A-Za-z0-9])/job/\d+[^\s\"'<>]*",
        r"(?<![A-Za-z0-9])/[A-Za-z]{2}(?:-[A-Za-z]{2})?/jobs/[A-Za-z0-9][^\s\"'<>]*",
        r"(?<![A-Za-z0-9])/jobs/[A-Za-z0-9][^\s\"'<>]*",
        r"(?<![A-Za-z0-9])/viewjob\?[^\s\"'<>]*jk=[A-Za-z0-9._-]+[^\s\"'<>]*",
        r"(?<![A-Za-z0-9])/rc/clk\?[^\s\"'<>]*jk=[A-Za-z0-9._-]+[^\s\"'<>]*",
        r"(?<![A-Za-z0-9])(?:jk|vjk|jobkey|job_key)[\"']?\s*[:=]\s*[\"']([A-Za-z0-9._-]{8,})[\"']",
    )
    matches: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, searchable_content, re.IGNORECASE):
            raw_match = match.group(1) if match.lastindex else match.group(0)
            if match.lastindex:
                raw_match = _job_key_url(base_url, raw_match)
            matches.append((match.start(), raw_match))
    for _position, raw_value in sorted(matches, key=lambda item: item[0]):
        value = html.unescape(raw_value).rstrip("),.;")
        normalized_url = _normalize_discovered_url(base_url, value)
        if not normalized_url or normalized_url in seen:
            continue
        if _job_detail_link_score(normalized_url, "") < 50:
            continue
        seen.add(normalized_url)
        candidates.append(JobLinkCandidate(source_url=normalized_url, title=""))
    return candidates


def extract_job_links_from_html(base_url: str, content: str, max_results: int = 25) -> list[JobLinkCandidate]:
    parser = JobListLinkParser()
    parser.feed(content)
    candidates_by_identity: dict[str, tuple[int, int, JobLinkCandidate]] = {}
    seen_urls: set[str] = set()
    link_candidates = parser.links + _extract_job_link_candidates_from_text(base_url, content)
    for index, candidate in enumerate(link_candidates):
        normalized_url = _normalize_discovered_url(base_url, candidate.source_url)
        if not normalized_url or normalized_url in seen_urls:
            continue
        title = clean_job_text(candidate.title)
        score = _job_detail_link_score(normalized_url, title)
        if score < 50:
            continue
        seen_urls.add(normalized_url)
        identity_key = _job_identity_key(normalized_url)
        candidate_score = _candidate_preference_score(normalized_url, title)
        next_candidate = (candidate_score, index, JobLinkCandidate(source_url=normalized_url, title=title))
        current_candidate = candidates_by_identity.get(identity_key)
        if current_candidate is None:
            candidates_by_identity[identity_key] = next_candidate
        elif candidate_score > current_candidate[0]:
            candidates_by_identity[identity_key] = (candidate_score, current_candidate[1], next_candidate[2])
    scored_candidates = list(candidates_by_identity.values())
    scored_candidates.sort(key=lambda item: item[1])
    return [candidate for _score, _index, candidate in scored_candidates[:max_results]]


def discover_job_list_from_url(url: str, max_results: int = 25) -> JobListDiscoveryResult:
    links: list[JobLinkCandidate] = []
    next_page_url: str | None = None
    next_page_confidence = 0.0
    try:
        content_type, text = _fetch_url_text(url)
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Job list URL must return HTML.",
            )
        links = extract_job_links_from_html(url, text, max_results=max_results)
        next_page_url, next_page_confidence = extract_next_page_url_from_html(url, text)
    except RenderableFetchError:
        text = ""

    if not links:
        rendered_html = _fetch_rendered_html(url)
        links = extract_job_links_from_html(url, rendered_html, max_results=max_results)
        next_page_url, next_page_confidence = extract_next_page_url_from_html(url, rendered_html)
    if not links:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "No job posting links could be discovered from the list URL after static and rendered-page extraction."
            ),
        )
    return JobListDiscoveryResult(
        links=links,
        next_page_url=next_page_url,
        next_page_confidence=next_page_confidence,
    )


def discover_job_links_from_url(url: str, max_results: int = 25) -> list[JobLinkCandidate]:
    return discover_job_list_from_url(url, max_results=max_results).links


def _unique_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    output: list[str] = []
    previous = ""
    for line in lines:
        if not line:
            if output and output[-1]:
                output.append("")
            continue
        if line == previous:
            continue
        if any(marker in line.lower() for marker in FOOTER_MARKERS):
            break
        output.append(line)
        previous = line
    return _normalize_job_text("\n".join(output))


def _dedupe_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not line:
            if output and output[-1]:
                output.append("")
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(line)
    return _normalize_job_text("\n".join(output))


def _trim_footer_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    output: list[str] = []
    for line in lines:
        if any(marker in line.lower() for marker in FOOTER_MARKERS):
            break
        output.append(line)
    return _normalize_job_text("\n".join(output))


def _section_marker_count(text_lower: str) -> int:
    return sum(1 for marker in SECTION_MARKERS if marker in text_lower)


def _candidate_score(candidate: CandidateBlock, text: str) -> int:
    text_lower = text.lower()
    attr = candidate.attr_text
    marker_count = _section_marker_count(text_lower)
    score = 0
    if "job-detail-body" in attr:
        score += 60
    if "job-description" in attr or "jobdescription" in attr or "job_description" in attr:
        score += 55
    if "job-detail" in attr or "job_detail" in attr or "job-details" in attr:
        score += 35
    if "description" in attr and marker_count:
        score += 15
    if "posting" in attr:
        score += 20
    if "content" in attr and marker_count >= 2:
        score += 12
    if candidate.tag in {"main", "article"} and marker_count:
        score += 10
    score += marker_count * 12
    if "basic qualifications" in text_lower and "preferred qualifications" in text_lower:
        score += 25
    if len(text) >= 500:
        score += 10
    if len(text) >= 1500:
        score += 10
    if any(marker in text_lower for marker in FOOTER_MARKERS):
        score -= 8
    return score


def _dom_visible_text(node: Any) -> str:
    try:
        parts = node.xpath(
            ".//text()[not(ancestor::script) and not(ancestor::style) and "
            "not(ancestor::noscript) and not(ancestor::svg)]"
        )
    except (AttributeError, etree.XPathError):
        return ""
    return _normalize_job_text("\n".join(str(part) for part in parts if str(part).strip()))


def _dom_attr_text(node: Any) -> str:
    attributes = getattr(node, "attrib", {})
    return " ".join(
        str(attributes.get(key, ""))
        for key in ("id", "class", "role", "itemprop", "itemtype", "data-testid")
        if attributes.get(key)
    ).lower()


def _dom_subtree_score(node: Any, text: str) -> int:
    if len(text) < 160:
        return 0
    text_lower = text.lower()
    attr_text = _dom_attr_text(node)
    marker_count = _section_marker_count(text_lower)
    strong_attr_markers = (
        "job-detail-body",
        "job-description",
        "job_description",
        "jobdescription",
        "job-details",
        "job_detail",
        "job-posting",
        "jobposting",
        "jobdescriptiontext",
    )
    has_strong_attr = any(marker in attr_text for marker in strong_attr_markers)
    tag = str(getattr(node, "tag", "")).lower()
    try:
        links = node.xpath(".//a")
        link_text_length = sum(len(_normalize_job_text(link.text_content())) for link in links)
        descendant_count = max(1, len(node.xpath(".//*")))
        heading_count = len(node.xpath(".//h1|.//h2|.//h3|.//h4"))
        paragraph_count = len(node.xpath(".//p"))
        list_item_count = len(node.xpath(".//li"))
        control_count = len(node.xpath(".//button|.//input|.//select|.//form"))
    except (AttributeError, etree.XPathError):
        return 0
    link_density = link_text_length / max(1, len(text))
    text_density = len(text) / descendant_count

    if not has_strong_attr and marker_count == 0 and tag not in {"main", "article"}:
        return 0
    score = 0
    if "schema.org/jobposting" in attr_text or "jobposting" in attr_text:
        score += 75
    elif has_strong_attr:
        score += 50
    elif "posting" in attr_text:
        score += 20
    if tag in {"main", "article"}:
        score += 12
    score += marker_count * 14
    score += min(18, heading_count * 3)
    score += min(18, paragraph_count * 2)
    score += min(15, list_item_count)
    if len(text) >= 500:
        score += 8
    if len(text) >= 1_500:
        score += 8
    if text_density >= 35:
        score += 8
    if ("content" in attr_text or "description" in attr_text) and marker_count:
        score += 8
    if link_density > 0.45:
        score -= 70
    elif link_density > 0.20:
        score -= 30
    elif link_density > 0.10:
        score -= 12
    score -= min(25, control_count * 3)
    if any(marker in attr_text for marker in ("nav", "footer", "related", "recommend", "search-results")):
        score -= 45
    return max(0, score)


def _best_dom_candidate_text_and_score(content: str) -> tuple[str, int] | None:
    parser = lxml_html.HTMLParser(recover=True, no_network=True, huge_tree=False)
    try:
        root = lxml_html.fromstring(content, parser=parser)
    except (etree.ParserError, ValueError, TypeError, UnicodeError):
        return None

    best_text: str | None = None
    best_score = 0
    evaluated = 0
    for node in root.iter():
        tag = str(getattr(node, "tag", "")).lower()
        if tag not in CONTAINER_TAGS:
            continue
        evaluated += 1
        if evaluated > MAX_DOM_CANDIDATES:
            break
        text = _dom_visible_text(node)
        score = _dom_subtree_score(node, text)
        if score <= best_score:
            continue
        best_text = text
        best_score = score
    if best_text and best_score >= 45:
        return best_text, best_score
    return None


def _best_candidate_text_and_score(candidates: list[CandidateBlock]) -> tuple[str, int] | None:
    best_text: str | None = None
    best_score = 0
    for candidate in candidates:
        text = _unique_lines("\n".join(candidate.parts))
        if len(text) < 200:
            continue
        score = _candidate_score(candidate, text)
        if score > best_score:
            best_score = score
            best_text = text
    if best_text and best_score >= 35:
        return best_text, best_score
    return None


def _best_candidate_text(candidates: list[CandidateBlock]) -> str | None:
    best = _best_candidate_text_and_score(candidates)
    return best[0] if best else None


def _heading_window_text(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    start = None
    for index, line in enumerate(lines):
        lowered = line.lower().strip(":")
        if lowered in SECTION_MARKERS or any(lowered.startswith(marker) for marker in SECTION_MARKERS):
            start = index
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        lowered = lines[index].lower()
        if any(marker in lowered for marker in FOOTER_MARKERS):
            end = index
            break
    window = _normalize_job_text("\n".join(lines[start:end]))
    return window if len(window) >= 200 else None


def strip_html_fragment(value: str) -> str:
    parser = JobHtmlParser()
    parser.feed(value)
    text = _normalize_job_text("\n".join(parser.visible_parts))
    return text or _normalize_job_text(re.sub(r"<[^>]+>", " ", value))


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _walk_json_objects(value: Any) -> Iterator[dict[str, Any]]:
    visited = 0

    def walk(current: Any, depth: int) -> Iterator[dict[str, Any]]:
        nonlocal visited
        if depth > MAX_STRUCTURED_JSON_DEPTH or visited >= MAX_STRUCTURED_JSON_OBJECTS:
            return
        if isinstance(current, dict):
            visited += 1
            yield current
            for nested in current.values():
                yield from walk(nested, depth + 1)
        elif isinstance(current, list):
            for nested in current:
                yield from walk(nested, depth + 1)

    yield from walk(value, 0)


def _flatten_json_ld(value: Any) -> list[dict[str, Any]]:
    return list(_walk_json_objects(value))


def _load_json_block(block: str) -> Any | None:
    if not block.strip() or len(block.encode("utf-8", errors="ignore")) > MAX_STRUCTURED_JSON_BYTES:
        return None
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        return None


def _mapping_lookup(mapping: dict[str, Any], *aliases: str) -> Any:
    normalized = {_normalized_key(str(key)): value for key, value in mapping.items()}
    for alias in aliases:
        value = normalized.get(_normalized_key(alias))
        if value is not None and value != "":
            return value
    return None


def _text_values(value: Any) -> list[str]:
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (str, int, float)):
        text = strip_html_fragment(str(value))
        return [text] if text else []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(_text_values(item))
        return output
    if isinstance(value, dict):
        preferred = _mapping_lookup(value, "name", "value", "label", "description")
        return _text_values(preferred)
    return []


def _first_text(value: Any) -> str | None:
    values = _text_values(value)
    return values[0] if values else None


def _organization_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _first_text(_mapping_lookup(value, "name", "legalName", "companyName"))
    return _first_text(value)


def _location_values(value: Any) -> list[str]:
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(_location_values(item))
        return list(dict.fromkeys(output))
    if isinstance(value, dict):
        address = _mapping_lookup(value, "address")
        if isinstance(address, dict):
            value = address
        fields = [
            _first_text(_mapping_lookup(value, "name")),
            _first_text(_mapping_lookup(value, "streetAddress")),
            _first_text(_mapping_lookup(value, "addressLocality", "city")),
            _first_text(_mapping_lookup(value, "addressRegion", "state", "region")),
            _first_text(_mapping_lookup(value, "postalCode")),
            _organization_name(_mapping_lookup(value, "addressCountry", "country")),
        ]
        text = ", ".join(dict.fromkeys(item for item in fields if item))
        return [text] if text else []
    return _text_values(value)


def _salary_values(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return _text_values(value)
    currency = _first_text(_mapping_lookup(value, "currency", "salaryCurrency"))
    amount = _mapping_lookup(value, "value")
    if isinstance(amount, dict):
        minimum = _first_text(_mapping_lookup(amount, "minValue", "minimum"))
        maximum = _first_text(_mapping_lookup(amount, "maxValue", "maximum"))
        unit = _first_text(_mapping_lookup(amount, "unitText", "unit"))
        if minimum and maximum:
            range_text = f"{minimum}-{maximum}"
        else:
            range_text = minimum or maximum or _first_text(_mapping_lookup(amount, "value"))
        text = " ".join(item for item in (currency, range_text, unit) if item)
        return [text] if text else []
    text = " ".join(item for item in (currency, _first_text(amount)) if item)
    return [text] if text else []


def _append_section(sections: dict[str, list[str]], name: str, values: list[str]) -> None:
    existing = sections.setdefault(name, [])
    seen = {item.lower() for item in existing}
    for value in values:
        cleaned = _normalize_job_text(value)
        if cleaned and cleaned.lower() not in seen:
            existing.append(cleaned)
            seen.add(cleaned.lower())
    if not existing:
        sections.pop(name, None)


def _section_for_heading(line: str) -> str | None:
    if len(line) > 90:
        return None
    normalized = re.sub(r"^[#*\-\s]+|[:\s]+$", "", line.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    for section, aliases in SECTION_HEADING_ALIASES.items():
        if normalized in aliases:
            return section
    return None


def normalize_job_sections(text: str) -> dict[str, list[str]]:
    lines = [line.strip() for line in _normalize_job_text(text).splitlines()]
    sections: dict[str, list[str]] = {}
    current_section = "summary"
    found_heading = False
    for line in lines:
        if not line:
            continue
        if any(marker in line.lower() for marker in FOOTER_MARKERS):
            break
        heading_section = _section_for_heading(line)
        if heading_section:
            current_section = heading_section
            found_heading = True
            continue
        _append_section(sections, current_section, [line])
    if not found_heading:
        normalized = _trim_footer_text(text)
        return {"summary": [normalized]} if normalized else {}
    return sections


def _truncate_section_value(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return _truncate_at_boundary(value, limit)


def _compose_focused_text(
    *,
    title: str | None,
    company: str | None,
    location: str | None,
    sections: dict[str, list[str]],
) -> tuple[str, bool]:
    header = "\n".join(
        line
        for line in (
            f"Title: {title}" if title else None,
            f"Company: {company}" if company else None,
            f"Location: {location}" if location else None,
        )
        if line
    )
    normalized_sections = {
        key: list(dict.fromkeys(item for item in values if item.strip()))
        for key, values in sections.items()
        if any(item.strip() for item in values)
    }

    def render(rendered_sections: dict[str, str]) -> str:
        blocks = [header] if header else []
        for section_name in SECTION_DISPLAY_NAMES:
            value = rendered_sections.get(section_name)
            if value:
                blocks.append(f"{SECTION_DISPLAY_NAMES[section_name]}\n{value}")
        for section_name, value in rendered_sections.items():
            if section_name not in SECTION_DISPLAY_NAMES and value:
                blocks.append(f"{section_name.replace('_', ' ').title()}\n{value}")
        return _normalize_job_text("\n\n".join(blocks))

    joined_sections = {key: "\n".join(values) for key, values in normalized_sections.items()}
    full_text = render(joined_sections)
    if len(full_text) <= MAX_JOB_TEXT_CHARS:
        return full_text, False

    section_names = list(joined_sections)
    label_cost = sum(len(SECTION_DISPLAY_NAMES.get(name, name)) + 2 for name in section_names)
    available = max(1_000, MAX_JOB_TEXT_CHARS - len(header) - label_cost - 32)
    total_weight = sum(SECTION_PRIORITY_WEIGHTS.get(name, 0.5) for name in section_names) or 1.0
    shortened_sections: dict[str, str] = {}
    for name, value in joined_sections.items():
        weighted_budget = int(available * SECTION_PRIORITY_WEIGHTS.get(name, 0.5) / total_weight)
        shortened_sections[name] = _truncate_section_value(value, max(300, weighted_budget))
    return _truncate_at_boundary(render(shortened_sections), MAX_JOB_TEXT_CHARS), True


def _candidate_confidence(candidate: JobExtractionCandidate, structural_score: int = 0) -> float:
    bases = {
        "json_ld": 0.72,
        "microdata": 0.62,
        "embedded_json": 0.58,
        "metadata": 0.40,
        "dom_candidate": min(0.72, 0.42 + structural_score / 300),
        "heading_window": 0.52,
        "visible_text": 0.36,
        "plain_text": 0.65,
    }
    confidence = 0.68 if candidate.method.startswith("ats_") else bases.get(candidate.method, 0.35)
    text_lower = candidate.focused_text.lower()
    marker_count = _section_marker_count(text_lower)
    confidence += min(0.16, marker_count * 0.04)
    if len(candidate.focused_text) >= 200:
        confidence += 0.04
    if len(candidate.focused_text) >= 500:
        confidence += 0.05
    if len(candidate.focused_text) >= 1_500:
        confidence += 0.04
    if candidate.title:
        confidence += 0.05
    if candidate.company:
        confidence += 0.03
    if candidate.location:
        confidence += 0.01
    meaningful_sections = sum(
        1
        for name in ("responsibilities", "required_qualifications", "preferred_qualifications", "experience", "education")
        if candidate.sections.get(name)
    )
    confidence += min(0.10, meaningful_sections * 0.025)
    link_lines = sum(1 for line in candidate.focused_text.splitlines() if "http://" in line or "https://" in line)
    if link_lines >= 5:
        confidence -= 0.12
    return round(max(0.0, min(confidence, 0.99)), 2)


def _finalize_candidate(candidate: JobExtractionCandidate, structural_score: int = 0) -> JobExtractionCandidate:
    candidate.confidence = _candidate_confidence(candidate, structural_score)
    if not candidate.title:
        candidate.warnings.append("missing_title")
    if not candidate.company:
        candidate.warnings.append("missing_company")
    meaningful_sections = sum(1 for name in candidate.sections if name != "summary")
    if meaningful_sections < 2:
        candidate.warnings.append("limited_job_sections")
    if candidate.method == "visible_text":
        candidate.warnings.append("broad_visible_text")
    if candidate.confidence < REVIEW_EXTRACTION_CONFIDENCE:
        candidate.warnings.append("review_recommended")
    candidate.warnings = list(dict.fromkeys(candidate.warnings))
    return candidate


def _make_text_candidate(
    method: str,
    text: str,
    *,
    source_url: str,
    canonical_url: str | None,
    title: str | None,
    company: str | None,
    location: str | None,
    raw_visible_text: str,
    structural_score: int = 0,
) -> JobExtractionCandidate | None:
    cleaned = _trim_footer_text(_unique_lines(text))
    if len(cleaned) < 80:
        return None
    sections = normalize_job_sections(cleaned)
    focused_text, shortened = _compose_focused_text(
        title=title,
        company=company,
        location=location,
        sections=sections,
    )
    candidate = JobExtractionCandidate(
        method=method,
        source_url=source_url,
        canonical_url=canonical_url,
        title=title,
        company=company,
        location=location,
        sections=sections,
        focused_text=focused_text,
        raw_visible_text=raw_visible_text,
        warnings=["content_shortened"] if shortened else [],
    )
    return _finalize_candidate(candidate, structural_score)


def _candidate_from_mapping(
    mapping: dict[str, Any],
    *,
    method: str,
    source_url: str,
    canonical_url: str | None,
    raw_visible_text: str,
    require_job_type: bool = False,
) -> JobExtractionCandidate | None:
    type_value = _mapping_lookup(mapping, "@type", "type")
    types = [item.lower() for item in _text_values(type_value)]
    if require_job_type and "jobposting" not in types:
        return None
    normalized_keys = {_normalized_key(str(key)) for key in mapping}
    job_signal_keys = {
        "jobid", "jobtitle", "positiontitle", "requisitionid", "hiringorganization",
        "companyname", "responsibilities", "qualifications", "requiredqualifications",
        "preferredqualifications", "experiencerequirements", "employmenttype", "joblocation",
    }
    if method == "embedded_json" and not normalized_keys.intersection(job_signal_keys):
        return None

    title = _first_text(_mapping_lookup(mapping, "title", "jobTitle", "positionTitle", "name"))
    company = _organization_name(
        _mapping_lookup(mapping, "hiringOrganization", "company", "companyName", "organization")
    )
    locations = _location_values(_mapping_lookup(mapping, "jobLocation", "location", "formattedLocation"))
    location = "; ".join(locations) if locations else None
    sections: dict[str, list[str]] = {}
    _append_section(sections, "summary", _text_values(_mapping_lookup(mapping, "description", "jobDescription", "summary")))
    _append_section(sections, "responsibilities", _text_values(_mapping_lookup(mapping, "responsibilities", "duties")))
    _append_section(
        sections,
        "required_qualifications",
        _text_values(_mapping_lookup(mapping, "qualifications", "requiredQualifications", "requirements")),
    )
    _append_section(
        sections,
        "preferred_qualifications",
        _text_values(_mapping_lookup(mapping, "preferredQualifications", "preferredSkills")),
    )
    _append_section(sections, "experience", _text_values(_mapping_lookup(mapping, "experienceRequirements", "requiredExperience")))
    _append_section(sections, "education", _text_values(_mapping_lookup(mapping, "educationRequirements", "education")))
    _append_section(sections, "skills", _text_values(_mapping_lookup(mapping, "skills", "requiredSkills")))
    _append_section(sections, "certifications", _text_values(_mapping_lookup(mapping, "certifications", "certification")))
    _append_section(sections, "compensation", _salary_values(_mapping_lookup(mapping, "baseSalary", "salary", "salaryRange")))
    work_arrangement = _text_values(_mapping_lookup(mapping, "jobLocationType", "workplaceType", "remoteType"))
    _append_section(sections, "location_and_work_arrangement", [*locations, *work_arrangement])
    application_details: list[str] = []
    for label, aliases in (
        ("Employment type", ("employmentType",)),
        ("Date posted", ("datePosted",)),
        ("Application deadline", ("validThrough", "applicationDeadline")),
        ("Industry", ("industry",)),
        ("Category", ("occupationalCategory",)),
    ):
        value = _first_text(_mapping_lookup(mapping, *aliases))
        if value:
            application_details.append(f"{label}: {value}")
    _append_section(sections, "application_details", application_details)

    body_length = sum(len(item) for values in sections.values() for item in values)
    if body_length < 80:
        return None
    focused_text, shortened = _compose_focused_text(
        title=title,
        company=company,
        location=location,
        sections=sections,
    )
    candidate = JobExtractionCandidate(
        method=method,
        source_url=source_url,
        canonical_url=canonical_url,
        title=title,
        company=company,
        location=location,
        sections=sections,
        focused_text=focused_text,
        raw_visible_text=raw_visible_text,
        warnings=["content_shortened"] if shortened else [],
    )
    return _finalize_candidate(candidate)


def _safe_canonical_url(source_url: str, value: str | None) -> str | None:
    if not value:
        return None
    resolved = urljoin(source_url, value) if source_url else value
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return None
    return resolved


def _metadata_value(parser: JobHtmlParser, *keys: str) -> str | None:
    for key in keys:
        value = parser.metadata.get(key.lower())
        if value:
            return strip_html_fragment(value)
    return None


def _structured_candidates(
    parser: JobHtmlParser,
    *,
    source_url: str,
    canonical_url: str | None,
    raw_visible_text: str,
) -> list[JobExtractionCandidate]:
    candidates: list[JobExtractionCandidate] = []
    for block in parser.json_ld_blocks:
        payload = _load_json_block(block)
        if payload is None:
            continue
        for item in _flatten_json_ld(payload):
            candidate = _candidate_from_mapping(
                item,
                method="json_ld",
                source_url=source_url,
                canonical_url=canonical_url,
                raw_visible_text=raw_visible_text,
                require_job_type=True,
            )
            if candidate:
                candidates.append(candidate)

    if parser.microdata_values:
        microdata_mapping = {key: values if len(values) > 1 else values[0] for key, values in parser.microdata_values.items()}
        candidate = _candidate_from_mapping(
            microdata_mapping,
            method="microdata",
            source_url=source_url,
            canonical_url=canonical_url,
            raw_visible_text=raw_visible_text,
        )
        if candidate:
            candidates.append(candidate)

    for block in parser.embedded_json_blocks:
        payload = _load_json_block(block)
        if payload is None:
            continue
        for item in _walk_json_objects(payload):
            candidate = _candidate_from_mapping(
                item,
                method="embedded_json",
                source_url=source_url,
                canonical_url=canonical_url,
                raw_visible_text=raw_visible_text,
            )
            if candidate:
                candidates.append(candidate)

    metadata_mapping = {
        "title": _metadata_value(parser, "og:title", "twitter:title", "title"),
        "description": _metadata_value(parser, "og:description", "twitter:description", "description"),
        "company": _metadata_value(parser, "job:company", "company"),
        "location": _metadata_value(parser, "job:location", "location"),
    }
    metadata_candidate = _candidate_from_mapping(
        metadata_mapping,
        method="metadata",
        source_url=source_url,
        canonical_url=canonical_url,
        raw_visible_text=raw_visible_text,
    )
    if metadata_candidate:
        candidates.append(metadata_candidate)
    return candidates


def _jobposting_text_from_json_ld(blocks: list[str]) -> str | None:
    parser = JobHtmlParser()
    parser.json_ld_blocks = blocks
    candidates = _structured_candidates(parser, source_url="", canonical_url=None, raw_visible_text="")
    json_ld_candidates = [candidate for candidate in candidates if candidate.method == "json_ld"]
    if not json_ld_candidates:
        return None
    return max(json_ld_candidates, key=lambda item: item.confidence).focused_text


def _result_from_candidate(candidate: JobExtractionCandidate) -> JobExtractionResult:
    return JobExtractionResult(
        source_url=candidate.source_url,
        canonical_url=candidate.canonical_url,
        title=candidate.title,
        company=candidate.company,
        location=candidate.location,
        sections=candidate.sections,
        focused_text=candidate.focused_text,
        raw_visible_text=candidate.raw_visible_text,
        extraction_method=candidate.method,
        confidence=candidate.confidence,
        warnings=list(candidate.warnings),
        extractor_version=JOB_EXTRACTOR_VERSION,
    )


def _ats_adapter_candidates(
    content: str,
    *,
    source_url: str,
    canonical_url: str | None,
    raw_visible_text: str,
) -> list[JobExtractionCandidate]:
    candidates: list[JobExtractionCandidate] = []
    for extraction in extract_from_adapters(url=source_url, html=content):
        extraction_canonical_url = _safe_canonical_url(
            source_url,
            extraction.canonical_url,
        ) or canonical_url
        candidate = _candidate_from_mapping(
            extraction.mapping,
            method=f"ats_{extraction.adapter_name}",
            source_url=source_url,
            canonical_url=extraction_canonical_url,
            raw_visible_text=raw_visible_text,
        )
        if candidate is None:
            continue
        candidate.warnings = list(
            dict.fromkeys(
                [
                    *candidate.warnings,
                    *extraction.warnings,
                    f"source_adapter:{extraction.adapter_name}",
                ]
            )
        )
        candidates.append(candidate)
    return candidates


def extract_job_result_from_html(content: str, *, source_url: str = "") -> JobExtractionResult:
    if len(content.encode("utf-8", errors="ignore")) > MAX_RENDERED_HTML_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Job page HTML is too large to parse.",
        )
    parser = JobHtmlParser()
    parser.feed(content)
    raw_unbounded = _dedupe_lines("\n".join(parser.visible_parts))
    _raise_if_access_gate_text(raw_unbounded)
    if len(raw_unbounded) < 80 and not parser.json_ld_blocks and not parser.embedded_json_blocks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not extract enough job text from the URL.",
        )
    raw_visible_text = _truncate_at_boundary(raw_unbounded, MAX_JOB_TEXT_CHARS)
    canonical_url = _safe_canonical_url(source_url, parser.canonical_url)
    title = _metadata_value(parser, "og:title", "twitter:title", "title")
    company = _metadata_value(parser, "job:company", "company")
    location = _metadata_value(parser, "job:location", "location")
    candidates = _ats_adapter_candidates(
        content,
        source_url=source_url,
        canonical_url=canonical_url,
        raw_visible_text=raw_visible_text,
    )
    candidates.extend(_structured_candidates(
        parser,
        source_url=source_url,
        canonical_url=canonical_url,
        raw_visible_text=raw_visible_text,
    ))

    dom_candidate = _best_dom_candidate_text_and_score(content)
    if dom_candidate:
        text, structural_score = dom_candidate
        candidate = _make_text_candidate(
            "dom_candidate",
            text,
            source_url=source_url,
            canonical_url=canonical_url,
            title=title,
            company=company,
            location=location,
            raw_visible_text=raw_visible_text,
            structural_score=structural_score,
        )
        if candidate:
            candidates.append(candidate)

    best_dom = _best_candidate_text_and_score(parser.candidate_blocks)
    if best_dom:
        text, structural_score = best_dom
        candidate = _make_text_candidate(
            "dom_candidate",
            text,
            source_url=source_url,
            canonical_url=canonical_url,
            title=title,
            company=company,
            location=location,
            raw_visible_text=raw_visible_text,
            structural_score=structural_score,
        )
        if candidate:
            candidates.append(candidate)

    trimmed_visible = _trim_footer_text(raw_unbounded)
    heading_text = _heading_window_text(trimmed_visible)
    if heading_text:
        candidate = _make_text_candidate(
            "heading_window",
            heading_text,
            source_url=source_url,
            canonical_url=canonical_url,
            title=title,
            company=company,
            location=location,
            raw_visible_text=raw_visible_text,
        )
        if candidate:
            candidates.append(candidate)
    if len(trimmed_visible) >= 200:
        candidate = _make_text_candidate(
            "visible_text",
            trimmed_visible,
            source_url=source_url,
            canonical_url=canonical_url,
            title=title,
            company=company,
            location=location,
            raw_visible_text=raw_visible_text,
        )
        if candidate:
            candidates.append(candidate)

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not extract enough job text from the URL.",
        )
    winner = max(candidates, key=lambda item: (item.confidence, len(item.focused_text)))
    if len(raw_unbounded) > MAX_JOB_TEXT_CHARS:
        winner.warnings = list(dict.fromkeys([*winner.warnings, "raw_content_shortened"]))
    return _result_from_candidate(winner)


def _result_from_plain_text(text: str, *, source_url: str) -> JobExtractionResult:
    raw_unbounded = _normalize_job_text(text)
    _raise_if_access_gate_text(raw_unbounded)
    if len(raw_unbounded) < 80:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not extract enough job text from the URL.",
        )
    raw_visible_text = _truncate_at_boundary(raw_unbounded, MAX_JOB_TEXT_CHARS)
    candidate = _make_text_candidate(
        "plain_text",
        raw_unbounded,
        source_url=source_url,
        canonical_url=None,
        title=None,
        company=None,
        location=None,
        raw_visible_text=raw_visible_text,
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Could not extract enough job text from the URL.",
        )
    if len(raw_unbounded) > MAX_JOB_TEXT_CHARS:
        candidate.warnings = list(dict.fromkeys([*candidate.warnings, "raw_content_shortened"]))
    return _result_from_candidate(candidate)


def extract_job_description_from_html(content: str) -> str:
    return extract_job_result_from_html(content).focused_text


def extract_job_page_text_from_html(content: str) -> str:
    result = extract_job_result_from_html(content)
    return result.raw_visible_text or result.focused_text


def _fetch_url_text(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,text/plain,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    deadline = time.monotonic() + STATIC_FETCH_TOTAL_TIMEOUT_SECONDS
    current_url = url
    visited: set[str] = set()
    total_response_bytes = 0
    response: NetworkResponse | None = None
    for redirect_count in range(MAX_REDIRECTS + 1):
        remaining_bytes = MAX_STATIC_TOTAL_BYTES - total_response_bytes
        if remaining_bytes <= 0:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Job URL responses exceeded the allowed total size.",
            )
        destination, response = _fetch_single_response(
            current_url,
            headers=headers,
            max_bytes=remaining_bytes,
            deadline=deadline,
        )
        total_response_bytes += len(response.body)
        if destination.url in visited:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Job URL redirect loop detected.")
        visited.add(destination.url)
        if response.status_code not in REDIRECT_STATUS_CODES:
            break
        location = response.header("location")
        if not location:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Job URL returned an invalid redirect.")
        if redirect_count >= MAX_REDIRECTS:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Job URL returned too many redirects.")
        current_url = validate_public_job_url(urljoin(destination.url, location))

    if response is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Job URL did not return a response.")
    if response.status_code in {401, 403, 429, 503}:
        raise RenderableFetchError(response.status_code, response.reason)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Job URL returned HTTP {response.status_code}.",
        )

    content_type = response.header("content-type")
    if "text/html" not in content_type and "text/plain" not in content_type and "application/xhtml" not in content_type:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Job URL did not return HTML or text.")

    charset = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.IGNORECASE)
    if match:
        charset = match.group(1)
    text = response.body.decode(charset, errors="ignore")
    return content_type, text


def _block_browser_route(
    route,
    budget: RenderedFetchBudget,
    reason: str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> None:
    if budget.blocked_reason is None:
        budget.blocked_reason = reason
        budget.blocked_status_code = status_code
    route.abort()


def _normalized_job_mapping_from_json(mapping: dict[str, Any]) -> dict[str, Any] | None:
    type_value = _mapping_lookup(mapping, "@type", "type")
    types = [item.lower() for item in _text_values(type_value)]
    is_job_posting = "jobposting" in types
    method = "json_ld" if is_job_posting else "embedded_json"
    candidate = _candidate_from_mapping(
        mapping,
        method=method,
        source_url="",
        canonical_url=None,
        raw_visible_text="",
        require_job_type=is_job_posting,
    )
    if candidate is None:
        return None
    normalized: dict[str, Any] = {
        "jobId": _first_text(_mapping_lookup(mapping, "jobId", "id", "requisitionId")) or "rendered-response",
        "jobTitle": candidate.title,
        "companyName": candidate.company,
        "formattedLocation": candidate.location,
        "jobDescription": candidate.focused_text,
    }
    return {key: value for key, value in normalized.items() if value}


def _capture_job_json_response(response: NetworkResponse, budget: RenderedFetchBudget) -> None:
    if len(budget.captured_json_blocks) >= MAX_RENDERED_JSON_RESPONSES:
        return
    content_type = response.header("content-type").lower()
    if "application/json" not in content_type and "+json" not in content_type and "text/json" not in content_type:
        return
    if response.status_code < 200 or response.status_code >= 300:
        return
    if len(response.body) > MAX_STRUCTURED_JSON_BYTES:
        return
    charset = "utf-8"
    charset_match = re.search(r"charset=([\w.-]+)", content_type, re.IGNORECASE)
    if charset_match:
        charset = charset_match.group(1)
    payload = _load_json_block(response.body.decode(charset, errors="ignore"))
    if payload is None:
        return
    existing = set(budget.captured_json_blocks)
    for mapping in _walk_json_objects(payload):
        budget.captured_json_objects += 1
        if budget.captured_json_objects > MAX_RENDERED_JSON_OBJECTS:
            return
        normalized = _normalized_job_mapping_from_json(mapping)
        if normalized is None:
            continue
        block = json.dumps(normalized, ensure_ascii=True, separators=(",", ":"))
        block_bytes = len(block.encode("utf-8"))
        if block in existing:
            continue
        if budget.captured_json_bytes + block_bytes > MAX_RENDERED_CAPTURED_JSON_BYTES:
            return
        budget.captured_json_blocks.append(block)
        budget.captured_json_bytes += block_bytes
        existing.add(block)
        if len(budget.captured_json_blocks) >= MAX_RENDERED_JSON_RESPONSES:
            return


def _inject_captured_json(rendered_html: str, blocks: list[str]) -> str:
    if not blocks:
        return rendered_html
    available = MAX_RENDERED_HTML_BYTES - len(rendered_html.encode("utf-8", errors="ignore"))
    if available <= 0:
        return rendered_html
    scripts: list[str] = []
    used = 0
    for block in blocks:
        safe_block = block.replace("</", "<\\/")
        script = f'<script type="application/json" data-dalijob-captured="true">{safe_block}</script>'
        script_bytes = len(script.encode("utf-8"))
        if used + script_bytes > available:
            break
        scripts.append(script)
        used += script_bytes
    if not scripts:
        return rendered_html
    injection = "".join(scripts)
    closing_body = rendered_html.lower().rfind("</body>")
    if closing_body >= 0:
        return f"{rendered_html[:closing_body]}{injection}{rendered_html[closing_body:]}"
    return f"{rendered_html}{injection}"


def _proxy_browser_route(route, budget: RenderedFetchBudget) -> None:
    request = route.request
    budget.requests += 1
    if budget.requests > MAX_RENDERED_SUBREQUESTS:
        _block_browser_route(
            route,
            budget,
            "Rendered job page exceeded the allowed network request count.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
        return
    if time.monotonic() >= budget.deadline:
        _block_browser_route(
            route,
            budget,
            "Rendered job page exceeded the allowed fetch time.",
            status.HTTP_504_GATEWAY_TIMEOUT,
        )
        return

    try:
        safe_url = validate_public_job_url(request.url)
    except HTTPException as exc:
        _block_browser_route(route, budget, str(exc.detail), exc.status_code)
        return

    if request.resource_type in {"image", "media", "font"}:
        route.abort()
        return
    if request.method.upper() not in {"GET", "HEAD"}:
        route.abort()
        return

    remaining_bytes = MAX_RENDERED_TOTAL_BYTES - budget.response_bytes
    if remaining_bytes <= 0:
        _block_browser_route(
            route,
            budget,
            "Rendered job page exceeded the allowed response size.",
            status.HTTP_413_CONTENT_TOO_LARGE,
        )
        return

    raw_headers = request.headers
    request_headers = {
        "User-Agent": raw_headers.get("user-agent", BROWSER_USER_AGENT),
        "Accept": raw_headers.get("accept", "*/*"),
        "Accept-Language": raw_headers.get("accept-language", "en-US,en;q=0.9"),
        "Cookie": raw_headers.get("cookie", ""),
        "Referer": raw_headers.get("referer", ""),
        "Origin": raw_headers.get("origin", ""),
    }
    try:
        destination, response = _fetch_single_response(
            safe_url,
            method=request.method.upper(),
            headers=request_headers,
            max_bytes=min(MAX_JOB_PAGE_BYTES, remaining_bytes),
            deadline=budget.deadline,
        )
        response_headers: dict[str, str] = {}
        for key, value in response.headers:
            lowered = key.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered == "content-length":
                continue
            response_headers[key] = value
        if response.status_code in REDIRECT_STATUS_CODES:
            location = response.header("location")
            if not location:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Rendered job page returned an invalid redirect.",
                )
            response_headers["Location"] = validate_public_job_url(urljoin(destination.url, location))
        _capture_job_json_response(response, budget)
        budget.response_bytes += len(response.body)
        route.fulfill(status=response.status_code, headers=response_headers, body=response.body)
    except HTTPException as exc:
        _block_browser_route(route, budget, str(exc.detail), exc.status_code)


def _remaining_render_timeout_ms(deadline: float, maximum_ms: int) -> int:
    remaining_ms = int((deadline - time.monotonic()) * 1000)
    if remaining_ms <= 0:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Rendered job page exceeded the allowed fetch time.",
        )
    return max(1, min(maximum_ms, remaining_ms))


def _wait_for_rendered_job_content(page: Any, playwright_timeout_error: type[Exception], deadline: float) -> None:
    try:
        page.wait_for_function(
            RENDERED_SEMANTIC_READY_SCRIPT,
            polling=100,
            timeout=_remaining_render_timeout_ms(deadline, RENDERED_SELECTOR_TIMEOUT_MS),
        )
    except playwright_timeout_error:
        pass
    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=_remaining_render_timeout_ms(deadline, RENDERED_SETTLE_TIMEOUT_MS),
        )
    except playwright_timeout_error:
        pass
    try:
        page.wait_for_function(
            RENDERED_DOM_STABLE_SCRIPT,
            polling=100,
            timeout=_remaining_render_timeout_ms(deadline, RENDERED_SETTLE_TIMEOUT_MS),
        )
    except playwright_timeout_error:
        pass


def _fetch_rendered_html(url: str) -> str:
    safe_url = validate_public_job_url(url)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The static job page could not be read. This page may require JavaScript rendering. "
                "Install Playwright with `python -m pip install -r requirements.txt` and "
                "`python -m playwright install chromium`, then restart the server."
            ),
        ) from exc

    budget = RenderedFetchBudget(deadline=time.monotonic() + RENDERED_FETCH_TOTAL_TIMEOUT_SECONDS)

    def render_with_browser(browser_type) -> str:
        browser = browser_type.launch(
            headless=True,
            timeout=_remaining_render_timeout_ms(budget.deadline, RENDERED_FETCH_TIMEOUT_MS),
        )
        try:
            context = browser.new_context(
                user_agent=BROWSER_USER_AGENT,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                service_workers="block",
            )
            try:
                context.route("**/*", lambda route: _proxy_browser_route(route, budget))
                context.route_web_socket(
                    "**/*",
                    lambda websocket: websocket.close(code=1008, reason="Network access is restricted."),
                )
                page = context.new_page()
                try:
                    page.goto(
                        safe_url,
                        wait_until="domcontentloaded",
                        timeout=_remaining_render_timeout_ms(budget.deadline, RENDERED_FETCH_TIMEOUT_MS),
                    )
                except PlaywrightError:
                    if budget.blocked_reason is not None:
                        raise HTTPException(
                            status_code=budget.blocked_status_code,
                            detail=budget.blocked_reason,
                        )
                    raise
                if budget.blocked_reason is not None:
                    raise HTTPException(status_code=budget.blocked_status_code, detail=budget.blocked_reason)
                _wait_for_rendered_job_content(page, PlaywrightTimeoutError, budget.deadline)
                if budget.blocked_reason is not None:
                    raise HTTPException(status_code=budget.blocked_status_code, detail=budget.blocked_reason)
                rendered_html = _inject_captured_json(page.content(), budget.captured_json_blocks)
                if len(rendered_html.encode("utf-8")) > MAX_RENDERED_HTML_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Rendered job page is too large to import.",
                    )
                return rendered_html
            finally:
                context.close()
        finally:
            browser.close()

    try:
        with sync_playwright() as playwright:
            rendered_html = render_with_browser(playwright.chromium)
            if _is_access_gate_text(_visible_text_from_html(rendered_html)):
                try:
                    return render_with_browser(playwright.firefox)
                except PlaywrightError:
                    return rendered_html
            return rendered_html
    except PlaywrightError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "The static job page could not be read, and the rendered-page fallback failed. "
                "Retry later or use the pasted job description fallback."
            ),
        ) from exc


def _add_result_warning(result: JobExtractionResult, warning: str) -> JobExtractionResult:
    result.warnings = list(dict.fromkeys([*result.warnings, warning]))
    return result


def _rendered_job_result(url: str) -> JobExtractionResult:
    result = extract_job_result_from_html(_fetch_rendered_html(url), source_url=url)
    return _add_result_warning(result, "rendered_fallback_used")


def _fetch_job_result_from_url(url: str) -> JobExtractionResult:
    static_result: JobExtractionResult | None = None
    static_error: HTTPException | None = None
    try:
        content_type, text = _fetch_url_text(url)
    except RenderableFetchError:
        rendered_result = _rendered_job_result(url)
        if rendered_result.confidence < MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The rendered page did not contain a sufficiently complete job posting. Paste the job description manually.",
            )
        return rendered_result

    try:
        static_result = (
            _result_from_plain_text(text, source_url=url)
            if "text/plain" in content_type
            else extract_job_result_from_html(text, source_url=url)
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT:
            raise
        static_error = exc

    if static_result is not None and static_result.confidence >= MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE:
        return static_result

    try:
        rendered_result = _rendered_job_result(url)
    except HTTPException:
        if static_error is not None:
            raise static_error
        raise

    candidates = [item for item in (static_result, rendered_result) if item is not None]
    winner = max(candidates, key=lambda item: (item.confidence, len(item.focused_text)))
    if winner.confidence < MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The page did not contain a sufficiently complete job posting. Paste the job description manually.",
        )
    if winner is static_result:
        _add_result_warning(winner, "rendered_candidate_not_better")
    return winner


def _confidence_band(confidence: float) -> str:
    if confidence >= REVIEW_EXTRACTION_CONFIDENCE:
        return "high"
    if confidence >= MIN_ACCEPTABLE_EXTRACTION_CONFIDENCE:
        return "acceptable"
    return "low"


def _extraction_path(result: JobExtractionResult) -> str:
    if "rendered_fallback_used" in result.warnings:
        return "rendered"
    if "rendered_candidate_not_better" in result.warnings:
        return "static_after_render"
    return "static"


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = str(exc.detail).lower()
        if exc.status_code == status.HTTP_413_CONTENT_TOO_LARGE:
            return "resource_limit"
        if exc.status_code == status.HTTP_400_BAD_REQUEST:
            return "invalid_url_or_network_policy"
        if any(marker in detail for marker in ("sign-in", "verification", "captcha", "bot-detection", "account login")):
            return "access_gate"
        if any(marker in detail for marker in ("expired", "removed", "no longer available")):
            return "expired_or_removed"
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
            return "unextractable"
        if exc.status_code in {status.HTTP_502_BAD_GATEWAY, status.HTTP_504_GATEWAY_TIMEOUT}:
            return "upstream_failure"
        return "http_error"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    return "unexpected_error"


def _safe_source_hostname(url: str) -> str:
    try:
        hostname = urlparse(url).hostname
    except ValueError:
        return "invalid"
    return (hostname or "unknown").lower()[:253]


def _log_extraction_success(url: str, result: JobExtractionResult, started: float) -> None:
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    warnings = ",".join(sorted(set(result.warnings))) or "none"
    LOGGER.info(
        "job_extraction extractor_version=%s host=%s outcome=succeeded method=%s "
        "confidence_band=%s confidence=%.2f path=%s duration_ms=%s "
        "visible_input_chars=%s focused_output_chars=%s warning_categories=%s failure_category=none",
        result.extractor_version,
        _safe_source_hostname(url),
        result.extraction_method,
        _confidence_band(result.confidence),
        result.confidence,
        _extraction_path(result),
        duration_ms,
        len(result.raw_visible_text or ""),
        len(result.focused_text),
        warnings,
    )


def _log_extraction_failure(url: str, exc: Exception, started: float) -> None:
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    LOGGER.warning(
        "job_extraction extractor_version=%s host=%s outcome=failed method=none "
        "confidence_band=none confidence=none path=unknown duration_ms=%s "
        "visible_input_chars=unknown focused_output_chars=0 warning_categories=none failure_category=%s",
        JOB_EXTRACTOR_VERSION,
        _safe_source_hostname(url),
        duration_ms,
        _failure_category(exc),
    )


def fetch_job_result_from_url(url: str) -> JobExtractionResult:
    started = time.monotonic()
    try:
        result = _fetch_job_result_from_url(url)
    except Exception as exc:
        _log_extraction_failure(url, exc, started)
        raise
    _log_extraction_success(url, result, started)
    return result


def fetch_job_description_from_url(url: str) -> str:
    return fetch_job_result_from_url(url).focused_text


def fetch_job_page_text_from_url(url: str) -> str:
    result = fetch_job_result_from_url(url)
    return result.raw_visible_text or result.focused_text
