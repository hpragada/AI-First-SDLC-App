/**
 * Where a link goes — one module, so the app stops guessing.
 *
 * **A link's text is a promise.** If the id of the thing promised is in hand, link to its DETAIL
 * route. If only a SCOPE is in hand (a run, a work item, a phase, a type), link to the LIST route
 * carrying that scope as a query param, and the list must honour it. Never link to a bare list
 * from text that names one thing.
 *
 * Across this app that promise was routinely broken: the text named one artifact and the link
 * opened the whole registry, so the user re-found by hand what they had just been looking at. It
 * is not a new requirement either — the team's own UX spec already says gates carry "a link to
 * preview the artifact under review" (J19) and that a traceability node deep-links. The preview
 * endpoint was built and signed off; the link to it never was.
 *
 * Pure functions, no React, modelled on `features/lifecycle/phases.ts`. Query strings are built
 * with `createSearchParams` rather than template concatenation, so a reserved character in an id
 * or a phase label cannot produce a malformed URL.
 */
import { createSearchParams } from "react-router-dom";

function withParams(path: string, params: Record<string, string>): string {
  const qs = createSearchParams(params).toString();
  return qs ? `${path}?${qs}` : path;
}

// ── detail routes: we have the id of the exact thing ──────────────────────
export const artifactLink = (id: string) => `/artifacts/${encodeURIComponent(id)}`;
export const artifactPublishLink = (id: string) => `${artifactLink(id)}/publish`;
export const runLink = (id: string) => `/runs/${encodeURIComponent(id)}`;
export const workItemLink = (id: string) => `/work-items/${encodeURIComponent(id)}`;
export const workItemBreakdownLink = (id: string) => `${workItemLink(id)}/breakdown`;
export const workItemTestCasesLink = (id: string) => `${workItemLink(id)}/test-cases`;
export const a11yFindingLink = (findingId: string) =>
  `/a11y/finding/${encodeURIComponent(findingId)}`;
export const transcriptLink = (runId: string) => `/transcripts/${encodeURIComponent(runId)}`;

// ── selection routes: a list screen that must open on one row ─────────────
// These stay list screens on purpose. The Gates screen holds the selection state and every
// phase-specific panel (merge-conflict banner, repo-assignment review); a separate detail screen
// would mean extracting that JSX and would create a THIRD gate-decision UI — `CriteriaGate` is
// already a second, partial one — which is exactly the drift this module exists to remove. It
// also keeps the master-detail layout, which is not noise: a reviewer with five pending gates
// wants to see the other four.
export const gateLink = (approvalId: string) => withParams("/gates", { gate: approvalId });
export const clarificationLink = (clarificationId: string) =>
  withParams("/clarifications", { clarification: clarificationId });
export const a11yFindingInReviewLink = (findingId: string) =>
  withParams("/a11y", { finding: findingId });

// ── scope routes: we have a scope, not an id ──────────────────────────────
/** Everything ONE RUN produced. This is how a gate reaches "the artifact under review" without
 *  the platform having to invent a notion of a run's *primary* artifact — a UX Design run
 *  registers several wireframes, and a "pick the first" rule would be a new lie in place of the
 *  old one. */
export const artifactsForRun = (runId: string) => withParams("/artifacts", { run: runId });

/** Every question still waiting for an answer on ONE work item. The "At a glance" card counts
 *  them; without this there was nowhere for that count to lead, so it was the one number on the
 *  card that could not be acted on. The screen narrows its PENDING list only — a history
 *  narrowed by a filter you cannot see is the more dangerous of the two. */
export const clarificationsForWorkItem = (workItemId: string) =>
  withParams("/clarifications", { work_item: workItemId });

/** Everything a PHASE produced.
 *
 *  **`phaseLabel` must be the phase LABEL, never an agent key.** `Artifact.phase` stores the
 *  catalog's label (`task_breakdown`, `context_extraction`); `Approval.phase` returns the agent
 *  KEY (`06_task_breakdown`, `00c_intelligent_context_extractor`). Passing a key here returns
 *  zero rows — a silent empty list, which is worse than the wrong-but-populated list this
 *  replaces. Two `string`s are indistinguishable to the type system, so this name and this
 *  comment are the guard. Use `approval.phase_label`, or `p.label` from `GET /api/phases/`. */
export const artifactsForPhase = (phaseLabel: string) =>
  withParams("/artifacts", { phase: phaseLabel });

export const artifactsOfType = (type: string) => withParams("/artifacts", { type });

/** Everything produced FOR one work item. An artifact has no direct work-item FK — the backend
 *  reaches it through `run__work_item_id` — which is exactly why this belongs in one place
 *  rather than being re-derived at each call site. */
export const artifactsForWorkItem = (workItemId: string) =>
  withParams("/artifacts", { work_item: workItemId });
export const runsForWorkItem = (workItemId: string) =>
  withParams("/runs", { work_item: workItemId });

/** The offline-takeover screen, focused on one parked run. `OfflineTakeover` has read `?run=`
 *  all along; nothing in the app ever produced the URL. */
export const recoveryLink = (runId: string) => withParams("/recovery", { run: runId });
