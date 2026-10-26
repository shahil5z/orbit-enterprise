import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Page } from "../../components/shared/Page";
import { ExportButton } from "../../components/shared/ExportButton";
import { Async, Badge, Button, Card, Drawer, Table, type Column } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { pick, useFilters } from "../../hooks/useFilters";
import { useReference } from "../../hooks/useReference";
import { api, qs } from "../../services/api";
import type { AnomalyDetail, AnomalyRow } from "../../types/api";
import { money, num, pct } from "../../utils/format";

const LIMIT = 25;

export default function AnomalyExplorer() {
  const { filters } = useFilters();
  const [params, setParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const selected = params.get("id");
  const fkey = [filters.region_id, filters.bu_id, filters.start, filters.end].join("|");
  useEffect(() => setOffset(0), [fkey]);
  const q = { ...pick(filters, ["region_id", "bu_id", "start", "end"]), limit: LIMIT, offset };
  const s = useApi(`anoms${qs(q)}`, () => api.anomalies(q));
  const { regionName, buName } = useReference();
  const select = (id: string | null) => setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("id", id); else n.delete("id"); return n; });
  const cols: Column<AnomalyRow>[] = [
    { key: "date", header: "Date", value: (r) => r.op_date },
    { key: "region", header: "Region", value: (r) => regionName(r.region_id) },
    { key: "bu", header: "Business unit", value: (r) => buName(r.bu_id) },
    { key: "score", header: "Anomaly score", align: "right", value: (r) => r.anomaly_score, render: (r) => r.anomaly_score.toFixed(3) },
    { key: "label", header: "Ground truth", value: (r) => r.labelled_anomaly, render: (r) => r.labelled_anomaly === 1 ? <Badge tone="bad">Injected anomaly</Badge> : r.labelled_anomaly === 0 ? <Badge>Not labelled</Badge> : "n/a" },
    { key: "orders", header: "Orders", align: "right", value: (r) => r.orders_processed ?? null, render: (r) => num(r.orders_processed) },
    { key: "uptime", header: "Uptime %", align: "right", value: (r) => r.uptime_pct ?? null, render: (r) => num(r.uptime_pct, 2) },
  ];
  return (
    <Page title="Anomaly Explorer" intro="Operational days flagged by the Isolation Forest, ranked by anomaly score (higher is more unusual). Open a row to see how unusual each metric was against its own 90-day baseline.">
      <Card title="Flagged operational days" actions={<ExportButton kind="anomalies.csv" />}
        subtitle={s.data ? `${num(s.data.total)} flagged for this selection. Showing ${offset + 1} to ${Math.min(offset + LIMIT, s.data.total)}.` : undefined}>
        <Async state={s} isEmpty={(d) => !d.rows.length}>
          {(d) => (
            <>
              <Table rows={d.rows} columns={cols} caption="Flagged anomalies" rowKey={(r) => r.operation_id} onRowClick={(r) => select(r.operation_id)} pageSize={LIMIT} dense />
              <nav className="pager" aria-label="Anomaly result pages">
                <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous {LIMIT}</Button>
                <Button size="sm" disabled={offset + LIMIT >= d.total} onClick={() => setOffset(offset + LIMIT)}>Next {LIMIT}</Button>
              </nav>
            </>
          )}
        </Async>
      </Card>
      <Drawer open={!!selected} title="Anomaly detail" onClose={() => select(null)} wide>
        {selected && <AnomalyPanel id={selected} />}
      </Drawer>
    </Page>
  );
}

function AnomalyPanel({ id }: { id: string }) {
  const s = useApi(`anom-${id}`, () => api.anomaly(id));
  return <Async state={s}>{(d) => <AnomalyBody d={d} />}</Async>;
}

function AnomalyBody({ d }: { d: AnomalyDetail }) {
  const { regionName, buName } = useReference();
  const o = d.operation;
  return (
    <div data-testid="anomaly-detail">
      <div className="decision-grid">
        <div className="decision-cell"><h4>Where</h4><p>{regionName(o.region_id)} / {buName(o.bu_id)}</p></div>
        <div className="decision-cell"><h4>When</h4><p>{o.op_date}</p></div>
        <div className="decision-cell"><h4>How unusual</h4><p>Score {o.anomaly_score.toFixed(3)} ({o.model_version})</p></div>
        <div className="decision-cell"><h4>Ground truth</h4><p>{o.labelled_anomaly === 1 ? "Injected anomaly (simulator label)" : "Not labelled as anomaly: possible false positive"}</p></div>
      </div>
      <Card title="What happened" subtitle={`Each metric vs ${d.baseline_window} (${d.baseline_days} days)`}>
        <Table rows={d.deviations} caption="Metric deviations" rowKey={(r) => r.metric} filterable={false} dense initialSort={{ key: "absz", dir: "desc" }}
          columns={[{ key: "m", header: "Metric", value: (r) => r.metric.replace(/_/g, " ") },
            { key: "v", header: "Value", align: "right", value: (r) => r.value, render: (r) => num(r.value, 2) },
            { key: "b", header: "Baseline mean", align: "right", value: (r) => r.baseline_mean, render: (r) => num(r.baseline_mean, 2) },
            { key: "p", header: "vs mean", align: "right", value: (r) => r.pct_vs_mean, render: (r) => pct(r.pct_vs_mean, 1, true) },
            { key: "absz", header: "z-score", align: "right", value: (r) => (r.z === null ? null : Math.abs(r.z)), render: (r) => <strong>{num(r.z, 2)}</strong> }]} />
      </Card>
      <Card title="Possible explanation" subtitle={d.explanation_method}><p data-testid="anomaly-explanation">{d.explanation}</p></Card>
      <Card title="Incidents within 3 days">
        {d.incidents_nearby.length === 0 ? <p className="small muted">No incidents recorded nearby.</p> : (
          <ul className="list">{d.incidents_nearby.map((i) => <li key={i.incident_id} className="small"><strong>{i.incident_id}</strong> {i.severity} {i.category ?? ""} opened {i.opened_at.slice(0, 10)}, cost {money(i.cost_impact)}</li>)}</ul>
        )}
      </Card>
      <div className="row">
        <Link className="btn btn-primary btn-md" style={{ textDecoration: "none" }} to={`/forecasts?region_id=${o.region_id}`}>See {regionName(o.region_id)} forecast</Link>
        <Link className="btn btn-secondary btn-md" style={{ textDecoration: "none" }} to={`/risk?entity=${o.region_id}`}>Region risk</Link>
      </div>
    </div>
  );
}
