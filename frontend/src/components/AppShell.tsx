import { Link, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { cx, StatusDot } from "./ui";

type NavId =
  | "dashboard"
  | "work-items"
  | "runs"
  | "gates"
  | "clarifications"
  | "artifacts"
  | "profile"
  | "onboarding"
  | "integrations"
  | "repositories"
  | "admin"
  | "connect";

const ICON = {
  dashboard: "M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z",
  work: "M4 4h16v4H4zM4 10h16v4H4zM4 16h10v4H4z",
  runs: "M8 5v14l11-7z",
  gate: "M12 2l8 4v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10V6l8-4z",
  clar: "M21 6h-7M3 6h7M3 12h18M3 18h11",
  artifacts: "M4 4h10l6 6v10H4z M14 4v6h6",
  profile: "M14 3H6v18h12V9z M14 3v6h6 M9 13h6M9 16h4",
  onboarding: "M12 3l9 5-9 5-9-5 9-5z M3 13l9 5 9-5",
  integrations: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  repos: "M5 3h11l3 3v15H5z M9 7h6M9 11h6M9 15h4",
  admin: "M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8z M4 21v-1c0-3.3 3.6-5 8-5s8 1.7 8 5v1",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9 M13.7 21a2 2 0 0 1-3.4 0",
};

const NAV: Array<{
  section?: string;
  adminOnly?: boolean;
  items: Array<{ id: NavId; label: string; icon: keyof typeof ICON; href: string; count?: number }>;
}> = [
  {
    items: [
      { id: "dashboard", label: "Workspace Dashboard", icon: "dashboard", href: "/" },
      { id: "work-items", label: "Work Items", icon: "work", href: "/work-items" },
      { id: "runs", label: "Phases & Runs", icon: "runs", href: "/runs" },
      { id: "gates", label: "Gates", icon: "gate", href: "/gates", count: 3 },
      { id: "clarifications", label: "Clarifications", icon: "clar", href: "/clarifications", count: 1 },
      { id: "artifacts", label: "Artifacts & Traceability", icon: "artifacts", href: "/artifacts" },
    ],
  },
  {
    section: "Project",
    items: [
      { id: "profile", label: "Project Profile", icon: "profile", href: "/profile" },
      { id: "onboarding", label: "Onboarding", icon: "onboarding", href: "/onboarding" },
      { id: "integrations", label: "Integrations", icon: "integrations", href: "/integrations" },
      { id: "repositories", label: "Repositories", icon: "repos", href: "/repositories" },
      { id: "connect", label: "Connect Machine", icon: "runs", href: "/connect" },
    ],
  },
  {
    section: "Admin",
    adminOnly: true,
    items: [{ id: "admin", label: "Workspace Admin", icon: "admin", href: "/admin" }],
  },
];

function SvgIcon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {path.split(" M").map((part, index) => (
        <path key={index} d={index === 0 ? part : `M${part}`} />
      ))}
    </svg>
  );
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function activeNav(pathname: string): NavId {
  if (pathname === "/") return "dashboard";
  if (pathname.startsWith("/work-items")) return "work-items";
  if (pathname.startsWith("/runs") || pathname.startsWith("/transcripts")) return "runs";
  if (pathname.startsWith("/gates")) return "gates";
  if (pathname.startsWith("/clarifications")) return "clarifications";
  if (pathname.startsWith("/artifacts") || pathname.startsWith("/traceability")) return "artifacts";
  if (pathname.startsWith("/profile")) return "profile";
  if (pathname.startsWith("/onboarding")) return "onboarding";
  if (pathname.startsWith("/integrations")) return "integrations";
  if (pathname.startsWith("/repositories") || pathname.startsWith("/contracts")) return "repositories";
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/connect") || pathname.startsWith("/setup")) return "connect";
  return "dashboard";
}

export function AppShell() {
  const location = useLocation();
  const { currentUser, selectedProject, setSelectedProjectId, isAdmin } = useAuth();
  const active = activeNav(location.pathname);
  const tenant = currentUser?.tenant.name ?? "Acme Corp";
  const project = selectedProject?.project_name ?? "No project yet";
  const user = currentUser?.user.name ?? "You";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__brand">
          <span className="sidebar__brand-mark" aria-hidden="true" />
          <span className="sidebar__brand-text">edvensoft</span>
        </div>
        <nav className="sidebar__nav" aria-label="Primary">
          {NAV.map((group, index) => {
            if (group.adminOnly && !isAdmin) return null;
            return (
              <div key={group.section ?? index}>
                {group.section && <div className="sidebar__section">{group.section}</div>}
                {group.items.map((item) => (
                  <Link key={item.id} className="nav-item" to={item.href} aria-current={item.id === active ? "page" : undefined}>
                    <SvgIcon path={ICON[item.icon]} />
                    <span className="nav-item__label">{item.label}</span>
                    {item.count !== undefined && <span className="nav-item__count">{item.count}</span>}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="sidebar__foot">
          <span className="companion-pill companion-pill--ready">
            <StatusDot />
            Companion: Ready
          </span>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <button className="switcher" aria-label="Switch tenant">
            <span className="switcher__glyph">{initials(tenant)}</span>
            {tenant}
            <span className="switcher__caret" aria-hidden="true">v</span>
          </button>
          <span className="crumb-sep" aria-hidden="true">/</span>
          <select
            className="switcher"
            aria-label="Switch project"
            value={selectedProject?.project_id ?? ""}
            onChange={(event) => setSelectedProjectId(event.target.value)}
          >
            {currentUser?.memberships.map((membership) => (
              <option key={membership.project_id} value={membership.project_id}>{membership.project_name}</option>
            ))}
            {!currentUser?.memberships.length && <option>{project}</option>}
          </select>
          <span className="u-spacer" />
          <span className="companion-pill companion-pill--ready" style={{ width: "auto" }}>
            <StatusDot />
            Companion: Ready
          </span>
          <button className="bell" aria-label="Notifications, 4 unread">
            <SvgIcon path={ICON.bell} />
            <span className="bell__badge">4</span>
          </button>
          <button className={cx("avatar")} aria-label={`Account menu for ${user}`}>
            {initials(user)}
          </button>
        </header>
        <div className="app-canvas">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
