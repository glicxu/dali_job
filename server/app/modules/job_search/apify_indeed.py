from __future__ import annotations

import json
import os
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from app.modules.jobs.schemas import IndeedJobSearchResult
from app.modules.resume_job_match.job_url_import import clean_job_text, strip_html_fragment

APIFY_INDEED_ACTOR_ID = "misceres~indeed-scraper"
APIFY_INDEED_SYNC_ENDPOINT = (
    f"https://api.apify.com/v2/acts/{APIFY_INDEED_ACTOR_ID}/run-sync-get-dataset-items"
)
APIFY_TIMEOUT_SECONDS = 120


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _string_from_nested(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, dict):
        return _first_string(value, ("text", "value", "label", "name"))
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(_first_string(item, ("text", "value", "label", "name")))
        return ", ".join(part for part in parts if part)
    return ""


def _extract_source_url(item: dict[str, Any]) -> str | None:
    source_url = _first_string(
        item,
        (
            "url",
            "jobUrl",
            "jobURL",
            "link",
            "postingUrl",
            "jobPostingUrl",
            "viewJobUrl",
            "indeedUrl",
        ),
    )
    if source_url:
        return source_url

    job_key = _first_string(item, ("jobKey", "jobkey", "jk", "id", "jobId"))
    if job_key:
        return f"https://www.indeed.com/viewjob?jk={job_key}"
    return None


def _extract_description(item: dict[str, Any]) -> str:
    description = _first_string(
        item,
        (
            "description",
            "jobDescription",
            "fullDescription",
            "htmlDescription",
            "descriptionHtml",
            "jobDescriptionHtml",
            "snippet",
            "summary",
        ),
    )
    if not description:
        description = _string_from_nested(item, "description")
    return clean_job_text(strip_html_fragment(description) if "<" in description and ">" in description else description)


def _build_summary(item: dict[str, Any], raw_description_text: str) -> str:
    summary = _first_string(item, ("snippet", "summary", "shortDescription"))
    if summary:
        return clean_job_text(strip_html_fragment(summary) if "<" in summary and ">" in summary else summary)[:500]
    return raw_description_text[:500]


def normalize_indeed_item(item: dict[str, Any]) -> IndeedJobSearchResult | None:
    source_url = _extract_source_url(item)
    raw_description_text = _extract_description(item)
    title = _first_string(item, ("title", "jobTitle", "positionName", "name"))
    company = _first_string(item, ("company", "companyName", "employerName"))
    location = _first_string(item, ("location", "jobLocation", "formattedLocation", "formattedLocationFull"))
    if not location:
        location = _string_from_nested(item, "jobLocation")
    salary_range = _first_string(item, ("salary", "salaryRange", "estimatedSalary"))
    if not salary_range:
        salary_range = _string_from_nested(item, "salary")
    employment_type = _first_string(item, ("jobType", "employmentType", "contractType"))
    posted_at = _first_string(item, ("postedAt", "postedDate", "datePosted", "age", "formattedRelativeTime"))
    external_id = _first_string(item, ("jobKey", "jobkey", "jk", "id", "jobId", "externalId"))
    if not external_id and source_url:
        external_id = sha256(source_url.encode("utf-8")).hexdigest()[:16]

    if not any((source_url, title, company, raw_description_text)):
        return None

    return IndeedJobSearchResult(
        external_id=external_id,
        title=title,
        company=company,
        location=location,
        source_url=source_url,
        summary=_build_summary(item, raw_description_text),
        raw_description_text=raw_description_text,
        salary_range=salary_range,
        employment_type=employment_type,
        posted_at=posted_at,
    )


class ApifyIndeedClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = (token or os.getenv("APIFY_API_TOKEN", "")).strip()

    def search(self, *, keyword: str, location: str, max_results: int = 5) -> list[IndeedJobSearchResult]:
        if not self._token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="APIFY_API_TOKEN is not configured for the server process.",
            )

        search_url = f"https://www.indeed.com/jobs?{urlencode({'q': keyword, 'l': location})}"
        apify_input = {
            "position": keyword,
            "maxItemsPerSearch": max_results,
            "country": "US",
            "location": location,
            "parseCompanyDetails": False,
            "saveOnlyUniqueItems": True,
            "followApplyRedirects": False,
            "startUrls": [{"url": search_url}],
        }
        endpoint = f"{APIFY_INDEED_SYNC_ENDPOINT}?{urlencode({'token': self._token})}"
        request = Request(
            endpoint,
            data=json.dumps(apify_input).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=APIFY_TIMEOUT_SECONDS) as response:
                response_body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Apify Indeed scraper returned HTTP {exc.code}: {detail}",
            ) from exc
        except URLError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not reach Apify Indeed scraper: {exc.reason}",
            ) from exc
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Apify Indeed scraper timed out.",
            ) from exc

        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Apify Indeed scraper returned invalid JSON.",
            ) from exc

        if not isinstance(payload, list):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Apify Indeed scraper did not return a dataset item list.",
            )

        normalized = []
        seen_urls = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            result = normalize_indeed_item(item)
            if result is None:
                continue
            dedupe_key = result.source_url or result.external_id or f"{result.title}|{result.company}|{result.location}"
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
            normalized.append(result)
            if len(normalized) >= max_results:
                break
        return normalized


def get_apify_indeed_client() -> ApifyIndeedClient:
    return ApifyIndeedClient()
