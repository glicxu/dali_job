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
  id: number | null;
  saved_job_id: number | null;
  saved_match_id: number | null;
  job_saved: boolean;
  pending_job: PendingMatchedJob | null;
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

export type ResumeJobMatchRequest = {
  resume_text?: string;
  resume_profile_id?: number;
  resume_document_id?: number;
  job_description_text?: string;
  job_url?: string;
};

export type JobUrlExtractResponse = {
  job_url: string;
  extracted_text: string;
  character_count: number;
};

export type JobDescriptionData = {
  title: string;
  company: string;
  summary: string;
  responsibilities: string[];
  required_skills: string[];
  preferred_skills: string[];
  required_experience: string[];
  preferred_experience: string[];
  education: string[];
  certifications: string[];
  tools_and_technologies: string[];
  keywords: string[];
  seniority_level: string;
  employment_type: string;
  security_clearance: string;
  work_location: string;
  salary_range: string;
  application_deadline: string;
};

export type StoredJob = {
  id: number;
  workspace_id: number;
  user_id: number;
  jobs_cache_id: number | null;
  title: string;
  company: string;
  source_url: string | null;
  raw_description_text: string;
  job_data: JobDescriptionData;
  notes: string | null;
  match_score: number | null;
  matched_resume_profile_id: number | null;
  matched_resume_document_id: number | null;
  matched_resume_source: string | null;
  created_at: string;
  updated_at: string;
};

export type JobDraftResponse = {
  source_url: string | null;
  raw_description_text: string;
  job_data: JobDescriptionData;
  fields_missing: string[];
};

export type JobSavePayload = {
  title: string;
  company: string;
  source_url?: string | null;
  raw_description_text: string;
  job_data: JobDescriptionData;
  notes?: string | null;
};

export type PendingMatchedJob = JobSavePayload & {
  match_score: number;
  matched_resume_profile_id: number | null;
  matched_resume_document_id: number | null;
  matched_resume_source: string;
};

export type SavePendingMatchedJobResponse = {
  saved_job_id: number;
  saved_match_id: number;
};

export type ResumeData = {
  headline: string | null;
  summary: string | null;
  experience: string[];
  skills: string[];
  education: string[];
  certifications: string[];
  projects: string[];
  awards: string[];
  publications: string[];
  languages: string[];
  volunteer: string[];
  target_roles: string[];
  notes: string[];
};

export type ResumeProfile = {
  id: number;
  workspace_id: number;
  user_id: number;
  title: string;
  resume_data: ResumeData;
  source_document_id: number | null;
  source_document_version_id: number | null;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
};

export type ResumeProfileListResponse = {
  resume_profiles: ResumeProfile[];
};

export type ResumeProfileCreatePayload = {
  title: string;
  resume_data: ResumeData;
  is_favorite?: boolean;
};

export type ResumeProfileUpdatePayload = {
  title?: string;
  resume_data?: ResumeData;
  is_favorite?: boolean;
};

export type ResumeImportResponse = {
  file_name: string;
  extracted_text_preview: string;
  suggestions: ResumeData;
};

export type CurrentUser = {
  auth_mode: string;
  external_user_id: string;
  email: string;
  display_name: string;
  provider: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: CurrentUser;
};

export type DocumentVersion = {
  id: number;
  document_id: number;
  version_number: number;
  file_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  extracted_text_available: boolean;
  created_at: string;
};

export type StoredDocument = {
  id: number;
  workspace_id: number;
  user_id: number;
  title: string;
  document_type: string;
  created_at: string;
  updated_at: string;
  latest_version: DocumentVersion | null;
};

export type DocumentListResponse = {
  documents: StoredDocument[];
};

export type DocumentTextResponse = {
  document_id: number;
  version_id: number;
  extracted_text: string;
};

export const emptyResumeData: ResumeData = {
  headline: null,
  summary: null,
  experience: [],
  skills: [],
  education: [],
  certifications: [],
  projects: [],
  awards: [],
  publications: [],
  languages: [],
  volunteer: [],
  target_roles: [],
  notes: [],
};

export const emptyJobDescriptionData: JobDescriptionData = {
  title: "",
  company: "",
  summary: "",
  responsibilities: [],
  required_skills: [],
  preferred_skills: [],
  required_experience: [],
  preferred_experience: [],
  education: [],
  certifications: [],
  tools_and_technologies: [],
  keywords: [],
  seniority_level: "",
  employment_type: "",
  security_clearance: "",
  work_location: "",
  salary_range: "",
  application_deadline: "",
};

