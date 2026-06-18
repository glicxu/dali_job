import { DocumentLibrary } from "../../components/DocumentLibrary";

export default function DocumentsPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Library</p>
        <h1>Documents</h1>
        <p className="lede">Upload and manage resume files for later matching and profile workflows.</p>
      </div>
      <DocumentLibrary />
    </section>
  );
}
