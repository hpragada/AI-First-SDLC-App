// Screen Words Sweep, group 4 (Option A) — one shared map per kind of stored value, so a raw
// key like `awaiting_gate`, `test_case`, `unlinked`, `internal` or `pointer_hash` can never
// reach a client's screen.
//
// Why one module rather than a helper per screen: the sweep found the same value printed raw on
// one screen and labelled on another, and a status shown in green whatever it meant. A screen
// that wants to show one of these values now has exactly one place to get the words from, and
// `labels.test.ts` fails if a key the backend can send has no entry here.
//
// Deliberately NOT here, because each already has a home that is the single source of truth:
//   - membership roles        -> features/identity/roles.ts (`roleLabel`)
//   - document status         -> features/observability/artifactStatus.tsx
//   - phase / gate names      -> features/lifecycle/phases.ts
//
// Every map has a humanizing fallback rather than a default label. A value added to the backend
// later then reads a little stiffly instead of silently claiming to be something it is not —
// which is the fault that made an APPROVED document read as "Draft".

/** `test_case` -> `Test case`. Underscores out, first word capitalized, nothing invented. */
export function humanize(token: string | null | undefined): string {
  if (!token) return "";
  const s = String(token).replace(/_/g, " ").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : "";
}

// ── Run status ──────────────────────────────────────────────────────────────
// Shown on the work-item screens, the run console and the Phases & Runs table. Every one of
// these used to render green, so a FAILED run and a completed one looked alike at a glance.
// The badge variants the design system already defines, so there is no second colour
// vocabulary to keep in step with `components/ui`.
import type { BadgeVariant } from "./components/ui";

// These are exactly `Run.Status` in backend/apps/runs/models.py — no more and no less. Written
// from the enum rather than from memory: a first pass here invented `queued` and `cancelled`
// (neither is a run status) and omitted `pending` and `stalled` (both are), which a trigger test
// caught by finding "it is pending" in a refusal.
const RUN_STATUS: Record<string, { label: string; tone: BadgeVariant }> = {
  // Created but not yet picked up by a worker. "Pending" says nothing about why the reader is
  // waiting; "Queued" does.
  pending: { label: "Queued", tone: "queued" },
  running: { label: "Running", tone: "running" },
  // The client-facing word for "a named person has been asked to decide". "Awaiting gate" is
  // the platform's own vocabulary and says nothing about anyone needing to act.
  awaiting_gate: { label: "Waiting for approval", tone: "gate" },
  approved: { label: "Approved", tone: "done" },
  completed: { label: "Completed", tone: "done" },
  rejected: { label: "Changes requested", tone: "failed" },
  failed: { label: "Failed", tone: "failed" },
  // Parked for human takeover, NOT terminal: a companion that only slept can still return and
  // report (Bugs S.No 89). So neither "failed" nor "done" — the design system's `parked`.
  //
  // This said "Paused — your machine stopped reporting" until a run could really be PAUSED by a
  // person. Two states both reading "Paused" left the word unable to tell the reader whether
  // anything had gone wrong, so this one became "Stopped". Keep the two distinct; mirrored in
  // backend apps/labels.py.
  stalled: { label: "Stopped — your machine stopped reporting", tone: "parked" },
  // A human stopped this run on purpose and means to resume it. Same `parked` tone — it is the
  // design system's colour for "alive, waiting on a person" — but the words are about a choice
  // somebody made, not a failure.
  paused: { label: "Paused by you", tone: "parked" },
  // `done` and `gate` are the short forms the component gallery's sample rows use. They are
  // not values the backend sends, but the gallery is what the team reviews, so they must read
  // the same way there as a real run does.
  done: { label: "Completed", tone: "done" },
  gate: { label: "Waiting for approval", tone: "gate" },
};

export function runStatusLabel(status: string | null | undefined): string {
  return RUN_STATUS[String(status ?? "")]?.label ?? humanize(status);
}

export function runStatusTone(status: string | null | undefined): BadgeVariant {
  return RUN_STATUS[String(status ?? "")]?.tone ?? "neutral";
}

// ── Work-item type ──────────────────────────────────────────────────────────
const WORK_ITEM_TYPE: Record<string, string> = {
  epic: "Epic",
  story: "Story",
  task: "Task",
  defect: "Defect",
  test_case: "Test case",
};

export function workItemTypeLabel(type: string | null | undefined): string {
  if (!type) return "Item";
  return WORK_ITEM_TYPE[String(type)] ?? humanize(type);
}

// ── Repository role and status ──────────────────────────────────────────────
// `Repository.role` is free text on the backend (frontend / backend / service / anything a
// project needs), so this humanizes rather than enumerating — an enumeration would be a lie
// about a field that accepts any word.
export function repoRoleLabel(role: string | null | undefined): string {
  return humanize(role) || "Unspecified";
}

const REPO_STATUS: Record<string, { label: string; tone: BadgeVariant }> = {
  connected: { label: "Connected", tone: "done" },
  // Was shown in green like everything else, which read as "fine" for a repository the
  // platform cannot reach. Amber: it is not broken, it is not finished either.
  unlinked: { label: "Not linked", tone: "gate" },
  error: { label: "Connection failed", tone: "failed" },
};

export function repoStatusLabel(status: string | null | undefined): string {
  return REPO_STATUS[String(status ?? "")]?.label ?? humanize(status);
}

