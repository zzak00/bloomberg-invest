import { Link, Outlet, useLocation } from "react-router";

/** Each tab, and the other paths that belong to it (a filing opened from the index). */
const NAV = [
  { to: "/map", label: "Map", also: [] },
  { to: "/index", label: "Index", also: ["/documents/"] },
  { to: "/checks", label: "Checks", also: [] },
  { to: "/kpis", label: "KPIs", also: [] },
];

export function Shell() {
  const { pathname } = useLocation();
  // "page" on the tab itself, "true" on a page that belongs to it.
  const current = (item: (typeof NAV)[number]) =>
    pathname === item.to ? "page" : item.also.some((p) => pathname.startsWith(p)) ? "true" : undefined;

  return (
    <div className="shell">
      <header className="header">
        <Link to="/index" className="brand" aria-label="Bloomberg Invest, home">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Bloomberg Invest</span>
          <span className="brand-chip">CSE</span>
        </Link>
        <nav className="nav" aria-label="Primary">
          {NAV.map((item) => (
            <Link key={item.to} to={item.to} aria-current={current(item)}>
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
