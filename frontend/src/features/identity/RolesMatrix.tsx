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
import { useRoleCoverage, useSetMembership, useUsers } from "./hooks";

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

function rolesFor(user: AdminUser, projectId: string): Set<string> {
  const roles = new Set(
    user.memberships.filter((m) => m.project_id === projectId).map((m) => m.role),
  );
  if (user.is_tenant_admin) roles.add("admin");
  return roles;
}

export function RolesMatrix({ forceView }: { forceView?: RolesView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const projectName = selectedProject?.project_name ?? "Payment Gateway v2";
  const users = useUsers();
  const coverage = useRoleCoverage(projectId);
  const setMembership = useSetMembership(projectId);

  const view: RolesView = forceView ?? (setMembership.isPending ? "saving" : "gap-warning");

  const list = users.data ?? [];
  const blockedRoles = coverage.data?.roles.filter((r) => r.gate_blocked) ?? [];

  const headers = ["User", ...ROLE_COLS.map((c) => <span title={c.key}>{c.short}</span>)];
  const rows = list.map((u) => {
    const held = projectId ? rolesFor(u, projectId) : new Set<string>();
    return [
      <span className="table__primary" key="u">
        {u.name}
      </span>,
      ...ROLE_COLS.map((c) => (
        <Switch
          key={c.key}
          label={`${u.name} — ${c.key}`}
          checked={held.has(c.key)}
          onChange={() =>
            projectId && setMembership.mutate({ user_id: u.id, role: c.key })
          }
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
            Per-project role grants. Each role gates specific decisions — uncovered gate roles make
            their gate unactionable.
          </p>
        </div>
        <select className="select" style={{ maxWidth: "220px" }} aria-label="Project">
          <option>{projectName}</option>
        </select>
      </div>

      {view === "saving" && (
        <Banner variant="info">
          Saving role change for Tom Reyes (reviewer @ {projectName})…
        </Banner>
      )}

      {view === "last-admin-guard" && (
        <div className="modal-scrim">
          <Modal
            title="Can't remove the last admin"
            footer={
              <>
                <Button variant="secondary">Cancel</Button>
                <Button variant="primary">Promote a member</Button>
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
          {blockedRoles.length > 0 && (
            <div style={{ marginBottom: "var(--space-4)" }}>
              <Banner variant="warning" title={`No reviewer on ${projectName}`}>
                {blockedRoles.map((r) => r.note).filter(Boolean).join(" ") ||
                  "The merge gate & code-review gate will be unactionable until someone holds the reviewer role."}
              </Banner>
            </div>
          )}
          <Panel flush>
            <div style={{ overflowX: "auto" }}>
              <Table matrix headers={headers} rows={rows} />
            </div>
          </Panel>

          <div style={{ marginTop: "var(--space-4)" }}>
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
                      {r.role}
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
