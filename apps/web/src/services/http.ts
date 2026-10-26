// The only module allowed to call fetch (enforced by eslint no-restricted-globals).
import type { ApiErrorItem, Envelope } from "../types/api";

// Same-origin by default (Vercel serves the web app and the API together). VITE_API_BASE_URL is the only
// build-time value exposed to the client and must be a public URL, never a secret.
export const API_BASE = `${(import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")}/api/v1`;

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly errors: ApiErrorItem[]) {
    super(errors.map((e) => e.message).join("; ") || `Request failed (HTTP ${status})`);
    this.name = "ApiError";
  }
  get retryable(): boolean {
    return this.status === 0 || this.status >= 500 || this.status === 409;
  }
}

export interface Timing { path: string; ms: number; status: number }
const timings: Timing[] = [];
export const recentTimings = (): readonly Timing[] => timings;

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const t0 = performance.now();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...(init?.headers ?? {}) },
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, [{ code: "NETWORK", message: "API unreachable. Check your connection and retry." }]);
  }
  timings.push({ path, ms: Math.round(performance.now() - t0), status: res.status });
  if (timings.length > 50) timings.shift();
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, [{ code: "BAD_RESPONSE", message: `Unexpected response (HTTP ${res.status})` }]);
  }
  if (!res.ok || !body.success || body.data === null) throw new ApiError(res.status, body.errors ?? []);
  return body.data;
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new ApiError(res.status, [{ code: "EXPORT_FAILED", message: `Export failed (HTTP ${res.status})` }]);
  saveBlob(await res.blob(), filename);
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
