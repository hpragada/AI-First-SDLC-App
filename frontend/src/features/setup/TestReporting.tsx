import { useState, type FormEvent } from "react";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CopyButton,
  EmptyState,
  Field,
  Input,
  Modal,
  Panel,
  Skeleton,
  Table,
  TokenReveal,
} from "../../components/ui";
import type { CIToken, CITokenIssued } from "../../types";
import { useCiTokens, useCreateCiToken, useRevokeCiToken } from "./hooks";

// View states for the gallery/tests (Bugs-style forceView convention):
// list · empty · add-form · revealed (one-time secret) · revoke (confirm).
export type TestReportingView = "list" | "empty" | "add-form" | "revealed" | "revoke";

// Relative "last used" from the real timestamp; null = the token has never authenticated a post.
function sinceLabel(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "recently";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function shortDate(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  return new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// The CI step to paste — CI-agnostic (any runner that can curl a JUnit file works). The token
// itself is referenced as $SDLC_CI_TOKEN (a CI secret), never baked into the snippet; only the
// project + tenant ids are substituted so it's copy-paste-correct for THIS project.
function ciSnippet(projectId: string, tenantId: string): string {
  return [
    "# After your test suite writes results.xml (JUnit), add this step to your CI:",
    'curl -sf -X POST \\',
    `  "$SDLC_URL/api/projects/${projectId}/test-results/?execution_ref=$CI_RUN_ID" \\`,
    '  -H "Authorization: CI $SDLC_CI_TOKEN" \\',
    `  -H "X-Tenant-ID: ${tenantId}" \\`,
    '  -H "Content-Type: application/xml" \\',
    "  --data-binary @results.xml",
  ].join("\n");
}

// Deterministic sample rows for the gallery/tests (forceView), so states render without a backend.
const SAMPLE: CIToken[] = [
  {
    id: "s1",
    label: "GitHub Actions",
    status: "active",
    last_used_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    created_at: "2026-07-12T09:00:00Z",
  },
  { id: "s2", label: "GitLab nightly", status: "active", last_used_at: null, created_at: "2026-07-18T09:00:00Z" },
  { id: "s3", label: "old-jenkins", status: "revoked", last_used_at: "2026-06-30T09:00:00Z", created_at: "2026-06-02T09:00:00Z" },
];
const SAMPLE_ISSUED: CITokenIssued = { ...SAMPLE[0], id: "new", token: "ci_7Kd9xQ2mNp4vL8wR3tZ0aB5cD6eF1gH" };

function IssuedReveal({ issued, projectId, tenantId, onDone }: {
  issued: CITokenIssued;
  projectId: string;
  tenantId: string;
  onDone: () => void;
}) {
  const snippet = ciSnippet(projectId, tenantId);
  return (
    <Card>
      <CardBody>
        <div className="u-row" style={{ alignItems: "center", gap: "8px", marginBottom: "var(--space-2)" }}>
          <span aria-hidden="true" style={{ color: "var(--text-success)", fontWeight: 500 }}>✓</span>
          <span className="t-h3">Token created</span>
        </div>
        <p className="t-sm" style={{ color: "var(--warning)", marginBottom: "var(--space-3)" }}>
          Copy it now — for security it's shown only once and can't be retrieved later.
        </p>

        <span className="field__label">Token</span>
        <div style={{ maxWidth: "480px", marginBottom: "var(--space-4)" }}>
          <TokenReveal token={issued.token} />
        </div>

        <span className="field__label">Add this step to your CI pipeline</span>
        <div style={{ position: "relative", marginTop: "var(--space-2)" }}>
          <pre
            className="t-mono"
            style={{
              background: "var(--surface-0)",
              border: "0.5px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: "12px 14px",
              margin: 0,
              overflowX: "auto",
              fontSize: "12.5px",
              lineHeight: 1.7,
            }}
          >
            {snippet}
          </pre>
          <div style={{ position: "absolute", top: "8px", right: "8px" }}>
            <CopyButton text={snippet} />
          </div>
        </div>
        <p className="field__help" style={{ marginTop: "var(--space-2)" }}>
          Store the token in your CI secret store as <code className="t-mono">SDLC_CI_TOKEN</code> and set{" "}
          <code className="t-mono">SDLC_URL</code> to this platform's URL. The same snippet works for any CI
          (GitHub Actions, GitLab, Jenkins, CircleCI…).
        </p>

        <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
          <Button variant="primary" onClick={onDone}>
            Done
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function AddTokenForm({ projectId, onIssued }: {
  projectId: string;
  onIssued: (issued: CITokenIssued) => void;
}) {
  const createToken = useCreateCiToken(projectId);
  const [label, setLabel] = useState("");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const issued = await createToken.mutateAsync({ label: label.trim() || undefined });
      onIssued(issued);
      setLabel("");
    } catch {
      /* surfaced inline below */
    }
  };

  return (
    <Card>
      <CardBody>
        <form className="u-row u-wrap" style={{ alignItems: "flex-end", gap: "var(--space-3)" }} onSubmit={onSubmit}>
          <Field
            label="Label"
            help="A name to recognize this token later — e.g. your CI system."
            style={{ marginBottom: 0, flex: 1, minWidth: "240px" }}
          >
            <Input placeholder="GitHub Actions" value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <Button variant="primary" type="submit" disabled={createToken.isPending}>
            {createToken.isPending ? "Generating…" : "Generate token"}
          </Button>
        </form>
        {createToken.isError && (
          <p className="t-sm" style={{ color: "var(--danger)", marginTop: "var(--space-2)" }}>
            {createToken.error instanceof ApiError ? createToken.error.message : "Couldn't create the token. Try again."}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

export function TestReporting({ forceView }: { forceView?: TestReportingView }) {
  const { selectedProject, currentUser } = useAuth();
  const projectId = selectedProject?.project_id;
  const tenantId = currentUser?.tenant.id ?? "<your-tenant-id>";
  const tokens = useCiTokens(projectId);
  const revokeToken = useRevokeCiToken(projectId);

  const [showAdd, setShowAdd] = useState(false);
  const [issued, setIssued] = useState<CITokenIssued | null>(null);
  const [confirming, setConfirming] = useState<CIToken | null>(null);

  const forced = Boolean(forceView);
  const list: CIToken[] = forced ? (forceView === "empty" ? [] : SAMPLE) : tokens.data ?? [];
  const shownIssued = forceView === "revealed" ? SAMPLE_ISSUED : issued;
  const shownConfirm = forceView === "revoke" ? SAMPLE[0] : confirming;
  const formOpen = forceView === "add-form" || (!forced && showAdd);

  const Head = (
    <div className="page-head">
      <div className="page-head__titles">
        <h1 className="t-h1">Test reporting</h1>
        <p className="page-head__sub">
          Tokens let your CI post automated-test results back to this project. Failing tests become tracked defects.
        </p>
      </div>
      {!formOpen && !shownIssued && (
        <Button variant="primary" onClick={() => setShowAdd(true)} disabled={!projectId && !forced}>
          + New token
        </Button>
      )}
    </div>
  );

  // Guard: a token is scoped to a project, so one must be selected first.
  if (!projectId && !forced) {
    return (
      <div className="canvas-pad">
        {Head}
        <Panel>
          <EmptyState
            title="No project selected"
            text="Select or create a project first — CI tokens are issued per project."
          />
        </Panel>
      </div>
    );
  }

  if (!forced && tokens.isLoading) {
    return (
      <div className="canvas-pad">
        {Head}
        <Panel>
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </div>
    );
  }

  if (!forced && tokens.isError) {
    return (
      <div className="canvas-pad">
        {Head}
        <Panel>
          <EmptyState
            title="Couldn't load tokens"
            text={tokens.error instanceof ApiError ? tokens.error.message : "Something went wrong. Refresh to try again."}
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="canvas-pad">
      {Head}

      {shownIssued && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <IssuedReveal
            issued={shownIssued}
            projectId={projectId ?? "<your-project-id>"}
            tenantId={tenantId}
            onDone={() => setIssued(null)}
          />
        </div>
      )}

      {formOpen && !shownIssued && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <AddTokenForm
            projectId={projectId as string}
            onIssued={(res) => {
              setIssued(res);
              setShowAdd(false);
            }}
          />
        </div>
      )}

      {list.length === 0 && !formOpen && !shownIssued ? (
        <Panel>
          <EmptyState
            title="No tokens yet"
            text="Generate one so your CI can report test results back to this project."
            action={
              <Button variant="primary" onClick={() => setShowAdd(true)}>
                + New token
              </Button>
            }
          />
        </Panel>
      ) : list.length > 0 ? (
        <Panel flush>
          <Table
            headers={["Label", "Status", "Last used", "Created", ""]}
            rows={list.map((token) => {
              const revoked = token.status === "revoked";
              return {
                cells: [
                  <span className="table__id" key="l">
                    {token.label || <span style={{ color: "var(--text-muted)" }}>unlabeled</span>}
                  </span>,
                  revoked ? (
                    <Badge variant="outline" key="s">
                      revoked
                    </Badge>
                  ) : (
                    <Badge variant="done" key="s">
                      active
                    </Badge>
                  ),
                  <span key="u" style={{ color: token.last_used_at ? undefined : "var(--text-muted)" }}>
                    {sinceLabel(token.last_used_at)}
                  </span>,
                  <span key="c">{shortDate(token.created_at)}</span>,
                  revoked ? (
                    <span key="a" />
                  ) : (
                    <Button variant="danger" size="sm" key="a" onClick={() => setConfirming(token)}>
                      Revoke
                    </Button>
                  ),
                ],
                className: revoked ? "table__row--muted" : undefined,
              };
            })}
          />
        </Panel>
      ) : null}

      {shownConfirm && (
        <Modal
          title="Revoke token?"
          onClose={() => setConfirming(null)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
              <Button
                variant="danger-solid"
                disabled={revokeToken.isPending}
                onClick={async () => {
                  try {
                    await revokeToken.mutateAsync(shownConfirm.id);
                    setConfirming(null);
                  } catch {
                    /* surfaced inline */
                  }
                }}
              >
                {revokeToken.isPending ? "Revoking…" : "Revoke token"}
              </Button>
            </>
          }
        >
          <p className="t-body">
            Revoking <strong>{shownConfirm.label || "this token"}</strong> stops its CI from reporting results
            immediately. This can't be undone — you'd have to issue a new token.
          </p>
          {revokeToken.isError && (
            <p className="t-sm" style={{ color: "var(--danger)", marginTop: "var(--space-2)" }}>
              {revokeToken.error instanceof ApiError ? revokeToken.error.message : "Couldn't revoke the token. Try again."}
            </p>
          )}
        </Modal>
      )}
    </div>
  );
}
