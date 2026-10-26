import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabDef { id: string; label: string }
/** WAI-ARIA tabs with arrow-key navigation. */
export function Tabs({ tabs, active, onChange, children, label }:
  { tabs: TabDef[]; active: string; onChange: (id: string) => void; children: ReactNode; label: string }) {
  const base = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    const n = tabs.length;
    const next = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i - 1 + n) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    const t = tabs[next];
    if (t) { onChange(t.id); refs.current[next]?.focus(); }
  };
  return (
    <div className="tabs">
      <div role="tablist" aria-label={label} className="tablist">
        {tabs.map((t, i) => (
          <button key={t.id} ref={(el) => { refs.current[i] = el; }} role="tab" type="button" id={`${base}-${t.id}`}
            aria-selected={active === t.id} aria-controls={`${base}-panel`} tabIndex={active === t.id ? 0 : -1}
            className={`tab ${active === t.id ? "tab-active" : ""}`} onClick={() => onChange(t.id)} onKeyDown={(e) => onKey(e, i)}>
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${base}-panel`} aria-labelledby={`${base}-${active}`} className="tabpanel">{children}</div>
    </div>
  );
}
