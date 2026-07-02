"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  analyzeJob,
  createJob,
  draftJobFromUrl,
  emptyJobDescriptionData,
  JobDescriptionData,
  JobSavePayload,
  listDocuments,
  listJobs,
  listResumeProfiles,
  ResumeProfile,
  StoredJob,
  StoredDocument,
  updateJob,
} from "../lib/api";

type ImportMode = "url" | "manual";
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
  };
}

function matchPageHref(job: StoredJob): string {
  const params = new URLSearchParams();
  if (job.source_url) {
    params.set("job_url", job.source_url);
  }
  if (job.matched_resume_profile_id) {
    params.set("resume_profile_id", String(job.matched_resume_profile_id));
  }
  if (job.matched_resume_document_id) {
    params.set("resume_document_id", String(job.matched_resume_document_id));
  }
  const query = params.toString();
  return query ? `/?${query}` : "/";
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

export function JobsManager() {
  const [jobs, setJobs] = useState<StoredJob[]>([]);
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [mode, setMode] = useState<ImportMode>("url");
  const [jobUrl, setJobUrl] = useState("");
  const [editor, setEditor] = useState<JobEditorState | null>(null);
  const [matchDataJob, setMatchDataJob] = useState<StoredJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isParsing, setIsParsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [analyzingJobId, setAnalyzingJobId] = useState<number | null>(null);

  const sortedJobs = useMemo(() => jobs, [jobs]);

  async function loadJobs() {
    setError(null);
    setIsLoading(true);
    try {
      setJobs(await listJobs());
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
  }, []);

  function startManualJob() {
    setError(null);
    setStatus(null);
    setEditor(emptyEditorState());
  }

  async function parseDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
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
    });
  }

  async function saveJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor) return;
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
    };
    setIsSaving(true);
    try {
      const saved = editor.id ? await updateJob(editor.id, payload) : await createJob(payload);
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

  return (
    <div className="jobs-manager">
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Import Job</h2>
            <p className="metadata">Create a draft from a URL or start with manual entry.</p>
          </div>
          <button type="button" className="secondary-button" onClick={startManualJob}>
            Manual
          </button>
        </div>

        <div className="segmented-control">
          <button type="button" className={mode === "url" ? "active" : ""} onClick={() => setMode("url")}>
            URL
          </button>
          <button type="button" className={mode === "manual" ? "active" : ""} onClick={() => setMode("manual")}>
            Manual
          </button>
        </div>

        {mode === "manual" ? (
          <div className="warning-banner">
            Manual entry opens a blank editable job form. Add the description and fields, then save.
            <button type="button" onClick={startManualJob}>
              Start Manual Job
            </button>
          </div>
        ) : (
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
              {isParsing ? "Parsing..." : "Create Draft"}
            </button>
          </form>
        )}
      </section>

      {editor ? (
        <JobEditor
          editor={editor}
          isSaving={isSaving}
          onSave={saveJob}
          onChange={setEditor}
          onJobDataChange={setJobDataField}
          onClose={() => setEditor(null)}
        />
      ) : null}

      {matchDataJob ? (
        <MatchDataViewer
          job={matchDataJob}
          resumeLabel={resumeReferenceLabel(matchDataJob, resumeProfiles, documents)}
          onClose={() => setMatchDataJob(null)}
        />
      ) : null}

      <section className="profile-card">
        <div className="profile-card-header">
          <h2>Saved Jobs</h2>
          <button type="button" className="secondary-button" onClick={() => void loadJobs()}>
            Refresh
          </button>
        </div>
        {isLoading ? <p className="empty">Loading jobs.</p> : null}
        {!isLoading && !sortedJobs.length ? <p className="empty">No saved jobs.</p> : null}
        <div className="job-list">
          {sortedJobs.map((job) => {
            const jobData = jobDataOrEmpty(job);
            const hasJobData = Boolean(job.job_data);
            return (
              <article className="job-row" key={job.id}>
                <div className="job-score-cell">
                  <span className="score-badge">{job.match_score === null ? "N/A" : `${job.match_score}/10`}</span>
                </div>
                <div>
                  <h2>{job.title || "Untitled Job"}</h2>
                  <p className="metadata">
                    {job.company || "Unknown company"} | {jobData.work_location || "Location not set"} |{" "}
                    {jobData.application_deadline || "No deadline"}
                  </p>
                  <p className="summary">{jobData.summary || "No structured summary saved yet."}</p>
                  <JobNotesPreview notes={job.notes} />
                </div>
                <div className="button-row job-row-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!job.source_url}
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
                        onClick={() => setMatchDataJob(job)}
                      >
                        Match Data
                      </button>
                      <button type="button" className="secondary-button" onClick={() => setEditor(editorFromJob(job))}>
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
    </div>
  );
}

function MatchDataViewer({
  job,
  resumeLabel,
  onClose,
}: {
  job: StoredJob;
  resumeLabel: string;
  onClose: () => void;
}) {
  const matchData = matchDataViewFromJob(job);

  return (
    <section className="profile-card">
      <div className="profile-card-header">
        <div>
          <h2>Match Data</h2>
          <p className="metadata">
            {job.title || "Untitled Job"} | {job.company || "Unknown company"}
          </p>
          <p className="metadata">Compared resume: {resumeLabel}</p>
        </div>
        <button type="button" className="secondary-button" onClick={onClose}>
          Close
        </button>
      </div>
      {job.match_data ? (
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
            <pre className="text-preview">{JSON.stringify(job.match_data, null, 2)}</pre>
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
}: {
  editor: JobEditorState;
  isSaving: boolean;
  onSave: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onChange: (value: JobEditorState) => void;
  onJobDataChange: <K extends keyof JobDescriptionData>(key: K, value: JobDescriptionData[K]) => void;
  onClose: () => void;
}) {
  const isSavedJob = Boolean(editor.id);
  const detailFieldHint = isSavedJob ? "Saved job details are read-only." : undefined;

  return (
    <form className="profile-card job-editor" onSubmit={onSave}>
      <div className="profile-card-header">
        <div>
          <h2>{isSavedJob ? "Saved Job Details" : "Review Job Draft"}</h2>
          <p className="metadata">
            {isSavedJob ? `Job ID: ${editor.id}` : "Nothing is saved until you click Save Job."}
          </p>
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={onClose}>
            Close
          </button>
          {editor.showSaveButton ? (
            <button type="submit" disabled={isSaving}>
              {isSaving ? "Saving..." : isSavedJob ? "Save Notes" : "Save Job"}
            </button>
          ) : null}
        </div>
      </div>

      <label>
        Notes
        <textarea value={editor.notes} onChange={(event) => onChange({ ...editor, notes: event.target.value })} />
      </label>

      <div className="profile-grid">
        <label>
          Title
          <input
            value={editor.title}
            onChange={(event) => onChange({ ...editor, title: event.target.value })}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Company
          <input
            value={editor.company}
            onChange={(event) => onChange({ ...editor, company: event.target.value })}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Source URL
          <input
            type="url"
            value={editor.source_url}
            onChange={(event) => onChange({ ...editor, source_url: event.target.value })}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Deadline
          <input
            value={editor.job_data.application_deadline}
            onChange={(event) => onJobDataChange("application_deadline", event.target.value)}
            placeholder="2026-07-01 or original posting text"
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Location
          <input
            value={editor.job_data.work_location}
            onChange={(event) => onJobDataChange("work_location", event.target.value)}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Salary
          <input
            value={editor.job_data.salary_range}
            onChange={(event) => onJobDataChange("salary_range", event.target.value)}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Employment Type
          <input
            value={editor.job_data.employment_type}
            onChange={(event) => onJobDataChange("employment_type", event.target.value)}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
        <label>
          Seniority
          <input
            value={editor.job_data.seniority_level}
            onChange={(event) => onJobDataChange("seniority_level", event.target.value)}
            readOnly={isSavedJob}
            title={detailFieldHint}
          />
        </label>
      </div>

      <label>
        Summary
        <textarea
          value={editor.job_data.summary}
          onChange={(event) => onJobDataChange("summary", event.target.value)}
          readOnly={isSavedJob}
          title={detailFieldHint}
        />
      </label>

      <div className="profile-columns">
        {arrayFields.map((field) => (
          <label className="section-editor" key={field}>
            {arrayFieldLabels[field]}
            <textarea
              value={listToText(editor.job_data[field])}
              onChange={(event) => onJobDataChange(field, textToList(event.target.value))}
              placeholder="One item per line"
              readOnly={isSavedJob}
              title={detailFieldHint}
            />
          </label>
        ))}
      </div>

      <label>
        Security Clearance
        <input
          value={editor.job_data.security_clearance}
          onChange={(event) => onJobDataChange("security_clearance", event.target.value)}
          readOnly={isSavedJob}
          title={detailFieldHint}
        />
      </label>

      <details>
        <summary>Raw Job Description</summary>
        <label className="details-field">
          Raw Job Description
          <textarea
            value={editor.raw_description_text}
            onChange={(event) => onChange({ ...editor, raw_description_text: event.target.value })}
            required
            readOnly={isSavedJob}
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
