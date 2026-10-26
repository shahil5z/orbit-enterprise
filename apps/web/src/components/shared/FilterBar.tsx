import { useMemo } from "react";
import { useFilters, type FilterKey } from "../../hooks/useFilters";
import { useReference } from "../../hooks/useReference";
import { Button, DateRange, Select } from "../ui";

/** Global, persistent filter bar. Each page declares which filters its backend endpoint honours. */
export function FilterBar({ keys, note }: { keys: readonly FilterKey[]; note?: string }) {
  const { filters, setFilter, reset, active } = useFilters();
  const { dims } = useReference();
  const has = (k: FilterKey) => keys.includes(k);
  const products = useMemo(
    () => (dims?.products ?? []).filter((p) => !filters.bu_id || p.bu_id === filters.bu_id).map((p) => ({ value: p.id, label: `${p.name} (${p.id})` })),
    [dims, filters.bu_id],
  );
  if (!keys.length) return null;
  return (
    <section className="filterbar" aria-label="Global filters">
      {(has("start") || has("end")) && (
        <DateRange start={filters.start} end={filters.end} min={dims?.date_range.start} max={dims?.date_range.end}
          onChange={(s, e) => { if (s !== filters.start) setFilter("start", s); else setFilter("end", e); }} />
      )}
      {has("region_id") && <Select label="Region" value={filters.region_id} onChange={(v) => setFilter("region_id", v)}
        options={(dims?.regions ?? []).map((r) => ({ value: r.id, label: r.name }))} allLabel="All regions" />}
      {has("bu_id") && <Select label="Business unit" value={filters.bu_id} onChange={(v) => setFilter("bu_id", v)}
        options={(dims?.business_units ?? []).map((r) => ({ value: r.id, label: r.name }))} allLabel="All business units" />}
      {has("segment") && <Select label="Segment" value={filters.segment} onChange={(v) => setFilter("segment", v)}
        options={(dims?.segments ?? []).map((s) => ({ value: s, label: s }))} allLabel="All segments" />}
      {has("product_id") && <Select label="Product" value={filters.product_id} onChange={(v) => setFilter("product_id", v)} options={products} allLabel="All products" />}
      {has("category") && <Select label="Ops category" value={filters.category} onChange={(v) => setFilter("category", v)}
        options={(dims?.incident_categories ?? []).map((s) => ({ value: s, label: s }))} allLabel="All categories" />}
      <div className="filterbar-meta">
        {note && <span className="muted small">{note}</span>}
        <Button size="sm" variant="ghost" onClick={reset} disabled={!active}>Clear filters{active ? ` (${active})` : ""}</Button>
      </div>
    </section>
  );
}
