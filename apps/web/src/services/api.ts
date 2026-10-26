import type {
  AnomalyDetail, Capabilities, AnomalyPage, DecisionTrace, Dimensions, ForecastSeries, Health, Intelligence, Kpi, ModelInfo, OpsSummary,
  OptimizationDetail, OptimizationParams, OptimizationResult, OptimizationRun, Overview, Quality, QualityDetail, Recommendation,
  Risk, RiskDetail, MonteCarlo, ScenarioResult, SearchResponse, SystemInfo, LeverKey,
} from "../types/api";
import { download, request } from "./http";

export type Query = Record<string, string | number | null | undefined>;

export function qs(params: Query = {}): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/health"),
  capabilities: () => request<Capabilities>("/capabilities"),
  kpis: () => request<{ kpis: Kpi[] }>("/kpis"),
  dimensions: () => request<Dimensions>("/dimensions"),
  overview: () => request<Overview>("/overview"),
  intelligence: (q: Query) => request<Intelligence>(`/intelligence${qs(q)}`),
  forecastSeries: (regionId?: string | null) => request<ForecastSeries>(`/forecasts/series${qs({ region_id: regionId })}`),
  risks: () => request<{ run_id: string; monte_carlo: MonteCarlo; risks: Risk[] }>("/risks"),
  riskRegion: (regionId: string) => request<RiskDetail>(`/risks/region/${encodeURIComponent(regionId)}`),
  anomalies: (q: Query) => request<AnomalyPage>(`/anomalies/explore${qs(q)}`),
  anomaly: (id: string) => request<AnomalyDetail>(`/anomalies/${encodeURIComponent(id)}`),
  operations: (q: Query) => request<OpsSummary>(`/operations/summary${qs(q)}`),
  optimizationRuns: (limit = 20) => request<{ runs: OptimizationRun[] }>(`/optimization${qs({ limit })}`),
  optimizationRun: (id: string) => request<OptimizationDetail>(`/optimization/${encodeURIComponent(id)}`),
  runOptimization: (p: OptimizationParams) => request<OptimizationResult>("/optimization/run", post(p)),
  recommendations: () => request<{ run_id: string; recommendations: Recommendation[] }>("/recommendations"),
  trace: (id: string) => request<DecisionTrace>(`/decisions/${encodeURIComponent(id)}/trace`),
  scenarioBaseline: () => request<ScenarioResult>("/scenarios/levers"),
  runScenario: (p: Partial<Record<LeverKey, number>>) => request<ScenarioResult>("/scenarios/run", post(p)),
  quality: () => request<Quality>("/data/quality"),
  qualityDataset: (ds: string) => request<QualityDetail>(`/data/quality/${encodeURIComponent(ds)}`),
  models: () => request<{ models: ModelInfo[] }>("/models/catalog"),
  system: () => request<SystemInfo>("/system"),
  search: (q: string) => request<SearchResponse>(`/search${qs({ q, limit: 5 })}`),
  exportFile: (kind: "risks.csv" | "recommendations.csv" | "anomalies.csv" | "risk-report.md") => download(`/exports/${kind}`, `orbit-${kind}`),
};
