import { defineConfig, devices } from "@playwright/test";

// E2E runs against the production build served by `vite preview` with the real FastAPI backend.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "test-results/e2e.json" }]],
  use: { baseURL: process.env.ORBIT_WEB_URL ?? "http://127.0.0.1:4173", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, testIgnore: /screenshots/ },
    { name: "laptop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } }, grep: /every page/, testIgnore: /screenshots/ },
    { name: "tablet", use: { ...devices["Desktop Chrome"], viewport: { width: 820, height: 1180 } }, grep: /every page/, testIgnore: /screenshots/ },
    { name: "screenshots", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, testMatch: /screenshots/ },
  ],
});
