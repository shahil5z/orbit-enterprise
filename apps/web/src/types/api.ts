// Types mirror the FastAPI responses (apps/api/orbit_api). Every response is wrapped in Envelope<T>.
export interface ApiErrorItem { code: string; message: string; details?: { field: string; message: string }[] }
export interface Envelope<T> {
  success: boolean;
  data: T | null;
  metadata: { api_version: string; generated_at: string; request_id: string; [k: string]: unknown };
  errors: ApiErrorItem[];
}

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type RunStatus = "SUCCESS" | "RUNNING" | "FAILED" | "WARNING";

export interface Kpi {
  key: string; name: string; definition: string; formula: string; source: string; refresh: string;
  dimensions: string[]; unit: "currency" | "percent" | "count" | "hours" | "score" | "ratio";
  higher_is_better: boolean; meaning: string;
}

export interface Dimensions {
  regions: { id: string; name: string; currency: string }[];
  business_units: { id: string; name: string }[];
  segments: string[];
  products: { id: string; name: string; bu_id: string; category: string }[];
  incident_categories: string[];
  date_range: { start: string; end: string };
}

export interface Health { status: "ok" | "degraded"; database: { status: "up" | "down"; database?: string; version?: string } }

export interface PeriodTotals {
  revenue: number; gross_margin: number; opex: number; operating_profit: number; gross_margin_pct: number;
  operating_margin_pct: number; transactions: number; incidents: number; incident_cost: number;
}
export interface Comparison { current: number; prior_quarter: number; same_quarter_last_year: number; qoq: number | null; yoy: number | null }
export interface CompanyMonth {
  period_month: string; revenue: number; gross_margin: number; opex: number; operating_profit: number;
  incidents: number; transactions: number; marketing_spend: number; uptime_pct: number;
}
export interface RegionPerf {
  region_id: string; name?: string; revenue: number; gross_margin: number; opex: number; incidents: number; uptime: number;
  prior_revenue: number; revenue_growth: number; gross_margin_pct: number; operating_margin_pct: number; revenue_share: number;
}
export interface BuPerf extends Omit<RegionPerf, "region_id"> { bu_id: string }

export interface RiskFactor { factor: string; weight: number; raw_value: number; normalized: number; description: string; contribution: number }
export interface Risk {
  entity_type: "region" | "business_unit"; region_id: string; bu_id: string | null; risk_score: number; risk_level: RiskLevel;
  risk_factors: RiskFactor[]; confidence: number; recommended_action: string; explanation: string;
}
export interface McStats { expected: number; p5: number; p50: number; p95: number; var95: number; cvar95: number }
export interface MonteCarlo {
  engine: string; simulations: number; rho: number; horizon_months: number; point_forecast_total: number;
  regions: Record<string, McStats>; total: McStats; elapsed_seconds: number;
}
export interface Evidence { ref: string; value: number | string; source: string }
export interface Recommendation {
  decision_id: string; scope: "company" | "region"; entity_id: string; priority: RiskLevel; observation: string; cause: string;
  forecast: string; risk: string; recommendation: string; expected_impact: string; confidence: number; evidence: Evidence[];
}
export interface AnomalyRow {
  operation_id: string; op_date: string; region_id: string; bu_id: string; anomaly_score: number; labelled_anomaly: number | null;
  orders_processed?: number; fulfillment_hours?: number; uptime_pct?: number; support_tickets?: number; opex?: number; model_version: string;
}

export interface Overview {
  label: string; as_of_month: string; ttm: PeriodTotals; prior_ttm: PeriodTotals; ttm_revenue_growth: number;
  quarter_comparison: Record<string, Comparison> & { period?: { current: string[]; prior_quarter_start: string; same_quarter_last_year_start: string } };
  monthly: CompanyMonth[]; by_region: RegionPerf[]; by_business_unit: BuPerf[]; top_risks: Risk[]; monte_carlo_total: McStats;
  top_anomalies: AnomalyRow[]; anomaly_total: number; recommendations: Recommendation[]; run_id: string;
}

