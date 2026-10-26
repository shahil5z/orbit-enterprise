import type { ReactNode } from "react";
import type { ApiError } from "../../services/http";
import { Button } from "./Button";

export function EmptyState({ title = "No data for this selection", hint, action }: { title?: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state state-empty" role="status">
      <p className="state-title">{title}</p>
      {hint && <p className="state-hint">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Could not load data" }: { error: ApiError | Error; onRetry?: () => void; title?: string }) {
  const status = "status" in error ? (error as ApiError).status : undefined;
  return (
    <div className="state state-error" role="alert">
      <p className="state-title">{title}</p>
      <p className="state-hint">{error.message}{status ? ` (HTTP ${status})` : ""}</p>
      {onRetry && <Button variant="primary" size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" style={{ width: `${90 - i * 12}%` }} />)}
    </div>
  );
}

interface AsyncLike<T> { status: "loading" | "error" | "success"; data: T | null; error: ApiError | null; reload: () => void }

/** Renders loading, error (with retry), empty and success states for any useApi result. */
export function Async<T>({ state, children, isEmpty, empty, loadingRows }:
  { state: AsyncLike<T>; children: (data: T) => ReactNode; isEmpty?: (d: T) => boolean; empty?: ReactNode; loadingRows?: number }) {
  if (state.status === "error" && !state.data) return <ErrorState error={state.error!} onRetry={state.reload} />;
  if (state.data === null) return <Loading rows={loadingRows} />;
  if (isEmpty?.(state.data)) return <>{empty ?? <EmptyState />}</>;
  return (
    <>
      {state.status === "error" && <ErrorState title="Refresh failed; showing previous data" error={state.error!} onRetry={state.reload} />}
      <div aria-busy={state.status === "loading"}>{children(state.data)}</div>
    </>
  );
}