export function repoStatusTone(status: string | null | undefined): BadgeVariant {
  return REPO_STATUS[String(status ?? "")]?.tone ?? "neutral";
}

// ── System of record ────────────────────────────────────────────────────────
// Every artifact carried the Confluence "C" glyph whatever system it actually lived in, so a
// file in GitHub and a page in Confluence were drawn identically. `chip` is the existing
// `sor-chip--*` modifier that colours the glyph.
const SOR: Record<string, { label: string; glyph: string; chip: string }> = {
  internal: { label: "Platform", glyph: "P", chip: "platform" },
  git: { label: "GitHub", glyph: "G", chip: "github" },
  github: { label: "GitHub", glyph: "G", chip: "github" },
  confluence: { label: "Confluence", glyph: "C", chip: "confluence" },
  jira: { label: "Jira", glyph: "J", chip: "jira" },
  figma: { label: "Figma", glyph: "F", chip: "figma" },
  xray: { label: "Xray", glyph: "X", chip: "xray" },
};

export function sorLabel(sor: string | null | undefined): string {
  return SOR[String(sor ?? "")]?.label ?? humanize(sor);
}

export function sorGlyph(sor: string | null | undefined): string {
  return SOR[String(sor ?? "")]?.glyph ?? (sorLabel(sor)[0] ?? "?").toUpperCase();
}

/** The full `class` for a system-of-record chip, e.g. `sor-chip sor-chip--github`. */
export function sorChipClass(sor: string | null | undefined): string {
  return `sor-chip sor-chip--${SOR[String(sor ?? "")]?.chip ?? "platform"}`;
}

// ── Uploaded source documents (brownfield) ──────────────────────────────────
// `uploaded` is the one its own label list forgot, so it was the one status that printed raw.
const DOCUMENT_STATUS: Record<string, string> = {
  uploaded: "Uploaded",
  extracting: "Reading it now",
  extracted: "Ready to adopt",
  adopted: "Adopted",
  failed: "Couldn't be read",
};

export function documentStatusLabel(status: string | null | undefined): string {
  return DOCUMENT_STATUS[String(status ?? "")] ?? humanize(status);
}

// ── Contract drift ──────────────────────────────────────────────────────────
// `DriftRecord.Kind` on the backend. "Pointer/Hash" is the enum's own label and is no better
// on a screen than the key, so both get a sentence a client can act on.
const DRIFT_KIND: Record<string, string> = {
  contract: "Contract changed",
  pointer_hash: "Document changed",
};

export function driftKindLabel(kind: string | null | undefined): string {
  return DRIFT_KIND[String(kind ?? "")] ?? humanize(kind);
}

// ── Engine and model ────────────────────────────────────────────────────────
// Group 4 Option A: the team chose to KEEP this line and make it readable, rather than drop it.
// The engine key is the driver (`claude`); the model is whatever id the run recorded.
const ENGINE_LABEL: Record<string, string> = { claude: "Claude" };

// Model ids are versioned and new ones appear without the UI changing, so this strips the
// vendor prefix and date suffix rather than listing every id: `claude-opus-5` -> `Opus 5`,
// `claude-haiku-4-5-20251001` -> `Haiku 4.5`.
export function modelLabel(model: string | null | undefined): string {
  const raw = String(model ?? "").trim();
  if (!raw) return "";
  const rest = raw.replace(/^claude[-_]?/i, "").replace(/[-_]?\d{8}$/, "");
  const family = rest.match(/^(opus|sonnet|haiku|fable)/i);
  if (!family) return humanize(rest) || raw;
  const version = rest
    .slice(family[0].length)
    .replace(/^[-_]/, "")
    .replace(/[-_]/g, ".");
  const name = family[0][0].toUpperCase() + family[0].slice(1).toLowerCase();
  return version ? `${name} ${version}` : name;
}

/** `claude` + `claude-opus-5` -> `Claude · Opus 5`. Either half may be missing. */
export function engineLabel(
  engine: string | null | undefined,
  model?: string | null,
): string {
  const e = ENGINE_LABEL[String(engine ?? "")] ?? humanize(engine);
  const m = modelLabel(model);
  return [e, m].filter(Boolean).join(" · ");
}

/** Whether a STORED failure reason is fit to show as the explanation, or is a log excerpt.
 *
 * The failure classifier (`describe_build_failure`) ends by passing an unrecognised reason through
 * word-for-word — "already a specific message - kept, never lost" — which is right for text that
 * really is a sentence and wrong for the rest. A real failed run in the local database stored
 * "Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for details",
 * and the run console printed it after the word "Reason:".
 *
 * A log excerpt gives itself away twice over: it runs to more than one line, and it names
 * machinery. Mirrors `_reads_as_prose` in `backend/api/serializers.py`, which does this for the
 * console's event lines; the two are deliberately the same rule, because they are shown a few
 * pixels apart and disagreeing would be worse than either answer.
 *
 * When this says no, the caller falls back to the sentence it already shows for a failure with no
 * reason recorded, and the raw text stays where it already goes — under "Technical details".
 */
const LOG_MARKERS = [
  "exit code", "traceback", "stderr", "stdout", "::", "errno", "activity task", "workflow task",
];

export function readsAsSentence(text: string): boolean {
  if (/[\r\n]/.test(text)) return false;
  const lowered = text.toLowerCase();
  return !LOG_MARKERS.some((marker) => lowered.includes(marker));
}