export interface GroupRow { key: string; label: string; revenue: number; gross_margin: number; transactions: number; customers: number }
export interface IncidentBreakdown {
  by_category: { key: string; incidents: number; cost: number }[];
  by_severity: { key: string; incidents: number; cost: number; mttr_hours: number | null; open: number }[];
  monthly: { month: string; incidents: number; major: number; mttr_hours: number | null }[];
  recent: { incident_id: string; region_id: string; bu_id: string | null; supplier_id: string | null; severity: string; category: string | null; opened_at: string; resolved_at: string | null; cost_impact: number }[];
}
export interface SegmentProfile { cluster: number; customers: number; avg_monetary: number; avg_frequency: number; avg_recency_days: number; churn_rate: number; enterprise_share: number; label: string }
export interface Intelligence {
  filters: Record<string, string | null>; comparison_period: { start: string; end: string };
  comparison: Record<"revenue" | "gross_margin" | "transactions" | "customers", { current: number | null; prior: number | null; change: number | null }>;
  monthly: (Omit<GroupRow, "key" | "label"> & { month: string })[];
  by_region: GroupRow[]; by_business_unit: GroupRow[]; by_segment: GroupRow[]; by_channel: GroupRow[]; top_products: GroupRow[];
  incidents: IncidentBreakdown;
  behaviour_segments: { k: number; features: string[]; profiles: SegmentProfile[]; silhouette_by_k: Record<string, number> };
}

export interface ForecastPoint { month: string; horizon: number; forecast: number; lower_80: number; upper_80: number }
export interface ErrorStats { mae: number; rmse: number; mape: number; bias: number; n: number }
export interface ForecastSeries {
  run_id: string; target: string; region_id: string | null; model_version: string; algorithm: string; horizon_months: number; band: string;
  history: { month: string; actual: number }[]; forecast: ForecastPoint[];
  backtest: { month: string; actual: number; prediction: number; seasonal_naive: number }[];
  accuracy: { model: ErrorStats; seasonal_naive: ErrorStats }; accuracy_by_region: Record<string, { mape: number; naive_mape: number; n: number }>;
  split: Record<string, string | number>; features: string[];
}

export interface RiskDetail {
  run_id: string; region_id: string; name: string; region: Risk | null; business_units: Risk[]; monte_carlo: McStats | null;
  driver_trend: { month: string; revenue: number; anomalies: number; unit_days: number; major_incidents: number }[];
  churn_by_segment: { segment: string; customers: number; predicted_churn: number; avg_probability: number }[];
  top_churn_customers: { customer_id: string; name: string; region_id: string; segment: string; industry: string; churn_probability: number; satisfaction_score: number | null }[];
  recommendation: Recommendation | null;
}

export interface AnomalyPage { run_id: string; rows: AnomalyRow[]; total: number; limit: number; offset: number }
export interface AnomalyDetail {
  run_id: string;
  operation: AnomalyRow & { headcount: number; marketing_spend: number; uptime_imputed: boolean; predicted_label: number };
  baseline_days: number; baseline_window: string;
  deviations: { metric: string; value: number; baseline_mean: number; baseline_sd: number | null; z: number | null; pct_vs_mean: number | null }[];
  incidents_nearby: { incident_id: string; bu_id: string | null; severity: string; category: string | null; opened_at: string; cost_impact: number }[];
  explanation: string; explanation_method: string;
}

export interface OpsMonth {
  month: string; orders: number; fulfillment_hours: number; uptime_pct: number; tickets: number; headcount: number; opex: number;
  orders_per_head: number; capacity: number; utilization: number; orders_target: number | null; fulfillment_target: number | null; uptime_target: number;
}
export interface OpsSummary {
  filters: Record<string, string | null>; latest_month: string;
  kpis: Record<string, { current: number; same_month_last_year: number | null; yoy: number | null }>;
  monthly: OpsMonth[]; orders_forecast: { month: string; orders_forecast: number }[]; incidents: IncidentBreakdown;
  bottlenecks: { region_id: string; bu_id: string; region_name: string; bu_name: string; fulfillment_hours: number; uptime_pct: number; tickets_per_1k_orders: number; orders_per_head_day: number; fulfillment_z: number | null }[];
  assumptions: Record<string, string | number>;
}

