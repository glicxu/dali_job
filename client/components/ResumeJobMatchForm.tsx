"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness, FileText, ScanSearch } from "lucide-react";
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
import { AlertBanner, Button, MatchScoreBadge, SectionHeader, ToastRegion } from "./ui";

type ResumeSourceMode = "profile" | "paste";

export function ResumeJobMatchForm() {
  if (!getAuthToken()) {
    return <ResumeJobMatchPreview />;
  }

  return <AuthenticatedResumeJobMatchForm />;
}

function AuthenticatedResumeJobMatchForm() {
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [resumeSourceMode, setResumeSourceMode] = useState<ResumeSourceMode>("profile");
  const [selectedResumeProfileId, setSelectedResumeProfileId] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [jobTitle, setJobTitle] = useState("");
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
  const hasJobSource = isBulkSavedJobMode || Boolean(jobTitle.trim() && jobText.trim());
  const selectedResumeProfile = resumeProfiles.find((profile) => String(profile.id) === selectedResumeProfileId) ?? null;
  const resumeWarning =
    !isLoadingDocuments && !hasResumeSource
      ? "Choose a saved resume profile or paste resume text before matching."
      : null;

  useEffect(() => {
    listResumeProfiles()
      .then((profilePayload) => {
        setResumeProfiles(profilePayload.resume_profiles);
        const firstProfile = profilePayload.resume_profiles[0];
        const params = new URLSearchParams(window.location.search);
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
        if (initialJobIds.length) {
          setSelectedBulkJobIds(initialJobIds);
          setJobTitle("");
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
      setError("Choose a saved resume profile or paste resume text before matching.");
      return;
    }
    if (!hasJobSource) {
      setError("Add the job title and job description before matching.");
      return;
    }

    setIsLoading(true);

    try {
      if (isBulkSavedJobMode) {
        const bulkMatch: BulkSavedJobMatchResponse = { matched: [], failed: [] };
        for (let index = 0; index < selectedBulkJobIds.length; index += 25) {
          const batch = await compareResumeToSavedJobs({
            user_job_ids: selectedBulkJobIds.slice(index, index + 25),
            resume_profile_id:
              resumeSourceMode === "profile" && selectedResumeProfileId
                ? Number(selectedResumeProfileId)
                : undefined,
            resume_text: resumeSourceMode === "paste" ? resumeText : undefined,
          });
          bulkMatch.matched.push(...batch.matched);
          bulkMatch.failed.push(...batch.failed);
        }
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
        job_title: jobTitle.trim(),
        job_description_text: jobText.trim(),
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
    <form className="match-form match-workbench" onSubmit={handleSubmit}>
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />
      {resumeWarning ? <AlertBanner tone="warning">{resumeWarning}</AlertBanner> : null}

      <section className="profile-card match-source-card">
        <SectionHeader title="Match sources" description="Choose one structured resume profile or paste resume text, then enter the job title and description to compare." />
        <div className={`match-source-workspace${isBulkSavedJobMode ? " single-source" : ""}`}>
          <section className="match-source-panel">
            <div className="match-source-panel-heading">
              <span className="match-source-step" aria-hidden="true">1</span>
              <FileText size={19} aria-hidden="true" />
              <div>
                <h2>Resume</h2>
                <p>Choose the experience you want to compare.</p>
              </div>
            </div>
            <label>
              Resume source
              <select
                value={resumeSourceMode === "paste" ? "__paste__" : `profile:${selectedResumeProfileId}`}
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
            {resumeSourceMode === "paste" ? (
              <label className="match-source-input">
                Resume text
                <textarea
                  value={resumeText}
                  onChange={(event) => setResumeText(event.target.value)}
                  placeholder="Paste resume text."
                />
              </label>
            ) : selectedResumeProfile ? (
              <div className="match-selected-source">
                <strong>{selectedResumeProfile.title}</strong>
                <span>{selectedResumeProfile.resume_data.headline || "Structured resume profile selected"}</span>
                {selectedResumeProfile.is_default ? <span className="default-label">Default resume</span> : null}
              </div>
            ) : (
              <p className="match-source-placeholder">Choose a resume profile to continue.</p>
            )}
          </section>

          {!isBulkSavedJobMode ? (
            <section className="match-source-panel">
              <div className="match-source-panel-heading">
                <span className="match-source-step" aria-hidden="true">2</span>
                <BriefcaseBusiness size={19} aria-hidden="true" />
                <div>
                  <h2>Job</h2>
                  <p>Add the opportunity you want to evaluate.</p>
                </div>
              </div>
              <label className="match-source-input">
                Job title
                <input
                  value={jobTitle}
                  onChange={(event) => setJobTitle(event.target.value)}
                  maxLength={255}
                  required
                />
              </label>
              <label className="match-source-input">
                Job description
                <textarea
                  value={jobText}
                  onChange={(event) => setJobText(event.target.value)}
                  placeholder="Paste as much of the full job posting as possible, including responsibilities, qualifications, location, application deadline, salary, and security clearance when applicable."
                  required
                />
              </label>
            </section>
          ) : null}
        </div>
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
                    {job.company || "Unknown company"}
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

      <Button type="submit" icon={ScanSearch} loading={isLoading} disabled={!hasResumeSource || !hasJobSource}>
        {isBulkSavedJobMode ? "Match Selected Jobs" : "Match"}
      </Button>

      {pendingLowMatchJob ? (
        <AlertBanner tone="warning">
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
        </AlertBanner>
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
          Job title
          <input value="Software Engineer" readOnly />
        </label>
        <label>
          Job description
          <textarea value="Example job description" readOnly />
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
              <MatchScoreBadge score={item.match.match_score} />
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
        <MatchScoreBadge score={result.match_score} />
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
        <MatchScoreBadge score={result.match_score} />
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
