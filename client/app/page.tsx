import { ResumeJobMatchForm } from "../components/ResumeJobMatchForm";

export default function HomePage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Phase 0.5 Prototype</p>
        <h1>Resume-to-job matching foundation</h1>
        <p className="lede">
          Compare an uploaded resume against a job URL and return a 0-10 match score.
          Pasted text remains available as a fallback.
        </p>
      </div>
      <ResumeJobMatchForm />
    </section>
  );
}
