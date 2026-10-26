import { useId } from "react";

export function DateRange({ start, end, min, max, onChange, label = "Date range" }:
  { start: string | null; end: string | null; min?: string; max?: string; onChange: (s: string | null, e: string | null) => void; label?: string }) {
  const id = useId();
  const invalid = Boolean(start && end && start > end);
  return (
    <fieldset className="field daterange" aria-describedby={invalid ? `${id}-err` : undefined}>
      <legend className="field-label">{label}</legend>
      <div className="daterange-inputs">
        <label className="sr-only" htmlFor={`${id}-s`}>Start date</label>
        <input id={`${id}-s`} className="input" type="date" value={start ?? ""} min={min} max={end ?? max}
          onChange={(e) => onChange(e.target.value || null, end)} />
        <span aria-hidden="true">to</span>
        <label className="sr-only" htmlFor={`${id}-e`}>End date</label>
        <input id={`${id}-e`} className="input" type="date" value={end ?? ""} min={start ?? min} max={max}
          onChange={(e) => onChange(start, e.target.value || null)} />
      </div>
      {invalid && <span id={`${id}-err`} className="field-error">Start must be before end</span>}
    </fieldset>
  );
}
