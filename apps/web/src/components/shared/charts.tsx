import type { ReactNode } from "react";
import { money } from "../../utils/format";

export const COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)"];
// recharts needs concrete colours for SVG attributes in some places
export const HEX = { c1: "#1f5fa8", c2: "#c98a2b", c3: "#4f7f6b", c4: "#7a5ea8", c5: "#a8483b", c6: "#5b6b7f", grid: "#e6eaf0", band: "#1f5fa8", scenario: "#5b3fa0" };
export const axis = { stroke: "#9aa5b3", tick: { fontSize: 11, fill: "#4a5666" }, tickLine: false } as const;
export const moneyTick = (v: number) => money(v, 0);

interface TipPayload { name?: string; value?: number | number[] | string; color?: string; dataKey?: string | number }
/** Shared chart tooltip; `fmt` formats each value. */
export function ChartTip({ active, payload, label, fmt = (v: number) => money(v), labelFmt = (l: string) => l }:
  { active?: boolean; payload?: TipPayload[]; label?: string; fmt?: (v: number) => string; labelFmt?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tip">
      <strong>{labelFmt(String(label ?? ""))}</strong>
      <ul>
        {payload.filter((p) => p.value !== undefined && p.value !== null).map((p) => (
          <li key={String(p.dataKey)}>
            <span style={{ color: p.color }} aria-hidden="true">{"\u25A0"} </span>{p.name}:{" "}
            {Array.isArray(p.value) ? `${fmt(p.value[0]!)} to ${fmt(p.value[1]!)}` : typeof p.value === "number" ? fmt(p.value) : p.value}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; kind?: "line" | "dash" | "band" }[] }) {
  return (
    <div className="legend" aria-hidden="true">
      {items.map((i) => <span key={i.label}><i className={i.kind ?? "line"} style={{ background: i.kind === "dash" ? undefined : i.color, color: i.color }} />{i.label}</span>)}
    </div>
  );
}

export function MiniTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="table-scroll"><table className="table table-dense">
      <thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
    </table></div>
  );
}
