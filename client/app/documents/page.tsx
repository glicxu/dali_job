import { DocumentLibrary } from "../../components/DocumentLibrary";
import { PageHeader } from "../../components/ui";
import { Files } from "lucide-react";

export default function DocumentsPage() {
  return (
    <section className="panel documents-page">
      <PageHeader
        eyebrow="Library"
        title="Documents"
        description="Upload and manage versioned resume files for matching and application workflows."
        icon={Files}
      />
      <DocumentLibrary />
    </section>
  );
}
