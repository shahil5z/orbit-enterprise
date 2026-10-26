import { useState } from "react";
import { Page } from "../../components/shared/Page";
import { Async, Card, Drawer, StatusIndicator, Table } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import type { ModelInfo } from "../../types/api";
import { dateTime, num } from "../../utils/format";

/** Flattens nested metric dicts into "test.mape = 0.09" style rows, keeping only measured numbers. */
export function flattenMetrics(m: Record<string, unknown>, prefix = ""): { key: string; value: number | string }[] {
  const out: { key: string; value: number | string }[] = [];
  for (const [k, v] of Object.entries(m)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v === null || v === undefined) continue;
    if (typeof v === "number") out.push({ key, value: Number(v.toFixed(4)) });
    else if (typeof v === "string") out.push({ key, value: v });
    else if (typeof v === "object" && !Array.isArray(v)) out.push(...flattenMetrics(v as Record<string, unknown>, key));
  }
  return out;
}

export default function ModelsPage() {
  const s = useApi("models", api.models);
  const [sel, setSel] = useState<ModelInfo | null>(null);
  return (
    <Page title="Model Intelligence" intro="Every registered model with its purpose, features, measured test metrics against a baseline, and the number of predictions stored from it.">
      <Async state={s} isEmpty={(d) => !d.models.length}>
        {(d) => (
          <>
            <div className="grid g-2">
              {d.models.filter((m) => m.status === "ACTIVE").map((m) => (
                <Card key={m.model_version} title={m.model_name.replace(/_/g, " ")} subtitle={`${m.task.replace(/_/g, " ")}, ${m.algorithm}`} actions={<StatusIndicator status={m.status} />}>
                  <p className="small">{m.purpose ?? "No purpose recorded."}</p>
                  <dl className="kv" style={{ marginTop: 8 }}>
                    <dt>Version</dt><dd className="mono">{m.model_version}</dd>
                    <dt>Trained</dt><dd>{dateTime(m.trained_at)}</dd>
                    <dt>Predictions stored</dt><dd>{num(m.prediction_count)}{m.positive_predictions !== null ? ` (${num(m.positive_predictions)} positive)` : ""}</dd>
                    <dt>Features</dt><dd>{m.features.join(", ") || "n/a"}</dd>
                  </dl>
                  <button className="btn btn-sm btn-ghost" style={{ marginTop: 8 }} onClick={() => setSel(m)}>Metrics and parameters</button>
                </Card>
              ))}
            </div>
            <Card title="Model registry" subtitle="All versions, including superseded">
              <Table rows={d.models} caption="Model registry" rowKey={(m) => m.model_version} onRowClick={setSel} dense exportName="orbit-models"
                columns={[{ key: "n", header: "Model", value: (m) => m.model_name }, { key: "v", header: "Version", value: (m) => m.model_version },
                  { key: "a", header: "Algorithm", value: (m) => m.algorithm }, { key: "s", header: "Status", value: (m) => m.status, render: (m) => <StatusIndicator status={m.status} /> },
                  { key: "p", header: "Predictions", align: "right", value: (m) => m.prediction_count, render: (m) => num(m.prediction_count) },
                  { key: "t", header: "Trained", value: (m) => m.trained_at, render: (m) => dateTime(m.trained_at) }]} />
            </Card>
          </>
        )}
      </Async>
      <Drawer open={!!sel} title={sel ? sel.model_version : ""} onClose={() => setSel(null)}>
        {sel && (
          <>
            <Table rows={flattenMetrics(sel.metrics)} caption="Model metrics" rowKey={(r) => r.key} dense pageSize={20}
              columns={[{ key: "k", header: "Metric", value: (r) => r.key }, { key: "v", header: "Value", align: "right", value: (r) => r.value }]} />
            <h3>Parameters</h3>
            <dl className="kv">{Object.entries(sel.params).map(([k, v]) => [<dt key={`${k}t`}>{k}</dt>, <dd key={`${k}d`}>{JSON.stringify(v)}</dd>])}</dl>
            <p className="small muted">Artifact: <code>{sel.artifact_path}</code></p>
          </>
        )}
      </Drawer>
    </Page>
  );
}
