import { getApiBaseUrl } from "./config";

export type SupportedRequirement = {
  requirement: string;
  resume_evidence: string;
  confidence: number;
};

export type UnsupportedRequirement = {
  requirement: string;
  reason: string;
};

export type ResumeJobMatchResponse = {
  id: string | null;
  match_score: number;
  score_scale: "0-10";
  summary: string;
  matched_skills: string[];
  missing_skills: string[];
  matched_keywords: string[];
  missing_keywords: string[];
  supported_requirements: SupportedRequirement[];
  unsupported_requirements: UnsupportedRequirement[];
  recommended_resume_updates: string[];
};

export type ResumeData = {
  name: string | null;
  headline: string | null;
  summary: string | null;
  contact: Record<string, string | null>;
  experience: string[];
  skills: string[];
  education: string[];
  certifications: string[];
  projects: string[];
  awards: string[];
  publications: string[];
  links: string[];
  languages: string[];
  volunteer: string[];
  target_roles: string[];
  target_locations: string[];
  notes: string[];
};

export type Profile = {
  id: string;
  workspace_id: string;
  user_id: string;
  resume_data: ResumeData;
  created_at: string;
  updated_at: string;
};

export type ResumeImportResponse = {
  file_name: string;
  extracted_text_preview: string;
  suggestions: ResumeData;
};

export const emptyResumeData: ResumeData = {
  name: null,
  headline: null,
  summary: null,
  contact: {},
  experience: [],
  skills: [],
  education: [],
  certifications: [],
  projects: [],
  awards: [],
  publications: [],
  links: [],
  languages: [],
  volunteer: [],
  target_roles: [],
  target_locations: [],
  notes: [],
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export async function compareResumeToJob(
  resumeText: string,
  jobDescriptionText: string,
): Promise<ResumeJobMatchResponse> {
  return requestJson<ResumeJobMatchResponse>("/resume-job-matches", {
    method: "POST",
    body: JSON.stringify({
      resume_text: resumeText,
      job_description_text: jobDescriptionText,
    }),
  });
}

export function getProfile(): Promise<Profile> {
  return requestJson<Profile>("/profile");
}

export function updateProfile(resumeData: ResumeData): Promise<Profile> {
  return requestJson<Profile>("/profile", {
    method: "PATCH",
    body: JSON.stringify({ resume_data: resumeData }),
  });
}

export async function importResumePdf(file: File): Promise<ResumeImportResponse> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${getApiBaseUrl()}/profile/resume-imports`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    let message = `Resume import failed with status ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }
    throw new Error(message);
  }

  return response.json();
}

export function applyResumeProfileSuggestions(suggestions: ResumeData): Promise<Profile> {
  return requestJson<Profile>("/profile/resume-imports/apply", {
    method: "POST",
    body: JSON.stringify(suggestions),
  });
}
