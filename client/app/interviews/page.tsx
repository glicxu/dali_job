import { InterviewManager } from "../../components/InterviewManager";
import { PageHeader } from "../../components/ui";
import { MessagesSquare } from "lucide-react";

export default function InterviewsPage() {
  return (
    <section className="panel interviews-page">
      <PageHeader
        eyebrow="Interview Preparation"
        title="Interviews"
        description="Add scheduled interviews, keep private notes, and build evidence-based preparation guides."
        icon={MessagesSquare}
      />
      <InterviewManager />
    </section>
  );
}
