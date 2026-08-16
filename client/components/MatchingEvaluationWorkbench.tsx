"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { FileUp, FlaskConical, Play, RefreshCw, SearchCheck } from "lucide-react";
import {
  applyResumeProfileSuggestions, createEvaluationRun, EvaluationEvidenceSpan,
  EvaluationJobSnapshot, EvaluationRequirementAssessment, EvaluationRunDetail,
  EvaluationRunSummary, getCurrentUser, getEvaluationRun, importEvaluationJobSnapshot,
  importResumePdf, listEvaluationJobSnapshots, listEvaluationRuns, listResumeProfiles, ResumeProfile,
} from "../lib/api";
import { AlertBanner, Button, EmptyState, SectionHeader } from "./ui";

const DEFAULT_RELEASE = "matching-benchmark-jobs.v1";

export function MatchingEvaluationWorkbench() {
  const [resumes, setResumes] = useState<ResumeProfile[]>([]);
  const [snapshots, setSnapshots] = useState<EvaluationJobSnapshot[]>([]);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [resumeId, setResumeId] = useState(0);
  const [snapshotId, setSnapshotId] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [release, setRelease] = useState(DEFAULT_RELEASE);
  const [coverageSlot, setCoverageSlot] = useState("");
  const [result, setResult] = useState<EvaluationRunDetail | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const [resumePayload, snapshotPayload, runPayload] = await Promise.all([
      listResumeProfiles(), listEvaluationJobSnapshots(), listEvaluationRuns(),
    ]);
    setResumes(resumePayload.resume_profiles);
    setSnapshots(snapshotPayload.snapshots);
    setRuns(runPayload.runs);
    setResumeId((current) => current || resumePayload.resume_profiles[0]?.id || 0);
    setSnapshotId((current) => current || snapshotPayload.snapshots[0]?.public_id || "");
  }

  useEffect(() => {
    getCurrentUser().then((user) => {
      if (user.role !== "admin") throw new Error("Admin access is required.");
      return refresh();
    }).catch((err) => setError(err instanceof Error ? err.message : "Could not load evaluation data."))
      .finally(() => setLoading(false));
  }, []);

  async function captureJob(event: FormEvent) {
    event.preventDefault(); setWorking("capture"); setError("");
    try {
      const captured = await importEvaluationJobSnapshot({ source_url: jobUrl, benchmark_release: release, coverage_slot: coverageSlot });
      await refresh(); setSnapshotId(captured.public_id); setJobUrl("");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not capture the job posting."); }
    finally { setWorking(""); }
  }

  async function loadResume(file: File | undefined) {
    if (!file) return; setWorking("resume"); setError("");
    try {
      const parsed = await importResumePdf(file);
      const profile = await applyResumeProfileSuggestions(parsed);
      await refresh(); setResumeId(profile.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not load the resume."); }
    finally { setWorking(""); }
  }

  async function runEvaluation() {
    if (!resumeId || !snapshotId) return; setWorking("run"); setError(""); setSelectedEvidence("");
    try {
      const detail = await createEvaluationRun({ resume_profile_id: resumeId, job_snapshot_id: snapshotId });
      setResult(detail); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "The evaluation run failed."); }
    finally { setWorking(""); }
  }

  async function openRun(runId: string) {
    setWorking("open"); setError("");
    try { setResult(await getEvaluationRun(runId)); setSelectedEvidence(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not open the evaluation run."); }
    finally { setWorking(""); }
  }

  if (loading) return <p>Loading evaluation workbench…</p>;
  return <div className="evaluation-workbench">
    {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
    <section className="evaluation-setup-grid">
      <form className="profile-card" onSubmit={captureJob}>
        <SectionHeader title="1. Freeze a job posting" description="The server fetches and stores an immutable JD snapshot for repeatable tests." />
        <label>Job URL<input type="url" required value={jobUrl} onChange={(event) => setJobUrl(event.target.value)} placeholder="https://company.com/jobs/123" /></label>
        <label>Benchmark release<input required value={release} onChange={(event) => setRelease(event.target.value)} /></label>
        <label>Coverage slot<input value={coverageSlot} onChange={(event) => setCoverageSlot(event.target.value)} placeholder="Senior software / infrastructure" /></label>
        <Button type="submit" icon={SearchCheck} loading={working === "capture"}>Fetch and freeze</Button>
      </form>
      <section className="profile-card">
        <SectionHeader title="2. Choose a resume" description="Use an existing profile or load a PDF fixture into your profile library." />
        <label>Resume profile<select value={resumeId} onChange={(event) => setResumeId(Number(event.target.value))}><option value={0}>Select a resume</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title}</option>)}</select></label>
        <label className="evaluation-file-button"><FileUp size={18} aria-hidden="true" /><span>{working === "resume" ? "Loading resume…" : "Load resume PDF"}</span><input type="file" accept="application/pdf,.pdf" disabled={Boolean(working)} onChange={(event) => void loadResume(event.target.files?.[0])} /></label>
      </section>
      <section className="profile-card">
        <SectionHeader title="3. Run the three stages" description="Creates or reuses the exact V2 Candidate Profile, Job Profile, and Qualification Assessment." />
        <label>Frozen job<select value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)}><option value="">Select a snapshot</option>{snapshots.map((snapshot) => <option key={snapshot.public_id} value={snapshot.public_id}>{snapshot.company ? `${snapshot.company} — ` : ""}{snapshot.title || snapshot.coverage_slot || snapshot.public_id}</option>)}</select></label>
        <Button type="button" icon={Play} loading={working === "run"} disabled={!resumeId || !snapshotId} onClick={() => void runEvaluation()}>Run evaluation now</Button>
        <small>No weighted score is generated; this evaluates the first three stages only.</small>
      </section>
    </section>
    {runs.length ? <section className="profile-card evaluation-history"><SectionHeader title="Recent runs" description="Open a persisted run without calling providers again." /><div className="evaluation-run-links">{runs.slice(0, 10).map((run) => <button type="button" key={run.public_id} onClick={() => void openRun(run.public_id)}><RefreshCw size={14} />{new Date(run.created_at).toLocaleString()} · {run.public_id}</button>)}</div></section> : null}
    {result ? <EvaluationResult detail={result} selectedEvidence={selectedEvidence} onSelectEvidence={setSelectedEvidence} /> : <EmptyState icon={FlaskConical} title="No evaluation selected" description="Choose a resume and frozen job, then run the three-stage pipeline." />}
  </div>;
}

