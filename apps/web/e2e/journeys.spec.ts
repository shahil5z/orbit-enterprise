import { expect, test, type Page } from "@playwright/test";

// Every journey runs against the real API and database (no mocks). Console errors fail the test.
function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

test.beforeEach(async ({ page }) => { await page.addInitScript(() => localStorage.clear()); });

test("overview > declining trend > anomaly > forecast > risk > recommendation", async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto("/overview");
  await expect(page.getByTestId("ttm-kpis")).toBeVisible();
  const declining = page.getByTestId("declining-regions");
  await expect(declining).toBeVisible();
  await declining.getByRole("link", { name: /Investigate anomalies/ }).first().click();
  await expect(page).toHaveURL(/\/anomalies\?region_id=R0\d/);
  await page.getByRole("table", { name: "Flagged anomalies" }).locator("tbody tr").first().click();
  const detail = page.getByTestId("anomaly-detail");
  await expect(detail).toBeVisible();
  await expect(page.getByTestId("anomaly-explanation")).not.toBeEmpty();
  await detail.getByRole("link", { name: /forecast$/ }).click();
  await expect(page).toHaveURL(/\/forecasts\?region_id=R0\d/);
  await expect(page.getByRole("img", { name: /History, backtest and forecast/ })).toBeVisible();
  await page.getByRole("link", { name: "Risk for this region" }).click();
  await expect(page.getByTestId("risk-detail")).toBeVisible();
  await expect(page.getByTestId("risk-recommendation")).toContainText("Recommendation");
  await page.getByRole("link", { name: "Open decision trace" }).click();
  const trace = page.getByTestId("decision-trace");
  await expect(trace).toBeVisible();
  for (const level of ["recommendation", "forecast", "model_output", "metric", "dataset"]) await expect(trace.locator(`[data-level="${level}"]`)).toBeVisible();
  expect(errors).toEqual([]);
});

test("optimization: change constraints > run > compare", async ({ page }) => {
  test.setTimeout(180_000);
  const errors = watchConsole(page);
  await page.goto("/optimization");
  await expect(page.getByTestId("optimization-result")).toBeVisible();
  const hires = page.getByLabel("Total hires");
  await hires.fill("55");
  await page.getByLabel("Budget multiplier").fill("1.15");
  await page.getByTestId("run-optimization").click();
  await expect(page.getByTestId("optimization-compare")).toBeVisible({ timeout: 150_000 });
  await expect(page.getByTestId("optimization-result")).toContainText("Optimized objective");
  await expect(page.getByText(/hires 55/).first()).toBeVisible();
  await expect(page.getByRole("table", { name: "Optimization constraints" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("risk: high-risk segment > drivers > evidence > recommendation", async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto("/risk");
  const register = page.getByRole("table", { name: "Risk register" });
  const top = register.locator("tbody tr").first();
  await expect(top).toContainText(/HIGH|CRITICAL/);
  await top.click();
  await expect(page.getByRole("table", { name: "Risk drivers" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Churn by segment" })).toBeVisible();
  await expect(page.getByTestId("risk-evidence").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("risk-recommendation")).not.toBeEmpty();
  expect(errors).toEqual([]);
});

test("data quality: unhealthy dataset > issues > pipeline status", async ({ page }) => {
  const errors = watchConsole(page);
  await page.goto("/quality");
  const first = page.getByRole("table", { name: "Dataset quality" }).locator("tbody tr").first();
  await expect(first).toContainText("Unhealthy");
  await first.click();
  const d = page.getByTestId("quality-detail");
  await expect(d.getByRole("table", { name: "Quality issues" }).locator("tbody tr").first()).toBeVisible();
  await expect(d.getByTestId("ingestion")).toBeVisible();
  await expect(d.getByTestId("pipeline-status").locator("li").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("every page renders without console errors", async ({ page }) => {
  const errors = watchConsole(page);
  for (const p of ["/", "/overview", "/intelligence", "/anomalies", "/forecasts", "/risk", "/operations", "/optimization", "/scenarios", "/decisions", "/quality", "/models", "/system"]) {
    await page.goto(p);
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".state-error")).toHaveCount(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${p}`).toBeLessThanOrEqual(1);
  }
  expect(errors).toEqual([]);
});
