"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { FileUp, FlaskConical, Play, RefreshCw, SearchCheck } from "lucide-react";
import {
  addEvaluationAnnotation,
  addEvaluationMatchReview,
  applyResumeProfileSuggestions,
  BenchmarkAdmissionReport,
  compareEvaluationRuns,
  createResumeProfile,
  createEvaluationRun,
  EvaluationAggregateMetrics,
  EvaluationAnnotation,
  EvaluationComparison,
  EvaluationDisagreementQueue,
  EvaluationEvidenceSpan,
  EvaluationFixtureCatalog,
  EvaluationJobSnapshot,
  EvaluationMatchReviewSummary,
  EvaluationRequirementAssessment,
  EvaluationRunDetail,
  EvaluationRunSummary,
  getCurrentUser,
  getAggregateEvaluationMetrics,
  getBenchmarkAdmissionReport,
  getEvaluationAdjudicationQueue,
  getEvaluationFixtureCatalog,
  getEvaluationRun,
  importEvaluationJobSnapshot,
  importResumePdf,
  listEvaluationJobSnapshots,
  listEvaluationRuns,
  listResumeProfiles,
  downloadEvaluationCorpus,
  reviewEvaluationJobSnapshot,
  ResumeProfile,
} from "../lib/api";
import { AlertBanner, Button, EmptyState, SectionHeader } from "./ui";

const DEFAULT_RELEASE = "matching-benchmark-jobs.v1";
const COVERAGE_SLOTS = [
  ["software_backend", "Backend or distributed systems"],
  ["software_infrastructure", "Infrastructure, cloud, or SRE"],
  ["software_mobile", "Mobile or client platform"],
  ["ml_data", "Machine learning or data platform"],
  ["cybersecurity_networking", "Cybersecurity or networking"],
  ["hardware_design", "Silicon, electrical, or hardware design"],
  ["embedded_firmware", "Embedded systems or firmware"],
  ["product_management", "Product Manager"],
  ["technical_program", "Technical Program Manager"],
  ["engineering_management", "Engineering Manager"],
  ["principal_architecture", "Principal, architect, or technical leader"],
] as const;
const LEVEL_BANDS = [
  ["entry_junior", "Entry or junior"], ["mid", "Mid-level"], ["senior", "Senior"],
  ["staff_principal", "Staff or principal"], ["management_leadership", "Management or leadership"],
] as const;
const DESCRIPTION_QUALITY_BANDS = [
  ["structured_high", "Structured and detailed"], ["mixed_medium", "Mixed or medium detail"],
  ["sparse_or_noisy", "Sparse or noisy"],
] as const;
const QUALIFICATION_STATUSES = [
  "met", "met_by_alternative", "partially_met", "not_demonstrated", "not_met", "needs_clarification",
];
type AnnotationPayload = Omit<
  EvaluationAnnotation,
  "public_id" | "reviewer_user_id" | "reviewer_label" | "created_at"
>;

