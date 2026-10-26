import { useId, useState, type ReactNode } from "react";
import { Button } from "./Button";

/** Wraps a chart with a title, an accessible description and a data-table alternative for screen readers and keyboard users. */
export function ChartContainer({ title, description, children, table, height = 260, actions, legend }:
  { title: string; description: string; children: ReactNode; table?: ReactNode; height?: number; actions?: ReactNode; legend?: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  const id = useId();
  return (
    <figure className="chart" aria-labelledby={`${id}-t`} aria-describedby={`${id}-d`}>
      <figcaption className="chart-head">
        <div>
          <h3 className="chart-title" id={`${id}-t`}>{title}</h3>
          <p className="chart-desc" id={`${id}-d`}>{description}</p>
        </div>
        <div className="chart-actions">
          {actions}
          {table && <Button size="sm" variant="ghost" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>{asTable ? "Show chart" : "Show table"}</Button>}
        </div>
      </figcaption>
      {legend}
      {asTable && table ? <div className="chart-table">{table}</div> : <div className="chart-body" style={{ height }} role="img" aria-label={`${title}. ${description}`}>{children}</div>}
    </figure>
  );
}
