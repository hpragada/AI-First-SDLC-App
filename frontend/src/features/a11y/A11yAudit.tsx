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
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  Disclosure,
  EmptyState,
  Modal,
  Panel,
  Skeleton,
  Switch,
  Table,
  Textarea,
  writeErrorSentence,
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
import { a11yTime, a11yWhen } from "./dates";
import { LoadFailed } from "./LoadFailed";
import {
  AUDIT_IN_FLIGHT,
  useA11yAudits,
  useA11yJourneys,
  useA11yRoutes,
  useDeleteA11yRoute,
  useFinishStalledA11yAudit,
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

/** What a pass left unasked, said only when it is finished and only when it is true.
 *
 * **Built from the stored numbers, never from the stored sentence**, and that is the whole
 * point of this function. The dispatcher records its reason the moment judging *starts*, so the
 * sentence exists for the entire pass — and it is written in the past tense. Rendered without a
 * guard it told a reader that a run still judging had "stopped". Worse, the sentence carried
 * the raw count of deferred request *slots* while the Check-the-rest button beside it counted
 * distinct *elements*, so one card could say 12 and offer 6.
 *
 * The numbers underneath were right all along. So the screen composes its own sentence from
 * `deferred_distinct` — which also means an audit whose summary already has the wrong prose
 * baked in displays correctly, rather than being wrong for ever.
 *
 * The judge-unavailable reasons ("no machine is connected") are a different thing and are still
 * shown as written: those are not derivable from a count, and they are told apart by
 * `filed_unjudged` rather than by matching on wording — which would break the moment someone
 * improved a sentence.
 *
 * **Both can be true at once, and both are said** (31 Aug). A pass that reached its limit and
 * then could not send what it had kept is two facts about two different sets of elements. The
 * dispatcher used to fold the second set into the first — so only one sentence could ever apply
 * — and now that it correctly keeps them apart, showing one of them would hide the other. The
 * failure comes first because it is the one somebody has to go and do something about.
 *
 * **And the COUNT comes from `audit.unanswered`, which is the one place that knows** (9.26.D).
 * `deferred_distinct` is what the DISPATCH knew when it stopped — how many elements it held back
 * at its own limit — and that is a fact about the dispatcher, decided before the judging had
 * happened. It cannot know that the judge would then fail to report on an element as well, so it
 * can only ever under-count. On 31 August this said *268 left for a second pass* directly beside
 * a card reading *269 never looked at*, and the button offered 269: the prominent, reassuring
 * number was the wrong one and the small print was right.
 *
 * `unanswered` is `baseline.unanswered_counts` — the same single source the button, the Past
 * audits card and the baseline document already read. This function's own note says why that
 * matters: two counts of one thing is how this capability spent 21 August telling a team six
 * elements were outstanding while the code that would ask about them said none were. So the
 * dispatcher's sentence stays as the EXPLANATION of why work was deferred, and never as the
 * number.
 */
function unaskedNote(audit: A11yAuditRow): string {
  if (AUDIT_IN_FLIGHT.includes(audit.status)) return "";
  const pass = audit.summary?.ai_pass;
  if (!pass) return "";
  const notes: string[] = [];
  // Nothing was deferred that anything else did not already answer. An audit recorded before
  // `deferred_distinct` existed reads as 0 here and says nothing, which is the same choice the
  // button makes: silence beats a number known to mislead.
  if ((pass.filed_unjudged ?? 0) > 0 && pass.reason) notes.push(pass.reason);
  // One source, and it is the source the button acts on. `deferred_distinct` is the fallback
  // only for an audit closed before `unanswered` was ever computed for it — never a second
  // opinion when both are present.
  const deferred = pass.deferred_distinct ?? 0;
  const left = audit.unanswered ?? deferred;
  if (left > 0) {
    // The two halves are said separately when they differ, because "the run hit its limit" and
    // "the judge never came back about this one" are different things and only the first is
    // explained by the limit.
    const missed = Math.max(0, left - deferred);
    notes.push(
      `${left} ${left === 1 ? "element was" : "elements were"} captured and never checked. ` +
      (deferred > 0
        ? `This run reached its limit, so ${deferred} ${deferred === 1 ? "was" : "were"} left ` +
          `for a second pass` +
          (missed > 0
            ? `, and ${missed} more ${missed === 1 ? "was" : "were"} sent to the check and never ` +
              `reported on`
            : "") + ". "
        : "") +
      `Nothing was skipped — asking again is the only thing that answers them.`
    );
  }
  return notes.join(" ");
}

/** Is what this audit is doing (or last did) a SECOND judging pass over the same capture?
 *
 * "Check the rest" deliberately re-uses the audit row rather than opening a second audit — it
 * visits no page and re-judges one stored capture, so a second audit would be a lie about what
 * happened. But nothing on screen read the flag, so the completed audit a person was looking at
 * appeared to vanish and be replaced by a running one, and the running panel said "Audit
 * running · Pages visited 12 of 12" for a pass that opens no browser at all.
 */
function isRejudge(audit: A11yAuditRow): boolean {
  return Boolean(audit.summary?.ai_pass?.rejudged);
}

/** When the work now on screen actually started. The audit's own `created_at` is the FIRST
 *  pass's, and putting it beside a second pass dates the screen an hour early. */
function passStartedAt(audit: A11yAuditRow): string {
  return audit.summary?.ai_pass?.rejudged_at || audit.updated_at || audit.created_at;
}

/** The status word, in the words of the pass actually running. `judging` on a re-judge is not
 *  "Checking what was found" — everything was found an hour ago; this is checking the rest. */
/** Did this audit finish with part of what it captured never looked at?
 *
 * `unanswered` is elements **nothing ever checked** — not elements a check reached and could not
 * decide, which are somebody's job in the review queue. It is what the Check-the-rest button
 * counts, and the API only sends it for a closed audit.
 */
function leftUnchecked(audit: A11yAuditRow): number {
  return AUDIT_IN_FLIGHT.includes(audit.status) ? 0 : audit.unanswered ?? 0;
}

/** The status word — from the audit's state AND from how much of it was never done.
 *
 * **Both facts were already on this screen and they contradicted each other.** The row said
 * `complete` because the RUN finished and nothing crashed, which is true of the run and not of
 * the work: directly underneath, its own warning said six elements were left for a second pass
 * and offered a button to do them. So the strongest signal on the row — a green badge and the
 * word Complete — told somebody scanning a list of past audits that an application had been
 * fully checked when part of it was never looked at. A quiet success is this capability's worst
 * failure, and it was sitting between two things that said otherwise.
 *
 * Derived rather than stored, so the moment Check the rest covers the remainder the count drops
 * to zero and this turns green on its own. Nothing to keep in step.
 *
 * **Not "In progress"** (team decision, 25 August): nothing is running at this point, and this
 * same screen shows a genuine "Audit running" panel for work actually in flight. Two different
 * things reading as in-flight sends somebody looking for a run that is not happening.
 */
function statusLabel(audit: A11yAuditRow): string {
  // **Before the status word, because it contradicts it.** `stalled` means the machine holding
  // this audit has said nothing for longer than its lease — so "Visiting pages" and "Checking
  // the rest" are both describing work that is not happening. The panel above the list was
  // taught this first, and the row underneath went on saying "Checking the rest" beside it: the
  // same audit, two answers, one screen (9.26.E1). One row of a list is exactly where somebody
  // scanning for what still needs attention looks, and it must not be the reassuring one.
  if (audit.stalled) return "Stopped";
  if (audit.status === "judging" && isRejudge(audit)) return "Checking the rest";
  if (audit.status === "complete" && leftUnchecked(audit) > 0) return "Not fully checked";
  return STATUS_LABEL[audit.status] ?? audit.status;
}

function auditBadge(audit: A11yAuditRow): "done" | "failed" | "waiting" {
  if (audit.stalled) return "failed";
  if (audit.status === "failed") return "failed";
  // Amber, not green, and this is the whole point: green is the one thing a person reads without
  // reading. An audit that never asked about part of its own capture has not earned it.
  if (audit.status === "complete") return leftUnchecked(audit) > 0 ? "waiting" : "done";
  return "waiting";
}

// One format across the Accessibility tabs: "10 Oct 2026, 6:12 PM" (see ./dates).
const when = a11yWhen;

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
            {writeErrorSentence(register.error)}
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
      {/* No "the platform cannot discover your pages" banner. It was here and on the empty
          state behind it, so the same explanation was read twice on the way to one action, and
          the field help below already says what to paste and in which formats — which is what
          somebody who has just opened this box actually needs (team decision, 25 August). */}
      <label className="field">
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
          {writeErrorSentence(error)}
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
          {writeErrorSentence(error)}
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
  address: suggested,
  hasMachine,
  canManage,
}: {
  projectId: string;
  routes: A11yRoute[];
  scopeChange: { added?: string[]; removed?: string[]; before?: number; now?: number };
  address: { url?: string; source?: string; reason?: string };
  hasMachine: boolean;
  canManage: boolean;
}) {
  // `undefined` until the person types, so the resolved address arrives without an effect and
  // without overwriting what they typed on the next poll. Same shape as the journeys panel
  // below, on purpose — two address boxes on one screen behaving differently is its own bug.
  const [address, setAddress] = useState<string | undefined>();
  const value = address ?? suggested.url ?? "";
  const start = useStartA11yAudit(projectId);
  const inScope = routes.filter((r) => r.enabled);
  const passes = Math.max(1, Math.ceil(inScope.length / PAGES_PER_PASS));
  const moved = (scopeChange.added?.length ?? 0) + (scopeChange.removed?.length ?? 0) > 0;

  // No machine badge in the corner (team decision, 25 August). The navigation bar already
  // carries `Companion: Ready` at all times, and the absence of a machine is stated below in a
  // banner that also says what to do about it — which is the half that was ever worth the space.
  return (
    <Panel title="Run an audit">
      {/* One sentence, then the detail behind a click (team decision, 25 August). Two dense
          paragraphs stood between the panel title and the button, and the second of them — what
          the machine needs installed — is worth reading once, on the day an audit fails because
          the browser is missing. Kept rather than deleted for exactly that day: it is still the
          only place that says an audit and a keyboard journey resolve their tooling differently,
          which is otherwise discovered from a failed run several minutes later. */}
      <p className="t-sm u-muted">
        The scan runs on your connected machine, not on our servers.
      </p>
      <Disclosure summary="What this means, and what your machine needs">
        <p>
          Your application is at an address only your machine can reach. Nothing about it is ever
          sent to us except what the scan writes down.
        </p>
        <p>
          Your machine needs a browser and the <span className="t-mono">axe</span> scanner. If the
          application's own repository is checked out there and ships them, the audit uses that
          copy — and the report names the version your application actually uses. Otherwise it
          falls back to the companion's own, and every scan says{" "}
          <span className="t-mono">(companion)</span> beside the version so the two are never
          confused.
        </p>
      </Disclosure>

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
          {/* The address the audit will actually use, shown rather than described. The
              placeholder used to read "taken from your repository's Preview URL" — a sentence
              about where the default comes from, sitting where an example of what to type
              belongs, above a box that was empty. So the one thing a person wanted to know
              (which address is this about to scan?) was the one thing not on screen, and the
              grey text read like something to copy. The journeys panel below has always done
              this properly; this is the same resolver and the same shape. */}
          <input
            className="input"
            type="text"
            aria-labelledby="app-address"
            placeholder="http://localhost:3000"
            value={value}
            onChange={(e) => setAddress(e.target.value)}
          />
          <span className="field__help">
            {suggested.source
              ? `Pre-filled from ${suggested.source}. `
              : `${suggested.reason || "Where the running application answers."} `}
            Typing a different one scans another environment for this run only — it is not saved
            back.
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
              {passes}{" "}
              <span className="u-muted">· up to {PAGES_PER_PASS} pages per pass</span>
            </span>
            <span className="t-sm">Standard</span>
            <span className="t-sm">WCAG 2.2 Level AA</span>
          </div>
        </div>
      </div>

      {start.isError && (
        <Banner variant="danger" title="The audit could not be started">
          {writeErrorSentence(start.error)}
        </Banner>
      )}

      <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
        <Button
          variant="primary"
          disabled={!canManage || inScope.length === 0 || start.isPending}
          onClick={() =>
            start.mutateAsync({ base_url: value.trim() || undefined }).catch(() => undefined)
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

  // No badges in the corner (team decision, 25 August). "Machine connected" repeated
  // `Companion: Ready` in the navigation bar, permanently on screen a few inches away — and when
  // there is NO machine this panel already says so in a full banner below, with what to do about
  // it, which is the version worth reading. "Reported, never blocking" is a policy about what
  // happens to results rather than a state, and it is stated in full at the foot of this panel.
  // Neither badge was the only place anything was said.
  return (
    <Panel title="Keyboard journeys">
      {/* One sentence, then the rest behind a click (team decision, 25 August). This paragraph
          and the "Start your application first" banner below it were about a third of the
          panel's height, above the table people come here for — read once and re-read past on
          every visit after. Both are folded in together because they are the same subject; see
          the note where the banner used to be. */}
      <p className="t-sm u-muted">
        Eight WCAG checks can only be answered by <em>operating</em> the application with a
        keyboard — the industry scanner covers one of the eight.
      </p>
      <Disclosure summary="What this means">
        <p>
          The eight are things no page can be judged on standing still: whether focus can get out
          of a menu, whether you can see where you are, whether a screen reader is told when
          something changes.
        </p>
        <p>
          <strong>Start your application first.</strong> A journey walks the live application,
          step by step. Make sure it is running at the address below before you start — if
          nothing answers there the run stops immediately and records no steps, rather than
          reporting on steps it never walked.
        </p>
      </Disclosure>

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

          {/* "Start your application first" moved up into the expander at the top of this
              panel, beside the rest of the explanation. It was a full-width banner in the same
              blue the platform uses for things that need doing, for a fact that is true on every
              visit — so it read as an alert and was one on no particular occasion. */}
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
              {writeErrorSentence(start.error)}
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

/** The panel S-38 designs for the newest audit — running, then finished (S-38 lines 598, 645).
 *
 * **Why it exists.** Until it did, the only thing on screen while an audit ran was a status word
 * in a list — so an audit that had visited 6 of 10 pages and one that had visited none looked
 * identical, and an audit whose judge had stopped looked exactly like one still working. That is
 * this capability's own standard turned on itself: a screen must not state progress it cannot
 * evidence, and "Checking what was found" for forty minutes states plenty.
 *
 * **And it does not disappear when the run ends.** It changes what it says. A person who started
 * an audit and watched it work must not have the answer vanish at the moment it arrives — that
 * is the same silence one step later, and it is what the team met on the first complete run.
 *
 * Three tiles throughout, because what you need to know changes with the stage: which pass while
 * the pages are being visited, how far the judging has got once they are in, and what the whole
 * thing came to once it stops. The design's live per-page console is a separate, larger piece of
 * work — screens are posted one per call with no progress channel to carry per-page lines — and
 * is recorded as a pending enhancement rather than half-built here.
 */
/** The one way out of a judging pass that was parked past its deadline (9.26.F).
 *
 *  **Why a button on this screen and not an automatic retry.** Accepting a parked run back into
 *  the claim lease would have been fewer moving parts, and it would spend the user's own Claude
 *  subscription on a decision nobody asked them about. The team has already ruled on this shape
 *  once, rejecting an audit that continues itself: *"what if he adds 30 routes and all his Claude
 *  usage burns?"* Offer the button; do not press it for them.
 *
 *  It is deliberately not called "take over", "abandon" or anything else the platform calls it
 *  internally. The person looking at this started an audit and wants it finished.
 */
function FinishStalledAudit({
  runId,
  projectId,
}: {
  runId: string;
  projectId: string | undefined;
}) {
  const finish = useFinishStalledA11yAudit(projectId);
  return (
    <div className="u-row" style={{ marginTop: "var(--space-4)" }}>
      <Button
        variant="primary"
        disabled={finish.isPending}
        onClick={() => finish.mutate(runId)}
      >
        {finish.isPending ? "Finishing…" : "Finish this audit"}
      </Button>
      {/* A failure here leaves the audit exactly as it was — nothing is half-closed — but the
          person has to be told, or the button just looks broken. */}
      {finish.isError && (
        <span className="t-sm u-danger">
          Could not finish it just now. Nothing was changed — try again in a moment.
        </span>
      )}
    </div>
  );
}

/** Mockup M5: "Audit complete · finished Oct 10, 3:45 PM" with "started 3:30 PM" under it. The
 *  header used to print the START time beside the word "complete", while the conformance
 *  statement printed the finish time — one audit, two times, neither labelled. */
function finishedTitle(done: string, audit: A11yAuditRow) {
  const started = a11yTime(audit.created_at);
  return (
    <>
      {done} · finished {when(audit.updated_at)}
      {started && (
        <span className="t-sm u-muted" style={{ display: "block", fontWeight: "normal" }}>
          started {started}
        </span>
      )}
    </>
  );
}

function LatestAudit({
  audit,
  projectId,
}: {
  audit: A11yAuditRow;
  projectId: string | undefined;
}) {
  const running = AUDIT_IN_FLIGHT.includes(audit.status);
  const asked = audit.summary?.asked ?? audit.routes.length;
  const badge = (
    <Badge variant={auditBadge(audit)}>
      {statusLabel(audit)}
    </Badge>
  );

  if (!running) {
    const outcome = audit.outcome ?? { problems: 0, critical: 0, high: 0, waiting: 0 };
    const neverOpened = audit.summary?.never_reported ?? [];
    const failed = audit.status === "failed";
    // `created_at` is when the AUDIT began, and it identifies the audit — but on one that has
    // since had a second judging pass it is the wrong time to sit above numbers that changed an
    // hour later. Both are said, in that order, so the row is still recognisable as the audit
    // it is.
    const rechecked = isRejudge(audit) ? when(passStartedAt(audit)) : "";
    // The heading says the same thing as the badge, for the same reason. "Audit complete" above
    // a warning that six elements were never checked is the contradiction this fix is about, and
    // leaving it in the title while correcting the badge would only move it.
    const done = leftUnchecked(audit) > 0 ? "Audit finished, not fully checked" : "Audit complete";
    return (
      <Panel
        title={
          failed
            ? "Audit could not run"
            : rechecked
              ? `${done} · ${when(audit.created_at)}, rechecked ${rechecked}`
              : finishedTitle(done, audit)
        }
        actions={badge}
      >
        {failed ? (
          // Its own words, whatever the machine gave us. The generic "the application did not
          // respond" would send someone to check a server that was never contacted.
          <p className="t-sm u-body">
            {audit.summary?.reason || "The audit stopped before it could report anything."}
          </p>
        ) : (
          <>
            <div className="grid grid--3" style={{ marginBottom: "var(--space-4)" }}>
              <div className="tile">
                <div className="tile__num">{audit.summary?.opened ?? 0}</div>
                <div className="tile__label">Pages reported</div>
                <div className="tile__sub">of {asked} asked for</div>
              </div>
              {/* This PROJECT open, not this audit. A finding carries no audit key, and the
                  Accessibility baseline is itself project-scoped for the same reason — so that
                  an audit covering part of an application never drops what is already known
                  about the rest. The sub-line says so rather than letting the tile imply a
                  per-run tally. */}
              <div className="tile">
                <div className="tile__num">{outcome.problems}</div>
                <div className="tile__label">Problems open</div>
                <div className="tile__sub">
                  {outcome.critical} critical &middot; {outcome.high} high &middot; in this project
                </div>
              </div>
              <div className="tile">
                <div className="tile__num">{outcome.waiting}</div>
                {/* Mockup M1: was "Waiting on a person", beside the Conformance tab's "Waiting on
                    you" — elements here, criteria there, and the shared words made two correct
                    numbers look like a contradiction. Named for what it counts, and it links to
                    where those items are. Never "0 problems left": nothing to review means every
                    check was sure enough to answer on its own, not that the application is clean. */}
                <div className="tile__label">Items to review</div>
                <div className="tile__sub">
                  <Link to="/a11y">in the Review queue →</Link>
                </div>
              </div>
            </div>

            {/* An audit that stopped at its own limit says so. The dispatch always recorded
                this — "stopped at this run's limit of N, M item(s) still need judging" — and
                nothing on any screen read it, so a pass that never asked about part of what it
                captured closed as COMPLETE and said nothing. A quiet success is the worst
                failure this capability has, and it was sitting in its own summary. */}
            {unaskedNote(audit) && (
              <Banner variant="warning" title="Not everything captured was checked">
                {unaskedNote(audit)}
              </Banner>
            )}

            {/* A different sentence from the one above, and a worse one: that says part of what
                was captured went unasked, this says one of the checks could not run at all.
                Named separately so it can never be read as "the application has no label
                problems" — nothing looked for any. (No count here, matching the visible copy
                and the backend prose: it said "four" from the day `structure` made it five.) */}
            {audit.summary?.names?.reason && (
              <Banner variant="warning" title="One of the checks could not run">
                {audit.summary.names.reason}
              </Banner>
            )}

            {/* A page that never opened is stated, never absorbed. Nothing it might have
                contained is treated as passing, and it cannot close a problem found there
                before. */}
            {neverOpened.length > 0 && (
              <Banner
                variant="warning"
                title={
                  neverOpened.length === 1
                    ? "One page was asked for and never opened"
                    : `${neverOpened.length} pages were asked for and never opened`
                }
              >
                <span className="t-mono">{neverOpened.slice(0, 4).join(", ")}</span>
                {neverOpened.length > 4 && ` and ${neverOpened.length - 4} more`}. Recorded as
                never seen, so nothing they might have contained is treated as passing.
              </Banner>
            )}

            <div className="u-row" style={{ marginTop: "var(--space-4)" }}>
              <span className="t-sm u-muted">
                The <strong>Accessibility baseline</strong> document is in Artifacts.
              </span>
              {outcome.waiting > 0 && (
                <Link to="/a11y" className="btn btn--secondary btn--sm">
                  Answer the {outcome.waiting} waiting
                </Link>
              )}
            </div>
          </>
        )}
      </Panel>
    );
  }

  const progress = audit.progress ?? { visited: 0, unreachable: 0 };
  // DISTINCT elements, not requests. The same markup on ten pages is one thing to judge, and
  // counting verdicts against requests made a finished audit read as two-thirds done. Declared
  // here rather than beside the running tiles because the stalled panel below says the same
  // number, and it is the same number.
  const dispatched = progress.dispatched ?? 0;

  // Says it is running, and nothing has come back from the machine holding it for a long while.
  // Shown BEFORE the running panel, because everything below this point describes work in
  // progress and none of it is happening. The audit is closed for real the moment any companion
  // on this project reports in; until then this is the honest reading of the same row, and if
  // that machine never comes back it is the only one there will ever be.
  if (audit.stalled) {
    // A stalled CAPTURE and a stalled JUDGING pass are not the same situation and must not be
    // told in the same words. A half-capture is thrown away — nothing is reported from a partial
    // pass, because a baseline drawn from four of twelve pages states coverage the audit never
    // had. A half-judged capture is the opposite: every verdict already written is kept for good,
    // no page has to be visited again, and starting the machine back up carries on from here.
    // Telling a judging pass it "will be closed as failed" and offering to start a new audit
    // would throw away an hour of judging that is already paid for and already correct.
    const stalledJudging = audit.status === "judging";
    const quietSince = when(audit.stalled_since);
    // **And within a stopped judging pass, two states that need opposite instructions.**
    //
    // For as long as the report deadline has not fired, the pass really does resume by itself:
    // a returning companion is offered the stale claim back and carries on. Once it fires the
    // run is PARKED, and the re-claim rule only ever offers PENDING or RUNNING runs — so from
    // that instant it can never be re-claimed, permanently, and restarting the machine does
    // nothing at all.
    //
    // The panel used to say "start the machine again and it carries on from where it stopped"
    // in both. That was true when it was written and false the moment the deadline fired, which
    // is worse than saying nothing: it sends somebody to restart a machine that will sit there
    // doing nothing, and offers them no other route. The only real way out was a human takeover
    // from the run-recovery console — a page somebody auditing their own website has no reason
    // to have ever opened.
    //
    // So the audit screen owns the whole recovery, because the audit is the thing the user
    // understands. One button, on the page they are already on, and they never learn the words
    // "parked run", "takeover" or "workflow".
    const parkedRunId = audit.parked_run_id ?? null;
    return (
      <Panel
        title={
          parkedRunId
            ? "This audit is waiting on you"
            : stalledJudging
              ? "Checking stopped"
              : "Audit stopped reporting"
        }
        actions={<Badge variant="failed">Stopped</Badge>}
      >
        <p className="t-sm u-body">
          {parkedRunId
            ? "The machine checking this audit did not come back in time, so the platform has stopped waiting for it. "
            : `Nothing has come back from the machine ${stalledJudging ? "checking" : "running"} this audit for a long while — it was most likely closed, restarted or disconnected part-way through. `}
          {stalledJudging ? (
            <>
              It answered{" "}
              <strong>
                {progress.judged ?? 0} of {dispatched}
              </strong>{" "}
              element(s){quietSince ? <>, last at <strong>{quietSince}</strong></> : null}.
            </>
          ) : (
            <>
              It reported{" "}
              <strong>
                {progress.visited} of {asked}
              </strong>{" "}
              pages before it went quiet
              {quietSince ? <>, last at <strong>{quietSince}</strong></> : null}.
            </>
          )}
        </p>
        <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
          {parkedRunId ? (
            <>
              Every answer it did give is kept. Finishing writes up what it found, sends
              everything it never got to for a person to look at, and closes the audit — then
              you can check the rest whenever a machine is connected again. Restarting the
              machine on its own will not pick this up.
            </>
          ) : stalledJudging ? (
            <>
              Every answer it did give is kept, and no page has to be visited again. Start the
              machine again and it carries on from where it stopped — nothing here needs to be
              re-run by hand.
            </>
          ) : (
            <>
              Nothing is reported from a partial pass, so this audit will be closed as failed as
              soon as a companion on this project reports in. You can start a new audit now — what
              was captured here costs only the minutes it took.
            </>
          )}
        </p>
        {parkedRunId && <FinishStalledAudit runId={parkedRunId} projectId={projectId} />}
      </Panel>
    );
  }

  const passes = Math.max(1, Math.ceil(asked / PAGES_PER_PASS));
  const judging = audit.status === "judging";
  // Which pass the capture is on, from what has come back. Derived rather than reported: the
  // companion writes one screen at a time and never says which pass it is in, and a number
  // computed from the screens actually posted cannot claim a pass that has not started.
  const pass = Math.min(passes, Math.floor(progress.visited / PAGES_PER_PASS) + 1);

  // A re-judge opens no browser and visits no page: the two capture tiles below are true about
  // the CAPTURE and would read as work happening now. Said once, plainly, rather than left to
  // be inferred from tiles that have not moved.
  const rejudging = isRejudge(audit);

  return (
    <Panel
      title={rejudging ? "Checking the rest of this audit" : "Audit running"}
      actions={badge}
    >
      {rejudging && (
        <p className="t-sm u-body" style={{ marginBottom: "var(--space-4)" }}>
          Started {when(passStartedAt(audit))}, going back over{" "}
          <strong>
            {audit.summary?.ai_pass?.rejudged_asked ?? 0} element(s)
          </strong>{" "}
          that nothing had looked at. No page is visited — everything needed was stored when the
          pages were captured, so the two counts below are what that capture found.
        </p>
      )}
      <div className="grid grid--3" style={{ marginBottom: "var(--space-4)" }}>
        {judging ? (
          <div className="tile">
            <div className="tile__num">
              {progress.judged ?? 0} <span className="t-sm u-muted">of {dispatched}</span>
            </div>
            <div className="tile__label">Elements judged</div>
            <div className="tile__sub">
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
          <div className="tile__label">{rejudging ? "Pages in the capture" : "Pages visited"}</div>
          <div className="tile__sub">
            {rejudging ? "visited when the audit ran" : `of ${asked} asked for`}
          </div>
        </div>
        <div className="tile">
          <div className="tile__num">{progress.unreachable}</div>
          <div className="tile__label">Pages that didn't load</div>
          <div className="tile__sub">
            {rejudging ? "when the audit ran" : "each one listed, never guessed"}
          </div>
        </div>
      </div>
      <p className="t-sm u-muted">
        You can leave this page. {rejudging ? "This carries on" : "The audit carries on"} and the
        result appears under Past audits.
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
              {/* A re-judge re-uses this row rather than adding one, so without this line the
                  row dates itself an hour early and a person who just pressed Check the rest
                  sees only the original audit's time above a badge that says it is running. */}
              {isRejudge(audit) && (
                <div className="artifact-row__meta">
                  Rechecked {when(passStartedAt(audit))}
                </div>
              )}
              <div className="u-row" style={{ marginTop: 6 }}>
                <Badge variant={auditBadge(audit)}>
                  {statusLabel(audit)}
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
              {/* And why part of it was never asked about, which is a different sentence from
                  the one above: that one is why the audit failed, this one is why a successful
                  audit is incomplete. */}
              {/* Silent while the audit is still judging. The sentence is written when the
                  pass STARTS, so rendering it unguarded described a running audit as stopped —
                  the same rule the API already follows by refusing to count `unanswered` for an
                  audit in flight, and the panel above by guarding on `!running`. */}
              {unaskedNote(audit) && (
                <p className="t-sm u-muted" style={{ marginTop: 6 }}>
                  {unaskedNote(audit)}
                </p>
              )}

              {/* Elements nothing ever looked at — offered back to the machine rather than left
                  on a person. Only on a CLOSED audit (the API only counts those), and only when
                  there are some: a button that is always there, usually saying nothing to do, is
                  a button nobody reads. The count is said out loud, because "check the rest" with
                  no number is a promise of unknown size. */}
              {(audit.unanswered ?? 0) > 0 && (
                <div style={{ marginTop: "var(--space-3)" }}>
                  {/* It does NOT say these are waiting in the review queue, and that sentence
                      was here until the first re-judge put it next to a "0 waiting on a person"
                      tile on the same screen. An element nothing ever looked at has no finding
                      and therefore no queue entry — that is exactly what distinguishes it from
                      an `uncertain`, which a check reached and could not decide. The old copy
                      sent a reader to an empty queue to look for work that was only ever here,
                      behind this button. */}
                  <p className="t-sm u-muted">
                    {audit.unanswered === 1
                      ? "1 element was never looked at"
                      : `${audit.unanswered} elements were never looked at`}
                    {" — not checked and undecided, but never checked at all. Nothing here says"}
                    {" whether they are accessible, and nobody is waiting on them: asking again"}
                    {" is the only thing that answers them."}
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
                          .catch((err: unknown) =>
                            setAsked({ id: audit.id, text: writeErrorSentence(err) }),
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
  // The newest audit, whatever state it is in. Deliberately not "the one in flight": the panel
  // stays after the run ends and shows what it came to, because the moment the answer arrives is
  // the worst possible moment for the panel somebody was watching to disappear.
  //
  // The list is newest-first, and Past audits below is the WHOLE history — this one included,
  // not just the older ones. So the newest audit is on screen twice: in detail here, and as a
  // row down there. That is deliberate (team decision, 21 August): the row is where "Check the
  // rest" lives, and moving it up here to remove the repetition would take the button off the
  // only audit anybody presses it on. A history that stops before today is the worse screen.
  const latest = (audits.data?.audits ?? [])[0];

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
            // Names which button to press, and nothing else. It used to open with why the
            // platform cannot discover the pages itself — three sentences of architecture
            // standing between somebody and the only two things they can do here. The
            // difference that actually needs stating is do you already have the list, or are
            // you building it up, and that is all this says now (team decision, 25 August).
            text="If you already have the list — a routes file, a sitemap, a page inventory — import it. Otherwise add them one page at a time."
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
              address={{
                url: routes.data?.base_url,
                source: routes.data?.base_url_source,
                reason: routes.data?.base_url_reason,
              }}
              hasMachine={hasMachine}
              canManage={canManage}
            />
          </div>

          {/* Full width, above everything, and only while something is actually happening. The
              audit in flight is the one thing on this screen nobody can afford to go looking
              for — it was in a 320px rail below seventy-nine page rows, which is exactly how
              far a running audit was from the person who had just started it. */}
          {latest && (
            <div style={{ marginBottom: "var(--space-5)" }}>
              <LatestAudit audit={latest} projectId={projectId} />
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
                  {writeErrorSentence(update.error ?? remove.error)}
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
