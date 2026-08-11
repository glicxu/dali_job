import { GraduationCap } from "lucide-react";
import { TutorialStartup } from "../../components/TutorialGuide";
import { PageHeader } from "../../components/ui";

export default function TutorialPage() {
  return (
    <section className="panel tutorial-page">
      <PageHeader
        eyebrow="Getting Started"
        title="DaliJob Tutorial"
        description="Learn the core workflow using your own account and data. Every step can be skipped."
        icon={GraduationCap}
      />
      <TutorialStartup />
    </section>
  );
}
