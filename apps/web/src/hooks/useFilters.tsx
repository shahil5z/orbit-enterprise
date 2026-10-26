import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

export const FILTER_KEYS = ["start", "end", "region_id", "bu_id", "segment", "product_id", "category"] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];
export type Filters = Record<FilterKey, string | null>;

const STORAGE = "orbit.filters";

interface Ctx { filters: Filters; setFilter: (k: FilterKey, v: string | null) => void; reset: () => void; active: number }
const FilterContext = createContext<Ctx | null>(null);

function fromStorage(): Partial<Filters> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE) ?? "{}") as Partial<Filters>;
  } catch {
    return {};
  }
}

/** Global filters live in the URL (shareable, back button works) and are mirrored to localStorage (persist). */
export function FilterProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const [stored, setStored] = useState<Partial<Filters>>(fromStorage);
  const filters = useMemo(() => {
    const f = {} as Filters;
    const anyInUrl = FILTER_KEYS.some((k) => params.has(k));
    for (const k of FILTER_KEYS) f[k] = params.get(k) ?? (anyInUrl ? null : stored[k] ?? null);
    return f;
  }, [params, stored]);

  const write = useCallback((next: Filters) => {
    localStorage.setItem(STORAGE, JSON.stringify(next));
    setStored(next);
    setParams((p) => {
      const out = new URLSearchParams(p);
      for (const k of FILTER_KEYS) {
        const v = next[k];
        if (v) out.set(k, v);
        else out.delete(k);
      }
      return out;
    }, { replace: true });
  }, [setParams]);

  const setFilter = useCallback((k: FilterKey, v: string | null) => write({ ...filters, [k]: v || null }), [filters, write]);
  const reset = useCallback(() => write(Object.fromEntries(FILTER_KEYS.map((k) => [k, null])) as Filters), [write]);
  const active = FILTER_KEYS.filter((k) => filters[k]).length;
  const value = useMemo(() => ({ filters, setFilter, reset, active }), [filters, setFilter, reset, active]);
  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

export function useFilters(): Ctx {
  const c = useContext(FilterContext);
  if (!c) throw new Error("useFilters outside FilterProvider");
  return c;
}

export function pick(f: Filters, keys: readonly FilterKey[]): Record<string, string | null> {
  return Object.fromEntries(keys.map((k) => [k, f[k]]));
}
