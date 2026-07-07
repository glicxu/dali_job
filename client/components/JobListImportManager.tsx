"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  discoverJobList,
  getAuthToken,
  importJobList,
  JobListCandidate,
  JobListDiscoverResponse,
  JobListImportResponse,
  listResumeProfiles,
  ResumeProfile,
} from "../lib/api";

export function JobListImportManager() {
  if (!getAuthToken()) {
    return <JobListImportPreview />;
  }

  const [listUrl, setListUrl] = useState("");
  const [result, setResult] = useState<JobListDiscoverResponse | null>(null);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [runMatching, setRunMatching] = useState(false);
  const [resumeProfileId, setResumeProfileId] = useState("");
  const [importResult, setImportResult] = useState<JobListImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const candidates = result?.candidates ?? [];
  const selectedCount = selectedUrls.size;
  const canImport = selectedCount > 0 && (!runMatching || Boolean(resumeProfileId));

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
      .catch(() => {
        setResumeProfiles([]);
      });
  }, []);

  async function discover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setResult(null);
    setImportResult(null);
    setSelectedUrls(new Set());
    setIsDiscovering(true);
    try {
      const payload = await discoverJobList(listUrl.trim(), 25);
      setResult(payload);
      setSelectedUrls(new Set(payload.candidates.map((candidate) => candidate.source_url)));
      setStatus(`Discovered ${payload.candidates.length} candidate job links.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job list discovery failed.");
    } finally {
      setIsDiscovering(false);
    }
  }

  function mergeDiscovery(current: JobListDiscoverResponse, next: JobListDiscoverResponse): JobListDiscoverResponse {
    const candidatesByUrl = new Map<string, JobListCandidate>();
    for (const candidate of current.candidates) {
      candidatesByUrl.set(candidate.source_url, candidate);
    }
    for (const candidate of next.candidates) {
      candidatesByUrl.set(candidate.source_url, candidate);
    }
    return {
      ...next,
      list_url: current.list_url,
      candidates: [...candidatesByUrl.values()],
      warnings: [...current.warnings, ...next.warnings].filter(
        (warning, index, warnings) => warnings.indexOf(warning) === index,
      ),
    };
  }

  async function loadMore() {
    if (!result?.next_page_url) return;
    setError(null);
    setStatus(null);
    setIsLoadingMore(true);
    try {
      const payload = await discoverJobList(result.next_page_url, 25);
      const existingUrls = new Set(result.candidates.map((candidate) => candidate.source_url));
      const newCandidates = payload.candidates.filter((candidate) => !existingUrls.has(candidate.source_url));
      setResult((current) => (current ? mergeDiscovery(current, payload) : payload));
      setSelectedUrls((current) => {
        const next = new Set(current);
        for (const candidate of newCandidates) {
          next.add(candidate.source_url);
        }
        return next;
      });
      setStatus(`Loaded ${newCandidates.length} additional candidate job links.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load more jobs.");
    } finally {
      setIsLoadingMore(false);
    }
  }

  function toggleCandidate(sourceUrl: string) {
    setSelectedUrls((current) => {
      const next = new Set(current);
      if (next.has(sourceUrl)) {
        next.delete(sourceUrl);
      } else {
        next.add(sourceUrl);
      }
      return next;
    });
  }

  function setAllCandidates(nextCandidates: JobListCandidate[]) {
    setSelectedUrls(new Set(nextCandidates.map((candidate) => candidate.source_url)));
  }

  async function importSelected() {
    if (!result) return;
    setError(null);
    setStatus(null);
    setImportResult(null);
    setIsImporting(true);
    try {
      const payload = await importJobList([...selectedUrls], {
        listUrl: result.list_url,
        resumeProfileId: resumeProfileId ? Number(resumeProfileId) : undefined,
        runMatching,
      });
      setImportResult(payload);
      setStatus(`Imported ${payload.imported.length} job${payload.imported.length === 1 ? "" : "s"}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk job import failed.");
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
            <h2>Discover Jobs From List URL</h2>
            <p className="metadata">Paste a public job search or listing page. Review discovered jobs before import.</p>
          </div>
        </div>

        <form className="inline-form resume-upload-form" onSubmit={discover}>
          <label>
            Job list URL
            <input
              type="url"
              value={listUrl}
              onChange={(event) => setListUrl(event.target.value)}
              placeholder="https://company.com/careers/search"
              required
            />
          </label>
          <button type="submit" disabled={isDiscovering}>
            {isDiscovering ? "Discovering..." : "Discover Jobs"}
          </button>
        </form>
      </section>

      {result ? (
        <section className="profile-card">
          <div className="profile-card-header">
            <div>
              <h2>Review Discovered Jobs</h2>
              <p className="metadata">
                {selectedCount} of {candidates.length} selected.
              </p>
            </div>
            <div className="button-row">
              <button type="button" className="secondary-button" onClick={() => setSelectedUrls(new Set())}>
                Clear
              </button>
              <button type="button" className="secondary-button" onClick={() => setAllCandidates(candidates)}>
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
            <div className="bulk-import-row bulk-import-header">
              <span>Select</span>
              <span>Job</span>
              <span>Status</span>
            </div>
            {candidates.map((candidate) => (
              <label className="bulk-import-row" key={candidate.source_url}>
                <span>
                  <input
                    type="checkbox"
                    checked={selectedUrls.has(candidate.source_url)}
                    onChange={() => toggleCandidate(candidate.source_url)}
                  />
                </span>
                <span>
                  <strong>{candidate.title || "Untitled job"}</strong>
                  <span className="metadata">{candidate.company || candidate.source_url}</span>
                </span>
                <span className="score-badge">{candidate.status.replace("_", " ")}</span>
              </label>
            ))}
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

          {result.next_page_url ? (
            <button
              type="button"
              className="secondary-button"
              disabled={isLoadingMore}
              onClick={() => void loadMore()}
            >
              {isLoadingMore ? "Loading..." : "Load More"}
            </button>
          ) : null}
          <button type="button" disabled={!canImport || isImporting} onClick={() => void importSelected()}>
            {isImporting ? "Importing..." : `Import ${selectedCount} Selected`}
          </button>
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

function JobListImportPreview() {
  return (
    <div className="jobs-manager">
      <div className="warning-banner">
        Login is required to discover, scrape, import, and match jobs from a list URL.
      </div>
      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Discover Jobs From List URL</h2>
            <p className="metadata">Paste a job search page after login and review discovered postings.</p>
          </div>
        </div>
        <form className="inline-form resume-upload-form">
          <label>
            Job list URL
            <input value="https://company.com/careers/search" readOnly />
          </label>
          <button type="button" disabled>
            Discover Jobs
          </button>
        </form>
      </section>
      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Review Discovered Jobs</h2>
            <p className="metadata">2 of 2 selected.</p>
          </div>
        </div>
        <div className="bulk-import-table">
          <div className="bulk-import-row bulk-import-header">
            <span>Select</span>
            <span>Job</span>
            <span>Status</span>
          </div>
          {["Backend Engineer", "Machine Learning Engineer"].map((title) => (
            <label className="bulk-import-row" key={title}>
              <span>
                <input type="checkbox" checked readOnly />
              </span>
              <span>
                <strong>{title}</strong>
                <span className="metadata">https://example.com/jobs/{title.toLowerCase().replaceAll(" ", "-")}</span>
              </span>
              <span className="score-badge">new</span>
            </label>
          ))}
        </div>
        <button type="button" disabled>
          Import 2 Selected
        </button>
      </section>
      <a className="button-link" href="/auth">
        Login / Register to Import Jobs
      </a>
    </div>
  );
}
