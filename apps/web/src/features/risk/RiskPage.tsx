import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ExportButton } from "../../components/shared/ExportButton";
import { ChartTip, HEX, Legend, MiniTable, axis, moneyTick } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Card, ChartContainer, Drawer, Metric, RiskBadge, Table, type Column } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { api } from "../../services/api";
import type { MonteCarlo, Risk, RiskDetail, RiskLevel } from "../../types/api";
import { money, month, num, pct } from "../../utils/format";

const LEVELS: RiskLevel[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function RiskPage() {
  const s = useApi("risks", api.risks);
  return (
    <Page title="Risk" intro="Risk score 0 to 100 = weighted sum of normalized factors. Levels: LOW below 25, MEDIUM below 50, HIGH below 70, CRITICAL 70 and above. Confidence = data coverage x model quality.">
      <Async state={s} isEmpty={(d) => !d.risks.length}>{(d) => <Body risks={d.risks} mc={d.monte_carlo} />}</Async>
    </Page>
  );
}

function Body({ risks, mc }: { risks: Risk[]; mc: MonteCarlo }) {
  const { kpis, regionName, buName } = useReference();
  const [params, setParams] = useSearchParams();
  const entity = params.get("entity");
  const open = (id: string | null) => setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("entity", id); else n.delete("entity"); return n; });
  const dist = LEVELS.map((l) => ({ level: l, regions: risks.filter((r) => r.risk_level === l && r.entity_type === "region").length, units: risks.filter((r) => r.risk_level === l && r.entity_type === "business_unit").length }));
  const regions = risks.filter((r) => r.entity_type === "region");
  const exposure = Object.entries(mc.regions).map(([id, v]) => ({ id, name: regionName(id), ...v }));
  const cols: Column<Risk>[] = [
    { key: "e", header: "Entity", value: (r) => `${regionName(r.region_id)}${r.bu_id ? ` / ${buName(r.bu_id)}` : ""}` },
    { key: "t", header: "Type", value: (r) => (r.entity_type === "region" ? "Region" : "Business unit") },
    { key: "score", header: "Risk", align: "right", value: (r) => r.risk_score, render: (r) => <RiskBadge level={r.risk_level} score={r.risk_score} /> },
    { key: "top", header: "Top driver", value: (r) => [...r.risk_factors].sort((a, b) => b.contribution - a.contribution)[0]?.factor.replace(/_/g, " ") },
    { key: "c", header: "Confidence", align: "right", value: (r) => r.confidence, render: (r) => pct(r.confidence, 0) },
  ];
  const high = risks.filter((r) => r.risk_level === "HIGH" || r.risk_level === "CRITICAL").length;
  return (
    <>
      <div className="row between"><span /><div className="row"><ExportButton kind="risks.csv" /><ExportButton kind="risk-report.md" /></div></div>
      <div className="metrics">
        <Metric kpi={kpis.var95} value={mc.total.var95} note={`${num(mc.simulations)} simulations, ${mc.horizon_months} months, rho ${mc.rho}`} />
        <Metric kpi={kpis.cvar95} value={mc.total.cvar95} />
        <Metric label="Expected revenue (P50)" unit="currency" value={mc.total.p50} note={`P5 ${money(mc.total.p5)} to P95 ${money(mc.total.p95)}`} />
        <Metric label="High or critical entities" unit="count" value={high} higherIsBetter={false} note={`of ${risks.length} scored`} />
      </div>
      <div className="grid g-2">
        <Card title="Risk distribution" subtitle="Count of entities per level">
          <ChartContainer title="Entities by risk level" description="Regions and business units in each risk level." height={180}
            legend={<Legend items={[{ label: "Regions", color: HEX.c1 }, { label: "Business units", color: HEX.c2 }]} />}
            table={<MiniTable head={["Level", "Regions", "Business units"]} rows={dist.map((x) => [x.level, x.regions, x.units])} />}>
            <ResponsiveContainer>
              <BarChart data={dist}><CartesianGrid stroke={HEX.grid} vertical={false} /><XAxis dataKey="level" {...axis} /><YAxis allowDecimals={false} {...axis} width={30} />
                <RTooltip content={<ChartTip fmt={(v) => num(v)} />} />
                <Bar dataKey="regions" name="Regions" fill={HEX.c1} isAnimationActive={false} /><Bar dataKey="units" name="Business units" fill={HEX.c2} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartContainer>
        </Card>
        <Card title="Revenue exposure by region" subtitle="Monte Carlo 6-month VaR95 (shortfall vs expected)">
          <Table rows={exposure} caption="Exposure by region" rowKey={(r) => r.id} filterable={false} dense initialSort={{ key: "var", dir: "desc" }} onRowClick={(r) => open(r.id)}
            columns={[{ key: "n", header: "Region", value: (r) => r.name },
              { key: "e", header: "Expected", align: "right", value: (r) => r.expected, render: (r) => money(r.expected) },
              { key: "var", header: "VaR95", align: "right", value: (r) => r.var95, render: (r) => money(r.var95) },
              { key: "cv", header: "CVaR95", align: "right", value: (r) => r.cvar95, render: (r) => money(r.cvar95) },
              { key: "rl", header: "Level", value: (r) => regions.find((x) => x.region_id === r.id)?.risk_score ?? null,
                render: (r) => { const x = regions.find((y) => y.region_id === r.id); return x ? <RiskBadge level={x.risk_level} /> : "n/a"; } }]} />
        </Card>
      </div>
      <Card title="Risk register" subtitle="Select an entity to see drivers, evidence and the recommended action">
        <Table rows={risks} columns={cols} caption="Risk register" rowKey={(r) => `${r.region_id}-${r.bu_id ?? ""}`} onRowClick={(r) => open(r.region_id)} exportName="orbit-risk-register" initialSort={{ key: "score", dir: "desc" }} dense />
      </Card>
      <Drawer open={!!entity} title={entity ? `Risk drill-in: ${regionName(entity)}` : ""} onClose={() => open(null)} wide>
        {entity && <RiskPanel id={entity} />}
      </Drawer>
    </>
  );
}

