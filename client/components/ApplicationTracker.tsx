"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addApplicationNote,
  addApplicationTask,
  ApplicationDetail,
  ApplicationPriority,
  ApplicationStatus,
  changeApplicationStatus,
  createApplication,
  getApplication,
  getAuthToken,
  listApplications,
  listJobs,
  StoredJob,
  TrackedApplication,
  updateApplication,
  updateApplicationTask,
} from "../lib/api";

const statusOptions: ApplicationStatus[] = [
  "interested",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
  "archived",
];

const priorityOptions: ApplicationPriority[] = ["low", "normal", "high"];

function labelize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function dateInputValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

function dateTimeInputValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function toIsoFromDate(value: string): string | null {
  return value ? new Date(`${value}T12:00:00`).toISOString() : null;
}

function toIsoFromDateTime(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

function applicationTitle(application: TrackedApplication | ApplicationDetail): string {
  return application.job?.title || "Untitled Application";
}

function applicationCompany(application: TrackedApplication | ApplicationDetail): string {
  return application.job?.company || "Unknown company";
}

export function ApplicationTracker() {
  if (!getAuthToken()) {
    return <ApplicationTrackerPreview />;
  }

  const [applications, setApplications] = useState<TrackedApplication[]>([]);
  const [savedJobs, setSavedJobs] = useState<StoredJob[]>([]);
  const [selectedApplication, setSelectedApplication] = useState<ApplicationDetail | null>(null);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [status, setStatus] = useState<ApplicationStatus>("interested");
  const [priority, setPriority] = useState<ApplicationPriority>("normal");
  const [nextActionLabel, setNextActionLabel] = useState("");
  const [nextActionAt, setNextActionAt] = useState("");
  const [appliedAt, setAppliedAt] = useState("");
  const [notes, setNotes] = useState("");
  const [statusReason, setStatusReason] = useState("");
  const [newNote, setNewNote] = useState("");
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskDueAt, setNewTaskDueAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const savedJobsWithoutApplications = useMemo(() => {
    const applicationJobIds = new Set(applications.map((application) => application.user_job_id).filter(Boolean));
    return savedJobs.filter((job) => !applicationJobIds.has(job.id));
  }, [applications, savedJobs]);

  async function loadApplications() {
    setError(null);
    setIsLoading(true);
    try {
      const [applicationPayload, jobPayload] = await Promise.all([listApplications(), listJobs()]);
      setApplications(applicationPayload);
      setSavedJobs(jobPayload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load applications.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadApplications();
  }, []);

  function syncEditor(application: ApplicationDetail) {
    setSelectedApplication(application);
    setStatus(application.status);
    setPriority(application.priority);
    setNextActionLabel(application.next_action_label ?? "");
    setNextActionAt(dateTimeInputValue(application.next_action_at));
    setAppliedAt(dateInputValue(application.applied_at));
    setNotes(application.notes ?? "");
    setStatusReason("");
  }

  async function openApplication(applicationId: number) {
    setError(null);
    try {
      syncEditor(await getApplication(applicationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open application.");
    }
  }

  async function createNewApplication(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedJobId) return;
    setError(null);
    setStatusMessage(null);
    setIsSaving(true);
    try {
      const created = await createApplication({
        user_job_id: Number(selectedJobId),
        status: "interested",
        priority: "normal",
      });
      setSelectedJobId("");
      syncEditor(created);
      setStatusMessage("Application created.");
      await loadApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Application creation failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function saveApplicationDetails(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication) return;
    setError(null);
    setStatusMessage(null);
    setIsSaving(true);
    try {
      let updated = await updateApplication(selectedApplication.id, {
        priority,
        applied_at: toIsoFromDate(appliedAt),
        next_action_at: toIsoFromDateTime(nextActionAt),
        next_action_label: nextActionLabel.trim() || null,
        notes: notes.trim() || null,
      });
      if (status !== selectedApplication.status) {
        updated = await changeApplicationStatus(selectedApplication.id, status, statusReason.trim() || undefined);
      }
      syncEditor(updated);
      setApplications(await listApplications());
      setStatusMessage("Application updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Application update failed.");
    } finally {
      setIsSaving(false);
    }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication || !newNote.trim()) return;
    setError(null);
    try {
      await addApplicationNote(selectedApplication.id, newNote.trim());
      setNewNote("");
      syncEditor(await getApplication(selectedApplication.id));
      setApplications(await listApplications());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Note creation failed.");
    }
  }

  async function addTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication || !newTaskTitle.trim()) return;
    setError(null);
    try {
      await addApplicationTask(selectedApplication.id, newTaskTitle.trim(), toIsoFromDateTime(newTaskDueAt));
      setNewTaskTitle("");
      setNewTaskDueAt("");
      syncEditor(await getApplication(selectedApplication.id));
      setApplications(await listApplications());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task creation failed.");
    }
  }

  async function toggleTask(taskId: number, completed: boolean) {
    if (!selectedApplication) return;
    setError(null);
    try {
      await updateApplicationTask(selectedApplication.id, taskId, { completed });
      syncEditor(await getApplication(selectedApplication.id));
      setApplications(await listApplications());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task update failed.");
    }
  }

  return (
    <div className="applications-manager">
      {error ? <div className="error-banner">{error}</div> : null}
      {statusMessage ? <div className="status-banner">{statusMessage}</div> : null}

      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Create Application</h2>
            <p className="metadata">Start tracking from a saved job.</p>
          </div>
        </div>
        <form className="inline-form" onSubmit={createNewApplication}>
          <label>
            Saved Job
            <select value={selectedJobId} onChange={(event) => setSelectedJobId(event.target.value)} required>
              <option value="">Select a saved job</option>
              {savedJobsWithoutApplications.map((job) => (
                <option value={job.id} key={job.id}>
                  {job.title || "Untitled Job"} - {job.company || "Unknown company"}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={isSaving || !selectedJobId}>
            {isSaving ? "Creating..." : "Create Application"}
          </button>
        </form>
      </section>

      <section className="applications-workspace">
        <section className="profile-card applications-list-card">
          <div className="profile-card-header">
            <h2>Applications</h2>
            <button type="button" className="secondary-button" onClick={() => void loadApplications()}>
              Refresh
            </button>
          </div>
          {isLoading ? <p className="empty">Loading applications.</p> : null}
          {!isLoading && !applications.length ? <p className="empty">No applications yet.</p> : null}
          <div className="application-list">
            {applications.map((application) => (
              <button
                type="button"
                key={application.id}
                className={`application-row${selectedApplication?.id === application.id ? " selected" : ""}`}
                onClick={() =>
                  selectedApplication?.id === application.id
                    ? setSelectedApplication(null)
                    : void openApplication(application.id)
                }
              >
                <span className={`status-pill status-${application.status}`}>{labelize(application.status)}</span>
                <span>
                  <strong>{applicationTitle(application)}</strong>
                  <span className="metadata">
                    {applicationCompany(application)} | Priority {application.priority}
                    {application.next_action_label ? ` | Next: ${application.next_action_label}` : ""}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <div className="applications-detail-pane">
          {selectedApplication ? (
            <section className="profile-card">
              <div className="profile-card-header">
                <div>
                  <h2>{applicationTitle(selectedApplication)}</h2>
                  <p className="metadata">
                    {applicationCompany(selectedApplication)} | Application ID: {selectedApplication.id}
                  </p>
                </div>
              </div>
              <form className="stack-form" onSubmit={saveApplicationDetails}>
                <div className="profile-grid">
                  <label>
                    Status
                    <select value={status} onChange={(event) => setStatus(event.target.value as ApplicationStatus)}>
                      {statusOptions.map((option) => (
                        <option value={option} key={option}>
                          {labelize(option)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Priority
                    <select value={priority} onChange={(event) => setPriority(event.target.value as ApplicationPriority)}>
                      {priorityOptions.map((option) => (
                        <option value={option} key={option}>
                          {labelize(option)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Applied Date
                    <input type="date" value={appliedAt} onChange={(event) => setAppliedAt(event.target.value)} />
                  </label>
                  <label>
                    Next Action Date
                    <input
                      type="datetime-local"
                      value={nextActionAt}
                      onChange={(event) => setNextActionAt(event.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Next Action
                  <input value={nextActionLabel} onChange={(event) => setNextActionLabel(event.target.value)} />
                </label>
                <label>
                  Status Change Reason
                  <input value={statusReason} onChange={(event) => setStatusReason(event.target.value)} />
                </label>
                <label>
                  Notes
                  <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
                </label>
                <button type="submit" disabled={isSaving}>
                  {isSaving ? "Saving..." : "Save Application"}
                </button>
              </form>

              <div className="detail-grid">
                <section className="result-list">
                  <h2>Tasks And Reminders</h2>
                  <form className="stack-form compact-form" onSubmit={addTask}>
                    <input
                      value={newTaskTitle}
                      onChange={(event) => setNewTaskTitle(event.target.value)}
                      placeholder="Task title"
                    />
                    <input
                      type="datetime-local"
                      value={newTaskDueAt}
                      onChange={(event) => setNewTaskDueAt(event.target.value)}
                    />
                    <button type="submit">Add Task</button>
                  </form>
                  {selectedApplication.tasks.length ? (
                    <ul>
                      {selectedApplication.tasks.map((task) => (
                        <li key={task.id}>
                          <label className="checkbox-row">
                            <input
                              type="checkbox"
                              checked={Boolean(task.completed_at)}
                              onChange={(event) => void toggleTask(task.id, event.target.checked)}
                            />
                            <span>
                              <strong>{task.title}</strong>
                              {task.due_at ? <span>{new Date(task.due_at).toLocaleString()}</span> : null}
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="empty">No tasks yet.</p>
                  )}
                </section>

                <section className="result-list">
                  <h2>Notes</h2>
                  <form className="stack-form compact-form" onSubmit={addNote}>
                    <textarea value={newNote} onChange={(event) => setNewNote(event.target.value)} />
                    <button type="submit">Add Note</button>
                  </form>
                  {selectedApplication.notes_list.length ? (
                    <ul>
                      {selectedApplication.notes_list.map((note) => (
                        <li key={note.id}>
                          <strong>{new Date(note.created_at).toLocaleString()}</strong>
                          <span>{note.body}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="empty">No timeline notes yet.</p>
                  )}
                </section>
              </div>

              <section className="result-list">
                <h2>Timeline</h2>
                {selectedApplication.events.length ? (
                  <ul>
                    {selectedApplication.events.map((event) => (
                      <li key={event.id}>
                        <strong>{labelize(event.event_type)}</strong>
                        <span>{new Date(event.created_at).toLocaleString()}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty">No timeline events yet.</p>
                )}
              </section>
            </section>
          ) : (
            <section className="profile-card">
              <h2>Application Detail</h2>
              <p className="empty">Select an application to view status, notes, tasks, reminders, and timeline.</p>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}

function ApplicationTrackerPreview() {
  return (
    <div className="applications-manager">
      <div className="warning-banner">Login is required to create, update, and track applications.</div>
      <section className="profile-card">
        <h2>Create Application</h2>
        <p className="metadata">Start tracking from a saved job after login.</p>
      </section>
      <section className="applications-workspace">
        <section className="profile-card applications-list-card">
          <h2>Applications</h2>
          <div className="application-list">
            <article className="application-row selected">
              <span className="status-pill status-applied">Applied</span>
              <span>
                <strong>Backend Software Engineer</strong>
                <span className="metadata">Example Cloud Co | Priority high | Next: Follow up</span>
              </span>
            </article>
          </div>
        </section>
        <section className="profile-card">
          <h2>Application Detail</h2>
          <p className="empty">Login to manage status, notes, tasks, reminders, and timeline.</p>
          <a className="button-link" href="/auth">
            Login / Register
          </a>
        </section>
      </section>
    </div>
  );
}
