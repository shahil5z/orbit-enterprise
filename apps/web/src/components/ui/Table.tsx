import { useMemo, useState, type ReactNode } from "react";
import { saveBlob } from "../../services/http";
import { toCsv } from "../../utils/csv";
import { Button } from "./Button";
import { EmptyState } from "./States";

export interface Column<T> {
  key: string; header: string; render?: (row: T) => ReactNode; value: (row: T) => string | number | null | undefined;
  align?: "left" | "right"; sortable?: boolean; width?: string;
}

/** Data table: sort, text filter, pagination, row details (click or Enter) and CSV export of the filtered rows. */
export function Table<T>({ rows, columns, caption, pageSize = 10, onRowClick, rowKey, exportName, filterable = true, initialSort, dense }:
  { rows: readonly T[]; columns: Column<T>[]; caption: string; pageSize?: number; onRowClick?: (row: T) => void;
    rowKey: (row: T) => string; exportName?: string; filterable?: boolean; initialSort?: { key: string; dir: "asc" | "desc" }; dense?: boolean }) {
  const [sort, setSort] = useState(initialSort ?? null);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let r = needle ? rows.filter((row) => columns.some((c) => String(c.value(row) ?? "").toLowerCase().includes(needle))) : [...rows];
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      if (col) {
        r = r.sort((a, b) => {
          const va = col.value(a), vb = col.value(b);
          if (va === vb) return 0;
          if (va === null || va === undefined) return 1;
          if (vb === null || vb === undefined) return -1;
          const cmp = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
          return sort.dir === "asc" ? cmp : -cmp;
        });
      }
    }
    return r;
  }, [rows, columns, q, sort]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const cur = Math.min(page, pages - 1);
  const visible = filtered.slice(cur * pageSize, cur * pageSize + pageSize);

  const toggle = (key: string) => {
    setSort((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));
    setPage(0);
  };
  const exportCsv = () => {
    const csv = toCsv(filtered, columns.map((c) => ({ key: c.key, header: c.header, value: c.value })));
    saveBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `${exportName ?? "orbit-table"}.csv`);
  };

  return (
    <div className={`table-wrap ${dense ? "table-dense" : ""}`}>
      {(filterable || exportName) && (
        <div className="table-tools">
          {filterable && (
            <label className="table-filter">
              <span className="sr-only">Filter {caption}</span>
              <input className="input" type="search" placeholder="Filter rows" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
            </label>
          )}
          <span className="muted small" aria-live="polite">{filtered.length} of {rows.length} rows</span>
          {exportName && <Button size="sm" onClick={exportCsv} disabled={!filtered.length}>Export CSV</Button>}
        </div>
      )}
      <div className="table-scroll">
        <table className="table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const aria = active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none";
                return (
                  <th key={c.key} scope="col" aria-sort={c.sortable === false ? undefined : aria} style={{ width: c.width, textAlign: c.align ?? "left" }}>
                    {c.sortable === false ? c.header : (
                      <button type="button" className="th-sort" onClick={() => toggle(c.key)}>
                        {c.header}<span aria-hidden="true" className="sort-mark">{active ? (sort!.dir === "asc" ? " \u25B2" : " \u25BC") : " \u2195"}</span>
                      </button>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={rowKey(row)} className={onRowClick ? "row-click" : undefined} tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={onRowClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); } } : undefined}>
                {columns.map((c) => <td key={c.key} style={{ textAlign: c.align ?? "left" }}>{c.render ? c.render(row) : (c.value(row) ?? "")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && <EmptyState title={q ? "No rows match the filter" : "No rows"} />}
      </div>
      {pages > 1 && (
        <nav className="pager" aria-label={`${caption} pagination`}>
          <Button size="sm" onClick={() => setPage(cur - 1)} disabled={cur === 0}>Previous</Button>
          <span className="small">Page {cur + 1} of {pages}</span>
          <Button size="sm" onClick={() => setPage(cur + 1)} disabled={cur >= pages - 1}>Next</Button>
        </nav>
      )}
    </div>
  );
}
