import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Avatar,
  Badge,
  Button,
  Drawer,
  EmptyState,
  Field,
  Input,
  Panel,
  Table,
} from "../../components/ui";
import type { AdminUser, Invitation } from "../../types";
import {
  useCreateInvitation,
  useInvitations,
  useResendInvitation,
  useRevokeInvitation,
  useUsers,
} from "./hooks";
import { ROLES, roleLabel } from "./roles";
import { SetupReturnLink } from "./SetupReturnLink";

// S-07 view states: populated · invite-drawer · dup-error · empty.
export type UsersView = "populated" | "invite-drawer" | "dup-error" | "empty";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function membershipSummary(u: AdminUser) {
  const roles = u.memberships.map((m) => `${roleLabel(m.role)} @ ${m.project_name}`).join(" · ");
  return [u.is_tenant_admin ? "Tenant-admin" : null, roles].filter(Boolean).join(" · ");
}

function invitationGrantSummary(inv: Invitation, projectNames: Map<string, string>) {
  // The backend normalizes grants down to {project_id, role} (no name) when an invitation
  // is created — resolve against the projects this admin already knows about for display.
  return inv.grants
    .map((g) => `${roleLabel(g.role)} @ ${g.project_name ?? projectNames.get(g.project_id) ?? g.project_id}`)
    .join(" · ");
}

function InviteDrawer({
  dup,
  onClose,
}: {
  dup?: boolean;
  onClose: () => void;
}) {
  const { currentUser } = useAuth();
  const createInvitation = useCreateInvitation();
  const [email, setEmail] = useState(dup ? "sarah@acme.com" : "");
  const [name, setName] = useState("");

  const projects = useMemo(() => {
    const seen = new Map<string, string>();
    for (const m of currentUser?.memberships ?? []) seen.set(m.project_id, m.project_name);
    return Array.from(seen, ([project_id, project_name]) => ({ project_id, project_name }));
  }, [currentUser]);
  const defaultProjectId = projects[0]?.project_id ?? "";
  const [grants, setGrants] = useState([{ project_id: defaultProjectId, role: "engineer" }]);

  const duplicate =
    dup || (createInvitation.error instanceof ApiError && createInvitation.error.status === 409);

  const updateGrant = (i: number, patch: Partial<{ project_id: string; role: string }>) =>
    setGrants((g) => g.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));

  const addGrant = () =>
    setGrants((g) => [...g, { project_id: defaultProjectId, role: "engineer" }]);

  const removeGrant = (i: number) => setGrants((g) => g.filter((_, idx) => idx !== i));

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createInvitation.mutateAsync({
        email,
        name: name || undefined,
        grants: grants.filter((g) => g.project_id).length ? grants.filter((g) => g.project_id) : undefined,
      });
      onClose();
    } catch {
      /* duplicate surfaced inline */
    }
  };

  return (
    <Drawer
      title="Invite teammate"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="invite-form"
            disabled={duplicate}
            aria-disabled={duplicate}
          >
            Send invite
          </Button>
        </>
      }
    >
      <form id="invite-form" onSubmit={onSubmit}>
        <Field
          label={
            <>
              Work email <span className="req">*</span>
            </>
          }
          error={duplicate ? `${email} is already a member of this workspace.` : undefined}
        >
          <Input
            type="email"
            placeholder="name@acme.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={duplicate}
          />
        </Field>
        {!duplicate && (
          <>
            <Field label="Name (optional)">
              <Input type="text" placeholder="e.g. Jordan Lee" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <div className="t-label" style={{ margin: "var(--space-4) 0 var(--space-2)" }}>
              Initial project & role grants
            </div>
            {grants.map((grant, i) => (
              <div className="u-row" style={{ gap: "var(--space-2)", marginBottom: "var(--space-2)" }} key={i}>
                <select
                  className="select"
                  aria-label="Project"
                  value={grant.project_id}
                  onChange={(e) => updateGrant(i, { project_id: e.target.value })}
                >
                  {projects.length === 0 && <option value="">No project</option>}
                  {projects.map((p) => (
                    <option key={p.project_id} value={p.project_id}>
                      {p.project_name}
                    </option>
                  ))}
                </select>
                <select
                  className="select"
                  aria-label="Role"
                  value={grant.role}
                  onChange={(e) => updateGrant(i, { role: e.target.value })}
                >
                  {ROLES.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.label}
                    </option>
                  ))}
                </select>
                {grants.length > 1 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    aria-label="Remove this grant"
                    title="Remove this grant"
                    onClick={() => removeGrant(i)}
                  >
                    ✕
                  </Button>
                )}
              </div>
            ))}
            <Button variant="ghost" size="sm" type="button" onClick={addGrant} style={{ marginTop: "var(--space-1)" }}>
              + Add another grant
            </Button>
          </>
        )}
      </form>
    </Drawer>
  );
}

