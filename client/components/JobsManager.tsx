"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  analyzeJob,
  archiveJob,
  bulkDeleteJobs,
  createJob,
  deleteJob,
  draftJobFromUrl,
  emptyJobDescriptionData,
  getAuthToken,
  JobDescriptionData,
  JobResumeMatchHistory,
  JobSavePayload,
  listDocuments,
  listJobs,
  listJobMatches,
  listResumeProfiles,
  ResumeProfile,
  restoreJob,
  StoredJob,
  StoredDocument,
  updateJob,
} from "../lib/api";

type ImportMode = "url" | "manual";
type BulkMode = "match" | "remove" | null;
type ArrayField =
  | "responsibilities"
  | "required_skills"
  | "preferred_skills"
  | "required_experience"
  | "preferred_experience"
  | "education"
  | "certifications"
  | "tools_and_technologies"
  | "keywords";

type JobEditorState = {
  id?: number;
  title: string;
  company: string;
  source_url: string;
  raw_description_text: string;
  job_data: JobDescriptionData;
  notes: string;
  showSaveButton: boolean;
  hasUserEdits: boolean;
  isEditing: boolean;
  archived_at: string | null;
};

type SupportedRequirementView = {
  requirement: string;
  resume_evidence: string;
};

type UnsupportedRequirementView = {
  requirement: string;
  reason: string;
};

type MatchDataView = {
  match_score: number | null;
  summary: string;
  matched_skills: string[];
  missing_skills: string[];
  matched_keywords: string[];
  missing_keywords: string[];
  supported_requirements: SupportedRequirementView[];
  unsupported_requirements: UnsupportedRequirementView[];
  recommended_resume_updates: string[];
};

const arrayFieldLabels: Record<ArrayField, string> = {
  responsibilities: "Responsibilities",
  required_skills: "Required Skills",
  preferred_skills: "Preferred Skills",
  required_experience: "Required Experience",
  preferred_experience: "Preferred Experience",
  education: "Education",
  certifications: "Certifications",
  tools_and_technologies: "Tools And Technologies",
  keywords: "Keywords",
};

const arrayFields: ArrayField[] = [
  "responsibilities",
  "required_skills",
  "preferred_skills",
  "required_experience",
  "preferred_experience",
  "education",
  "certifications",
  "tools_and_technologies",
  "keywords",
];

function listToText(items: string[]): string {
  return items.join("\n");
}

function textToList(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function emptyEditorState(): JobEditorState {
  return {
    title: "",
    company: "",
    source_url: "",
    raw_description_text: "",
    job_data: { ...emptyJobDescriptionData },
    notes: "",
    showSaveButton: true,
    hasUserEdits: true,
    isEditing: true,
    archived_at: null,
  };
}

function jobDataOrEmpty(job: StoredJob): JobDescriptionData {
  return job.job_data ?? { ...emptyJobDescriptionData };
}

function editorFromJob(job: StoredJob, showSaveButton = true): JobEditorState {
  return {
    id: job.id,
    title: job.title,
    company: job.company,
    source_url: job.source_url ?? "",
    raw_description_text: job.raw_description_text,
    job_data: jobDataOrEmpty(job),
    notes: job.notes ?? "",
    showSaveButton,
    hasUserEdits: false,
    isEditing: false,
    archived_at: job.archived_at,
  };
}

function matchPageHref(job: StoredJob): string {
  const params = new URLSearchParams();
  if (job.source_url) {
    params.set("job_url", job.source_url);
  } else {
    params.set("job_ids", String(job.id));
  }
  if (job.matched_resume_profile_id) {
    params.set("resume_profile_id", String(job.matched_resume_profile_id));
  }
  if (job.matched_resume_document_id) {
    params.set("resume_document_id", String(job.matched_resume_document_id));
  }
  const query = params.toString();
  return query ? `/match?${query}` : "/match";
}

function stringArrayFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function matchDataObject(value: Record<string, unknown> | null): Record<string, unknown> {
  return value ?? {};
}

function supportedRequirementsFromUnknown(value: unknown): SupportedRequirementView[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const requirement = "requirement" in item ? item.requirement : "";
      const resumeEvidence = "resume_evidence" in item ? item.resume_evidence : "";
      if (typeof requirement !== "string" || typeof resumeEvidence !== "string") return null;
      return { requirement, resume_evidence: resumeEvidence };
    })
    .filter((item): item is SupportedRequirementView => Boolean(item));
}

