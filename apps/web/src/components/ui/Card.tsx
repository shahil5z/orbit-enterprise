import type { ReactNode } from "react";

export function Card({ title, subtitle, actions, children, className = "", id }:
  { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section className={`card ${className}`} aria-labelledby={title ? headingId : undefined} id={id}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2 className="card-title" id={headingId}>{title}</h2>}
            {subtitle && <p className="card-sub">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}
