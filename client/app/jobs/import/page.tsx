import { JobListImportManager } from "../../../components/JobListImportManager";

export default function JobListImportPage() {
  return (
    <div className="panel">
      <div>
        <p className="eyebrow">Bulk Job Import</p>
        <h1>Import Jobs From List URL</h1>
        <p className="lede">
          Discover individual job postings from a search results page, choose the jobs to save, and optionally match
          them against a resume profile.
        </p>
      </div>
      <JobListImportManager />
    </div>
  );
}
