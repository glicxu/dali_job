# Job Posting Scraper Generalization Plan

## Purpose

This document defines how DaliJob should improve job-posting URL extraction without turning the scraper into an unmaintainable collection of employer-specific CSS selectors.

The current implementation already has important network protections, including public-destination validation, redirect revalidation, request and response limits, and a bounded Playwright fallback. The primary weakness is extraction quality: a static page can return enough unrelated or incomplete text to be accepted even when a rendered page or structured source would produce a better job posting.

This plan applies to individual job URL imports and the URL-backed matching workflow. Job-list discovery and Apify job search remain separate concerns, although they may reuse shared URL validation and source-adapter infrastructure.

## Goals

1. Extract the title, company, location, description, responsibilities, qualifications, and other useful job fields from a wider range of job pages.
2. Prefer deterministic structured data over heuristic text extraction.
3. Detect low-quality extraction instead of treating any sufficiently long text as success.
4. Render JavaScript-dependent pages when static extraction is missing or low quality.
5. Preserve relevant sections when a page exceeds text or model-input limits.
6. Support common applicant-tracking systems through bounded adapters.
7. Keep the existing SSRF, redirect, port, credential, request-count, byte, and timeout protections.
8. Return understandable warnings and preserve pasted-text fallback when a site cannot be imported safely.

## Non-Goals

- Bypassing CAPTCHA, authentication, verification, paywalls, or bot-detection systems.
- Guaranteeing extraction from every employer or job board.
- Sending complete raw HTML to OpenAI to determine what is safe or relevant.
- Making Playwright the default for every URL.
- Adding an unlimited collection of global selectors for individual websites.
- Automatically submitting applications or interacting with job-site controls.

## Current Implementation

The current pipeline lives primarily in `server/app/modules/resume_job_match/job_url_import.py` and performs the following work:

1. Validate that the URL uses HTTP or HTTPS, has no embedded credentials, uses an allowed port, and resolves to a public destination.
2. Fetch static HTML or text with redirect, byte, and time limits.
3. Parse JSON-LD `JobPosting` data when available.
4. Score possible job-description containers using class and ID keywords.
5. Fall back to heading-window extraction or broad visible text.
6. Use Playwright after selected HTTP failures and use Firefox as a fallback for some access-gate responses.
7. Reject recognizable sign-in, verification, and bot-detection pages.

Important current limitations:

- Playwright is not automatically attempted when a `200 OK` static page contains an incomplete JavaScript shell or low-quality text.
- Individual job imports often use broad visible page text so navigation and promotional content can reach the job parser.
- Candidate scoring includes broad signals such as `content`, which can select an entire page.
- JSON-LD extraction handles only a subset of useful `JobPosting` fields.
- Heading recognition relies mostly on a fixed list of English section names.
- Extracted text is truncated to a fixed character limit without preserving later sections.
- Extraction returns a plain string and therefore cannot expose method, confidence, warnings, or discovered metadata.

## Proposed Architecture

### Extraction result contract

All extraction strategies should return candidates using a shared internal contract instead of returning an unqualified string.

```python
@dataclass
class JobExtractionCandidate:
    method: str
    source_url: str
    canonical_url: str | None
    title: str | None
    company: str | None
    location: str | None
    sections: dict[str, list[str]]
    focused_text: str
    raw_visible_text: str | None
    confidence: float
    warnings: list[str]


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
```

The public service should choose the best candidate and return one `JobExtractionResult`. API responses do not need to expose every internal candidate, but they should expose warnings that help the user decide whether to review or paste the description manually.

### Extraction sequence

The scraper should use this ordered pipeline:

1. Validate and fetch the static response using the existing network-safety boundary.
2. Extract structured candidates from JSON-LD, microdata, metadata, and recognized embedded application state.
3. Extract DOM subtree candidates from the static page.
4. Score all static candidates for completeness and noise.
5. If no candidate meets the acceptance threshold, render the page with Playwright.
6. Extract structured and DOM candidates again from the rendered page.
7. Optionally collect safe job-shaped JSON responses observed during rendering.
8. Choose the highest-confidence candidate.
9. Normalize the winning candidate into sections and focused text.
10. Return a review warning when confidence is marginal, or fail with pasted-text guidance when no acceptable candidate exists.

Playwright should therefore be a quality fallback, not only an HTTP-status fallback.

