"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness, Check, Eye, MapPin, Search, X } from "lucide-react";
import {
  createJobSearchCriterion,
  getAuthToken,
  importIndeedSearchResults,
  IndeedJobSearchResponse,
  IndeedJobSearchResult,
  JobSearchCriterion,
  JobListImportResponse,
  listJobSearchCriteria,
  listResumeProfiles,
  ResumeProfile,
  searchIndeedJobs,
} from "../lib/api";
import {
  AlertBanner,
  Button,
  EmptyState,
  Field,
  MatchScoreBadge,
  SectionHeader,
  ToastRegion,
  Toolbar,
} from "./ui";
import { isTutorialActive } from "./TutorialGuide";

const RESULTS_PER_PAGE = 5;

function resultKey(result: IndeedJobSearchResult): string {
  return result.source_url || result.external_id || `${result.title}|${result.company}|${result.location}`;
}

function descriptionParagraphs(value: string): string[] {
  return value
    .split(/\n{2,}|\r?\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

export function IndeedJobSearchManager() {
  if (!getAuthToken()) {
    return <IndeedJobSearchPreview />;
  }

  return <AuthenticatedIndeedJobSearchManager />;
}

function AuthenticatedIndeedJobSearchManager() {
  const [keyword, setKeyword] = useState("");
  const [location, setLocation] = useState("");
  const [searchCriteria, setSearchCriteria] = useState<JobSearchCriterion[]>([]);
  const [selectedCriterionId, setSelectedCriterionId] = useState<number | null>(null);
  const [searchEditorOpen, setSearchEditorOpen] = useState(false);
  const [saveAdjustedSearch, setSaveAdjustedSearch] = useState(false);
  const [result, setResult] = useState<IndeedJobSearchResponse | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [activeResult, setActiveResult] = useState<IndeedJobSearchResult | null>(null);
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [runMatching, setRunMatching] = useState(false);
  const [resumeProfileId, setResumeProfileId] = useState("");
  const [tutorialActive, setTutorialActive] = useState(false);
  const [importResult, setImportResult] = useState<JobListImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const results = result?.results ?? [];
  const totalPages = Math.max(1, Math.ceil(results.length / RESULTS_PER_PAGE));
  const pageStartIndex = (currentPage - 1) * RESULTS_PER_PAGE;
  const visibleResults = results.slice(pageStartIndex, pageStartIndex + RESULTS_PER_PAGE);
  const selectedResults = results.filter((item) => selectedKeys.has(resultKey(item)));
  const canImport = selectedResults.length > 0 && (!runMatching || Boolean(resumeProfileId));
  const selectedCriterion = searchCriteria.find((criterion) => criterion.id === selectedCriterionId) ?? null;

  const sortedResumeProfiles = useMemo(
    () =>
      [...resumeProfiles].sort((left, right) => {
        if (left.is_default !== right.is_default) return left.is_default ? -1 : 1;
        return left.title.localeCompare(right.title);
      }),
    [resumeProfiles],
  );

  useEffect(() => {
    const active = isTutorialActive();
    setTutorialActive(active);
    if (active) {
      setRunMatching(false);
      setResumeProfileId("");
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const queryKeyword = params.get("keyword")?.trim().slice(0, 200) || "";
    const queryLocation = params.get("location")?.trim().slice(0, 200) || "";
    Promise.all([listResumeProfiles(), listJobSearchCriteria()])
      .then(([profilePayload, criteriaPayload]) => {
        setResumeProfiles(profilePayload.resume_profiles);
        setSearchCriteria(criteriaPayload);
        if (queryKeyword || queryLocation) {
          setKeyword(queryKeyword);
          setLocation(queryLocation);
          setSearchEditorOpen(true);
          return;
        }
        const criterion = criteriaPayload[0];
        if (criterion) {
          setSelectedCriterionId(criterion.id);
          setKeyword(criterion.keyword);
          setLocation(criterion.location || "");
          setSearchEditorOpen(false);
        } else {
          setSearchEditorOpen(true);
        }
      })
      .catch(() => {
        setResumeProfiles([]);
        setSearchCriteria([]);
        setSearchEditorOpen(true);
      });
  }, []);

  function selectCriterion(criterion: JobSearchCriterion) {
    setSelectedCriterionId(criterion.id);
    setKeyword(criterion.keyword);
    setLocation(criterion.location || "");
    setSearchEditorOpen(false);
    setSaveAdjustedSearch(false);
  }

  async function refreshCriteria(preferredId?: number) {
    const criteria = await listJobSearchCriteria();
    setSearchCriteria(criteria);
    const preferred = criteria.find((criterion) => criterion.id === preferredId);
    if (preferred) selectCriterion(preferred);
  }

  function changeKeyword(value: string) {
    setKeyword(value);
    if (selectedCriterion && value.trim() !== selectedCriterion.keyword) {
      setSelectedCriterionId(null);
    }
  }

  function changeLocation(value: string) {
    setLocation(value);
    if (selectedCriterion?.location && value.trim() !== selectedCriterion.location) {
      setSelectedCriterionId(null);
    }
  }

  async function executeSearch(
    searchKeyword: string,
    searchLocation: string,
    criterion: JobSearchCriterion | null,
    saveAsCriterion = false,
  ) {
    setError(null);
    setStatus(null);
    setImportResult(null);
    setActiveResult(null);
    setCurrentPage(1);
    setSelectedKeys(new Set());
    setIsSearching(true);
    try {
      const payload = await searchIndeedJobs(
        searchKeyword,
        searchLocation,
        10,
        criterion?.id,
      );
      setResult(payload);
      setSelectedKeys(new Set(payload.results.map((item) => resultKey(item))));
      let criterionSaved = false;
      if (criterion) {
        await refreshCriteria(criterion.id);
      } else if (saveAsCriterion) {
        try {
          const saved = await createJobSearchCriterion({ keyword: payload.keyword, location: payload.location });
          await refreshCriteria(saved.id);
          setSaveAdjustedSearch(false);
          criterionSaved = true;
        } catch (saveError) {
          setError(saveError instanceof Error ? saveError.message : "The search criteria could not be saved.");
        }
      }
      setStatus(
        `Found ${payload.results.length} job${payload.results.length === 1 ? "" : "s"}.${criterionSaved ? " Search criteria saved." : ""}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job search failed.");
    } finally {
      setIsSearching(false);
    }
  }

  async function searchJobs(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedKeyword = keyword.trim();
    const trimmedLocation = location.trim();
    const matchingCriterion = selectedCriterion
      && selectedCriterion.keyword === trimmedKeyword
      && selectedCriterion.location === trimmedLocation
      ? selectedCriterion
      : null;
    await executeSearch(trimmedKeyword, trimmedLocation, matchingCriterion, saveAdjustedSearch);
  }

  async function searchWithCriterion(criterion: JobSearchCriterion) {
    const criterionLocation = criterion.location?.trim() || "";
    selectCriterion(criterion);
    if (!criterionLocation) {
      setSearchEditorOpen(true);
      setError("Add a location before using this saved search.");
      return;
    }
    await executeSearch(criterion.keyword.trim(), criterionLocation, criterion);
  }

  function toggleResult(item: IndeedJobSearchResult) {
    const key = resultKey(item);
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function setAllResults(nextResults: IndeedJobSearchResult[]) {
    setSelectedKeys(new Set(nextResults.map((item) => resultKey(item))));
  }

  function openResultsPage(page: number) {
    setCurrentPage(page);
    setActiveResult(null);
  }

  async function importSelected() {
    setError(null);
    setStatus(null);
    setImportResult(null);
    setIsImporting(true);
    try {
      const payload = await importIndeedSearchResults(selectedResults, {
        resumeProfileId: !tutorialActive && resumeProfileId ? Number(resumeProfileId) : undefined,
        runMatching: !tutorialActive && runMatching,
      });
      setImportResult(payload);
      setStatus(`Imported ${payload.imported.length} job${payload.imported.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job import failed.");
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <div className="jobs-manager">
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />

      <section className="profile-card job-search-form-section quick-find-search-card">
        <SectionHeader
          title="Saved Search Criteria"
          description="Run a saved search or adjust the keywords and location."
        />
        {searchCriteria.length ? (
          <div className="quick-find-criteria-list" aria-label="Saved search criteria">
            {searchCriteria.map((criterion) => (
              <article
                className={`quick-find-criterion${criterion.id === selectedCriterionId ? " selected" : ""}`}
                key={criterion.id}
              >
                <span className="quick-find-criterion-copy">
                  <strong>{criterion.keyword}</strong>
                  <span>{criterion.location || "Location needed"}</span>
                </span>
                <span className="quick-find-criterion-actions">
                  <span className="quick-find-criterion-source">Saved</span>
                  <Button
                    type="button"
                    size="compact"
                    icon={Search}
                    loading={isSearching && criterion.id === selectedCriterionId}
                    disabled={isSearching || !criterion.location?.trim()}
                    title={criterion.location?.trim() ? `Search for ${criterion.keyword}` : "Add a location before searching"}
                    onClick={() => void searchWithCriterion(criterion)}
                  >
                    Search
                  </Button>
                </span>
              </article>
            ))}
          </div>
        ) : (
          <p className="metadata">No searches are saved yet. Enter keywords and a location to begin.</p>
        )}
      </section>

      <details
        className="quick-find-search-editor"
        open={searchEditorOpen}
        onToggle={(event) => setSearchEditorOpen(event.currentTarget.open)}
      >
        <summary>Make a Search</summary>
        <form className="quick-find-search-form" onSubmit={searchJobs}>
          <Field label="Search for a job or keyword">
            <input
              type="text"
              value={keyword}
              onChange={(event) => changeKeyword(event.target.value)}
              maxLength={255}
              required
            />
          </Field>
          <Field label="Location">
            <div className="input-with-icon">
              <MapPin size={17} aria-hidden="true" />
              <input
                type="text"
                value={location}
                onChange={(event) => changeLocation(event.target.value)}
                maxLength={255}
                required
              />
            </div>
          </Field>
          <div className="quick-find-search-actions">
            <label className="quick-find-save-option">
              <input
                type="checkbox"
                checked={saveAdjustedSearch}
                onChange={(event) => setSaveAdjustedSearch(event.target.checked)}
              />
              <span>Save Search Options</span>
            </label>
            <Button type="submit" icon={Search} loading={isSearching}>Search</Button>
          </div>
        </form>
      </details>

      {result ? (
        <section className="job-search-workspace">
          <section className="profile-card">
            <div className="profile-card-header">
              <SectionHeader title="Search Results" description={`${selectedResults.length} of ${results.length} selected`} />
              <Toolbar label="Search result selection">
                <Button type="button" variant="ghost" icon={X} onClick={() => setSelectedKeys(new Set())}>Clear</Button>
                <Button type="button" variant="secondary" icon={Check} onClick={() => setAllResults(results)}>Select All</Button>
              </Toolbar>
            </div>

            {result.warnings.length ? (
              <AlertBanner tone="warning">
                {result.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </AlertBanner>
            ) : null}

            {!results.length ? <EmptyState icon={BriefcaseBusiness} title="No jobs found" description="Try a broader keyword or another location." /> : null}

            <div className="bulk-import-table">
              <div className="bulk-import-row bulk-import-header indeed-search-row">
                <span>Select</span>
                <span>Job</span>
              </div>
              {visibleResults.map((item) => {
                const key = resultKey(item);
                const isActive = activeResult ? resultKey(activeResult) === key : false;
                return (
                  <div
                    className={`bulk-import-row indeed-search-row${isActive ? " selected" : ""}`}
                    key={key}
                    role="button"
                    tabIndex={0}
                    aria-label={`View ${item.title || "Untitled job"}`}
                    onClick={() => setActiveResult(item)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setActiveResult(item);
                      }
                    }}
                  >
                    {isActive ? <span className="sr-only">Viewed job</span> : null}
                    <span onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedKeys.has(key)}
                        onChange={() => toggleResult(item)}
                        aria-label={`Select ${item.title || "Untitled job"}`}
                      />
                    </span>
                    <span>
                      <strong>{item.title || "Untitled job"}</strong>
                      <span className="metadata">
                        {item.company || "Unknown company"} {item.location ? `| ${item.location}` : ""}
                      </span>
                      <span className="metadata">{item.source_url || "No source URL returned"}</span>
                    </span>
                  </div>
                );
              })}
            </div>

            {results.length ? (
              <nav className="job-search-pagination" aria-label="Search result pages">
                <p className="metadata">
                  Showing {pageStartIndex + 1}-{Math.min(pageStartIndex + RESULTS_PER_PAGE, results.length)} of {results.length}
                </p>
                <div className="job-search-page-list">
                  {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
                    <button
                      type="button"
                      className={pageNumber === currentPage ? "job-search-page-button active" : "job-search-page-button"}
                      aria-current={pageNumber === currentPage ? "page" : undefined}
                      aria-label={`Show search results page ${pageNumber}`}
                      onClick={() => openResultsPage(pageNumber)}
                      key={pageNumber}
                    >
                      {pageNumber}
                    </button>
                  ))}
                </div>
              </nav>
            ) : null}

            {!tutorialActive ? (
              <div className="bulk-import-options">
                <label className="checkbox-row">
                  <input type="checkbox" checked={runMatching} onChange={(event) => setRunMatching(event.target.checked)} />
                  Run matching after import
                </label>
                {runMatching ? (
                  <label>
                    Resume profile
                    <select value={resumeProfileId} onChange={(event) => setResumeProfileId(event.target.value)} required>
                      <option value="">Select resume profile</option>
                      {sortedResumeProfiles.map((profile) => (
                        <option value={profile.id} key={profile.id}>
                          {profile.is_default ? "Default - " : ""}
                          {profile.title}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>
            ) : null}

            <Button type="button" icon={BriefcaseBusiness} loading={isImporting} disabled={!canImport || isImporting} onClick={() => void importSelected()}>
              Import {selectedResults.length} Selected
            </Button>
          </section>

          <div className="job-search-detail-pane">
            {activeResult ? (
              <JobSearchResultDetail result={activeResult} onClose={() => setActiveResult(null)} />
            ) : (
              <EmptyState icon={Eye} title="Job Description" description="Select a search result to open the full description here." />
            )}
          </div>
        </section>
      ) : null}

      {importResult ? (
        <section className="profile-card">
          <h2>Import Results</h2>
          {importResult.imported.length ? (
            <div className="job-list">
              {importResult.imported.map((item) => (
                <article className="job-row" key={`${item.user_job_id}-${item.source_url}`}>
                  <div className="job-score-cell">
                    <MatchScoreBadge score={item.match_score} />
                  </div>
                  <div>
                    <h2>{item.title || "Untitled Job"}</h2>
                    <p className="metadata">
                      {item.company || "Unknown company"} | User Job ID: {item.user_job_id}
                    </p>
                    <p className="summary">{item.source_url}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : null}
          {importResult.failed.length ? (
            <div className="warning-banner">
              {importResult.failed.map((failure) => (
                <span key={failure.source_url}>
                  {failure.source_url}: {failure.reason}
                </span>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function JobSearchResultDetail({
  result,
  onClose,
}: {
  result: IndeedJobSearchResult;
  onClose: () => void;
}) {
  const paragraphs = descriptionParagraphs(
    result.raw_description_text || result.summary || "No detailed description was returned for this result.",
  );

  return (
    <section className="profile-card job-search-detail-card">
      <div className="profile-card-header">
        <div>
          <h2>{result.title || "Untitled Job"}</h2>
          <p className="metadata">
            {result.company || "Unknown company"} {result.location ? `| ${result.location}` : ""}
          </p>
        </div>
        <Button type="button" size="compact" variant="secondary" icon={X} onClick={onClose}>Close</Button>
      </div>
      {result.source_url ? <p className="metadata">{result.source_url}</p> : null}
      {result.summary ? <p className="summary">{result.summary}</p> : null}
      <div className="job-description-text">
        {paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
    </section>
  );
}

function IndeedJobSearchPreview() {
  return (
    <div className="jobs-manager">
      <div className="warning-banner">
        Login is required to search for jobs and import selected postings.
      </div>
      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Job Search</h2>
            <p className="metadata">Search jobs, review results, and import selected postings after login.</p>
          </div>
        </div>
        <form className="inline-form">
          <label>
            Search for a job or keyword
            <input value="" readOnly />
          </label>
          <label>
            Location
            <input value="" readOnly />
          </label>
          <button type="button" disabled>
            Search
          </button>
        </form>
      </section>
      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Search Results</h2>
            <p className="metadata">2 of 2 selected.</p>
          </div>
        </div>
        <div className="bulk-import-table">
          <div className="bulk-import-row bulk-import-header indeed-search-row">
            <span>Select</span>
            <span>Job</span>
          </div>
          {["Software Engineer", "Data Platform Engineer"].map((title) => (
            <div className="bulk-import-row indeed-search-row" key={title}>
              <span>
                <input type="checkbox" checked readOnly />
              </span>
              <span>
                <strong>{title}</strong>
                <span className="metadata">Example Company | Remote</span>
              </span>
            </div>
          ))}
        </div>
        <button type="button" disabled>
          Import 2 Selected
        </button>
      </section>
      <a className="button-link" href="/auth">
        Login / Register to Search Jobs
      </a>
    </div>
  );
}
