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
import { LoadFailed } from "./LoadFailed";
import {
  AUDIT_IN_FLIGHT,
  useA11yAudits,
  useA11yJourneys,
  useA11yRoutes,
  useDeleteA11yRoute,
  usePreviewA11yRoutes,
  useRegisterA11yRoutes,
  useRejudgeA11yAudit,
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
      // Named for the button that opens it. It used to be titled "Add pages", which is nearly
      // the name of the OTHER button on that screen — so clicking `Import a list` landed you on
      // something that read like the single-page form, and the two were told apart by guessing.
      title="Import a list"
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
        {/* BOTH formats are shown because both are accepted, and which one you need depends on
            what you have. The pattern appears only in the JSON half, and that placement is the
            point: line mode returns bare paths, so there is nowhere to say what `/events/:id`
            should open. Demonstrating a pattern in the line half — which is what this
            placeholder used to do — teaches the one combination that cannot work, and every
            audit afterwards reports that page unreachable. */}
        <Textarea
          aria-labelledby="pages-box"
          rows={12}
          placeholder={
            "/\n/catalogue\n/about/history\n" +
            "\n— or a JSON list —\n\n" +
            '[{"path": "/catalogue", "title": "Browse the catalogue"},\n' +
            ' {"path": "/events/:id", "example": "/events/482"}]'
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <span className="field__help">
          <strong>Either format works.</strong> One path per line is enough. Paste a JSON list
          when you also want to give each page a name, say whether it is in scope, or point a
          pattern at a real page: entries carrying <span className="t-mono">path</span>, with
          optional <span className="t-mono">title</span>, <span className="t-mono">enabled</span>{" "}
          (or <span className="t-mono">in_scope</span>) and <span className="t-mono">example</span>.
          A path no browser can open — <span className="t-mono">/events/:id</span> — needs the
          JSON form, because only it can carry the example page to visit. Anything we cannot read
          is named back to you, never silently dropped.
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
        {/* Read on its own — which is how a person scanning down the form reads it — the old
            wording ("Only for a pattern like /events/:id") described the DIALOG rather than the
            field, and people came away believing this form only accepted patterns. It says what
            to do with it when you have a normal page first, because that is nearly everyone.

            Several shapes, because the platform does not parse patterns at all: `normalise_path`
            wants a leading `/` and nothing else, so `:id`, `[isbn]` and `{id}` are stored as
            written. The rule is not "must look like :id" — it is "if the path as written cannot
            be opened, give one that can", and naming one framework's syntax made it look like
            the only one allowed. */}
        <span className="field__help">
          <strong>Leave this empty for a normal page.</strong> It is only needed when the path
          above cannot be opened in a browser as written — whatever your framework writes them
          as: <span className="t-mono">/events/:id</span>,{" "}
          <span className="t-mono">/books/[isbn]</span>,{" "}
          <span className="t-mono">/users/{"{id}"}/loans</span>. Give one real page that matches —{" "}
          <span className="t-mono">/events/482</span> — and the audit visits that, while still
          recording what it finds against the pattern above.
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
  canManage,
}: {
  projectId: string;
  routes: A11yRoute[];
  scopeChange: { added?: string[]; removed?: string[]; before?: number; now?: number };
  hasMachine: boolean;
  canManage: boolean;
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
      {/* Said here rather than discovered from a failed audit several minutes later. The two
          things on this screen genuinely need different setups, and the difference used to be
          invisible: an audit resolves its browser and scanner out of the audited project, a
          keyboard journey below fetches its own. */}
      <p className="t-sm u-muted" style={{ marginTop: "var(--space-2)" }}>
        Your machine needs a browser and the <span className="t-mono">axe</span> scanner. If the
        application's own repository is checked out there and ships them, the audit uses that
        copy — and the report names the version your application actually uses. Otherwise it
        falls back to the companion's own, and every scan says{" "}
        <span className="t-mono">(companion)</span> beside the version so the two are never
        confused.
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

      {/* Read-only, said before the button rather than discovered by a 403 on click — the same
          shape the keyboard-journeys panel below has always had. */}
      {!canManage && (
        <Banner variant="info" title="You can see this; the QA Lead or Tech Lead runs it">
          An audit spends a real browser on a real application for several minutes, so starting
          one — and deciding which pages it covers — belongs to them. Everything here is
          readable by anyone on the project.
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
          disabled={!canManage || inScope.length === 0 || start.isPending}
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
  // "queued" is derived by the platform, not stored: dispatched, and no machine has taken it.
  // Without this the row said "Walking now" for ever when no companion was running — while the
  // audit strip directly above told the same two states apart. Same words as the audit, on
  // purpose: one screen, one vocabulary.
  if (row.status === "queued") return { label: "Waiting for a machine", variant: "outline" };
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
  // In flight means dispatched OR being walked. A queued journey is already spoken for, so
  // ticking it again would only earn an "already being walked" refusal.
  const inFlight = (r: A11yJourneyRow) => r.status === "walking" || r.status === "queued";
  const walkable = rows.filter((r) => !inFlight(r));
  const chosen = rows.filter((r) => picked.has(r.id) && !inFlight(r));

  if (journeys.isLoading) {
    return (
      <Panel title="Keyboard journeys">
        <Skeleton kind="title" />
        <Skeleton kind="block" />
      </Panel>
    );
  }

  // Same rule as the page list above: a failure here used to read "No journeys to walk yet",
  // which is a statement about the project rather than about the request that failed.
  if (journeys.isError) {
    return (
      <LoadFailed
        what="The keyboard journeys"
        error={journeys.error}
        onRetry={() => void journeys.refetch()}
      />
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
                  disabled={inFlight(row)}
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

// ── the audit that is running now ───────────────────────────────────────────

/** The panel S-38 designs for a running audit: what stage, and three counts (S-38 line 598).
 *
 * **Why it exists.** Until it did, the only thing on screen while an audit ran was a status
 * word in a list — so an audit that had visited 6 of 10 pages and one that had visited none
 * looked identical, and an audit whose judge had stopped looked exactly like one still working.
 * That is this capability's own standard turned on itself: a screen must not state progress it
 * cannot evidence, and "Checking what was found" for forty minutes states plenty.
 *
 * Three tiles, and the middle one changes with the stage, because what you need to know changes
 * with it: while pages are being visited it is which pass; once they are in it is how far the
 * judging has got. The design's live console is a separate, larger piece of work — screens are
 * posted one per call with no progress channel to carry per-page lines — and is recorded as a
 * pending enhancement rather than half-built here.
 */
function RunningAudit({ audit }: { audit: A11yAuditRow }) {
  const progress = audit.progress ?? { visited: 0, unreachable: 0 };
  const asked = audit.routes.length;
  const passes = Math.max(1, Math.ceil(asked / PAGES_PER_PASS));
  const judging = audit.status === "judging";
  // Which pass the capture is on, from what has come back. Derived rather than reported: the
  // companion writes one screen at a time and never says which pass it is in, and a number
  // computed from the screens actually posted cannot claim a pass that has not started.
  const pass = Math.min(passes, Math.floor(progress.visited / PAGES_PER_PASS) + 1);
  const dispatched = progress.dispatched ?? 0;

  return (
    <Panel
      title="Audit running"
      actions={
        <Badge variant={auditBadge(audit.status)}>
          {STATUS_LABEL[audit.status] ?? audit.status}
        </Badge>
      }
    >
      <div className="grid grid--3" style={{ marginBottom: "var(--space-4)" }}>
        {judging ? (
          <div className="tile">
            <div className="tile__num">
              {progress.judged ?? 0}{" "}
              <span className="t-sm u-muted">of {dispatched}</span>
            </div>
            <div className="tile__label">Elements judged</div>
            <div className="tile__sub">
              {/* Never "0 problems". An element nobody has looked at yet is not an element that
                  passed, and this panel is on screen precisely while that is the case. */}
              {dispatched === 0 ? "none needed judging" : "the AI half, in progress"}
            </div>
          </div>
        ) : (
          <div className="tile">
            <div className="tile__num">
              {pass} <span className="t-sm u-muted">of {passes}</span>
            </div>
            <div className="tile__label">Pass</div>
            <div className="tile__sub">{PAGES_PER_PASS} pages per pass</div>
          </div>
        )}
        <div className="tile">
          <div className="tile__num">{progress.visited}</div>
          <div className="tile__label">Pages visited</div>
          <div className="tile__sub">of {asked} asked for</div>
        </div>
        <div className="tile">
          <div className="tile__num">{progress.unreachable}</div>
          <div className="tile__label">Would not open</div>
          <div className="tile__sub">recorded, never guessed</div>
        </div>
      </div>
      <p className="t-sm u-muted">
        You can leave this page. The audit carries on and the result appears under Past audits.
      </p>
    </Panel>
  );
}

// ── past audits ─────────────────────────────────────────────────────────────

function PastAudits({
  audits,
  projectId,
  canManage,
}: {
  audits: A11yAuditRow[];
  projectId: string | undefined;
  canManage: boolean;
}) {
  const rejudge = useRejudgeA11yAudit(projectId);
  // Which audit was asked about, so the message lands on that row and not on all of them.
  const [asked, setAsked] = useState<{ id: string; text: string } | null>(null);

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

              {/* Elements nothing ever looked at — offered back to the machine rather than left
                  on a person. Only on a CLOSED audit (the API only counts those), and only when
                  there are some: a button that is always there, usually saying nothing to do, is
                  a button nobody reads. The count is said out loud, because "check the rest" with
                  no number is a promise of unknown size. */}
              {(audit.unanswered ?? 0) > 0 && (
                <div style={{ marginTop: "var(--space-3)" }}>
                  <p className="t-sm u-muted">
                    {audit.unanswered === 1
                      ? "1 element was never looked at"
                      : `${audit.unanswered} elements were never looked at`}
                    {" — not checked and undecided, but never checked at all. They are waiting on"}
                    {" a person in the review queue."}
                  </p>
                  <div className="u-row" style={{ marginTop: 6 }}>
                    <Button
                      variant="secondary"
                      disabled={!canManage || rejudge.isPending}
                      onClick={() => {
                        setAsked(null);
                        rejudge
                          .mutateAsync(audit.id)
                          .then((out) =>
                            setAsked({
                              id: audit.id,
                              text: out.started
                                ? `Asking again about ${out.asked} element(s). No page is visited — everything needed was stored when they were captured.`
                                : out.reason || "Nothing was asked again.",
                            }),
                          )
                          .catch((err: Error) =>
                            setAsked({ id: audit.id, text: err.message }),
                          );
                      }}
                    >
                      {rejudge.isPending ? "Asking…" : "Check the rest"}
                    </Button>
                    {!canManage && (
                      <span className="t-sm u-muted">
                        The QA Lead or Tech Lead on this project runs this.
                      </span>
                    )}
                  </div>
                  {asked?.id === audit.id && (
                    <p className="t-sm u-body" style={{ marginTop: 6 }}>
                      {asked.text}
                    </p>
                  )}
                </div>
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
  // The audit in flight, if there is one. Nothing refuses a second audit while one is running,
  // so there can genuinely be more than one — the list is newest-first, and the newest is the
  // one the person on this screen just started. Any older one is still listed under Past audits
  // with its own live badge, so showing one panel hides nothing.
  const running = (audits.data?.audits ?? []).find((a) => AUDIT_IN_FLIGHT.includes(a.status));

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

  // A FAILED load, said as one. Falling through here rendered "No pages are registered yet"
  // over a broken platform — a system that is down looking like a project nobody has started.
  if (routes.isError) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="audit" />
        <LoadFailed
          what="The page list"
          error={routes.error}
          onRetry={() => void routes.refetch()}
        />
      </main>
    );
  }

  const rows = routes.data?.routes ?? [];
  const inScope = rows.filter((r) => r.enabled);
  const excluded = rows.filter((r) => !r.enabled);
  const shown = filter === "scope" ? inScope : filter === "excluded" ? excluded : rows;
  // Only this user's machines are visible to the app, so the wording says "you", never "nobody".
  const hasMachine = Boolean(runners.data?.some((r) => r.online || r.last_seen));
  // Absent on an older payload reads as "no" — the safe direction: a reader shown a disabled
  // button loses nothing, while an operator shown one for a moment simply reloads.
  const canManage = Boolean(routes.data?.can_manage);

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
            // The last sentence names which button to press. Without it the two buttons are a
            // choice with nothing to make it on: both add pages, and the difference — do you
            // already have the list, or are you building it up — was never stated anywhere.
            text="The platform has no access to your application, so it cannot discover its pages — somebody has to say what they are. Nothing is audited until you do. If you already have the list — a routes file, a sitemap, a page inventory — import it. Otherwise add them one page at a time."
            action={
              canManage ? (
                <div className="gate-panel__actions" style={{ justifyContent: "center" }}>
                  <Button variant="primary" onClick={() => setImporting(true)}>
                    Import a list
                  </Button>
                  <Button variant="secondary" onClick={() => setEditing(null)}>
                    Add a page
                  </Button>
                </div>
              ) : (
                <p className="t-sm u-muted">
                  The QA Lead or Tech Lead on this project registers the pages.
                </p>
              )
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
              canManage={canManage}
            />
          </div>

          {/* Full width, above everything, and only while something is actually happening. The
              audit in flight is the one thing on this screen nobody can afford to go looking
              for — it was in a 320px rail below seventy-nine page rows, which is exactly how
              far a running audit was from the person who had just started it. */}
          {running && (
            <div style={{ marginBottom: "var(--space-5)" }}>
              <RunningAudit audit={running} />
            </div>
          )}

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
                <Button
                  variant="secondary"
                  disabled={!canManage}
                  onClick={() => setEditing(null)}
                >
                  Add a page
                </Button>
                <Button variant="ghost" disabled={!canManage} onClick={() => setImporting(true)}>
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
                      disabled={!canManage || update.isPending}
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
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!canManage}
                      onClick={() => setEditing(row)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={!canManage || remove.isPending}
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
              <PastAudits
                audits={audits.data?.audits ?? []}
                projectId={projectId}
                canManage={canManage}
              />
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
