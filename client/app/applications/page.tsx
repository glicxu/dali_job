import { ApplicationTracker } from "../../components/ApplicationTracker";
import { PageHeader } from "../../components/ui";
import { ClipboardList } from "lucide-react";

export default function ApplicationsPage() {
  return (
    <section className="panel applications-page">
      <PageHeader
        eyebrow="Application Tracking"
        title="Applications"
        description="Track application status, follow-ups, notes, reminders, and timeline events for saved jobs."
        icon={ClipboardList}
      />
      <ApplicationTracker />
    </section>
  );
}