function unsupportedRequirementsFromUnknown(value: unknown): UnsupportedRequirementView[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const requirement = "requirement" in item ? item.requirement : "";
      const reason = "reason" in item ? item.reason : "";
      if (typeof requirement !== "string" || typeof reason !== "string") return null;
      return { requirement, reason };
    })
    .filter((item): item is UnsupportedRequirementView => Boolean(item));
}

function matchDataViewFromJob(job: StoredJob): MatchDataView {
  const data = matchDataObject(job.match_data);
  const score = data.match_score;
  const summary = data.summary;
  return {
    match_score: typeof score === "number" ? score : job.match_score,
    summary: typeof summary === "string" ? summary : "No summary was saved with this match.",
    matched_skills: stringArrayFromUnknown(data.matched_skills),
    missing_skills: stringArrayFromUnknown(data.missing_skills),
    matched_keywords: stringArrayFromUnknown(data.matched_keywords),
    missing_keywords: stringArrayFromUnknown(data.missing_keywords),
    supported_requirements: supportedRequirementsFromUnknown(data.supported_requirements),
    unsupported_requirements: unsupportedRequirementsFromUnknown(data.unsupported_requirements),
    recommended_resume_updates: stringArrayFromUnknown(data.recommended_resume_updates),
  };
}

function resumeReferenceLabel(
  job: StoredJob,
  resumeProfiles: ResumeProfile[],
  documents: StoredDocument[],
): string {
  if (job.matched_resume_profile_id) {
    const profile = resumeProfiles.find((item) => item.id === job.matched_resume_profile_id);
    return profile ? profile.title : `Resume profile #${job.matched_resume_profile_id}`;
  }
  if (job.matched_resume_document_id) {
    const document = documents.find((item) => item.id === job.matched_resume_document_id);
    return document ? document.title : `Resume document #${job.matched_resume_document_id}`;
  }
  if (job.matched_resume_source === "pasted_text") {
    return "Pasted resume text";
  }
  return "Resume source not saved";
}

function notePreviewLines(notes: string | null): string[] {
  const cleaned = notes?.trim();
  if (!cleaned) return [];
  const words = cleaned.replace(/\s+/g, " ").split(" ").filter(Boolean);
  const lines: string[] = [];
  let current = "";
  const maxCharacters = 115;

  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxCharacters && current) {
      lines.push(current);
      current = word;
      if (lines.length === 2) break;
    } else {
      current = next;
    }
  }
  if (lines.length < 2 && current) {
    lines.push(current);
  }

  const preview = lines.slice(0, 2);
  const previewTextLength = preview.join(" ").length;
  if (cleaned.replace(/\s+/g, " ").length > previewTextLength && preview.length) {
    preview[preview.length - 1] = `${preview[preview.length - 1].replace(/[.,;:!?-]*$/, "")}...`;
  }
  return preview;
}

