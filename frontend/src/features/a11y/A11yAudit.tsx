// S-38 — Pages & audit (task 8a).
//
// The brownfield way in. Everything the accessibility capability has done until now was a side
// effect of BUILDING something: a story ran, its suite drove some screens, and whatever it
// happened to visit got captured. An application that was imported rather than built here has
// no story and no suite, so nothing anywhere says which pages it even has — and the platform
// cannot go and look, because it has no access to the running application and never will.
//
// So this screen is two facts the platform cannot discover: which pages exist, and where the
// application answers. Everything else follows from them.
//
// **A page is identified by its path.** There is no hidden id — the database's one rule is one
// row per (project, path). That makes editing the text of a path indistinguishable from adding
// a page, which is why registering goes through a confirm step that shows the difference before
// anything is written. See `AddPages` below, and `preview_registration` on the platform.
import { useState } from "react";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  EmptyState,
  Modal,
  Panel,
  Skeleton,
  Switch,
  Table,
  Textarea,
} from "../../components/ui";
import { useRunners } from "../identity/hooks";
import type { A11yAudit as A11yAuditRow, A11yRegistrationPreview, A11yRoute } from "../../types";
import { A11yTabs } from "./A11yTabs";
import {
  useA11yAudits,
  useA11yRoutes,
  usePreviewA11yRoutes,
  useRegisterA11yRoutes,
  useStartA11yAudit,
} from "./hooks";

// Mirrors `apps.a11y.capture.MAX_SCREENS`. It bounds ONE capture document, not an application:
// a bigger audit runs in more passes. Shown so the count on screen is the platform's own
// arithmetic rather than a number the reader has to trust.
const PAGES_PER_PASS = 60;

const STATUS_LABEL: Record<string, string> = {
  pending: "Waiting for a machine",
  claimed: "Starting",
  capturing: "Visiting pages",
  judging: "Checking what was found",
  complete: "Complete",
  failed: "Could not run",
};

function auditBadge(status: string): "done" | "failed" | "waiting" {
  if (status === "complete") return "done";
  if (status === "failed") return "failed";
  return "waiting";
}

