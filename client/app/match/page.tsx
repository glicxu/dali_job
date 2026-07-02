import { ResumeJobMatchForm } from "../../components/ResumeJobMatchForm";

export default function MatchPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Match</p>
        <h1>Resume-to-job matching</h1>
        <p className="lede">
          Compare a saved resume profile or uploaded resume against a job URL and return a 0-10 match score.
          Pasted text remains available as a fallback.
        </p>
      </div>
      <ResumeJobMatchForm />
    </section>
  );
}
