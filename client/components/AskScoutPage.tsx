"use client";

import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Compass, LockKeyhole, Send } from "lucide-react";
import { askScout, AskScoutResult, getAuthToken } from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, PageHeader, SectionHeader } from "./ui";

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

function statusTone(status: AskScoutResult["status"]): "info" | "warning" | "danger" | "neutral" {
  if (status === "navigate") return "info";
  if (status === "needs_context") return "warning";
  if (status === "unsupported") return "danger";
  return "neutral";
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
        <PageHeader
          eyebrow="Ask Scout"
          title="Find your next step"
          description="Ask Scout guides you to the right DaliJob workflow without performing actions for you."
          icon={Compass}
          actions={<a className="button-link secondary-button action-with-icon" href={returnPath}><ArrowLeft size={17} aria-hidden="true" /> Back</a>}
        />
        <EmptyState
          icon={LockKeyhole}
          title="Login required"
          description="Login or register to ask Scout for personalized navigation help."
          action={<a className="button-link" href="/auth">Login / Register</a>}
        />
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
      <PageHeader
        eyebrow="Ask Scout"
        title="What would you like to do?"
        description="Describe your goal. Scout will explain the workflow and guide you to the right page."
        icon={Compass}
        actions={<a className="button-link secondary-button action-with-icon" href={returnPath}><ArrowLeft size={17} aria-hidden="true" /> Back</a>}
      />
      <AlertBanner tone="info">Scout provides navigation guidance only. You review and perform every action yourself.</AlertBanner>

      <form className="profile-card ask-scout-form" onSubmit={submit}>
        <SectionHeader title="Ask a question" description="Include the outcome you want and any relevant job URL or application context." />
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
          <Button type="submit" icon={Send} loading={isAsking} disabled={question.trim().length < 3}>Ask Scout</Button>
        </div>
      </form>

      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      {answers.length ? (
        <section className="ask-scout-answers" aria-live="polite">
          <SectionHeader title="Guidance" description="Most recent guidance appears first." />
          {answers.map((result, index) => (
            <article className="profile-card ask-scout-answer" key={`${index}-${result.answer}`}>
              <Badge tone={statusTone(result.status)}>{statusLabel(result.status)}</Badge>
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
      ) : <EmptyState compact icon={Compass} title="No guidance yet" description="Ask how to complete a DaliJob workflow and Scout will suggest the appropriate page." />}
    </>
  );
}
