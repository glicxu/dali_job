"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  addApplicationNote,
  addApplicationTask,
  ApiRequestError,
  archiveApplication,
  ApplicationDetail,
  ApplicationDocumentPurpose,
  ApplicationPriority,
  ApplicationStage,
  ApplicationStatus,
  ApplicationTask,
  ApplicationTaskType,
  attachApplicationDocument,
  changeApplicationStatus,
  createApplication,
  detachApplicationDocument,
  downloadApplicationDocument,
  getApplication,
  getAuthToken,
  listApplications,
  listDocuments,
  listJobs,
  openApplicationDocument,
  restoreApplication,
  StoredDocument,
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
const taskTypeOptions: ApplicationTaskType[] = ["follow_up", "interview_prep", "document", "deadline", "other"];
const attachmentPurposeOptions: ApplicationDocumentPurpose[] = ["resume", "cover_letter", "supporting"];

type TaskDraft = {
  taskType: ApplicationTaskType;
  dueAt: string;
  reminderAt: string;
};

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

type ApplicationTrackerProps = {
  applicationId?: number;
};

export function ApplicationTracker({ applicationId }: ApplicationTrackerProps = {}) {
  if (!getAuthToken()) {
    return <ApplicationTrackerPreview />;
  }

  const [applications, setApplications] = useState<TrackedApplication[]>([]);
  const [savedJobs, setSavedJobs] = useState<StoredJob[]>([]);
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
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
  const [newTaskReminderAt, setNewTaskReminderAt] = useState("");
  const [newTaskType, setNewTaskType] = useState<ApplicationTaskType>("other");
  const [taskStatusFilter, setTaskStatusFilter] = useState<"" | "open" | "completed">("");
  const [taskTypeFilter, setTaskTypeFilter] = useState<"" | ApplicationTaskType>("");
  const [taskDrafts, setTaskDrafts] = useState<Record<number, TaskDraft>>({});
  const [attachmentVersionId, setAttachmentVersionId] = useState("");
  const [attachmentPurpose, setAttachmentPurpose] = useState<ApplicationDocumentPurpose>("resume");
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "">("");
  const [stageFilter, setStageFilter] = useState<ApplicationStage | "">("");
  const [showArchived, setShowArchived] = useState(false);
  const openedQueryApplication = useRef(false);
  const isDetailPage = applicationId !== undefined;

  const visibleSavedJobs = useMemo(() => savedJobs, [savedJobs]);
  const visibleTasks = useMemo(
    () => selectedApplication?.tasks.filter((task) => {
      if (taskStatusFilter === "open" && task.completed_at) return false;
      if (taskStatusFilter === "completed" && !task.completed_at) return false;
      if (taskTypeFilter && task.task_type !== taskTypeFilter) return false;
      return true;
    }) ?? [],
    [selectedApplication, taskStatusFilter, taskTypeFilter],
  );

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
      const [applicationPayload, jobPayload, documentPayload] = await Promise.all([
        listApplications(applicationListOptions()),
        listJobs(),
        listDocuments(),
      ]);
      setApplications(applicationPayload);
      setSavedJobs(jobPayload);
      setDocuments(documentPayload.documents);
      if (applicationId !== undefined) {
        syncEditor(await getApplication(applicationId));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load applications.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadApplications();
  }, [statusFilter, stageFilter, showArchived, applicationId]);

  useEffect(() => {
    if (isDetailPage || isLoading || openedQueryApplication.current || typeof window === "undefined") return;
    openedQueryApplication.current = true;
    const applicationId = Number(new URLSearchParams(window.location.search).get("application_id"));
    if (Number.isInteger(applicationId) && applicationId > 0) void openApplication(applicationId);
  }, [isDetailPage, isLoading]);

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
    setTaskDrafts(Object.fromEntries(application.tasks.map((task) => [
      task.id,
      {
        taskType: task.task_type,
        dueAt: dateTimeInputValue(task.due_at),
        reminderAt: dateTimeInputValue(task.reminder_at),
      },
    ])));
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
      await addApplicationTask(selectedApplication.id, newTaskTitle.trim(), {
        taskType: newTaskType,
        dueAt: toIsoFromDateTime(newTaskDueAt),
        reminderAt: toIsoFromDateTime(newTaskReminderAt),
      });
      setNewTaskTitle("");
      setNewTaskDueAt("");
      setNewTaskReminderAt("");
      setNewTaskType("other");
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

  async function saveTaskSchedule(task: ApplicationTask) {
    if (!selectedApplication) return;
    const draft = taskDrafts[task.id];
    if (!draft) return;
    setError(null);
    try {
      await updateApplicationTask(selectedApplication.id, task.id, {
        task_type: draft.taskType,
        due_at: toIsoFromDateTime(draft.dueAt),
        reminder_at: toIsoFromDateTime(draft.reminderAt),
      });
      syncEditor(await getApplication(selectedApplication.id));
      setStatusMessage("Task schedule updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task reschedule failed.");
    }
  }

  async function dismissTaskReminder(taskId: number) {
    if (!selectedApplication) return;
    setError(null);
    try {
      await updateApplicationTask(selectedApplication.id, taskId, { dismiss_reminder: true });
      syncEditor(await getApplication(selectedApplication.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reminder dismissal failed.");
    }
  }

  async function attachDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedApplication || !attachmentVersionId) return;
    setError(null);
    try {
      await attachApplicationDocument(selectedApplication.id, Number(attachmentVersionId), attachmentPurpose);
      setAttachmentVersionId("");
      syncEditor(await getApplication(selectedApplication.id));
      setStatusMessage("Document version attached.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document attachment failed.");
    }
  }

  async function detachDocument(attachmentId: number) {
    if (!selectedApplication || !window.confirm("Detach this document version from the application?")) return;
    setError(null);
    try {
      await detachApplicationDocument(selectedApplication.id, attachmentId);
      syncEditor(await getApplication(selectedApplication.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document detachment failed.");
    }
  }

  async function downloadAttachment(attachmentId: number, fileName: string) {
    if (!selectedApplication) return;
    setError(null);
    try {
      await downloadApplicationDocument(selectedApplication.id, attachmentId, fileName);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document download failed.");
    }
  }

  async function openAttachment(attachmentId: number) {
    if (!selectedApplication) return;
    setError(null);
    try {
      await openApplicationDocument(selectedApplication.id, attachmentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document preview failed.");
    }
  }

  async function archiveSelectedApplication() {
    if (!selectedApplication) return;
    setError(null);
    setStatusMessage(null);
    try {
      const archived = await archiveApplication(selectedApplication.id);
      if (isDetailPage) {
        syncEditor(archived);
      } else {
        setSelectedApplication(null);
      }
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

      {!isDetailPage ? <section className="profile-card">
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
      </section> : null}

      <section className={isDetailPage ? "application-detail-page" : "applications-workspace"}>
        {!isDetailPage ? <section className="profile-card applications-list-card">
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
        </section> : null}

        <div className="applications-detail-pane">
          {selectedApplication ? (
            isDetailPage ? (
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

              <div className="application-editor-sections">
                <CollapsibleApplicationSection
                  title="Application Materials"
                  description={`${selectedApplication.documents.length} attached document${selectedApplication.documents.length === 1 ? "" : "s"}`}
                >
                <p className="metadata">Attachments stay pinned to the exact file version shown.</p>
                <form className="inline-form" onSubmit={attachDocument}>
                  <label>
                    Document Version
                    <select
                      value={attachmentVersionId}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setAttachmentVersionId(event.target.value)}
                      required
                    >
                      <option value="">Select a document</option>
                      {documents.filter((document) => document.latest_version).map((document) => (
                        <option value={document.latest_version?.id} key={document.id}>
                          {document.title} - v{document.latest_version?.version_number}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Purpose
                    <select
                      value={attachmentPurpose}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setAttachmentPurpose(event.target.value as ApplicationDocumentPurpose)}
                    >
                      {attachmentPurposeOptions.map((option) => (
                        <option value={option} key={option}>{labelize(option)}</option>
                      ))}
                    </select>
                  </label>
                  <button type="submit" disabled={Boolean(selectedApplication.archived_at) || !attachmentVersionId}>
                    Attach
                  </button>
                </form>
                {selectedApplication.documents.length ? (
                  <div className="application-document-list">
                    {selectedApplication.documents.map((attachment) => (
                      <article className="application-document-row" key={attachment.id}>
                        <div>
                          <button
                            type="button"
                            className="document-preview-link"
                            onClick={() => void openAttachment(attachment.id)}
                          >
                            {attachment.document_title}
                          </button>
                          <span className="metadata">
                            {labelize(attachment.purpose)} | Version {attachment.version_number} | {attachment.file_name}
                          </span>
                        </div>
                        <div className="button-row">
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() => void downloadAttachment(attachment.id, attachment.file_name)}
                          >
                            Download
                          </button>
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={Boolean(selectedApplication.archived_at)}
                            onClick={() => void detachDocument(attachment.id)}
                          >
                            Detach
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="empty">No submitted documents attached.</p>
                )}
                </CollapsibleApplicationSection>

                <CollapsibleApplicationSection
                  title="Tasks And Reminders"
                  description={`${selectedApplication.tasks.length} task${selectedApplication.tasks.length === 1 ? "" : "s"}`}
                >
                  <form className="stack-form compact-form" onSubmit={addTask}>
                    <input
                      value={newTaskTitle}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setNewTaskTitle(event.target.value)}
                      placeholder="Task title"
                    />
                    <select
                      value={newTaskType}
                      disabled={Boolean(selectedApplication.archived_at)}
                      onChange={(event) => setNewTaskType(event.target.value as ApplicationTaskType)}
                    >
                      {taskTypeOptions.map((option) => (
                        <option value={option} key={option}>{labelize(option)}</option>
                      ))}
                    </select>
                    <label>
                      Due
                      <input
                        type="datetime-local"
                        value={newTaskDueAt}
                        disabled={Boolean(selectedApplication.archived_at)}
                        onChange={(event) => setNewTaskDueAt(event.target.value)}
                      />
                    </label>
                    <label>
                      Remind At
                      <input
                        type="datetime-local"
                        value={newTaskReminderAt}
                        disabled={Boolean(selectedApplication.archived_at)}
                        onChange={(event) => setNewTaskReminderAt(event.target.value)}
                      />
                    </label>
                    <button type="submit" disabled={Boolean(selectedApplication.archived_at)}>Add Task</button>
                  </form>
                  <div className="inline-form application-task-filters">
                    <label>
                      State
                      <select value={taskStatusFilter} onChange={(event) => setTaskStatusFilter(event.target.value as "" | "open" | "completed")}>
                        <option value="">All</option>
                        <option value="open">Open</option>
                        <option value="completed">Completed</option>
                      </select>
                    </label>
                    <label>
                      Type
                      <select value={taskTypeFilter} onChange={(event) => setTaskTypeFilter(event.target.value as "" | ApplicationTaskType)}>
                        <option value="">All types</option>
                        {taskTypeOptions.map((option) => (
                          <option value={option} key={option}>{labelize(option)}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {visibleTasks.length ? (
                    <ul>
                      {visibleTasks.map((task) => (
                        <li className={task.is_overdue ? "application-task-overdue" : ""} key={task.id}>
                          <label className="checkbox-row">
                            <input
                              type="checkbox"
                              checked={Boolean(task.completed_at)}
                              disabled={Boolean(selectedApplication.archived_at)}
                              onChange={(event) => void toggleTask(task.id, event.target.checked)}
                            />
                            <span>
                              <strong>{task.title}</strong>
                              <span>{labelize(task.task_type)}{task.is_overdue ? " | Overdue" : ""}</span>
                            </span>
                          </label>
                          <div className="application-task-schedule">
                            <label>
                              Due
                              <input
                                type="datetime-local"
                                value={taskDrafts[task.id]?.dueAt ?? ""}
                                disabled={Boolean(selectedApplication.archived_at)}
                                onChange={(event) => setTaskDrafts((current) => ({
                                  ...current,
                                  [task.id]: {
                                    ...(current[task.id] ?? { taskType: task.task_type, dueAt: "", reminderAt: "" }),
                                    dueAt: event.target.value,
                                  },
                                }))}
                              />
                            </label>
                            <label>
                              Reminder
                              <input
                                type="datetime-local"
                                value={taskDrafts[task.id]?.reminderAt ?? ""}
                                disabled={Boolean(selectedApplication.archived_at)}
                                onChange={(event) => setTaskDrafts((current) => ({
                                  ...current,
                                  [task.id]: {
                                    ...(current[task.id] ?? { taskType: task.task_type, dueAt: "", reminderAt: "" }),
                                    reminderAt: event.target.value,
                                  },
                                }))}
                              />
                            </label>
                            <select
                              aria-label="Task type"
                              value={taskDrafts[task.id]?.taskType ?? task.task_type}
                              disabled={Boolean(selectedApplication.archived_at)}
                              onChange={(event) => setTaskDrafts((current) => ({
                                ...current,
                                [task.id]: {
                                  ...(current[task.id] ?? { taskType: task.task_type, dueAt: "", reminderAt: "" }),
                                  taskType: event.target.value as ApplicationTaskType,
                                },
                              }))}
                            >
                              {taskTypeOptions.map((option) => (
                                <option value={option} key={option}>{labelize(option)}</option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className="secondary-button"
                              disabled={Boolean(selectedApplication.archived_at)}
                              onClick={() => void saveTaskSchedule(task)}
                            >
                              Update
                            </button>
                            {task.reminder_due ? (
                              <button
                                type="button"
                                className="secondary-button"
                                disabled={Boolean(selectedApplication.archived_at)}
                                onClick={() => void dismissTaskReminder(task.id)}
                              >
                                Dismiss Reminder
                              </button>
                            ) : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="empty">No tasks match these filters.</p>
                  )}
                </CollapsibleApplicationSection>

                <CollapsibleApplicationSection
                  title="Notes"
                  description={`${selectedApplication.notes_list.length} note${selectedApplication.notes_list.length === 1 ? "" : "s"}`}
                >
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
                </CollapsibleApplicationSection>
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
              <ApplicationReadOnlyPreview
                application={selectedApplication}
                onOpenDocument={(attachmentId) => void openAttachment(attachmentId)}
              />
            )
          ) : (
            <section className="profile-card">
              <h2>Application Detail</h2>
              <p className="empty">
                {isDetailPage
                  ? "Loading application details."
                  : "Select an application to view its summary and attached documents."}
              </p>
            </section>
          )}
        </div>
      </section>
    </div>
  );
}

function ApplicationReadOnlyPreview({
  application,
  onOpenDocument,
}: {
  application: ApplicationDetail;
  onOpenDocument: (attachmentId: number) => void;
}) {
  return (
    <section className="profile-card application-readonly-preview">
      <div className="profile-card-header">
        <div>
          <h2>{applicationTitle(application)}</h2>
          <p className="metadata">
            {applicationCompany(application)} | Application ID: {application.id}
          </p>
        </div>
        <a className="button-link" href={`/applications/${application.id}`}>
          View / Edit
        </a>
      </div>

      <dl className="application-summary-grid">
        <div><dt>Status</dt><dd>{labelize(application.status)}</dd></div>
        <div><dt>Stage</dt><dd>{application.stage ? labelize(application.stage) : "No stage"}</dd></div>
        <div><dt>Priority</dt><dd>{labelize(application.priority)}</dd></div>
        <div><dt>Match Score</dt><dd>{application.match_score === null ? "N/A" : `${application.match_score}/10`}</dd></div>
        <div><dt>Applied</dt><dd>{application.applied_at ? new Date(application.applied_at).toLocaleDateString() : "Not recorded"}</dd></div>
        <div><dt>Next Action</dt><dd>{application.next_action_label || "Not set"}</dd></div>
      </dl>

      <section className="application-preview-section">
        <h3>Notes</h3>
        <p>{application.notes || "No application notes."}</p>
      </section>

      <section className="application-preview-section">
        <h3>Attached Documents</h3>
        {application.documents.length ? (
          <div className="application-document-list">
            {application.documents.map((attachment) => (
              <button
                type="button"
                className="application-document-row application-document-open"
                key={attachment.id}
                onClick={() => onOpenDocument(attachment.id)}
              >
                <span>
                  <strong>{attachment.document_title}</strong>
                  <span className="metadata">
                    {labelize(attachment.purpose)} | Version {attachment.version_number} | {attachment.file_name}
                  </span>
                </span>
                <span className="document-open-label">View</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="empty">No submitted documents attached.</p>
        )}
      </section>

      <div className="application-preview-counts metadata">
        {application.tasks.length} task{application.tasks.length === 1 ? "" : "s"} | {application.notes_list.length} timeline note{application.notes_list.length === 1 ? "" : "s"}
      </div>
    </section>
  );
}

function CollapsibleApplicationSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className={`result-list application-editor-collapsible${expanded ? " expanded" : ""}`}>
      <button
        type="button"
        className="application-editor-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span>
          <strong>{title}</strong>
          <span className="metadata">{description}</span>
        </span>
        <span>{expanded ? "Hide" : "Show"}</span>
      </button>
      {expanded ? <div className="application-editor-collapsible-content">{children}</div> : null}
    </section>
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
