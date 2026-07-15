"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addApplicationNote,
  addApplicationTask,
  ApiRequestError,
  archiveApplication,
  ApplicationDetail,
  ApplicationPriority,
  ApplicationStage,
  ApplicationStatus,
  changeApplicationStatus,
  createApplication,
  getApplication,
  getAuthToken,
  listApplications,
  listJobs,
  restoreApplication,
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
  "accepted",
  "rejected",
  "withdrawn",
];

const stageOptions: ApplicationStage[] = [
  "recruiter_contact",
  "assessment",
  "phone_screen",
  "technical_interview",
  "final_interview",
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
  const [stage, setStage] = useState<ApplicationStage | "">("");
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
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "">("");
  const [stageFilter, setStageFilter] = useState<ApplicationStage | "">("");
  const [showArchived, setShowArchived] = useState(false);

  const visibleSavedJobs = useMemo(() => savedJobs, [savedJobs]);

  function applicationListOptions() {
    return {
      status: statusFilter || undefined,
      stage: stageFilter || undefined,
      includeArchived: showArchived,
    };
  }

  async function loadApplications() {
    setError(null);
    setIsLoading(true);
    try {
      const [applicationPayload, jobPayload] = await Promise.all([
        listApplications(applicationListOptions()),
        listJobs(),
      ]);
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
  }, [statusFilter, stageFilter, showArchived]);

  function syncEditor(application: ApplicationDetail) {
    setSelectedApplication(application);
    setStatus(application.status);
    setStage(application.stage ?? "");
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
    const create = (confirmDuplicate: boolean) =>
      createApplication({
        user_job_id: Number(selectedJobId),
        status: "interested",
        priority: "normal",
        confirm_duplicate: confirmDuplicate,
      });
    try {
      let created: ApplicationDetail;
      try {
        created = await create(false);
      } catch (err) {
        const detail = err instanceof ApiRequestError && err.detail && typeof err.detail === "object"
          ? err.detail as { code?: string; existing_application_id?: number }
          : null;
        if (detail?.code !== "duplicate_active_application") throw err;
        const confirmed = window.confirm(
          `An active application already exists${detail.existing_application_id ? ` (application #${detail.existing_application_id})` : ""}. Create another active application intentionally?`,
        );
        if (!confirmed) return;
        created = await create(true);
      }
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
        stage: stage || null,
        applied_at: toIsoFromDate(appliedAt),
        next_action_at: toIsoFromDateTime(nextActionAt),
        next_action_label: nextActionLabel.trim() || null,
        notes: notes.trim() || null,
      });
      if (status !== selectedApplication.status) {
        updated = await changeApplicationStatus(selectedApplication.id, status, statusReason.trim() || undefined);
      }
      syncEditor(updated);
      setApplications(await listApplications(applicationListOptions()));
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
      setApplications(await listApplications(applicationListOptions()));
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
      setApplications(await listApplications(applicationListOptions()));
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
      setApplications(await listApplications(applicationListOptions()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task update failed.");
    }
  }

  async function archiveSelectedApplication() {
    if (!selectedApplication) return;
    setError(null);
    setStatusMessage(null);
    try {
      await archiveApplication(selectedApplication.id);
      setSelectedApplication(null);
      setStatusMessage("Application archived.");
      await loadApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Application archive failed.");
    }
  }

  async function restoreSelectedApplication(confirmDuplicate = false) {
    if (!selectedApplication) return;
    setError(null);
    setStatusMessage(null);
    try {
      let restored: ApplicationDetail;
      try {
        restored = await restoreApplication(selectedApplication.id, confirmDuplicate);
      } catch (err) {
        const detail = err instanceof ApiRequestError && err.detail && typeof err.detail === "object"
          ? err.detail as { code?: string; existing_application_id?: number }
          : null;
        if (!confirmDuplicate && detail?.code === "duplicate_active_application") {
          const confirmed = window.confirm(
            `Another active application exists${detail.existing_application_id ? ` (application #${detail.existing_application_id})` : ""}. Restore this application as an intentional duplicate?`,
          );
          if (!confirmed) return;
          await restoreSelectedApplication(true);
          return;
        }
        throw err;
      }
      syncEditor(restored);
      setStatusMessage("Application restored.");
      await loadApplications();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Application restore failed.");
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
              {visibleSavedJobs.map((job) => (
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
          <div className="inline-form">
            <label>
              Status
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ApplicationStatus | "")}>
                <option value="">All statuses</option>
                {statusOptions.map((option) => (
                  <option value={option} key={option}>{labelize(option)}</option>
                ))}
              </select>
            </label>
            <label>
              Stage
              <select value={stageFilter} onChange={(event) => setStageFilter(event.target.value as ApplicationStage | "")}>
                <option value="">All stages</option>
                {stageOptions.map((option) => (
                  <option value={option} key={option}>{labelize(option)}</option>
                ))}
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
              />
              <span>Show archived</span>
            </label>
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
                  <strong>
                    {applicationTitle(application)}{application.archived_at ? " (Archived)" : ""}
                  </strong>
                  <span className="metadata">
                    {applicationCompany(application)} | Priority {application.priority}
                    {application.stage ? ` | Stage: ${labelize(application.stage)}` : ""}
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
                <div className="button-row">
                  {selectedApplication.archived_at ? (
                    <button type="button" onClick={() => void restoreSelectedApplication()}>
                      Restore
                    </button>
                  ) : (
                    <button type="button" className="secondary-button" onClick={() => void archiveSelectedApplication()}>
                      Archive
                    </button>
                  )}
                </div>
              </div>
              <form className="stack-form" onSubmit={saveApplicationDetails}>
                {selectedApplication.archived_at ? (
                  <div className="warning-banner">Restore this application before changing its status, stage, notes, or tasks.</div>
                ) : null}
                <div className="profile-grid">
                  <label>
                    Status
                    <select
                      value={status}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setStatus(event.target.value as ApplicationStatus)}
                    >
                      {statusOptions
                        .filter((option) =>
                          option === selectedApplication.status
                          || selectedApplication.allowed_status_transitions.includes(option),
                        )
                        .map((option) => (
                        <option value={option} key={option}>
                          {labelize(option)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Interview Stage
                    <select
                      value={stage}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setStage(event.target.value as ApplicationStage | "")}
                    >
                      <option value="">No stage</option>
                      {stageOptions.map((option) => (
                        <option value={option} key={option}>{labelize(option)}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Priority
                    <select
                      value={priority}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setPriority(event.target.value as ApplicationPriority)}
                    >
                      {priorityOptions.map((option) => (
                        <option value={option} key={option}>
                          {labelize(option)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Applied Date
                    <input
                      type="date"
                      value={appliedAt}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setAppliedAt(event.target.value)}
                    />
                  </label>
                  <label>
                    Next Action Date
                    <input
                      type="datetime-local"
                      value={nextActionAt}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setNextActionAt(event.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Next Action
                  <input
                    value={nextActionLabel}
                    disabled={Boolean(selectedApplication.archived_at)}
                    onChange={(event) => setNextActionLabel(event.target.value)}
                  />
                </label>
                <label>
                  Status Change Reason
                  <input
                    value={statusReason}
                    disabled={Boolean(selectedApplication.archived_at)}
                    onChange={(event) => setStatusReason(event.target.value)}
                  />
                </label>
                <label>
                  Notes
                  <textarea
                    value={notes}
                    disabled={Boolean(selectedApplication.archived_at)}
                    onChange={(event) => setNotes(event.target.value)}
                  />
                </label>
                <button type="submit" disabled={isSaving || Boolean(selectedApplication.archived_at)}>
                  {isSaving ? "Saving..." : "Save Application"}
                </button>
              </form>

              <div className="detail-grid">
                <section className="result-list">
                  <h2>Tasks And Reminders</h2>
                  <form className="stack-form compact-form" onSubmit={addTask}>
                    <input
                      value={newTaskTitle}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setNewTaskTitle(event.target.value)}
                      placeholder="Task title"
                    />
                    <input
                      type="datetime-local"
                      value={newTaskDueAt}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setNewTaskDueAt(event.target.value)}
                    />
                    <button type="submit" disabled={Boolean(selectedApplication.archived_at)}>Add Task</button>
                  </form>
                  {selectedApplication.tasks.length ? (
                    <ul>
                      {selectedApplication.tasks.map((task) => (
                        <li key={task.id}>
                          <label className="checkbox-row">
                            <input
                              type="checkbox"
                              checked={Boolean(task.completed_at)}
                              disabled={Boolean(selectedApplication.archived_at)}
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
                    <textarea
                      value={newNote}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setNewNote(event.target.value)}
                    />
                    <button type="submit" disabled={Boolean(selectedApplication.archived_at)}>Add Note</button>
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
                        <span>
                          {new Date(event.created_at).toLocaleString()}
                          {typeof event.payload.actor_external_user_id === "string"
                            ? ` | Actor: ${event.payload.actor_external_user_id}`
                            : ""}
                        </span>
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
