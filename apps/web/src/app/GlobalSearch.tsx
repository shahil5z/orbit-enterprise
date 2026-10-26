import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import type { SearchResult } from "../types/api";

function target(r: SearchResult): string {
  switch (r.type) {
    case "region": return `/risk?entity=${r.id}`;
    case "risk": return `/risk?entity=${r.region_id ?? r.id}`;
    case "business_unit": return `/intelligence?bu_id=${r.id}`;
    case "product": return `/intelligence?product_id=${r.id}`;
    case "customer": return `/risk?entity=${r.region_id ?? ""}`;
    case "recommendation": return `/decisions?id=${encodeURIComponent(r.id)}`;
    case "anomaly": return `/anomalies?id=${encodeURIComponent(r.id)}`;
  }
}

/** Global search backed by GET /api/v1/search (customers, products, regions, BUs, risks, recommendations, anomalies). */
export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const id = useId();
  const seq = useRef(0);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setResults(null); setErr(null); return; }
    const n = ++seq.current;
    const t = setTimeout(() => {
      api.search(term).then((r) => { if (n === seq.current) { setResults(r.results); setErr(null); setIdx(0); } },
        (e: Error) => { if (n === seq.current) setErr(e.message); });
    }, 220);
    return () => clearTimeout(t);
  }, [q]);

  const go = (r: SearchResult) => { setOpen(false); setQ(""); nav(target(r)); };
  const list = results ?? [];
  return (
    <div className="search" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false); }}>
      <label htmlFor={id} className="sr-only">Search entities</label>
      <input id={id} className="input" type="search" placeholder="Search customers, products, regions, decisions" value={q}
        role="combobox" aria-expanded={open && q.trim().length >= 2} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={list[idx] ? `${id}-${idx}` : undefined}
        onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, list.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
          else if (e.key === "Enter" && list[idx]) go(list[idx]!);
          else if (e.key === "Escape") setOpen(false);
        }} />
      {open && q.trim().length >= 2 && (
        <div className="search-pop" id={`${id}-list`} role="listbox" aria-label="Search results">
          {err && <div role="option" aria-selected="false" className="small">Search failed: {err}</div>}
          {!err && results === null && <div role="option" aria-selected="false" className="small muted">Searching</div>}
          {!err && results?.length === 0 && <div role="option" aria-selected="false" className="small muted">No matches</div>}
          {list.map((r, i) => (
            <div key={`${r.type}-${r.id}`} id={`${id}-${i}`} role="option" aria-selected={i === idx} tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()} onClick={() => go(r)}>
              <span className="search-type">{r.type.replace("_", " ")}</span>
              <span><strong>{r.label}</strong> <span className="muted small">{r.context}</span></span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
