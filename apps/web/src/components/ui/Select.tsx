import { useId } from "react";

export interface Option { value: string; label: string }
export function Select({ label, value, options, onChange, allLabel = "All", disabled, hideLabel }:
  { label: string; value: string | null; options: Option[]; onChange: (v: string | null) => void; allLabel?: string | null; disabled?: boolean; hideLabel?: boolean }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id} className={hideLabel ? "sr-only" : "field-label"}>{label}</label>
      <select id={id} className="input" value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
        {allLabel !== null && <option value="">{allLabel}</option>}
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
