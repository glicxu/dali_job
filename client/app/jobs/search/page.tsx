import { IndeedJobSearchManager } from "../../../components/IndeedJobSearchManager";

export default function IndeedJobSearchPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Job Search</p>
        <h1>Job Search</h1>
        <p className="lede">Search for jobs and import selected postings into DaliJob.</p>
      </div>
      <IndeedJobSearchManager />
    </section>
  );
}