export function MatchingEvaluationWorkbench() {
  const [blindReview] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("review") === "blind");
  const [requestedRunId] = useState(() => typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("run_id") ?? "" : "");
  const [resumes, setResumes] = useState<ResumeProfile[]>([]);
  const [snapshots, setSnapshots] = useState<EvaluationJobSnapshot[]>([]);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [aggregateMetrics, setAggregateMetrics] = useState<EvaluationAggregateMetrics | null>(null);
  const [admission, setAdmission] = useState<BenchmarkAdmissionReport | null>(null);
  const [fixtureCatalog, setFixtureCatalog] = useState<EvaluationFixtureCatalog | null>(null);
  const [disagreements, setDisagreements] = useState<EvaluationDisagreementQueue>({ items: [] });
  const [resumeId, setResumeId] = useState(0);
  const [snapshotId, setSnapshotId] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [release, setRelease] = useState(DEFAULT_RELEASE);
  const [coverageSlot, setCoverageSlot] = useState("");
  const [levelBand, setLevelBand] = useState("");
  const [descriptionQuality, setDescriptionQuality] = useState("");
  const [fixtureLabel, setFixtureLabel] = useState("");
  const [pastedResume, setPastedResume] = useState("");
  const [result, setResult] = useState<EvaluationRunDetail | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [comparisonRunId, setComparisonRunId] = useState("");
  const [comparison, setComparison] = useState<EvaluationComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState("");
  const [error, setError] = useState("");
  const selectedSnapshot = snapshots.find((snapshot) => snapshot.public_id === snapshotId) ?? null;

  const refresh = useCallback(async (activeRelease: string) => {
    const [resumePayload, snapshotPayload, runPayload, metricsPayload, admissionPayload, queuePayload, catalogPayload] = await Promise.all([
      listResumeProfiles(), listEvaluationJobSnapshots(), listEvaluationRuns(), getAggregateEvaluationMetrics(activeRelease),
      getBenchmarkAdmissionReport(activeRelease), getEvaluationAdjudicationQueue(), getEvaluationFixtureCatalog(),
    ]);
    setResumes(resumePayload.resume_profiles);
    setSnapshots(snapshotPayload.snapshots);
    setRuns(runPayload.runs);
    setAggregateMetrics(metricsPayload);
    setAdmission(admissionPayload);
    setDisagreements(queuePayload);
    setFixtureCatalog(catalogPayload);
    setResumeId((current) => current || resumePayload.resume_profiles[0]?.id || 0);
    setSnapshotId((current) => current || snapshotPayload.snapshots[0]?.public_id || "");
  }, []);

  useEffect(() => {
    getCurrentUser()
      .then(async (user) => {
        if (user.role !== "admin") throw new Error("Admin access is required.");
        await refresh(DEFAULT_RELEASE);
        if (requestedRunId) setResult(await getEvaluationRun(requestedRunId, blindReview));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load evaluation data."))
      .finally(() => setLoading(false));
  }, [blindReview, refresh, requestedRunId]);

  async function captureJob(event: FormEvent) {
    event.preventDefault();
    setWorking("capture"); setError("");
    try {
      const captured = await importEvaluationJobSnapshot({
        source_url: jobUrl, benchmark_release: release, coverage_slot: coverageSlot,
        ...(levelBand ? { level_band: levelBand as (typeof LEVEL_BANDS)[number][0] } : {}),
        ...(descriptionQuality ? {
          description_quality: descriptionQuality as (typeof DESCRIPTION_QUALITY_BANDS)[number][0],
        } : {}),
      });
      await refresh(release); setSnapshotId(captured.public_id); setJobUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not capture the job posting.");
    } finally { setWorking(""); }
  }

  async function loadResume(file: File | undefined) {
    if (!file) return;
    setWorking("resume"); setError("");
    try {
      const profile = await applyResumeProfileSuggestions(await importResumePdf(file));
      await refresh(release); setResumeId(profile.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the resume.");
    } finally { setWorking(""); }
  }

  async function loadPastedResume() {
    if (!pastedResume.trim()) return;
    setWorking("resume-paste"); setError("");
    try {
      const profile = await createResumeProfile({
        title: fixtureLabel.trim() || `Evaluation fixture ${resumes.length + 1}`,
        resume_data: {
          headline: null, summary: pastedResume.trim(), experience: [], skills: [], education: [],
          certifications: [], projects: [], awards: [], publications: [], languages: [], volunteer: [],
          target_roles: [], notes: ["Internal matching evaluation fixture"],
        },
      });
      await refresh(release); setResumeId(profile.id); setPastedResume(""); setFixtureLabel("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the pasted resume fixture.");
    } finally { setWorking(""); }
  }

  async function runEvaluation() {
    if (!resumeId || !snapshotId) return;
    setWorking("run"); setError(""); setSelectedEvidence(""); setComparison(null);
    try {
      setResult(await createEvaluationRun({
        resume_profile_id: resumeId,
        job_snapshot_id: snapshotId,
        candidate_fixture_release: fixtureCatalog?.candidate_fixture_release,
      }));
      await refresh(release);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The evaluation run failed.");
    } finally { setWorking(""); }
  }

  async function openRun(runId: string) {
    setWorking("open"); setError(""); setComparison(null);
    try { setResult(await getEvaluationRun(runId)); setSelectedEvidence(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not open the evaluation run."); }
    finally { setWorking(""); }
  }

  async function saveAnnotation(payload: AnnotationPayload) {
    if (!result) return;
    const reviewPayload = blindReview
      ? { ...payload, review_kind: "independent" as const, expected_value: null }
      : payload;
    setWorking(`annotation:${payload.target_ref}`); setError("");
    try {
      await addEvaluationAnnotation(result.public_id, reviewPayload);
      setResult(await getEvaluationRun(result.public_id, blindReview));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the annotation.");
    } finally { setWorking(""); }
  }

  async function saveMatchReview(payload: { review_kind: "independent" | "adjudication"; overall_score: number; confidence: number; rationale: string }) {
    if (!result) return;
    const reviewPayload = blindReview
      ? { ...payload, review_kind: "independent" as const }
      : payload;
    setWorking("match-review"); setError("");
    try {
      await addEvaluationMatchReview(result.public_id, reviewPayload);
      setResult(await getEvaluationRun(result.public_id, blindReview));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the human match review.");
    } finally { setWorking(""); }
  }

  async function runComparison() {
    if (!result || !comparisonRunId) return;
    setWorking("comparison"); setError("");
    try { setComparison(await compareEvaluationRuns(result.public_id, comparisonRunId)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not compare the runs."); }
    finally { setWorking(""); }
  }

  async function reviewSnapshot(reviewStatus: "accepted" | "rejected") {
    if (!selectedSnapshot) return;
    setWorking("snapshot-review"); setError("");
    try {
      await reviewEvaluationJobSnapshot(selectedSnapshot.public_id, {
        review_status: reviewStatus,
        review_notes: reviewStatus === "accepted"
          ? "Reviewed for official source, completeness, and assigned coverage slot."
          : "Rejected during benchmark admission review.",
      });
      await refresh(release);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not review the snapshot.");
    } finally { setWorking(""); }
  }

  async function exportCorpus(format: "json" | "markdown") {
    setWorking(`export:${format}`); setError("");
    try { await downloadEvaluationCorpus(format); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not export the corpus."); }
    finally { setWorking(""); }
  }

  if (loading) return <p>Loading evaluation workbench…</p>;
  if (blindReview) {
    const blindResult = result ? {
      ...result,
      annotations: [],
      metrics: {
        ...result.metrics,
        annotation_count: 0,
        adjudicated_count: 0,
        positive_evidence_support_precision: null,
        positive_evidence_support_counts: { supported: 0, reviewed: 0 },
        qualification_confusion_matrix: {},
      },
    } : null;
    return <div className="evaluation-workbench">
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <AlertBanner tone="info">Blind independent review: expected match categories, aggregate results, comparisons, prior reviews, and adjudication outcomes are hidden.</AlertBanner>
      {blindResult ? <EvaluationResult detail={blindResult} selectedEvidence={selectedEvidence} annotatingTarget={working.startsWith("annotation:") ? working.slice(11) : ""} onSelectEvidence={setSelectedEvidence} onAnnotate={saveAnnotation} onMatchReview={saveMatchReview} matchReviewSaving={working === "match-review"} blindReview /> : <EmptyState icon={FlaskConical} title="Review run unavailable" description="Open a valid blind-review link containing a canonical run ID." />}
    </div>;
  }
  return <div className="evaluation-workbench">
    {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
    <section className="evaluation-setup-grid">
      <form className="profile-card" onSubmit={captureJob}>
        <SectionHeader title="1. Freeze a job posting" description="The server fetches and stores an immutable JD snapshot for repeatable tests." />
        <label>Job URL<input type="url" required value={jobUrl} onChange={(event) => setJobUrl(event.target.value)} placeholder="https://company.com/jobs/123" /></label>
        <label>Benchmark release<input required value={release} onChange={(event) => setRelease(event.target.value)} /></label>
        <label>Coverage slot<select required value={coverageSlot} onChange={(event) => setCoverageSlot(event.target.value)}><option value="">Select a role family</option>{COVERAGE_SLOTS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
        {release.startsWith("matching-benchmark-jobs.e3") ? <>
          <label>Level band<select required value={levelBand} onChange={(event) => setLevelBand(event.target.value)}><option value="">Select a level band</option>{LEVEL_BANDS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
          <label>Description quality<select required value={descriptionQuality} onChange={(event) => setDescriptionQuality(event.target.value)}><option value="">Classify the frozen JD</option>{DESCRIPTION_QUALITY_BANDS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
        </> : null}
        <Button type="submit" icon={SearchCheck} loading={working === "capture"}>Fetch and freeze</Button>
      </form>
      <section className="profile-card">
        <SectionHeader title="2. Choose a resume" description="Use an existing profile or load a PDF fixture into your profile library." />
        <label>Resume profile<select value={resumeId} onChange={(event) => setResumeId(Number(event.target.value))}><option value={0}>Select a resume</option>{resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title}</option>)}</select></label>
        <label className="evaluation-file-button"><FileUp size={18} aria-hidden="true" /><span>{working === "resume" ? "Loading resume…" : "Load resume PDF"}</span><input type="file" accept="application/pdf,.pdf" disabled={Boolean(working)} onChange={(event) => void loadResume(event.target.files?.[0])} /></label>
        <details><summary>Or paste a de-identified fixture</summary><div className="evaluation-paste-fixture"><label>Fixture label<input value={fixtureLabel} onChange={(event) => setFixtureLabel(event.target.value)} placeholder="Synthetic senior backend candidate" /></label><label>Resume text<textarea rows={6} value={pastedResume} onChange={(event) => setPastedResume(event.target.value)} placeholder="Paste the complete de-identified resume. More detail produces a better evaluation fixture." /></label><Button type="button" size="compact" loading={working === "resume-paste"} disabled={!pastedResume.trim()} onClick={() => void loadPastedResume()}>Load pasted fixture</Button></div></details>
      </section>
      <section className="profile-card">
        <SectionHeader title="3. Run the three stages" description="Creates or reuses the exact V2 Candidate Profile, Job Profile, and Qualification Assessment." />
        <label>Frozen job<select value={snapshotId} onChange={(event) => setSnapshotId(event.target.value)}><option value="">Select a snapshot</option>{snapshots.map((snapshot) => <option key={snapshot.public_id} value={snapshot.public_id}>{snapshot.company ? `${snapshot.company} — ` : ""}{snapshot.title || snapshot.coverage_slot || snapshot.public_id}</option>)}</select></label>
        <Button type="button" icon={Play} loading={working === "run"} disabled={!resumeId || !snapshotId || selectedSnapshot?.review_status !== "accepted"} onClick={() => void runEvaluation()}>Run evaluation now</Button>
        {selectedSnapshot && selectedSnapshot.review_status !== "accepted" ? <small>Accept this snapshot into the benchmark before running it.</small> : null}
        <small>No weighted score is generated; this evaluates the first three stages only.</small>
      </section>
    </section>
    {fixtureCatalog ? <FixtureLibrary
      catalog={fixtureCatalog}
      resumes={resumes}
      snapshots={snapshots}
      resumeId={resumeId}
      snapshotId={snapshotId}
      onSelectCandidate={setResumeId}
      onSelectJob={setSnapshotId}
      onSelectPair={(candidateId, jobId) => { setResumeId(candidateId); setSnapshotId(jobId); setResult(null); }}
    /> : null}
    {selectedSnapshot ? <SnapshotReview snapshot={selectedSnapshot} loading={working === "snapshot-review"} onReview={reviewSnapshot} /> : null}
    {admission ? <AdmissionReport report={admission} /> : null}
    {aggregateMetrics ? <AggregateMetrics metrics={aggregateMetrics} /> : null}
    <section className="profile-card evaluation-export"><SectionHeader title="Corpus export" description="Candidate contact details and URLs are redacted; complete job snapshots remain internal-testing data." /><div className="button-row"><Button type="button" variant="secondary" loading={working === "export:json"} onClick={() => void exportCorpus("json")}>Export JSON</Button><Button type="button" variant="secondary" loading={working === "export:markdown"} onClick={() => void exportCorpus("markdown")}>Export Markdown</Button></div></section>
    <AdjudicationQueue queue={disagreements} onOpen={openRun} />
    {runs.length ? <RunHistory runs={runs} onOpen={openRun} /> : null}
    {result ? <>
      <RunComparison currentRunId={result.public_id} runs={runs} selectedRunId={comparisonRunId} comparison={comparison} loading={working === "comparison"} onSelect={setComparisonRunId} onCompare={runComparison} />
      <EvaluationResult detail={result} selectedEvidence={selectedEvidence} annotatingTarget={working.startsWith("annotation:") ? working.slice(11) : ""} onSelectEvidence={setSelectedEvidence} onAnnotate={saveAnnotation} onMatchReview={saveMatchReview} matchReviewSaving={working === "match-review"} />
    </> : <EmptyState icon={FlaskConical} title="No evaluation selected" description="Choose a resume and frozen job, then run the three-stage pipeline." />}
  </div>;
}

function FixtureLibrary({ catalog, resumes, snapshots, resumeId, snapshotId, onSelectCandidate, onSelectJob, onSelectPair }: {
  catalog: EvaluationFixtureCatalog;
  resumes: ResumeProfile[];
  snapshots: EvaluationJobSnapshot[];
  resumeId: number;
  snapshotId: string;
  onSelectCandidate: (id: number) => void;
  onSelectJob: (id: string) => void;
  onSelectPair: (candidateId: number, jobId: string) => void;
}) {
  const selectedResume = resumes.find((resume) => resume.id === resumeId) ?? null;
  const selectedJob = snapshots.find((snapshot) => snapshot.public_id === snapshotId) ?? null;
  const acceptedJobs = snapshots.filter((snapshot) =>
    snapshot.benchmark_release === catalog.benchmark_release && snapshot.review_status === "accepted"
  );
  const candidateLabels = new Map(catalog.candidates.map((candidate) => [candidate.fixture_id, candidate.label]));
  const jobsById = new Map(snapshots.map((snapshot) => [snapshot.public_id, snapshot]));

  return <section className="profile-card evaluation-fixture-library">
    <SectionHeader title="Manual pilot test inputs" description={`${catalog.candidates.length} candidate fixtures · ${acceptedJobs.length} accepted jobs · ${catalog.pairs.length} suggested diagnostic pairs. Selecting inputs never starts a run.`} />
    <div className="evaluation-library-grid">
      <section>
        <h3>Candidate fixtures</h3>
        <div className="evaluation-library-list">
          {catalog.candidates.map((candidate) => <article key={candidate.fixture_id} className={candidate.resume_profile_id === resumeId ? "selected" : ""}>
            <div><strong>{candidate.label}</strong><small>{candidate.fixture_id} · {candidate.coverage.career_stage} · {candidate.coverage.role_family.replaceAll("_", " ")}</small>{candidate.intended_failure_modes.length ? <small>Tests: {candidate.intended_failure_modes.join(", ").replaceAll("_", " ")}</small> : null}</div>
            <Button type="button" size="compact" variant="secondary" disabled={!candidate.loaded || candidate.resume_profile_id === null} onClick={() => candidate.resume_profile_id && onSelectCandidate(candidate.resume_profile_id)}>{candidate.resume_profile_id === resumeId ? "Selected" : candidate.loaded ? "Select" : "Not loaded"}</Button>
          </article>)}
        </div>
      </section>
      <section>
        <h3>Accepted benchmark jobs</h3>
        <div className="evaluation-library-list">
          {acceptedJobs.map((job) => <article key={job.public_id} className={job.public_id === snapshotId ? "selected" : ""}>
            <div><strong>{job.company ? `${job.company} — ` : ""}{job.title}</strong><small>{job.coverage_slot.replaceAll("_", " ")} · {job.public_id}</small></div>
            <Button type="button" size="compact" variant="secondary" onClick={() => onSelectJob(job.public_id)}>{job.public_id === snapshotId ? "Selected" : "Select"}</Button>
          </article>)}
        </div>
      </section>
    </div>
    <div className="evaluation-source-grid evaluation-input-preview">
      <section><h3>Selected resume fixture</h3>{selectedResume ? <><strong>{selectedResume.title}</strong><p><small>The generated Candidate Profile will appear only after a manual run.</small></p><pre className="text-preview large-preview">{JSON.stringify(selectedResume.resume_data, null, 2)}</pre></> : <p>Select a candidate to inspect its resume.</p>}</section>
      <section><h3>Selected frozen job description</h3>{selectedJob ? <><strong>{selectedJob.company ? `${selectedJob.company} — ` : ""}{selectedJob.title}</strong><p><small>{selectedJob.coverage_slot.replaceAll("_", " ")} · {selectedJob.review_status}</small></p><pre className="text-preview large-preview">{selectedJob.raw_description_text}</pre></> : <p>Select a job to inspect its frozen description.</p>}</section>
    </div>
    <details>
      <summary>Suggested diagnostic pairs ({catalog.pairs.length})</summary>
      <p><small>These strong, adjacent, and mismatch expectations were assigned before any matcher results. Choosing a pair only fills the two selectors.</small></p>
      <div className="evaluation-pair-list">
        {catalog.pairs.map((pair) => {
          const job = pair.job_snapshot_id ? jobsById.get(pair.job_snapshot_id) : null;
          return <article key={pair.pair_id}>
            <div><strong>{pair.expectation.replaceAll("_", " ")}</strong><span>{candidateLabels.get(pair.candidate_fixture_id) ?? pair.candidate_fixture_id} ↔ {job ? `${job.company} — ${job.title}` : pair.coverage_slot.replaceAll("_", " ")}</span><small>{pair.rationale}</small></div>
            <Button type="button" size="compact" variant="secondary" disabled={!pair.available || pair.resume_profile_id === null || pair.job_snapshot_id === null} onClick={() => pair.resume_profile_id && pair.job_snapshot_id && onSelectPair(pair.resume_profile_id, pair.job_snapshot_id)}>Choose pair</Button>
          </article>;
        })}
      </div>
    </details>
  </section>;
}

function SnapshotReview({ snapshot, loading, onReview }: { snapshot: EvaluationJobSnapshot; loading: boolean; onReview: (status: "accepted" | "rejected") => Promise<void> }) {
  return <section className="profile-card"><SectionHeader title="Snapshot admission" description={`${snapshot.company || "Unknown company"} — ${snapshot.title || snapshot.coverage_slot}`} /><p><strong>Status:</strong> {snapshot.review_status} · <strong>Source confidence:</strong> {String(snapshot.capture_metadata.confidence ?? "unknown")}</p>{snapshot.benchmark_release.startsWith("matching-benchmark-jobs.e3") ? <p><strong>Level:</strong> {String(snapshot.capture_metadata.level_band).replaceAll("_", " ")} · <strong>JD quality:</strong> {String(snapshot.capture_metadata.description_quality).replaceAll("_", " ")} · <strong>ATS:</strong> {String(snapshot.capture_metadata.ats_family)}</p> : null}<p>{snapshot.raw_description_text.slice(0, 600)}{snapshot.raw_description_text.length > 600 ? "…" : ""}</p>{snapshot.capture_metadata.warnings instanceof Array && snapshot.capture_metadata.warnings.length ? <AlertBanner tone="warning">Extraction warnings: {snapshot.capture_metadata.warnings.join(", ")}</AlertBanner> : null}<div className="button-row"><Button type="button" loading={loading} onClick={() => void onReview("accepted")}>Accept snapshot</Button><Button type="button" variant="danger" loading={loading} onClick={() => void onReview("rejected")}>Reject snapshot</Button></div></section>;
}

function AdmissionReport({ report }: { report: BenchmarkAdmissionReport }) {
  return <section className="profile-card"><SectionHeader title={report.benchmark_release.startsWith("matching-benchmark-jobs.e3") ? "E3 coverage admission" : "Pilot coverage admission"} description={`${report.accepted_count} accepted · ${report.draft_count} awaiting review · ${report.rejected_count} rejected`} /><div className="evaluation-coverage-grid">{report.slots.map((slot) => <article key={slot.code} className={`coverage-${slot.status}`}><strong>{slot.label}</strong><span>{slot.status.replaceAll("_", " ")}</span></article>)}</div>{report.balance_violations.length ? <AlertBanner tone="warning">Balance checks: {report.balance_violations.join(", ")}</AlertBanner> : null}<small>Storage policy: {report.storage_policy}</small></section>;
}

function AdjudicationQueue({ queue, onOpen }: { queue: EvaluationDisagreementQueue; onOpen: (id: string) => Promise<void> }) {
  const pending = queue.items.filter((item) => item.status === "pending");
  return <section className="profile-card"><SectionHeader title="Adjudication queue" description={`${pending.length} pending reviewer disagreements`} />{queue.items.length ? <div className="evaluation-disagreement-list">{queue.items.map((item) => <article key={`${item.run_id}:${item.stage}:${item.target_ref}`}><header><strong>{item.target_ref}</strong><span>{item.status}</span></header><p>{item.stage} · {item.reviews.map((review) => `${review.reviewer_label}: ${review.verdict}/${review.evidence_support}`).join(" · ")}</p><Button type="button" size="compact" variant="secondary" onClick={() => void onOpen(item.run_id)}>Open run</Button></article>)}</div> : <p>No reviewer disagreements yet.</p>}</section>;
}

function AggregateMetrics({ metrics }: { metrics: EvaluationAggregateMetrics }) {
  return <section className="profile-card"><SectionHeader title="Benchmark overview" description={`${metrics.run_count} persisted runs · ${metrics.annotation_count} reviews · ${metrics.severe_error_count} severe errors`} /><div className="evaluation-metric-grid">{Object.entries(metrics.contract_pass_counts).map(([name, counts]) => <article key={name} className={counts.passed === counts.total ? "passed" : "failed"}><strong>{name.replaceAll("_", " ")}</strong><span>{counts.passed}/{counts.total} runs pass</span></article>)}<article><strong>Positive evidence support</strong><span>{metrics.positive_evidence_support_precision === null ? "Awaiting adjudication" : `${Math.round(metrics.positive_evidence_support_precision * 100)}%`}</span><small>{metrics.positive_evidence_support_counts.supported}/{metrics.positive_evidence_support_counts.reviewed} reviewed positives</small></article></div></section>;
}

function RunHistory({ runs, onOpen }: { runs: EvaluationRunSummary[]; onOpen: (id: string) => Promise<void> }) {
  return <section className="profile-card evaluation-history"><SectionHeader title="Recent runs" description="Open a persisted run without calling providers again." /><div className="evaluation-run-links">{runs.slice(0, 10).map((run) => <button type="button" key={run.public_id} onClick={() => void onOpen(run.public_id)}><RefreshCw size={14} />{new Date(run.created_at).toLocaleString()} · {run.public_id}</button>)}</div></section>;
}

function RunComparison({ currentRunId, runs, selectedRunId, comparison, loading, onSelect, onCompare }: { currentRunId: string; runs: EvaluationRunSummary[]; selectedRunId: string; comparison: EvaluationComparison | null; loading: boolean; onSelect: (id: string) => void; onCompare: () => Promise<void> }) {
  return <section className="profile-card evaluation-compare"><SectionHeader title="Compare frozen runs" description="Changed source snapshots are reported as incompatible rather than as model-only changes." /><div className="evaluation-compare-controls"><select value={selectedRunId} onChange={(event) => onSelect(event.target.value)}><option value="">Select another run</option>{runs.filter((run) => run.public_id !== currentRunId).map((run) => <option key={run.public_id} value={run.public_id}>{new Date(run.created_at).toLocaleString()} · {run.public_id}</option>)}</select><Button type="button" variant="secondary" loading={loading} disabled={!selectedRunId} onClick={() => void onCompare()}>Compare</Button></div>{comparison ? <div className={`evaluation-comparison-result ${comparison.comparable ? "compatible" : "incompatible"}`}><strong>{comparison.comparable ? "Comparable frozen inputs" : "Inputs are not comparable"}</strong>{comparison.incompatibilities.length ? <p>{comparison.incompatibilities.join(", ")}</p> : null}<p>{comparison.qualification_changes.length} qualification changes · Candidate Profile {comparison.candidate_profile_changed ? "changed" : "unchanged"} · Job Profile {comparison.job_profile_changed ? "changed" : "unchanged"}</p><details><summary>Version and artifact differences</summary><pre className="text-preview">{JSON.stringify(comparison, null, 2)}</pre></details></div> : null}</section>;
}

function EvaluationResult({ detail, selectedEvidence, annotatingTarget, onSelectEvidence, onAnnotate, onMatchReview, matchReviewSaving, blindReview = false }: { detail: EvaluationRunDetail; selectedEvidence: string; annotatingTarget: string; onSelectEvidence: (value: string) => void; onAnnotate: (payload: AnnotationPayload) => Promise<void>; onMatchReview: (payload: { review_kind: "independent" | "adjudication"; overall_score: number; confidence: number; rationale: string }) => Promise<void>; matchReviewSaving: boolean; blindReview?: boolean }) {
  const assessments = useMemo(() => [
    ...(detail.qualification.assessment.hard_constraint_assessments ?? []),
    ...detail.qualification.assessment.requirement_assessments,
  ], [detail]);
  return <section className="evaluation-result">
    <SectionHeader title={`${detail.resume_title} ↔ ${detail.job_company ? `${detail.job_company} ` : ""}${detail.job_title}`} description={`Run ${detail.public_id} · ${detail.benchmark_release}`} />
    <MetricsSummary detail={detail} />
    <div className="evaluation-source-grid"><SourcePanel title="Resume source" text={detail.resume_source.text} spans={detail.resume_source.spans} selectedEvidence={selectedEvidence} /><JsonPanel title="Candidate Profile" value={detail.candidate_profile} /><SourcePanel title="Job description snapshot" text={detail.job_source.text} spans={detail.job_source.spans} selectedEvidence={selectedEvidence} /><JsonPanel title="Job Profile" value={detail.job_profile} /></div>
    <div className="evaluation-source-grid"><ArtifactReviewPanel title="Candidate Profile fact review" stage="candidate_profile" targets={detail.annotation_targets.filter((target) => target.stage === "candidate_profile")} annotations={detail.annotations} annotatingTarget={annotatingTarget} onSelectEvidence={onSelectEvidence} onAnnotate={onAnnotate} /><ArtifactReviewPanel title="Job Profile fact review" stage="job_profile" targets={detail.annotation_targets.filter((target) => target.stage === "job_profile")} annotations={detail.annotations} annotatingTarget={annotatingTarget} onSelectEvidence={onSelectEvidence} onAnnotate={onAnnotate} /></div>
    <section className="profile-card"><SectionHeader title="Qualification Assessment" description={`${assessments.length} requirement decisions with evidence and reviewer labels.`} /><div className="evaluation-assessments">{assessments.map((item) => <AssessmentCard key={item.requirement_id} item={item} annotations={detail.annotations.filter((annotation) => annotation.stage === "qualification" && annotation.target_ref === item.requirement_id)} saving={annotatingTarget === item.requirement_id} onSelectEvidence={onSelectEvidence} onAnnotate={onAnnotate} />)}</div><details><summary>Run manifest and generation metadata</summary><pre className="text-preview">{JSON.stringify({ manifest: detail.manifest, input_quality: detail.qualification.input_quality, generation: detail.qualification.generation, run: detail.run_metadata }, null, 2)}</pre></details></section>
    <HumanMatchReview summary={detail.match_review} saving={matchReviewSaving} independentOnly={blindReview} onSubmit={onMatchReview} />
  </section>;
}

function HumanMatchReview({ summary, saving, independentOnly, onSubmit }: { summary: EvaluationMatchReviewSummary; saving: boolean; independentOnly: boolean; onSubmit: (payload: { review_kind: "independent" | "adjudication"; overall_score: number; confidence: number; rationale: string }) => Promise<void> }) {
  const [reviewKind, setReviewKind] = useState<"independent" | "adjudication">("independent");
  const [score, setScore] = useState(50);
  const [confidence, setConfidence] = useState(0.75);
  const [rationale, setRationale] = useState("");
  const recommendation = score >= 85 ? "strong match" : score >= 70 ? "good match" : score >= 55 ? "consider" : score >= 40 ? "stretch" : "unlikely fit";
  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSubmit({ review_kind: independentOnly ? "independent" : reviewKind, overall_score: score, confidence, rationale });
    setRationale("");
  }
  return <section className="profile-card evaluation-human-match-review">
    <SectionHeader title="Human match review" description="Compare the Candidate Profile with the Job Profile and submit your overall 0–100 assessment. This score is human QA data, not the model score." />
    {summary.reviews.length ? <div className="evaluation-review-list">{summary.reviews.map((review) => <p key={review.public_id}><strong>{review.review_kind}:</strong> {review.overall_score}/100 · {review.recommendation.replaceAll("_", " ")} · {review.reviewer_label}</p>)}</div> : <p>No visible human match score has been submitted for this reviewer.</p>}
    <form className="evaluation-annotation-form" onSubmit={submit}>
      {!independentOnly ? <label>Review type<select value={reviewKind} onChange={(event) => setReviewKind(event.target.value as typeof reviewKind)}><option value="independent">Independent review</option><option value="adjudication">Adjudicated golden score</option></select></label> : null}
      <label>Overall match score<input type="number" min={0} max={100} required value={score} onChange={(event) => setScore(Math.max(0, Math.min(100, Number(event.target.value))))} /></label>
      <p><strong>Score interpretation:</strong> {recommendation}</p>
      <label>Confidence<select value={confidence} onChange={(event) => setConfidence(Number(event.target.value))}><option value={0.5}>Low (50%)</option><option value={0.75}>Medium (75%)</option><option value={1}>High (100%)</option></select></label>
      <label className="evaluation-comment">Rationale<textarea required minLength={1} maxLength={4000} rows={4} value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Explain the strongest evidence, material gaps, and why this score is appropriate." /></label>
      <Button type="submit" loading={saving}>Submit human match score</Button>
    </form>
    <small>Review state: {summary.state.replaceAll("_", " ")} · {summary.independent_reviewer_count}/2 independent reviewers</small>
  </section>;
}

function ArtifactReviewPanel({ title, stage, targets, annotations, annotatingTarget, onSelectEvidence, onAnnotate }: { title: string; stage: "candidate_profile" | "job_profile"; targets: EvaluationRunDetail["annotation_targets"]; annotations: EvaluationAnnotation[]; annotatingTarget: string; onSelectEvidence: (value: string) => void; onAnnotate: (payload: AnnotationPayload) => Promise<void> }) {
  return <section className="profile-card"><SectionHeader title={title} description={`${targets.length} independently reviewable generated facts`} /><div className="evaluation-fact-list">{targets.map((target) => <FactReviewCard key={target.target_ref} stage={stage} target={target} annotations={annotations.filter((annotation) => annotation.stage === stage && annotation.target_ref === target.target_ref)} saving={annotatingTarget === target.target_ref} onSelectEvidence={onSelectEvidence} onAnnotate={onAnnotate} />)}</div></section>;
}

function FactReviewCard({ stage, target, annotations, saving, onSelectEvidence, onAnnotate }: { stage: "candidate_profile" | "job_profile"; target: EvaluationRunDetail["annotation_targets"][number]; annotations: EvaluationAnnotation[]; saving: boolean; onSelectEvidence: (value: string) => void; onAnnotate: (payload: AnnotationPayload) => Promise<void> }) {
  const [reviewKind, setReviewKind] = useState<"independent" | "adjudication">("independent");
  const [verdict, setVerdict] = useState<AnnotationPayload["verdict"]>("correct");
  const [evidenceSupport, setEvidenceSupport] = useState<AnnotationPayload["evidence_support"]>("supported");
  const [severity, setSeverity] = useState<AnnotationPayload["severity"]>("none");
  const [comment, setComment] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    await onAnnotate({ stage, target_ref: target.target_ref, review_kind: reviewKind, verdict, evidence_support: evidenceSupport, expected_value: reviewKind === "adjudication" ? { verdict } : null, confidence: 1, severity, error_taxonomy_code: verdict === "correct" ? null : `${stage}.review_error`, comment });
    setComment("");
  }
  return <article className="evaluation-fact"><strong>{target.label}</strong><pre>{JSON.stringify(target.value, null, 2)}</pre><div className="evaluation-evidence-links">{target.evidence_refs.map((ref) => <button type="button" key={ref} onClick={() => { onSelectEvidence(ref); requestAnimationFrame(() => document.getElementById(ref)?.scrollIntoView({ behavior: "smooth", block: "center" })); }}>{ref}</button>)}</div>{annotations.map((annotation) => <p key={annotation.public_id}><strong>{annotation.review_kind}:</strong> {annotation.verdict}/{annotation.evidence_support} · {annotation.reviewer_label}</p>)}<details><summary>Review fact</summary><form className="evaluation-fact-form" onSubmit={submit}><label>Review<select value={reviewKind} onChange={(event) => setReviewKind(event.target.value as typeof reviewKind)}><option value="independent">Independent</option><option value="adjudication">Adjudication</option></select></label><label>Verdict<select value={verdict} onChange={(event) => setVerdict(event.target.value as typeof verdict)}><option value="correct">Correct</option><option value="partially_correct">Partially correct</option><option value="incorrect">Incorrect</option><option value="missing">Missing</option><option value="ambiguous">Ambiguous</option></select></label><label>Evidence<select value={evidenceSupport} onChange={(event) => setEvidenceSupport(event.target.value as typeof evidenceSupport)}><option value="supported">Supported</option><option value="partially_supported">Partially supported</option><option value="unsupported">Unsupported</option><option value="ambiguous">Ambiguous</option><option value="not_reviewed">Not reviewed</option></select></label><label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="none">None</option><option value="minor">Minor</option><option value="major">Major</option><option value="severe">Severe</option></select></label><label className="evaluation-comment">Comment<textarea rows={2} value={comment} onChange={(event) => setComment(event.target.value)} /></label><Button type="submit" size="compact" loading={saving}>Save review</Button></form></details></article>;
}

function MetricsSummary({ detail }: { detail: EvaluationRunDetail }) {
  const metrics = detail.metrics;
  return <section className="profile-card"><SectionHeader title="Evaluation checks" description={`${metrics.annotation_count} reviews · ${metrics.adjudicated_count} adjudicated`} /><div className="evaluation-metric-grid">{metrics.contract_metrics.map((metric) => <article key={metric.name} className={metric.passed ? "passed" : "failed"}><strong>{metric.name.replaceAll("_", " ")}</strong><span>{metric.passed ? "Pass" : "Fail"}</span><small>{metric.numerator}/{metric.denominator}{metric.details.length ? ` · ${metric.details.join(", ")}` : ""}</small></article>)}</div><p>Positive evidence support: {metrics.positive_evidence_support_precision === null ? "Awaiting adjudicated reviews" : `${Math.round(metrics.positive_evidence_support_precision * 100)}% (${metrics.positive_evidence_support_counts.supported}/${metrics.positive_evidence_support_counts.reviewed})`}</p></section>;
}

function SourcePanel({ title, text, spans, selectedEvidence }: { title: string; text: string; spans: EvaluationEvidenceSpan[]; selectedEvidence: string }) {
  return <section className="profile-card evaluation-source"><SectionHeader title={title} description={`${spans.length} stable evidence spans`} /><pre className="text-preview large-preview">{text}</pre><details open={Boolean(selectedEvidence)}><summary>Evidence spans</summary><div className="evaluation-spans">{spans.map((span) => <article id={span.span_id} key={span.span_id} className={selectedEvidence === span.span_id ? "selected" : ""}><strong>{span.span_id}</strong><small>{span.section}</small><p>{span.excerpt}</p></article>)}</div></details></section>;
}

function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> }) {
  return <section className="profile-card"><SectionHeader title={title} description="The exact persisted structured artifact." /><pre className="text-preview large-preview">{JSON.stringify(value, null, 2)}</pre></section>;
}

function AssessmentCard({ item, annotations, saving, onSelectEvidence, onAnnotate }: { item: EvaluationRequirementAssessment; annotations: EvaluationAnnotation[]; saving: boolean; onSelectEvidence: (value: string) => void; onAnnotate: (payload: AnnotationPayload) => Promise<void> }) {
  const [reviewKind, setReviewKind] = useState<"independent" | "adjudication">("independent");
  const [verdict, setVerdict] = useState<AnnotationPayload["verdict"]>("correct");
  const [evidenceSupport, setEvidenceSupport] = useState<AnnotationPayload["evidence_support"]>("supported");
  const [expectedStatus, setExpectedStatus] = useState(item.status);
  const [severity, setSeverity] = useState<AnnotationPayload["severity"]>("none");
  const [errorCode, setErrorCode] = useState("");
  const [comment, setComment] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onAnnotate({
      stage: "qualification", target_ref: item.requirement_id, review_kind: reviewKind,
      verdict, evidence_support: evidenceSupport,
      expected_value: reviewKind === "adjudication" ? { status: expectedStatus } : null,
      confidence: 1, severity, error_taxonomy_code: errorCode || null, comment,
    });
    setComment("");
  }

  return <article className="evaluation-assessment"><header><strong>{item.requirement_id}</strong><span className={`evaluation-status status-${item.status}`}>{item.status.replaceAll("_", " ")}</span><small>{Math.round(item.confidence * 100)}% confidence</small></header><p>{item.reason}</p>{item.missing.length ? <p><strong>Missing:</strong> {item.missing.join("; ")}</p> : null}<div className="evaluation-evidence-links">{item.evidence_refs.map((ref) => <button type="button" key={ref} onClick={() => { onSelectEvidence(ref); requestAnimationFrame(() => document.getElementById(ref)?.scrollIntoView({ behavior: "smooth", block: "center" })); }}>{ref}</button>)}</div>{annotations.length ? <div className="evaluation-review-list">{annotations.map((annotation) => <p key={annotation.public_id}><strong>{annotation.review_kind}:</strong> {annotation.verdict}, evidence {annotation.evidence_support} · {annotation.reviewer_label}{annotation.comment ? ` — ${annotation.comment}` : ""}</p>)}</div> : null}<details><summary>Add reviewer annotation</summary><form className="evaluation-annotation-form" onSubmit={submit}><label>Review type<select value={reviewKind} onChange={(event) => setReviewKind(event.target.value as typeof reviewKind)}><option value="independent">Independent review</option><option value="adjudication">Adjudicated golden label</option></select></label><label>Verdict<select value={verdict} onChange={(event) => setVerdict(event.target.value as typeof verdict)}><option value="correct">Correct</option><option value="partially_correct">Partially correct</option><option value="incorrect">Incorrect</option><option value="missing">Missing</option><option value="ambiguous">Ambiguous</option></select></label><label>Evidence support<select value={evidenceSupport} onChange={(event) => setEvidenceSupport(event.target.value as typeof evidenceSupport)}><option value="supported">Supported</option><option value="partially_supported">Partially supported</option><option value="unsupported">Unsupported</option><option value="ambiguous">Ambiguous</option><option value="not_reviewed">Not reviewed</option></select></label>{reviewKind === "adjudication" ? <label>Golden status<select value={expectedStatus} onChange={(event) => setExpectedStatus(event.target.value)}>{QUALIFICATION_STATUSES.map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label> : null}<label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value as typeof severity)}><option value="none">None</option><option value="minor">Minor</option><option value="major">Major</option><option value="severe">Severe</option></select></label><label>Error code<input value={errorCode} onChange={(event) => setErrorCode(event.target.value)} placeholder="evidence.unsupported" /></label><label className="evaluation-comment">Comment<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={2} /></label><Button type="submit" size="compact" loading={saving}>Save annotation</Button></form></details></article>;
}
