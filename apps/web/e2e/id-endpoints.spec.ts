import { expect, test, type APIRequestContext } from "@playwright/test";

// Live checks for the 8 path-parameter endpoints. Valid IDs are discovered from the
// list endpoints of whatever deployment ORBIT_WEB_URL points at (local or production).
const API = "/api/v1";

async function json(request: APIRequestContext, path: string) {
  const res = await request.get(API + path);
  return { status: res.status(), body: await res.json(), headers: res.headers() };
}

function expectEnvelopeOk(body: { success: boolean; data: unknown; errors: unknown[]; metadata: { api_version: string } }) {
  expect(body.success).toBe(true);
  expect(body.errors).toEqual([]);
  expect(body.metadata.api_version).toBe("v1");
  expect(body.data).toBeTruthy();
}

async function expectControlledError(request: APIRequestContext, path: string, statuses: number[]) {
  const r = await json(request, path);
  expect(statuses, `${path} returned ${r.status}`).toContain(r.status);
  expect(r.body.success).toBe(false);
  expect(r.body.data).toBeNull();
  expect(r.body.errors[0].code).toMatch(/^[A-Z_]+$/);
  const text = JSON.stringify(r.body);
  expect(text).not.toMatch(/Traceback|File "|psycopg|SELECT |postgres(ql)?:\/\/|\/var\/task/i);
  expect(r.headers["access-control-allow-origin"]).toBeUndefined();
  expect(r.headers["x-content-type-options"]).toBe("nosniff");
}

test.describe("ID endpoints", () => {
  let ids: { region: string; operation: string; decision: string; dataset: string; optimization: string; model: string; run: string };

  test.beforeAll(async ({ request }) => {
    const risks = (await json(request, "/risks")).body.data.risks;
    const anomalies = (await json(request, "/anomalies?limit=1")).body.data.anomalies;
    const recs = (await json(request, "/recommendations")).body.data.recommendations;
    const quality = (await json(request, "/data/quality")).body.data.datasets;
    const opt = (await json(request, "/optimization?limit=1")).body.data.runs;
    const models = (await json(request, "/models")).body.data.models;
    const runs = (await json(request, "/operations?limit=1")).body.data.pipeline_runs;
    ids = {
      region: risks.find((r: { region_id?: string }) => r.region_id).region_id,
      operation: anomalies[0].operation_id,
      decision: recs[0].decision_id,
      dataset: quality[0].dataset,
      optimization: opt[0].optimization_id,
      model: models[0].model_version,
      run: runs[0].run_id,
    };
  });

  test("risks/region/{region_id}", async ({ request }) => {
    const r = await json(request, `/risks/region/${ids.region}`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.region_id).toBe(ids.region);
    expect(typeof r.body.data.region.risk_score).toBe("number");
    await expectControlledError(request, "/risks/region/R99", [400, 404]);
  });

  test("anomalies/{operation_id}", async ({ request }) => {
    const r = await json(request, `/anomalies/${ids.operation}`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.operation.operation_id).toBe(ids.operation);
    await expectControlledError(request, "/anomalies/OP9999999", [404]);
  });

  test("decisions/{decision_id}/trace", async ({ request }) => {
    const r = await json(request, `/decisions/${encodeURIComponent(ids.decision)}/trace`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.decision.decision_id).toBe(ids.decision);
    await expectControlledError(request, "/decisions/no-such-decision/trace", [404]);
  });

  test("data/quality/{dataset}", async ({ request }) => {
    const r = await json(request, `/data/quality/${ids.dataset}`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.dataset.dataset).toBe(ids.dataset);
    await expectControlledError(request, "/data/quality/no_such_dataset", [404]);
  });

  test("exports/{kind}", async ({ request }) => {
    for (const kind of ["risks.csv", "recommendations.csv", "anomalies.csv", "risk-report.md"]) {
      const res = await request.get(`${API}/exports/${kind}`);
      expect(res.status(), kind).toBe(200);
      expect(res.headers()["content-disposition"]).toContain(`orbit-${kind}`);
      const body = await res.text();
      expect(body.length).toBeGreaterThan(50);
      expect(body).not.toMatch(/ORBIT\s*\/\//);
    }
    await expectControlledError(request, "/exports/secrets.txt", [422]);
  });

  test("optimization/{optimization_id}", async ({ request }) => {
    const r = await json(request, `/optimization/${ids.optimization}`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.optimization_id).toBe(ids.optimization);
    expect(r.body.data.status).toBe("OPTIMAL");
    await expectControlledError(request, "/optimization/OPT-does-not-exist", [404]);
  });

  test("models/{model_version}", async ({ request }) => {
    const r = await json(request, `/models/${ids.model}`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.model_version).toBe(ids.model);
    expect(r.body.data.metrics).toBeTruthy();
    await expectControlledError(request, "/models/no-such-model", [404]);
  });

  test("operations/runs/{run_id}", async ({ request }) => {
    const r = await json(request, `/operations/runs/${ids.run}`);
    expect(r.status).toBe(200); expectEnvelopeOk(r.body);
    expect(r.body.data.run_id).toBe(ids.run);
    expect(r.body.data.stages.length).toBe(11);
    await expectControlledError(request, "/operations/runs/no-such-run", [404]);
  });
});
