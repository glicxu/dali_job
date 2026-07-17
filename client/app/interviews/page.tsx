import { InterviewManager } from "../../components/InterviewManager";

export default function InterviewsPage() {
  return (
    <section className="panel interviews-page">
      <div>
        <p className="eyebrow">Interview Preparation</p>
        <h1>Interviews</h1>
        <p className="lede">Add scheduled interviews, keep private notes, and build evidence-based preparation guides.</p>
      </div>
      <InterviewManager />
    </section>
  );
}
