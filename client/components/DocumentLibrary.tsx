"use client";

import { FormEvent, useEffect, useState } from "react";
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
      {error ? <div className="error-banner">{error}</div> : null}
      {status ? <div className="status-banner">{status}</div> : null}

      <section className="profile-card">
        <div>
          <h2>Upload Document</h2>
          <p className="metadata">
            PDF and plain text files are stored locally. Extracted text is redacted before it is saved for reuse.
          </p>
        </div>
        <form className="document-upload-form" onSubmit={submitUpload}>
          <input name="title" placeholder="Document title" />
          <input name="document" type="file" accept="application/pdf,text/plain" required />
          <button type="submit" disabled={isUploading}>
            {isUploading ? "Uploading..." : "Upload"}
          </button>
        </form>
      </section>

      <section className="profile-card">
        <div className="profile-card-header">
          <h2>Document Library</h2>
          <button type="button" className="secondary-button" onClick={() => void loadDocuments()}>
            Refresh
          </button>
        </div>

        {isLoading ? <p className="empty">Loading documents.</p> : null}
        {!isLoading && !documents.length ? <p className="empty">No documents uploaded.</p> : null}
        <div className="document-list">
          {documents.map((document) => (
            <article className="document-row" key={document.id}>
              <div>
                <h2>{document.title}</h2>
                <p className="metadata">
                  {document.latest_version?.file_name ?? "No file"} ·{" "}
                  {document.latest_version ? formatBytes(document.latest_version.size_bytes) : "0 B"} ·{" "}
                  {document.document_type}
                </p>
              </div>
              <div className="button-row">
                <label className="secondary-button document-version-button">
                  New Version
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
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!document.latest_version?.extracted_text_available}
                  onClick={() => void previewText(document)}
                >
                  Text
                </button>
                <button type="button" className="secondary-button" onClick={() => void downloadDocument(document)}>
                  Download
                </button>
                <button type="button" className="secondary-button" onClick={() => void removeDocument(document)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {textPreview ? (
        <section className="profile-card">
          <div className="profile-card-header">
            <h2>{textPreviewTitle}</h2>
            <button type="button" className="secondary-button" onClick={() => setTextPreview(null)}>
              Close
            </button>
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
