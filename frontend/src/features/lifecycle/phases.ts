// Human-readable phase names + brownfield-phase visibility for the work-item lifecycle.
// Bugs.xlsx row 21: phase names must never show raw (e.g. "task_breakdown" or "06_task_breakdown"),
// and the brownfield-only onboarding phases must not appear on a work item's lifecycle rail
// (they belong to project onboarding, not per-work-item flow). This is a UI-only concern —
// it filters/relabels what the rail shows; it does not change orchestration.
import { PLANNING_PHASES } from "../../types";
import type { LifecycleNode } from "../../types";

// Phases that are NOT board columns but still need a human name.
//
// They are kept out of PLANNING_PHASES deliberately. That array does double duty — it is the
// label catalog AND the source of the Work Items board's columns (`lifecyclePhaseColumns`), so
// adding an entry to fix a NAME silently adds a COLUMN. These three are not places a work item
// sits: the two accessibility phases run on hidden carrier work items, and document vision
// belongs to project onboarding.
//
// Without them the lookup missed and the fallback below prettified the raw key — which is how
// `09c_a11y_judge` reached a client's screen as "A11y Judge" (2026-10-06). The fallback is
// right to exist and wrong to be relied on: it produces something plausible, so nobody notices.
const EXTRA_PHASE_LABELS: [string, string][] = [
  ["00e_document_vision", "Document Vision"],
  ["09c_a11y_judge", "Accessibility Judge"],
  ["09d_a11y_journey", "Keyboard Journey"],
];

const LABEL_BY_KEY = new Map<string, string>([
  ...PLANNING_PHASES.map((p) => [p.key, p.label] as [string, string]),
  ...EXTRA_PHASE_LABELS,
]);
// Also index by the bare (ordinal-stripped) name so a backend node label like "prd" or
// "ux_design" still resolves to the catalog's proper casing ("PRD", "UX Design") instead of
// the naive title-case fallback ("Prd", "Ux Design"). Bugs.xlsx: rail vs board disagreed.
const LABEL_BY_BARE = new Map<string, string>([
  ...PLANNING_PHASES.map((p) => [normalize(p.key), p.label] as [string, string]),
  ...EXTRA_PHASE_LABELS.map(([k, l]) => [normalize(k), l] as [string, string]),
]);

// Brownfield / project-onboarding phases (the 00_* group) — hidden from a work item's rail.
const BROWNFIELD_PHASE_KEYS = new Set([
  "00_onboarding",
  "00b_context_bridge",
  "00c_intelligent_context_extractor",
  // Added to the platform after this filter was written, and never registered here — so the one
  // onboarding phase nobody remembered appeared on every work item's rail (2026-10-06).
  "00e_document_vision",
]);

// Match either the raw key or the bare name, with or without the leading "NN[x]_" ordinal.
function normalize(phase: string): string {
  return phase.replace(/^\d+[a-z]?_/i, "");
}

export function isBrownfieldPhase(phase: string): boolean {
  if (BROWNFIELD_PHASE_KEYS.has(phase)) return true;
  const bare = normalize(phase);
  return ["onboarding", "context_bridge", "intelligent_context_extractor",
    "document_vision"].includes(bare);
}

// A clean, human-readable label for a phase key/name — no underscores, no ordinal prefix.
export function phaseLabel(phase: string | null | undefined): string {
  if (!phase) return "—";
  const known = LABEL_BY_KEY.get(phase) ?? LABEL_BY_BARE.get(normalize(phase));
  if (known) return known;
  return normalize(phase)
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// The human-readable name for an artifact (Bugs S.No 120): prefer the agent-authored `title`;
// fall back to a humanized `type` for artifacts registered before titles existed / singletons.
export function artifactLabel(
  title: string | null | undefined,
  type: string | null | undefined,
): string {
  const t = (title ?? "").trim();
  return t || phaseLabel(type);
}

// The nodes a work item's rail should actually show: brownfield/onboarding phases dropped,
// every label humanized.
export function visibleLifecycleNodes(nodes: LifecycleNode[]): LifecycleNode[] {
  return nodes
    .filter((n) => !isBrownfieldPhase(n.phase))
    .map((n) => ({ ...n, label: phaseLabel(n.label && n.label !== n.phase ? n.label : n.phase) }));
}

// The full lifecycle in SDLC order as board columns (Bugs.xlsx row 27.1): every non-brownfield
// phase from the catalog, humanized. Ordinal-labelled so the sequence reads at a glance.
export function lifecyclePhaseColumns(): { key: string; label: string }[] {
  return PLANNING_PHASES.filter((p) => !isBrownfieldPhase(p.key)).map((p, i) => ({
    key: p.key,
    label: `${i + 1}. ${p.label}`,
  }));
}

// Humanize a label that may embed a raw phase key (e.g. "04_architecture gate" -> "Architecture
// gate"). Left untouched when it has no underscore, so plain labels like "Needs answer" are safe.
export function humanizeLabel(text: string | null | undefined): string {
  if (!text) return "";
  if (!text.includes("_")) return text;
  return text
    .split(/\s+/)
    .map((tok) => (tok.includes("_") ? phaseLabel(tok) : tok))
    .join(" ");
}

// A human gate label from a gate type, e.g. "phase_gate" -> "Phase gate": one lowercase "gate",
// no underscores, never doubled. Callers must NOT append the word "gate" themselves — this
// returns the whole phrase. Bugs.xlsx rows 54/56/57/58 ("Phase Gate gate" / "phase_gate").
export function gateLabel(gateType: string | null | undefined): string {
  if (!gateType) return "Gate";
  const words = gateType.split(/[_\s]+/).filter(Boolean);
  const hasGate = words.length > 0 && words[words.length - 1].toLowerCase() === "gate";
  const base = (hasGate ? words.slice(0, -1) : words)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
  return base ? `${base} gate` : "Gate";
}

// Humanize a run/gate status token for display: underscores -> spaces, first word capitalized.
// "awaiting_gate" -> "Awaiting gate", "running" -> "Running". Bugs.xlsx rows 57/58.
export function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  const s = String(status).replace(/_/g, " ").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : "—";
}
