"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { FilePlus2, FileText, Pencil, Save, Trash2, Upload, X } from "lucide-react";
import {
  applyResumeProfileSuggestions,
  createResumeProfile,
  deleteResumeProfile,
  forceDeleteResumeProfile,
  getResumeProfileDependencies,
  emptyResumeData,
  getAuthToken,
  importResumePdf,
  listResumeProfiles,
  retryResumeImport,
  ResumeData,
  ResumeImportResponse,
  ResumeProfile,
  updateResumeProfile,
} from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, IconButton, SectionHeader, SkeletonRows, ToastRegion } from "./ui";

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

  return <AuthenticatedProfileEditor />;
}

function AuthenticatedProfileEditor() {
  const [resumeProfiles, setResumeProfiles] = useState<ResumeProfile[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [title, setTitle] = useState("Master Resume");
  const [resumeData, setResumeData] = useState<ResumeData>(emptyResumeData);
  const [sectionText, setSectionText] = useState<Record<SectionKey, string>>(
    makeSectionText(emptyResumeData),
  );
  const [resumeImport, setResumeImport] = useState<ResumeImportResponse | null>(null);
  const [selectedResumeFileName, setSelectedResumeFileName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportingResume, setIsImportingResume] = useState(false);
  const [isApplyingResume, setIsApplyingResume] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isCreatingProfile, setIsCreatingProfile] = useState(false);
  const [deletingProfileId, setDeletingProfileId] = useState<number | null>(null);

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
    setIsCreatingProfile(false);
    setIsEditing(false);
  }

  function toggleProfileSelection(profile: ResumeProfile) {
    if (selectedId === profile.id) {
      resetEditor();
      return;
    }
    setEditorFromProfile(profile);
  }

  function resetEditor() {
    setSelectedId(null);
    setTitle("Master Resume");
    setResumeData(emptyResumeData);
    setSectionText(makeSectionText(emptyResumeData));
    setIsCreatingProfile(false);
    setIsEditing(false);
  }

  function upsertResumeProfile(profile: ResumeProfile, options: { select?: boolean } = { select: true }) {
    setResumeProfiles((current) => {
      const withoutSaved = current.filter((item) => item.id !== profile.id);
      return sortResumeProfiles([...withoutSaved, profile]);
    });
    if (options.select) {
      setEditorFromProfile(profile);
    }
  }

  async function loadResumeProfiles(selectId?: number) {
    setError(null);
    setIsLoading(true);
    try {
      const payload = await listResumeProfiles();
      const sortedProfiles = sortResumeProfiles(payload.resume_profiles);
      setResumeProfiles(sortedProfiles);
      const nextSelection = selectId ? sortedProfiles.find((profile) => profile.id === selectId) ?? null : null;
      if (nextSelection) {
        setEditorFromProfile(nextSelection);
      } else {
        resetEditor();
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
      setIsCreatingProfile(false);
      upsertResumeProfile(saved);
      setIsEditing(false);
      setStatus("Resume profile saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume profile save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  function createBlankResumeProfile() {
    setError(null);
    setStatus(null);
    setSelectedId(null);
    setTitle("Untitled Resume");
    setResumeData(emptyResumeData);
    setSectionText(makeSectionText(emptyResumeData));
    setIsCreatingProfile(true);
    setIsEditing(true);
  }

  async function setDefaultProfile(profile: ResumeProfile) {
    setError(null);
    setStatus(null);
    try {
      const updated = await updateResumeProfile(profile.id, { is_default: true });
      upsertResumeProfile(updated, { select: selectedId === updated.id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Default resume update failed.");
    }
  }

  async function removeResumeProfile(profile: ResumeProfile) {
    setError(null);
    setStatus(null);
    setDeletingProfileId(profile.id);
    try {
      const dependencyReport = await getResumeProfileDependencies(profile.id);
      if (dependencyReport.dependencies.length) {
        const warning = dependencyReport.dependencies.map((item) => item.message).join("\n");
        const confirmed = window.confirm(
          `Delete "${profile.title}"?\n\n${warning}\n\nHistorical match snapshots will remain available, but this profile will no longer be selectable.`,
        );
        if (!confirmed) return;
        await forceDeleteResumeProfile(profile.id);
      } else {
        const confirmed = window.confirm(`Delete "${profile.title}"? This action cannot be undone.`);
        if (!confirmed) return;
        await deleteResumeProfile(profile.id);
      }
      setResumeProfiles((current) => {
        const remaining = current.filter((item) => item.id !== profile.id);
        if (!profile.is_default || remaining.length === 0 || remaining.some((item) => item.is_default)) {
          return sortResumeProfiles(remaining);
        }

        const fallback = [...remaining].sort((a, b) => {
          const updatedDifference = new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
          return updatedDifference || b.id - a.id;
        })[0];
        return sortResumeProfiles(
          remaining.map((item) => (item.id === fallback.id ? { ...item, is_default: true } : item)),
        );
      });
      if (selectedId === profile.id) {
        resetEditor();
      }
      setStatus("Resume profile deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume profile delete failed.");
    } finally {
      setDeletingProfileId(null);
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
      setStatus(
        imported.parse_warning
          ? "The resume file and cleaned text were saved, but automatic analysis needs attention."
          : "Resume analyzed for preview only. Nothing is saved until you click Save Resume Profile.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume import failed.");
    } finally {
      setIsImportingResume(false);
    }
  }

  async function retryImportedResume() {
    if (!resumeImport) return;
    setError(null);
    setStatus(null);
    setIsImportingResume(true);
    try {
      const retried = await retryResumeImport(resumeImport.document_id);
      setResumeImport(retried);
      setStatus(
        retried.parse_warning
          ? "Resume analysis is still unavailable. You can retry or create a manual profile from this saved document."
          : "Resume analysis completed. Review the suggestions before applying them.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resume analysis retry failed.");
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
      upsertResumeProfile(saved, { select: false });
      resetEditor();
      setStatus("Resume suggestions saved as a new resume profile. Select it from the list to view or edit it.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Saving resume profile failed.");
    } finally {
      setIsApplyingResume(false);
    }
  }

  if (isLoading) {
    return <SkeletonRows count={4} />;
  }

  return (
    <div className="profile-editor">
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />

      <section className="profile-card profile-import-card">
        <SectionHeader title="Upload Resume" description="Recommended: upload a PDF to generate a reviewable structured profile. Analysis does not save the JSON automatically." />
        <ResumePrivacyNotice />
        <form className="inline-form resume-upload-form" onSubmit={importResume}>
          <div className="resume-file-picker">
            <input
              className="sr-only resume-file-input"
              id="resume-file-upload"
              name="resume"
              type="file"
              accept="application/pdf"
              required
              onChange={(event) => setSelectedResumeFileName(event.target.files?.[0]?.name ?? "")}
            />
            <label className="button-link secondary-button action-with-icon resume-file-button" htmlFor="resume-file-upload">
              <Upload size={17} aria-hidden="true" /> Upload File
            </label>
            <span className="metadata resume-file-name" aria-live="polite">
              {selectedResumeFileName || "No file selected"}
            </span>
          </div>
          <Button type="submit" icon={Upload} loading={isImportingResume}>Analyze Resume</Button>
        </form>
        {resumeImport ? (
          <ResumeImportReview
            result={resumeImport}
            isApplying={isApplyingResume}
            isRetrying={isImportingResume}
            onApply={applyResumeImport}
            onRetry={retryImportedResume}
            onDiscard={() => setResumeImport(null)}
          />
        ) : null}
      </section>

      <section className="manual-resume-option">
        <SectionHeader
          title="Prefer manual entry?"
          description="Create a resume profile manually if you cannot upload a PDF or prefer to enter each section yourself."
        />
        <Button type="button" variant="secondary" icon={FilePlus2} onClick={createBlankResumeProfile}>Create Resume Profile</Button>
      </section>

      <section className="profile-workspace">
        <section className="profile-card resume-profiles-list-card">
          <div className="profile-card-header">
            <SectionHeader title="Your Resumes" description="Select a resume to preview its structured profile. Your default resume appears first." />
          </div>
          {resumeProfiles.length ? (
            <div className="resume-profile-list">
              {resumeProfiles.map((profile) => (
                <ResumeProfileCard
                  key={profile.id}
                  profile={profile}
                  isSelected={profile.id === selectedId}
                  onOpen={() => toggleProfileSelection(profile)}
                  onSetDefault={() => void setDefaultProfile(profile)}
                  onDelete={() => void removeResumeProfile(profile)}
                  isDeleting={deletingProfileId === profile.id}
                />
              ))}
            </div>
          ) : (
            <EmptyState icon={FileText} title="No resume profiles" description="Importing a PDF is recommended, or you can create a resume profile manually and enter each section yourself." />
          )}
        </section>

        <div className="profile-detail-pane">
          {isEditing && (selectedProfile || isCreatingProfile) ? (
            <form className="profile-card resume-profile-editor" onSubmit={saveResumeProfile}>
              <div className="profile-card-header">
                <div>
                  <p className="eyebrow">{isCreatingProfile ? "New resume profile" : "Editing resume"}</p>
                  <h2>{isCreatingProfile ? "Create Resume Profile" : selectedProfile?.title}</h2>
                  {selectedProfile ? <p className="metadata">Resume Profile ID: {selectedProfile.id}</p> : null}
                </div>
                <div className="button-row">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => selectedProfile ? setEditorFromProfile(selectedProfile) : resetEditor()}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" icon={Save} loading={isSaving}>Save Resume</Button>
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
          ) : selectedProfile ? (
            <ReadableResumeProfile
              profile={selectedProfile}
              onEdit={() => setIsEditing(true)}
              onClose={resetEditor}
            />
          ) : (
            <EmptyState icon={FileText} title="Resume profile details" description="Select a resume profile from the list to read or edit its full details." />
          )}
        </div>
      </section>
    </div>
  );
}

function ReadableResumeProfile({
  profile,
  onEdit,
  onClose,
}: {
  profile: ResumeProfile;
  onEdit: () => void;
  onClose: () => void;
}) {
  const data = normalizeResumeData(profile.resume_data);
  const populatedSections = editableSections.filter((key) => data[key].length > 0);

  return (
    <article className="profile-card readable-resume-profile">
      <header className="readable-resume-header">
        <div>
          <div className="resume-title-row">
            <h2>{profile.title}</h2>
            {profile.is_default ? <Badge tone="info">Default</Badge> : null}
          </div>
          <p className="metadata">Updated {new Date(profile.updated_at).toLocaleDateString()}</p>
        </div>
        <div className="button-row">
          <Button type="button" size="compact" icon={Pencil} onClick={onEdit}>Edit</Button>
          <Button type="button" size="compact" variant="secondary" icon={X} onClick={onClose}>Close</Button>
        </div>
      </header>
      {data.summary ? <section className="readable-resume-section"><h3>Summary</h3><p>{data.summary}</p></section> : null}
      {populatedSections.map((key) => (
        <section className="readable-resume-section" key={key}>
          <h3>{sectionLabels[key]}</h3>
          {key === "skills" ? (
            <div className="resume-chip-row">{data[key].map((item) => <span className="resume-chip" key={item}>{item}</span>)}</div>
          ) : (
            <ul>{data[key].map((item) => <li key={item}>{item}</li>)}</ul>
          )}
        </section>
      ))}
      {!data.summary && !populatedSections.length ? <EmptyState compact icon={FileText} title="Empty resume profile" description="Click Edit to add resume information." /> : null}
    </article>
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
        Login is required to upload, analyze, edit, and save resume profiles.
      </div>
      <section className="profile-card profile-import-card">
        <div className="profile-card-header">
          <div>
            <h2>Upload Resume</h2>
            <p className="metadata">Recommended: upload a PDF after login to generate a structured resume profile.</p>
          </div>
        </div>
        <ResumePrivacyNotice />
        <form className="inline-form resume-upload-form">
          <div className="resume-file-picker">
            <button type="button" className="secondary-button action-with-icon resume-file-button" disabled>
              <Upload size={17} aria-hidden="true" /> Upload File
            </button>
            <span className="metadata resume-file-name">No file selected</span>
          </div>
          <button type="button" disabled>
            Analyze Resume
          </button>
        </form>
      </section>
      <section className="manual-resume-option">
        <div>
          <h2>Prefer manual entry?</h2>
          <p className="metadata">Create a resume profile manually if you cannot upload a PDF or prefer to enter each section yourself.</p>
        </div>
        <button type="button" className="secondary-button" disabled>
          Create Resume Profile
        </button>
      </section>
      <section className="profile-workspace">
        <section className="profile-card resume-profiles-list-card">
          <div className="profile-card-header">
            <div>
              <h2>Your Resumes</h2>
              <p className="metadata">Select a resume to preview its structured profile. Your default resume appears first.</p>
            </div>
          </div>
          <div className="resume-profile-list">
            <article className="resume-profile-card selected">
              <IconButton className="resume-profile-delete" type="button" variant="danger" icon={Trash2} label="Delete resume" disabled />
              <button type="button" className="resume-profile-open" disabled>
                <span className="resume-profile-title">
                  Software Engineering Resume
                  <span className="default-label">Default</span>
                </span>
                <span className="resume-profile-preview">{profilePreview(previewData)}</span>
              </button>
              <div className="resume-profile-actions">
                <button type="button" className="secondary-button default-button" disabled>
                  Default
                </button>
              </div>
            </article>
          </div>
        </section>
        <div className="profile-detail-pane">
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
        </div>
      </section>
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
  onDelete,
  isDeleting,
}: {
  profile: ResumeProfile;
  isSelected: boolean;
  onOpen: () => void;
  onSetDefault: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}) {
  const data = normalizeResumeData(profile.resume_data);
  const skillPreview = data.skills.slice(0, 5);

  return (
    <article className={`resume-profile-card${isSelected ? " selected" : ""}`}>
      <IconButton
        className="resume-profile-delete"
        type="button"
        variant="danger"
        icon={Trash2}
        label={`Delete ${profile.title}`}
        disabled={isDeleting}
        onClick={onDelete}
      />
      <button type="button" className="resume-profile-open" onClick={onOpen}>
        <span className="resume-profile-title">
          {profile.title}
          {profile.is_default ? <span className="default-label">Default</span> : null}
        </span>
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
      <div className="resume-profile-actions">
        <button
          type="button"
          className="secondary-button default-button"
          onClick={onSetDefault}
          disabled={profile.is_default || isDeleting}
          aria-label={profile.is_default ? "Default resume" : "Set default resume"}
        >
          {profile.is_default ? "Default" : "Set default"}
        </button>
      </div>
    </article>
  );
}

function ResumePrivacyNotice() {
  return (
    <AlertBanner tone="info">
      <strong>Privacy.</strong> DaliJob removes detected names, email addresses, phone numbers,
      residential locations, and personal links prior to AI analysis.
    </AlertBanner>
  );
}

function ResumeImportReview({
  result,
  isApplying,
  isRetrying,
  onApply,
  onRetry,
  onDiscard,
}: {
  result: ResumeImportResponse;
  isApplying: boolean;
  isRetrying: boolean;
  onApply: () => Promise<void>;
  onRetry: () => Promise<void>;
  onDiscard: () => void;
}) {
  const suggestions = result.suggestions;

  return (
    <section className="resume-review">
      <div className="profile-card-header">
        <div>
          <h2>Resume Analysis</h2>
          <p className="metadata">{result.file_name}</p>
        </div>
        <div className="button-row">
          {result.parse_warning ? (
            <button type="button" className="secondary-button" disabled={isRetrying} onClick={() => void onRetry()}>
              {isRetrying ? "Retrying..." : "Retry Analysis"}
            </button>
          ) : null}
          <button type="button" className="secondary-button" onClick={onDiscard}>
            Discard
          </button>
          <button type="button" disabled={isApplying} onClick={() => void onApply()}>
            {isApplying ? "Saving..." : result.parse_warning ? "Create Manual Profile" : "Save Resume Profile"}
          </button>
        </div>
      </div>

      {result.parse_warning ? <AlertBanner tone="warning">{result.parse_warning}</AlertBanner> : null}

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
