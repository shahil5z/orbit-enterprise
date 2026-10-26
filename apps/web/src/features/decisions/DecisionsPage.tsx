import { Link, useSearchParams } from "react-router-dom";
import { ExportButton } from "../../components/shared/ExportButton";
import { Page } from "../../components/shared/Page";
import { Async, Button, Card, Drawer, RiskBadge, StatusIndicator, Table } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { api } from "../../services/api";
import type { DecisionTrace, Recommendation, TraceLevel } from "../../types/api";
import { dateTime, num, pct } from "../../utils/format";

export default function DecisionsPage() {
  const s = useApi("recs", api.recommendations);
  const [params, setParams] = useSearchParams();
  const id = params.get("id");
  const open = (v: string | null) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set("id", v); else n.delete("id"); return n; });
  return (
    <Page title="Decision Center" intro="Each card follows observation, cause, forecast, risk, recommendation and expected impact. Select Why? to trace it back to the forecast, model output, metric and dataset.">
      <div className="row between"><span /><div className="row"><ExportButton kind="recommendations.csv" /><ExportButton kind="risk-report.md" /></div></div>
      <Async state={s} isEmpty={(d) => !d.recommendations.length}>
        {(d) => <div className="grid g-2">{d.recommendations.map((r) => <DecisionCard key={r.decision_id} r={r} onWhy={() => open(r.decision_id)} />)}</div>}
      </Async>
      <Drawer open={!!id} title="Why? Decision trace" onClose={() => open(null)} wide>{id && <Trace id={id} />}</Drawer>
    </Page>
  );
}

function DecisionCard({ r, onWhy }: { r: Recommendation; onWhy: () => void }) {
  const { regionName } = useReference();
  const title = r.scope === "company" ? "Company portfolio" : regionName(r.entity_id);
  return (
    <Card title={title} subtitle={r.decision_id} actions={<RiskBadge level={r.priority} />}>
      <div className="decision-grid">
        {([["Observation", r.observation], ["Cause", r.cause], ["Forecast", r.forecast], ["Risk", r.risk]] as const).map(([h, t]) => <div className="decision-cell" key={h}><h4>{h}</h4><p>{t}</p></div>)}
      </div>
      <p style={{ marginTop: 10 }}><strong>Recommendation:</strong> {r.recommendation}</p>
      <p className="small muted">{r.expected_impact}</p>
      <div className="row between" style={{ marginTop: 8 }}>
        <span className="small">Confidence {pct(r.confidence, 0)}, {r.evidence.length} evidence items</span>
        <Button variant="primary" size="sm" onClick={onWhy} aria-label={`Why? Trace ${title}`}>Why?</Button>
      </div>
    </Card>
  );
}

function Trace({ id }: { id: string }) {
  const s = useApi(`trace-${id}`, () => api.trace(id));
  return <Async state={s}>{(d) => <TraceBody d={d} />}</Async>;
}

const LEVEL_LABEL: Record<TraceLevel["level"], string> = { recommendation: "Recommendation", forecast: "Forecast", model_output: "Model output", metric: "Metric", dataset: "Dataset" };

function TraceBody({ d }: { d: DecisionTrace }) {
  return (
    <div data-testid="decision-trace">
      <p className="small muted">Run <code>{d.decision.run_id}</code>, created {dateTime(d.decision.created_at)}.</p>
      <ol className="chain">
        {d.chain.map((l) => (
          <li key={l.level} data-level={l.level}>
            <div className="chain-level">{LEVEL_LABEL[l.level]}</div>
            <p><strong>{l.title}</strong></p>
            {l.detail && <p className="small">{l.detail}</p>}
            <p className="small muted">Source: <code>{l.ref}</code>{l.confidence !== undefined ? `, confidence ${pct(l.confidence, 0)}` : ""}</p>
            {l.kpi && <p className="small">KPI <strong>{l.kpi.name}</strong>: {l.kpi.definition} Formula <code>{l.kpi.formula}</code>.</p>}
            {l.rows && l.rows.length > 0 && (
              <Table rows={l.rows} caption={`${LEVEL_LABEL[l.level]} rows`} rowKey={(r) => JSON.stringify(r)} filterable={false} dense pageSize={6}
                columns={Object.keys(l.rows[0]!).slice(0, 6).map((k) => ({ key: k, header: k.replace(/_/g, " "), value: (r: Record<string, unknown>) => fmtCell(r[k]) }))} />
            )}
            {l.models?.map((m) => <p key={m.model_version} className="small"><code>{m.model_version}</code> {m.algorithm}, trained {dateTime(m.trained_at)}, {m.predictions === null ? "outputs stored in the forecasts table" : `${num(m.predictions)} predictions stored`}.</p>)}
            {l.datasets && (
              <ul className="list">{l.datasets.map((ds) => (
                <li key={ds.dataset} className="row between small"><Link to={`/quality?dataset=${ds.dataset}`}>{ds.dataset}</Link><span>quality {num(ds.quality_score, 2)}, {num(ds.rows_checked)} rows, {ds.issue_count} issues</span></li>))}</ul>
            )}
            {l.lineage && <ul className="list">{l.lineage.map((x) => <li key={x.stage} className="row between small"><span>{x.stage} <span className="muted">({x.component})</span></span><span className="row">{num(x.records_processed)} records <StatusIndicator status={x.status} /></span></li>)}</ul>}
          </li>
        ))}
      </ol>
      <h3>Evidence</h3>
      <ul className="list">{d.decision.evidence.map((e) => <li key={e.ref} className="small"><code>{e.ref}</code> = <strong>{String(e.value)}</strong> <span className="muted">({e.source})</span></li>)}</ul>
    </div>
  );
}

function fmtCell(v: unknown): string | number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Math.abs(v) >= 1000 ? Math.round(v) : Number(v.toFixed(4));
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