## Extraction Strategies

### 1. Structured data

Structured extraction has the highest priority because it is usually less noisy and less dependent on page presentation.

Supported sources should include:

- JSON-LD objects with `@type: JobPosting`, including arrays and nested `@graph` structures.
- Schema.org microdata using `itemtype` and `itemprop`.
- Open Graph and standard metadata for title, company, description, and canonical URL when stronger data is unavailable.
- Recognized framework payloads such as `__NEXT_DATA__` and other embedded hydration JSON.
- Safe JSON or XHR responses captured during rendering when they contain recognizable job fields.

The JSON-LD normalizer should support at least:

- `title`
- `description`
- `responsibilities`
- `qualifications`
- `skills`
- `experienceRequirements`
- `educationRequirements`
- `hiringOrganization.name`
- `jobLocation`
- `jobLocationType`
- `employmentType`
- `baseSalary`
- `datePosted`
- `validThrough`
- `industry`
- `occupationalCategory`
- `identifier`

Embedded JSON must be parsed with a real JSON parser. Recursive traversal should use a bounded depth and object-count limit so an unusually large payload cannot consume unbounded memory or CPU.

### 2. DOM subtree scoring

The custom streaming parser should be augmented or replaced for extraction with a real DOM parser such as `selectolax` or `lxml`. Network validation remains independent of the DOM library.

Each plausible subtree should be scored using multiple signals:

- Positive signals: job-related IDs/classes, `main` or `article`, semantic headings, paragraph density, list density, sufficient text length, title/company proximity, and multiple job sections.
- Negative signals: high link density, navigation controls, account prompts, cookie text, legal-only content, repeated site chrome, related-job lists, and excessive duplicated lines.
- Completeness signals: title plus description, responsibilities or duties, qualifications or requirements, and meaningful body length.

The generic word `content` must not be sufficient by itself to establish a high-confidence candidate. It may contribute a small signal only when supported by job headings, low link density, or structured metadata.

### 3. Section normalization

The winning candidate should be normalized before OpenAI parsing. Preserve headings and list items long enough to classify content into stable sections:

- `summary`
- `responsibilities`
- `required_qualifications`
- `preferred_qualifications`
- `experience`
- `education`
- `skills`
- `tools_and_technologies`
- `certifications`
- `compensation`
- `benefits`
- `location_and_work_arrangement`
- `application_details`
- `other`

Heading aliases should include common variants such as "What you'll do," "What you bring," "Your impact," "Who you are," "Minimum requirements," and "Nice to have." Exact aliases are a useful signal, but DOM and density scoring should keep extraction from depending entirely on English headings.

The normalized sections do not replace the existing OpenAI-generated `job_data`. They provide cleaner input from which `job_data` can be generated.

### 4. Quality scoring

Confidence should be deterministic and explainable. Initial scoring can use a weighted model rather than machine learning.

Example factors:

| Signal | Effect |
| --- | --- |
| Valid `JobPosting` structured data | Strong positive |
| Title plus company plus meaningful description | Strong positive |
| Responsibilities and qualifications found | Positive |
| Several paragraphs or list items with low link density | Positive |
| Access-gate or account language | Immediate rejection |
| Mostly links, navigation, or related jobs | Strong negative |
| Legal, cookie, or marketing content dominates | Negative |
| Very short or highly duplicated text | Negative |
| Title conflicts with the page metadata | Warning and negative |

Suggested thresholds:

- `0.80-1.00`: accept automatically.
- `0.60-0.79`: accept with a review warning.
- Below `0.60`: attempt rendered extraction or another adapter.
- No acceptable candidate after all strategies: return a clear failure and pasted-text fallback guidance.

Thresholds must be calibrated against fixtures rather than treated as permanent constants.

### 5. Section-aware limits

The scraper must not truncate the final input by simply removing everything after a fixed character boundary.

When content exceeds the configured limit:

1. Preserve the title, company, location, and section headings.
2. Reserve space for responsibilities, required qualifications, preferred qualifications, experience, and education.
3. Remove duplicate lines and repeated legal text.
4. Shorten oversized sections proportionally.
5. Drop low-value sections such as related jobs or generic company marketing before job requirements.
6. Add a warning indicating that the source content was shortened.

The complete bounded raw visible text may still be retained for debugging or reparsing when allowed by the existing data lifecycle, but it should not be sent indiscriminately to OpenAI.

