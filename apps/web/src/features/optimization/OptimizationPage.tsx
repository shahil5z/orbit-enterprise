import { useCallback, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ChartTip, HEX, Legend, MiniTable, axis, moneyTick } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Badge, Button, Card, ChartContainer, ErrorState, Metric, StatusIndicator, Table } from "../../components/ui";
import { useApi, useMutation } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { api } from "../../services/api";
import type { OptimizationDetail, OptimizationParams, OptimizationRun } from "../../types/api";
import { dateTime, money, num, pct } from "../../utils/format";

const DEFAULTS: OptimizationParams = { budget_multiplier: 1.0, total_hires: 40, risk_cap_factor: 0.95, min_region_share: 0.85 };
const FIELDS: { key: keyof OptimizationParams; label: string; min: number; max: number; step: number; fmt: (v: number) => string; help: string }[] = [
  { key: "budget_multiplier", label: "Budget multiplier", min: 0.5, max: 1.5, step: 0.05, fmt: (v) => `${v.toFixed(2)}x`, help: "Total marketing budget relative to the last 6 months." },
  { key: "total_hires", label: "Total hires", min: 0, max: 200, step: 5, fmt: (v) => String(v), help: "Headcount to allocate across units (integer decision variables)." },
  { key: "risk_cap_factor", label: "Risk cap factor", min: 0.7, max: 1.2, step: 0.05, fmt: (v) => `${v.toFixed(2)}x`, help: "Cap on risk-weighted spend relative to the baseline allocation." },
  { key: "min_region_share", label: "Min region share", min: 0.5, max: 1.0, step: 0.05, fmt: (v) => pct(v, 0), help: "Each region keeps at least this share of its baseline spend." },
];

