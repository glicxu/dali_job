"use client";

import { FormEvent, useState } from "react";
import { Bug, SearchCheck } from "lucide-react";
import { extractJobUrl, getAuthToken, JobUrlExtractResponse } from "../lib/api";
import { AlertBanner, Button, EmptyState, SectionHeader } from "./ui";

export function JobUrlDebugTool() {
  if (!getAuthToken()) {
    return <JobUrlDebugPreview />;
  }

  return <AuthenticatedJobUrlDebugTool />;
}

function AuthenticatedJobUrlDebugTool() {
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
        <SectionHeader title="Inspect a job URL" description="This diagnostic extracts text only and does not save or analyze the posting." />
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
        <Button type="submit" icon={SearchCheck} loading={isLoading} disabled={!jobUrl.trim()}>Scrape URL</Button>
      </form>

      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}

      {result ? (
        <section className="profile-card">
          <SectionHeader title="Scraped text" description={`${result.character_count.toLocaleString()} characters from ${result.job_url}`} />
          <pre className="text-preview large-preview">{result.extracted_text}</pre>
        </section>
      ) : null}
    </div>
  );
}

function JobUrlDebugPreview() {
  return (
    <div className="debug-tool">
      <AlertBanner tone="warning">Login is required to scrape and debug job URLs.</AlertBanner>
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
      <EmptyState compact icon={Bug} title="Diagnostic preview" description="Login to run the scraper against a public job URL." action={<a className="button-link" href="/auth">Login / Register</a>} />
    </div>
  );
}
