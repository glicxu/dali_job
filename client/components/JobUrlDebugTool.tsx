"use client";

import { FormEvent, useState } from "react";
import { extractJobUrl, getAuthToken, JobUrlExtractResponse } from "../lib/api";

export function JobUrlDebugTool() {
  if (!getAuthToken()) {
    return <JobUrlDebugPreview />;
  }

  const [jobUrl, setJobUrl] = useState("");
  const [result, setResult] = useState<JobUrlExtractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setIsLoading(true);
    try {
      const payload = await extractJobUrl(jobUrl);
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job URL extraction failed.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="debug-tool">
      <form className="profile-card" onSubmit={submit}>
        <label>
          Job Description URL
          <input
            type="url"
            value={jobUrl}
            onChange={(event) => setJobUrl(event.target.value)}
            placeholder="https://company.com/careers/job-id"
            required
          />
        </label>
        <button type="submit" disabled={isLoading || !jobUrl.trim()}>
          {isLoading ? "Scraping..." : "Scrape URL"}
        </button>
      </form>

      {error ? <div className="error-banner">{error}</div> : null}

      {result ? (
        <section className="profile-card">
          <div>
            <h2>Scraped Text</h2>
            <p className="metadata">
              {result.character_count.toLocaleString()} characters from {result.job_url}
            </p>
          </div>
          <pre className="text-preview large-preview">{result.extracted_text}</pre>
        </section>
      ) : null}
    </div>
  );
}

function JobUrlDebugPreview() {
  return (
    <div className="debug-tool">
      <div className="warning-banner">
        Login is required to scrape and debug job URLs.
      </div>
      <form className="profile-card">
        <label>
          Job Description URL
          <input value="https://company.com/careers/job-id" readOnly />
        </label>
        <button type="button" disabled>
          Scrape URL
        </button>
      </form>
      <section className="profile-card">
        <div>
          <h2>Scraped Text</h2>
          <p className="metadata">Example preview</p>
        </div>
        <pre className="text-preview large-preview">
          Job title, responsibilities, required skills, qualifications, and application details would appear here
          after login.
        </pre>
      </section>
      <a className="button-link" href="/auth">
        Login / Register to Debug URLs
      </a>
    </div>
  );
}
