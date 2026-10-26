import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ChartTip, HEX, Legend, MiniTable, axis } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Card, ChartContainer, Metric, Table } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { pick, useFilters } from "../../hooks/useFilters";
import { useReference } from "../../hooks/useReference";
import { api, qs } from "../../services/api";
import type { OpsSummary } from "../../types/api";
import { money, month, num, pct } from "../../utils/format";

const KPI_MAP: [string, string, string, boolean][] = [
  ["orders", "Orders processed", "count", true], ["fulfillment_hours", "Fulfillment time", "hours", false], ["uptime_pct", "Uptime %", "score", true],
  ["tickets", "Support tickets", "count", false], ["headcount", "Headcount (avg)", "count", true], ["orders_per_head", "Orders per head", "ratio", true], ["opex", "Operating expense", "currency", false],
];

export default function OperationsPage() {
  const { filters } = useFilters();
  const q = pick(filters, ["region_id", "bu_id", "category"]);
  const s = useApi(`ops${qs(q)}`, () => api.operations(q));
  return <Page title="Operations"><Async state={s} isEmpty={(d) => !d.monthly.length}>{(d) => <Body d={d} />}</Async></Page>;
}

function Body({ d }: { d: OpsSummary }) {
  const { regionName } = useReference();
  const series = useMemo(() => {
    const rows: Record<string, number | string | null>[] = d.monthly.map((m) => ({ month: m.month, orders: m.orders, target: m.orders_target, capacity: Math.round(m.capacity) }));
    for (const f of d.orders_forecast) rows.push({ month: f.month, forecast: Math.round(f.orders_forecast) });
    const last = d.monthly[d.monthly.length - 1];
    if (last && rows[d.monthly.length - 1]) rows[d.monthly.length - 1]!.forecast = last.orders;
    return rows;
  }, [d]);
  const last = d.monthly[d.monthly.length - 1];
  return (
    <>
      <p className="small muted">Latest month {month(d.latest_month)}, compared with the same month last year.</p>
      <div className="metrics">
        {KPI_MAP.map(([k, label, unit, hib]) => {
          const v = d.kpis[k];
          return v ? <Metric key={k} label={label} unit={unit as "count"} higherIsBetter={hib} value={v.current} deltas={[{ label: "YoY", value: v.yoy }]} /> : null;
        })}
        {last && <Metric label="Capacity utilization" unit="percent" value={last.utilization} higherIsBetter={false} note="Orders / modelled capacity" />}
      </div>
      <Card title="Orders: actual vs target vs forecast" subtitle="Target = prior year +3%. Capacity = p95 orders per head (24 months) x headcount. Forecast = seasonal naive, 3 months.">
        <ChartContainer title="Orders actual, target, capacity and forecast" description="Monthly orders processed against target, modelled capacity and a 3-month forecast." height={280}
          legend={<Legend items={[{ label: "Actual", color: HEX.c1 }, { label: "Target", color: HEX.c2, kind: "dash" }, { label: "Capacity", color: HEX.c6, kind: "dash" }, { label: "Forecast", color: HEX.c4, kind: "dash" }]} />}
          table={<MiniTable head={["Month", "Actual", "Target", "Capacity", "Forecast"]} rows={series.map((r) => [month(String(r.month)), num(r.orders as number), num(r.target as number), num(r.capacity as number), num(r.forecast as number)])} />}>
          <ResponsiveContainer>
            <ComposedChart data={series}><CartesianGrid stroke={HEX.grid} vertical={false} />
              <XAxis dataKey="month" tickFormatter={month} {...axis} minTickGap={24} /><YAxis tickFormatter={(v: number) => num(v)} {...axis} width={56} />
              <RTooltip content={<ChartTip labelFmt={month} fmt={(v) => num(v)} />} />
              <Line dataKey="orders" name="Actual" stroke={HEX.c1} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="target" name="Target" stroke={HEX.c2} strokeDasharray="5 3" dot={false} isAnimationActive={false} />
              <Line dataKey="capacity" name="Capacity" stroke={HEX.c6} strokeDasharray="2 3" dot={false} isAnimationActive={false} />
              <Line dataKey="forecast" name="Forecast" stroke={HEX.c4} strokeDasharray="6 3" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartContainer>
      </Card>
      <div className="grid g-2">
        <Card title="Workload and capacity" subtitle="Headcount and utilization by month">
          <Table rows={[...d.monthly].reverse()} caption="Workload by month" rowKey={(m) => m.month} filterable={false} pageSize={6} dense exportName="orbit-ops-monthly"
            columns={[{ key: "m", header: "Month", value: (m) => m.month, render: (m) => month(m.month) },
              { key: "o", header: "Orders", align: "right", value: (m) => m.orders, render: (m) => num(m.orders) },
              { key: "h", header: "Headcount", align: "right", value: (m) => m.headcount, render: (m) => num(m.headcount) },
              { key: "u", header: "Utilization", align: "right", value: (m) => m.utilization, render: (m) => pct(m.utilization) },
              { key: "f", header: "Fulfillment h", align: "right", value: (m) => m.fulfillment_hours, render: (m) => num(m.fulfillment_hours, 1) },
              { key: "up", header: "Uptime %", align: "right", value: (m) => m.uptime_pct, render: (m) => num(m.uptime_pct, 2) }]} />
        </Card>
        <Card title="Incidents" subtitle="By severity, latest data">
          <ChartContainer title="Incidents per month" description="All incidents and major (SEV1 and SEV2) incidents per month." height={160}
            table={<MiniTable head={["Month", "Incidents", "Major", "MTTR h"]} rows={d.incidents.monthly.map((m) => [month(m.month), m.incidents, m.major, num(m.mttr_hours, 1)])} />}>
            <ResponsiveContainer>
              <BarChart data={d.incidents.monthly}><XAxis dataKey="month" tickFormatter={month} {...axis} minTickGap={30} /><YAxis allowDecimals={false} {...axis} width={28} />
                <RTooltip content={<ChartTip labelFmt={month} fmt={(v) => num(v, 1)} />} />
                <Bar dataKey="incidents" name="Incidents" fill={HEX.c6} isAnimationActive={false} /><Bar dataKey="major" name="Major" fill={HEX.c5} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartContainer>
          <Table rows={d.incidents.by_severity} caption="Incidents by severity" rowKey={(r) => r.key} filterable={false} dense
            columns={[{ key: "k", header: "Severity", value: (r) => r.key }, { key: "n", header: "Count", align: "right", value: (r) => r.incidents },
              { key: "o", header: "Open", align: "right", value: (r) => r.open }, { key: "mt", header: "MTTR h", align: "right", value: (r) => r.mttr_hours, render: (r) => num(r.mttr_hours, 1) },
              { key: "c", header: "Cost", align: "right", value: (r) => r.cost, render: (r) => money(r.cost) }]} />
        </Card>
      </div>
      <Card title="Bottlenecks" subtitle="Units ranked by fulfillment time z-score vs all units (last 90 days)">
        <Table rows={d.bottlenecks} caption="Operational bottlenecks" rowKey={(b) => `${b.region_id}-${b.bu_id}`} exportName="orbit-bottlenecks" initialSort={{ key: "z", dir: "desc" }} dense
          columns={[{ key: "u", header: "Unit", value: (b) => `${b.region_name || regionName(b.region_id)} / ${b.bu_name}` },
            { key: "f", header: "Fulfillment h", align: "right", value: (b) => b.fulfillment_hours, render: (b) => num(b.fulfillment_hours, 1) },
            { key: "z", header: "z-score", align: "right", value: (b) => b.fulfillment_z, render: (b) => num(b.fulfillment_z, 2) },
            { key: "up", header: "Uptime %", align: "right", value: (b) => b.uptime_pct, render: (b) => num(b.uptime_pct, 2) },
            { key: "t", header: "Tickets / 1k orders", align: "right", value: (b) => b.tickets_per_1k_orders, render: (b) => num(b.tickets_per_1k_orders, 1) },
            { key: "o", header: "Orders / head / day", align: "right", value: (b) => b.orders_per_head_day, render: (b) => num(b.orders_per_head_day, 2) }]} />
      </Card>
      <Card title="Assumptions">
        <dl className="kv">{Object.entries(d.assumptions).map(([k, v]) => [<dt key={`${k}t`}>{k.replace(/_/g, " ")}</dt>, <dd key={`${k}d`}>{String(v)}</dd>])}</dl>
      </Card>
    </>
  );
}
