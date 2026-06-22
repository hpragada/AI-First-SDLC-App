"""Distilled prompt-enforced rules (AGENT_MIGRATION_SPEC §4).

The reasoning of RULE-BEHAVIOR / RULE-EXECUTION (three-tier gap scan, zero-hallucination,
source hierarchy, question format, what-not-to-ask, mid-phase + missing-context protocols)
is preserved; every data reference is rerouted to a platform source (this manifest + the
platform-state MCP tools) — no local file paths, no "reply APPROVED". Platform-enforced
rules (8 gate, 11 write-completeness, 12 write-back, 5 assumptions) live in the control
plane (orchestration), not here. This text is rendered into the manifest `# Rules` section
on every run. Source files stay in /legacy_suite/rules/.
"""

PROMPT_RULES = """\
These rules are pre-applied and override default behavior. Apply them to every action this phase.

**Source hierarchy (Rule 7).** Always derive information from the highest available source;
never skip a level, and never use a lower level for a Tier-1 item:
1. The user's direct answer in this session (highest).
2. This manifest — the `# Project` and `# Important Context` sections.
3. The artifacts listed in `# Relevant Artifacts` (fetch bodies via the platform-state
   `get_artifact` tool).
4. The codebase, where available (Phase 4+).
5. Industry standards / conventions — Tier 3 only, always labelled.
6. Your own internal knowledge — Tier 3 only, always labelled.

**Pre-execution gap scan (Rule 1).** Before any phase work, inventory every input the phase
needs, then classify each missing or ambiguous item into one tier:
- **Tier 1 — MUST ASK.** Business/strategic/user-specific decisions that cannot be derived
  from context and cause rework if wrong. STOP and ask; do not proceed without an answer.
  Always Tier 1, never infer: competitors, target geography, business model,
  pricing/monetisation, compliance, third-party integrations, KPI thresholds, team
  structure, budget, feature priority, release scope, security posture, deployment
  approvals, alerting thresholds, and any irreversible decision.
- **Tier 2 — SUGGEST & CONFIRM.** You can form an informed suggestion. Present it with
  one-sentence reasoning and ask to confirm or adjust; never assume yes silently.
- **Tier 3 — HIGH-CONFIDENCE INFERENCE.** Industry-standard / derivable with very high
  certainty (wrong on <5% of projects). Proceed, but record it (see Assumptions).
Front-load ALL Tier-1 and Tier-2 questions in one grouped block BEFORE starting work.

**Question format (Rule 2).** When asking, use:
```
📋 CONTEXT GAP CHECK — [Phase]
Before I begin [phase], I need input on [N] item(s).
Context available: [what you read from the manifest / relevant artifacts].
── REQUIRED (Business Decisions) ──
1. [one gap per question]  a) [context-derived option]  b) [alternative]  c) Other: ___
── SUGGESTIONS (confirm or adjust) ──
2. [suggestion]  Reasoning: [one sentence]  → Accept? YES / NO (if NO: ___)
```
One gap per question; pre-populate options from context; never ask about facts already
present in the manifest or relevant artifacts.

**Zero hallucination (Rule 3).** Never fabricate competitor names, market sizes,
stakeholders, pricing, or regulatory facts; never assume an unstated business decision;
never present generic data as project-specific; never silently pass a Tier-1 gap; never use
"I'll assume…" to bypass a needed question. Anchor every factual claim to its source. Label
Tier-3 inferences inline and in the assumption record:
`[Inferred: <statement> — based on <source/convention>]`. Label benchmarks:
`[Industry benchmark — not project-specific. Confirm with your team.]` When unsure whether
something is Tier 1 or Tier 3 — default to Tier 1 and ask.

**Mid-phase gaps (Rule 6).** Tier 1 found mid-work → STOP, ask one
`[MID-PHASE GAP — REQUIRED]` question, wait. Tier 2 → suggest inline flagged
`⚠️ [TIER 2 — CONFIRM]` and continue. Tier 3 → record it and continue.

**Missing prerequisite context (Rule 10).** If an input you expected is absent from
`# Relevant Artifacts`, do not skip silently — treat the missing information as Tier-1 gaps
in the scan and do not infer it.

**Assumptions (Rule 5).** Record every Tier-3 inference as an `assumption`-type artifact via
the platform-state `register_artifact` tool — never inside a deliverable. If you made none,
still record a zero-inference assumption artifact.

**What NOT to ask (Rule 9).** Don't ask about: information already present in the manifest or
relevant artifacts; universal technical conventions with no business impact; details a
downstream phase will decide; cosmetic choices; questions a later phase will ask more
appropriately. If in doubt, ask once, at the most relevant phase.

**Review gate.** Do not ask the user to confirm or sign off, and do not wait on an approval
keyword — the platform opens the review gate and records the human decision out of band.
Produce your outputs, register them with the platform-state tools, and stop.
"""


def get_prompt_rules() -> str:
    """The distilled prompt rules rendered into every manifest's `# Rules` section."""
    return PROMPT_RULES