export interface OptimizationParams { budget_multiplier: number; total_hires: number; risk_cap_factor: number; min_region_share: number }
export interface RegionAllocation { region_id: string; baseline_spend: number; optimized_spend: number; baseline_hires: number; optimized_hires: number; spend_change_pct: number }
export interface OptimizationRun {
  optimization_id: string; run_id: string; status: string; objective: number; baseline_objective: number; improvement_abs: number;
  improvement_pct: number; parameters: OptimizationParams; triggered_by: string; created_at: string;
}
export interface Constraint { lhs: number; rhs: number; binding?: boolean }
export interface OptimizationDetail extends OptimizationRun {
  result: {
    by_region: RegionAllocation[]; assumptions: Record<string, unknown>;
    result: { engine: string; budget: number; solve_seconds: number; mip_gap: number; total_hires: number;
      constraints: { hires: Constraint; budget: Constraint; risk_cap: Constraint; region_minimums: Record<string, Constraint> };
      allocations: { unit_id: string; region_id: string; bu_id: string; baseline_spend: number; optimized_spend: number; baseline_hires: number; optimized_hires: number; spend_change_pct: number }[] };
  };
}
export interface OptimizationResult {
  optimization_id: string; run_id: string; status: string; parameters: OptimizationParams; objective: number; baseline_objective: number;
  improvement_abs: number; improvement_pct: number; by_region: RegionAllocation[]; assumptions: Record<string, unknown>;
}

export interface TraceLevel {
  level: "recommendation" | "forecast" | "model_output" | "metric" | "dataset"; title: string; ref: string; detail?: string; confidence?: number;
  rows?: Record<string, unknown>[]; kpi?: Kpi;
  models?: { model_version: string; model_name: string; algorithm: string; trained_at: string; predictions: number | null; metrics: Record<string, unknown> }[];
  datasets?: QualityDataset[]; lineage?: { stage: string; status: RunStatus; records_processed: number; ended_at: string; component: string }[];
}
export interface DecisionTrace { decision: Recommendation & { run_id: string; created_at: string }; chain: TraceLevel[] }

export type LeverKey = "demand_change" | "cost_change" | "capacity_change" | "workforce_change" | "marketing_budget_change" | "churn_change";
export interface ScenarioSide { revenue: number; gross_margin: number; opex: number; operating_profit: number; p5: number; cvar95: number }
export interface ScenarioResult {
  label: "SCENARIO"; baseline_label: string; parameters: Record<LeverKey, number>; assumptions: Record<string, string | number>;
  levers: Record<LeverKey, { min: number; max: number; description: string }>;
  regions: { region_id: string; name: string; baseline: ScenarioSide & { utilization: number }; scenario: ScenarioSide & { utilization: number; demanded_revenue: number; capacity_bound: boolean } }[];
  totals: { baseline: ScenarioSide; scenario: ScenarioSide }; delta: ScenarioSide; delta_pct: Record<keyof ScenarioSide, number | null>;
  capacity_bound_regions: string[];
}

export interface QualityIssue { check: string; column?: string; count: number; rate: number; family: string; severity: string; detail?: string }
export interface QualityDataset { dataset: string; rows_checked: number; quality_score: number; issue_count: number; issues: QualityIssue[]; created_at: string }
export interface Quality { run_id: string; overall_quality_score: number; scoring: { weights: Record<string, number>; method: string }; datasets: QualityDataset[] }
export interface QualityDetail {
  run_id: string; dataset: QualityDataset; history: { run_id: string; quality_score: number; issue_count: number; rows_checked: number; created_at: string }[];
  ingestion: { stage?: string; ended_at?: string; record_count?: number; quarantined?: number; duplicates_removed?: number; validation_status?: string; generated?: number };
  pipeline: { stage: string; status: RunStatus; ended_at: string }[];
}

export interface ModelInfo {
  model_version: string; model_name: string; task: string; algorithm: string; run_id: string; metrics: Record<string, unknown>;
  params: Record<string, unknown>; artifact_path: string; trained_at: string; purpose: string | null; features: string[];
  prediction_count: number; positive_predictions: number | null; status: "ACTIVE" | "SUPERSEDED";
}

export interface PipelineRun { run_id: string; started_at: string; ended_at: string | null; stages: number; records_processed: number; errors: number; all_succeeded: boolean; status: RunStatus }
export interface StageRun { stage: string; component: string; status: RunStatus; started_at: string; ended_at: string; duration_s: number; records_processed: number; error_count: number; details: Record<string, unknown> }
export interface SystemInfo {
  runs: PipelineRun[]; latest: { run_id: string; stages: StageRun[] } | null; table_counts: Record<string, number>;
  rust_benchmark: Record<string, unknown> | null; health: Health;
}

export interface SearchResult { type: "customer" | "product" | "region" | "business_unit" | "risk" | "recommendation" | "anomaly"; id: string; label: string; context: string; region_id?: string; bu_id?: string | null }
export interface SearchResponse { query: string; results: SearchResult[]; counts: Record<string, number> }
