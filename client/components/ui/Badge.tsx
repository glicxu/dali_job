import { ReactNode } from "react";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

export function Badge({ children, tone = "neutral", className = "" }: { children: ReactNode; tone?: BadgeTone; className?: string }) {
  return <span className={`ui-badge ui-badge-${tone} ${className}`.trim()}>{children}</span>;
}

export function MatchScoreBadge({ score }: { score: number | null }) {
  const tone = score === null ? "neutral" : score >= 8 ? "success" : score >= 5 ? "warning" : "danger";
  return <Badge tone={tone} className="ui-match-score">{score === null ? "N/A" : `${score}/10`}</Badge>;
}
