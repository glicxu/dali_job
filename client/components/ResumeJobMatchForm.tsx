"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  BulkSavedJobMatchResponse,
  compareResumeToSavedJobs,
  compareResumeToJob,
  getAuthToken,
  listJobs,
  listResumeProfiles,
  PendingMatchedJob,
  ResumeJobMatchResponse,
  ResumeProfile,
  savePendingMatchedJob,
  StoredJob,
} from "../lib/api";

type ResumeSourceMode = "profile" | "paste";
type JobSourceMode = "url" | "paste";

export function ResumeJobMatchForm() {
  if (!getAuthToken()) {
    return <ResumeJobMatchPreview />;
  }
  return <AuthenticatedResumeJobMatchForm />;
}

function AuthenticatedResumeJobMatchForm() {
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [resumeSourceMode, setResumeSourceMode] = useState<ResumeSourceMode>("profile");
  const [jobSourceMode, setJobSourceMode] = useState<JobSourceMode>("url");
  const [selectedResumeProfileId, setSelectedResumeProfileId] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [jobText, setJobText] = useState("");
  const [result, setResult] = useState<ResumeJobMatchResponse | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkSavedJobMatchResponse | null>(null);
  const [selectedBulkJobIds, setSelectedBulkJobIds] = useState<number[]>([]);
  const [selectedBulkJobs, setSelectedBulkJobs] = useState<StoredJob[]>([]);
  const [pendingLowMatchJob, setPendingLowMatchJob] = useState<PendingMatchedJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  const hasResumeSource = resumeSourceMode === "profile" ? Boolean(selectedResumeProfileId) : Boolean(resumeText.trim());
  const isBulkSavedJobMode = selectedBulkJobIds.length > 0;
  const hasJobSource = isBulkSavedJobMode || (jobSourceMode === "url" ? Boolean(jobUrl.trim()) : Boolean(jobText.trim()));
  const resumeWarning =
    !isLoadingDocuments && !hasResumeSource
      ? "Add a saved resume profile, uploaded resume, or pasted resume text before matching."
      : null;

  useEffect(() => {
    listResumeProfiles()
      .then((profilePayload) => {
        setResumeProfiles(profilePayload.resume_profiles);
        const firstProfile = profilePayload.resume_profiles[0];
        const params = new URLSearchParams(window.location.search);
        const initialJobUrl = params.get("job_url");
        const initialJobIds = params
          .get("job_ids")
          ?.split(",")
          .map((value) => Number(value.trim()))
          .filter((value) => Number.isInteger(value) && value > 0) ?? [];
        const initialResumeProfileId = params.get("resume_profile_id");
        if (firstProfile) {
          setSelectedResumeProfileId(String(firstProfile.id));
          setResumeSourceMode("profile");
        } else {
          setResumeSourceMode("paste");
        }
        if (initialJobUrl) {
          setJobSourceMode("url");
          setJobUrl(initialJobUrl);
          setJobText("");
        }
        if (initialJobIds.length) {
          setSelectedBulkJobIds(initialJobIds);
          setJobUrl("");
          setJobText("");
          listJobs()
            .then((jobs) => {
              const selectedIds = new Set(initialJobIds);
              setSelectedBulkJobs(jobs.filter((job) => selectedIds.has(job.id)));
            })
            .catch(() => {
              setSelectedBulkJobs([]);
            });
        }
        if (initialResumeProfileId) {
          setResumeSourceMode("profile");
          setSelectedResumeProfileId(initialResumeProfileId);
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
    setBulkResult(null);
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
      if (isBulkSavedJobMode) {
        const bulkMatch = await compareResumeToSavedJobs({
          user_job_ids: selectedBulkJobIds,
          resume_profile_id:
            resumeSourceMode === "profile" && selectedResumeProfileId
              ? Number(selectedResumeProfileId)
              : undefined,
          resume_text: resumeSourceMode === "paste" ? resumeText : undefined,
        });
        setBulkResult(bulkMatch);
        const failedCount = bulkMatch.failed.length;
        setStatus(
          failedCount
            ? `Matched ${bulkMatch.matched.length} job(s). ${failedCount} job(s) failed.`
            : `Matched ${bulkMatch.matched.length} job(s).`,
        );
        return;
      }
      const match = await compareResumeToJob({
        resume_profile_id:
          resumeSourceMode === "profile" && selectedResumeProfileId
            ? Number(selectedResumeProfileId)
            : undefined,
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
                : `profile:${selectedResumeProfileId}`
            }
            onChange={(event) => {
              const value = event.target.value;
              if (value === "__paste__") {
                setResumeSourceMode("paste");
                setSelectedResumeProfileId("");
              } else if (value.startsWith("profile:")) {
                setResumeSourceMode("profile");
                setSelectedResumeProfileId(value.replace("profile:", ""));
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
                {profile.is_default ? "Default - " : ""}
                {profile.title}
              </option>
            ))}
            <option value="__paste__">Paste resume text</option>
          </select>
        </label>

        {!isBulkSavedJobMode ? (
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
        ) : null}
      </section>

      <section className={isBulkSavedJobMode ? "input-grid single-column" : "input-grid"}>
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
        {!isBulkSavedJobMode ? (
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
        ) : null}
      </section>

      {isBulkSavedJobMode ? (
        <section className="profile-card">
          <h2>Selected Jobs</h2>
          {selectedBulkJobs.length ? (
            <div className="dashboard-card-list">
              {selectedBulkJobs.map((job) => (
                <article className="compact-job-card" key={job.id}>
                  <strong>{job.title || "Untitled Job"}</strong>
                  <span className="metadata">
                    {job.company || "Unknown company"} | {job.job_data ? "Analyzed" : "Needs analysis"}
                  </span>
                </article>
              ))}
            </div>
          ) : (
            <p className="empty">
              {selectedBulkJobIds.length} saved job(s) selected. Details will load when available.
            </p>
          )}
        </section>
      ) : null}

      <button type="submit" disabled={isLoading || !hasResumeSource || !hasJobSource}>
        {isLoading ? "Comparing..." : isBulkSavedJobMode ? "Match Selected Jobs" : "Match"}
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
      {bulkResult ? <BulkMatchResult result={bulkResult} /> : null}
    </form>
  );
}

function ResumeJobMatchPreview() {
  return (
    <div className="match-form">
      <div className="warning-banner">
        Login is required to use resume-to-job matching.
      </div>
      <section className="match-source-grid">
        <label>
          Resume source
          <select disabled>
            <option>Software engineering resume profile</option>
          </select>
        </label>
        <label>
          Job source
          <select disabled>
            <option>Saved job or pasted job URL</option>
          </select>
        </label>
      </section>
      <section className="result-panel">
        <div className="score-row">
          <div className="score">8</div>
          <div>
            <p className="score-label">Example match score</p>
            <p className="summary">
              Strong backend match with gaps around cloud deployment and observability.
            </p>
          </div>
        </div>
        <div className="result-grid">
          <ResultList title="Matched Skills" items={["Python", "APIs", "SQL"]} />
          <ResultList title="Missing Skills" items={["Kubernetes", "Monitoring"]} />
        </div>
      </section>
      <a className="button-link" href="/auth">
        Login / Register to Match
      </a>
    </div>
  );
}

function BulkMatchResult({ result }: { result: BulkSavedJobMatchResponse }) {
  const [selectedMatchId, setSelectedMatchId] = useState<number | null>(null);
  const selectedMatch = result.matched.find((item) => item.saved_match_id === selectedMatchId) ?? null;

  return (
    <section className="result-panel" aria-live="polite">
      <div>
        <p className="score-label">Bulk match results</p>
        <p className="summary">
          {result.matched.length} matched, {result.failed.length} failed.
        </p>
      </div>
      {result.matched.length ? (
        <div className="dashboard-card-list">
          {result.matched.map((item) => (
            <article className="bulk-match-result-card" key={item.saved_match_id}>
              <div className="score">{item.match.match_score}</div>
              <div>
                <h2>{item.title || "Untitled Job"}</h2>
                <p className="metadata">{item.company || "Unknown company"}</p>
                <p className="summary">{item.match.summary}</p>
                <div className="resume-chip-row">
                  {item.match.matched_skills.slice(0, 6).map((skill) => (
                    <span className="resume-chip" key={skill}>
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setSelectedMatchId((current) => (current === item.saved_match_id ? null : item.saved_match_id))
                }
              >
                Match Data
              </button>
            </article>
          ))}
        </div>
      ) : null}
      {selectedMatch ? (
        <section className="profile-card">
          <div className="profile-card-header">
            <div>
              <h2>Match Data</h2>
              <p className="metadata">
                {selectedMatch.title || "Untitled Job"} | {selectedMatch.company || "Unknown company"}
              </p>
            </div>
            <button type="button" className="secondary-button" onClick={() => setSelectedMatchId(null)}>
              Close
            </button>
          </div>
          <MatchDataDetails result={selectedMatch.match} />
        </section>
      ) : null}
      {result.failed.length ? (
        <section className="result-list">
          <h2>Failed Jobs</h2>
          <ul>
            {result.failed.map((item) => (
              <li key={item.user_job_id}>
                Job #{item.user_job_id}
                <span>{item.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}

function MatchDataDetails({ result }: { result: ResumeJobMatchResponse }) {
  return (
    <section className="result-panel">
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
          <h2>Unsupported Requirements</h2>
          {result.unsupported_requirements.length ? (
            <ul>
              {result.unsupported_requirements.map((item) => (
                <li key={`${item.requirement}-${item.reason}`}>
                  <strong>{item.requirement}</strong>
                  <span>{item.reason}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">No unsupported requirements returned.</p>
          )}
        </section>
      </div>

      <ResultList title="Recommended Resume Updates" items={result.recommended_resume_updates} />
    </section>
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