const tokenStorageKey = "dalijob_access_token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(tokenStorageKey);
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(tokenStorageKey, token);
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(tokenStorageKey);
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
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

export async function registerUser(
  email: string,
  password: string,
  displayName: string,
): Promise<AuthResponse> {
  const payload = await requestJson<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      display_name: displayName,
    }),
  });
  setAuthToken(payload.access_token);
  return payload;
}

export async function loginUser(email: string, password: string): Promise<AuthResponse> {
  const payload = await requestJson<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setAuthToken(payload.access_token);
  return payload;
}

export function getCurrentUser(): Promise<CurrentUser> {
  return requestJson<CurrentUser>("/me");
}

export function listDocuments(): Promise<DocumentListResponse> {
  return requestJson<DocumentListResponse>("/documents");
}

export async function uploadDocument(
  file: File,
  title: string,
  documentType = "resume",
): Promise<StoredDocument> {
  const form = new FormData();
  form.append("file", file);
  if (title.trim()) {
    form.append("title", title.trim());
  }
  form.append("document_type", documentType);

  const response = await fetch(`${getApiBaseUrl()}/documents`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });

  if (!response.ok) {
    let message = `Document upload failed with status ${response.status}`;
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

export function getDocumentText(documentId: number): Promise<DocumentTextResponse> {
  return requestJson<DocumentTextResponse>(`/documents/${documentId}/text`);
}

export function getDocumentDownloadUrl(documentId: number): string {
  return `${getApiBaseUrl()}/documents/${documentId}/download`;
}

export async function downloadDocumentFile(documentId: number, fileName: string): Promise<void> {
  const response = await fetch(getDocumentDownloadUrl(documentId), {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`Document download failed with status ${response.status}`);
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function compareResumeToJob(payload: ResumeJobMatchRequest): Promise<ResumeJobMatchResponse> {
  return requestJson<ResumeJobMatchResponse>("/resume-job-matches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function extractJobUrl(jobUrl: string): Promise<JobUrlExtractResponse> {
  return requestJson<JobUrlExtractResponse>("/resume-job-matches/job-url-extract", {
    method: "POST",
    body: JSON.stringify({ job_url: jobUrl }),
  });
}

export function savePendingMatchedJob(payload: PendingMatchedJob): Promise<SavePendingMatchedJobResponse> {
  return requestJson<SavePendingMatchedJobResponse>("/resume-job-matches/pending-job", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listJobs(): Promise<StoredJob[]> {
  return requestJson<StoredJob[]>("/jobs");
}

export function draftJobFromUrl(jobUrl: string): Promise<JobDraftResponse> {
  return requestJson<JobDraftResponse>("/jobs/draft", {
    method: "POST",
    body: JSON.stringify({ job_url: jobUrl }),
  });
}

export function draftJobFromText(jobDescriptionText: string): Promise<JobDraftResponse> {
  return requestJson<JobDraftResponse>("/jobs/draft", {
    method: "POST",
    body: JSON.stringify({ job_description_text: jobDescriptionText }),
  });
}

export function createJob(payload: JobSavePayload): Promise<StoredJob> {
  return requestJson<StoredJob>("/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateJob(jobId: number, payload: JobSavePayload): Promise<StoredJob> {
  return requestJson<StoredJob>(`/jobs/${jobId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listResumeProfiles(): Promise<ResumeProfileListResponse> {
  return requestJson<ResumeProfileListResponse>("/resume-profiles");
}

export function createResumeProfile(payload: ResumeProfileCreatePayload): Promise<ResumeProfile> {
  return requestJson<ResumeProfile>("/resume-profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateResumeProfile(
  resumeProfileId: number,
  payload: ResumeProfileUpdatePayload,
): Promise<ResumeProfile> {
  return requestJson<ResumeProfile>(`/resume-profiles/${resumeProfileId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteResumeProfile(resumeProfileId: number): Promise<void> {
  return requestJson<void>(`/resume-profiles/${resumeProfileId}`, {
    method: "DELETE",
  });
}

export async function importResumePdf(file: File): Promise<ResumeImportResponse> {
  const form = new FormData();
  form.append("file", file);

  const response = await fetch(`${getApiBaseUrl()}/profile/resume-imports`, {
    method: "POST",
    headers: authHeaders(),
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

export function applyResumeProfileSuggestions(suggestions: ResumeData): Promise<ResumeProfile> {
  return requestJson<ResumeProfile>("/profile/resume-imports/apply", {
    method: "POST",
    body: JSON.stringify(suggestions),
  });
}
