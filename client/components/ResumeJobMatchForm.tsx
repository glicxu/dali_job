"use client";

import { FormEvent, useState } from "react";
import { compareResumeToJob, ResumeJobMatchResponse } from "../lib/api";

export function ResumeJobMatchForm() {
  const [resumeText, setResumeText] = useState("");
  const [jobText, setJobText] = useState("");
  const [result, setResult] = useState<ResumeJobMatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setIsLoading(true);

    try {
      const match = await compareResumeToJob(resumeText, jobText);
      setResult(match);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <form className="match-form" onSubmit={handleSubmit}>
      <div className="input-grid">
        <label>
          Master resume
          <textarea
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            placeholder="Paste your master resume text."
            required
          />
        </label>
        <label>
          Job description
          <textarea
            value={jobText}
            onChange={(event) => setJobText(event.target.value)}
            placeholder="Paste the job description text."
            required
          />
        </label>
      </div>

      <button type="submit" disabled={isLoading || !resumeText.trim() || !jobText.trim()}>
        {isLoading ? "Comparing..." : "Compare Resume To Job"}
      </button>

      {error ? <div className="error-banner">{error}</div> : null}
      {result ? <MatchResult result={result} /> : null}
    </form>
  );
}

function MatchResult({ result }: { result: ResumeJobMatchResponse }) {
  return (
    <section className="result-panel" aria-live="polite">
      <div className="score-row">
        <div className="score">{result.match_score}</div>
        <div>
          <p className="score-label">Match score</p>
          <p className="summary">{result.summary}</p>
        </div>
      </div>

      <div className="result-grid">
        <ResultList title="Matched Skills" items={result.matched_skills} />
        <ResultList title="Missing Skills" items={result.missing_skills} />
        <ResultList title="Matched Keywords" items={result.matched_keywords} />
        <ResultList title="Missing Keywords" items={result.missing_keywords} />
      </div>

      <div className="detail-grid">
        <section>
          <h2>Supported Requirements</h2>
          {result.supported_requirements.length ? (
            <ul>
              {result.supported_requirements.map((item) => (
                <li key={`${item.requirement}-${item.resume_evidence}`}>
                  <strong>{item.requirement}</strong>
                  <span>{item.resume_evidence}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">No supported requirements returned.</p>
          )}
        </section>

        <section>
          <h2>Recommended Resume Updates</h2>
          <ResultList items={result.recommended_resume_updates} />
        </section>
      </div>
    </section>
  );
}

function ResultList({ title, items }: { title?: string; items: string[] }) {
  return (
    <section className="result-list">
      {title ? <h2>{title}</h2> : null}
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="empty">None returned.</p>
      )}
    </section>
  );
}
