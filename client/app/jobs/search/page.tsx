import { IndeedJobSearchManager } from "../../../components/IndeedJobSearchManager";

export default function IndeedJobSearchPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Job Search</p>
        <h1>Indeed Search</h1>
        <p className="lede">Search Indeed through Apify and import selected job postings into DaliJob.</p>
      </div>
      <IndeedJobSearchManager />
    </section>
  );
}
