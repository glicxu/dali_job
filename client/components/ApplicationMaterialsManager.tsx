"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ApplicationMaterial, ApplicationMaterialVersion, CoverLetterContent, generateCoverLetter,
  generateTailoredResume, getAuthToken, listApplicationMaterials, listApplications, listDocuments,
  reviseApplicationMaterial, StoredDocument, TailoredResumeContent, TrackedApplication,
} from "../lib/api";

type MaterialKind = "tailored_resume" | "cover_letter";

function isTailoredResume(content: object): content is TailoredResumeContent {
  return "experience" in content && "tailoring_notes" in content;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

export function ApplicationMaterialsManager() {
  if (!getAuthToken()) {
    return <section className="material-empty panel-card"><h2>Application materials workspace</h2><p>Login is required to generate materials and access private resume and application data.</p><a className="button-link" href="/auth">Login or Register</a></section>;
  }
  return <AuthenticatedMaterialsManager />;
}

function AuthenticatedMaterialsManager() {
  const [applications, setApplications] = useState<TrackedApplication[]>([]);
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [materials, setMaterials] = useState<ApplicationMaterial[]>([]);
  const [applicationId, setApplicationId] = useState("");
  const [documentVersionId, setDocumentVersionId] = useState("");
  const [kind, setKind] = useState<MaterialKind>("tailored_resume");
  const [sourceMaterialVersionId, setSourceMaterialVersionId] = useState("");
  const [notes, setNotes] = useState("");
  const [selectedMaterialId, setSelectedMaterialId] = useState<number | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [revisionText, setRevisionText] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const resumeVersions = useMemo(() => documents.filter((document) => document.document_type === "resume")
    .flatMap((document) => document.versions.map((version) => ({ document, version }))), [documents]);
  const tailoredVersions = useMemo(() => materials
    .filter((material) => material.material_type === "tailored_resume" && (!applicationId || material.application_id === Number(applicationId)))
    .flatMap((material) => material.versions.filter((version) => version.content_data).map((version) => ({ material, version }))), [materials, applicationId]);
  const selectedMaterial = materials.find((material) => material.id === selectedMaterialId) || null;
  const selectedVersion = selectedMaterial?.versions.find((version) => version.id === selectedVersionId) || selectedMaterial?.versions[0] || null;

  async function load() {
    setError(null);
    try {
      const [applicationPayload, documentPayload, materialPayload] = await Promise.all([
        listApplications({ includeArchived: true }), listDocuments(), listApplicationMaterials(),
      ]);
      setApplications(applicationPayload);
      setDocuments(documentPayload.documents);
      setMaterials(materialPayload.materials);
      if (!applicationId && applicationPayload.length) setApplicationId(String(applicationPayload[0].id));
      if (!documentVersionId) {
        const resume = documentPayload.documents.find((document) => document.document_type === "resume" && document.versions.length);
        if (resume) setDocumentVersionId(String(resume.versions[0].id));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load application materials.");
    }
  }

  useEffect(() => { void load(); }, []);

  function selectMaterial(material: ApplicationMaterial) {
    setSelectedMaterialId(material.id);
    setSelectedVersionId(material.versions[0]?.id || null);
    setEditing(false);
  }

  async function handleGenerate(event: FormEvent) {
    event.preventDefault();
    if (!applicationId || !documentVersionId) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const payload = { application_id: Number(applicationId), source_document_version_id: Number(documentVersionId), target_notes: notes.trim() || undefined };
      const generated = kind === "tailored_resume" ? await generateTailoredResume(payload) : await generateCoverLetter({ ...payload, source_material_version_id: sourceMaterialVersionId ? Number(sourceMaterialVersionId) : undefined });
      await load();
      setSelectedMaterialId(generated.id);
      setSelectedVersionId(generated.versions[0]?.id || null);
      setMessage(`${kind === "tailored_resume" ? "Tailored resume" : "Cover letter"} generated as version ${generated.versions[0]?.version_number}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate application material.");
    } finally { setBusy(false); }
  }

  function beginRevision() {
    if (!selectedVersion?.content_data) return;
    setRevisionText(JSON.stringify(selectedVersion.content_data, null, 2));
    setEditing(true);
  }

  async function saveRevision() {
    if (!selectedMaterial || !selectedVersion) return;
    setBusy(true); setError(null);
    try {
      const updated = await reviseApplicationMaterial(selectedMaterial.id, selectedVersion.id, JSON.parse(revisionText) as Record<string, unknown>);
      await load();
      setSelectedMaterialId(updated.id); setSelectedVersionId(updated.versions[0]?.id || null); setEditing(false);
      setMessage(`Saved user revision ${updated.versions[0]?.version_number}. Earlier versions were preserved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the revision.");
    } finally { setBusy(false); }
  }

  return <div className="materials-manager">
    {error ? <p className="error-banner">{error}</p> : null}{message ? <p className="status-banner">{message}</p> : null}
    <form className="panel-card material-generator" onSubmit={handleGenerate}>
      <div className="section-heading"><div><h2>Generate material</h2><p>Inputs are snapshotted when generation starts.</p></div></div>
      <div className="material-form-grid">
        <label>Application<select value={applicationId} onChange={(event) => { setApplicationId(event.target.value); setSourceMaterialVersionId(""); }} required><option value="">Select an application</option>{applications.map((application) => <option key={application.id} value={application.id}>{application.job?.title || "Untitled"} - {application.job?.company || "Unknown company"}</option>)}</select></label>
        <label>Exact resume version<select value={documentVersionId} onChange={(event) => setDocumentVersionId(event.target.value)} required><option value="">Select a resume version</option>{resumeVersions.map(({ document, version }) => <option key={version.id} value={version.id}>{document.title} - v{version.version_number} ({version.file_name})</option>)}</select></label>
        <label>Material type<select value={kind} onChange={(event) => setKind(event.target.value as MaterialKind)}><option value="tailored_resume">Tailored resume</option><option value="cover_letter">Cover letter</option></select></label>
        {kind === "cover_letter" ? <label>Tailored resume source (optional)<select value={sourceMaterialVersionId} onChange={(event) => setSourceMaterialVersionId(event.target.value)}><option value="">Use selected original resume only</option>{tailoredVersions.map(({ material, version }) => <option key={version.id} value={version.id}>{material.application_label} - tailored v{version.version_number}</option>)}</select></label> : <div />}
      </div>
      <label>Targeting notes<textarea className="material-notes" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional emphasis, tone, or role-specific instructions" /></label>
      <button type="submit" disabled={busy || !applications.length || !resumeVersions.length}>{busy ? "Generating..." : `Generate ${kind === "tailored_resume" ? "tailored resume" : "cover letter"}`}</button>
    </form>
    <div className="materials-workspace">
      <section className="panel-card materials-list-card"><div className="section-heading"><div><h2>Generated materials</h2><p>{materials.length} application material{materials.length === 1 ? "" : "s"}</p></div></div>{!materials.length ? <p className="empty">No application materials have been generated.</p> : null}<div className="materials-list">{materials.map((material) => <button type="button" key={material.id} className={`material-list-row ${selectedMaterialId === material.id ? "selected" : ""}`} onClick={() => selectMaterial(material)}><strong>{material.material_type === "tailored_resume" ? "Tailored resume" : "Cover letter"}</strong><span>{material.application_label}</span><small>{material.versions.length} version{material.versions.length === 1 ? "" : "s"}</small></button>)}</div></section>
      <section className="panel-card material-detail-pane">{!selectedMaterial || !selectedVersion ? <div className="material-empty"><h2>Review a material</h2><p>Select a generated material to inspect its content, exact source version, and revision history.</p></div> : <>
        <div className="section-heading"><div><h2>{selectedMaterial.material_type === "tailored_resume" ? "Tailored resume" : "Cover letter"}</h2><p>{selectedMaterial.application_label}</p></div><button type="button" className="secondary-button" onClick={beginRevision} disabled={!selectedVersion.content_data}>Edit revision</button></div>
        <div className="material-provenance"><strong>Version {selectedVersion.version_number}</strong><span>{selectedVersion.version_source === "ai" ? "AI generated" : "User revision"}</span><span>{selectedVersion.source_document_title} v{selectedVersion.source_document_version_number}</span><span>{formatDate(selectedVersion.created_at)}</span></div>
        {selectedVersion.warnings.map((warning) => <p className="warning-banner" key={warning}>{warning}</p>)}
        {editing ? <div className="material-editor"><label>Structured material JSON<textarea value={revisionText} onChange={(event) => setRevisionText(event.target.value)} /></label><div className="button-row"><button type="button" className="secondary-button" onClick={() => setEditing(false)}>Cancel</button><button type="button" onClick={() => void saveRevision()} disabled={busy}>Save revision</button></div></div> : <MaterialContent materialType={selectedMaterial.material_type} content={selectedVersion.content_data} />}
        <section className="material-history"><h3>Version history</h3><div>{selectedMaterial.versions.map((version) => <button type="button" key={version.id} className={version.id === selectedVersion.id ? "selected" : ""} onClick={() => { setSelectedVersionId(version.id); setEditing(false); }}>v{version.version_number} · {version.version_source} · {formatDate(version.created_at)}</button>)}</div></section>
      </>}</section>
    </div>
  </div>;
}

function MaterialContent({ materialType, content }: { materialType: MaterialKind; content: object | null }) {
  if (!content) return <p className="empty">This version is still being generated or its operation failed.</p>;
  if (materialType === "tailored_resume" && isTailoredResume(content)) {
    const sections: [string, { text: string; source_evidence: string }[]][] = [["Summary", content.summary], ["Skills", content.skills], ["Experience", content.experience], ["Education", content.education], ["Certifications", content.certifications], ["Projects", content.projects]];
    return <div className="material-document">{content.headline ? <header><h3>{content.headline.text}</h3><Evidence text={content.headline.source_evidence} /></header> : null}{sections.filter(([, items]) => items.length).map(([name, items]) => <section key={name}><h3>{name}</h3><ul>{items.map((item, index) => <li key={`${name}-${index}`}><span>{item.text}</span><Evidence text={item.source_evidence} /></li>)}</ul></section>)}{content.unsupported_requirements.length ? <section><h3>Unsupported requirements</h3><ul>{content.unsupported_requirements.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}</div>;
  }
  const letter = content as CoverLetterContent;
  return <article className="material-document cover-letter"><p>{letter.salutation}</p>{letter.paragraphs.map((paragraph, index) => <div key={index}><p>{paragraph.text}</p>{paragraph.resume_evidence.map((item) => <Evidence key={item} text={`Resume: ${item}`} />)}{paragraph.job_evidence.map((item) => <Evidence key={item} text={`Job: ${item}`} />)}</div>)}<p>{letter.closing}</p></article>;
}

function Evidence({ text }: { text: string }) {
  return <details className="material-evidence"><summary>Source evidence</summary><p>{text}</p></details>;
}