## ATS Adapter Boundary

A generic extractor cannot reliably model every applicant-tracking system. DaliJob should support narrowly scoped adapters for common systems without moving employer-specific behavior into the generic parser.

```python
class JobSourceAdapter(Protocol):
    name: str

    def matches(self, url: str, html: str | None) -> bool: ...

    def extract(
        self,
        *,
        url: str,
        html: str,
        network: SafeJobNetworkClient,
    ) -> JobExtractionCandidate | None: ...
```

Adapter rules:

- Use the same validated network client and resource limits as the generic scraper.
- Prefer public structured endpoints or embedded data over visual selectors.
- Never receive unrestricted HTTP access.
- Return the shared candidate contract.
- Fail independently so the generic pipeline can continue.
- Have fixture-based tests for every supported source.

Recommended initial adapters:

1. Greenhouse
2. Lever
3. Workday
4. SmartRecruiters
5. Ashby
6. iCIMS

Adapters should be prioritized from actual failed-import telemetry, not added only because a platform exists.

## Browser Rendering Strategy

Rendered extraction should remain bounded and secondary to static extraction.

Required behavior:

- Attempt rendering when static extraction fails, is below the confidence threshold, or appears to be an incomplete application shell.
- Wait for semantic content candidates and short DOM stability rather than relying only on a fixed timeout.
- Continue blocking images, media, fonts, unsafe methods, WebSockets, private destinations, unsafe redirects, and excessive requests.
- Inspect bounded JSON responses during rendering when their content type and shape suggest job data.
- Compare rendered candidates with static candidates instead of automatically preferring rendered content.
- Return explicit access-gate guidance when authentication, CAPTCHA, or bot verification is detected.

DaliJob must not provide a user-assisted CAPTCHA bypass or reuse user login sessions for scraping protected sites.

## Persistence And API Impact

The database does not initially require new columns. Existing fields can continue to store:

- `jobs_cache.raw_description_text`: bounded cleaned source text.
- `jobs_cache.job_data`: OpenAI-normalized job JSON generated lazily.
- `jobs_cache.source_url`: submitted or canonical URL according to the existing cache policy.

The service layer should distinguish `raw_visible_text` from `focused_text`. The focused text should be used for OpenAI analysis. Persisting additional extraction metadata may be considered later if operational data demonstrates value.

An optional future metadata object could contain:

```json
{
  "method": "json_ld",
  "confidence": 0.94,
  "warnings": [],
  "extractor_version": "2",
  "canonical_url": "https://example.com/jobs/123"
}
```

If persisted, extraction metadata requires a separate migration and must not include raw secrets, cookies, browser storage, or response headers.

## Module Structure

The current scraper module combines network safety, browser rendering, detail extraction, and job-list discovery. It should be separated incrementally:

```text
server/app/modules/job_import/
  network.py
  render.py
  models.py
  quality.py
  structured_data.py
  dom_extract.py
  normalize.py
  service.py
  adapters/
    base.py
    greenhouse.py
    lever.py
    workday.py
  list_discovery.py
```

The refactor must preserve public behavior while each concern is moved. A single large rewrite is not required.

## Security Requirements

All new strategies must preserve the existing security boundary:

- Revalidate every URL and redirect.
- Permit only configured HTTP and HTTPS ports.
- Reject embedded URL credentials and non-public destinations.
- Pin validated network destinations to prevent DNS rebinding.
- Limit redirects, requests, response bytes, rendered HTML size, parsing depth, parsing object count, and total duration.
- Do not forward authorization headers or unrelated user cookies.
- Do not log raw job content, query-string secrets, cookies, or browser storage.
- Treat extracted text and embedded JSON as untrusted data.
- Do not execute page-provided scripts outside the bounded Playwright environment.
- Keep OpenAI calls behind authentication, operation limits, and the existing managed-operation boundary.

## Testing Strategy

Create a sanitized fixture corpus representing:

- Schema.org JSON-LD postings.
- Nested `@graph` and array-based JSON-LD.
- Microdata-based postings.
- Server-rendered pages with navigation and legal noise.
- JavaScript shells that require rendering.
- Embedded framework state.
- Greenhouse, Lever, Workday, SmartRecruiters, Ashby, and iCIMS pages as adapters are added.
- Expired, removed, sign-in, CAPTCHA, cookie-only, and bot-detection pages.
- Pages where education or qualifications appear near the end.
- Non-English or unconventional headings.
- Conflicting title or company metadata.
- Oversized and malformed HTML or JSON.

