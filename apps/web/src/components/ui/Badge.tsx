import type { ReactNode } from "react";
import type { RiskLevel } from "../../types/api";

type Tone = "neutral" | "info" | "good" | "warn" | "bad" | "critical" | "scenario";
export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

const RISK_TONE: Record<RiskLevel, Tone> = { LOW: "good", MEDIUM: "warn", HIGH: "bad", CRITICAL: "critical" };
const RISK_MARK: Record<RiskLevel, string> = { LOW: "\u25CB", MEDIUM: "\u25D0", HIGH: "\u25CF", CRITICAL: "\u25A0" };

/** Risk level is always shown as text plus a shape, never colour alone. */
export function RiskBadge({ level, score }: { level: RiskLevel; score?: number }) {
  return (
    <Badge tone={RISK_TONE[level]} title={`Risk level ${level}${score !== undefined ? `, score ${score}` : ""}`}>
      <span aria-hidden="true">{RISK_MARK[level]}</span> {level}{score !== undefined ? ` ${score.toFixed(1)}` : ""}
    </Badge>
  );
}
