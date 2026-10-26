import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusIndicator } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { GlobalSearch } from "./GlobalSearch";
import { ROUTES, routeFor } from "./routes";

const GROUPS = [...new Set(ROUTES.map((r) => r.group))];

export function Layout() {
  const loc = useLocation();
  const route = routeFor(loc.pathname);
  const [open, setOpen] = useState(false);
  const health = useApi("health", api.health);
  useEffect(() => setOpen(false), [loc.pathname]);
  const hs = health.status === "error" ? "DOWN" : health.data?.status === "ok" ? "UP" : health.data ? "DEGRADED" : "RUNNING";
  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Primary">
        <NavLink to="/" className="brand">
          <img src="/logo-64.png" alt="" width={34} height={34} />
          <span><span className="brand-name">ORBIT // ENTERPRISE</span><br /><span className="brand-sub">DECISION INTELLIGENCE</span></span>
        </NavLink>
        <nav className="nav">
          {GROUPS.map((g) => (
            <div className="nav-group" key={g}>
              <div className="nav-group-label">{g}</div>
              {ROUTES.filter((r) => r.group === g).map((r) => <NavLink key={r.path} to={{ pathname: r.path, search: loc.search }}>{r.label}</NavLink>)}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">Simulated enterprise dataset. All figures come from the ORBIT API and PostgreSQL.</div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button type="button" className="btn btn-secondary btn-sm menu-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>Menu</button>
          <div className="topbar-title">
            <h1>{route?.label ?? "ORBIT"}</h1>
            <p>{route?.subtitle}</p>
          </div>
          <div className="topbar-right">
            <GlobalSearch />
            <span className="pill-sim">Simulated enterprise dataset</span>
            <span title={health.data?.database.version}><StatusIndicator status={hs} label={`API ${hs === "UP" ? "online" : hs.toLowerCase()}`} /></span>
          </div>
        </header>
        <main id="main" className="content" tabIndex={-1}>
          {route && <FilterBar keys={route.filters} note={route.filters.length ? "Filters persist across pages and in the URL" : undefined} />}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