Required test categories:

1. Unit tests for structured-data normalization, subtree scoring, quality scoring, and section-aware shortening.
2. Contract tests ensuring every adapter returns the shared candidate model.
3. Regression tests using fixture HTML with expected included and excluded text.
4. Security tests for SSRF, redirects, DNS rebinding, unsafe ports, oversized responses, and malicious embedded JSON.
5. Integration tests proving low-confidence static extraction triggers rendering.
6. API tests confirming failure messages preserve pasted-text fallback.

Tests should not depend on live job sites in normal CI. Optional scheduled diagnostics may use approved public URLs, but fixture tests remain authoritative.

## Observability

Record structured operational metadata without storing job text in logs:

- Source hostname.
- Extraction method.
- Confidence band.
- Static or rendered path.
- Adapter name when used.
- Extraction duration.
- Input and output character counts.
- Warning and failure category.

Useful reliability metrics include success rate by hostname and method, rendered-fallback rate, low-confidence rate, access-gate rate, and regression rate after extractor-version changes.

## Implementation Phases

### Phase 1: Quality-aware generic pipeline

- [ ] Add `JobExtractionCandidate` and `JobExtractionResult` internal models.
- [ ] Add deterministic confidence scoring and warning categories.
- [ ] Attempt rendered extraction after static extraction failure or low confidence.
- [ ] Return and compare static and rendered candidates.
- [ ] Separate focused job text from broad visible page text.
- [ ] Add regression fixtures for existing Amazon and USAJobs behavior.
- [ ] Preserve all existing network-safety tests.

### Phase 2: Structured data and normalization

- [ ] Expand JSON-LD `JobPosting` field coverage.
- [ ] Support nested JSON-LD graphs and arrays with bounded recursion.
- [ ] Add microdata and metadata extraction.
- [ ] Add bounded embedded application-state parsing.
- [ ] Normalize headings and list content into stable sections.
- [ ] Replace blind truncation with section-aware shortening.

### Phase 3: DOM and rendered-response improvements

- [ ] Introduce a maintained DOM parser dependency.
- [ ] Implement subtree scoring with text density and link-density signals.
- [ ] Remove broad container keywords as standalone acceptance signals.
- [ ] Add semantic wait and short DOM-stability behavior to Playwright.
- [ ] Capture bounded job-shaped JSON responses during rendering.
- [ ] Add malformed and oversized DOM/JSON tests.

### Phase 4: ATS adapters

- [ ] Add the adapter interface and registry.
- [ ] Implement Greenhouse and Lever adapters first.
- [ ] Add Workday and SmartRecruiters based on fixture coverage.
- [ ] Add Ashby and iCIMS when supported by actual failure data.
- [ ] Document adapter ownership and source-specific limitations.

### Phase 5: Reliability measurement

- [ ] Add extractor method, confidence band, timing, and failure-category logs.
- [ ] Add an extractor version to diagnostic metadata.
- [ ] Establish fixture-based extraction quality metrics.
- [ ] Review source reliability before changing acceptance thresholds.

## Acceptance Criteria

The generalized scraper is ready when:

1. A low-quality `200 OK` static shell triggers rendered extraction.
2. Structured `JobPosting` data is preferred over noisy visible text.
3. The selected result excludes navigation, related jobs, account prompts, and repeated legal content in representative fixtures.
4. Qualifications and education sections are preserved when they occur late in a long posting.
5. The API distinguishes successful, review-recommended, access-gated, expired, and unextractable results.
6. Existing URL validation and SSRF tests continue to pass.
7. Static pages do not incur Playwright cost when a high-confidence candidate is available.
8. Unsupported protected sites return pasted-text guidance rather than attempting to bypass access controls.
9. At least two ATS adapters pass fixture-based contract and regression tests.
10. Extraction diagnostics do not log raw page content or credentials.

## Recommended First Delivery

The first implementation should be limited to Phase 1 and the section-aware shortening portion of Phase 2. This provides the highest immediate value: JavaScript shells receive a real fallback, noisy results become reviewable, and late qualifications stop disappearing. DOM-library adoption and ATS adapters can then be added against a stable result and quality contract.
