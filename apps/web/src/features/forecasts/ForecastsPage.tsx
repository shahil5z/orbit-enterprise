import { Fragment, useMemo } from "react";
import { Link } from "react-router-dom";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { ChartTip, HEX, Legend, MiniTable, axis, moneyTick } from "../../components/shared/charts";
import { Page } from "../../components/shared/Page";
import { Async, Badge, Card, ChartContainer, Metric, Select, Table } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useFilters } from "../../hooks/useFilters";
import { useReference } from "../../hooks/useReference";
import { api } from "../../services/api";
import type { ForecastSeries } from "../../types/api";
import { money, month, pct } from "../../utils/format";

export default function ForecastsPage() {
  const { filters, setFilter } = useFilters();
  const { dims } = useReference();
  const region = filters.region_id;
  const s = useApi(`fc-${region ?? "ALL"}`, () => api.forecastSeries(region));
  return (
    <Page title="Forecasts">
      <div className="filterbar" aria-label="Forecast target">
        <Select label="Target metric" value="revenue" allLabel={null} onChange={() => undefined} options={[{ value: "revenue", label: "Revenue (monthly, USD)" }]} />
        <Select label="Target entity" value={region} allLabel="Company total" onChange={(v) => setFilter("region_id", v)}
          options={(dims?.regions ?? []).map((r) => ({ value: r.id, label: r.name }))} />
        <span className="muted small" style={{ alignSelf: "center" }}>Revenue is the only forecast target trained in this release.</span>
      </div>
      <Async state={s} isEmpty={(d) => !d.history.length}>{(d) => <Body d={d} />}</Async>
    </Page>
  );
}

function Body({ d }: { d: ForecastSeries }) {
  const { kpis, regionName } = useReference();
  const data = useMemo(() => {
    const m = new Map<string, Record<string, number | number[] | string>>();
    for (const h of d.history) m.set(h.month, { month: h.month, actual: h.actual });
    for (const b of d.backtest) Object.assign(m.get(b.month) ?? m.set(b.month, { month: b.month }).get(b.month)!, { backtest: b.prediction, naive: b.seasonal_naive });
    const last = d.history[d.history.length - 1];
    if (last) Object.assign(m.get(last.month)!, { forecast: last.actual, band: [last.actual, last.actual] });
    for (const f of d.forecast) m.set(f.month, { month: f.month, forecast: f.forecast, band: [f.lower_80, f.upper_80] });
    return [...m.values()].sort((a, b) => String(a.month).localeCompare(String(b.month)));
  }, [d]);
  const total = d.forecast.reduce((a, f) => a + f.forecast, 0);
  const last6 = d.history.slice(-6).reduce((a, h) => a + h.actual, 0);
  const acc = d.accuracy;
  const reg = d.region_id ? d.accuracy_by_region[d.region_id] : undefined;
  const beats = reg ? reg.mape < reg.naive_mape : acc.model.mape < acc.seasonal_naive.mape;
  const scope = reg ? "in this region (test)" : "overall (test)";
  return (
    <>
      <div className="metrics">
        <Metric label={`${d.horizon_months}-month forecast`} unit="currency" value={total} deltas={[{ label: "vs last 6 months actual", value: last6 ? total / last6 - 1 : null }]} />
        <Metric kpi={kpis.forecast_mape} label="Model MAPE (test, all regions)" value={acc.model.mape} note={`n=${acc.model.n} region-months`} />
        <Metric label="Seasonal naive MAPE" unit="percent" value={acc.seasonal_naive.mape} higherIsBetter={false} note="Baseline: same month last year" />
        <Metric label="Model bias (test)" unit="currency" value={acc.model.bias} note="Positive means over-forecast" />
      </div>
      <Card title={`Revenue: ${d.region_id ? regionName(d.region_id) : "Company total"}`} subtitle={`Model ${d.model_version} (${d.algorithm}). ${d.band}${d.region_id ? "" : ". Company band is the sum of regional bounds, a conservative envelope."}`}
        actions={<span className="row">{d.region_id && <Link className="small" to={`/risk?entity=${d.region_id}`}>Risk for this region</Link>}<Badge tone={beats ? "good" : "warn"}>{beats ? `Model beats naive baseline ${scope}` : `Naive baseline beats model ${scope}`}</Badge></span>}>
        <ChartContainer title="History, backtest and forecast" description="Actual monthly revenue, out-of-sample backtest predictions, and the forecast with its 80% band." height={320}
          legend={<Legend items={[{ label: "Actual", color: HEX.c6 }, { label: "Backtest prediction", color: HEX.c2, kind: "dash" }, { label: "Seasonal naive", color: HEX.c3, kind: "dash" }, { label: "Forecast", color: HEX.c1 }, { label: "80% band", color: HEX.band, kind: "band" }]} />}
          table={<MiniTable head={["Month", "Horizon", "Forecast", "Lower 80%", "Upper 80%"]} rows={d.forecast.map((f) => [month(f.month), f.horizon, money(f.forecast), money(f.lower_80), money(f.upper_80)])} />}>
          <ResponsiveContainer>
            <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={HEX.grid} vertical={false} />
              <XAxis dataKey="month" tickFormatter={month} {...axis} minTickGap={24} /><YAxis tickFormatter={moneyTick} {...axis} width={56} />
              <RTooltip content={<ChartTip labelFmt={month} />} />
              <Area dataKey="band" name="80% band" stroke="none" fill={HEX.band} fillOpacity={0.15} isAnimationActive={false} />
              <Line dataKey="actual" name="Actual" stroke={HEX.c6} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="backtest" name="Backtest prediction" stroke={HEX.c2} strokeDasharray="5 3" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
              <Line dataKey="naive" name="Seasonal naive" stroke={HEX.c3} strokeDasharray="2 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="forecast" name="Forecast" stroke={HEX.c1} strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartContainer>
      </Card>
      <div className="grid g-2">
        <Card title="Accuracy by region" subtitle="Held-out test months; lower MAPE is better">
          <Table rows={Object.entries(d.accuracy_by_region).map(([id, v]) => ({ id, ...v }))} caption="Forecast accuracy by region" rowKey={(r) => r.id} filterable={false} dense
            columns={[{ key: "r", header: "Region", value: (r) => regionName(r.id) },
              { key: "m", header: "Model MAPE", align: "right", value: (r) => r.mape, render: (r) => pct(r.mape) },
              { key: "n", header: "Naive MAPE", align: "right", value: (r) => r.naive_mape, render: (r) => pct(r.naive_mape) },
              { key: "w", header: "Better", value: (r) => (r.mape < r.naive_mape ? "Model" : "Naive"), render: (r) => r.mape < r.naive_mape ? <Badge tone="good">Model</Badge> : <Badge tone="warn">Naive</Badge> }]} />
        </Card>
        <Card title="Model and data split">
          <dl className="kv">
            {Object.entries(d.split).map(([k, v]) => <Fragment key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{String(v)}</dd></Fragment>)}
            <dt>Features</dt><dd>{d.features.join(", ")}</dd>
            <dt>Horizon</dt><dd>{d.horizon_months} months</dd>
            <dt>Run</dt><dd className="mono">{d.run_id}</dd>
          </dl>
        </Card>
      </div>
    </>
  );
}
