import type { FilterKey } from "../hooks/useFilters";

export interface RouteDef { path: string; label: string; group: string; subtitle: string; filters: readonly FilterKey[] }

/** Single source of truth for navigation, page titles and which global filters each page honours. */
export const ROUTES: RouteDef[] = [
  { path: "/overview", label: "Executive Overview", group: "Observe", subtitle: "Trailing twelve months, quarter comparisons, risks and actions", filters: [] },
  { path: "/intelligence", label: "Business Intelligence", group: "Understand", subtitle: "Drill into revenue, customers and incidents by any dimension", filters: ["start", "end", "region_id", "bu_id", "segment", "product_id", "category"] },
  { path: "/anomalies", label: "Anomaly Explorer", group: "Understand", subtitle: "What happened, how unusual, where, when, and a possible explanation", filters: ["start", "end", "region_id", "bu_id"] },
  { path: "/forecasts", label: "Forecasts", group: "Predict", subtitle: "History, forecast and prediction band with measured accuracy", filters: [] },
  { path: "/risk", label: "Risk", group: "Predict", subtitle: "Exposure, drivers, evidence and confidence per entity", filters: [] },
  { path: "/operations", label: "Operations", group: "Optimize", subtitle: "Throughput, capacity, incidents and bottlenecks", filters: ["region_id", "bu_id", "category"] },
  { path: "/optimization", label: "Optimization Center", group: "Optimize", subtitle: "Budget and headcount allocation solved by Julia JuMP + HiGHS", filters: [] },
  { path: "/scenarios", label: "Scenario Lab", group: "Optimize", subtitle: "What-if analysis computed by the backend, always labelled scenario vs baseline", filters: [] },
  { path: "/decisions", label: "Decision Center", group: "Decide", subtitle: "Recommendations with a traceable evidence chain", filters: [] },
  { path: "/quality", label: "Data Quality", group: "Platform", subtitle: "Per-dataset quality scores, issues and ingestion", filters: [] },
  { path: "/models", label: "Model Intelligence", group: "Platform", subtitle: "Registered models, purpose, features and measured metrics", filters: [] },
  { path: "/system", label: "System & Pipeline", group: "Platform", subtitle: "Pipeline runs, stage status and service health", filters: [] },
];

export const routeFor = (pathname: string) => ROUTES.find((r) => pathname.startsWith(r.path));