export default function OptimizationPage() {
  const [p, setP] = useState<OptimizationParams>(DEFAULTS);
  const runs = useApi("opt-runs", () => api.optimizationRuns(20));
  const caps = useApi("capabilities", () => api.capabilities());
  const hosted = caps.data?.optimization_solver === false;
  const run = useMutation(useCallback((x: OptimizationParams) => api.runOptimization(x), []));
  const [persistedNote, setPersistedNote] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [compare, setCompare] = useState<string | null>(null);
  const current = selected ?? runs.data?.runs[0]?.optimization_id ?? null;
  const submit = async () => {
    const before = current;
    const r = await run.run(p);
    if (!r) return;
    if (r.mode === "persisted") { setPersistedNote(r.message ?? "Showing the latest persisted run."); setSelected(r.optimization_id); return; }
    setPersistedNote(null); setCompare(before); setSelected(r.optimization_id); runs.reload();
  };
  return (
    <Page title="Optimization Center" intro="Each run calls the Julia JuMP + HiGHS mixed-integer model on the server. Objective = expected incremental gross margin from marketing spend and hires, subject to budget, hiring, risk and regional minimum constraints.">
      <div className="grid g-1-2">
        <Card title="Parameters" subtitle="Change constraints, then run the solver">
          <form onSubmit={(e) => { e.preventDefault(); void submit(); }} className="grid" style={{ gap: 14 }} aria-label="Optimization parameters">
            {FIELDS.map((f) => (
              <div className="lever" key={f.key}>
                <label htmlFor={`opt-${f.key}`}>{f.label}</label>
                <output htmlFor={`opt-${f.key}`}>{f.fmt(p[f.key])}</output>
                <input id={`opt-${f.key}`} type="range" min={f.min} max={f.max} step={f.step} value={p[f.key]} style={{ gridColumn: "1 / -1" }}
                  onChange={(e) => setP({ ...p, [f.key]: Number(e.target.value) })} aria-describedby={`opt-${f.key}-h`} />
                <span className="lever-desc" id={`opt-${f.key}-h`}>{f.help} Range {f.fmt(f.min)} to {f.fmt(f.max)}.</span>
              </div>
            ))}
            <div className="row">
              <Button variant="primary" type="submit" disabled={run.status === "loading"} data-testid="run-optimization">{run.status === "loading" ? "Solving" : hosted ? "Show latest persisted run" : "Run optimizer"}</Button>
              <Button onClick={() => setP(DEFAULTS)}>Reset</Button>
            </div>
            {hosted && <p className="notice small" role="note" data-testid="runs-locally">{caps.data?.note} The Julia JuMP + HiGHS solver runs locally; run <code>scripts/orbit.ps1 dev</code> on the workstation to solve new parameters.</p>}
            {persistedNote && <p className="notice small" role="status" data-testid="persisted-note">{persistedNote}</p>}
            {run.status === "loading" && !hosted && <p className="small muted" role="status">Julia is solving; the first run can take 20 to 60 seconds while Julia compiles.</p>}
            {run.status === "error" && run.error && <ErrorState title="Optimization failed" error={run.error} onRetry={() => void submit()} />}
          </form>
        </Card>
        <div className="grid">
          {current ? <RunDetail id={current} compareId={compare} /> : <Card title="Result"><p className="small muted">No optimization runs yet. Run the solver to see a result.</p></Card>}
        </div>
      </div>
      <Card title="Run history" subtitle="Select a run to view it; choose a second run to compare">
        <Async state={runs} isEmpty={(d) => !d.runs.length}>
          {(d) => (
            <Table rows={d.runs} caption="Optimization runs" rowKey={(r) => r.optimization_id} dense filterable={false} pageSize={8} exportName="orbit-optimization-runs"
              columns={[
                { key: "t", header: "Created", value: (r) => r.created_at, render: (r) => dateTime(r.created_at) },
                { key: "s", header: "Status", value: (r) => r.status, render: (r) => <StatusIndicator status={r.status} /> },
                { key: "p", header: "Parameters", sortable: false, value: (r) => paramText(r) },
                { key: "i", header: "Improvement", align: "right", value: (r) => r.improvement_pct, render: (r) => pct(r.improvement_pct, 2, true) },
                { key: "o", header: "Objective", align: "right", value: (r) => r.objective, render: (r) => money(r.objective) },
                { key: "a", header: "Actions", sortable: false, value: () => "", render: (r) => (
                  <span className="row">
                    <Button size="sm" variant={r.optimization_id === current ? "primary" : "secondary"} onClick={() => setSelected(r.optimization_id)} aria-label={`View run ${r.optimization_id}`}>View</Button>
                    <Button size="sm" variant={r.optimization_id === compare ? "primary" : "ghost"} disabled={r.optimization_id === current} onClick={() => setCompare(r.optimization_id === compare ? null : r.optimization_id)} aria-label={`Compare with run ${r.optimization_id}`}>Compare</Button>
                  </span>) },
              ]} />
          )}
        </Async>
      </Card>
    </Page>
  );
}

const paramText = (r: OptimizationRun) => `budget ${r.parameters.budget_multiplier}x, hires ${r.parameters.total_hires}, risk cap ${r.parameters.risk_cap_factor}, min share ${r.parameters.min_region_share}`;

function RunDetail({ id, compareId }: { id: string; compareId: string | null }) {
  const s = useApi(`opt-${id}`, () => api.optimizationRun(id));
  const c = useApi(compareId ? `opt-${compareId}` : null, () => api.optimizationRun(compareId!));
  return <Async state={s}>{(d) => <DetailBody d={d} other={compareId ? c.data : null} />}</Async>;
}

