"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createJob,
  draftJobFromUrl,
  emptyJobDescriptionData,
  JobDescriptionData,
  JobSavePayload,
  listJobs,
  StoredJob,
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
  id?: string;
  title: string;
  company: string;
  source_url: string;
  raw_description_text: string;
  job_data: JobDescriptionData;
  notes: string;
  showSaveButton: boolean;
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

function editorFromJob(job: StoredJob, showSaveButton = true): JobEditorState {
  return {
    id: job.id,
    title: job.title,
    company: job.company,
    source_url: job.source_url ?? "",
    raw_description_text: job.raw_description_text,
    job_data: job.job_data,
    notes: job.notes ?? "",
    showSaveButton,
  };
}

export function JobsManager() {
  const [jobs, setJobs] = useState<StoredJob[]>([]);
  const [mode, setMode] = useState<ImportMode>("url");
  const [jobUrl, setJobUrl] = useState("");
  const [editor, setEditor] = useState<JobEditorState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isParsing, setIsParsing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

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
      setEditor(editorFromJob(saved, false));
      setStatus(editor.id ? "Job updated." : "Job saved.");
      await loadJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job save failed.");
    } finally {
      setIsSaving(false);
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
          {sortedJobs.map((job) => (
            <article className="job-row" key={job.id}>
              <div className="job-score-cell">
                <span className="score-badge">{job.match_score === null ? "N/A" : `${job.match_score}/10`}</span>
              </div>
              <div>
                <h2>{job.title || "Untitled Job"}</h2>
                <p className="metadata">
                  {job.company || "Unknown company"} | {job.job_data.work_location || "Location not set"} |{" "}
                  {job.job_data.application_deadline || "No deadline"}
                </p>
                <p className="summary">{job.job_data.summary || "No summary saved."}</p>
              </div>
              <button type="button" className="secondary-button" onClick={() => setEditor(editorFromJob(job))}>
                Edit
              </button>
            </article>
          ))}
        </div>
      </section>
    </div>
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
  return (
    <form className="profile-card job-editor" onSubmit={onSave}>
      <div className="profile-card-header">
        <div>
          <h2>{editor.id ? "Edit Job" : "Review Job Draft"}</h2>
          <p className="metadata">
            {editor.id
              ? `Job ID: ${editor.id}`
              : "Nothing is saved until you click Save Job."}
          </p>
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={onClose}>
            Close
          </button>
          {editor.showSaveButton ? (
            <button type="submit" disabled={isSaving}>
              {isSaving ? "Saving..." : "Save Job"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="profile-grid">
        <label>
          Title
          <input value={editor.title} onChange={(event) => onChange({ ...editor, title: event.target.value })} />
        </label>
        <label>
          Company
          <input value={editor.company} onChange={(event) => onChange({ ...editor, company: event.target.value })} />
        </label>
        <label>
          Source URL
          <input
            type="url"
            value={editor.source_url}
            onChange={(event) => onChange({ ...editor, source_url: event.target.value })}
          />
        </label>
        <label>
          Deadline
          <input
            value={editor.job_data.application_deadline}
            onChange={(event) => onJobDataChange("application_deadline", event.target.value)}
            placeholder="2026-07-01 or original posting text"
          />
        </label>
        <label>
          Location
          <input
            value={editor.job_data.work_location}
            onChange={(event) => onJobDataChange("work_location", event.target.value)}
          />
        </label>
        <label>
          Salary
          <input
            value={editor.job_data.salary_range}
            onChange={(event) => onJobDataChange("salary_range", event.target.value)}
          />
        </label>
        <label>
          Employment Type
          <input
            value={editor.job_data.employment_type}
            onChange={(event) => onJobDataChange("employment_type", event.target.value)}
          />
        </label>
        <label>
          Seniority
          <input
            value={editor.job_data.seniority_level}
            onChange={(event) => onJobDataChange("seniority_level", event.target.value)}
          />
        </label>
      </div>

      <label>
        Summary
        <textarea value={editor.job_data.summary} onChange={(event) => onJobDataChange("summary", event.target.value)} />
      </label>

      <div className="profile-columns">
        {arrayFields.map((field) => (
          <label className="section-editor" key={field}>
            {arrayFieldLabels[field]}
            <textarea
              value={listToText(editor.job_data[field])}
              onChange={(event) => onJobDataChange(field, textToList(event.target.value))}
              placeholder="One item per line"
            />
          </label>
        ))}
      </div>

      <label>
        Security Clearance
        <input
          value={editor.job_data.security_clearance}
          onChange={(event) => onJobDataChange("security_clearance", event.target.value)}
        />
      </label>

      <label>
        Raw Job Description
        <textarea
          value={editor.raw_description_text}
          onChange={(event) => onChange({ ...editor, raw_description_text: event.target.value })}
          required
        />
      </label>

      <label>
        Notes
        <textarea value={editor.notes} onChange={(event) => onChange({ ...editor, notes: event.target.value })} />
      </label>

      <details>
        <summary>Job JSON preview</summary>
        <pre className="text-preview">{JSON.stringify({ ...editor.job_data, title: editor.title, company: editor.company }, null, 2)}</pre>
      </details>
    </form>
  );
}
