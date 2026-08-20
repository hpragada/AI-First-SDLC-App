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
import type { BadgeVariant } from "../../components/ui";
import { useRunners } from "../identity/hooks";
import type {
  A11yAudit as A11yAuditRow,
  A11yJourneyQueued,
  A11yJourneyRow,
  A11yRegistrationPreview,
  A11yRoute,
} from "../../types";
import { A11yTabs } from "./A11yTabs";
import {
  useA11yAudits,
  useA11yJourneys,
  useA11yRoutes,
  useDeleteA11yRoute,
  usePreviewA11yRoutes,
  useRegisterA11yRoutes,
  useStartA11yAudit,
  useStartA11yJourneys,
  useUpdateA11yRoute,
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

// ── one page at a time (task 8b) ────────────────────────────────────────────
//
// Registering works by path, because a pasted list carries no identities — which is why
// correcting a path THERE adds a page and leaves the old one in scope, and why the paste has a
// confirm step. Here the row is named, so an edit is an edit and the ghost page cannot happen.
//
// What this still cannot do is move a page's history: a finding is identified by the page it was
// found on, so renaming leaves the problems at the old address. That is correct and it is not
// obvious, so it is said before it happens rather than discovered afterwards.

function PageEditor({
  projectId,
  page,
  onClose,
}: {
  projectId: string;
  page?: A11yRoute;          // absent = adding a new page
  onClose: () => void;
}) {
  const [path, setPath] = useState(page?.path ?? "");
  const [label, setLabel] = useState(page?.label ?? "");
  const [example, setExample] = useState(page?.example_path ?? "");
  const [enabled, setEnabled] = useState(page?.enabled ?? true);
  const update = useUpdateA11yRoute(projectId);
  const register = useRegisterA11yRoutes(projectId);
  const busy = update.isPending || register.isPending;
  const error = (update.error ?? register.error) as Error | undefined;

  const history = (page?.open_findings ?? 0) + (page?.visits ?? 0);
  const renaming = Boolean(page && path.trim() && path.trim() !== page.path && history > 0);

  const save = () => {
    const fields = { path: path.trim(), label, example_path: example.trim(), enabled };
    const done = page
      ? update.mutateAsync({ routeId: page.id, fields })
      : register.mutateAsync({
          routesText: JSON.stringify([{
            path: fields.path,
            title: label,
            enabled,
            ...(fields.example_path ? { example: fields.example_path } : {}),
          }]),
          replace: false,
        });
    done.then(onClose).catch(() => undefined);
  };

  return (
    <Modal
      title={page ? "Edit page" : "Add a page"}
      onClose={onClose}
      footer={
        <>
          <Button variant="primary" disabled={!path.trim() || busy} onClick={save}>
            {page ? "Save" : "Add page"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </>
      }
    >
      <label className="field">
        <span className="field__label" id="page-path">Path</span>
        <input
          className="input"
          aria-labelledby="page-path"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="/checkout"
        />
        <span className="field__help">
          The path only. Where the application is running belongs to the machine auditing it and
          changes between runs; the page does not.
        </span>
      </label>

      {/* The warning that makes a rename a decision rather than a surprise. */}
      {renaming && (
        <Banner variant="warning" title="This page has a history">
          {page!.open_findings > 0 && (
            <>
              {page!.open_findings} recorded problem
              {page!.open_findings === 1 ? "" : "s"} stay with <strong>{page!.path}</strong>.{" "}
            </>
          )}
          A problem is identified by the page it was found on, so <strong>{path.trim()}</strong>{" "}
          starts with no history and will need reviewing again.
        </Banner>
      )}

      <label className="field" style={{ marginTop: "var(--space-4)" }}>
        <span className="field__label" id="page-name">Name</span>
        <input
          className="input"
          aria-labelledby="page-name"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Browse the catalogue"
        />
        <span className="field__help">Only used to make the report readable.</span>
      </label>

      <label className="field" style={{ marginTop: "var(--space-4)" }}>
        <span className="field__label" id="page-example">Example page</span>
        <input
          className="input"
          aria-labelledby="page-example"
          value={example}
          onChange={(e) => setExample(e.target.value)}
          placeholder="/events/482"
        />
        <span className="field__help">
          Only for a pattern like <span className="t-mono">/events/:id</span>, which no browser
          can open. The audit visits the example and still records the finding against the
          pattern.
        </span>
      </label>

      <label className="u-row" style={{ alignItems: "center", gap: 8, marginTop: "var(--space-4)" }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span className="t-sm u-body">Audit this page</span>
      </label>

      {error && (
        <Banner variant="danger" title="Nothing was changed">
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

// ── keyboard journeys (G6c) ─────────────────────────────────────────────────
//
// Eight WCAG criteria cannot be answered by reading a page standing still — whether tabbing ever
// traps you, whether you can see where you are, whether anyone is told when something changed.
// They are only answerable by OPERATING the application, and the industry scanner covers one of
// the eight. That is the whole reason this panel exists.
//
// It sits on this tab and not a new one because it is the same subject, the same role and the
// same address as the audit above it. And it renders whether or not any pages are registered: a
// journey follows a test case, not the page list, so a project with journeys and no registered
// pages must still be able to walk them.

function journeyResult(row: A11yJourneyRow): { label: string; variant: BadgeVariant } {
  if (row.status === "walking") return { label: "Walking now", variant: "waiting" };
  if (!row.last_walked) return { label: "Never walked", variant: "outline" };
  if (row.status === "failed") return { label: "Nothing was walked", variant: "failed" };
  const blocked = row.summary.blocked?.length ?? 0;
  const findings = row.summary.findings ?? 0;
  if (!blocked && !findings) return { label: "Walked · nothing found", variant: "done" };
  return {
    label: [blocked ? `${blocked} blocked` : "", findings ? `${findings} finding(s)` : ""]
      .filter(Boolean)
      .join(" · "),
    variant: blocked ? "failed" : "orange",
  };
}

function KeyboardJourneys({ projectId, hasMachine }: { projectId: string; hasMachine: boolean }) {
  const journeys = useA11yJourneys(projectId);
  const start = useStartA11yJourneys(projectId);
  const [address, setAddress] = useState<string | undefined>();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [queued, setQueued] = useState<A11yJourneyQueued | undefined>();

  const data = journeys.data;
  // `undefined` until the user types, so the suggested address arrives without an effect and
  // without overwriting what they typed on the next poll.
  const value = address ?? data?.base_url ?? "";
  const rows = data?.journeys ?? [];
  const walkable = rows.filter((r) => r.status !== "walking");
  const chosen = rows.filter((r) => picked.has(r.id) && r.status !== "walking");

  if (journeys.isLoading) {
    return (
      <Panel title="Keyboard journeys">
        <Skeleton kind="title" />
        <Skeleton kind="block" />
      </Panel>
    );
  }

  const toggle = (id: string) =>
    setPicked((was) => {
      const next = new Set(was);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <Panel
      title="Keyboard journeys"
      actions={
        <>
          <Badge variant="outline" dot={false}>Reported, never blocking</Badge>
          {hasMachine ? (
            <Badge variant="done">Machine connected</Badge>
          ) : (
            <Badge variant="failed">No machine connected</Badge>
          )}
        </>
      }
    >
      <p className="t-sm u-muted">
        Eight things cannot be judged from a page standing still — whether focus can get out of a
        menu, whether you can see where you are, whether a screen reader is told when something
        changes. They can only be answered by <em>operating</em> the application with a keyboard.
        The industry scanner covers one of the eight.
      </p>

      {rows.length === 0 ? (
        <EmptyState
          title="No journeys to walk yet"
          text="A keyboard journey follows a test case describing a complete path through the application. This project has none yet — run the Testing phase and they appear here as soon as it writes them."
        />
      ) : (
        <>
          {/* Said BEFORE the button, because it is the one thing the platform cannot do for
              them: nothing here starts the application, and a walk against an address nothing
              answers on stops immediately and records no steps. */}
          {!hasMachine && (
            <Banner variant="warning" title="You have no machine connected">
              A journey runs a real browser on your machine, against an application only your
              machine can reach. Connect it first. (A colleague's may be connected — this only
              knows about yours.)
            </Banner>
          )}

          <Banner variant="info" title="Start your application first">
            A journey walks the live application, step by step. Make sure it is running at the
            address below before you start — if nothing answers there the run stops immediately
            and records no steps, rather than reporting on steps it never walked.
          </Banner>

          <label className="field" style={{ marginTop: "var(--space-5)", maxWidth: 520 }}>
            <span className="field__label" id="journey-address">
              Address to walk
            </span>
            <input
              className="input"
              type="text"
              aria-labelledby="journey-address"
              value={value}
              placeholder="http://127.0.0.1:5173"
              onChange={(e) => setAddress(e.target.value)}
            />
            <span className="field__help">
              {data?.base_url_source
                ? `Pre-filled from ${data.base_url_source}.`
                : data?.base_url_reason || "Where the running application answers."}
            </span>
          </label>

          <Table
            headers={["", "Test case", "Steps", "Last walked", "Result"]}
            rows={rows.map((row) => {
              const result = journeyResult(row);
              return [
                <input
                  type="checkbox"
                  aria-label={`Walk ${row.test_ref || row.title}`}
                  checked={picked.has(row.id)}
                  disabled={row.status === "walking"}
                  onChange={() => toggle(row.id)}
                />,
                <>
                  {row.test_ref && <span className="t-mono">{row.test_ref}</span>}
                  {row.test_ref ? " — " : ""}
                  {row.title}
                </>,
                <span className="t-sm">{row.steps}</span>,
                <span className="t-sm u-muted">{when(row.last_walked) || "—"}</span>,
                <Badge variant={result.variant} dot={false}>
                  {result.label}
                </Badge>,
              ];
            })}
          />

          {/* What was found and CANNOT be walked. Never hidden: a list that quietly omitted these
              is how an application with no keyboard coverage comes to look like one with no
              keyboard problems. */}
          {(data?.unwalkable?.length ?? 0) > 0 && (
            <div style={{ marginTop: "var(--space-4)" }}>
              <p className="t-sm u-muted">
                Found and not walkable — each says why, so it can be fixed rather than guessed at:
              </p>
              <ul className="t-sm u-muted">
                {data?.unwalkable.map((u) => (
                  <li key={u.artifact_id}>
                    <strong>{u.test_ref || u.title}</strong> — {u.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(data?.over_cap?.length ?? 0) > 0 && (
            <Banner variant="warning" title="More journeys than one run can take">
              {data?.over_cap.join(", ")} are past the limit of {data?.max_journeys} and were left
              for the next run. They are named here rather than dropped.
            </Banner>
          )}

          {!data?.can_start && (
            <Banner variant="info" title="You can see these; the QA Lead starts them">
              Starting a journey spends a real browser on a real application, so it is the
              accessibility reviewer's call. Everything here is readable by anyone on the project.
            </Banner>
          )}

          {start.isError && (
            <Banner variant="danger" title="Nothing was started">
              {(start.error as Error).message}
            </Banner>
          )}

          {/* What actually happened, said in full: what started, and what did not and why. */}
          {queued && (
            <div style={{ marginTop: "var(--space-4)" }}>
              {queued.started.length > 0 && (
                <Banner variant="info" title={`Walking ${queued.started.length} journey(s)`}>
                  {queued.started.map((j) => j.name).join(", ")}. This takes a few minutes in a
                  real browser on your machine; the table above updates as each finishes.
                </Banner>
              )}
              {queued.refused.length > 0 && (
                <Banner variant="warning" title={`${queued.refused.length} was not started`}>
                  <ul>
                    {queued.refused.map((r) => (
                      <li key={r.name}>
                        <strong>{r.name}</strong> — {r.reason}
                      </li>
                    ))}
                  </ul>
                </Banner>
              )}
              {queued.started.length === 0 && queued.refused.length === 0 && queued.reason && (
                <Banner variant="warning" title="Nothing was started">
                  {queued.reason}
                </Banner>
              )}
            </div>
          )}

          <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
            <Button
              variant="primary"
              disabled={!data?.can_start || chosen.length === 0 || start.isPending || !value.trim()}
              onClick={() =>
                start
                  .mutateAsync({ base_url: value.trim(), test_refs: chosen.map((r) => r.id) })
                  .then((out) => {
                    setQueued(out);
                    setPicked(new Set());
                  })
                  .catch(() => undefined)
              }
            >
              {chosen.length === 1
                ? "Walk 1 selected journey"
                : `Walk ${chosen.length} selected journeys`}
            </Button>
            <Button
              variant="ghost"
              disabled={walkable.length === 0}
              onClick={() => setPicked(new Set(walkable.map((r) => r.id)))}
            >
              Select all walkable ({walkable.length})
            </Button>
          </div>

          <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
            Up to {data?.max_journeys} at a time. What the keyboard journey finds is reported,
            ticketed and reviewed like everything else — it never blocks a gate.
          </p>
        </>
      )}
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
  const [importing, setImporting] = useState(false);
  // `undefined` = closed, `null` = adding a new page, a route = editing that one.
  const [editing, setEditing] = useState<A11yRoute | null | undefined>(undefined);
  const [removed, setRemoved] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const update = useUpdateA11yRoute(projectId);
  const remove = useDeleteA11yRoute(projectId);

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

      {importing && projectId && (
        <AddPages projectId={projectId} onClose={() => setImporting(false)} />
      )}
      {editing !== undefined && projectId && (
        <PageEditor
          projectId={projectId}
          page={editing ?? undefined}
          onClose={() => setEditing(undefined)}
        />
      )}

      {/* Removing a page usually does not remove it. Said afterwards, because the answer depends
          on what the page has accumulated and the person asking cannot be expected to know. */}
      {removed && (
        <Banner variant="info" title="Kept, and taken out of scope">
          {removed}
        </Banner>
      )}

      {rows.length === 0 ? (
        <Panel>
          <EmptyState
            title="No pages are registered yet"
            text="The platform has no access to your application, so it cannot discover its pages — somebody has to say what they are. Nothing is audited until you do."
            action={
              <div className="gate-panel__actions" style={{ justifyContent: "center" }}>
                <Button variant="primary" onClick={() => setImporting(true)}>
                  Import a list
                </Button>
                <Button variant="secondary" onClick={() => setEditing(null)}>
                  Add a page
                </Button>
              </div>
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
                {/* Adding one page is the everyday action, so it leads. Importing is how a
                    project starts, not how it is kept. */}
                <Button variant="secondary" onClick={() => setEditing(null)}>
                  Add a page
                </Button>
                <Button variant="ghost" onClick={() => setImporting(true)}>
                  Import a list
                </Button>
              </div>

              <Table
                headers={["Path", "Name", "In scope", "Last visited", ""]}
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
                  // The toggle AND the word. A toggle that is off reads as "not set yet"; the
                  // design said "Excluded", and that is a decision somebody took about this
                  // page, not a default. Now it is both editable and legible.
                  <div className="u-row" style={{ alignItems: "center", gap: 8 }}>
                    <Switch
                      label={`Audit ${row.path}`}
                      checked={row.enabled}
                      disabled={update.isPending}
                      onChange={(e) =>
                        update
                          .mutateAsync({ routeId: row.id, fields: { enabled: e.target.checked } })
                          .catch(() => undefined)
                      }
                    />
                    {!row.enabled && (
                      <Badge variant="neutral" dot={false}>
                        Excluded
                      </Badge>
                    )}
                  </div>,
                  row.last_visited ? (
                    <span className="t-sm u-muted">{when(row.last_visited)}</span>
                  ) : row.enabled ? (
                    <Badge variant="outline" dot={false}>
                      Never visited
                    </Badge>
                  ) : (
                    <span className="t-sm u-muted">—</span>
                  ),
                  <div className="u-row">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(row)}>
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={remove.isPending}
                      onClick={() =>
                        remove
                          .mutateAsync(row.id)
                          .then((r: { removed: boolean; reason: string }) =>
                            setRemoved(r.removed ? "" : r.reason))
                          .catch(() => undefined)
                      }
                    >
                      Remove
                    </Button>
                  </div>,
                ])}
              />

              {(update.isError || remove.isError) && (
                <Banner variant="danger" title="That change was not saved">
                  {((update.error ?? remove.error) as Error).message}
                </Banner>
              )}

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

      {/* OUTSIDE the "no pages registered" branch above, and that is deliberate: a keyboard
          journey follows a test case, not the page list. A project with journeys and no
          registered pages must still be able to walk them, and a panel that disappeared with
          the page list would look like a feature that does not exist. */}
      <div style={{ marginTop: "var(--space-5)" }}>
        <KeyboardJourneys projectId={projectId as string} hasMachine={hasMachine} />
      </div>
    </main>
  );
}
