"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { compareResumeToJob, listDocuments, ResumeJobMatchResponse, StoredDocument } from "../lib/api";

export function ResumeJobMatchForm() {
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [jobText, setJobText] = useState("");
  const [result, setResult] = useState<ResumeJobMatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  const resumeDocuments = useMemo(
    () =>
      documents.filter(
        (document) =>
          document.document_type === "resume" && Boolean(document.latest_version?.extracted_text_available),
      ),
    [documents],
  );

  useEffect(() => {
    listDocuments()
      .then((payload) => {
        setDocuments(payload.documents);
        const firstResume = payload.documents.find(
          (document) =>
            document.document_type === "resume" && Boolean(document.latest_version?.extracted_text_available),
        );
        if (firstResume) {
          setSelectedDocumentId(firstResume.id);
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load uploaded documents.");
      })
      .finally(() => setIsLoadingDocuments(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setResult(null);
    setIsLoading(true);

    try {
      const match = await compareResumeToJob({
        resume_document_id: selectedDocumentId || undefined,
        resume_text: selectedDocumentId ? undefined : resumeText,
        job_url: jobUrl.trim() || undefined,
        job_description_text: jobUrl.trim() ? undefined : jobText,
      });
      setResult(match);
      setStatus("Comparison complete.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setIsLoading(false);
    }
  }

  const hasResumeSource = Boolean(selectedDocumentId || resumeText.trim());
  const hasJobSource = Boolean(jobUrl.trim() || jobText.trim());

  return (
    <form className="match-form" onSubmit={handleSubmit}>
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="match-source-grid">
        <label>
          Uploaded resume
          <select
            value={selectedDocumentId}
            onChange={(event) => setSelectedDocumentId(event.target.value)}
            disabled={isLoadingDocuments}
          >
            <option value="">
              {isLoadingDocuments ? "Loading documents..." : "Use pasted resume text"}
            </option>
            {resumeDocuments.map((document) => (
              <option key={document.id} value={document.id}>
                {document.title}
              </option>
            ))}
          </select>
        </label>

        <label>
          Job URL
          <input
            type="url"
            value={jobUrl}
            onChange={(event) => setJobUrl(event.target.value)}
            placeholder="https://company.com/careers/job-id"
          />
        </label>
      </section>

      <div className="input-grid">
        <label>
          Resume text fallback
          <textarea
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            placeholder="Paste resume text if you do not want to use an uploaded resume."
            disabled={Boolean(selectedDocumentId)}
          />
        </label>
        <label>
          Job description fallback
          <textarea
            value={jobText}
            onChange={(event) => setJobText(event.target.value)}
            placeholder="Paste the job description if URL extraction fails or the page blocks fetching."
            disabled={Boolean(jobUrl.trim())}
          />
        </label>
      </div>

      <button type="submit" disabled={isLoading || !hasResumeSource || !hasJobSource}>
        {isLoading ? "Comparing..." : "Compare Resume To Job"}
      </button>

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
