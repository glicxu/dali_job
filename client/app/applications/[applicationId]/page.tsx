import { ApplicationTracker } from "../../../components/ApplicationTracker";

type ApplicationDetailPageProps = {
  params: Promise<{ applicationId: string }>;
};

export default async function ApplicationDetailPage({ params }: ApplicationDetailPageProps) {
  const { applicationId: rawApplicationId } = await params;
  const applicationId = Number(rawApplicationId);

  return (
    <section className="panel applications-page">
      <a className="back-link" href="/applications">
        <span aria-hidden="true">&larr;</span> Back to Applications
      </a>
      <div>
        <p className="eyebrow">Application Tracking</p>
        <h1>Application Details</h1>
        <p className="lede">Review and update this application, its submitted documents, tasks, notes, and timeline.</p>
      </div>
      {Number.isInteger(applicationId) && applicationId > 0 ? (
        <ApplicationTracker applicationId={applicationId} />
      ) : (
        <div className="error-banner">The application ID is invalid.</div>
      )}
    </section>
  );
}
