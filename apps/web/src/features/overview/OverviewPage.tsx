import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ExportButton } from "../../components/shared/ExportButton";
import { ChartTip, HEX, Legend, MiniTable, axis, moneyTick } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Badge, Card, ChartContainer, Metric, RiskBadge, Table, type Column } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { api } from "../../services/api";
import type { Overview, RegionPerf } from "../../types/api";
import { money, month, num, pct } from "../../utils/format";

const Q_KEYS = [["revenue", "revenue"], ["gross_margin", "gross_margin"], ["operating_profit", "operating_profit"], ["opex", "opex"], ["transactions", "txn_count"], ["incidents", "incident_count"]] as const;

export default function OverviewPage() {
  const s = useApi("overview", api.overview);
  return (
    <Page title="Executive Overview">
      <Async state={s} loadingRows={8}>{(d) => <OverviewBody d={d} />}</Async>
    </Page>
  );
}

function OverviewBody({ d }: { d: Overview }) {
  const { kpis } = useReference();
  const q = d.quarter_comparison;
  const period = q.period;
  const regionCols: Column<RegionPerf>[] = [
    { key: "name", header: "Region", value: (r) => r.name ?? r.region_id, render: (r) => <Link to={`/risk?entity=${r.region_id}`}>{r.name ?? r.region_id}</Link> },
    { key: "revenue", header: "TTM revenue", align: "right", value: (r) => r.revenue, render: (r) => money(r.revenue) },
    { key: "growth", header: "YoY", align: "right", value: (r) => r.revenue_growth, render: (r) => <span className={r.revenue_growth < 0 ? "up-bad" : "up-good"}>{pct(r.revenue_growth, 1, true)}</span> },
    { key: "gm", header: "GM %", align: "right", value: (r) => r.gross_margin_pct, render: (r) => pct(r.gross_margin_pct) },
    { key: "om", header: "Op. margin", align: "right", value: (r) => r.operating_margin_pct, render: (r) => pct(r.operating_margin_pct) },
    { key: "share", header: "Share", align: "right", value: (r) => r.revenue_share, render: (r) => pct(r.revenue_share) },
    { key: "inc", header: "Incidents", align: "right", value: (r) => r.incidents },
  ];
  const buRows = d.by_business_unit.map((b) => ({ ...b, region_id: b.bu_id }));
  const buCols = regionCols.map((c) => c.key === "name" ? { ...c, header: "Business unit", render: (r: RegionPerf) => <Link to={`/intelligence?bu_id=${r.region_id}`}>{r.name ?? r.region_id}</Link> } : c);
  const declining = d.by_region.filter((r) => r.revenue_growth < 0).sort((a, b) => a.revenue_growth - b.revenue_growth);
  return (
    <>
      <div className="row between">
        <p className="small muted">
          As of {month(d.as_of_month)}. Quarter compared: {period ? `${month(period.current[0])} to ${month(period.current[period.current.length - 1])}` : "latest"} vs prior quarter
          {period ? ` (from ${month(period.prior_quarter_start)})` : ""} and same quarter last year{period ? ` (from ${month(period.same_quarter_last_year_start)})` : ""}. Run <code>{d.run_id}</code>.
        </p>
        <div className="row"><ExportButton kind="recommendations.csv" /><ExportButton kind="risk-report.md" /></div>
      </div>
      <h2 className="section-title">Trailing twelve months</h2>
      <div className="metrics" data-testid="ttm-kpis">
        <Metric kpi={kpis.revenue} value={d.ttm.revenue} deltas={[{ label: "vs prior TTM", value: d.ttm_revenue_growth }]} />
        <Metric kpi={kpis.gross_margin_pct} value={d.ttm.gross_margin_pct} deltas={[{ label: "pts vs prior TTM", value: d.ttm.gross_margin_pct - d.prior_ttm.gross_margin_pct }]} />
        <Metric kpi={kpis.operating_margin_pct} value={d.ttm.operating_margin_pct} deltas={[{ label: "pts vs prior TTM", value: d.ttm.operating_margin_pct - d.prior_ttm.operating_margin_pct }]} />
        <Metric kpi={kpis.incident_cost} value={d.ttm.incident_cost} deltas={[{ label: "vs prior TTM", value: d.prior_ttm.incident_cost ? d.ttm.incident_cost / d.prior_ttm.incident_cost - 1 : null }]} />
        <Metric kpi={kpis.var95} value={d.monte_carlo_total.var95} note="6-month horizon, Monte Carlo" />
        <Metric label="Open anomalies (flagged)" unit="count" value={d.anomaly_total} higherIsBetter={false} note="Isolation Forest, latest run" />
      </div>
      <h2 className="section-title">Latest quarter</h2>
      <div className="metrics">
        {Q_KEYS.map(([k, kk]) => {
          const c = q[k];
          if (!c) return null;
          return <Metric key={k} kpi={kpis[kk]} label={kpis[kk]?.name} value={c.current} deltas={[{ label: "QoQ", value: c.qoq }, { label: "YoY", value: c.yoy }]} />;
        })}
      </div>
      <div className="grid g-2-1">
        <Card title="Monthly revenue and operating profit" subtitle="Company total, 36 months">
          <ChartContainer title="Revenue trend" description="Monthly revenue and operating profit in USD."
            legend={<Legend items={[{ label: "Revenue", color: HEX.c1 }, { label: "Operating profit", color: HEX.c2 }]} />}
            table={<MiniTable head={["Month", "Revenue", "Operating profit"]} rows={d.monthly.map((m) => [month(m.period_month), money(m.revenue), money(m.operating_profit)])} />}>
            <ResponsiveContainer>
              <LineChart data={d.monthly} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={HEX.grid} vertical={false} />
                <XAxis dataKey="period_month" tickFormatter={month} {...axis} minTickGap={24} />
                <YAxis tickFormatter={moneyTick} {...axis} width={56} />
                <RTooltip content={<ChartTip labelFmt={month} />} />
                <Line type="monotone" dataKey="revenue" name="Revenue" stroke={HEX.c1} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="operating_profit" name="Operating profit" stroke={HEX.c2} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartContainer>
        </Card>
        <Card title="Declining regions" subtitle="TTM revenue growth below zero">
          {declining.length === 0 ? <p className="small muted">No region shows a TTM decline.</p> : (
            <ul className="list" data-testid="declining-regions">
              {declining.map((r) => (
                <li key={r.region_id} className="row between">
                  <span><strong>{r.name}</strong><br /><span className="small muted">TTM {money(r.revenue)} vs {money(r.prior_revenue)}</span></span>
                  <span className="row"><span className="up-bad">{"\u25BC"} {pct(r.revenue_growth, 1, true)}</span>
                    <Link className="btn btn-sm btn-secondary" style={{ textDecoration: "none" }} to={`/anomalies?region_id=${r.region_id}`} aria-label={`Investigate anomalies in ${r.name}`}>Investigate</Link></span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <div className="grid g-2">
        <Card title="Region performance" subtitle="TTM, sortable"><Table rows={d.by_region} columns={regionCols} caption="Region performance" rowKey={(r) => r.region_id} exportName="orbit-region-performance" filterable={false} initialSort={{ key: "revenue", dir: "desc" }} dense /></Card>
        <Card title="Business unit performance" subtitle="TTM, sortable">
          <ChartContainer title="Revenue by business unit" description="TTM revenue per business unit." height={150}
            table={<MiniTable head={["Business unit", "Revenue", "YoY"]} rows={d.by_business_unit.map((b) => [b.name, money(b.revenue), pct(b.revenue_growth, 1, true)])} />}>
            <ResponsiveContainer>
              <BarChart data={d.by_business_unit} layout="vertical" margin={{ left: 8, right: 12 }}>
                <XAxis type="number" tickFormatter={moneyTick} {...axis} />
                <YAxis type="category" dataKey="name" width={150} {...axis} />
                <RTooltip content={<ChartTip />} />
                <Bar dataKey="revenue" name="Revenue" fill={HEX.c1} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartContainer>
          <Table rows={buRows} columns={buCols} caption="Business unit performance" rowKey={(r) => r.region_id} filterable={false} dense />
        </Card>
      </div>
      <div className="grid g-3">
        <Card title="Top risks" actions={<Link to="/risk" className="small">All risks</Link>}>
          <ul className="list">{d.top_risks.map((r) => (
            <li key={`${r.region_id}-${r.bu_id}`}>
              <div className="row between"><Link to={`/risk?entity=${r.region_id}`}><strong>{r.region_id}{r.bu_id ? ` / ${r.bu_id}` : ""}</strong></Link><RiskBadge level={r.risk_level} score={r.risk_score} /></div>
              <p className="small muted">{r.recommended_action}</p>
            </li>))}</ul>
        </Card>
        <Card title="Top anomalies" subtitle={`${num(d.anomaly_total)} flagged in total`} actions={<Link to="/anomalies" className="small">Explore</Link>}>
          <ul className="list">{d.top_anomalies.map((a) => (
            <li key={a.operation_id} className="row between">
              <span><Link to={`/anomalies?id=${a.operation_id}`}>{a.region_id} / {a.bu_id}</Link> <span className="small muted">{a.op_date}</span></span>
              <span className="row"><span className="mono">{a.anomaly_score.toFixed(3)}</span>{a.labelled_anomaly === 1 && <Badge tone="bad">Confirmed</Badge>}</span>
            </li>))}</ul>
        </Card>
        <Card title="Recommended actions" actions={<Link to="/decisions" className="small">Decision center</Link>}>
          <ul className="list">{d.recommendations.slice(0, 4).map((r) => (
            <li key={r.decision_id}>
              <div className="row between"><strong>{r.scope === "company" ? "Company" : r.entity_id}</strong><RiskBadge level={r.priority} /></div>
              <p className="small">{r.recommendation}</p>
              <Link className="small" to={`/decisions?id=${encodeURIComponent(r.decision_id)}`}>Why?</Link>
            </li>))}</ul>
        </Card>
      </div>
    </>
  );
}
