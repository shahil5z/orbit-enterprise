import { useSearchParams } from "react-router-dom";
import { Page } from "../../components/shared/Page";
import { Async, Badge, Card, Drawer, Metric, StatusIndicator, Table } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { api } from "../../services/api";
import type { QualityDataset, QualityDetail } from "../../types/api";
import { dateTime, num, pct } from "../../utils/format";

/** Text plus tone: health is never conveyed by colour alone. */
export function health(score: number): { label: string; tone: "good" | "warn" | "bad" } {
  if (score >= 99) return { label: "Healthy", tone: "good" };
  if (score >= 95) return { label: "Watch", tone: "warn" };
  return { label: "Unhealthy", tone: "bad" };
}

export default function QualityPage() {
  const s = useApi("quality", api.quality);
  const { kpis } = useReference();
  const [params, setParams] = useSearchParams();
  const ds = params.get("dataset");
  const open = (v: string | null) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set("dataset", v); else n.delete("dataset"); return n; });
  return (
    <Page title="Data Quality" intro="Health: Healthy at 99 and above, Watch from 95, Unhealthy below 95. Scores are weighted by check family; see the scoring method below.">
      <Async state={s} isEmpty={(d) => !d.datasets.length}>
        {(d) => (
          <>
            <div className="metrics">
              <Metric kpi={kpis.quality_score} label="Overall quality score" value={d.overall_quality_score} />
              <Metric label="Datasets checked" unit="count" value={d.datasets.length} />
              <Metric label="Datasets below 99" unit="count" higherIsBetter={false} value={d.datasets.filter((x) => x.quality_score < 99).length} />
              <Metric label="Total issues" unit="count" higherIsBetter={false} value={d.datasets.reduce((a, x) => a + x.issue_count, 0)} />
            </div>
            <Card title="Datasets" subtitle={`Run ${d.run_id}. Select a dataset for issues, ingestion and pipeline status.`}>
              <Table<QualityDataset> rows={d.datasets} caption="Dataset quality" rowKey={(x) => x.dataset} onRowClick={(x) => open(x.dataset)} initialSort={{ key: "q", dir: "asc" }} exportName="orbit-data-quality" dense pageSize={12}
                columns={[{ key: "d", header: "Dataset", value: (x) => x.dataset },
                  { key: "h", header: "Health", value: (x) => health(x.quality_score).label, render: (x) => { const h = health(x.quality_score); return <Badge tone={h.tone}>{h.label}</Badge>; } },
                  { key: "q", header: "Score", align: "right", value: (x) => x.quality_score, render: (x) => num(x.quality_score, 2) },
                  { key: "r", header: "Rows checked", align: "right", value: (x) => x.rows_checked, render: (x) => num(x.rows_checked) },
                  { key: "i", header: "Issues", align: "right", value: (x) => x.issue_count },
                  { key: "t", header: "Checked", value: (x) => x.created_at, render: (x) => dateTime(x.created_at) }]} />
              <p className="small muted" style={{ marginTop: 8 }}>Scoring: {d.scoring.method}. Weights: {Object.entries(d.scoring.weights).map(([k, v]) => `${k} ${v}`).join(", ")}.</p>
            </Card>
          </>
        )}
      </Async>
      <Drawer open={!!ds} title={ds ? `Dataset: ${ds}` : ""} onClose={() => open(null)} wide>{ds && <DatasetPanel ds={ds} />}</Drawer>
    </Page>
  );
}

function DatasetPanel({ ds }: { ds: string }) {
  const s = useApi(`qds-${ds}`, () => api.qualityDataset(ds));
  return <Async state={s}>{(d) => <DatasetBody d={d} />}</Async>;
}

function DatasetBody({ d }: { d: QualityDetail }) {
  const h = health(d.dataset.quality_score);
  const ing = d.ingestion;
  return (
    <div data-testid="quality-detail">
      <div className="row between"><Badge tone={h.tone}>{h.label}</Badge><span className="small">Score <strong>{num(d.dataset.quality_score, 2)}</strong>, {num(d.dataset.rows_checked)} rows, {d.dataset.issue_count} issues</span></div>
      <Card title="Issues" subtitle="Each failed check with affected row count and rate">
        <Table rows={d.dataset.issues} caption="Quality issues" rowKey={(i) => `${i.check}-${i.column ?? ""}`} filterable={false} dense
          columns={[{ key: "c", header: "Check", value: (i) => i.check.replace(/_/g, " ") }, { key: "col", header: "Column", value: (i) => i.column ?? "" },
            { key: "f", header: "Family", value: (i) => i.family }, { key: "s", header: "Severity", value: (i) => i.severity, render: (i) => <Badge tone={i.severity === "high" ? "bad" : i.severity === "medium" ? "warn" : "neutral"}>{i.severity}</Badge> },
            { key: "n", header: "Rows", align: "right", value: (i) => i.count }, { key: "r", header: "Rate", align: "right", value: (i) => i.rate, render: (i) => pct(i.rate, 2) },
            { key: "d", header: "Detail", value: (i) => i.detail ?? "", sortable: false }]} />
      </Card>
      <Card title="Latest ingestion">
        <dl className="kv" data-testid="ingestion">
          <dt>Ingestion stage</dt><dd>{ing.stage ? <StatusIndicator status={ing.stage} /> : "n/a"}</dd>
          <dt>Finished</dt><dd>{dateTime(ing.ended_at)}</dd>
          <dt>Generated rows</dt><dd>{num(ing.generated)}</dd>
          <dt>Loaded rows</dt><dd>{num(ing.record_count)}</dd>
          <dt>Quarantined</dt><dd>{num(ing.quarantined)}</dd>
          <dt>Duplicates removed</dt><dd>{num(ing.duplicates_removed)}</dd>
          <dt>Validation</dt><dd>{ing.validation_status ? <StatusIndicator status={ing.validation_status} /> : "n/a"}</dd>
        </dl>
      </Card>
      <Card title="Pipeline status" subtitle="Stages of the run that produced this score">
        <ul className="list" data-testid="pipeline-status">{d.pipeline.map((p) => <li key={p.stage} className="row between small"><span>{p.stage}</span><span className="row"><span className="muted">{dateTime(p.ended_at)}</span><StatusIndicator status={p.status} /></span></li>)}</ul>
      </Card>
      <Card title="Score history">
        <Table rows={d.history} caption="Quality score history" rowKey={(x) => x.run_id} filterable={false} dense
          columns={[{ key: "r", header: "Run", value: (x) => x.run_id }, { key: "q", header: "Score", align: "right", value: (x) => x.quality_score },
            { key: "i", header: "Issues", align: "right", value: (x) => x.issue_count }, { key: "t", header: "Checked", value: (x) => x.created_at, render: (x) => dateTime(x.created_at) }]} />
      </Card>
    </div>
  );
}
