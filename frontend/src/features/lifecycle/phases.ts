// Human-readable phase names + brownfield-phase visibility for the work-item lifecycle.
// Bugs.xlsx row 21: phase names must never show raw (e.g. "task_breakdown" or "06_task_breakdown"),
// and the brownfield-only onboarding phases must not appear on a work item's lifecycle rail
// (they belong to project onboarding, not per-work-item flow). This is a UI-only concern —
// it filters/relabels what the rail shows; it does not change orchestration.
import { PLANNING_PHASES } from "../../types";
import type { LifecycleNode } from "../../types";

const LABEL_BY_KEY = new Map(PLANNING_PHASES.map((p) => [p.key, p.label]));

// Brownfield / project-onboarding phases (the 00_* group) — hidden from a work item's rail.
const BROWNFIELD_PHASE_KEYS = new Set([
  "00_onboarding",
  "00b_context_bridge",
  "00c_intelligent_context_extractor",
]);

// Match either the raw key or the bare name, with or without the leading "NN[x]_" ordinal.
function normalize(phase: string): string {
  return phase.replace(/^\d+[a-z]?_/i, "");
}

export function isBrownfieldPhase(phase: string): boolean {
  if (BROWNFIELD_PHASE_KEYS.has(phase)) return true;
  const bare = normalize(phase);
  return ["onboarding", "context_bridge", "intelligent_context_extractor"].includes(bare);
}

// A clean, human-readable label for a phase key/name — no underscores, no ordinal prefix.
export function phaseLabel(phase: string | null | undefined): string {
  if (!phase) return "—";
  const known = LABEL_BY_KEY.get(phase);
  if (known) return known;
  return normalize(phase)
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// The nodes a work item's rail should actually show: brownfield/onboarding phases dropped,
// every label humanized.
export function visibleLifecycleNodes(nodes: LifecycleNode[]): LifecycleNode[] {
  return nodes
    .filter((n) => !isBrownfieldPhase(n.phase))
    .map((n) => ({ ...n, label: phaseLabel(n.label && n.label !== n.phase ? n.label : n.phase) }));
}
