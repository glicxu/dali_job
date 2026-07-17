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

export type BulkSavedJobMatchRequest = {
  user_job_ids: number[];
  resume_text?: string;
  resume_profile_id?: number;
  resume_document_id?: number;
};

export type BulkSavedJobMatchItem = {
  user_job_id: number;
  jobs_cache_id: number | null;
  title: string;
  company: string;
  saved_match_id: number;
  match: ResumeJobMatchResponse;
};

export type BulkSavedJobMatchFailure = {
  user_job_id: number;
  reason: string;
};

export type BulkSavedJobMatchResponse = {
  matched: BulkSavedJobMatchItem[];
  failed: BulkSavedJobMatchFailure[];
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
  user_edited_job_id: number | null;
  title: string;
  company: string;
  source_url: string | null;
  raw_description_text: string;
  job_data: JobDescriptionData | null;
  notes: string | null;
  match_score: number | null;
  matched_resume_profile_id: number | null;
  matched_resume_document_id: number | null;
  matched_resume_source: string | null;
  match_data: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type ManagedOperationStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type ManagedOperation = {
  id: number;
  operation_type: string;
  status: ManagedOperationStatus;
  progress_current: number;
  progress_total: number | null;
  progress_message: string | null;
  attempt_count: number;
  max_attempts: number;
  result_payload: Record<string, unknown> | unknown[] | null;
  error_code: string | null;
  error_message: string | null;
  provider: string | null;
  model_or_actor: string | null;
  prompt_version: string | null;
  usage: Record<string, unknown>;
  cancel_requested_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ManagedOperationSummary = {
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  cancelled: number;
  provider_failures: Record<string, number>;
};

export type JobDraftResponse = {
  source_url: string | null;
  raw_description_text: string;
  job_data: JobDescriptionData;
  fields_missing: string[];
};

export type JobListCandidate = {
  title: string;
  company: string;
  source_url: string;
  status: "new" | "already_cached" | "duplicate" | "unsupported" | "failed";
  jobs_cache_id: number | null;
};

export type JobListDiscoverResponse = {
  list_url: string;
  candidates: JobListCandidate[];
  next_page_url: string | null;
  next_page_confidence: number;
  warnings: string[];
};

export type JobListImportItem = {
  user_job_id: number;
  jobs_cache_id: number | null;
  source_url: string;
  title: string;
  company: string;
  match_score: number | null;
  match_id: number | null;
};

export type JobListImportFailure = {
  source_url: string;
  reason: string;
};

export type JobListImportResponse = {
  imported: JobListImportItem[];
  failed: JobListImportFailure[];
};

export type IndeedJobSearchResult = {
  external_id: string;
  title: string;
  company: string;
  location: string;
  source_url: string | null;
  summary: string;
  raw_description_text: string;
  salary_range: string;
  employment_type: string;
  posted_at: string;
  status: "new" | "already_cached";
  jobs_cache_id: number | null;
};

export type IndeedJobSearchResponse = {
  provider: "apify_indeed";
  keyword: string;
  location: string;
  results: IndeedJobSearchResult[];
  warnings: string[];
};

export type JobSavePayload = {
  title: string;
  company: string;
  source_url?: string | null;
  raw_description_text: string;
  job_data: JobDescriptionData;
  notes?: string | null;
  save_as_user_edit?: boolean;
};

export type JobUpdatePayload = Partial<JobSavePayload> & {
  notes?: string | null;
};

export type JobBulkDeleteResponse = {
  deleted_job_ids: number[];
  missing_job_ids: number[];
  blocked_jobs: RecordDependency[];
};

export type RecordDependency = {
  record_id?: number;
  dependency_type: string;
  dependency_count: number;
  message: string;
};

export type RecordDependencyResponse = {
  can_delete?: boolean;
  can_delete_without_warning?: boolean;
  dependencies: RecordDependency[];
};

export type JobResumeMatchHistory = {
  id: number;
  user_job_id: number;
  resume_profile_id: number | null;
  resume_document_id: number | null;
  resume_source: string;
  match_score: number;
  match_data: Record<string, unknown>;
  resume_data_snapshot: Record<string, unknown>;
  job_data_snapshot: Record<string, unknown>;
  provider: string;
  model_name: string | null;
  prompt_version: string;
  schema_version: string;
  provider_execution_reference: string | null;
  resume_is_stale: boolean;
  job_is_stale: boolean;
  is_stale: boolean;
  created_at: string;
};

export type PendingMatchedJob = JobSavePayload & {
  match_score: number;
  matched_resume_profile_id: number | null;
  matched_resume_document_id: number | null;
  matched_resume_source: string;
  match_data?: Record<string, unknown>;
  resume_data_snapshot?: Record<string, unknown>;
  job_data_snapshot?: Record<string, unknown>;
  model_name?: string | null;
  provider_execution_reference?: string | null;
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
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type ResumeProfileListResponse = {
  resume_profiles: ResumeProfile[];
};

export type ResumeProfileCreatePayload = {
  title: string;
  resume_data: ResumeData;
  source_document_id?: number | null;
  source_document_version_id?: number | null;
  is_default?: boolean;
};

export type ResumeProfileUpdatePayload = {
  title?: string;
  resume_data?: ResumeData;
  is_default?: boolean;
};

export type ResumeImportResponse = {
  file_name: string;
  document_id: number;
  document_version_id: number;
  extracted_text_preview: string;
  suggestions: ResumeData;
  parse_warning?: string | null;
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
  versions: DocumentVersion[];
};

export type EvidenceBackedText = { text: string; source_evidence: string };

export type TailoredResumeContent = {
  headline: EvidenceBackedText | null;
  summary: EvidenceBackedText[];
  skills: EvidenceBackedText[];
  experience: EvidenceBackedText[];
  education: EvidenceBackedText[];
  certifications: EvidenceBackedText[];
  projects: EvidenceBackedText[];
  unsupported_requirements: string[];
  tailoring_notes: string[];
};

export type CoverLetterContent = {
  salutation: string;
  paragraphs: { text: string; resume_evidence: string[]; job_evidence: string[] }[];
  closing: string;
  warnings: string[];
};

export type ApplicationMaterialVersion = {
  id: number; material_id: number; version_number: number; parent_version_id: number | null;
  operation_id: number | null; source_document_version_id: number | null; source_material_version_id: number | null;
  source_document_title: string; source_document_file_name: string; source_document_version_number: number;
  source_document_sha256: string; content_data: TailoredResumeContent | CoverLetterContent | null;
  version_source: "ai" | "user"; warnings: string[]; provider: string; model_name: string | null;
  prompt_version: string; schema_version: string; provider_execution_reference: string | null;
  created_at: string; completed_at: string | null;
};

export type ApplicationMaterial = {
  id: number; application_id: number; material_type: "tailored_resume" | "cover_letter";
  application_label: string; created_at: string; updated_at: string; versions: ApplicationMaterialVersion[];
};

export type DocumentListResponse = {
  documents: StoredDocument[];
};

export type DocumentTextResponse = {
  document_id: number;
  version_id: number;
  extracted_text: string;
};

export type DashboardAlert = {
  kind: string;
  message: string;
  href: string;
};

export type DashboardNextStep = {
  kind: string;
  label: string;
  href: string;
  reason: string;
};

export type DashboardBestMatch = {
  user_saved_job_id: number;
  job_cache_id: number | null;
  title: string;
  company: string;
  match_score: number;
  resume_profile_id: number | null;
  resume_label: string;
  match_summary: string;
  href: string;
};

export type DashboardRecentJob = {
  user_saved_job_id: number;
  job_cache_id: number | null;
  title: string;
  company: string;
  source_url: string | null;
  status: "needs_analysis" | "ready_to_match" | "matched" | string;
  created_at: string;
  href: string;
};

export type DashboardApplicationAction = {
  task_id: number;
  application_id: number;
  title: string;
  task_type: ApplicationTaskType;
  due_at: string | null;
  reminder_at: string | null;
  is_overdue: boolean;
  reminder_due: boolean;
  job_title: string;
  company: string;
  href: string;
};

export type DashboardResponse = {
  setup_alerts: DashboardAlert[];
  recommended_next_step: DashboardNextStep;
  best_matches: DashboardBestMatch[];
  recently_saved_jobs: DashboardRecentJob[];
  application_actions: DashboardApplicationAction[];
};

export type ApplicationStatus =
  | "interested"
  | "applied"
  | "interviewing"
  | "offer"
  | "accepted"
  | "rejected"
  | "withdrawn";

export type ApplicationStage =
  | "recruiter_contact"
  | "assessment"
  | "phone_screen"
  | "technical_interview"
  | "final_interview";

export type ApplicationPriority = "low" | "normal" | "high";
export type ApplicationTaskType = "follow_up" | "interview_prep" | "document" | "deadline" | "other";
export type ApplicationDocumentPurpose = "resume" | "cover_letter" | "supporting";

export type ApplicationJobSummary = {
  id: number | null;
  title: string;
  company: string;
  source_url: string | null;
  summary: string;
  work_location: string;
  application_deadline: string;
};

export type TrackedApplication = {
  id: number;
  workspace_id: number;
  user_id: number;
  user_job_id: number | null;
  status: ApplicationStatus;
  stage: ApplicationStage | null;
  priority: ApplicationPriority;
  match_score: number | null;
  salary_notes: string | null;
  applied_at: string | null;
  next_action_at: string | null;
  next_action_label: string | null;
  notes: string | null;
  job: ApplicationJobSummary | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  allowed_status_transitions: ApplicationStatus[];
};

export type ApplicationStatusHistory = {
  id: number;
  application_id: number;
  from_status: string | null;
  to_status: string;
  source: string;
  reason: string | null;
  created_at: string;
};

export type ApplicationEvent = {
  id: number;
  application_id: number;
  event_type: string;
  source: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type ApplicationNote = {
  id: number;
  application_id: number;
  body: string;
  created_at: string;
};

export type ApplicationTask = {
  id: number;
  application_id: number;
  title: string;
  task_type: ApplicationTaskType;
  due_at: string | null;
  reminder_at: string | null;
  reminder_dismissed_at: string | null;
  completed_at: string | null;
  is_overdue: boolean;
  reminder_due: boolean;
  created_at: string;
  updated_at: string;
};

export type ApplicationDocument = {
  id: number;
  application_id: number;
  document_id: number;
  document_version_id: number;
  purpose: ApplicationDocumentPurpose;
  document_title: string;
  document_type: string;
  version_number: number;
  file_name: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
};

export type ApplicationDetail = TrackedApplication & {
  status_history: ApplicationStatusHistory[];
  events: ApplicationEvent[];
  notes_list: ApplicationNote[];
  tasks: ApplicationTask[];
  documents: ApplicationDocument[];
};

export type InterviewType =
  | "recruiter_screen"
  | "phone"
  | "technical"
  | "behavioral"
  | "hiring_manager"
  | "panel"
  | "final"
  | "other";
export type InterviewStatus = "scheduled" | "completed" | "cancelled";
export type InterviewStage = ApplicationStage | "other";
export type InterviewOutcome = "advanced" | "rejected" | "offer" | "withdrawn" | "no_decision";

export type InterviewNote = {
  id: number;
  interview_id: number;
  body: string;
  created_at: string;
};

export type InterviewPrepOutput = {
  overview: string;
  study_priorities: { topic: string; reason: string; source_evidence: string[] }[];
  likely_questions: { question: string; rationale: string; preparation_points: string[] }[];
  talking_points: { topic: string; supported_claim: string; resume_evidence: string }[];
  skill_gaps: { skill: string; gap_evidence: string; study_action: string }[];
  questions_to_research: string[];
  warnings: string[];
};

export type InterviewPrepGuide = {
  id: number;
  interview_id: number;
  operation_id: number | null;
  resume_profile_id: number | null;
  source_warnings: string[];
  output_data: InterviewPrepOutput | null;
  provider: string;
  model_name: string | null;
  prompt_version: string;
  schema_version: string;
  provider_execution_reference: string | null;
  created_at: string;
  completed_at: string | null;
};

export type Interview = {
  id: number;
  workspace_id: number;
  user_id: number;
  application_id: number;
  interview_type: InterviewType;
  status: InterviewStatus;
  stage: InterviewStage;
  scheduled_at: string | null;
  timezone: string;
  duration_minutes: number | null;
  location_or_url: string | null;
  outcome: InterviewOutcome | null;
  private_notes: string | null;
  job: ApplicationJobSummary | null;
  created_at: string;
  updated_at: string;
};

export type InterviewDetail = Interview & {
  notes: InterviewNote[];
  prep_guides: InterviewPrepGuide[];
};

export type AnalyticsRate = {
  outcome: string;
  numerator: number;
  denominator: number;
  percentage: number | null;
};

export type AnalyticsPerformanceGroup = {
  key: string;
  label: string;
  sample_size: number;
  response_rate: number | null;
  interview_rate: number | null;
  offer_rate: number | null;
  rejection_rate: number | null;
  withdrawal_rate: number | null;
  small_sample: boolean;
};

export type AnalyticsSummary = {
  metric_version: string;
  timezone: string;
  range_start: string | null;
  range_end_exclusive: string | null;
  generated_at: string;
  application_count: number;
  submitted_application_count: number;
  status_counts: { status: string; count: number }[];
  application_trend: { period: string; count: number }[];
  rates: AnalyticsRate[];
  durations: {
    metric: string;
    sample_size: number;
    average_hours: number | null;
    median_hours: number | null;
  }[];
  source_performance: AnalyticsPerformanceGroup[];
  resume_version_performance: AnalyticsPerformanceGroup[];
  definitions: { metric: string; definition: string; denominator: string }[];
  data_quality: {
    missing_applied_at: number;
    missing_source_snapshot: number;
    missing_resume_version: number;
    resume_attached_after_applied: number;
    events_before_applied: number;
    warnings: string[];
  };
};

export type InterviewCreatePayload = {
  application_id: number;
  interview_type?: InterviewType;
  stage?: InterviewStage;
  scheduled_at?: string | null;
  timezone?: string | null;
  duration_minutes?: number | null;
  location_or_url?: string | null;
  private_notes?: string | null;
};

export type InterviewUpdatePayload = Partial<Omit<InterviewCreatePayload, "application_id">> & {
  status?: InterviewStatus;
  outcome?: InterviewOutcome | null;
};

export type ApplicationCreatePayload = {
  user_job_id: number;
  status?: ApplicationStatus;
  stage?: ApplicationStage | null;
  priority?: ApplicationPriority;
  match_score?: number | null;
  salary_notes?: string | null;
  applied_at?: string | null;
  next_action_at?: string | null;
  next_action_label?: string | null;
  notes?: string | null;
  confirm_duplicate?: boolean;
};

export type ApplicationUpdatePayload = {
  stage?: ApplicationStage | null;
  priority?: ApplicationPriority;
  match_score?: number | null;
  salary_notes?: string | null;
  applied_at?: string | null;
  next_action_at?: string | null;
  next_action_label?: string | null;
  notes?: string | null;
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

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
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
    let detail: unknown = null;
    try {
      const payload = await response.json();
      detail = payload.detail;
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail && typeof payload.detail.message === "string") {
        message = payload.detail.message;
      }
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }
    throw new ApiRequestError(message, response.status, detail);
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

export function getDashboard(): Promise<DashboardResponse> {
  return requestJson<DashboardResponse>("/dashboard");
}

export function listApplications(options: {
  status?: ApplicationStatus;
  stage?: ApplicationStage;
  includeArchived?: boolean;
} = {}): Promise<TrackedApplication[]> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.stage) params.set("stage", options.stage);
  if (options.includeArchived) params.set("include_archived", "true");
  const query = params.size ? `?${params.toString()}` : "";
  return requestJson<TrackedApplication[]>(`/applications${query}`);
}

export function createApplication(payload: ApplicationCreatePayload): Promise<ApplicationDetail> {
  return requestJson<ApplicationDetail>("/applications", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getApplication(applicationId: number): Promise<ApplicationDetail> {
  return requestJson<ApplicationDetail>(`/applications/${applicationId}`);
}

export function updateApplication(
  applicationId: number,
  payload: ApplicationUpdatePayload,
): Promise<ApplicationDetail> {
  return requestJson<ApplicationDetail>(`/applications/${applicationId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function changeApplicationStatus(
  applicationId: number,
  status: ApplicationStatus,
  reason?: string,
): Promise<ApplicationDetail> {
  return requestJson<ApplicationDetail>(`/applications/${applicationId}/status`, {
    method: "POST",
    body: JSON.stringify({ status, reason: reason || undefined }),
  });
}

export function addApplicationNote(applicationId: number, body: string): Promise<ApplicationNote> {
  return requestJson<ApplicationNote>(`/applications/${applicationId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function addApplicationTask(
  applicationId: number,
  title: string,
  options?: { taskType?: ApplicationTaskType; dueAt?: string | null; reminderAt?: string | null },
): Promise<ApplicationTask> {
  return requestJson<ApplicationTask>(`/applications/${applicationId}/tasks`, {
    method: "POST",
    body: JSON.stringify({
      title,
      task_type: options?.taskType ?? "other",
      due_at: options?.dueAt || null,
      reminder_at: options?.reminderAt || null,
    }),
  });
}

export function listInterviews(applicationId?: number): Promise<Interview[]> {
  const query = applicationId ? `?application_id=${applicationId}` : "";
  return requestJson<Interview[]>(`/interviews${query}`);
}

export function getAnalyticsSummary(options: {
  startDate?: string;
  endDate?: string;
} = {}): Promise<AnalyticsSummary> {
  const params = new URLSearchParams();
  if (options.startDate) params.set("start_date", options.startDate);
  if (options.endDate) params.set("end_date", options.endDate);
  const query = params.size ? `?${params.toString()}` : "";
  return requestJson<AnalyticsSummary>(`/analytics/summary${query}`);
}

export function createInterview(payload: InterviewCreatePayload): Promise<InterviewDetail> {
  return requestJson<InterviewDetail>("/interviews", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getInterview(interviewId: number): Promise<InterviewDetail> {
  return requestJson<InterviewDetail>(`/interviews/${interviewId}`);
}

export function updateInterview(
  interviewId: number,
  payload: InterviewUpdatePayload,
): Promise<InterviewDetail> {
  return requestJson<InterviewDetail>(`/interviews/${interviewId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function addInterviewNote(interviewId: number, body: string): Promise<InterviewNote> {
  return requestJson<InterviewNote>(`/interviews/${interviewId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function generateInterviewPrep(payload: {
  interview_id: number;
  resume_profile_id: number;
  company_notes?: string;
}): Promise<InterviewPrepGuide> {
  return runManagedOperation<InterviewPrepGuide>(
    "interview_prep",
    "/operations/interview-prep",
    payload,
  );
}

const operationPollIntervalMs = 750;
const operationPollTimeoutMs = 15 * 60 * 1000;

function operationIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function activeOperationKey(operationType: string): string {
  return `dalijob_active_operation_${operationType}`;
}

function rememberActiveOperation(operationType: string, operationId: number, fingerprint: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(activeOperationKey(operationType), JSON.stringify({ operationId, fingerprint }));
}

function forgetActiveOperation(operationType: string, operationId: number): void {
  if (typeof window === "undefined") return;
  const key = activeOperationKey(operationType);
  try {
    const saved = JSON.parse(window.localStorage.getItem(key) || "null");
    if (saved?.operationId === operationId) window.localStorage.removeItem(key);
  } catch {
    window.localStorage.removeItem(key);
  }
}

function recalledOperationId(operationType: string, fingerprint: string): number | null {
  if (typeof window === "undefined") return null;
  try {
    const saved = JSON.parse(window.localStorage.getItem(activeOperationKey(operationType)) || "null");
    return saved?.fingerprint === fingerprint && Number.isInteger(saved?.operationId) ? saved.operationId : null;
  } catch {
    return null;
  }
}

export function getManagedOperation(operationId: number): Promise<ManagedOperation> {
  return requestJson<ManagedOperation>(`/operations/${operationId}`);
}

export function listManagedOperations(options?: {
  status?: ManagedOperationStatus;
  operationType?: string;
  limit?: number;
}): Promise<{ operations: ManagedOperation[] }> {
  const params = new URLSearchParams();
  if (options?.status) params.set("status", options.status);
  if (options?.operationType) params.set("operation_type", options.operationType);
  params.set("limit", String(options?.limit ?? 50));
  return requestJson<{ operations: ManagedOperation[] }>(`/operations?${params.toString()}`);
}

export function getManagedOperationSummary(): Promise<ManagedOperationSummary> {
  return requestJson<ManagedOperationSummary>("/operations/summary");
}

export function retryManagedOperation(operationId: number): Promise<ManagedOperation> {
  return requestJson<ManagedOperation>(`/operations/${operationId}/retry`, { method: "POST" });
}

export function cancelManagedOperation(operationId: number): Promise<ManagedOperation> {
  return requestJson<ManagedOperation>(`/operations/${operationId}/cancel`, { method: "POST" });
}

async function waitForManagedOperation<T>(operation: ManagedOperation): Promise<T> {
  const started = Date.now();
  let current = operation;
  while (current.status === "queued" || current.status === "running") {
    if (Date.now() - started > operationPollTimeoutMs) {
      throw new Error("This operation is still running. Its progress is available on the Operations page.");
    }
    await new Promise((resolve) => setTimeout(resolve, operationPollIntervalMs));
    current = await getManagedOperation(operation.id);
  }
  forgetActiveOperation(operation.operation_type, operation.id);
  if (current.status !== "succeeded") {
    throw new Error(current.error_message || "The operation did not complete successfully.");
  }
  if (current.result_payload === null) {
    throw new Error("The operation completed without a result.");
  }
  return current.result_payload as T;
}

async function runManagedOperation<T>(
  operationType: string,
  path: string,
  payload: object,
): Promise<T> {
  const fingerprint = JSON.stringify(payload);
  const recalledId = recalledOperationId(operationType, fingerprint);
  if (recalledId !== null) {
    let recalled: ManagedOperation | null = null;
    try {
      recalled = await getManagedOperation(recalledId);
    } catch (err) {
      if (!(err instanceof ApiRequestError && err.status === 404)) throw err;
      forgetActiveOperation(operationType, recalledId);
    }
    if (recalled) {
      return waitForManagedOperation<T>(recalled);
    }
  }

  const operation = await requestJson<ManagedOperation>(path, {
    method: "POST",
    headers: { "Idempotency-Key": operationIdempotencyKey() },
    body: JSON.stringify(payload),
  });
  rememberActiveOperation(operationType, operation.id, fingerprint);
  return waitForManagedOperation<T>(operation);
}

export function listApplicationTasks(
  applicationId: number,
  options: { taskType?: ApplicationTaskType; status?: "open" | "completed" } = {},
): Promise<ApplicationTask[]> {
  const params = new URLSearchParams();
  if (options.taskType) params.set("task_type", options.taskType);
  if (options.status) params.set("status", options.status);
  const query = params.size ? `?${params.toString()}` : "";
  return requestJson<ApplicationTask[]>(`/applications/${applicationId}/tasks${query}`);
}

export function updateApplicationTask(
  applicationId: number,
  taskId: number,
  payload: {
    title?: string;
    task_type?: ApplicationTaskType;
    due_at?: string | null;
    reminder_at?: string | null;
    dismiss_reminder?: boolean;
    completed?: boolean;
  },
): Promise<ApplicationTask> {
  return requestJson<ApplicationTask>(`/applications/${applicationId}/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listDocuments(): Promise<DocumentListResponse> {
  return requestJson<DocumentListResponse>("/documents");
}

export function listApplicationMaterials(applicationId?: number): Promise<{ materials: ApplicationMaterial[] }> {
  const query = applicationId ? `?application_id=${applicationId}` : "";
  return requestJson<{ materials: ApplicationMaterial[] }>(`/application-materials${query}`);
}

export function generateTailoredResume(payload: {
  application_id: number; source_document_version_id: number; target_notes?: string;
}): Promise<ApplicationMaterial> {
  return runManagedOperation<ApplicationMaterial>("tailored_resume", "/operations/tailored-resume", payload);
}

export function generateCoverLetter(payload: {
  application_id: number; source_document_version_id: number; source_material_version_id?: number; target_notes?: string;
}): Promise<ApplicationMaterial> {
  return runManagedOperation<ApplicationMaterial>("cover_letter", "/operations/cover-letter", payload);
}

export function reviseApplicationMaterial(
  materialId: number,
  parentVersionId: number,
  contentData: Record<string, unknown>,
): Promise<ApplicationMaterial> {
  return requestJson<ApplicationMaterial>(`/application-materials/${materialId}/versions`, {
    method: "POST",
    body: JSON.stringify({ parent_version_id: parentVersionId, content_data: contentData }),
  });
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

export async function uploadDocumentVersion(documentId: number, file: File): Promise<StoredDocument> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${getApiBaseUrl()}/documents/${documentId}/versions`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });
  if (!response.ok) {
    let message = `Document version upload failed with status ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
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

export function archiveApplication(applicationId: number): Promise<ApplicationDetail> {
  return requestJson<ApplicationDetail>(`/applications/${applicationId}/archive`, { method: "POST" });
}

export function restoreApplication(
  applicationId: number,
  confirmDuplicate = false,
): Promise<ApplicationDetail> {
  return requestJson<ApplicationDetail>(`/applications/${applicationId}/restore`, {
    method: "POST",
    body: JSON.stringify({ confirm_duplicate: confirmDuplicate }),
  });
}

export function attachApplicationDocument(
  applicationId: number,
  documentVersionId: number,
  purpose: ApplicationDocumentPurpose,
): Promise<ApplicationDocument> {
  return requestJson<ApplicationDocument>(`/applications/${applicationId}/documents`, {
    method: "POST",
    body: JSON.stringify({ document_version_id: documentVersionId, purpose }),
  });
}

export function detachApplicationDocument(applicationId: number, attachmentId: number): Promise<void> {
  return requestJson<void>(`/applications/${applicationId}/documents/${attachmentId}`, { method: "DELETE" });
}

type DocumentDownloadTicket = { download_path: string; expires_at: string };

async function downloadTicketFile(ticket: DocumentDownloadTicket, fileName: string): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}${ticket.download_path}`);
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

export async function downloadApplicationDocument(
  applicationId: number,
  attachmentId: number,
  fileName: string,
): Promise<void> {
  const ticket = await requestJson<DocumentDownloadTicket>(
    `/applications/${applicationId}/documents/${attachmentId}/download-ticket`,
    { method: "POST" },
  );
  await downloadTicketFile(ticket, fileName);
}

export function getDocumentDependencies(documentId: number): Promise<RecordDependencyResponse> {
  return requestJson<RecordDependencyResponse>(`/documents/${documentId}/dependencies`);
}

export function deleteDocument(documentId: number, force = false): Promise<void> {
  return requestJson<void>(`/documents/${documentId}?force=${force}`, { method: "DELETE" });
}

export async function downloadDocumentFile(documentId: number, fileName: string): Promise<void> {
  const ticket = await requestJson<DocumentDownloadTicket>(`/documents/${documentId}/download-ticket`, {
    method: "POST",
  });
  await downloadTicketFile(ticket, fileName);
}

export async function compareResumeToJob(payload: ResumeJobMatchRequest): Promise<ResumeJobMatchResponse> {
  return runManagedOperation<ResumeJobMatchResponse>("resume_job_match", "/operations/resume-job-match", payload);
}

export async function compareResumeToSavedJobs(
  payload: BulkSavedJobMatchRequest,
): Promise<BulkSavedJobMatchResponse> {
  return runManagedOperation<BulkSavedJobMatchResponse>(
    "bulk_resume_job_match",
    "/operations/bulk-resume-job-match",
    payload,
  );
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

export function listJobs(includeArchived = false): Promise<StoredJob[]> {
  return requestJson<StoredJob[]>(`/jobs?include_archived=${includeArchived}`);
}

export function draftJobFromUrl(jobUrl: string): Promise<JobDraftResponse> {
  return runManagedOperation<JobDraftResponse>("job_draft", "/operations/job-draft", { job_url: jobUrl });
}

export function draftJobFromText(jobDescriptionText: string): Promise<JobDraftResponse> {
  return runManagedOperation<JobDraftResponse>("job_draft", "/operations/job-draft", {
    job_description_text: jobDescriptionText,
  });
}

export function discoverJobList(listUrl: string, maxResults = 25): Promise<JobListDiscoverResponse> {
  return runManagedOperation<JobListDiscoverResponse>("job_list_discover", "/operations/job-list-discover", {
    list_url: listUrl,
    max_results: maxResults,
  });
}

export function importJobList(
  selectedUrls: string[],
  options?: { listUrl?: string; resumeProfileId?: number; runMatching?: boolean },
): Promise<JobListImportResponse> {
  return runManagedOperation<JobListImportResponse>("job_list_import", "/operations/job-list-import", {
      list_url: options?.listUrl || undefined,
      selected_urls: selectedUrls,
      resume_profile_id: options?.resumeProfileId || undefined,
      run_matching: Boolean(options?.runMatching),
  });
}

export function searchIndeedJobs(
  keyword: string,
  location: string,
  maxResults = 5,
): Promise<IndeedJobSearchResponse> {
  return runManagedOperation<IndeedJobSearchResponse>("job_search", "/operations/job-search", {
      keyword,
      location,
      max_results: maxResults,
  });
}

export function importIndeedSearchResults(
  selectedResults: IndeedJobSearchResult[],
  options?: { resumeProfileId?: number; runMatching?: boolean },
): Promise<JobListImportResponse> {
  return runManagedOperation<JobListImportResponse>("provider_job_import", "/operations/provider-job-import", {
      selected_results: selectedResults,
      resume_profile_id: options?.resumeProfileId || undefined,
      run_matching: Boolean(options?.runMatching),
  });
}

export function createJob(payload: JobSavePayload): Promise<StoredJob> {
  return requestJson<StoredJob>("/jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function analyzeJob(jobId: number): Promise<StoredJob> {
  return runManagedOperation<StoredJob>("job_analyze", "/operations/job-analyze", { job_id: jobId });
}

export function updateJob(jobId: number, payload: JobUpdatePayload): Promise<StoredJob> {
  return requestJson<StoredJob>(`/jobs/${jobId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteJob(jobId: number): Promise<void> {
  return requestJson<void>(`/jobs/${jobId}`, {
    method: "DELETE",
  });
}

export function archiveJob(jobId: number): Promise<void> {
  return requestJson<void>(`/jobs/${jobId}/archive`, { method: "POST" });
}

export function restoreJob(jobId: number): Promise<void> {
  return requestJson<void>(`/jobs/${jobId}/restore`, { method: "POST" });
}

export function getJobDependencies(jobId: number): Promise<RecordDependencyResponse> {
  return requestJson<RecordDependencyResponse>(`/jobs/${jobId}/dependencies`);
}

export function listJobMatches(jobId: number): Promise<{ matches: JobResumeMatchHistory[] }> {
  return requestJson<{ matches: JobResumeMatchHistory[] }>(`/jobs/${jobId}/matches`);
}

export function bulkDeleteJobs(jobIds: number[]): Promise<JobBulkDeleteResponse> {
  return requestJson<JobBulkDeleteResponse>("/jobs/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds }),
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

export function forceDeleteResumeProfile(resumeProfileId: number): Promise<void> {
  return requestJson<void>(`/resume-profiles/${resumeProfileId}?force=true`, {
    method: "DELETE",
  });
}

export function getResumeProfileDependencies(resumeProfileId: number): Promise<RecordDependencyResponse> {
  return requestJson<RecordDependencyResponse>(`/resume-profiles/${resumeProfileId}/dependencies`);
}

export async function importResumePdf(file: File): Promise<ResumeImportResponse> {
  const fingerprint = `${file.name}:${file.size}:${file.lastModified}`;
  const recalledId = recalledOperationId("resume_parse", fingerprint);
  if (recalledId !== null) {
    try {
      const recalled = await getManagedOperation(recalledId);
      return waitForManagedOperation<ResumeImportResponse>(recalled);
    } catch (err) {
      if (!(err instanceof ApiRequestError && err.status === 404)) throw err;
      forgetActiveOperation("resume_parse", recalledId);
    }
  }
  const form = new FormData();
  form.append("file", file);

  const operation = await fetch(`${getApiBaseUrl()}/operations/resume-parse`, {
    method: "POST",
    headers: { ...authHeaders(), "Idempotency-Key": operationIdempotencyKey() },
    body: form,
  });

  if (!operation.ok) {
    let message = `Resume import failed with status ${operation.status}`;
    try {
      const payload = await operation.json();
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }
    throw new Error(message);
  }
  const queued = (await operation.json()) as ManagedOperation;
  rememberActiveOperation("resume_parse", queued.id, fingerprint);
  return waitForManagedOperation<ResumeImportResponse>(queued);
}

export function retryResumeImport(documentId: number): Promise<ResumeImportResponse> {
  return runManagedOperation<ResumeImportResponse>("resume_parse", "/operations/resume-parse/retry", {
    document_id: documentId,
  });
}

export function applyResumeProfileSuggestions(importResult: ResumeImportResponse): Promise<ResumeProfile> {
  return requestJson<ResumeProfile>("/profile/resume-imports/apply", {
    method: "POST",
    body: JSON.stringify({
      resume_data: importResult.suggestions,
      source_document_id: importResult.document_id,
      source_document_version_id: importResult.document_version_id,
    }),
  });
}
