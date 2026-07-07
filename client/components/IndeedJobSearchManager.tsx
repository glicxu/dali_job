"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  getAuthToken,
  importIndeedSearchResults,
  IndeedJobSearchResponse,
  IndeedJobSearchResult,
  JobListImportResponse,
  listResumeProfiles,
  ResumeProfile,
  searchIndeedJobs,
} from "../lib/api";

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

  const [keyword, setKeyword] = useState("");
  const [location, setLocation] = useState("");
  const [result, setResult] = useState<IndeedJobSearchResponse | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [activeResult, setActiveResult] = useState<IndeedJobSearchResult | null>(null);
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [runMatching, setRunMatching] = useState(false);
  const [resumeProfileId, setResumeProfileId] = useState("");
  const [importResult, setImportResult] = useState<JobListImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const results = result?.results ?? [];
  const selectedResults = results.filter((item) => selectedKeys.has(resultKey(item)));
  const canImport = selectedResults.length > 0 && (!runMatching || Boolean(resumeProfileId));

  const sortedResumeProfiles = useMemo(
    () =>
      [...resumeProfiles].sort((left, right) => {
        if (left.is_default !== right.is_default) return left.is_default ? -1 : 1;
        return left.title.localeCompare(right.title);
      }),
    [resumeProfiles],
  );

  useEffect(() => {
    listResumeProfiles()
      .then((payload) => setResumeProfiles(payload.resume_profiles))
      .catch(() => setResumeProfiles([]));
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setImportResult(null);
    setActiveResult(null);
    setSelectedKeys(new Set());
    setIsSearching(true);
    try {
      const payload = await searchIndeedJobs(keyword.trim(), location.trim(), 5);
      setResult(payload);
      setSelectedKeys(new Set(payload.results.map((item) => resultKey(item))));
      setStatus(`Found ${payload.results.length} job${payload.results.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job search failed.");
    } finally {
      setIsSearching(false);
    }
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

  async function importSelected() {
    setError(null);
    setStatus(null);
    setImportResult(null);
    setIsImporting(true);
    try {
      const payload = await importIndeedSearchResults(selectedResults, {
        resumeProfileId: resumeProfileId ? Number(resumeProfileId) : undefined,
        runMatching,
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
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Job Search</h2>
            <p className="metadata">Search jobs, review results, and import selected postings.</p>
          </div>
        </div>

        <form className="inline-form" onSubmit={search}>
          <label>
            Keyword
            <input
              type="text"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="software engineer"
              required
            />
          </label>
          <label>
            Location
            <input
              type="text"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Maryland"
              required
            />
          </label>
          <button type="submit" disabled={isSearching}>
            {isSearching ? "Searching..." : "Search"}
          </button>
        </form>
      </section>

      {result ? (
        <section className="job-search-workspace">
          <section className="profile-card">
            <div className="profile-card-header">
              <div>
                <h2>Search Results</h2>
                <p className="metadata">
                  {selectedResults.length} of {results.length} selected.
                </p>
              </div>
              <div className="button-row">
                <button type="button" className="secondary-button" onClick={() => setSelectedKeys(new Set())}>
                  Clear
                </button>
                <button type="button" className="secondary-button" onClick={() => setAllResults(results)}>
                  Select All
                </button>
              </div>
            </div>

            {result.warnings.length ? (
              <div className="warning-banner">
                {result.warnings.map((warning) => (
                  <span key={warning}>{warning}</span>
                ))}
              </div>
            ) : null}

            <div className="bulk-import-table">
              <div className="bulk-import-row bulk-import-header indeed-search-row">
                <span>Select</span>
                <span>Job</span>
                <span>Status</span>
                <span>Actions</span>
              </div>
              {results.map((item) => {
                const key = resultKey(item);
                const isActive = activeResult ? resultKey(activeResult) === key : false;
                return (
                  <div className={`bulk-import-row indeed-search-row${isActive ? " selected" : ""}`} key={key}>
                    <span>
                      <input
                        type="checkbox"
                        checked={selectedKeys.has(key)}
                        onChange={() => toggleResult(item)}
                      />
                    </span>
                    <span>
                      <strong>{item.title || "Untitled job"}</strong>
                      <span className="metadata">
                        {item.company || "Unknown company"} {item.location ? `| ${item.location}` : ""}
                      </span>
                      <span className="metadata">{item.source_url || "No source URL returned"}</span>
                    </span>
                    <span className="score-badge">{item.status.replace("_", " ")}</span>
                    <span>
                      <button type="button" className="secondary-button" onClick={() => setActiveResult(item)}>
                        View
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>

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

            <button type="button" disabled={!canImport || isImporting} onClick={() => void importSelected()}>
              {isImporting ? "Importing..." : `Import ${selectedResults.length} Selected`}
            </button>
          </section>

          <div className="job-search-detail-pane">
            {activeResult ? (
              <JobSearchResultDetail result={activeResult} onClose={() => setActiveResult(null)} />
            ) : (
              <section className="saved-jobs-empty-detail">
                <h2>Job Description</h2>
                <p className="empty">Select View from a search result to open the job description here.</p>
              </section>
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
                    <span className="score-badge">{item.match_score === null ? "N/A" : `${item.match_score}/10`}</span>
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
        <button type="button" className="secondary-button" onClick={onClose}>
          Close
        </button>
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
            Keyword
            <input value="software engineer" readOnly />
          </label>
          <label>
            Location
            <input value="Maryland" readOnly />
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
            <span>Status</span>
            <span>Actions</span>
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
              <span className="score-badge">new</span>
              <span>
                <button type="button" className="secondary-button" disabled>
                  View
                </button>
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
