import { ResumeJobMatchForm } from "../components/ResumeJobMatchForm";

export default function HomePage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Phase 0.5 Prototype</p>
        <h1>Resume-to-job matching foundation</h1>
        <p className="lede">
          Compare pasted resume text against a pasted job description and return a 0-10
          match score.
        </p>
      </div>
      <ResumeJobMatchForm />
    </section>
  );
}
