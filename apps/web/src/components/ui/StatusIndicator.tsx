import type { RunStatus } from "../../types/api";

const MAP: Record<string, { cls: string; mark: string }> = {
  SUCCESS: { cls: "good", mark: "\u2713" }, OK: { cls: "good", mark: "\u2713" }, UP: { cls: "good", mark: "\u2713" },
  OPTIMAL: { cls: "good", mark: "\u2713" }, ACTIVE: { cls: "good", mark: "\u2713" }, PASSED: { cls: "good", mark: "\u2713" },
  RUNNING: { cls: "info", mark: "\u21BB" }, WARNING: { cls: "warn", mark: "!" }, PASSED_WITH_WARNINGS: { cls: "warn", mark: "!" },
  DEGRADED: { cls: "warn", mark: "!" }, SUPERSEDED: { cls: "neutral", mark: "\u2013" },
  FAILED: { cls: "bad", mark: "\u2715" }, DOWN: { cls: "bad", mark: "\u2715" }, INFEASIBLE: { cls: "bad", mark: "\u2715" },
};

export function StatusIndicator({ status, label }: { status: RunStatus | string; label?: string }) {
  const s = MAP[status.toUpperCase()] ?? { cls: "neutral", mark: "\u2022" };
  return (
    <span className={`status status-${s.cls}`}>
      <span className="status-dot" aria-hidden="true">{s.mark}</span>
      <span>{label ?? status.replace(/_/g, " ")}</span>
    </span>
  );
}
