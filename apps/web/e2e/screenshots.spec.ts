import { expect, test, type APIRequestContext } from "@playwright/test";

// Captures real screenshots of the running app into docs/screenshots. Run with: npx playwright test --project=screenshots
const OUT = process.env.ORBIT_SCREENSHOT_DIR ?? "../../docs/screenshots";
const PAGES: [string, string][] = [
  ["01-landing", "/"], ["02-overview", "/overview"], ["03-intelligence", "/intelligence"], ["04-anomalies", "/anomalies"],
  ["05-forecasts", "/forecasts?region_id=R04"], ["06-risk", "/risk?entity=R04"], ["07-operations", "/operations"], ["08-optimization", "/optimization"],
  ["09-scenarios", "/scenarios"], ["10-decisions", "/decisions"], ["11-decision-trace", "/decisions?id={R04_DECISION}"],
  ["12-quality", "/quality?dataset=incidents"], ["13-models", "/models"], ["14-system", "/system"],
];

test.beforeEach(async ({ page }) => { await page.addInitScript(() => localStorage.clear()); });

// The decision trace shot uses the R04 decision of the run the API currently serves, not a hardcoded id.
async function resolvePath(path: string, request: APIRequestContext): Promise<string> {
  if (!path.includes("{R04_DECISION}")) return path;
  const res = await request.get("/api/v1/recommendations");
  expect(res.status()).toBe(200);
  const { run_id, recommendations } = (await res.json()).data as { run_id: string; recommendations: { decision_id: string }[] };
  const id = recommendations.find((r) => r.decision_id === `${run_id}-R04`)?.decision_id;
  expect(id, `R04 decision for run ${run_id}`).toBeTruthy();
  return path.replace("{R04_DECISION}", encodeURIComponent(id!));
}

for (const [name, path] of PAGES) {
  test(`screenshot ${name}`, async ({ page, request }) => {
    await page.goto(await resolvePath(path, request));
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".state-loading")).toHaveCount(0);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
  });
}
