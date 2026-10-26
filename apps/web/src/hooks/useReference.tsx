import { createContext, useContext, useMemo, type ReactNode } from "react";
import { api } from "../services/api";
import type { Dimensions, Kpi } from "../types/api";
import { useApi } from "./useApi";

interface Ref { kpis: Record<string, Kpi>; dims: Dimensions | null; regionName: (id?: string | null) => string; buName: (id?: string | null) => string }
const RefContext = createContext<Ref>({ kpis: {}, dims: null, regionName: (id) => id ?? "", buName: (id) => id ?? "" });

/** Loads the KPI governance catalogue and dimensions once and shares them app-wide. */
export function ReferenceProvider({ children }: { children: ReactNode }) {
  const k = useApi("kpis", api.kpis);
  const d = useApi("dimensions", api.dimensions);
  const value = useMemo<Ref>(() => {
    const kpis = Object.fromEntries((k.data?.kpis ?? []).map((x) => [x.key, x]));
    const rn = new Map((d.data?.regions ?? []).map((r) => [r.id, r.name]));
    const bn = new Map((d.data?.business_units ?? []).map((r) => [r.id, r.name]));
    return {
      kpis, dims: d.data,
      regionName: (id) => (id ? rn.get(id) ?? id : ""),
      buName: (id) => (id ? bn.get(id) ?? id : ""),
    };
  }, [k.data, d.data]);
  return <RefContext.Provider value={value}>{children}</RefContext.Provider>;
}

export const useReference = () => useContext(RefContext);