function when(value: string | null | undefined): string {
  if (!value) return "";
  return new Date(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── adding pages ────────────────────────────────────────────────────────────
//
// One box. There used to be two — a line-per-path form beside this one — and it was dropped
// because its name separator was two spaces, which nothing could validate: a single space
// produces a path containing a space, and the path checker rejects empty paths, full URLs,
// paths not starting with `/` and line breaks, but not spaces. So a typo nobody can see would
// register a page that cannot exist and be reported unreachable on every audit, forever.

function AddPages({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [confirming, setConfirming] = useState<A11yRegistrationPreview | undefined>();
  const [replace, setReplace] = useState(false);
  const preview = usePreviewA11yRoutes(projectId);
  const register = useRegisterA11yRoutes(projectId);
  const error = (preview.error ?? register.error) as Error | undefined;

  if (confirming) {
    const missing = confirming.missing;
    return (
      <Modal
        title="Ready to register"
        onClose={() => setConfirming(undefined)}
        footer={
          <>
            <Button
              variant="primary"
              disabled={register.isPending}
              onClick={() =>
                register
                  .mutateAsync({ routesText: text, replace })
                  .then(onClose)
                  .catch(() => undefined)
              }
            >
              Register {confirming.adding.length + confirming.updating.length} pages
            </Button>
            <Button variant="ghost" onClick={() => setConfirming(undefined)}>
              Back
            </Button>
          </>
        }
      >
        <p className="t-sm u-body">
          <strong>{confirming.adding.length}</strong> new ·{" "}
          <strong>{confirming.updating.length}</strong> already registered, names will be updated.
        </p>

        {confirming.ignored_keys.length > 0 && (
          <Banner variant="warning" title="Some columns were not recognised">
            {confirming.ignored_keys
              .map((k) => `${k.key} (${k.entries} ${k.entries === 1 ? "entry" : "entries"})`)
              .join(", ")}
            . They will be ignored. If one of them says whether a page is in scope, those pages
            will be audited.
          </Banner>
        )}

        {/* The half that matters. A page already registered that this list does not mention is
            either a page being removed or — far more often — a path somebody just corrected by
            editing the text. The platform cannot tell those apart, and nobody has to: the
            difference is obvious to the person looking at it, before anything is written. */}
        {missing.length > 0 && (
          <>
            <h3 className="t-h3" style={{ marginTop: "var(--space-5)" }}>
              {missing.length} page{missing.length === 1 ? " you" : "s you"} already have{" "}
              {missing.length === 1 ? "is" : "are"} not in this list
            </h3>
            <Table
              headers={["Path", "Name", "Recorded problems"]}
              rows={missing.map((row) => [
                <span className="t-mono">{row.path}</span>,
                row.label || "—",
                row.open_findings || "none",
              ])}
            />
            <div className="field" style={{ marginTop: "var(--space-4)" }}>
              <label className="u-row" style={{ alignItems: "flex-start", gap: 8 }}>
                <input
                  type="radio"
                  name="missing"
                  checked={!replace}
                  onChange={() => setReplace(false)}
                />
                <span className="t-sm u-body">
                  <strong>Keep them in scope</strong> — I am adding pages, not replacing the list.
                </span>
              </label>
              <label className="u-row" style={{ alignItems: "flex-start", gap: 8, marginTop: 8 }}>
                <input
                  type="radio"
                  name="missing"
                  checked={replace}
                  onChange={() => setReplace(true)}
                />
                <span className="t-sm u-body">
                  <strong>Take them out of scope</strong> — they are gone, or I renamed them.
                </span>
              </label>
            </div>
            {replace && (
              <Banner variant="info" title="If you renamed a page">
                Its recorded problems stay with the old address. The new one starts with no
                history and will need reviewing again.
              </Banner>
            )}
          </>
        )}

        {register.isError && (
          <Banner variant="danger" title="Nothing was registered">
            {(register.error as Error).message}
          </Banner>
        )}
      </Modal>
    );
  }

  return (
    <Modal
      title="Add pages"
      onClose={onClose}
      footer={
        <>
          <Button
            variant="primary"
            disabled={!text.trim() || preview.isPending}
            onClick={() =>
              preview.mutateAsync(text).then((r) => setConfirming(r.preview)).catch(() => undefined)
            }
          >
            Continue
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <Banner variant="info" title="The platform cannot discover your pages">
        It has no access to your application — that is deliberate. Tell it which addresses to
        visit and it will visit exactly those, and report on anything it was asked for and could
        not open.
      </Banner>

      <label className="field" style={{ marginTop: "var(--space-4)" }}>
        <span className="field__label" id="pages-box">
          Your pages
        </span>
        <Textarea
          aria-labelledby="pages-box"
          rows={10}
          placeholder={'[{ "path": "/", "title": "Home", "enabled": true }, …]'}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="field__help">
          A list of paths — <span className="t-mono">["/", "/catalogue"]</span> — or a list of
          entries carrying <span className="t-mono">path</span>, with optional{" "}
          <span className="t-mono">title</span>, <span className="t-mono">enabled</span> and{" "}
          <span className="t-mono">example</span>. Anything we cannot read is named back to you,
          never silently dropped.
        </span>
      </label>

      {error && (
        <Banner variant="danger" title="This could not be read">
          {error.message}
        </Banner>
      )}
    </Modal>
  );
}

// ── the run strip ───────────────────────────────────────────────────────────

function RunStrip({
  projectId,
  routes,
  scopeChange,
  hasMachine,
}: {
  projectId: string;
  routes: A11yRoute[];
  scopeChange: { added?: string[]; removed?: string[]; before?: number; now?: number };
  hasMachine: boolean;
}) {
  const [address, setAddress] = useState("");
  const start = useStartA11yAudit(projectId);
  const inScope = routes.filter((r) => r.enabled);
  const passes = Math.max(1, Math.ceil(inScope.length / PAGES_PER_PASS));
  const moved = (scopeChange.added?.length ?? 0) + (scopeChange.removed?.length ?? 0) > 0;

  return (
    <Panel
      title="Run an audit"
      actions={
        hasMachine ? (
          <Badge variant="done">Machine connected</Badge>
        ) : (
          <Badge variant="failed">No machine connected</Badge>
        )
      }
    >
      <p className="t-sm u-muted">
        The scan runs on your connected machine, not on our servers — your application is at an
        address only your machine can reach. Nothing about it is ever sent to us except what the
        scan writes down.
      </p>

      {/* Scope moved since the last audit. The report's own Movement section compares findings
          between audits and reads as progress; if the page list shrank, the numbers improve on
          their own. Said here, and in the document, so neither reader has to guess. */}
      {moved && (
        <Banner variant="warning" title="The page list has changed since the last audit">
          {[
            scopeChange.added?.length ? `${scopeChange.added.length} added` : "",
            scopeChange.removed?.length
              ? `${scopeChange.removed.length} taken out of scope`
              : "",
          ]
            .filter(Boolean)
            .join(" · ")}
          . This audit will cover {scopeChange.now} page(s) where the last one covered{" "}
          {scopeChange.before}, so the two are not directly comparable.
        </Banner>
      )}

      {!hasMachine && (
        <Banner variant="warning" title="You have no machine connected">
          Nothing can reach your application without one. Connect your machine, then run the
          audit. (A colleague's machine may be connected — this only knows about yours.)
        </Banner>
      )}

      <div className="grid grid--2" style={{ marginTop: "var(--space-4)" }}>
        <label className="field">
          <span className="field__label" id="app-address">
            Address of the running application
          </span>
          <input
            className="input"
            type="text"
            aria-labelledby="app-address"
            placeholder="taken from your repository's Preview URL"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <span className="field__help">
            Leave it blank to use the address the platform already holds for this project. Typing
            one here scans a different environment for this run only — it is not saved back.
          </span>
        </label>
        <div className="field">
          <span className="field__label">What will be visited</span>
          <div className="kv" style={{ marginTop: 6 }}>
            <span className="t-sm">Pages in scope</span>
            <span className="t-sm">
              <strong>{inScope.length}</strong> of {routes.length}
            </span>
            <span className="t-sm">Passes</span>
            <span className="t-sm">
              {passes} <span className="u-muted">({PAGES_PER_PASS} pages each)</span>
            </span>
            <span className="t-sm">Standard</span>
            <span className="t-sm">WCAG 2.2 Level AA</span>
          </div>
        </div>
      </div>

      {start.isError && (
        <Banner variant="danger" title="The audit could not be started">
          {(start.error as Error).message}
        </Banner>
      )}

      <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
        <Button
          variant="primary"
          disabled={inScope.length === 0 || start.isPending}
          onClick={() =>
            start.mutateAsync({ base_url: address.trim() || undefined }).catch(() => undefined)
          }
        >
          Run audit
        </Button>
      </div>
    </Panel>
  );
}

// ── past audits ─────────────────────────────────────────────────────────────

function PastAudits({ audits }: { audits: A11yAuditRow[] }) {
  return (
    <Panel title="Past audits" flush>
      {audits.length === 0 ? (
        <div className="panel__body">
          <p className="t-sm u-muted">No audit has run yet.</p>
        </div>
      ) : (
        audits.map((audit) => (
          <div className="artifact-row" key={audit.id}>
            <div className="artifact-row__main">
              <div className="artifact-row__title">{when(audit.created_at)}</div>
              <div className="artifact-row__meta">
                {audit.summary?.asked ?? audit.routes.length} asked for ·{" "}
                {audit.summary?.opened ?? 0} reported
              </div>
              <div className="u-row" style={{ marginTop: 6 }}>
                <Badge variant={auditBadge(audit.status)}>
                  {STATUS_LABEL[audit.status] ?? audit.status}
                </Badge>
                {(audit.summary?.never_reported?.length ?? 0) > 0 && (
                  <Badge variant="outline" dot={false}>
                    {audit.summary.never_reported!.length} never opened
                  </Badge>
                )}
              </div>
              {/* A failed audit says why in its own words. The generic "the application did not
                  respond" is only used when the machine had nothing better to offer — most
                  often it did: no browser installed in the project folder, and it says so. */}
              {audit.summary?.reason && (
                <p className="t-sm u-muted" style={{ marginTop: 6 }}>
                  {audit.summary.reason}
                </p>
              )}
            </div>
          </div>
        ))
      )}
    </Panel>
  );
}

// ── the screen ──────────────────────────────────────────────────────────────

type Filter = "all" | "scope" | "excluded";

export function A11yAudit() {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const routes = useA11yRoutes(projectId);
  const audits = useA11yAudits(projectId);
  const runners = useRunners();
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  // `!projectId` counts as loading, and that is not defensive tidying. The query is disabled
  // until the project resolves, so `isLoading` is false and `routes.data` is undefined — which
  // rendered the empty state and told a brownfield user "no pages are registered yet" before the
  // platform had asked. On this screen of all screens, that sentence has to be an answer rather
  // than a stage of loading.
  if (!projectId || routes.isLoading) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="audit" />
        <Panel title="Loading the pages">
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </main>
    );
  }

  const rows = routes.data?.routes ?? [];
  const inScope = rows.filter((r) => r.enabled);
  const excluded = rows.filter((r) => !r.enabled);
  const shown = filter === "scope" ? inScope : filter === "excluded" ? excluded : rows;
  // Only this user's machines are visible to the app, so the wording says "you", never "nobody".
  const hasMachine = Boolean(runners.data?.some((r) => r.online || r.last_seen));

  return (
    <main className="canvas-pad">
      <A11yTabs active="audit" />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Pages &amp; audit</h1>
          <p className="page-head__sub">
            Which pages of this application to check, and the audits that have checked them.
          </p>
        </div>
      </div>

      {adding && projectId && (
        <AddPages projectId={projectId} onClose={() => setAdding(false)} />
      )}

      {rows.length === 0 ? (
        <Panel>
          <EmptyState
            title="No pages are registered yet"
            text="The platform has no access to your application, so it cannot discover its pages — somebody has to say what they are. Nothing is audited until you do."
            action={
              <Button variant="primary" onClick={() => setAdding(true)}>
                Add pages
              </Button>
            }
          />
        </Panel>
      ) : (
        <>
          <div style={{ marginBottom: "var(--space-5)" }}>
            <RunStrip
              projectId={projectId as string}
              routes={rows}
              scopeChange={routes.data?.scope_change ?? {}}
              hasMachine={hasMachine}
            />
          </div>

          <div className="grid grid--detail">
            <Panel title="Pages" actions={<span className="t-sm u-muted">{routes.data?.summary}</span>}>
              <div className="u-row" style={{ marginBottom: "var(--space-4)" }}>
                {(
                  [
                    ["all", `All (${rows.length})`],
                    ["scope", `In scope (${inScope.length})`],
                    ["excluded", `Excluded (${excluded.length})`],
                  ] as [Filter, string][]
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className="chip chip--filter"
                    aria-pressed={filter === id}
                    onClick={() => setFilter(id)}
                  >
                    {label}
                  </button>
                ))}
                <span className="u-spacer" />
                <Button variant="secondary" onClick={() => setAdding(true)}>
                  Add pages
                </Button>
              </div>

              <Table
                headers={["Path", "Name", "In scope", "Last visited"]}
                rows={shown.map((row) => [
                  <span className="t-mono">{row.path}</span>,
                  <>
                    {row.label || "—"}
                    {/* A pattern route is visited by example. Saying which one keeps the report
                        from claiming a page that does not exist was checked. */}
                    {row.example_path && (
                      <div className="t-sm u-muted">checked using {row.example_path}</div>
                    )}
                  </>,
                  row.enabled ? (
                    <Switch label={`${row.path} in scope`} checked readOnly />
                  ) : (
                    <Badge variant="neutral" dot={false}>
                      Excluded
                    </Badge>
                  ),
                  row.last_visited ? (
                    <span className="t-sm u-muted">{when(row.last_visited)}</span>
                  ) : row.enabled ? (
                    <Badge variant="outline" dot={false}>
                      Never visited
                    </Badge>
                  ) : (
                    <span className="t-sm u-muted">—</span>
                  ),
                ])}
              />

              {shown.length === 0 && (
                <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
                  No pages match this filter.
                </p>
              )}
            </Panel>

            <div>
              <PastAudits audits={audits.data?.audits ?? []} />
              <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
                Each audit writes an <strong>Accessibility baseline</strong> document you can open
                from Artifacts.
              </p>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
