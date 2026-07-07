"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  applyResumeProfileSuggestions,
  createResumeProfile,
  deleteResumeProfile,
  emptyResumeData,
  getAuthToken,
  importResumePdf,
  listResumeProfiles,
  ResumeData,
  ResumeImportResponse,
  ResumeProfile,
  updateResumeProfile,
} from "../lib/api";

type SectionKey =
  | "experience"
  | "skills"
  | "education"
  | "certifications"
  | "projects"
  | "awards"
  | "publications"
  | "languages"
  | "volunteer"
  | "target_roles"
  | "notes";

const sectionLabels: Record<SectionKey, string> = {
  experience: "Experience",
  skills: "Skills",
  education: "Education",
  certifications: "Certifications",
  projects: "Projects",
  awards: "Awards",
  publications: "Publications",
  languages: "Languages",
  volunteer: "Volunteer",
  target_roles: "Target Roles",
  notes: "Notes",
};

const editableSections: SectionKey[] = [
  "experience",
  "skills",
  "education",
  "certifications",
  "projects",
  "awards",
  "publications",
  "languages",
  "volunteer",
  "target_roles",
  "notes",
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

function normalizeResumeData(value?: Partial<ResumeData> | null): ResumeData {
  return {
    ...emptyResumeData,
    ...(value ?? {}),
  };
}

function makeSectionText(data: ResumeData): Record<SectionKey, string> {
  return Object.fromEntries(
    editableSections.map((key) => [key, listToText(data[key])]),
  ) as Record<SectionKey, string>;
}

function profilePreview(data: ResumeData): string {
  const parts = [
    data.summary,
    data.experience[0],
    data.projects[0],
    data.education[0],
  ].filter(Boolean);
  return parts[0] || "No preview content yet.";
}

function sortResumeProfiles(profiles: ResumeProfile[]): ResumeProfile[] {
  return [...profiles].sort((a, b) => {
    if (a.is_default !== b.is_default) {
      return a.is_default ? -1 : 1;
    }
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
}

export function ProfileEditor() {
  if (!getAuthToken()) {
    return <ProfileEditorPreview />;
  }

  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [title, setTitle] = useState("Master Resume");
  const [resumeData, setResumeData] = useState<ResumeData>(emptyResumeData);
  const [sectionText, setSectionText] = useState<Record<SectionKey, string>>(
    makeSectionText(emptyResumeData),
  );
  const [resumeImport, setResumeImport] = useState<ResumeImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportingResume, setIsImportingResume] = useState(false);
  const [isApplyingResume, setIsApplyingResume] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const selectedProfile = useMemo(
    () => resumeProfiles.find((profile) => profile.id === selectedId) ?? null,
    [resumeProfiles, selectedId],
  );

  function setEditorFromProfile(profile: ResumeProfile) {
    const normalized = normalizeResumeData(profile.resume_data);
    setSelectedId(profile.id);
    setTitle(profile.title);
    setResumeData(normalized);
    setSectionText(makeSectionText(normalized));
  }

  function upsertResumeProfile(profile: ResumeProfile) {
    setResumeProfiles((current) => {
      const withoutSaved = current.filter((item) => item.id !== profile.id);
      return sortResumeProfiles([...withoutSaved, profile]);
    });
    setEditorFromProfile(profile);
  }

  async function loadResumeProfiles(selectId?: number) {
    setError(null);
    setIsLoading(true);
    try {
      const payload = await listResumeProfiles();
      setResumeProfiles(payload.resume_profiles);
      const nextSelection =
        payload.resume_profiles.find((profile) => profile.id === selectId) ??
        payload.resume_profiles.find((profile) => profile.id === selectedId) ??
        payload.resume_profiles[0] ??
        null;
      if (nextSelection) {
        setEditorFromProfile(nextSelection);
      } else {
        setSelectedId(null);
        setTitle("Master Resume");
        setResumeData(emptyResumeData);
        setSectionText(makeSectionText(emptyResumeData));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume profiles failed to load.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadResumeProfiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function buildResumeDataFromEditor(): ResumeData {
    const next: ResumeData = {
      ...resumeData,
    };
    for (const key of editableSections) {
      next[key] = textToList(sectionText[key]);
    }
    return next;
  }

  async function saveResumeProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setIsSaving(true);
    try {
      const payload = {
        title: title.trim() || "Untitled Resume",
        resume_data: buildResumeDataFromEditor(),
      };
      const saved = selectedProfile
        ? await updateResumeProfile(selectedProfile.id, payload)
        : await createResumeProfile({ ...payload, is_default: false });
      upsertResumeProfile(saved);
      setStatus("Resume profile saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume profile save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function createBlankResumeProfile() {
    setError(null);
    setStatus(null);
    try {
      const created = await createResumeProfile({
        title: "Untitled Resume",
        resume_data: emptyResumeData,
        is_default: false,
      });
      upsertResumeProfile(created);
      setStatus("Blank resume profile created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume profile creation failed.");
    }
  }

  async function setDefaultProfile(profile: ResumeProfile) {
    setError(null);
    setStatus(null);
    try {
      const updated = await updateResumeProfile(profile.id, { is_default: true });
      upsertResumeProfile(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Default resume update failed.");
    }
  }

  async function removeSelectedResumeProfile() {
    if (!selectedProfile) return;
    setError(null);
    setStatus(null);
    try {
      await deleteResumeProfile(selectedProfile.id);
      await loadResumeProfiles();
      setStatus("Resume profile deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume profile delete failed.");
    }
  }

  async function importResume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setResumeImport(null);
    const input = event.currentTarget.elements.namedItem("resume") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;

    setIsImportingResume(true);
    try {
      const imported = await importResumePdf(file);
      setResumeImport(imported);
      setStatus("Resume parsed for preview only. Nothing is saved until you click Apply JSON.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume import failed.");
    } finally {
      setIsImportingResume(false);
    }
  }

  async function applyResumeImport() {
    if (!resumeImport) return;
    setError(null);
    setStatus(null);
    setIsApplyingResume(true);
    try {
      const saved = await applyResumeProfileSuggestions(resumeImport);
      setResumeImport(null);
      upsertResumeProfile(saved);
      setStatus("Resume suggestions saved as a new resume profile.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Applying resume suggestions failed.");
    } finally {
      setIsApplyingResume(false);
    }
  }

  if (isLoading) {
    return <p className="empty">Loading resume profiles.</p>;
  }

  return (
    <div className="profile-editor">
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Import Master Resume</h2>
            <p className="metadata">
              Upload a PDF resume to generate a structured resume profile preview. Parsing does
              not save changes.
            </p>
          </div>
        </div>
        <form className="inline-form resume-upload-form" onSubmit={importResume}>
          <input name="resume" type="file" accept="application/pdf" required />
          <button type="submit" disabled={isImportingResume}>
            {isImportingResume ? "Parsing..." : "Parse Resume"}
          </button>
        </form>
        {resumeImport ? (
          <ResumeImportReview
            result={resumeImport}
            isApplying={isApplyingResume}
            onApply={applyResumeImport}
            onDiscard={() => setResumeImport(null)}
          />
        ) : null}
      </section>

      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Resume Profiles</h2>
            <p className="metadata">Your default resume appears first.</p>
          </div>
          <button type="button" className="secondary-button" onClick={() => void createBlankResumeProfile()}>
            New Resume
          </button>
        </div>
        {resumeProfiles.length ? (
          <div className="resume-profile-list">
            {resumeProfiles.map((profile) => (
              <ResumeProfileCard
                key={profile.id}
                profile={profile}
                isSelected={profile.id === selectedId}
                onOpen={() => setEditorFromProfile(profile)}
                onSetDefault={() => void setDefaultProfile(profile)}
              />
            ))}
          </div>
        ) : (
          <p className="empty">No resume profiles yet.</p>
        )}
      </section>

      <form className="profile-card" onSubmit={saveResumeProfile}>
        <div className="profile-card-header">
          <div>
            <h2>Full Resume Profile</h2>
            {selectedProfile ? <p className="metadata">Resume Profile ID: {selectedProfile.id}</p> : null}
          </div>
          <div className="button-row">
            {selectedProfile ? (
              <button type="button" className="secondary-button" onClick={() => void removeSelectedResumeProfile()}>
                Delete
              </button>
            ) : null}
            <button type="submit" disabled={isSaving}>
              {isSaving ? "Saving..." : "Save Resume"}
            </button>
          </div>
        </div>

        <div className="profile-grid">
          <label>
            Resume Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            Headline
            <input
              value={resumeData.headline ?? ""}
              onChange={(event) =>
                setResumeData({ ...resumeData, headline: event.target.value || null })
              }
            />
          </label>
        </div>

        <label>
          Summary
          <textarea
            value={resumeData.summary ?? ""}
            onChange={(event) => setResumeData({ ...resumeData, summary: event.target.value || null })}
          />
        </label>

        <div className="profile-columns">
          {editableSections.map((key) => (
            <label key={key} className="section-editor">
              {sectionLabels[key]}
              <textarea
                value={sectionText[key]}
                onChange={(event) =>
                  setSectionText((current) => ({ ...current, [key]: event.target.value }))
                }
                placeholder="One item per line"
              />
            </label>
          ))}
        </div>
      </form>
    </div>
  );
}

function ProfileEditorPreview() {
  const previewData = normalizeResumeData({
    headline: "Backend Software Engineer",
    summary: "Builds APIs, data workflows, and user-facing tools.",
    experience: ["Built REST services and internal tools for product teams."],
    skills: ["Python", "SQL", "APIs", "React", "Testing"],
    education: ["B.S. Computer Science"],
    projects: ["Job matching prototype with structured resume data."],
  });
  const sectionText = makeSectionText(previewData);

  return (
    <div className="profile-editor">
      <div className="warning-banner">
        Login is required to upload, parse, edit, and save resume profiles.
      </div>
      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Import Master Resume</h2>
            <p className="metadata">Upload a PDF after login to generate structured resume JSON.</p>
          </div>
        </div>
        <form className="inline-form resume-upload-form">
          <input type="file" disabled />
          <button type="button" disabled>
            Parse Resume
          </button>
        </form>
      </section>
      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Resume Profiles</h2>
            <p className="metadata">Your default resume appears first.</p>
          </div>
          <button type="button" className="secondary-button" disabled>
            New Resume
          </button>
        </div>
        <div className="resume-profile-list">
          <article className="resume-profile-card selected">
            <button type="button" className="resume-profile-open" disabled>
              <span className="resume-profile-title">
                Software Engineering Resume
                <span className="default-label">Default</span>
              </span>
              <span className="metadata">{previewData.headline}</span>
              <span className="resume-profile-preview">{profilePreview(previewData)}</span>
            </button>
            <button type="button" className="secondary-button default-button" disabled>
              Default
            </button>
          </article>
        </div>
      </section>
      <form className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Full Resume Profile</h2>
            <p className="metadata">Preview only</p>
          </div>
          <button type="button" disabled>
            Save Resume
          </button>
        </div>
        <div className="profile-grid">
          <label>
            Resume Title
            <input value="Software Engineering Resume" readOnly />
          </label>
          <label>
            Headline
            <input value={previewData.headline ?? ""} readOnly />
          </label>
        </div>
        <label>
          Summary
          <textarea value={previewData.summary ?? ""} readOnly />
        </label>
        <div className="profile-columns">
          {editableSections.slice(0, 6).map((key) => (
            <label className="section-editor" key={key}>
              {sectionLabels[key]}
              <textarea value={sectionText[key]} readOnly />
            </label>
          ))}
        </div>
      </form>
      <a className="button-link" href="/auth">
        Login / Register to Edit Profiles
      </a>
    </div>
  );
}

function ResumeProfileCard({
  profile,
  isSelected,
  onOpen,
  onSetDefault,
}: {
  profile: ResumeProfile;
  isSelected: boolean;
  onOpen: () => void;
  onSetDefault: () => void;
}) {
  const data = normalizeResumeData(profile.resume_data);
  const skillPreview = data.skills.slice(0, 5);

  return (
    <article className={`resume-profile-card${isSelected ? " selected" : ""}`}>
      <button type="button" className="resume-profile-open" onClick={onOpen}>
        <span className="resume-profile-title">
          {profile.title}
          {profile.is_default ? <span className="default-label">Default</span> : null}
        </span>
        <span className="metadata">{data.headline || "No headline yet"}</span>
        <span className="resume-profile-preview">{profilePreview(data)}</span>
        {skillPreview.length ? (
          <span className="resume-chip-row">
            {skillPreview.map((skill) => (
              <span className="resume-chip" key={skill}>
                {skill}
              </span>
            ))}
          </span>
        ) : null}
      </button>
      <button
        type="button"
        className="secondary-button default-button"
        onClick={onSetDefault}
        disabled={profile.is_default}
        aria-label={profile.is_default ? "Default resume" : "Set default resume"}
      >
        {profile.is_default ? "Default" : "Set default"}
      </button>
    </article>
  );
}

function ResumeImportReview({
  result,
  isApplying,
  onApply,
  onDiscard,
}: {
  result: ResumeImportResponse;
  isApplying: boolean;
  onApply: () => Promise<void>;
  onDiscard: () => void;
}) {
  const suggestions = result.suggestions;

  return (
    <section className="resume-review">
      <div className="profile-card-header">
        <div>
          <h2>Parsed Resume JSON</h2>
          <p className="metadata">{result.file_name}</p>
        </div>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={onDiscard}>
            Discard
          </button>
          <button type="button" disabled={isApplying} onClick={() => void onApply()}>
            {isApplying ? "Applying..." : "Apply JSON"}
          </button>
        </div>
      </div>

      <div className="suggestion-grid">
        <ReviewText title="Headline" value={suggestions.headline} />
        <ReviewText title="Summary" value={suggestions.summary} />
      </div>

      <div className="suggestion-grid">
        <ReviewBlock title="Experience" items={suggestions.experience} />
        <ReviewBlock title="Skills" items={suggestions.skills} />
        <ReviewBlock title="Education" items={suggestions.education} />
        <ReviewBlock title="Projects" items={suggestions.projects} />
        <ReviewBlock title="Certifications" items={suggestions.certifications} />
        <ReviewBlock title="Notes" items={suggestions.notes} />
      </div>

      <details>
        <summary>Resume JSON preview</summary>
        <pre className="text-preview">{JSON.stringify(suggestions, null, 2)}</pre>
      </details>

      <details>
        <summary>Cleaned text preview</summary>
        <pre className="text-preview">{result.extracted_text_preview}</pre>
      </details>
    </section>
  );
}

function ReviewText({ title, value }: { title: string; value: string | null }) {
  return (
    <section className="result-list">
      <h2>{title}</h2>
      {value ? <p className="summary">{value}</p> : <p className="empty">No suggestion.</p>}
    </section>
  );
}

function ReviewBlock({ title, items }: { title: string; items: string[] }) {
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
        <p className="empty">No suggestions.</p>
      )}
    </section>
  );
}