function DetailBody({ d, other }: { d: OptimizationDetail; other: OptimizationDetail | null }) {
  const { regionName } = useReference();
  const res = d.result.result;
  const regions = d.result.by_region.map((r) => ({ ...r, name: regionName(r.region_id) }));
  const cons = res.constraints;
  const consRows = [
    { name: "Hires", lhs: cons.hires.lhs, rhs: cons.hires.rhs, binding: Math.abs(cons.hires.lhs - cons.hires.rhs) < 1e-6, fmt: (v: number) => num(v) },
    { name: "Budget", lhs: cons.budget.lhs, rhs: cons.budget.rhs, binding: cons.budget.binding ?? false, fmt: (v: number) => money(v) },
    { name: "Risk cap", lhs: cons.risk_cap.lhs, rhs: cons.risk_cap.rhs, binding: cons.risk_cap.binding ?? false, fmt: (v: number) => money(v) },
    ...Object.entries(cons.region_minimums).map(([k, v]) => ({ name: `Min spend ${regionName(k)}`, lhs: v.lhs, rhs: v.rhs, binding: Math.abs(v.lhs - v.rhs) / Math.max(1, v.rhs) < 1e-6, fmt: (x: number) => money(x) })),
  ];
  return (
    <>
      <Card title="Result" subtitle={`${d.optimization_id}, solved by ${res.engine} in ${num(res.solve_seconds, 3)} s, MIP gap ${num(res.mip_gap, 4)}`} actions={<StatusIndicator status={d.status} />}>
        <div className="metrics" data-testid="optimization-result">
          <Metric label="Optimized objective" unit="currency" value={d.objective} />
          <Metric label="Baseline objective" unit="currency" value={d.baseline_objective} note="Pro-rata allocation, same budget" />
          <Metric label="Impact" unit="currency" value={d.improvement_abs} deltas={[{ label: "vs baseline", value: d.improvement_pct }]} />
          <Metric label="Budget" unit="currency" value={res.budget} note={paramText(d)} />
        </div>
        {other && (
          <div className="notice" style={{ marginTop: 10 }} data-testid="optimization-compare">
            Compared with run {other.optimization_id} ({paramText(other)}): objective {money(other.objective)} ({pct(other.improvement_pct, 2, true)} vs its baseline).
            Difference: <strong>{money(d.objective - other.objective)}</strong> ({pct(other.objective ? d.objective / other.objective - 1 : null, 2, true)}).
          </div>
        )}
      </Card>
      <Card title="Baseline vs optimized allocation" subtitle="Marketing spend by region">
        <ChartContainer title="Spend by region" description="Baseline pro-rata spend compared with optimized spend per region." height={220}
          legend={<Legend items={[{ label: "Baseline", color: HEX.c6 }, { label: "Optimized", color: HEX.c1 }, ...(other ? [{ label: "Compared run", color: HEX.c2 }] : [])]} />}
          table={<MiniTable head={["Region", "Baseline", "Optimized", "Change", "Hires"]} rows={regions.map((r) => [r.name, money(r.baseline_spend), money(r.optimized_spend), pct(r.spend_change_pct, 1, true), `${r.baseline_hires} to ${r.optimized_hires}`])} />}>
          <ResponsiveContainer>
            <BarChart data={regions.map((r) => ({ ...r, compared: other?.result.by_region.find((x) => x.region_id === r.region_id)?.optimized_spend }))}>
              <CartesianGrid stroke={HEX.grid} vertical={false} /><XAxis dataKey="name" {...axis} interval={0} tick={{ fontSize: 10, fill: "#4a5666" }} /><YAxis tickFormatter={moneyTick} {...axis} width={56} />
              <RTooltip content={<ChartTip />} />
              <Bar dataKey="baseline_spend" name="Baseline" fill={HEX.c6} isAnimationActive={false} />
              <Bar dataKey="optimized_spend" name="Optimized" fill={HEX.c1} isAnimationActive={false} />
              {other && <Bar dataKey="compared" name="Compared run" fill={HEX.c2} isAnimationActive={false} />}
            </BarChart>
          </ResponsiveContainer>
        </ChartContainer>
      </Card>
      <Card title="Constraints" subtitle="Left-hand side vs limit; binding constraints limit the objective">
        <Table rows={consRows} caption="Optimization constraints" rowKey={(r) => r.name} filterable={false} dense pageSize={12}
          columns={[{ key: "n", header: "Constraint", value: (r) => r.name }, { key: "l", header: "Value", align: "right", value: (r) => r.lhs, render: (r) => r.fmt(r.lhs) },
            { key: "r", header: "Limit", align: "right", value: (r) => r.rhs, render: (r) => r.fmt(r.rhs) },
            { key: "b", header: "State", value: (r) => (r.binding ? "Binding" : "Slack"), render: (r) => r.binding ? <Badge tone="warn">Binding</Badge> : <Badge>Slack</Badge> }]} />
        <p className="small muted" style={{ marginTop: 8 }}>Assumptions: {Object.entries(d.result.assumptions).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k.replace(/_/g, " ")} = ${String(v)}`).join("; ")}.</p>
      </Card>
    </>
  );
}
