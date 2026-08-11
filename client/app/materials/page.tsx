import { ApplicationMaterialsManager } from "../../components/ApplicationMaterialsManager";
import { PageHeader } from "../../components/ui";
import { FileCheck2 } from "lucide-react";

export default function MaterialsPage() {
  return (
    <section className="panel materials-page">
      <PageHeader
        eyebrow="Application Materials"
        title="Tailored resumes and cover letters"
        description="Generate, review, and revise materials from an exact saved job and resume version."
        icon={FileCheck2}
      />
      <ApplicationMaterialsManager />
    </section>
  );
}
