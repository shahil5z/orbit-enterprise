import { useCallback, useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ChartTip, HEX, Legend, MiniTable, axis, moneyTick } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Badge, Button, Card, ChartContainer, ErrorState, Table } from "../../components/ui";
import { useApi, useMutation } from "../../hooks/useApi";
import { api } from "../../services/api";
import type { LeverKey, ScenarioResult, ScenarioSide } from "../../types/api";
import { money, pct } from "../../utils/format";

const LABELS: Record<LeverKey, string> = {
  demand_change: "Demand", cost_change: "Unit cost", capacity_change: "Capacity", workforce_change: "Workforce",
  marketing_budget_change: "Marketing budget", churn_change: "Customer churn",
};
const ORDER = Object.keys(LABELS) as LeverKey[];
const ZERO = Object.fromEntries(ORDER.map((k) => [k, 0])) as Record<LeverKey, number>;
const SIDES: [keyof ScenarioSide, string][] = [["revenue", "Revenue"], ["gross_margin", "Gross margin"], ["opex", "Operating expense"], ["operating_profit", "Operating profit"], ["p5", "Revenue P5 (sum of regions)"], ["cvar95", "CVaR95 (sum of regions)"]];

export default function ScenarioPage() {
  const base = useApi("scenario-baseline", api.scenarioBaseline);
  return (
    <Page title="Scenario Lab" intro="Move the levers; the backend recomputes the 6-month outlook per region. Results are a SCENARIO against the forecast BASELINE, built on stated planning assumptions, not a causal model.">
      <Async state={base}>{(b) => <Lab baseline={b} />}</Async>
    </Page>
  );
}

function Lab({ baseline }: { baseline: ScenarioResult }) {
  const [levers, setLevers] = useState<Record<LeverKey, number>>(ZERO);
  const m = useMutation(useCallback((p: Record<LeverKey, number>) => api.runScenario(p), []));
  const first = useRef(true);
  const { run } = m;
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const t = setTimeout(() => void run(levers), 300);
    return () => clearTimeout(t);
  }, [levers, run]);
  const r = m.data ?? baseline;
  const changed = ORDER.some((k) => levers[k] !== 0);
  return (
    <div className="grid g-1-2">
      <Card title="Levers" subtitle="Relative change vs baseline">
        <div className="grid" style={{ gap: 14 }}>
          {ORDER.map((k) => {
            const l = baseline.levers[k];
            return (
              <div className="lever" key={k}>
                <label htmlFor={`lv-${k}`}>{LABELS[k]}</label>
                <output htmlFor={`lv-${k}`}>{pct(levers[k], 0, true)}</output>
                <input id={`lv-${k}`} type="range" min={l.min} max={l.max} step={0.01} value={levers[k]} style={{ gridColumn: "1 / -1" }}
                  aria-describedby={`lv-${k}-d`} onChange={(e) => setLevers({ ...levers, [k]: Number(e.target.value) })} />
                <span className="lever-desc" id={`lv-${k}-d`}>{l.description}</span>
              </div>
            );
          })}
          <div className="row"><Button onClick={() => setLevers(ZERO)} disabled={!changed}>Reset to baseline</Button>
            {m.status === "loading" && <span className="small muted" role="status">Recomputing</span>}</div>
          {m.status === "error" && m.error && <ErrorState title="Scenario failed" error={m.error} onRetry={() => void run(levers)} />}
        </div>
      </Card>
      <div className="grid">
        <div className="notice notice-scenario" role="note"><Badge tone="scenario">SCENARIO</Badge> vs <Badge>BASELINE</Badge> {r.baseline_label}. {changed ? "" : "All levers at zero: scenario equals baseline."}</div>
        <Card title="Scenario vs baseline" subtitle="6-month totals">
          <Table rows={SIDES} caption="Scenario totals" rowKey={([k]) => k} filterable={false} dense
            columns={[{ key: "m", header: "Measure", value: ([, l]) => l },
              { key: "b", header: "Baseline", align: "right", value: ([k]) => r.totals.baseline[k], render: ([k]) => money(r.totals.baseline[k]) },
              { key: "s", header: "Scenario", align: "right", value: ([k]) => r.totals.scenario[k], render: ([k]) => <strong data-testid={`scenario-${k}`}>{money(r.totals.scenario[k])}</strong> },
              { key: "d", header: "Change", align: "right", value: ([k]) => r.delta[k], render: ([k]) => `${money(r.delta[k])} (${pct(r.delta_pct[k], 1, true)})` }]} />
          {r.capacity_bound_regions.length > 0 && <p className="small" style={{ marginTop: 8 }}><Badge tone="warn">Capacity bound</Badge> Demand exceeds capacity in: {r.capacity_bound_regions.join(", ")}. Revenue is capped there.</p>}
        </Card>
        <Card title="By region">
          <ChartContainer title="Operating profit by region" description="Baseline and scenario operating profit per region." height={200}
            legend={<Legend items={[{ label: "Baseline", color: HEX.c6 }, { label: "Scenario", color: HEX.scenario }]} />}
            table={<MiniTable head={["Region", "Baseline OP", "Scenario OP", "Utilization", "Capacity bound"]} rows={r.regions.map((x) => [x.name, money(x.baseline.operating_profit), money(x.scenario.operating_profit), pct(x.scenario.utilization), x.scenario.capacity_bound ? "Yes" : "No"])} />}>
            <ResponsiveContainer>
              <BarChart data={r.regions.map((x) => ({ name: x.name, baseline: x.baseline.operating_profit, scenario: x.scenario.operating_profit }))}>
                <CartesianGrid stroke={HEX.grid} vertical={false} /><XAxis dataKey="name" {...axis} interval={0} tick={{ fontSize: 10, fill: "#4a5666" }} /><YAxis tickFormatter={moneyTick} {...axis} width={56} />
                <RTooltip content={<ChartTip />} />
                <Bar dataKey="baseline" name="Baseline" fill={HEX.c6} isAnimationActive={false} /><Bar dataKey="scenario" name="Scenario" fill={HEX.scenario} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartContainer>
        </Card>
        <Card title="Assumptions"><dl className="kv">{Object.entries(r.assumptions).map(([k, v]) => [<dt key={`${k}t`}>{k.replace(/_/g, " ")}</dt>, <dd key={`${k}d`}>{String(v)}</dd>])}</dl></Card>
      </div>
    </div>
  );
}
