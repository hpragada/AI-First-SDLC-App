import { useRef, useState } from "react";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Assess,
  Banner,
  Button,
  Modal,
  Panel,
  Switch,
  Table,
} from "../../components/ui";
import type { AdminUser } from "../../types";
import { useRevokeMembership, useRoleCoverage, useSetMembership, useSetTenantAdmin, useUsers } from "./hooks";
import { roleLabel } from "./roles";

// S-08 view states: gap-warning · saving · last-admin-guard.
export type RolesView = "gap-warning" | "saving" | "last-admin-guard";

const ROLE_COLS: { key: string; short: string }[] = [
  { key: "product_owner", short: "PO" },
  { key: "architect", short: "Arch" },
  { key: "designer", short: "Design" },
  { key: "tech_lead", short: "Lead" },
  { key: "engineer", short: "Eng" },
  { key: "reviewer", short: "Rev" },
  { key: "qa_lead", short: "QA" },
  { key: "security_engineer", short: "Sec" },
  { key: "devops", short: "DevOps" },
  { key: "admin", short: "Admin" },
];

// role → membership id, for this project only — needed to revoke a specific grant.
function membershipMapFor(user: AdminUser, projectId: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const m of user.memberships) {
    if (m.project_id === projectId) map.set(m.role, m.id);
  }
  return map;
}

