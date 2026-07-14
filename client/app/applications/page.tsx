import { ApplicationTracker } from "../../components/ApplicationTracker";

export default function ApplicationsPage() {
  return (
    <section className="panel applications-page">
      <div>
        <p className="eyebrow">Application Tracking</p>
        <h1>Applications</h1>
        <p className="lede">
          Track application status, follow-ups, notes, reminders, and timeline events for saved jobs.
        </p>
      </div>
      <ApplicationTracker />
    </section>
  );
}
