"use client";

import { FormEvent, useEffect, useState } from "react";
import { Download, Eye, FileText, RefreshCw, Trash2, Upload, UploadCloud, X } from "lucide-react";
import {
  deleteDocument,
  getDocumentDependencies,
  getAuthToken,
  getDocumentText,
  listDocuments,
  StoredDocument,
  downloadDocumentFile,
  uploadDocument,
  uploadDocumentVersion,
} from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, SectionHeader, SkeletonRows, ToastRegion } from "./ui";

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentLibrary() {
  if (!getAuthToken()) {
    return <DocumentLibraryPreview />;
  }

  return <AuthenticatedDocumentLibrary />;
}

function AuthenticatedDocumentLibrary() {
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [textPreview, setTextPreview] = useState<string | null>(null);
  const [textPreviewTitle, setTextPreviewTitle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);

  async function loadDocuments() {
    setError(null);
    setIsLoading(true);
    try {
      const payload = await listDocuments();
      setDocuments(payload.documents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document load failed.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadDocuments();
  }, []);

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setStatus(null);
    const form = event.currentTarget;
    const input = form.elements.namedItem("document") as HTMLInputElement | null;
    const titleInput = form.elements.namedItem("title") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;

    setIsUploading(true);
    try {
      await uploadDocument(file, titleInput?.value ?? "");
      form.reset();
      setStatus("Document uploaded.");
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function previewText(document: StoredDocument) {
    setError(null);
    setTextPreview(null);
    setTextPreviewTitle(null);
    try {
      const payload = await getDocumentText(document.id);
      setTextPreview(payload.extracted_text);
      setTextPreviewTitle(document.title);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Text preview failed.");
    }
  }

  async function downloadDocument(document: StoredDocument) {
    setError(null);
    try {
      await downloadDocumentFile(document.id, document.latest_version?.file_name ?? `${document.title}.pdf`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document download failed.");
    }
  }

  async function replaceDocumentVersion(document: StoredDocument, file: File | undefined) {
    if (!file) return;
    setError(null);
    setStatus(null);
    setIsUploading(true);
    try {
      await uploadDocumentVersion(document.id, file);
      setStatus(`Version ${document.latest_version ? document.latest_version.version_number + 1 : 1} uploaded.`);
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document version upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function removeDocument(document: StoredDocument) {
    setError(null);
    setStatus(null);
    try {
      const dependencyReport = await getDocumentDependencies(document.id);
      let force = false;
      if (dependencyReport.dependencies.length) {
        const warning = dependencyReport.dependencies.map((item) => item.message).join("\n");
        force = window.confirm(
          `${warning}\n\nThe stored file will be hidden, while historical match snapshots remain available. Delete it?`,
        );
        if (!force) return;
      } else if (!window.confirm(`Delete "${document.title}"?`)) {
        return;
      }
      await deleteDocument(document.id, force);
      if (textPreviewTitle === document.title) {
        setTextPreview(null);
        setTextPreviewTitle(null);
      }
      setStatus("Document deleted.");
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document delete failed.");
    }
  }

  return (
    <div className="document-library">
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={status} onDismiss={() => setStatus(null)} />

      <section className="profile-card document-upload-card">
        <SectionHeader title="Upload document" description="Add a PDF or text document. Extracted text is redacted before storage and each replacement creates a preserved version." />
        <form className="document-upload-form" onSubmit={submitUpload}>
          <input name="title" placeholder="Document title" />
          <input name="document" type="file" accept="application/pdf,text/plain" required />
          <Button type="submit" icon={Upload} loading={isUploading}>Upload</Button>
        </form>
      </section>

      <section className="profile-card document-library-card">
        <div className="profile-card-header">
          <SectionHeader title="Document library" description={`${documents.length} document${documents.length === 1 ? "" : "s"} with preserved version history`} />
          <Button type="button" variant="secondary" size="compact" icon={RefreshCw} onClick={() => void loadDocuments()}>Refresh</Button>
        </div>

        {isLoading ? <SkeletonRows count={4} /> : null}
        {!isLoading && !documents.length ? <EmptyState icon={FileText} title="No documents" description="Upload a resume or supporting document to begin your versioned library." /> : null}
        {documents.length ? <div className="document-table-header" aria-hidden="true"><span>Document</span><span>Version</span><span>Type</span><span>Actions</span></div> : null}
        <div className="document-list structured-document-list">
          {documents.map((document) => (
            <article className="document-row" key={document.id}>
              <div className="document-primary-cell">
                <h2>{document.title}</h2>
                <p className="metadata">
                  {document.latest_version?.file_name ?? "No file"} | {document.latest_version ? formatBytes(document.latest_version.size_bytes) : "0 B"}
                </p>
              </div>
              <div className="document-version-cell">
                <strong>v{document.latest_version?.version_number ?? 0}</strong>
                <span className="metadata">{document.versions.length} saved</span>
              </div>
              <div><Badge tone={document.document_type === "resume" ? "info" : "neutral"}>{document.document_type}</Badge></div>
              <div className="button-row document-actions">
                <label className="secondary-button document-version-button action-with-icon" title="Upload a new version">
                  <UploadCloud size={16} aria-hidden="true" /> New Version
                  <input
                    type="file"
                    accept="application/pdf,text/plain"
                    disabled={isUploading}
                    onChange={(event) => {
                      void replaceDocumentVersion(document, event.target.files?.[0]);
                      event.target.value = "";
                    }}
                  />
                </label>
                <Button
                  type="button"
                  variant="secondary"
                  size="compact"
                  icon={Eye}
                  disabled={!document.latest_version?.extracted_text_available}
                  onClick={() => void previewText(document)}
                >
                  Text
                </Button>
                <Button type="button" variant="secondary" size="compact" icon={Download} onClick={() => void downloadDocument(document)}>Download</Button>
                <Button type="button" variant="danger" size="compact" icon={Trash2} onClick={() => void removeDocument(document)}>Delete</Button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {textPreview ? (
        <section className="profile-card document-text-preview">
          <div className="profile-card-header">
            <SectionHeader title={textPreviewTitle || "Extracted text"} description="Redacted text saved for matching and profile workflows." />
            <Button type="button" variant="secondary" size="compact" icon={X} onClick={() => setTextPreview(null)}>Close</Button>
          </div>
          <pre className="text-preview">{textPreview}</pre>
        </section>
      ) : null}
    </div>
  );
}

function DocumentLibraryPreview() {
  return (
    <div className="document-library">
      <div className="warning-banner">
        Login is required to upload, extract, download, and store documents.
      </div>
      <section className="profile-card">
        <div>
          <h2>Upload Document</h2>
          <p className="metadata">Upload resume files after login so they can be stored privately.</p>
        </div>
        <form className="document-upload-form">
          <input placeholder="Document title" disabled />
          <input type="file" disabled />
          <button type="button" disabled>
            Upload
          </button>
        </form>
      </section>
      <section className="profile-card">
        <div className="profile-card-header">
          <h2>Document Library</h2>
          <button type="button" className="secondary-button" disabled>
            Refresh
          </button>
        </div>
        <div className="document-list">
          <article className="document-row">
            <div>
              <h2>Master Resume.pdf</h2>
              <p className="metadata">resume.pdf | 145 KB | resume</p>
            </div>
            <div className="button-row">
              <button type="button" className="secondary-button" disabled>
                Text
              </button>
              <button type="button" className="secondary-button" disabled>
                Download
              </button>
            </div>
          </article>
        </div>
      </section>
      <a className="button-link" href="/auth">
        Login / Register to Manage Documents
      </a>
    </div>
  );
}
