"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  addInterviewNote,
  createInterview,
  generateInterviewPrep,
  getAuthToken,
  getInterview,
  Interview,
  InterviewDetail,
  InterviewOutcome,
  InterviewStage,
  InterviewStatus,
  InterviewType,
  listApplications,
  listInterviews,
  listResumeProfiles,
  ResumeProfile,
  TrackedApplication,
  updateInterview,
} from "../lib/api";

const interviewTypes: InterviewType[] = [
  "recruiter_screen", "phone", "technical", "behavioral", "hiring_manager", "panel", "final", "other",
];
const interviewStages: InterviewStage[] = [
  "recruiter_contact", "assessment", "phone_screen", "technical_interview", "final_interview", "other",
];
const interviewStatuses: InterviewStatus[] = ["scheduled", "completed", "cancelled"];
const interviewOutcomes: InterviewOutcome[] = ["advanced", "rejected", "offer", "withdrawn", "no_decision"];

function labelize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateTimeInputValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function jobLabel(application: TrackedApplication): string {
  return `${application.job?.title || "Untitled application"} - ${application.job?.company || "Unknown company"}`;
}

export function InterviewManager() {
  if (!getAuthToken()) return <InterviewPreview />;
  return <AuthenticatedInterviewManager />;
}

function AuthenticatedInterviewManager() {
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [applications, setApplications] = useState<TrackedApplication[]>([]);
  const [resumes, setResumes] = useState<ResumeProfile[]>([]);
  const [selected, setSelected] = useState<InterviewDetail | null>(null);
  const [applicationId, setApplicationId] = useState("");
  const [interviewType, setInterviewType] = useState<InterviewType>("other");
  const [stage, setStage] = useState<InterviewStage>("other");
  const [scheduledAt, setScheduledAt] = useState("");
  const [duration, setDuration] = useState("60");
  const [location, setLocation] = useState("");
  const [privateNotes, setPrivateNotes] = useState("");
  const [newNote, setNewNote] = useState("");
  const [prepResumeId, setPrepResumeId] = useState("");
  const [companyNotes, setCompanyNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const queryHandled = useRef(false);

  const activeApplications = useMemo(
    () => applications.filter((application) => !application.archived_at),
    [applications],
  );

  async function loadWorkspace() {
    setError(null);
    try {
      const [interviewPayload, applicationPayload, resumePayload] = await Promise.all([
        listInterviews(), listApplications(), listResumeProfiles(),
      ]);
      setInterviews(interviewPayload);
      setApplications(applicationPayload);
      setResumes(resumePayload.resume_profiles);
      if (!prepResumeId) {
        const defaultResume = resumePayload.resume_profiles.find((resume) => resume.is_default);
        if (defaultResume) setPrepResumeId(String(defaultResume.id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load interviews.");
    }
  }

  useEffect(() => { void loadWorkspace(); }, []);

  useEffect(() => {
    if (queryHandled.current || typeof window === "undefined" || !applications.length) return;
    queryHandled.current = true;
    const queryId = Number(new URLSearchParams(window.location.search).get("application_id"));
    if (Number.isInteger(queryId) && applications.some((application) => application.id === queryId)) {
      setApplicationId(String(queryId));
    }
  }, [applications]);

  async function openInterview(interviewId: number) {
    setError(null);
    try {
      setSelected(await getInterview(interviewId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open interview.");
    }
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!applicationId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createInterview({
        application_id: Number(applicationId),
        interview_type: interviewType,
        stage,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        duration_minutes: duration ? Number(duration) : null,
        location_or_url: location || null,
        private_notes: privateNotes || null,
      });
      setSelected(created);
      setMessage("Interview scheduled.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not schedule interview.");
    } finally {
      setBusy(false);
    }
  }

  async function saveInterview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const updated = await updateInterview(selected.id, {
        interview_type: data.get("interview_type") as InterviewType,
        status: data.get("status") as InterviewStatus,
        stage: data.get("stage") as InterviewStage,
        scheduled_at: data.get("scheduled_at") ? new Date(String(data.get("scheduled_at"))).toISOString() : null,
        duration_minutes: data.get("duration_minutes") ? Number(data.get("duration_minutes")) : null,
        location_or_url: String(data.get("location_or_url") || "") || null,
        outcome: (data.get("outcome") || null) as InterviewOutcome | null,
        private_notes: String(data.get("private_notes") || "") || null,
      });
      setSelected(updated);
      setMessage("Interview updated.");
      await loadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update interview.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddNote(event: FormEvent) {
    event.preventDefault();
    if (!selected || !newNote.trim()) return;
    setBusy(true);
    try {
      await addInterviewNote(selected.id, newNote);
      setNewNote("");
      setSelected(await getInterview(selected.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add note.");
    } finally {
      setBusy(false);
    }
  }

  async function handleGeneratePrep(event: FormEvent) {
    event.preventDefault();
    if (!selected || !prepResumeId) return;
    setBusy(true);
    setError(null);
    setMessage("Preparing interview guide.");
    try {
      await generateInterviewPrep({
        interview_id: selected.id,
        resume_profile_id: Number(prepResumeId),
        company_notes: companyNotes || undefined,
      });
      setSelected(await getInterview(selected.id));
      setMessage("Interview guide ready.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate interview preparation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="interviews-manager">
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      <form className="interview-create-form" onSubmit={handleCreate}>
        <div className="section-heading"><div><h2>Schedule Interview</h2><p className="metadata">Link the interview to an existing application.</p></div></div>
        <div className="form-grid">
          <label>Application<select value={applicationId} onChange={(event) => setApplicationId(event.target.value)} required><option value="">Select application</option>{activeApplications.map((application) => <option key={application.id} value={application.id}>{jobLabel(application)}</option>)}</select></label>
          <label>Type<select value={interviewType} onChange={(event) => setInterviewType(event.target.value as InterviewType)}>{interviewTypes.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select></label>
          <label>Stage<select value={stage} onChange={(event) => setStage(event.target.value as InterviewStage)}>{interviewStages.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select></label>
          <label>Date and time<input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} /></label>
          <label>Duration in minutes<input type="number" min="15" max="480" value={duration} onChange={(event) => setDuration(event.target.value)} /></label>
          <label>Location or meeting URL<input value={location} onChange={(event) => setLocation(event.target.value)} /></label>
        </div>
        <label>Private notes<textarea rows={3} value={privateNotes} onChange={(event) => setPrivateNotes(event.target.value)} /></label>
        <button disabled={busy || !applicationId}>Schedule Interview</button>
      </form>

      <div className="interviews-workspace">
        <section className="interviews-list-card">
          <div className="section-heading"><h2>Interview Schedule</h2><button type="button" className="secondary" onClick={() => void loadWorkspace()}>Refresh</button></div>
          <div className="application-list">
            {interviews.map((interview) => (
              <button key={interview.id} type="button" className={`application-row ${selected?.id === interview.id ? "selected" : ""}`} onClick={() => void openInterview(interview.id)}>
                <span className={`status-pill status-${interview.status}`}>{labelize(interview.status)}</span>
                <span><strong>{interview.job?.title || "Untitled application"}</strong><span className="metadata">{interview.job?.company || "Unknown company"} | {labelize(interview.interview_type)}</span><span className="metadata">{interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleString() : "Time not scheduled"}</span></span>
              </button>
            ))}
            {!interviews.length ? <p className="empty">No interviews scheduled.</p> : null}
          </div>
        </section>

        <aside className="interviews-detail-pane">
          {selected ? (
            <>
              <form key={selected.id} className="interview-detail-section" onSubmit={saveInterview}>
                <div className="section-heading"><div><h2>{selected.job?.title || "Interview"}</h2><p className="metadata">{selected.job?.company || "Unknown company"}</p></div><button disabled={busy}>Save Changes</button></div>
                <div className="form-grid">
                  <label>Type<select name="interview_type" defaultValue={selected.interview_type}>{interviewTypes.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select></label>
                  <label>Status<select name="status" defaultValue={selected.status}>{interviewStatuses.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select></label>
                  <label>Stage<select name="stage" defaultValue={selected.stage}>{interviewStages.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select></label>
                  <label>Outcome<select name="outcome" defaultValue={selected.outcome || ""}><option value="">No outcome</option>{interviewOutcomes.map((value) => <option key={value} value={value}>{labelize(value)}</option>)}</select></label>
                  <label>Date and time<input name="scheduled_at" type="datetime-local" defaultValue={dateTimeInputValue(selected.scheduled_at)} /></label>
                  <label>Duration<input name="duration_minutes" type="number" min="15" max="480" defaultValue={selected.duration_minutes || ""} /></label>
                </div>
                <label>Location or meeting URL<input name="location_or_url" defaultValue={selected.location_or_url || ""} /></label>
                <label>Private notes<textarea name="private_notes" rows={4} defaultValue={selected.private_notes || ""} /></label>
              </form>

              <section className="interview-detail-section">
                <h2>Interview Journal</h2>
                <form className="inline-note-form" onSubmit={handleAddNote}><textarea rows={3} value={newNote} onChange={(event) => setNewNote(event.target.value)} placeholder="Add a private preparation or follow-up note" /><button disabled={busy || !newNote.trim()}>Add Note</button></form>
                <div className="journal-list">{selected.notes.map((note) => <article key={note.id}><p>{note.body}</p><p className="metadata">{new Date(note.created_at).toLocaleString()}</p></article>)}{!selected.notes.length ? <p className="empty">No journal notes.</p> : null}</div>
              </section>

              <section className="interview-detail-section">
                <h2>Preparation Guide</h2>
                <form onSubmit={handleGeneratePrep}>
                  <label>Resume profile<select value={prepResumeId} onChange={(event) => setPrepResumeId(event.target.value)} required><option value="">Select resume</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title}{resume.is_default ? " (Default)" : ""}</option>)}</select></label>
                  <label>Company notes<textarea rows={4} value={companyNotes} onChange={(event) => setCompanyNotes(event.target.value)} placeholder="Optional facts or research to include" /></label>
                  <button disabled={busy || !prepResumeId}>{selected.prep_guides.length ? "Regenerate Guide" : "Generate Guide"}</button>
                </form>
                <div className="prep-guide-list">{selected.prep_guides.map((guide, index) => <PrepGuideView key={guide.id} guide={guide} title={`Guide ${selected.prep_guides.length - index}`} />)}{!selected.prep_guides.length ? <p className="empty">No preparation guide generated.</p> : null}</div>
              </section>
            </>
          ) : <section className="interview-detail-section"><p className="empty">Select an interview to review details and preparation.</p></section>}
        </aside>
      </div>
    </div>
  );
}

function PrepGuideView({ guide, title }: { guide: InterviewDetail["prep_guides"][number]; title: string }) {
  const output = guide.output_data;
  const [expanded, setExpanded] = useState(true);
  return (
    <article className="prep-guide">
      <button type="button" className="prep-guide-toggle" onClick={() => setExpanded((current) => !current)}><strong>{title}</strong><span className="metadata">{new Date(guide.created_at).toLocaleString()}</span></button>
      {expanded && output ? <div className="prep-guide-content">
        <p>{output.overview}</p>
        {output.warnings.length ? <div className="warning"><strong>Evidence warnings</strong><ul>{output.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
        <div className="result-grid">
          <section><h2>Study Priorities</h2><ul>{output.study_priorities.map((item) => <li key={`${item.topic}-${item.reason}`}><strong>{item.topic}</strong><span>{item.reason}</span></li>)}</ul></section>
          <section><h2>Likely Questions</h2><ul>{output.likely_questions.map((item) => <li key={item.question}><strong>{item.question}</strong><span>{item.rationale}</span></li>)}</ul></section>
          <section><h2>Evidence Talking Points</h2><ul>{output.talking_points.map((item) => <li key={`${item.topic}-${item.resume_evidence}`}><strong>{item.topic}</strong><span>{item.supported_claim}</span><span>Resume evidence: {item.resume_evidence}</span></li>)}</ul></section>
          <section><h2>Skill Gaps</h2><ul>{output.skill_gaps.map((item) => <li key={item.skill}><strong>{item.skill}</strong><span>{item.gap_evidence}</span><span>{item.study_action}</span></li>)}</ul></section>
        </div>
        {output.questions_to_research.length ? <section className="result-list"><h2>Questions to Research</h2><ul>{output.questions_to_research.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      </div> : expanded ? <p className="empty">This guide is still being prepared.</p> : null}
    </article>
  );
}

function InterviewPreview() {
  return <div className="interviews-manager"><section className="interview-detail-section"><h2>Interview workspace</h2><p>Log in to schedule interviews, keep private notes, and generate preparation guides from your saved application and resume evidence.</p><a className="button-link" href="/auth">Login or Register</a></section></div>;
}
