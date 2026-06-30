"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  compareResumeToJob,
  listDocuments,
  listResumeProfiles,
  PendingMatchedJob,
  ResumeJobMatchResponse,
  ResumeProfile,
  savePendingMatchedJob,
  StoredDocument,
} from "../lib/api";

type ResumeSourceMode = "profile" | "document" | "paste";
type JobSourceMode = "url" | "paste";

export function ResumeJobMatchForm() {
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [resumeSourceMode, setResumeSourceMode] = useState<ResumeSourceMode>("profile");
  const [jobSourceMode, setJobSourceMode] = useState<JobSourceMode>("url");
  const [selectedResumeProfileId, setSelectedResumeProfileId] = useState("");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [jobText, setJobText] = useState("");
  const [result, setResult] = useState<ResumeJobMatchResponse | null>(null);
  const [pendingLowMatchJob, setPendingLowMatchJob] = useState<PendingMatchedJob | null>(null);
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
  const hasResumeSource =
    resumeSourceMode === "profile"
      ? Boolean(selectedResumeProfileId)
      : resumeSourceMode === "document"
        ? Boolean(selectedDocumentId)
        : Boolean(resumeText.trim());
  const hasJobSource = jobSourceMode === "url" ? Boolean(jobUrl.trim()) : Boolean(jobText.trim());
  const resumeWarning =
    !isLoadingDocuments && !hasResumeSource
      ? "Add a saved resume profile, uploaded resume, or pasted resume text before matching."
      : null;

  useEffect(() => {
    Promise.all([listResumeProfiles(), listDocuments()])
      .then(([profilePayload, documentPayload]) => {
        setResumeProfiles(profilePayload.resume_profiles);
        setDocuments(documentPayload.documents);
        const firstProfile = profilePayload.resume_profiles[0];
        const firstResume = documentPayload.documents.find(
          (document) =>
            document.document_type === "resume" && Boolean(document.latest_version?.extracted_text_available),
        );
        const params = new URLSearchParams(window.location.search);
        const initialJobUrl = params.get("job_url");
        const initialResumeProfileId = params.get("resume_profile_id");
        const initialResumeDocumentId = params.get("resume_document_id");
        if (firstProfile) {
          setSelectedResumeProfileId(String(firstProfile.id));
          setResumeSourceMode("profile");
        } else if (firstResume) {
          setSelectedDocumentId(String(firstResume.id));
          setResumeSourceMode("document");
        } else {
          setResumeSourceMode("paste");
        }
        if (initialJobUrl) {
          setJobSourceMode("url");
          setJobUrl(initialJobUrl);
          setJobText("");
        }
        if (initialResumeProfileId) {
          setResumeSourceMode("profile");
          setSelectedResumeProfileId(initialResumeProfileId);
          setSelectedDocumentId("");
          setResumeText("");
        } else if (initialResumeDocumentId) {
          setResumeSourceMode("document");
          setSelectedDocumentId(initialResumeDocumentId);
          setSelectedResumeProfileId("");
          setResumeText("");
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load resume sources.");
      })
      .finally(() => setIsLoadingDocuments(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setResult(null);
    setPendingLowMatchJob(null);

    if (!hasResumeSource) {
      setError("Add a saved resume profile, uploaded resume, or pasted resume text before matching.");
      return;
    }
    if (!hasJobSource) {
      setError("Add a job URL or paste a job description before matching.");
      return;
    }

    setIsLoading(true);

    try {
      const match = await compareResumeToJob({
        resume_profile_id:
          resumeSourceMode === "profile" && selectedResumeProfileId
            ? Number(selectedResumeProfileId)
            : undefined,
        resume_document_id:
          resumeSourceMode === "document" && selectedDocumentId ? Number(selectedDocumentId) : undefined,
        resume_text: resumeSourceMode === "paste" ? resumeText : undefined,
        job_url: jobSourceMode === "url" ? jobUrl.trim() : undefined,
        job_description_text: jobSourceMode === "paste" ? jobText : undefined,
      });
      setResult(match);
      if (match.pending_job && match.match_score < 5) {
        setPendingLowMatchJob(match.pending_job);
        setStatus("Low compatibility match. Choose whether to save this job.");
      } else {
        setStatus(match.job_saved ? "Comparison complete. Job saved." : "Comparison complete.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setIsLoading(false);
    }
  }

  async function saveLowMatchJob() {
    if (!pendingLowMatchJob) return;
    setError(null);
    setStatus(null);
    setIsLoading(true);
    try {
      const saved = await savePendingMatchedJob(pendingLowMatchJob);
      setPendingLowMatchJob(null);
      setResult((current) =>
        current
          ? {
              ...current,
              saved_job_id: saved.saved_job_id,
              saved_match_id: saved.saved_match_id,
              job_saved: true,
              pending_job: null,
            }
          : current,
      );
      setStatus("Low compatibility job saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job save failed.");
    } finally {
      setIsLoading(false);
    }
  }

  function declineLowMatchJob() {
    setPendingLowMatchJob(null);
    setStatus("Low compatibility job was not saved.");
  }

  return (
    <form className="match-form" onSubmit={handleSubmit}>
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}
      {resumeWarning ? <div className="status-banner">{resumeWarning}</div> : null}

      <section className="match-source-grid">
        <label>
        Resume source
        <select
            value={
              resumeSourceMode === "paste"
                ? "__paste__"
                : resumeSourceMode === "profile"
                  ? `profile:${selectedResumeProfileId}`
                  : `document:${selectedDocumentId}`
            }
            onChange={(event) => {
              const value = event.target.value;
              if (value === "__paste__") {
                setResumeSourceMode("paste");
                setSelectedResumeProfileId("");
                setSelectedDocumentId("");
              } else if (value.startsWith("profile:")) {
                setResumeSourceMode("profile");
                setSelectedResumeProfileId(value.replace("profile:", ""));
                setSelectedDocumentId("");
                setResumeText("");
              } else {
                setResumeSourceMode("document");
                setSelectedDocumentId(value.replace("document:", ""));
                setSelectedResumeProfileId("");
                setResumeText("");
              }
            }}
            disabled={isLoadingDocuments}
          >
            <option value="">
              {isLoadingDocuments ? "Loading resume sources..." : "Choose a resume source"}
            </option>
            {resumeProfiles.map((profile) => (
              <option key={profile.id} value={`profile:${profile.id}`}>
                {profile.is_favorite ? "Starred - " : ""}
                {profile.title}
              </option>
            ))}
            {resumeDocuments.length ? <option disabled>Uploaded resumes</option> : null}
            <option value="__paste__">Paste resume text</option>
            {resumeDocuments.map((document) => (
              <option key={document.id} value={`document:${document.id}`}>
                {document.title}
              </option>
            ))}
          </select>
        </label>

        <label>
          Job source
          <select
            value={jobSourceMode}
            onChange={(event) => {
              const nextMode = event.target.value as JobSourceMode;
              setJobSourceMode(nextMode);
              if (nextMode === "url") {
                setJobText("");
              } else {
                setJobUrl("");
              }
            }}
          >
            <option value="url">Paste job URL</option>
            <option value="paste">Paste job description</option>
          </select>
        </label>
      </section>

      <section className="input-grid">
        <div>
          {resumeSourceMode === "paste" ? (
            <label>
              Resume text
              <textarea
                value={resumeText}
                onChange={(event) => setResumeText(event.target.value)}
                placeholder="Paste resume text."
              />
            </label>
          ) : null}
        </div>
        <div>
          {jobSourceMode === "url" ? (
            <label>
              Job URL
              <input
                type="url"
                value={jobUrl}
                onChange={(event) => setJobUrl(event.target.value)}
                placeholder="https://company.com/careers/job-id"
              />
            </label>
          ) : (
            <label>
              Job description
              <textarea
                value={jobText}
                onChange={(event) => setJobText(event.target.value)}
                placeholder="Paste the job description."
              />
            </label>
          )}
        </div>
      </section>

      <button type="submit" disabled={isLoading || !hasResumeSource || !hasJobSource}>
        {isLoading ? "Comparing..." : "Match"}
      </button>

      {pendingLowMatchJob ? (
        <section className="warning-banner">
          <div>
            <strong>Low compatibility</strong>
            <p className="summary">
              This job scored below 5. Save it only if you still want to keep it in your job list.
            </p>
          </div>
          <div className="button-row">
            <button type="button" className="secondary-button" onClick={declineLowMatchJob}>
              Do Not Save
            </button>
            <button type="button" disabled={isLoading} onClick={() => void saveLowMatchJob()}>
              Save Job
            </button>
          </div>
        </section>
      ) : null}
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
