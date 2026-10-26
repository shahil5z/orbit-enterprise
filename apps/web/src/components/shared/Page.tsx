import { useEffect, type ReactNode } from "react";

/** Sets the document title and renders page-level intro text. The h1 lives in the top bar. */
export function Page({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  useEffect(() => { document.title = `${title} | ORBIT // ENTERPRISE`; }, [title]);
  return <>{intro && <p className="muted small">{intro}</p>}{children}</>;
}
