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

export async function compareResumeToJob(
  resumeText: string,
  jobDescriptionText: string,
): Promise<ResumeJobMatchResponse> {
  const response = await fetch(`${getApiBaseUrl()}/resume-job-matches`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      resume_text: resumeText,
      job_description_text: jobDescriptionText,
    }),
  });

  if (!response.ok) {
    let message = `Comparison failed with status ${response.status}`;
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
