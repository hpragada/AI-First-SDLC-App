import { useState, type FormEvent } from "react";

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
import type { AdminUser } from "../../types";
import {
  useCreateInvitation,
  useResendInvitation,
  useRevokeInvitation,
  useUsers,
} from "./hooks";

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
  const roles = u.memberships.map((m) => `${m.role} @ ${m.project_name}`).join(" · ");
  return [u.is_tenant_admin ? "Tenant-admin" : null, roles].filter(Boolean).join(" · ");
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
  const projectName = currentUser?.memberships[0]?.project_name ?? "Payment Gateway v2";
  const projectId = currentUser?.memberships[0]?.project_id ?? "";
  const [role, setRole] = useState("engineer");

  const duplicate =
    dup || (createInvitation.error instanceof ApiError && createInvitation.error.status === 409);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createInvitation.mutateAsync({
        email,
        name: name || undefined,
        grants: projectId ? [{ project_id: projectId, role }] : undefined,
      });
      onClose();
    } catch {
      /* duplicate surfaced inline */
    }
  };

  return (
    <Drawer
      title="Invite teammate"
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
              <Input type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <div className="t-label" style={{ margin: "var(--space-4) 0 var(--space-2)" }}>
              Initial project & role grants
            </div>
            <div className="u-row" style={{ gap: "var(--space-2)" }}>
              <select className="select" aria-label="Project">
                <option>{projectName}</option>
              </select>
              <select
                className="select"
                aria-label="Role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="engineer">engineer</option>
                <option value="product_owner">product_owner</option>
                <option value="architect">architect</option>
                <option value="reviewer">reviewer</option>
              </select>
            </div>
            <Button variant="ghost" size="sm" type="button" style={{ marginTop: "var(--space-3)" }}>
              + Add another grant
            </Button>
          </>
        )}
      </form>
    </Drawer>
  );
}

export function UsersInvites({ forceView }: { forceView?: UsersView }) {
  const users = useUsers();
  const resend = useResendInvitation();
  const revoke = useRevokeInvitation();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const list = users.data ?? [];
  const view: UsersView =
    forceView ??
    (drawerOpen ? "invite-drawer" : list.length <= 1 && users.isSuccess ? "empty" : "populated");

  const rows = list.map((u) => {
    const pending = u.status !== "active";
    const cells = [
      <div className="u-row-tight" key="n">
        <Avatar size="sm">{u.name ? initials(u.name) : u.email[0]?.toUpperCase()}</Avatar>
        <span className="table__primary">{u.name || u.email}</span>
      </div>,
      u.email,
      pending ? (
        <Badge variant="gate">Invited · pending</Badge>
      ) : (
        <Badge variant="done">Active</Badge>
      ),
      membershipSummary(u),
      pending ? (
        <span className="u-row-tight">
          <Button variant="ghost" size="sm" onClick={() => resend.mutate(u.id)}>
            Resend
          </Button>
          <Button variant="danger" size="sm" onClick={() => revoke.mutate(u.id)}>
            Revoke
          </Button>
        </span>
      ) : (
        <Button variant="ghost" size="sm">
          Manage
        </Button>
      ),
    ];
    return pending ? { cells, style: { background: "var(--warning-bg)" } } : cells;
  });

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Users & invitations</h1>
          <p className="page-head__sub">
            Everyone in the Acme Corp workspace. Invite by email and grant initial project roles.
          </p>
        </div>
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
