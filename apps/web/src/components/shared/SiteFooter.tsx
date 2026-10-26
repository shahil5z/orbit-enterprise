export const CREDIT = "An independent portfolio project \u00b7 \u00a9 2026 Shahil";

/** Shared credit line rendered by the app shell and the landing page. */
export function SiteFooter({ className = "app-foot" }: { className?: string }) {
  return <footer className={className} data-testid="site-footer">{CREDIT}</footer>;
}
