import { useState } from "react";
import { api } from "../../services/api";
import { Button } from "../ui";

type Kind = Parameters<typeof api.exportFile>[0];
const LABEL: Record<Kind, string> = { "risks.csv": "Risk register CSV", "recommendations.csv": "Recommendations CSV", "anomalies.csv": "Anomalies CSV", "risk-report.md": "Risk report" };

/** Downloads a server-generated export built from live database rows. */
export function ExportButton({ kind }: { kind: Kind }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  const go = async () => {
    setState("busy");
    try { await api.exportFile(kind); setState("idle"); } catch { setState("error"); }
  };
  return (
    <span className="row">
      <Button size="sm" onClick={go} disabled={state === "busy"}>{state === "busy" ? "Preparing" : `Export ${LABEL[kind]}`}</Button>
      {state === "error" && <span role="alert" className="small" style={{ color: "var(--bad)" }}>Export failed. <button className="btn btn-ghost btn-sm" onClick={go}>Retry</button></span>}
    </span>
  );
}
