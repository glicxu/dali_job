from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, unquote, urldefrag, urljoin, urlunparse
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException, status


class RenderableFetchError(Exception):
    def __init__(self, status_code: int, reason: str) -> None:
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


MAX_JOB_PAGE_BYTES = 2 * 1024 * 1024
MAX_JOB_TEXT_CHARS = 30_000
FETCH_TIMEOUT_SECONDS = 12
RENDERED_FETCH_TIMEOUT_MS = 20_000
RENDERED_SELECTOR_TIMEOUT_MS = 6_000
RENDERED_SETTLE_TIMEOUT_MS = 2_000
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
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


@dataclass
class CandidateBlock:
    tag: str
    attr_text: str
    depth: int = 1
    parts: list[str] = field(default_factory=list)


def _is_public_host(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False

    for item in addresses:
        ip_text = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def validate_public_job_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL must use http or https.")
    if not parsed.hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host is required.")
    if not _is_public_host(parsed.hostname):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job URL host is not allowed.")
    return url


class JobHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._script_type: str | None = None
        self._script_buffer: list[str] = []
        self.visible_parts: list[str] = []
        self.json_ld_blocks: list[str] = []
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
            else:
                self._skip_depth += 1
            return

        for candidate in self._active_candidates:
            candidate.depth += 1

        if self._skip_depth == 0 and self._script_type is None and tag in CONTAINER_TAGS:
            if tag in {"main", "article"} or any(keyword in attr_text for keyword in CONTAINER_ATTR_KEYWORDS):
                self._active_candidates.append(CandidateBlock(tag=tag, attr_text=attr_text))
        if tag in BLOCK_TAGS:
            self.visible_parts.append("\n")
            for candidate in self._active_candidates:
                candidate.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._script_type == "ld+json":
            self.json_ld_blocks.append("".join(self._script_buffer))
            self._script_type = None
            self._script_buffer = []
            return
        if tag in {"style", "noscript", "svg", "script"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in BLOCK_TAGS:
            self.visible_parts.append("\n")
            for candidate in self._active_candidates:
                candidate.parts.append("\n")

        remaining: list[CandidateBlock] = []
        for candidate in self._active_candidates:
            candidate.depth -= 1
            if candidate.depth <= 0:
                self.candidate_blocks.append(candidate)
            else:
                remaining.append(candidate)
        self._active_candidates = remaining

    def handle_data(self, data: str) -> None:
        if self._script_type == "ld+json":
            self._script_buffer.append(data)
            return
        if self._skip_depth == 0:
            self.visible_parts.append(data)
            for candidate in self._active_candidates:
                candidate.parts.append(data)


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


def clean_job_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_JOB_TEXT_CHARS]


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
    return clean_job_text("\n".join(output))


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
    return clean_job_text("\n".join(output))


def _trim_footer_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    output: list[str] = []
    for line in lines:
        if any(marker in line.lower() for marker in FOOTER_MARKERS):
            break
        output.append(line)
    return clean_job_text("\n".join(output))


def _section_marker_count(text_lower: str) -> int:
    return sum(1 for marker in SECTION_MARKERS if marker in text_lower)


def _candidate_score(candidate: CandidateBlock, text: str) -> int:
    text_lower = text.lower()
    attr = candidate.attr_text
    score = 0
    if "job-detail-body" in attr:
        score += 60
    if "job-description" in attr or "jobdescription" in attr or "job_description" in attr:
        score += 55
    if "job-detail" in attr or "job_detail" in attr or "job-details" in attr:
        score += 35
    if "description" in attr:
        score += 25
    if "posting" in attr:
        score += 20
    if "content" in attr:
        score += 12
    if candidate.tag in {"main", "article"}:
        score += 10
    score += _section_marker_count(text_lower) * 12
    if "basic qualifications" in text_lower and "preferred qualifications" in text_lower:
        score += 25
    if len(text) >= 500:
        score += 10
    if len(text) >= 1500:
        score += 10
    if any(marker in text_lower for marker in FOOTER_MARKERS):
        score -= 8
    return score


def _best_candidate_text(candidates: list[CandidateBlock]) -> str | None:
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
        return best_text
    return None


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
    window = clean_job_text("\n".join(lines[start:end]))
    return window if len(window) >= 200 else None


def strip_html_fragment(value: str) -> str:
    parser = JobHtmlParser()
    parser.feed(value)
    text = clean_job_text("\n".join(parser.visible_parts))
    return text or clean_job_text(re.sub(r"<[^>]+>", " ", value))


def _flatten_json_ld(value) -> list[dict]:
    if isinstance(value, dict):
        items = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            items.extend(item for item in graph if isinstance(item, dict))
        return items
    if isinstance(value, list):
        items: list[dict] = []
        for item in value:
            items.extend(_flatten_json_ld(item))
        return items
    return []


def _jobposting_text_from_json_ld(blocks: list[str]) -> str | None:
    for block in blocks:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in _flatten_json_ld(payload):
            type_value = item.get("@type")
            types = type_value if isinstance(type_value, list) else [type_value]
            if not any(str(value).lower() == "jobposting" for value in types):
                continue
            parts: list[str] = []
            for key in ("title", "description", "responsibilities", "qualifications", "skills", "experienceRequirements"):
                value = item.get(key)
                if isinstance(value, str):
                    parts.append(strip_html_fragment(value))
                elif isinstance(value, list):
                    parts.extend(strip_html_fragment(str(entry)) for entry in value if entry)
            organization = item.get("hiringOrganization")
            if isinstance(organization, dict) and organization.get("name"):
                parts.insert(0, strip_html_fragment(str(organization["name"])))
            text = _trim_footer_text(clean_job_text("\n\n".join(parts)))
            if len(text) >= 80:
                return text
    return None


def extract_job_description_from_html(content: str) -> str:
    parser = JobHtmlParser()
    parser.feed(content)
    structured_text = _jobposting_text_from_json_ld(parser.json_ld_blocks)
    if structured_text:
        _raise_if_access_gate_text(structured_text)
        return structured_text
    candidate_text = _best_candidate_text(parser.candidate_blocks)
    if candidate_text:
        _raise_if_access_gate_text(candidate_text)
        return candidate_text
    text = clean_job_text("\n".join(parser.visible_parts))
    text = _trim_footer_text(text)
    heading_text = _heading_window_text(text)
    if heading_text:
        _raise_if_access_gate_text(heading_text)
        return heading_text
    _raise_if_access_gate_text(text)
    if len(text) < 200:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Could not extract enough job text from the URL.")
    return text


def extract_job_page_text_from_html(content: str) -> str:
    parser = JobHtmlParser()
    parser.feed(content)
    text = _dedupe_lines("\n".join(parser.visible_parts))
    _raise_if_access_gate_text(text)
    if len(text) < 200:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Could not extract enough job text from the URL.")
    return text


def _fetch_url_text(url: str) -> tuple[str, str]:
    safe_url = validate_public_job_url(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "text/html,text/plain,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(MAX_JOB_PAGE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403, 429, 503}:
            raise RenderableFetchError(exc.code, exc.reason) from exc
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Job URL returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The job URL is temporarily unreachable. Retry or paste the job description manually.",
        ) from exc

    if len(raw) > MAX_JOB_PAGE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Job page is too large to import.")
    if "text/html" not in content_type and "text/plain" not in content_type and "application/xhtml" not in content_type:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Job URL did not return HTML or text.")

    charset = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, re.IGNORECASE)
    if match:
        charset = match.group(1)
    text = raw.decode(charset, errors="ignore")
    return content_type, text


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

    def render_with_browser(browser_type) -> str:
        browser = browser_type.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=BROWSER_USER_AGENT,
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"image", "media", "font"}
                else route.continue_(),
            )
            page.goto(safe_url, wait_until="domcontentloaded", timeout=RENDERED_FETCH_TIMEOUT_MS)
            try:
                page.wait_for_selector(
                    "a[href*='/jobs/'], a[href*='/job/'], a[href*='/GetJob/ViewDetails/'], "
                    "a[href*='/viewjob'], a[href*='/rc/clk'], [data-document-id], [data-job-id], "
                    "[data-requisition-id], [data-jk], [data-vjk], #jobDescriptionText, "
                    "[class*='jobsearch-RightPane'], [class*='jobDescription'], "
                    "[data-testid='jobsearch-JobComponent-description']",
                    timeout=RENDERED_SELECTOR_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=RENDERED_SETTLE_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                pass
            return page.content()
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


def fetch_job_description_from_url(url: str) -> str:
    try:
        content_type, text = _fetch_url_text(url)
    except RenderableFetchError:
        return extract_job_description_from_html(_fetch_rendered_html(url))
    if "text/plain" in content_type:
        return clean_job_text(text)
    return extract_job_description_from_html(text)


def fetch_job_page_text_from_url(url: str) -> str:
    try:
        content_type, text = _fetch_url_text(url)
    except RenderableFetchError:
        return extract_job_page_text_from_html(_fetch_rendered_html(url))
    if "text/plain" in content_type:
        return clean_job_text(text)
    return extract_job_page_text_from_html(text)
