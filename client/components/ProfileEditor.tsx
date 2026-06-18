"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  applyResumeProfileSuggestions,
  emptyResumeData,
  getProfile,
  importResumePdf,
  Profile,
  ResumeData,
  ResumeImportResponse,
  updateProfile,
} from "../lib/api";

type SectionKey =
  | "experience"
  | "skills"
  | "education"
  | "certifications"
  | "projects"
  | "awards"
  | "publications"
  | "links"
  | "languages"
  | "volunteer"
  | "target_roles"
  | "target_locations"
  | "notes";

const sectionLabels: Record<SectionKey, string> = {
  experience: "Experience",
  skills: "Skills",
  education: "Education",
  certifications: "Certifications",
  projects: "Projects",
  awards: "Awards",
  publications: "Publications",
  links: "Links",
  languages: "Languages",
  volunteer: "Volunteer",
  target_roles: "Target Roles",
  target_locations: "Target Locations",
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
  "links",
  "languages",
  "volunteer",
  "target_roles",
  "target_locations",
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

function normalizeResumeData(value: ResumeData): ResumeData {
  return {
    ...emptyResumeData,
    ...value,
    contact: value.contact ?? {},
  };
}

export function ProfileEditor() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [resumeData, setResumeData] = useState<ResumeData>(emptyResumeData);
  const [sectionText, setSectionText] = useState<Record<SectionKey, string>>(
    Object.fromEntries(editableSections.map((key) => [key, ""])) as Record<SectionKey, string>,
  );
  const [resumeImport, setResumeImport] = useState<ResumeImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isImportingResume, setIsImportingResume] = useState(false);
  const [isApplyingResume, setIsApplyingResume] = useState(false);

  function setEditorData(data: ResumeData) {
    const normalized = normalizeResumeData(data);
    setResumeData(normalized);
    setSectionText(
      Object.fromEntries(
        editableSections.map((key) => [key, listToText(normalized[key])]),
      ) as Record<SectionKey, string>,
    );
  }

  async function loadProfile() {
    setError(null);
    setIsLoading(true);
    try {
      const profilePayload = await getProfile();
      setProfile(profilePayload);
      setEditorData(profilePayload.resume_data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Profile load failed.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadProfile();
  }, []);

  function buildResumeDataFromEditor(): ResumeData {
    const next: ResumeData = {
      ...resumeData,
      contact: {
        email: resumeData.contact.email ?? null,
        phone: resumeData.contact.phone ?? null,
        location: resumeData.contact.location ?? null,
        website: resumeData.contact.website ?? null,
        linkedin: resumeData.contact.linkedin ?? null,
        github: resumeData.contact.github ?? null,
      },
    };
    for (const key of editableSections) {
      next[key] = textToList(sectionText[key]);
    }
    return next;
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    try {
      const saved = await updateProfile(buildResumeDataFromEditor());
      setProfile(saved);
      setEditorData(saved.resume_data);
      setStatus("Resume JSON saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Profile save failed.");
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
      setStatus("Resume parsed. Review the JSON suggestions before applying them.");
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
      const saved = await applyResumeProfileSuggestions(resumeImport.suggestions);
      setProfile(saved);
      setEditorData(saved.resume_data);
      setResumeImport(null);
      setStatus("Resume suggestions applied to resume JSON.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Applying resume suggestions failed.");
    } finally {
      setIsApplyingResume(false);
    }
  }

  function updateContact(key: string, value: string) {
    setResumeData((current) => ({
      ...current,
      contact: {
        ...current.contact,
        [key]: value || null,
      },
    }));
  }

  if (isLoading) {
    return <p className="empty">Loading profile.</p>;
  }

  return (
    <div className="profile-editor">
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="profile-card">
        <div>
          <h2>Import Master Resume</h2>
          <p className="metadata">
            Upload a PDF resume to extract cleaned text and generate one structured resume JSON
            document for review.
          </p>
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

      <form className="profile-card" onSubmit={saveProfile}>
        <div className="profile-card-header">
          <h2>Resume JSON Profile</h2>
          <button type="submit">Save JSON</button>
        </div>

        <div className="profile-grid">
          <label>
            Name
            <input
              value={resumeData.name ?? ""}
              onChange={(event) => setResumeData({ ...resumeData, name: event.target.value || null })}
            />
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
          <label>
            Email
            <input
              value={resumeData.contact.email ?? ""}
              onChange={(event) => updateContact("email", event.target.value)}
            />
          </label>
          <label>
            Phone
            <input
              value={resumeData.contact.phone ?? ""}
              onChange={(event) => updateContact("phone", event.target.value)}
            />
          </label>
          <label>
            Location
            <input
              value={resumeData.contact.location ?? ""}
              onChange={(event) => updateContact("location", event.target.value)}
            />
          </label>
          <label>
            Website
            <input
              value={resumeData.contact.website ?? ""}
              onChange={(event) => updateContact("website", event.target.value)}
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

        {profile ? <p className="metadata">Profile ID: {profile.id}</p> : null}
      </form>
    </div>
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
