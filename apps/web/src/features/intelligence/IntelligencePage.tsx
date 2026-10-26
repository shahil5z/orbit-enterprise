import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ChartTip, HEX, MiniTable, axis, moneyTick } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Card, ChartContainer, Drawer, Metric, Table, Tabs, Tooltip, type Column } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { FILTER_KEYS, pick, useFilters, type FilterKey } from "../../hooks/useFilters";
import { useReference } from "../../hooks/useReference";
import { api, qs } from "../../services/api";
import type { GroupRow, Intelligence } from "../../types/api";
import { money, month, num, pct } from "../../utils/format";

type Dim = "by_region" | "by_business_unit" | "by_segment" | "by_channel" | "top_products";
const DIMS: { id: Dim; label: string; filter?: FilterKey }[] = [
  { id: "by_region", label: "Region", filter: "region_id" }, { id: "by_business_unit", label: "Business unit", filter: "bu_id" },
  { id: "by_segment", label: "Segment", filter: "segment" }, { id: "by_channel", label: "Channel" }, { id: "top_products", label: "Top products", filter: "product_id" },
];

export default function IntelligencePage() {
  const { filters } = useFilters();
  const q = pick(filters, FILTER_KEYS);
  const s = useApi(`intelligence${qs(q)}`, () => api.intelligence(q));
  return (
    <Page title="Business Intelligence" intro="Every figure is computed by the API from the warehouse for the selected filters. The comparison period is the immediately preceding period of equal length.">
      <Async state={s} loadingRows={8} isEmpty={(d) => !d.monthly.length}>{(d) => <Body d={d} />}</Async>
    </Page>
  );
}

