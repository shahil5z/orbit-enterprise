import type {
  Envelope, Health, OptimizationParams, OptimizationSummary, Recommendation, Risk, RiskLevel,
} from "./types.js";

export class ApiRequestError extends Error {
  constructor(public readonly status: number, public readonly errors: Envelope<unknown>["errors"]) {
    super(errors.map((e) => `${e.code}: ${e.message}`).join("; ") || `HTTP ${status}`);
  }
}

export class OrbitClient {
  constructor(private readonly baseUrl: string = "http://localhost:8000/api/v1") {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const body = (await res.json()) as Envelope<T>;
    if (!res.ok || !body.success || body.data === null) {
      throw new ApiRequestError(res.status, body.errors ?? []);
    }
    return body.data;
  }

  health(): Promise<Health> {
    return this.request<Health>("/health");
  }

  risks(level?: RiskLevel): Promise<{ run_id: string; risks: Risk[] }> {
    const q = level ? `?level=${encodeURIComponent(level)}` : "";
    return this.request(`/risks${q}`);
  }

  recommendations(): Promise<{ run_id: string; recommendations: Recommendation[] }> {
    return this.request("/recommendations");
  }

  runOptimization(params: OptimizationParams): Promise<OptimizationSummary> {
    return this.request("/optimization/run", { method: "POST", body: JSON.stringify(params) });
  }
}
