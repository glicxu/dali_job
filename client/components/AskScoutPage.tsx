"use client";

import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { askScout, AskScoutResult, getAuthToken } from "../lib/api";

const knownPaths = new Set([
  "/", "/profile", "/match", "/jobs", "/jobs/import-url", "/jobs/manual", "/jobs/import",
  "/jobs/search", "/applications", "/materials", "/interviews", "/documents", "/analytics",
  "/auth", "/operations",
]);

function safeReturnPath(value: string | null): string {
  if (!value || value.length > 255 || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }
  const path = value.split("?", 1)[0].replace(/\/$/, "") || "/";
  if (knownPaths.has(path) || /^\/applications\/\d+$/.test(path)) return value;
  return "/";
}

function pageContextFromPath(value: string) {
  const parsed = new URL(value, "https://dalijob.local");
  const applicationMatch = parsed.pathname.match(/^\/applications\/(\d+)$/);
  const positiveId = (name: string) => {
    const number = Number(parsed.searchParams.get(name));
    return Number.isInteger(number) && number > 0 ? number : undefined;
  };
  return {
    application_id: applicationMatch ? Number(applicationMatch[1]) : positiveId("application_id"),
    job_id: positiveId("job_id"),
    interview_id: positiveId("interview_id"),
    resume_profile_id: positiveId("resume_profile_id"),
  };
}

function statusLabel(status: AskScoutResult["status"]): string {
  if (status === "navigate") return "Recommended path";
  if (status === "needs_context") return "More detail needed";
  if (status === "unsupported") return "Not supported";
  return "Guidance";
}

export function AskScoutPage() {
  const searchParams = useSearchParams();
  const returnPath = useMemo(() => safeReturnPath(searchParams.get("from")), [searchParams]);
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<AskScoutResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);

  if (!getAuthToken()) {
    return (
      <>
        <a className="back-link" href={returnPath}><span aria-hidden="true">&larr;</span> Back</a>
        <div>
          <p className="eyebrow">Ask Scout</p>
          <h1>Find your next step</h1>
          <p className="lede">Ask Scout guides you to the right DaliJob workflow without performing actions for you.</p>
        </div>
        <section className="card ask-scout-login-card">
          <h2>Login required</h2>
          <p>Login or register to ask Scout for personalized navigation help.</p>
          <a className="button-link" href="/auth">Login / Register</a>
        </section>
      </>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (question.trim().length < 3 || isAsking) return;
    setError(null);
    setIsAsking(true);
    try {
      const result = await askScout({
        question: question.trim(),
        current_path: returnPath,
        page_context: pageContextFromPath(returnPath),
      });
      setAnswers((current) => [result, ...current].slice(0, 6));
      setQuestion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ask Scout could not prepare guidance.");
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <>
      <a className="back-link" href={returnPath}><span aria-hidden="true">&larr;</span> Back</a>
      <div>
        <p className="eyebrow">Ask Scout</p>
        <h1>What would you like to do?</h1>
        <p className="lede">Describe your goal. Scout will explain the workflow and guide you to the right page.</p>
      </div>

      <form className="card ask-scout-form" onSubmit={submit}>
        <label>
          Question
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="How do I add a job from a URL?"
            maxLength={1000}
            rows={5}
          />
        </label>
        <div className="ask-scout-form-footer">
          <span className="metadata">{question.length}/1000</span>
          <button type="submit" disabled={question.trim().length < 3 || isAsking}>
            {isAsking ? "Asking Scout..." : "Ask Scout"}
          </button>
        </div>
      </form>

      {error ? <p className="error">{error}</p> : null}
      {answers.length ? (
        <section className="ask-scout-answers" aria-live="polite">
          <h2>Guidance</h2>
          {answers.map((result, index) => (
            <article className="card ask-scout-answer" key={`${index}-${result.answer}`}>
              <p className={`ask-scout-status ${result.status}`}>{statusLabel(result.status)}</p>
              <p>{result.answer}</p>
              {result.limitations.length ? (
                <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
              ) : null}
              <div className="ask-scout-actions">
                {result.primary_action ? (
                  <a className="button-link" href={result.primary_action.href}>{result.primary_action.label}</a>
                ) : null}
                {result.alternative_actions.map((action) => (
                  <a className="button-link secondary-button" href={action.href} key={action.action_id}>{action.label}</a>
                ))}
              </div>
            </article>
          ))}
        </section>
      ) : null}
    </>
  );
}