export function JobsManager({ creationMode = null }: { creationMode?: ImportMode | null } = {}) {
  if (!getAuthToken()) {
    return creationMode ? <JobCreationPreview mode={creationMode} /> : <JobsManagerPreview />;
  }

  const [jobs, setJobs] = useState<StoredJob[]>([]);
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [jobUrl, setJobUrl] = useState("");
  const [editor, setEditor] = useState<JobEditorState | null>(
    creationMode === "manual" ? emptyEditorState() : null,
  );
  const [matchDataJob, setMatchDataJob] = useState<StoredJob | null>(null);
  const [matchHistory, setMatchHistory] = useState<JobResumeMatchHistory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isParsing, setIsParsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [analyzingJobId, setAnalyzingJobId] = useState<number | null>(null);
  const [bulkMode, setBulkMode] = useState<BulkMode>(null);
  const [selectedBulkJobIds, setSelectedBulkJobIds] = useState<number[]>([]);
  const [isBulkRemoving, setIsBulkRemoving] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const sortedJobs = useMemo(() => jobs, [jobs]);

  async function loadJobs() {
    setError(null);
    setIsLoading(true);
    try {
      const loadedJobs = await listJobs(showArchived);
      setJobs(showArchived ? loadedJobs.filter((job) => job.archived_at !== null) : loadedJobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load jobs.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadJobs();
    Promise.all([listResumeProfiles(), listDocuments()])
      .then(([profilePayload, documentPayload]) => {
        setResumeProfiles(profilePayload.resume_profiles);
        setDocuments(documentPayload.documents);
      })
      .catch(() => {
        setResumeProfiles([]);
        setDocuments([]);
      });
  }, [showArchived]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedJobId = Number(params.get("job_id"));
    const requestedView = params.get("view");
    if (!requestedJobId) return;
    const requestedJob = jobs.find((job) => job.id === requestedJobId);
    if (requestedJob) {
      if (requestedView === "match" && requestedJob.match_data) {
        void openMatchHistory(requestedJob);
      } else {
        setEditor(editorFromJob(requestedJob));
        setMatchDataJob(null);
      }
    }
  }, [jobs]);

  function toggleBulkJob(jobId: number) {
    setSelectedBulkJobIds((current) =>
      current.includes(jobId) ? current.filter((id) => id !== jobId) : [...current, jobId],
    );
  }

  function startBulkMatch() {
    setBulkMode("match");
    setSelectedBulkJobIds([]);
  }

  function startBulkRemove() {
    setBulkMode("remove");
    setSelectedBulkJobIds([]);
  }

  function cancelBulkMode() {
    setBulkMode(null);
    setSelectedBulkJobIds([]);
  }

  function matchSelectedJobs() {
    if (!selectedBulkJobIds.length) return;
    const params = new URLSearchParams();
    params.set("job_ids", selectedBulkJobIds.join(","));
    window.location.href = `/match?${params.toString()}`;
  }

  async function removeSelectedJobs() {
    if (!selectedBulkJobIds.length) return;
    setError(null);
    setStatus(null);
    setIsBulkRemoving(true);
    try {
      const result = await bulkDeleteJobs(selectedBulkJobIds);
      setJobs((current) => current.filter((job) => !result.deleted_job_ids.includes(job.id)));
      if (editor?.id && result.deleted_job_ids.includes(editor.id)) {
        setEditor(null);
      }
      if (matchDataJob?.id && result.deleted_job_ids.includes(matchDataJob.id)) {
        setMatchDataJob(null);
      }
      const removedMessage = `${result.deleted_job_ids.length} saved job${result.deleted_job_ids.length === 1 ? "" : "s"} removed.`;
      const blockedMessage = result.blocked_jobs.length
        ? ` ${result.blocked_jobs.map((item) => item.message).join(" ")}`
        : "";
      setStatus(`${removedMessage}${blockedMessage}`);
      cancelBulkMode();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk remove failed.");
    } finally {
      setIsBulkRemoving(false);
    }
  }

  async function parseDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setMatchDataJob(null);
    setIsParsing(true);
    try {
      const draft = await draftJobFromUrl(jobUrl.trim());
      setEditor({
        title: draft.job_data.title,
        company: draft.job_data.company,
        source_url: draft.source_url ?? "",
        raw_description_text: draft.raw_description_text,
        job_data: draft.job_data,
        notes: "",
        showSaveButton: true,
        hasUserEdits: false,
        isEditing: true,
        archived_at: null,
      });
      setStatus("Review and edit the parsed job before saving.");
    } catch (err) {
      setEditor({
        ...emptyEditorState(),
        source_url: jobUrl.trim(),
      });
      setError(
        err instanceof Error
          ? `${err.message} You can manually complete the job below.`
          : "URL extraction failed. You can manually complete the job below.",
      );
    } finally {
      setIsParsing(false);
    }
  }

  function setJobDataField<K extends keyof JobDescriptionData>(key: K, value: JobDescriptionData[K]) {
    if (!editor) return;
    const nextJobData = {
      ...editor.job_data,
      [key]: value,
    };
    setEditor({
      ...editor,
      job_data: nextJobData,
      title: key === "title" ? String(value) : editor.title,
      company: key === "company" ? String(value) : editor.company,
      hasUserEdits: true,
    });
  }

  async function saveJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor) return;
    if (editor.id && !editor.isEditing) return;
    setError(null);
    setStatus(null);
    if (!editor.raw_description_text.trim()) {
      setError("Add the job description before saving.");
      return;
    }
    const jobData = {
      ...editor.job_data,
      title: editor.title.trim(),
      company: editor.company.trim(),
    };
    const payload: JobSavePayload = {
      title: editor.title.trim(),
      company: editor.company.trim(),
      source_url: editor.source_url.trim() || undefined,
      raw_description_text: editor.raw_description_text.trim(),
      job_data: jobData,
      notes: editor.notes.trim() || null,
      save_as_user_edit: editor.hasUserEdits || !editor.source_url.trim(),
    };
    setIsSaving(true);
    try {
      const saved = editor.id
        ? await updateJob(editor.id, editor.hasUserEdits ? payload : { notes: editor.notes.trim() || null })
        : await createJob(payload);
      if (!editor.id && creationMode) {
        window.location.href = "/jobs";
        return;
      }
      setEditor(null);
      setStatus(editor.id ? "Job updated." : "Job saved.");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function analyzeSavedJob(job: StoredJob) {
    setError(null);
    setStatus(null);
    setAnalyzingJobId(job.id);
    try {
      const analyzed = await analyzeJob(job.id);
      setJobs((current) => current.map((item) => (item.id === analyzed.id ? analyzed : item)));
      setStatus("Job analysis completed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job analysis failed.");
    } finally {
      setAnalyzingJobId(null);
    }
  }

  async function openMatchHistory(job: StoredJob) {
    setError(null);
    try {
      const payload = await listJobMatches(job.id);
      setMatchHistory(payload.matches);
      setMatchDataJob(job);
      setEditor(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Match history failed to load.");
    }
  }

  async function archiveSavedJob(jobId: number) {
    setError(null);
    try {
      await archiveJob(jobId);
      setEditor(null);
      setMatchDataJob(null);
      setStatus("Saved job archived.");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job archive failed.");
    }
  }

  async function restoreSavedJob(jobId: number) {
    setError(null);
    try {
      await restoreJob(jobId);
      setEditor(null);
      setStatus("Saved job restored.");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job restore failed.");
    }
  }

  async function permanentlyRemoveSavedJob(jobId: number) {
    if (!window.confirm("Remove this saved job? This cannot be undone from the website.")) return;
    setError(null);
    try {
      await deleteJob(jobId);
      setEditor(null);
      setMatchDataJob(null);
      setStatus("Saved job removed.");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job removal failed.");
    }
  }

  if (creationMode) {
    return (
      <div className="jobs-manager job-creation-manager">
        {error ? <div className="error-banner">{error}</div> : null}
        {status ? <div className="status-banner">{status}</div> : null}

        {creationMode === "url" && !editor ? (
          <section className="profile-card job-creation-card">
            <div>
              <h2>Import from a job URL</h2>
              <p className="metadata">Paste one job posting URL to extract a reviewable job profile.</p>
            </div>
            <form className="stack-form" onSubmit={parseDraft}>
              <label>
                Job URL
                <input
                  type="url"
                  value={jobUrl}
                  onChange={(event) => setJobUrl(event.target.value)}
                  placeholder="https://company.com/careers/job-id"
                  required
                />
              </label>
              <button type="submit" disabled={isParsing}>
                {isParsing ? "Parsing..." : "Create Job Profile"}
              </button>
            </form>
          </section>
        ) : null}

        {editor && !editor.id ? (
          <JobEditor
            editor={editor}
            isSaving={isSaving}
            onSave={saveJob}
            onChange={setEditor}
            onJobDataChange={setJobDataField}
            onClose={() => {
              if (creationMode === "manual") window.location.href = "/jobs";
              else setEditor(null);
            }}
            onArchive={archiveSavedJob}
            onRestore={restoreSavedJob}
            onDelete={permanentlyRemoveSavedJob}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="jobs-manager">
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="profile-card job-add-card">
        <div>
          <h2>Add a Job</h2>
          <p className="metadata">Import one job description, multiple jobs from a search list, or add one manually.</p>
        </div>
        <div className="job-create-actions" aria-label="Create a saved job">
          <a className="button-link" href="/jobs/import-url">Import Job</a>
          <a className="button-link secondary-button" href="/jobs/import">Import Job List</a>
          <a className="button-link secondary-button" href="/jobs/manual">Create Manual Job</a>
        </div>
      </section>

      <section className="saved-jobs-workspace">
        <section className="profile-card saved-jobs-list-card">
          <div className="profile-card-header">
            <h2>Saved Jobs</h2>
            <div className="button-row">
              <label>
                <input
                  type="checkbox"
                  checked={showArchived}
                  onChange={(event) => setShowArchived(event.target.checked)}
                />{" "}
                Show archived
              </label>
              {bulkMode ? (
                <>
                  <button type="button" className="secondary-button" onClick={cancelBulkMode}>
                    Cancel
                  </button>
                  {bulkMode === "match" ? (
                    <button type="button" disabled={!selectedBulkJobIds.length} onClick={matchSelectedJobs}>
                      Match with Selected
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={!selectedBulkJobIds.length || isBulkRemoving}
                      onClick={() => void removeSelectedJobs()}
                    >
                      {isBulkRemoving ? "Removing..." : "Remove Selected"}
                    </button>
                  )}
                </>
              ) : (
                <>
                  <button type="button" onClick={startBulkMatch}>
                    Bulk Match
                  </button>
                  <button type="button" className="secondary-button" onClick={startBulkRemove}>
                    Bulk Remove
                  </button>
                </>
              )}
              <button type="button" className="secondary-button" onClick={() => void loadJobs()}>
                Refresh
              </button>
            </div>
          </div>
          {bulkMode ? (
            <p className="metadata">
              {bulkMode === "match"
                ? "Select saved jobs to compare against one resume on the Match page."
                : "Select saved jobs to remove from your saved jobs list."}
            </p>
          ) : null}
          {isLoading ? <p className="empty">Loading jobs.</p> : null}
          {!isLoading && !sortedJobs.length ? <p className="empty">No saved jobs.</p> : null}
          <div className="job-list">
            {sortedJobs.map((job) => {
              const jobData = jobDataOrEmpty(job);
              const hasJobData = Boolean(job.job_data);
              const isSelected = editor?.id === job.id || matchDataJob?.id === job.id;
              return (
                <article
                  className={`job-row${bulkMode ? " job-row-bulk" : ""}${isSelected ? " selected" : ""}`}
                  key={job.id}
                >
                  {bulkMode ? (
                    <label className="bulk-job-checkbox" aria-label={`Select ${job.title || "Untitled Job"}`}>
                      <input
                        type="checkbox"
                        checked={selectedBulkJobIds.includes(job.id)}
                        onChange={() => toggleBulkJob(job.id)}
                      />
                    </label>
                  ) : null}
                  <div className="job-score-cell">
                    <span className="score-badge">{job.match_score === null ? "N/A" : `${job.match_score}/10`}</span>
                  </div>
                  <div>
                    <h2>
                      {job.title || "Untitled Job"}
                      {job.archived_at ? " (Archived)" : ""}
                    </h2>
                    <p className="metadata">
                      {job.company || "Unknown company"} | {jobData.work_location || "Location not set"} |{" "}
                      {jobData.application_deadline || "Deadline Unavailable"}
                    </p>
                    <p className="summary">{jobData.summary || "No structured summary saved yet."}</p>
                    <JobNotesPreview notes={job.notes} />
                  </div>
                  <div className="button-row job-row-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        window.location.href = matchPageHref(job);
                      }}
                    >
                      Match
                    </button>
                    {!hasJobData ? (
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={analyzingJobId === job.id}
                        onClick={() => void analyzeSavedJob(job)}
                      >
                        {analyzingJobId === job.id ? "Analyzing..." : "Analyze"}
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={!job.match_data}
                          onClick={() => void openMatchHistory(job)}
                        >
                          Match Data
                        </button>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() => {
                            setEditor(editorFromJob(job));
                            setMatchDataJob(null);
                          }}
                        >
                          View
                        </button>
                      </>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <div className="saved-jobs-detail-pane">
          {editor?.id ? (
            <JobEditor
              editor={editor}
              isSaving={isSaving}
              onSave={saveJob}
              onChange={setEditor}
              onJobDataChange={setJobDataField}
              onClose={() => setEditor(null)}
              onArchive={archiveSavedJob}
              onRestore={restoreSavedJob}
              onDelete={permanentlyRemoveSavedJob}
            />
          ) : null}

          {matchDataJob ? (
            <MatchDataViewer
              job={matchDataJob}
              resumeLabel={resumeReferenceLabel(matchDataJob, resumeProfiles, documents)}
              matches={matchHistory}
              onClose={() => setMatchDataJob(null)}
            />
          ) : null}

          {!editor?.id && !matchDataJob ? (
            <section className="saved-jobs-empty-detail">
              <h2>Job Details</h2>
              <p className="empty">Select View or Match Data from a saved job to open details here.</p>
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function JobsManagerPreview() {
  const previewJobs = [
    {
      title: "Backend Software Engineer",
      company: "Example Cloud Co",
      location: "Remote",
      deadline: "Deadline Unavailable",
      score: "8/10",
      summary: "Build APIs, improve data workflows, and collaborate with product engineering teams.",
    },
    {
      title: "Data Platform Engineer",
      company: "Sample Analytics",
      location: "Maryland",
      deadline: "Deadline Unavailable",
      score: "6/10",
      summary: "Support data pipelines, SQL modeling, and operational reporting systems.",
    },
  ];

  return (
    <div className="jobs-manager">
      <div className="warning-banner">
        Login is required to save jobs, import postings, write notes, analyze jobs, and run matching.
      </div>
      <section className="profile-card job-add-card">
        <div>
          <h2>Add a Job</h2>
          <p className="metadata">Import one job description, multiple jobs from a search list, or add one manually.</p>
        </div>
        <div className="job-create-actions" aria-label="Preview job creation options">
          <a className="button-link" href="/jobs/import-url">Import Job</a>
          <a className="button-link secondary-button" href="/jobs/import">Import Job List</a>
          <a className="button-link secondary-button" href="/jobs/manual">Create Manual Job</a>
        </div>
      </section>

      <section className="saved-jobs-workspace">
        <section className="profile-card saved-jobs-list-card">
          <div className="profile-card-header">
            <h2>Saved Jobs</h2>
            <div className="button-row">
              <button type="button" disabled>
                Bulk Match
              </button>
              <button type="button" className="secondary-button" disabled>
                Bulk Remove
              </button>
              <button type="button" className="secondary-button" disabled>
                Refresh
              </button>
            </div>
          </div>
          <div className="job-list">
            {previewJobs.map((job) => (
              <article className="job-row" key={job.title}>
                <div className="job-score-cell">
                  <span className="score-badge">{job.score}</span>
                </div>
                <div>
                  <h2>{job.title}</h2>
                  <p className="metadata">
                    {job.company} | {job.location} | {job.deadline}
                  </p>
                  <p className="summary">{job.summary}</p>
                </div>
                <div className="button-row job-row-actions">
                  <button type="button" className="secondary-button" disabled>
                    Match
                  </button>
                  <button type="button" className="secondary-button" disabled>
                    Match Data
                  </button>
                  <button type="button" className="secondary-button" disabled>
                    View
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className="saved-jobs-empty-detail">
          <h2>Job Details</h2>
          <p className="empty">Login to open saved job details, notes, and match data here.</p>
          <a className="button-link" href="/auth">
            Login / Register
          </a>
        </section>
      </section>
    </div>
  );
}

function JobCreationPreview({ mode }: { mode: ImportMode }) {
  return (
    <div className="jobs-manager job-creation-manager">
      <div className="warning-banner">Login is required to create and save a job profile.</div>
      <section className="profile-card job-creation-card">
        <h2>{mode === "url" ? "Import from a job URL" : "Create a manual job"}</h2>
        <p className="metadata">
          {mode === "url"
            ? "After login, paste a job URL and review the extracted profile before saving."
            : "After login, enter the job description and structured details manually."}
        </p>
        <a className="button-link" href="/auth">Login / Register</a>
      </section>
    </div>
  );
}

function MatchDataViewer({
  job,
  resumeLabel,
  matches,
  onClose,
}: {
  job: StoredJob;
  resumeLabel: string;
  matches: JobResumeMatchHistory[];
  onClose: () => void;
}) {
  const [selectedMatchId, setSelectedMatchId] = useState<number | null>(matches[0]?.id ?? null);
  const selectedMatch = matches.find((item) => item.id === selectedMatchId) ?? matches[0] ?? null;
  const viewedJob = selectedMatch ? { ...job, match_data: selectedMatch.match_data } : job;
  const matchData = matchDataViewFromJob(viewedJob);
  const selectedResumeLabel = selectedMatch?.id === matches[0]?.id
    ? resumeLabel
    : selectedMatch?.resume_profile_id
      ? `Resume profile #${selectedMatch.resume_profile_id}`
      : selectedMatch?.resume_document_id
        ? `Document #${selectedMatch.resume_document_id}`
        : resumeLabel;

  return (
    <section className="profile-card">
      <div className="profile-card-header">
        <div>
          <h2>Match Data</h2>
          <p className="metadata">
            {job.title || "Untitled Job"} | {job.company || "Unknown company"}
          </p>
          <p className="metadata">Compared resume: {selectedResumeLabel}</p>
        </div>
        <button type="button" className="secondary-button" onClick={onClose}>
          Close
        </button>
      </div>
      {matches.length > 1 ? (
        <div className="button-row" aria-label="Match history">
          {matches.map((match) => (
            <button
              type="button"
              className={match.id === selectedMatch?.id ? "" : "secondary-button"}
              key={match.id}
              onClick={() => setSelectedMatchId(match.id)}
            >
              {match.match_score}/10 | {new Date(match.created_at).toLocaleDateString()}
            </button>
          ))}
        </div>
      ) : null}
      {selectedMatch?.is_stale ? (
        <div className="warning-banner">
          This historical result is older than the current {selectedMatch.resume_is_stale ? "resume" : ""}
          {selectedMatch.resume_is_stale && selectedMatch.job_is_stale ? " and " : ""}
          {selectedMatch.job_is_stale ? "job data" : ""}. Run Match again to create a new result; this one will remain unchanged.
        </div>
      ) : null}
      {selectedMatch ? (
        <p className="metadata">
          {selectedMatch.provider} | {selectedMatch.model_name || "Model unavailable"} | Prompt {selectedMatch.prompt_version}
        </p>
      ) : null}
      {viewedJob.match_data ? (
        <section className="result-panel" aria-live="polite">
          <div className="score-row">
            <div className="score">{matchData.match_score ?? "N/A"}</div>
            <div>
              <p className="score-label">Match score</p>
              <p className="summary">{matchData.summary}</p>
            </div>
          </div>

          <div className="result-grid">
            <MatchDataList title="Matched Skills" items={matchData.matched_skills} />
            <MatchDataList title="Missing Skills" items={matchData.missing_skills} />
            <MatchDataList title="Matched Keywords" items={matchData.matched_keywords} />
            <MatchDataList title="Missing Keywords" items={matchData.missing_keywords} />
          </div>

          <div className="detail-grid">
            <section>
              <h2>Supported Requirements</h2>
              {matchData.supported_requirements.length ? (
                <ul>
                  {matchData.supported_requirements.map((item) => (
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
              {matchData.unsupported_requirements.length ? (
                <ul>
                  {matchData.unsupported_requirements.map((item) => (
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

          <MatchDataList title="Recommended Resume Updates" items={matchData.recommended_resume_updates} />

          <details>
            <summary>Raw Match JSON</summary>
            <pre className="text-preview">{JSON.stringify(viewedJob.match_data, null, 2)}</pre>
          </details>
        </section>
      ) : (
        <p className="empty">No match data has been saved for this job.</p>
      )}
    </section>
  );
}

function MatchDataList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="result-list">
      <h2>{title}</h2>
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

function JobNotesPreview({ notes }: { notes: string | null }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const cleaned = notes?.trim();
  const lines = notePreviewLines(notes);
  if (!cleaned || !lines.length) return null;

  return (
    <button
      type="button"
      className={`job-notes-preview${isExpanded ? " job-notes-preview-expanded" : ""}`}
      onClick={() => setIsExpanded((current) => !current)}
      aria-expanded={isExpanded}
    >
      {isExpanded ? (
        <span className="job-notes-preview-full">{cleaned}</span>
      ) : (
        lines.map((line, index) => (
          <span className="job-notes-preview-line" key={`${index}-${line}`}>
            {line}
          </span>
        ))
      )}
    </button>
  );
}

function JobEditor({
  editor,
  isSaving,
  onSave,
  onChange,
  onJobDataChange,
  onClose,
  onArchive,
  onRestore,
  onDelete,
}: {
  editor: JobEditorState;
  isSaving: boolean;
  onSave: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onChange: (value: JobEditorState) => void;
  onJobDataChange: <K extends keyof JobDescriptionData>(key: K, value: JobDescriptionData[K]) => void;
  onClose: () => void;
  onArchive: (jobId: number) => Promise<void>;
  onRestore: (jobId: number) => Promise<void>;
  onDelete: (jobId: number) => Promise<void>;
}) {
  const isSavedJob = Boolean(editor.id);
  const canEdit = !isSavedJob || editor.isEditing;
  const detailFieldHint = isSavedJob
    ? canEdit
      ? "Changes save only to your saved job copy."
      : "Click Edit before changing this saved job."
    : undefined;
  const updateDetail = (patch: Partial<JobEditorState>) => onChange({ ...editor, ...patch, hasUserEdits: true });

  return (
    <form
      className="profile-card job-editor"
      onSubmit={(event) => {
        if (isSavedJob && !editor.isEditing) {
          event.preventDefault();
          return;
        }
        void onSave(event);
      }}
    >
      <div className="profile-card-header">
        <div>
          <h2>{isSavedJob ? "Saved Job Details" : "Review Job Draft"}</h2>
          <p className="metadata">
            {isSavedJob ? `Job ID: ${editor.id}` : "Nothing is saved until you click Save Job."}
          </p>
        </div>
        <div className="button-row">
          {editor.id ? (
            editor.archived_at ? (
              <button type="button" className="secondary-button" onClick={() => void onRestore(editor.id!)}>
                Restore
              </button>
            ) : (
              <button type="button" className="secondary-button" onClick={() => void onArchive(editor.id!)}>
                Archive
              </button>
            )
          ) : null}
          {editor.id ? (
            <button type="button" className="secondary-button" onClick={() => void onDelete(editor.id!)}>
              Delete
            </button>
          ) : null}
          <button type="button" className="secondary-button" onClick={onClose}>
            Close
          </button>
          {isSavedJob && !editor.isEditing ? (
            <button
              type="button"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onChange({ ...editor, isEditing: true });
              }}
            >
              Edit
            </button>
          ) : editor.showSaveButton ? (
            <button type="submit" disabled={isSaving}>
              {isSaving ? "Saving..." : isSavedJob ? "Save changes" : "Save Job"}
            </button>
          ) : null}
        </div>
      </div>

      <label>
        Notes
        <textarea
          value={editor.notes}
          readOnly={!canEdit}
          onChange={(event) => onChange({ ...editor, notes: event.target.value })}
        />
      </label>

      <div className="profile-grid">
        <label>
          Title
          <input
            value={editor.title}
            readOnly={!canEdit}
            onChange={(event) => updateDetail({ title: event.target.value })}
            title={detailFieldHint}
          />
        </label>
        <label>
          Company
          <input
            value={editor.company}
            readOnly={!canEdit}
            onChange={(event) => updateDetail({ company: event.target.value })}
            title={detailFieldHint}
          />
        </label>
        <label>
          Source URL
          <input
            type="url"
            value={editor.source_url}
            readOnly={!canEdit}
            onChange={(event) => updateDetail({ source_url: event.target.value })}
            title={detailFieldHint}
          />
        </label>
        <label>
          Deadline
          <input
            value={
              isSavedJob && !canEdit && !editor.job_data.application_deadline.trim()
                ? "Deadline Unavailable"
                : editor.job_data.application_deadline
            }
            placeholder="Deadline Unavailable"
            readOnly={!canEdit}
            onChange={(event) => onJobDataChange("application_deadline", event.target.value)}
            title={detailFieldHint}
          />
        </label>
        <label>
          Location
          <input
            value={editor.job_data.work_location}
            readOnly={!canEdit}
            onChange={(event) => onJobDataChange("work_location", event.target.value)}
            title={detailFieldHint}
          />
        </label>
        <label>
          Salary
          <input
            value={editor.job_data.salary_range}
            readOnly={!canEdit}
            onChange={(event) => onJobDataChange("salary_range", event.target.value)}
            title={detailFieldHint}
          />
        </label>
        <label>
          Employment Type
          <input
            value={editor.job_data.employment_type}
            readOnly={!canEdit}
            onChange={(event) => onJobDataChange("employment_type", event.target.value)}
            title={detailFieldHint}
          />
        </label>
        <label>
          Seniority
          <input
            value={editor.job_data.seniority_level}
            readOnly={!canEdit}
            onChange={(event) => onJobDataChange("seniority_level", event.target.value)}
            title={detailFieldHint}
          />
        </label>
      </div>

      <label>
        Summary
        <textarea
          value={editor.job_data.summary}
          readOnly={!canEdit}
          onChange={(event) => onJobDataChange("summary", event.target.value)}
          title={detailFieldHint}
        />
      </label>

      <div className="profile-columns">
        {arrayFields.map((field) => (
          <label className="section-editor" key={field}>
            {arrayFieldLabels[field]}
            <textarea
              value={listToText(editor.job_data[field])}
              readOnly={!canEdit}
              onChange={(event) => onJobDataChange(field, textToList(event.target.value))}
              placeholder="One item per line"
              title={detailFieldHint}
            />
          </label>
        ))}
      </div>

      <label>
        Security Clearance
        <input
          value={editor.job_data.security_clearance}
          readOnly={!canEdit}
          onChange={(event) => onJobDataChange("security_clearance", event.target.value)}
          title={detailFieldHint}
        />
      </label>

      <details>
        <summary>Raw Job Description</summary>
        <label className="details-field">
          Raw Job Description
          <textarea
            value={editor.raw_description_text}
            readOnly={!canEdit}
            onChange={(event) => updateDetail({ raw_description_text: event.target.value })}
            required
            title={detailFieldHint}
          />
        </label>
      </details>

      <details>
        <summary>Job JSON preview</summary>
        <pre className="text-preview">{JSON.stringify({ ...editor.job_data, title: editor.title, company: editor.company }, null, 2)}</pre>
      </details>
    </form>
  );
}