function EvaluationResult({ detail, selectedEvidence, onSelectEvidence }: { detail: EvaluationRunDetail; selectedEvidence: string; onSelectEvidence: (value: string) => void }) {
  const assessments = useMemo(() => [...detail.qualification.assessment.hard_constraint_assessments, ...detail.qualification.assessment.requirement_assessments], [detail]);
  return <section className="evaluation-result">
    <SectionHeader title={`${detail.resume_title} ↔ ${detail.job_company ? `${detail.job_company} ` : ""}${detail.job_title}`} description={`Run ${detail.public_id} · ${detail.benchmark_release}`} />
    <div className="evaluation-source-grid"><SourcePanel title="Resume source" text={detail.resume_source.text} spans={detail.resume_source.spans} selectedEvidence={selectedEvidence} /><JsonPanel title="Candidate Profile" value={detail.candidate_profile} /><SourcePanel title="Job description snapshot" text={detail.job_source.text} spans={detail.job_source.spans} selectedEvidence={selectedEvidence} /><JsonPanel title="Job Profile" value={detail.job_profile} /></div>
    <section className="profile-card"><SectionHeader title="Qualification Assessment" description={`${assessments.length} requirement decisions with evidence and missing-information detail.`} /><div className="evaluation-assessments">{assessments.map((item) => <AssessmentCard key={item.requirement_id} item={item} onSelectEvidence={onSelectEvidence} />)}</div><details><summary>Generation and input-quality metadata</summary><pre className="text-preview">{JSON.stringify({ input_quality: detail.qualification.input_quality, generation: detail.qualification.generation, run: detail.run_metadata }, null, 2)}</pre></details></section>
  </section>;
}

function SourcePanel({ title, text, spans, selectedEvidence }: { title: string; text: string; spans: EvaluationEvidenceSpan[]; selectedEvidence: string }) {
  return <section className="profile-card evaluation-source"><SectionHeader title={title} description={`${spans.length} stable evidence spans`} /><pre className="text-preview large-preview">{text}</pre><details open={Boolean(selectedEvidence)}><summary>Evidence spans</summary><div className="evaluation-spans">{spans.map((span) => <article id={span.span_id} key={span.span_id} className={selectedEvidence === span.span_id ? "selected" : ""}><strong>{span.span_id}</strong><small>{span.section}</small><p>{span.excerpt}</p></article>)}</div></details></section>;
}

function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> }) {
  return <section className="profile-card"><SectionHeader title={title} description="The exact persisted structured artifact." /><pre className="text-preview large-preview">{JSON.stringify(value, null, 2)}</pre></section>;
}

function AssessmentCard({ item, onSelectEvidence }: { item: EvaluationRequirementAssessment; onSelectEvidence: (value: string) => void }) {
  return <article className="evaluation-assessment"><header><strong>{item.requirement_id}</strong><span className={`evaluation-status status-${item.status}`}>{item.status.replaceAll("_", " ")}</span><small>{Math.round(item.confidence * 100)}% confidence</small></header><p>{item.reason}</p>{item.missing.length ? <p><strong>Missing:</strong> {item.missing.join("; ")}</p> : null}<div className="evaluation-evidence-links">{item.evidence_refs.map((ref) => <button type="button" key={ref} onClick={() => { onSelectEvidence(ref); requestAnimationFrame(() => document.getElementById(ref)?.scrollIntoView({ behavior: "smooth", block: "center" })); }}>{ref}</button>)}</div></article>;
}