function Body({ d }: { d: Intelligence }) {
  const { kpis } = useReference();
  const { setFilter } = useFilters();
  const [dim, setDim] = useState<Dim>("by_region");
  const [detail, setDetail] = useState<GroupRow | null>(null);
  const def = DIMS.find((x) => x.id === dim)!;
  const rows = d[dim];
  const total = rows.reduce((a, r) => a + r.revenue, 0);
  const c = d.comparison;
  const cols: Column<GroupRow>[] = [
    { key: "label", header: def.label, value: (r) => r.label },
    { key: "revenue", header: "Revenue", align: "right", value: (r) => r.revenue, render: (r) => money(r.revenue) },
    { key: "share", header: "Share", align: "right", value: (r) => (total ? r.revenue / total : 0), render: (r) => pct(total ? r.revenue / total : null) },
    { key: "gm", header: "Gross margin", align: "right", value: (r) => r.gross_margin, render: (r) => money(r.gross_margin) },
    { key: "gmp", header: "GM %", align: "right", value: (r) => (r.revenue ? r.gross_margin / r.revenue : null), render: (r) => pct(r.revenue ? r.gross_margin / r.revenue : null) },
    { key: "txn", header: "Transactions", align: "right", value: (r) => r.transactions, render: (r) => num(r.transactions) },
    { key: "cust", header: "Customers", align: "right", value: (r) => r.customers, render: (r) => num(r.customers) },
  ];
  return (
    <>
      <p className="small muted">Comparison period: {d.comparison_period.start} to {d.comparison_period.end}.</p>
      <div className="metrics">
        <Metric kpi={kpis.revenue} value={c.revenue.current} deltas={[{ label: "vs prior period", value: c.revenue.change }]} />
        <Metric kpi={kpis.gross_margin} value={c.gross_margin.current} deltas={[{ label: "vs prior period", value: c.gross_margin.change }]} />
        <Metric kpi={kpis.txn_count} value={c.transactions.current} deltas={[{ label: "vs prior period", value: c.transactions.change }]} />
        <Metric kpi={kpis.active_customers} value={c.customers.current} deltas={[{ label: "vs prior period", value: c.customers.change }]} />
      </div>
      <Card title="Monthly trend" subtitle="Revenue for the current filter selection">
        <ChartContainer title="Revenue by month" description="Monthly revenue for the filtered transactions." height={220}
          table={<MiniTable head={["Month", "Revenue", "Gross margin", "Transactions"]} rows={d.monthly.map((m) => [month(m.month), money(m.revenue), money(m.gross_margin), num(m.transactions)])} />}>
          <ResponsiveContainer>
            <LineChart data={d.monthly}><CartesianGrid stroke={HEX.grid} vertical={false} />
              <XAxis dataKey="month" tickFormatter={month} {...axis} minTickGap={24} /><YAxis tickFormatter={moneyTick} {...axis} width={56} />
              <RTooltip content={<ChartTip labelFmt={month} />} />
              <Line dataKey="revenue" name="Revenue" stroke={HEX.c1} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="gross_margin" name="Gross margin" stroke={HEX.c3} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartContainer>
      </Card>
      <Card title="Drill-down" subtitle="Select a row for details; apply it as a global filter to drill further">
        <Tabs label="Breakdown dimension" tabs={DIMS.map((x) => ({ id: x.id, label: x.label }))} active={dim} onChange={(id) => setDim(id as Dim)}>
          <div className="grid g-1-2">
            <ChartContainer title={`Revenue by ${def.label.toLowerCase()}`} description="Bar length is revenue in the filtered period." height={Math.max(160, rows.length * 26)}>
              <ResponsiveContainer>
                <BarChart data={rows.slice(0, 12)} layout="vertical" margin={{ left: 4, right: 12 }}>
                  <XAxis type="number" tickFormatter={moneyTick} {...axis} /><YAxis type="category" dataKey="label" width={130} {...axis} />
                  <RTooltip content={<ChartTip />} /><Bar dataKey="revenue" name="Revenue" fill={HEX.c1} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </ChartContainer>
            <Table rows={rows} columns={cols} caption={`Revenue by ${def.label}`} rowKey={(r) => r.key} onRowClick={setDetail} exportName={`orbit-${dim}`} initialSort={{ key: "revenue", dir: "desc" }} dense />
          </div>
        </Tabs>
      </Card>
      <div className="grid g-2">
        <Card title="Incidents by category" subtitle="Ops category filter applies here">
          <Table rows={d.incidents.by_category} caption="Incidents by category" rowKey={(r) => r.key} filterable={false} dense
            columns={[{ key: "k", header: "Category", value: (r) => r.key }, { key: "n", header: "Incidents", align: "right", value: (r) => r.incidents },
              { key: "c", header: "Cost impact", align: "right", value: (r) => r.cost, render: (r) => money(r.cost) }]} />
        </Card>
        <Card title="Customer behaviour segments" subtitle={`K-means, k=${d.behaviour_segments.k}`}
          actions={<Tooltip label="About behaviour segments" content={<>Clusters on {d.behaviour_segments.features.join(", ")}. Silhouette by k: {Object.entries(d.behaviour_segments.silhouette_by_k).map(([k, v]) => `${k}: ${Number(v).toFixed(3)}`).join(", ")}.</>} />}>
          <Table rows={d.behaviour_segments.profiles} caption="Behaviour segments" rowKey={(r) => String(r.cluster)} filterable={false} dense
            columns={[{ key: "l", header: "Segment", value: (r) => r.label }, { key: "n", header: "Customers", align: "right", value: (r) => r.customers },
              { key: "m", header: "Avg monetary", align: "right", value: (r) => r.avg_monetary, render: (r) => money(r.avg_monetary) },
              { key: "f", header: "Avg frequency", align: "right", value: (r) => r.avg_frequency, render: (r) => num(r.avg_frequency, 1) },
              { key: "c", header: "Churn rate", align: "right", value: (r) => r.churn_rate, render: (r) => pct(r.churn_rate) }]} />
        </Card>
      </div>
      <Drawer open={detail !== null} title={detail ? `${def.label}: ${detail.label}` : ""} onClose={() => setDetail(null)}>
        {detail && (
          <>
            <dl className="kv">
              <dt>Revenue</dt><dd>{money(detail.revenue)} ({pct(total ? detail.revenue / total : null)} of selection)</dd>
              <dt>Gross margin</dt><dd>{money(detail.gross_margin)} ({pct(detail.revenue ? detail.gross_margin / detail.revenue : null)})</dd>
              <dt>Transactions</dt><dd>{num(detail.transactions)}</dd>
              <dt>Customers</dt><dd>{num(detail.customers)}</dd>
              <dt>Revenue per transaction</dt><dd>{money(detail.transactions ? detail.revenue / detail.transactions : null)}</dd>
            </dl>
            {def.filter ? (
              <button className="btn btn-primary btn-md" onClick={() => { setFilter(def.filter!, detail.key); setDetail(null); }}>Drill into {detail.label}</button>
            ) : <p className="small muted">Channel is not a global filter; it is shown for context only.</p>}
          </>
        )}
      </Drawer>
    </>
  );
}
