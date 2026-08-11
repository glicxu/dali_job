import { ResumeJobMatchForm } from "../../components/ResumeJobMatchForm";
import { PageHeader } from "../../components/ui";
import { ScanSearch } from "lucide-react";

export default function MatchPage() {
  return (
    <section className="panel match-page">
      <PageHeader
        eyebrow="Match"
        title="Resume-to-job matching"
        description="Compare a saved resume profile or pasted resume text against one or more jobs and receive evidence-based match results."
        icon={ScanSearch}
      />
      <ResumeJobMatchForm />
    </section>
  );
}
