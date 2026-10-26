import { Fragment } from "react";
import { Page } from "../../components/shared/Page";
import { Async, Card, Metric, StatusIndicator, Table } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { recentTimings } from "../../services/http";
import { api } from "../../services/api";
import type { SystemInfo } from "../../types/api";
import { dateTime, num } from "../../utils/format";

export default function SystemPage() {
  const s = useApi("system", api.system);
  return <Page title="System & Pipeline"><Async state={s}>{(d) => <Body d={d} reload={s.reload} />}</Async></Page>;
}

function Body({ d, reload }: { d: SystemInfo; reload: () => void }) {
  const latest = d.runs[0];
  const timings = [...recentTimings()].reverse().slice(0, 15);
  const rb = d.rust_benchmark as { speedup_median_wall?: number; rows?: number } | null;
  return (
    <>
      <div className="row between">
        <span className="row">Status legend: <StatusIndicator status="SUCCESS" /> <StatusIndicator status="RUNNING" /> <StatusIndicator status="WARNING" label="WARNING (succeeded with errors)" /> <StatusIndicator status="FAILED" /></span>
        <button className="btn btn-sm btn-secondary" onClick={reload}>Refresh</button>
      </div>
      <div className="metrics">
        <div className="metric"><div className="metric-label">API</div><div className="metric-value" style={{ fontSize: "1rem", marginTop: 6 }}><StatusIndicator status={d.health.status === "ok" ? "UP" : "DEGRADED"} label={d.health.status} /></div><div className="metric-note">{d.health.database.version}</div></div>
        <div className="metric"><div className="metric-label">Latest run</div><div className="metric-value" style={{ fontSize: "1rem", marginTop: 6 }}>{latest ? <StatusIndicator status={latest.status} /> : "n/a"}</div><div className="metric-note">{latest?.run_id}</div></div>
        <Metric label="Records processed (latest)" unit="count" value={latest?.records_processed} />
        <Metric label="Stage errors (latest)" unit="count" higherIsBetter={false} value={latest?.errors} />
        {rb?.speedup_median_wall && <Metric label="Rust vs Python speed-up" unit="ratio" value={rb.speedup_median_wall} note={`Rolling z-scores, ${num(rb.rows)} rows, median wall time`} />}
      </div>
      {d.latest && (
        <Card title="Stages of the latest run" subtitle={d.latest.run_id}>
          <Table rows={d.latest.stages} caption="Pipeline stages" rowKey={(x) => x.stage} filterable={false} dense pageSize={20} exportName="orbit-pipeline-stages"
            columns={[{ key: "s", header: "Stage", value: (x) => x.stage }, { key: "c", header: "Component", value: (x) => x.component },
              { key: "st", header: "Status", value: (x) => x.status, render: (x) => <StatusIndicator status={x.status} /> },
              { key: "d", header: "Duration s", align: "right", value: (x) => x.duration_s, render: (x) => num(x.duration_s, 2) },
              { key: "r", header: "Records", align: "right", value: (x) => x.records_processed, render: (x) => num(x.records_processed) },
              { key: "e", header: "Errors", align: "right", value: (x) => x.error_count },
              { key: "t", header: "Ended", value: (x) => x.ended_at, render: (x) => dateTime(x.ended_at) }]} />
        </Card>
      )}
      <div className="grid g-2">
        <Card title="Pipeline runs">
          <Table rows={d.runs} caption="Pipeline runs" rowKey={(r) => r.run_id} filterable={false} dense
            columns={[{ key: "r", header: "Run", value: (r) => r.run_id }, { key: "s", header: "Status", value: (r) => r.status, render: (r) => <StatusIndicator status={r.status} /> },
              { key: "n", header: "Stages", align: "right", value: (r) => r.stages }, { key: "e", header: "Errors", align: "right", value: (r) => r.errors },
              { key: "t", header: "Started", value: (r) => r.started_at, render: (r) => dateTime(r.started_at) }]} />
        </Card>
        <Card title="Warehouse row counts">
          <dl className="kv">{Object.entries(d.table_counts).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{num(v)}</dd></Fragment>)}</dl>
        </Card>
      </div>
      <Card title="API response times (this browser session)" subtitle="Measured client-side by the API client, most recent first">
        {timings.length === 0 ? <p className="small muted">No requests recorded yet.</p> : (
          <Table rows={timings.map((t, i) => ({ ...t, i }))} caption="API timings" rowKey={(t) => String(t.i)} filterable={false} dense
            columns={[{ key: "p", header: "Endpoint", value: (t) => t.path }, { key: "st", header: "HTTP", align: "right", value: (t) => t.status }, { key: "ms", header: "ms", align: "right", value: (t) => t.ms }]} />
        )}
      </Card>
    </>
  );
}
