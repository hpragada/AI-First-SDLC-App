import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError, fieldError, formError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Avatar,
  Badge,
  Banner,
  Button,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Panel,
  Table,
  WriteError,
} from "../../components/ui";
import type { AdminUser, Invitation, InvitationSent } from "../../types";
import {
  useCreateInvitation,
  useInvitations,
  useResendInvitation,
  useRevokeInvitation,
  useUsers,
} from "./hooks";
import { ROLES, roleLabel } from "./roles";
import { SetupReturnLink } from "./SetupReturnLink";
import { fullWhen, whenLabel } from "./when";

// 2026-10-09 (team-approved mockup 2): after Send invite and Resend, the admin is told what
// actually happened to the email. Before, the drawer just closed, and the link existed only in
// the server terminal.
function SentNotice({ sent }: { sent: InvitationSent }) {
  if (sent.email_delivery === "console") {
    return <Banner variant="info">Invite created. The link is in the server terminal.</Banner>;
  }
  if (!sent.email_sent) {
    return (
      <Banner variant="danger">
        The invite was saved but the email couldn&apos;t be sent. Try Resend in a few minutes.
      </Banner>
    );
  }
  return <Banner variant="success">Invite emailed to {sent.email}</Banner>;
}

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
  onSent,
}: {
  dup?: boolean;
  onClose: () => void;
  onSent?: (sent: InvitationSent) => void;
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

  // Screen Words group 6b. This waited for a 409 and nothing else. Inviting an email that
  // already has an account makes the server answer 400 with the reason filed under `email`, so
  // the drawer just sat there — no message, no closed drawer, nothing to act on. Invalid emails
  // and refused role grants were silent for the same reason.
  //
  // `duplicate` still means only "this person is already here", because it also hides the rest
  // of the form and disables Send: an ordinary validation complaint must not do either.
  const duplicate =
    dup || (createInvitation.error instanceof ApiError && createInvitation.error.status === 409);
  // What the server said about the email field, whichever status it used.
  const emailError = duplicate
    ? `${email} is already a member of this workspace.`
    : fieldError(createInvitation.error, "email");
  // Anything the server refused that no field on screen owns — a bad role grant, a project the
  // inviter cannot grant on, an expired session. Previously swallowed entirely.
  const otherError = formError(createInvitation.error, ["email", "name", "grants"]);

  const updateGrant = (i: number, patch: Partial<{ project_id: string; role: string }>) =>
    setGrants((g) => g.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));

  const addGrant = () =>
    setGrants((g) => [...g, { project_id: defaultProjectId, role: "engineer" }]);

  const removeGrant = (i: number) => setGrants((g) => g.filter((_, idx) => idx !== i));

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const sent = await createInvitation.mutateAsync({
        email,
        name: name || undefined,
        grants: grants.filter((g) => g.project_id).length ? grants.filter((g) => g.project_id) : undefined,
      });
      onSent?.(sent);
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
        {/* Screen Words group 6b: a refusal no field owns, in the drawer rather than nowhere. */}
        {otherError && (
          <div style={{ marginBottom: "var(--space-4)" }}>
            <WriteError title="Couldn't send the invitation" detail={createInvitation.error} />
          </div>
        )}
        <Field
          label={
            <>
              Work email <span className="req">*</span>
            </>
          }
          error={emailError}
        >
          <Input
            type="email"
            placeholder="name@acme.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={Boolean(emailError)}
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
  const [sent, setSent] = useState<InvitationSent | null>(null);

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
      <span key="s" style={{ display: "flex", flexDirection: "column", gap: "2px", alignItems: "flex-start" }}>
        <Badge variant="gate">Invited · waiting to join</Badge>
        {inv.sent_at && (
          <span className="t-xs u-muted">
            sent <time dateTime={inv.sent_at} title={fullWhen(inv.sent_at)}>{whenLabel(inv.sent_at)}</time>
          </span>
        )}
      </span>,
      invitationGrantSummary(inv, projectNames),
      <span className="u-row-tight" key="a">
        <Button variant="ghost" size="sm" onClick={() => resend.mutate(inv.id, { onSuccess: setSent })}>
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

      {sent && !resend.isError && !revoke.isError && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <SentNotice sent={sent} />
        </div>
      )}

      {/* S.No 220: both queries are read as `?? []`, so a failed one produced an empty roster and
          this screen then told an admin their whole team was just them. That is the most alarming
          form the bug takes — it looks like data loss rather than a failed request. */}
      {!forceView && (users.isError || invitations.isError) ? (
        <Panel>
          <ErrorState
            title="We couldn't load your team"
            detail={users.error ?? invitations.error}
            onRetry={() => {
              void users.refetch();
              void invitations.refetch();
            }}
          />
        </Panel>
      ) : view === "empty" ? (
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
          {/* Bugs S.No 219: Resend and Revoke were fire-and-forget — `.mutate()` with nothing
              reading `isError`. An expired or already-accepted invitation failed silently, and
              the admin clicked Resend again and again believing it had worked. The screen has
              always had an error state for the READ; the writes had none. */}
          {(resend.isError || revoke.isError) && (
            <div style={{ padding: "var(--space-4) var(--space-4) 0" }}>
              <WriteError
                title={resend.isError ? "Invitation not resent" : "Invitation not revoked"}
                detail={resend.error ?? revoke.error}
              />
            </div>
          )}
          <Table
            headers={["Name", "Email", "Status", "Projects & roles", ""]}
            rows={rows}
          />
        </Panel>
      )}

      {(view === "invite-drawer" || view === "dup-error") && (
        <InviteDrawer
          dup={view === "dup-error"}
          onClose={() => setDrawerOpen(false)}
          onSent={setSent}
        />
      )}
    </div>
  );
}
