import { expect, test } from "@playwright/test";

// Captures real screenshots of the running app into docs/screenshots. Run with: npx playwright test --project=screenshots
const OUT = process.env.ORBIT_SCREENSHOT_DIR ?? "../../docs/screenshots";
const PAGES: [string, string][] = [
  ["01-landing", "/"], ["02-overview", "/overview"], ["03-intelligence", "/intelligence"], ["04-anomalies", "/anomalies"],
  ["05-forecasts", "/forecasts?region_id=R04"], ["06-risk", "/risk?entity=R04"], ["07-operations", "/operations"], ["08-optimization", "/optimization"],
  ["09-scenarios", "/scenarios"], ["10-decisions", "/decisions"], ["11-decision-trace", "/decisions?id=20261026T160340Z-f5255777-R04"],
  ["12-quality", "/quality?dataset=incidents"], ["13-models", "/models"], ["14-system", "/system"],
];

test.beforeEach(async ({ page }) => { await page.addInitScript(() => localStorage.clear()); });

for (const [name, path] of PAGES) {
  test(`screenshot ${name}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await expect(page.locator(".state-loading")).toHaveCount(0);
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
  });
}
