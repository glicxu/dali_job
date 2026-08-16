"use client";

import { useEffect, useState } from "react";
import { getAuthToken, listMatchInbox, MatchInboxItem, V2ExplanationItem } from "../lib/api";
import { AlertBanner, Badge, SectionHeader } from "./ui";

const label = (value: string) =>
  value
    .split("_")
    .map((part) => (part ? `${part[0].toUpperCase()}${part.slice(1)}` : part))
    .join(" ");

function EvidenceGroup({ title, items }: { title: string; items: V2ExplanationItem[] }) {
  if (!items.length) return null;
  return (
    <details className="v2-evidence-group">
      <summary>{title} ({items.length})</summary>
      <ul>
        {items.map((item) => (
          <li key={`${title}:${item.key}`}>
            <strong>{item.label}</strong>
            <p>{item.detail}</p>
          </li>
        ))}
      </ul>
      {/* Evidence IDs are not links: this response does not authorize source excerpts. */}
    </details>
  );
}

function MatchCard({ item }: { item: MatchInboxItem }) {
  const result = item.matching_v2_result;
  if (!result) {
    return (
      <article className="profile-card v2-match-card">
        <h3>{item.title}</h3>
        <p>{item.company}</p>
        <Badge>{item.match_score === null ? "Score unavailable" : `${item.match_score}/10 legacy score`}</Badge>
        <p>This historical result remains readable while V2 matching rolls out.</p>
      </article>
    );
  }
  const { scores, explanation } = result;
  const questions = [...new Set([...scores.questions, ...explanation.questions])];
  return (
    <article className="profile-card v2-match-card" data-recommendation={scores.recommendation}>
      <div className="v2-match-heading">
        <div>
          <h3>{item.title}</h3>
          <p>{item.company}</p>
        </div>
        <div className="v2-match-score">
          {scores.overall_score === null ? <span>More information needed</span> : <strong>{scores.overall_score}/100</strong>}
          <small>{label(scores.recommendation)}</small>
        </div>
      </div>
      <p>{explanation.summary}</p>
      <p className="v2-score-components">
        Qualification {scores.qualification_score === null ? "not scored" : `${scores.qualification_score}/100`}
        {" · "}Coverage {Math.round(scores.qualification_coverage * 100)}%
        {" · "}Preferences {scores.preference_score === null ? "not scored" : `${scores.preference_score}/100`}
      </p>
      <div className="v2-reason-codes">
        {scores.reason_codes.map((code) => <Badge key={code}>{label(code)}</Badge>)}
      </div>
      <EvidenceGroup title="Strengths" items={explanation.strengths} />
      <EvidenceGroup title="Gaps" items={explanation.gaps} />
      <EvidenceGroup title="Unknowns" items={explanation.unknowns} />
      <EvidenceGroup title="Preference conflicts" items={explanation.preference_conflicts} />
      {questions.length ? (
        <section className="v2-questions">
          <h4>Help improve this match</h4>
          <ul>{questions.map((question) => <li key={question}>{question}</li>)}</ul>
        </section>
      ) : null}
    </article>
  );
}

export function V2MatchInbox() {
  const [items, setItems] = useState<MatchInboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthToken()) {
      setItems([]);
      return;
    }
    listMatchInbox()
      .then((payload) => setItems(payload.items))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Could not load matches."));
  }, []);

  if (error) return <AlertBanner tone="danger">{error}</AlertBanner>;
  if (items === null) return <p>Loading your match inbox…</p>;
  if (!items.length) return null;
  return (
    <section className="v2-match-inbox">
      <SectionHeader
        title="Your latest matches"
        description="V2 results preserve uncertainty, component coverage, and the evidence-based explanation returned by the server."
      />
      <div className="v2-match-grid">{items.map((item) => <MatchCard key={item.match_id} item={item} />)}</div>
    </section>
  );
}
