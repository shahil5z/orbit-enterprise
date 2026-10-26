import type { Kpi } from "../../types/api";
import { byUnit, pct } from "../../utils/format";
import { Tooltip } from "./Tooltip";

export interface Delta { label: string; value: number | null }

/** KPI tile. Label, unit and direction come from the KPI governance catalogue when `kpi` is given. */
export function Metric({ kpi, label, value, unit, deltas = [], note, higherIsBetter }:
  { kpi?: Kpi; label?: string; value: number | null | undefined; unit?: Kpi["unit"]; deltas?: Delta[]; note?: string; higherIsBetter?: boolean }) {
  const u = unit ?? kpi?.unit ?? "count";
  const hib = higherIsBetter ?? kpi?.higher_is_better ?? true;
  return (
    <div className="metric">
      <div className="metric-label">
        <span>{label ?? kpi?.name}</span>
        {kpi && <Tooltip label={`Definition of ${kpi.name}`} content={<><strong>{kpi.name}</strong>: {kpi.definition}<br />Formula: <code>{kpi.formula}</code><br />Source: {kpi.source}</>} />}
      </div>
      <div className="metric-value">{byUnit(value, u)}</div>
      {deltas.length > 0 && (
        <ul className="metric-deltas">
          {deltas.map((d) => {
            const good = d.value === null ? null : (d.value >= 0) === hib;
            const cls = d.value === null || Math.abs(d.value) < 0.0005 ? "flat" : good ? "up-good" : "up-bad";
            const arrow = d.value === null ? "" : d.value > 0 ? "\u25B2" : d.value < 0 ? "\u25BC" : "";
            return <li key={d.label} className={`delta ${cls}`}><span aria-hidden="true">{arrow}</span> {pct(d.value, 1, true)} <span className="muted">{d.label}</span></li>;
          })}
        </ul>
      )}
      {note && <div className="metric-note">{note}</div>}
    </div>
  );
}
