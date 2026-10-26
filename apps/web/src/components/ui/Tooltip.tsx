import { useId, useState, type ReactNode } from "react";

/** Accessible tooltip: shows on hover and keyboard focus, linked with aria-describedby. */
export function Tooltip({ content, children, label = "More information" }: { content: ReactNode; children?: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="tip" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className="tip-trigger" aria-label={label} aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
        {children ?? <span aria-hidden="true">i</span>}
      </button>
      {open && <span role="tooltip" id={id} className="tip-body">{content}</span>}
    </span>
  );
}
