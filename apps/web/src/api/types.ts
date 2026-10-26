// Response contracts for the ORBIT FastAPI service (apps/api). Mirrors the envelope in envelope.py.
export interface ApiError {
  code: string;
  message: string;
  details?: { field: string; message: string }[];
}

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  metadata: { api_version: string; generated_at: string; request_id: string; count?: number };
  errors: ApiError[];
}

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Health {
  status: "ok" | "degraded";
  database: { status: "up" | "down"; database?: string; version?: string };
}

export interface Risk {
  entity_type: "region" | "business_unit";
  region_id: string;
  bu_id: string | null;
  risk_score: number;
  risk_level: RiskLevel;
  confidence: number;
  recommended_action: string;
  explanation: string;
}

export interface Recommendation {
  decision_id: string;
  scope: "company" | "region";
  entity_id: string;
  priority: RiskLevel;
  observation: string;
  cause: string;
  forecast: string;
  risk: string;
  recommendation: string;
  expected_impact: string;
  confidence: number;
  evidence: { source: string; ref: string; value: unknown }[];
}

export interface OptimizationParams {
  budget_multiplier?: number;
  total_hires?: number;
  risk_cap_factor?: number;
  min_region_share?: number;
}

export interface OptimizationSummary {
  optimization_id: string;
  status: string;
  objective: number | null;
  baseline_objective: number;
  improvement_abs: number | null;
  improvement_pct: number | null;
}