export function UsersInvites({ forceView }: { forceView?: UsersView }) {
  const { currentUser } = useAuth();
  const users = useUsers();
  const invitations = useInvitations();
  const resend = useResendInvitation();
  const revoke = useRevokeInvitation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const list = users.data ?? [];
  // GET /users/ only ever returns accepted accounts — pending invites are a separate
  // resource (GET /invitations/) that has to be merged in for the table to be honest
  // about who's been invited and hasn't joined yet.
  const pendingInvites = (invitations.data ?? []).filter((i) => i.status === "pending");
  const projectNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of currentUser?.memberships ?? []) map.set(m.project_id, m.project_name);
    for (const u of list) for (const m of u.memberships) map.set(m.project_id, m.project_name);
    return map;
  }, [currentUser, list]);
  // Bugs.xlsx row 31.1: the table must show whenever there's anyone to list (the admin always is
  // one row) — the old heuristic hid it behind an "It's just you" empty state, so registered/invited
  // users only appeared once the Invite drawer flipped the view. Reserve empty for a truly empty
  // list (which, since the admin always exists, is effectively never a live state).
  const hasAnyRow = list.length > 0 || pendingInvites.length > 0;
  const view: UsersView =
    forceView ??
    (drawerOpen
      ? "invite-drawer"
      : users.isSuccess && !hasAnyRow
        ? "empty"
        : "populated");

  const activeRows = list.map((u) => [
    <div className="u-row-tight" key="n">
      <Avatar size="sm">{u.name ? initials(u.name) : u.email[0]?.toUpperCase()}</Avatar>
      <span className="table__primary">{u.name || u.email}</span>
    </div>,
    u.email,
    <Badge variant="done" key="s">
      Active
    </Badge>,
    membershipSummary(u),
    <Link to="/admin/roles" className="btn btn--ghost btn--sm" key="a">
      Manage
    </Link>,
  ]);

  const pendingRows = pendingInvites.map((inv) => ({
    cells: [
      <div className="u-row-tight" key="n">
        <Avatar size="sm">{inv.name ? initials(inv.name) : inv.email[0]?.toUpperCase()}</Avatar>
        <span className="table__primary">{inv.name || inv.email}</span>
      </div>,
      inv.email,
      <Badge variant="gate" key="s">
        Invited · pending
      </Badge>,
      invitationGrantSummary(inv, projectNames),
      <span className="u-row-tight" key="a">
        <Button variant="ghost" size="sm" onClick={() => resend.mutate(inv.id)}>
          Resend
        </Button>
        <Button variant="danger" size="sm" onClick={() => revoke.mutate(inv.id)}>
          Revoke
        </Button>
      </span>,
    ],
    style: { background: "var(--warning-bg)" },
  }));

  const rows = [...pendingRows, ...activeRows];

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Users & invitations</h1>
          <p className="page-head__sub">
            Everyone in the {currentUser?.tenant.name ?? "your"} workspace. Invite by email and grant
            initial project roles.
          </p>
        </div>
        <SetupReturnLink />
        <Button variant="primary" onClick={() => setDrawerOpen(true)}>
          + Invite
        </Button>
      </div>

      {view === "empty" ? (
        <Panel>
          <EmptyState
            title="It's just you so far"
            text="Invite teammates and assign roles — gates need role-holders to be actionable."
            action={
              <Button variant="primary" onClick={() => setDrawerOpen(true)}>
                + Invite
              </Button>
            }
          />
        </Panel>
      ) : (
        <Panel flush>
          <Table
            headers={["Name", "Email", "Status", "Projects & roles", ""]}
            rows={rows}
          />
        </Panel>
      )}

      {(view === "invite-drawer" || view === "dup-error") && (
        <InviteDrawer dup={view === "dup-error"} onClose={() => setDrawerOpen(false)} />
      )}
    </div>
  );
}