export function RolesMatrix({ forceView }: { forceView?: RolesView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const projectName = selectedProject?.project_name ?? "this project";
  const users = useUsers();
  const coverage = useRoleCoverage(projectId);
  const setMembership = useSetMembership(projectId);
  const revokeMembership = useRevokeMembership(projectId);
  const setTenantAdmin = useSetTenantAdmin();
  const [guardOpen, setGuardOpen] = useState(false);
  // The change currently being saved, so the banner names the real user + role instead of a
  // hardcoded sample (Bugs.xlsx row 53: was always "Tom Reyes (reviewer …)").
  const [pending, setPending] = useState<{ name: string; role: string } | null>(null);

  const view: RolesView =
    forceView ??
    (guardOpen
      ? "last-admin-guard"
      : setMembership.isPending || revokeMembership.isPending || setTenantAdmin.isPending
        ? "saving"
        : "gap-warning");

  const list = users.data ?? [];
  // Every gate role nobody on this project holds — not only the ones the platform calls
  // "blocked".
  //
  // The warning used to be drawn from `gate_blocked`, which means "nobody holds it AND no admin
  // could approve instead". Only a workspace admin can open this screen, and the platform counts
  // any workspace admin as backup for every gate — so whoever is reading this page IS the backup,
  // `gate_blocked` was false for them, and the warning could never appear. A workspace cannot
  // lose its last admin either, so it could not appear anywhere. An unfilled role was reported
  // only as a red line at the bottom of the page, under a ten-column table, while its gates
  // quietly fell to the admins.
  const uncovered = coverage.data?.roles.filter((r) => !r.covered) ?? [];
  // The genuine hard block is still worth its own, stronger wording: nobody holds the role and
  // there is no admin either, so that gate cannot be approved by anyone.
  const blocked = uncovered.filter((r) => r.gate_blocked);
  const coverageRef = useRef<HTMLDivElement>(null);
  const showCoverage = () => {
    coverageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    coverageRef.current?.focus();
  };
  // The team's option B+: ONE line however many roles are empty, so a new project — which starts
  // with nearly all eight unfilled — cannot turn this into a wall of text that pushes the table
  // off the screen. It names the roles while one or two are missing (the steady state once a
  // project is staffed, where naming them saves the trip down the page) and counts them beyond
  // that.
  const names = uncovered.map((r) => roleLabel(r.role));
  const gapTitle =
    names.length === 1
      ? `Nobody holds ${names[0]} on ${projectName}.`
      : names.length === 2
        ? `Nobody holds ${names[0]} or ${names[1]} on ${projectName}.`
        : `${names.length} roles have nobody on ${projectName}.`;
  const gapDetail =
    blocked.length > 0
      ? names.length === 1
        ? "That gate cannot be approved by anyone until someone holds the role."
        : "Those gates cannot be approved by anyone until someone holds the roles."
      : names.length === 1
        ? "That gate falls to an admin meanwhile —"
        : "Those gates fall to an admin meanwhile —";

  const toggleRole = (u: AdminUser, roleKey: string) => {
    setPending({ name: u.name, role: roleKey });
    if (roleKey === "admin") {
      setTenantAdmin.mutate(
        { userId: u.id, isTenantAdmin: !u.is_tenant_admin },
        {
          onError: (err) => {
            if (err instanceof ApiError && err.status === 409) setGuardOpen(true);
          },
        },
      );
      return;
    }
    if (!projectId) return;
    const membershipId = membershipMapFor(u, projectId).get(roleKey);
    if (membershipId) {
      revokeMembership.mutate(membershipId);
    } else {
      setMembership.mutate({ user_id: u.id, role: roleKey });
    }
  };

  const headers = ["User", ...ROLE_COLS.map((c) => <span title={c.key}>{c.short}</span>)];
  const rows = list.map((u) => {
    const membershipMap = projectId ? membershipMapFor(u, projectId) : new Map<string, string>();
    return [
      <span className="table__primary" key="u">
        {u.name}
      </span>,
      ...ROLE_COLS.map((c) => (
        <Switch
          key={c.key}
          label={`${u.name} — ${c.key}`}
          checked={c.key === "admin" ? u.is_tenant_admin : membershipMap.has(c.key)}
          onChange={() => toggleRole(u, c.key)}
        />
      )),
    ];
  });

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Roles & memberships</h1>
          <p className="page-head__sub">
            Per-project role grants. Each role gates specific decisions — a role nobody holds
            leaves its gate to an admin.
          </p>
        </div>
        {/* The project these roles belong to, as a plain line. It was a dropdown holding exactly
            one option and no handler, two inches under the top bar's project switcher, which is
            the real one — two pickers on one screen, only one of which worked. */}
        <p className="t-sm u-muted">
          Project <strong className="u-strong">{projectName}</strong>
        </p>
      </div>

      {view === "saving" && (
        <Banner variant="info">
          {pending
            ? `Saving role change for ${pending.name} (${roleLabel(pending.role)} @ ${projectName})…`
            : "Saving role change…"}
        </Banner>
      )}

      {view === "last-admin-guard" && (
        <div className="modal-scrim">
          <Modal inline
            title="Can't remove the last admin"
            footer={
              <>
                <Button variant="secondary" onClick={() => setGuardOpen(false)}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={() => setGuardOpen(false)}>
                  Promote a member
                </Button>
              </>
            }
          >
            <Banner variant="danger">
              You're the only tenant-admin. Promote another member to admin before removing your own
              admin role, or the workspace would be left unmanageable.
            </Banner>
          </Modal>
        </div>
      )}

      {view === "gap-warning" && (
        <>
          {uncovered.length > 0 && (
            <div style={{ marginBottom: "var(--space-4)" }}>
              <Banner variant={blocked.length > 0 ? "danger" : "warning"}>
                <strong className="u-strong">{gapTitle}</strong> {gapDetail}
                {blocked.length === 0 && (
                  <>
                    {" "}
                    <button type="button" className="btn-link" onClick={showCoverage}>
                      see gate-role coverage
                    </button>
                    .
                  </>
                )}
              </Banner>
            </div>
          )}
          <Panel flush>
            <div style={{ overflowX: "auto" }}>
              <Table matrix headers={headers} rows={rows} />
            </div>
          </Panel>

          {/* `tabIndex={-1}` so the warning's link can put the cursor here, not just scroll the
              page: a keyboard user following it lands in the box rather than back at the top.
              `Panel` does not forward an id, so the wrapper carries it. */}
          <div
            id="gate-role-coverage"
            ref={coverageRef}
            tabIndex={-1}
            style={{ marginTop: "var(--space-4)", scrollMarginTop: "var(--space-6)" }}
          >
            <Panel title="Gate-role coverage">
              <div className="u-stack">
                {(coverage.data?.roles ?? []).map((r) => (
                  <div className="u-row-tight" key={r.role}>
                    {r.covered ? (
                      <Assess state="complete">✓</Assess>
                    ) : (
                      <Assess state="missing">✗</Assess>
                    )}
                    <span className={r.covered ? "t-sm" : "t-sm u-danger"}>
                      {roleLabel(r.role)}
                      {r.covered
                        ? ` — ${r.holders.map((h) => h.name).join(", ")}`
                        : ` — nobody${r.note ? ` (${r.note})` : ""}`}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
