import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { useA11yReviewQueue } from "../features/a11y/hooks";
import { CompanionDropBanner } from "../features/identity/CompanionDropBanner";
import { useCompanionStatus } from "../features/identity/hooks";
import { useDashboard } from "../features/observability/hooks";
import type { ProjectTrack } from "../types";
import { closeOnTab, cx, FloatingLayer, StatusDot, useDismissable, useFloatingPosition } from "./ui";

type NavId =
  | "dashboard"
  | "work-items"
  | "runs"
  | "gates"
  | "clarifications"
  | "artifacts"
  | "a11y"
  | "profile"
  | "onboarding"
  | "integrations"
  | "repositories"
  | "test-reporting"
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
  "test-reporting": "M9 3h6v2H9z M6 5h12v16H6z M9 12l2 2 4-4",
  admin: "M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8z M4 21v-1c0-3.3 3.6-5 8-5s8 1.7 8 5v1",
  a11y: "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z M12 6.1a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8z M7 10.5h10 M12 11v4 M12 15l-2.2 3.5 M12 15l2.2 3.5",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9 M13.7 21a2 2 0 0 1-3.4 0",
};

// What a nav item is allowed to know about the person and the project they have open.
// Bugs S.No 221: this used to be a single hardcoded `adminOnly` boolean, so the second rule
// ("hide the brownfield wizard on a greenfield project") had nowhere to go and was simply
// never written — every project was offered every item. A predicate takes any rule; a second
// one-off boolean is how the first one became a problem.
type NavContext = { isAdmin: boolean; track?: ProjectTrack };

