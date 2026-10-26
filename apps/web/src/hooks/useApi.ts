import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../services/http";

export type AsyncState<T> =
  | { status: "loading"; data: T | null; error: null }
  | { status: "error"; data: T | null; error: ApiError }
  | { status: "success"; data: T; error: null };

const cache = new Map<string, { at: number; value: unknown }>();
const TTL_MS = 60_000;

/** Fetch with loading/error/success states, retry, stale-while-revalidate cache and race protection. */
export function useApi<T>(key: string | null, fn: () => Promise<T>): AsyncState<T> & { reload: () => void } {
  const cached = key ? (cache.get(key)?.value as T | undefined) : undefined;
  const [state, setState] = useState<AsyncState<T>>(
    cached !== undefined ? { status: "success", data: cached, error: null } : { status: "loading", data: null, error: null },
  );
  const [nonce, setNonce] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (key === null) return;
    let live = true;
    const hit = cache.get(key);
    const fresh = hit && Date.now() - hit.at < TTL_MS && nonce === 0;
    if (fresh) {
      setState({ status: "success", data: hit.value as T, error: null });
      return;
    }
    setState((s) => ({ status: "loading", data: s.data, error: null }));
    fnRef.current().then(
      (value) => {
        cache.set(key, { at: Date.now(), value });
        if (live) setState({ status: "success", data: value, error: null });
      },
      (e: unknown) => {
        const err = e instanceof ApiError ? e : new ApiError(0, [{ code: "CLIENT", message: String(e) }]);
        if (live) setState((s) => ({ status: "error", data: s.data, error: err }));
      },
    );
    return () => {
      live = false;
    };
  }, [key, nonce]);

  const reload = useCallback(() => {
    if (key) cache.delete(key);
    setNonce((n) => n + 1);
  }, [key]);
  return { ...state, reload };
}

export function clearApiCache(): void {
  cache.clear();
}

/** Imperative mutation state for POST actions (optimization, scenarios). */
export function useMutation<P, T>(fn: (p: P) => Promise<T>) {
  const [state, setState] = useState<{ status: "idle" | "loading" | "success" | "error"; data: T | null; error: ApiError | null }>(
    { status: "idle", data: null, error: null },
  );
  const run = useCallback(async (p: P) => {
    setState((s) => ({ ...s, status: "loading", error: null }));
    try {
      const data = await fn(p);
      setState({ status: "success", data, error: null });
      return data;
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, [{ code: "CLIENT", message: String(e) }]);
      setState((s) => ({ ...s, status: "error", error: err }));
      return null;
    }
  }, [fn]);
  return { ...state, run };
}