function RiskPanel({ id }: { id: string }) {
  const s = useApi(`risk-${id}`, () => api.riskRegion(id));
  return <Async state={s}>{(d) => <RiskDetailView d={d} />}</Async>;
}

function RiskDetailView({ d }: { d: RiskDetail }) {
  const { buName } = useReference();
  const r = d.region;
  const factors = r ? [...r.risk_factors].sort((a, b) => b.contribution - a.contribution) : [];
  const worstSeg = [...d.churn_by_segment].sort((a, b) => b.avg_probability - a.avg_probability)[0];
  return (
    <div data-testid="risk-detail">
      {r && (
        <div className="row between">
          <RiskBadge level={r.risk_level} score={r.risk_score} />
          <span className="small muted">Confidence {pct(r.confidence, 0)}{d.monte_carlo ? `, VaR95 ${money(d.monte_carlo.var95)}` : ""}</span>
        </div>
      )}
      <Card title="Drivers" subtitle="Contribution in risk points = weight x normalized value x 100">
        <Table rows={factors} caption="Risk drivers" rowKey={(f) => f.factor} filterable={false} dense
          columns={[{ key: "f", header: "Factor", value: (f) => f.factor.replace(/_/g, " ") },
            { key: "d", header: "Meaning", value: (f) => f.description, sortable: false },
            { key: "raw", header: "Raw", align: "right", value: (f) => f.raw_value, render: (f) => num(f.raw_value, 3) },
            { key: "w", header: "Weight", align: "right", value: (f) => f.weight },
            { key: "c", header: "Points", align: "right", value: (f) => f.contribution, render: (f) => <strong>{num(f.contribution, 2)}</strong> }]} />
      </Card>
      <Card title="Driver trend" subtitle="Monthly revenue with flagged anomalies and major incidents (risk scores are snapshots; drivers are tracked over time)">
        <ChartContainer title="Driver trend" description="Revenue line with anomaly and major incident counts." height={200}
          legend={<Legend items={[{ label: "Revenue", color: HEX.c1 }, { label: "Anomalies", color: HEX.c5 }, { label: "Major incidents", color: HEX.c2 }]} />}
          table={<MiniTable head={["Month", "Revenue", "Anomalies", "Major incidents"]} rows={d.driver_trend.map((t) => [month(t.month), money(t.revenue), t.anomalies, t.major_incidents])} />}>
          <ResponsiveContainer>
            <ComposedChart data={d.driver_trend}><CartesianGrid stroke={HEX.grid} vertical={false} />
              <XAxis dataKey="month" tickFormatter={month} {...axis} minTickGap={24} />
              <YAxis yAxisId="l" tickFormatter={moneyTick} {...axis} width={56} /><YAxis yAxisId="r" orientation="right" allowDecimals={false} {...axis} width={28} />
              <RTooltip content={<ChartTip labelFmt={month} fmt={(v) => (v > 1000 ? money(v) : num(v))} />} />
              <Bar yAxisId="r" dataKey="anomalies" name="Anomalies" fill={HEX.c5} fillOpacity={0.6} isAnimationActive={false} />
              <Bar yAxisId="r" dataKey="major_incidents" name="Major incidents" fill={HEX.c2} isAnimationActive={false} />
              <Line yAxisId="l" dataKey="revenue" name="Revenue" stroke={HEX.c1} strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartContainer>
      </Card>
      <Card title="Churn risk by customer segment" subtitle={worstSeg ? `Highest average churn probability: ${worstSeg.segment}` : undefined}>
        <Table rows={d.churn_by_segment} caption="Churn by segment" rowKey={(x) => x.segment} filterable={false} dense initialSort={{ key: "p", dir: "desc" }}
          columns={[{ key: "s", header: "Segment", value: (x) => x.segment }, { key: "c", header: "Customers", align: "right", value: (x) => x.customers },
            { key: "pc", header: "Predicted to churn", align: "right", value: (x) => x.predicted_churn },
            { key: "p", header: "Avg probability", align: "right", value: (x) => x.avg_probability, render: (x) => pct(x.avg_probability) }]} />
        <Table rows={d.top_churn_customers} caption="Highest churn probability customers" rowKey={(x) => x.customer_id} filterable={false} pageSize={5} dense exportName={`orbit-churn-${d.region_id}`}
          columns={[{ key: "n", header: "Customer", value: (x) => x.name }, { key: "s", header: "Segment", value: (x) => x.segment }, { key: "i", header: "Industry", value: (x) => x.industry },
            { key: "p", header: "Churn prob.", align: "right", value: (x) => x.churn_probability, render: (x) => pct(x.churn_probability) },
            { key: "sat", header: "Satisfaction", align: "right", value: (x) => x.satisfaction_score, render: (x) => num(x.satisfaction_score, 1) }]} />
      </Card>
      <Card title="Business units in this region">
        <ul className="list">{d.business_units.map((b) => <li key={b.bu_id} className="row between"><span>{buName(b.bu_id)}</span><RiskBadge level={b.risk_level} score={b.risk_score} /></li>)}</ul>
      </Card>
      {d.recommendation ? (
        <Card title="Evidence and recommended action">
          <ul className="list" data-testid="risk-evidence">{d.recommendation.evidence.map((e) => <li key={e.ref} className="small"><code>{e.ref}</code> = <strong>{String(e.value)}</strong> <span className="muted">({e.source})</span></li>)}</ul>
          <p data-testid="risk-recommendation"><strong>Recommendation:</strong> {d.recommendation.recommendation}</p>
          <p className="small muted">{d.recommendation.expected_impact}</p>
          <Link className="btn btn-primary btn-md" style={{ textDecoration: "none", alignSelf: "flex-start" }} to={`/decisions?id=${encodeURIComponent(d.recommendation.decision_id)}`}>Open decision trace</Link>
        </Card>
      ) : <p className="small muted">No recommendation was generated for this region in the latest run.</p>}
    </div>
  );
}