const NAV: Array<{
  section?: string;
  adminOnly?: boolean;
  items: Array<{
    id: NavId;
    label: string;
    icon: keyof typeof ICON;
    href: string;
    count?: number;
    /** Shown when this returns true, or when it is absent. */
    when?: (ctx: NavContext) => boolean;
  }>;
}> = [
  {
    items: [
      { id: "dashboard", label: "Workspace Dashboard", icon: "dashboard", href: "/" },
      { id: "work-items", label: "Work Items", icon: "work", href: "/work-items" },
      { id: "runs", label: "Phases & Runs", icon: "runs", href: "/runs" },
      { id: "gates", label: "Gates", icon: "gate", href: "/gates" },
      { id: "clarifications", label: "Clarifications", icon: "clar", href: "/clarifications" },
      { id: "artifacts", label: "Artifacts & Traceability", icon: "artifacts", href: "/artifacts" },
      // Accessibility (QA-23). Its own item rather than buried under Gates or Artifacts: it is a
      // named job a named role does repeatedly, and the count is how the reviewer learns there is
      // work without going to look. ALWAYS present, never revealed by a run — "no menu" and
      // "nothing was ever checked" must not look the same (D-A11Y-94).
      // `/a11y/pages`, NOT `/a11y`. The tab strip puts Pages & audit first because that is
      // where the work starts — and the sidebar used to disagree with it, landing every first
      // visit on the review queue, the one tab with nothing on it until an audit has run. The
      // queue's count still rides on this item, so a reviewer loses nothing.
      { id: "a11y", label: "Accessibility", icon: "a11y", href: "/a11y/pages" },
    ],
  },
  {
    section: "Project",
    items: [
      { id: "profile", label: "Project Profile", icon: "profile", href: "/profile" },
      // Brownfield only (S.No 221). Onboarding reads an EXISTING codebase and reports what is
      // missing from it; on a project started from scratch there is nothing to read, and the
      // screen behind this used to assert "Brownfield project" over whatever you had open.
      // Hidden rather than disabled: an item you can never usefully click is clutter, and a
      // permanently dead row in every greenfield sidebar is worse than an absence.
      // `!== "greenfield"` and not `=== "brownfield"`, so an API too old to send the track
      // shows the item rather than hiding it from the people who need it.
      {
        id: "onboarding", label: "Onboarding", icon: "onboarding", href: "/onboarding",
        when: (ctx) => ctx.track !== "greenfield",
      },
      { id: "integrations", label: "Integrations", icon: "integrations", href: "/integrations" },
      { id: "repositories", label: "Repositories", icon: "repos", href: "/repositories" },
      {
        id: "test-reporting", label: "Test Reporting", icon: "test-reporting", href: "/test-reporting",
        when: (ctx) => ctx.isAdmin,
      },
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
  if (pathname.startsWith("/a11y")) return "a11y";
  if (pathname.startsWith("/profile")) return "profile";
  if (pathname.startsWith("/onboarding")) return "onboarding";
  if (pathname.startsWith("/integrations")) return "integrations";
  if (pathname.startsWith("/repositories") || pathname.startsWith("/contracts")) return "repositories";
  if (pathname.startsWith("/test-reporting")) return "test-reporting";
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/connect") || pathname.startsWith("/setup")) return "connect";
  return "dashboard";
}

// Account menu on the topbar avatar — the only affordance that invokes the (already
// wired) AuthContext.logout(). Kept self-contained so its open/close state and the
// sign-out lifecycle never leak into the shell.
function AccountMenu({ name, email }: { name: string; email: string }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const itemRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);

  // Close on outside click + Escape, and focus the first item on open. Shared with the work
  // items board's row menu (S.No 140) — the markup differs, this part must not. The menu is drawn
  // in the floating layer like every other popup (S.No 166), so the hook is told where it is.
  useDismissable(open, close, rootRef, itemRef, popRef);
  useFloatingPosition(open, triggerRef, popRef, { align: "end", gap: 8 });

  // Any navigation dismisses the menu.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  const onSignOut = async () => {
    if (signingOut) return; // guard double-clicks
    setSigningOut(true);
    try {
      // logout() clears the query cache + selectedProjectId even if the network call
      // fails (AuthContext onSettled), so redirect regardless of the outcome.
      await logout();
    } catch {
      /* client session already cleared; fall through to the redirect */
    } finally {
      setOpen(false);
      navigate("/login", { replace: true });
    }
  };

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        ref={triggerRef}
        className="avatar"
        aria-label={`Account menu for ${name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {initials(name)}
      </button>
      {open && (
        <FloatingLayer>
        <div
          ref={popRef}
          className="popover-layer account-menu__pop"
          role="menu"
          aria-label="Account"
          onKeyDown={closeOnTab(close, triggerRef)}
        >
          <div className="account-menu__head">
            <div className="account-menu__name">{name}</div>
            <div className="account-menu__email">{email}</div>
          </div>
          <div className="account-menu__sep" role="separator" />
          <button
            ref={itemRef}
            className="account-menu__item account-menu__item--danger"
            role="menuitem"
            onClick={onSignOut}
            disabled={signingOut}
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
        </FloatingLayer>
      )}
    </div>
  );
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { currentUser, selectedProject, setSelectedProjectId, isAdmin, projects } = useAuth();
  const active = activeNav(location.pathname);

  // Live nav/bell counts from the real needs-me rollup (Bugs.xlsx row 29.2) — no longer
  // hardcoded. The dashboard query polls, so these stay current; zero when nothing needs you.
  // Bugs S.No 222: the rollup is now filtered to the person reading it, and carries true totals
  // beside lists trimmed to 20 — the lengths of those lists under-reported a busy project. The
  // lengths remain as the fallback for an API too old to send the totals.
  const dashboard = useDashboard(selectedProject?.project_id);
  const needs = dashboard.data?.needs_me;
  const gateCount = needs?.counts?.gates ?? needs?.gates.length ?? 0;
  const clarCount = needs?.counts?.clarifications ?? needs?.clarifications.length ?? 0;
  // Accessibility findings waiting on THIS person (QA-23, D-A11Y-94). The item is always in the
  // sidebar; the count is how a reviewer learns there is work without going to look, and it was
  // missing — the item shipped as a plain link while the mockup and the decision both said
  // otherwise.
  //
  // Gated on `can_review`, and that is the point of the number rather than a detail: the badge
  // means "waiting on you". Someone without the reviewer role can still open the queue and read
  // every finding — they simply have no work there, so no badge. A count on their sidebar would
  // be an alert for something they cannot act on.
  const a11yQueue = useA11yReviewQueue(selectedProject?.project_id);
  const a11yCount = a11yQueue.data?.can_review ? a11yQueue.data.queue.length : 0;
  const navCounts: Partial<Record<NavId, number>> = {
    gates: gateCount,
    clarifications: clarCount,
    a11y: a11yCount,
  };
  const bellCount = gateCount + clarCount;

  // Companion pill reflects the real runner status (Bugs.xlsx row 30) — not a hardcoded "Ready".
  // Poll gently here since the shell is mounted on every screen (Bugs.xlsx row 13); the
  // Connect/Phases screens keep the fast 4s cadence via their own useRunners call (shared key).
  //
  // Scoped to the SELECTED project. It used to ask `runners.some(r => r.online)` — "is any
  // machine of mine alive anywhere?" — so a companion running another project's work kept this
  // green while the machine executing the phase you were watching was dead. That was the one
  // defect in this class with no time limit: it never corrected itself.
  const companion = useCompanionStatus(selectedProject?.project_id,
                                       { poll: true, intervalMs: 15000 });
  const companionPillClass = {
    ready: "companion-pill--ready",
    checking: "companion-pill--connecting",
    offline: "companion-pill--offline",
    unknown: "companion-pill--offline",
  }[companion.state];
  // "unknown" (first load) reads as not-connected on purpose: the pill must never claim a
  // machine is there before the answer has arrived.
  const companionPillText = {
    ready: "Companion: Ready",
    checking: "Companion: checking…",
    offline: "Companion: not connected",
    unknown: "Companion: not connected",
  }[companion.state];
  // Only `offline` is actionable. `checking` deliberately offers nothing: one missed heartbeat
  // is not yet a problem, and a reconnect prompt that appeared and vanished every time a laptop
  // got briefly busy would train people to ignore it. `unknown` offers nothing either — the
  // first load has not learned anything yet to act on.
  const companionNeedsAction = companion.state === "offline" && Boolean(selectedProject);
  // Read from the SELECTED project, not the first membership: switching projects has to
  // change what the sidebar offers, or the greenfield rule would only ever be right once.
  const navContext: NavContext = { isAdmin, track: selectedProject?.track };
  const tenant = currentUser?.tenant.name ?? "Acme Corp";
  const project = selectedProject?.project_name ?? "No project yet";
  const user = currentUser?.user.name ?? "You";
  const userEmail = currentUser?.user.email ?? "";

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
                {group.items.map((item) => {
                  if (item.when && !item.when(navContext)) return null;
                  const count = item.count ?? navCounts[item.id];
                  return (
                    <Link key={item.id} className="nav-item" to={item.href} aria-current={item.id === active ? "page" : undefined}>
                      <SvgIcon path={ICON[item.icon]} />
                      <span className="nav-item__label">{item.label}</span>
                      {count !== undefined && count > 0 && <span className="nav-item__count">{count}</span>}
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>
        <div className="sidebar__foot">
          <span className={cx("companion-pill", companionPillClass)}>
            <StatusDot />
            {companionPillText}
          </span>
          {/* The status alone leaves the reader stuck: knowing the machine is gone is only
              useful next to the one thing that fixes it. Said here rather than in the top bar
              because this column has the room for a second line. "Reconnect" vs "Connect"
              turns on whether a machine was ever set up for this project — telling somebody to
              re-connect something they never connected is its own small dead end. */}
          {companionNeedsAction && (
            <Link className="sidebar__foot-link" to="/connect">
              {companion.everConnected ? "Reconnect" : "Connect"} to run phases
              {selectedProject?.project_name ? ` on ${selectedProject.project_name}` : ""} ↗
            </Link>
          )}
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
            {/* `projects`, not `memberships` — memberships are one row per role, so a person
                holding three roles on one project saw it listed three times (and React
                complained about the duplicate keys, every render). */}
            {projects.map((membership) => (
              <option key={membership.project_id} value={membership.project_id}>{membership.project_name}</option>
            ))}
            {projects.length === 0 && <option>{project}</option>}
          </select>
          <span className="u-spacer" />
          {/* The top bar has no room for a second line, so when there is something to do the
              pill itself becomes the way to do it rather than a dead label. */}
          {companionNeedsAction ? (
            <Link
              to="/connect"
              className={cx("companion-pill", companionPillClass)}
              style={{ width: "auto" }}
              title={`${companion.everConnected ? "Reconnect" : "Connect"} your machine`}
            >
              <StatusDot />
              {companionPillText}
            </Link>
          ) : (
            <span className={cx("companion-pill", companionPillClass)} style={{ width: "auto" }}>
              <StatusDot />
              {companionPillText}
            </span>
          )}
          {/* N2: this had a live count and no click handler — the one control saying "something
              needs you" was the one that did not respond. It opens the Needs-me queue, which is
              the dashboard's own list with a link into every item; a second notification centre
              would be a second place the same information lives and drifts. At zero it still
              opens, and the queue says you are all caught up: a control that silently does
              nothing under some conditions is the bug being fixed. */}
          <button
            type="button"
            className="bell"
            aria-label={`Notifications, ${bellCount} unread`}
            onClick={() => navigate({ pathname: "/", hash: "#needs-me" })}
          >
            <SvgIcon path={ICON.bell} />
            {bellCount > 0 && <span className="bell__badge">{bellCount}</span>}
          </button>
          <AccountMenu name={user} email={userEmail} />
        </header>
        <div className="app-canvas">
          {/* Above the page, so somebody deep in a work item learns their machine has gone
              without having to look at the corner of the screen.

              Mounted only while the companion is offline, and that is a requirement of the
              component rather than a nicety: it polls the project's runs every 4s to find out
              whether anything is actually stranded, and the app shell is on every screen in the
              product. Rendered unconditionally it would put that poll everywhere — the
              background churn S.No 12 asked us to cut. */}
          {companionNeedsAction && (
            <CompanionDropBanner
              projectId={selectedProject?.project_id}
              everConnected={companion.everConnected}
            />
          )}
          <Outlet />
        </div>
      </div>
    </div>
  );
}
