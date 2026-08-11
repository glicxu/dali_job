import { ApplicationTracker } from "../../../components/ApplicationTracker";
import { PageHeader } from "../../../components/ui";
import { ArrowLeft, ClipboardPenLine } from "lucide-react";
import Link from "next/link";

type ApplicationDetailPageProps = {
  params: Promise<{ applicationId: string }>;
};

export default async function ApplicationDetailPage({ params }: ApplicationDetailPageProps) {
  const { applicationId: rawApplicationId } = await params;
  const applicationId = Number(rawApplicationId);

  return (
    <section className="panel applications-page">
      <PageHeader
        eyebrow="Application Tracking"
        title="Application Details"
        description="Review and update this application, its submitted documents, tasks, notes, and timeline."
        icon={ClipboardPenLine}
        actions={<Link className="button-link secondary-button action-with-icon" href="/applications"><ArrowLeft size={17} aria-hidden="true" /> Applications</Link>}
      />
      {Number.isInteger(applicationId) && applicationId > 0 ? (
        <ApplicationTracker applicationId={applicationId} />
      ) : (
        <div className="error-banner">The application ID is invalid.</div>
      )}
    </section>
  );
}
