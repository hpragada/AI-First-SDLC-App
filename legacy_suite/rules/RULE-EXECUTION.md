# RULE-EXECUTION.md — Execution, Logging & Phase Completion Rules

> **Authority:** This file defines the universal execution and phase completion contract for all phase agents (01–14).
> **Companion File:** `rules/RULE-BEHAVIOR.md` — read that file first, then this one.
> **Override Priority:** These rules take precedence over any individual agent's default behavior.
> **Mandatory:** Both rule files are pre-loaded via the CLAUDE.md preamble. Every agent applies all rules without re-reading. No exceptions.

---

## Rule 4 — Execution Protocol (Strict Order)

Every agent must follow this exact sequence:

```
Step 0   Rules pre-loaded via CLAUDE.md preamble — confirm both rule files are applied
Step 1   Read all available context files listed in Context Loading
Step 2   Perform the full gap scan
Step 3   IF Tier 1 or Tier 2 gaps exist → present question block → STOP and wait
Step 4   Wait for user answers
Step 5   Re-scan with answers incorporated
Step 6   Execute phase work
         → Use provided answers as highest-trust source
         → Log every Tier 3 inference in the Assumption Log
Step 7   Write Assumption Log to its dedicated file
Step 8   Perform all Post-Phase Writes
Step 8a  Perform Universal Write Completeness Scan
Step 8b  Apply Rule 12 — Derived Context Write-Back (scan CLAUDE.md for [TBD] values resolved this phase)
Step 9   Present the Human Gate → STOP and wait for APPROVED
Step 10  On APPROVED: write approval to CLAUDE.md Human Gates Log
Step 11  Surface the next phase command
```

If **no gaps exist** after Step 2 → proceed directly to Step 6 with:
> `"✅ Context Gap Check — No missing information detected. Proceeding with full phase execution."`

---

## Rule 5 — Assumption Log

Every Tier 3 inference made during a phase must be written to a **dedicated, phase-specific file** under `docs/assumptions/`. Never embed assumption logs inside deliverable artifacts.

### File Path Convention

| Phase Agent | Assumption Log File |
|-------------|---------------------|
| 01 — Ideation | `docs/assumptions/01-ideation-assumptions.md` |
| 02 — Requirements | `docs/assumptions/02-requirements-assumptions.md` |
| 03 — PRD | `docs/assumptions/03-prd-assumptions.md` |
| 04 — Architecture | `docs/assumptions/04-architecture-assumptions.md` |
| 05 — UX Design | `docs/assumptions/05-ux-design-assumptions.md` |
| 06 — Task Breakdown | `docs/assumptions/06-task-breakdown-assumptions.md` |
| 07 — Implementation | `docs/assumptions/07-implementation-assumptions.md` |
| 08 — Code Review | `docs/assumptions/08-code-review-assumptions.md` |
| 09 — Testing | `docs/assumptions/09-testing-assumptions.md` |
| 10 — Security | `docs/assumptions/10-security-assumptions.md` |
| 11 — CI/CD | `docs/assumptions/11-cicd-assumptions.md` |
| 12 — Deployment | `docs/assumptions/12-deployment-assumptions.md` |
| 13 — Monitoring | `docs/assumptions/13-monitoring-assumptions.md` |
| 14 — Retrospective | `docs/assumptions/14-retrospective-assumptions.md` |

### File Format

```markdown
# [Phase Name] — Assumption Log
**Phase:** [NN — Phase Name]
**Agent:** [agent filename]
**Generated:** [YYYY-MM-DD]
**Session:** [brief description]

---

## Tier 3 Inferences Made This Phase

| ID | Inference | Basis | Confidence | Must Validate Before Phase |
|----|-----------|-------|------------|---------------------------|
| A-[NN]-001 | [What was inferred] | [Exact source] | High | [Phase N] |

---

## Open Flags (Tier 2 — Unconfirmed Suggestions)

| Flag ID | Suggestion Made | Location in Artifact | Status |
|---------|----------------|----------------------|--------|
| F-[NN]-001 | [What was suggested] | [Section/file] | Pending confirmation |

---

## Resolution Log

| ID | Original Assumption | Resolution | Resolved By | Date |
|----|--------------------|-----------|-----------:|------|
| A-[NN]-001 | [original] | [confirmed / corrected to: X] | [name or phase] | [date] |
```

**If no inferences were made:** still create the file confirming zero inferences. A missing file is unambiguous evidence the phase skipped Rule 5.

**Writing order:** Assumption log is always written **after** all primary deliverable artifacts, as the final write before Post-Phase Writes.

---

## Rule 6 — Mid-Phase Unexpected Gap Protocol

If an unexpected gap is discovered **during execution** (after the front-loaded question block has already been answered):

- **Tier 1 gap mid-execution:** STOP at that section. Present a single follow-up question labelled `[MID-PHASE GAP — REQUIRED]`. Do not continue until answered.
- **Tier 2 gap mid-execution:** Provide the suggestion inline, flag with `⚠️ [TIER 2 — CONFIRM]:`. Continue but highlight for review at the Human Gate.
- **Tier 3 gap mid-execution:** Log it in `docs/assumptions/` and continue.

---

## Rule 8 — Human Gate Compliance

The Context Gap Scan and the Human Gate are independent requirements. Both are mandatory:

- **Context Gap Scan:** Runs at the start of the phase — ensures inputs are complete before work begins
- **Human Gate:** Runs at the end of the phase — ensures outputs are reviewed and approved before the next phase begins

Completing the gap scan does not constitute a Human Gate. Passing a Human Gate does not mean the gap scan was done.

---

## Rule 11 — Phase Completion & Artifact Synchronization Protocol

This rule governs everything that must happen **after phase execution is complete** and **before and after the Human Gate**. It ensures CLAUDE.md and cross-phase artifacts remain fully synchronized at all times and that no phase advances without explicit approval.

### Step A — Post-Phase Writes (Run BEFORE Presenting Human Gate)

After all primary artifacts are written and the Assumption Log is complete, the agent must perform the **Post-Phase Writes** defined in its Handoff section. These writes happen **before** the Human Gate is presented.

All Post-Phase Writes must be completed before the Human Gate is presented. The user reviews the gate knowing CLAUDE.md is already updated.

### Step A1 — Universal Post-Phase Write Completeness Scan (Run AFTER Step A, BEFORE Step B)

After completing all Post-Phase Writes defined in respective agent handoff section, perform this universal self-audit to detect **any additional files that require updating** based on the content actually produced in the current phase. This scan is phase-agnostic — it applies identically to every phase agent (01–14) and every track agent (15–17).

**The Core Question:** "Does the content I produced this phase imply any update I haven't made yet?"

Work through each check in order:

---

**Check 1 — CLAUDE.md Section Audit**

Read the current `CLAUDE.md`. For every section present in it, ask: *"Did the content I produced change any fact, value, or status tracked by this section?"* If YES → update accordingly and accurately before continuing.

---

**Check 2 — Cross-Phase Artifact Audit**

For each cross-phase artifact that are produced during the current phase agent execution or previous phase agent executions, ask: *"Does the work I did this phase add, change, or resolve information tracked in this artifact or any of the previous artifacts produced?"* If YES → update accordingly and accurately before continuing.

> **Illustrative Examples — Adapt accordingly**

| Artifact | Update Trigger |
|----------|----------------|
| `docs/requirements/TRACEABILITY-MATRIX.md` | Any requirement implemented, tested, or verified — fill the corresponding matrix cell |
| `docs/planning/TASKS.md` | Any task status changed (Pending → In Progress → Done), or acceptance criteria updated |
| `docs/design/adrs/ADR-NNN.md` | Any new architectural decision made during this phase, even if outside Phase 4 |
| `docs/ops/DEPLOYMENT-LOG.md` | Any deployment action taken this phase |
| `docs/retros/` | Any action item from a previous retrospective resolved as a side-effect of this phase |

---

**Completeness Check Output:**

Before proceeding to Step B, output this one-line summary inline — it is informational only and does not require a human response:

```
📋 Write Completeness Scan — [N additional update(s) applied / no additional updates detected]
   [If updates applied: list them concisely — e.g., "CLAUDE.md → Open Questions updated; TRACEABILITY-MATRIX.md → TC-007 filled"]
📋 Derived Context Write-Back (Rule 12) — [N CLAUDE.md [TBD] values resolved and written back / none]
   [If written back: list them — e.g., "Technology Stack → Cloud Provider → AWS; Key Commands → backend dev server → python manage.py runserver"]
```

---

### Step B — Present the Human Gate (Standardized Format)

After all Post-Phase Writes are complete, present the Human Gate using this exact structure:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  HUMAN GATE — Phase [N]: [Phase Name]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ ARTIFACTS PRODUCED:
  - [file path] — [one-line description]
  - [file path] — [one-line description]

✅ CLAUDE.md & CROSS-PHASE FILES UPDATED:
  - CLAUDE.md → Current Phase: updated to "[Next Phase Name]"
  - CLAUDE.md → Phase Artifacts Index: Phase [N] marked ✅ Complete
  - [any other specific updates made]

✅ DERIVED CONTEXT WRITTEN BACK (Rule 12):
  - [CLAUDE.md section → field → value written] — or "None this phase"

📋 PLEASE REVIEW BEFORE APPROVING:
  - [ ] [specific, verifiable review item]
  - [ ] [specific, verifiable review item]
  - [ ] [specific, verifiable review item]

─────────────────────────────────────────────────────────────
Reply APPROVED to log approval and surface the next phase command.
Reply with specific change details to trigger re-execution of only the
affected artifact(s) — the gate will re-present after correction.
⛔  The next phase command will NOT surface until APPROVED is received.
─────────────────────────────────────────────────────────────
```

### Step C — STOP. Wait for APPROVED.

The agent must not surface the next phase command under any circumstances until the user explicitly replies with `APPROVED` or `approved`. Any other response — including "looks good", "yes", "ok" — must be treated as a change request unless the user has clearly indicated approval.

### Step D — On Change Request (Not APPROVED)

If the user describes changes needed instead of replying APPROVED:
1. Acknowledge the specific change(s) requested
2. Re-execute **only** the affected artifact(s) — do not re-run the entire phase
3. Update the affected file(s) on disk
4. Re-present the full Human Gate block (Step B) with a note that the change was applied
5. Wait for APPROVED again

### Step E — On APPROVED: Write to Human Gates Log, Then Surface Next Command

Immediately upon receiving APPROVED:

1. Append to `CLAUDE.md → Human Gates Log`:

```
| Phase [N] — [Phase Name] | ✅ Approved | [Approved By — ask if not provided, default to "Stakeholder"] | [YYYY-MM-DD] | [any condition stated, or "None"] |
```

2. Output the next phase command:

```
✅ Phase [N] — [Phase Name] approved and logged.

Run the next phase:
/sdlc:[next-command]
```

### Rule 11 — for Phase 7 (Implementation)

Phase 7 is iterative. This applies at **sprint completion**, not after every task:
- Individual task gates (session-start and task-completion gates) operate as defined in the agent
- At the end of each **sprint** (all sprint tasks Done): perform Post-Phase Writes for that sprint and present a Sprint Completion Human Gate
- CLAUDE.md Phase Artifacts Index Row 7 is updated at each sprint completion with progress status
- When ALL tasks across ALL sprints are complete: update Row 7 to ✅ Complete and run the full Human Gate before surfacing `/sdlc:code-review`

---

## Rule 12 — Derived Context Write-Back Protocol

Whenever an agent determines, confirms, or fills in information that was blank, `[TBD]`, or a placeholder in `CLAUDE.md` during a phase (whether as a Tier 3 inference, a direct phase output, or a stakeholder-answered Tier 1 item), the agent **MUST** write that resolved information back to `CLAUDE.md` before presenting the Human Gate.

**This rule fires during Step 8b of the Execution Protocol and is verified by Rule 11 Step A1 Check 1.**

### Trigger Conditions

- A **Technology Stack** row that was `[TBD]` has been determined (e.g., Architecture Agent selects the cloud provider, cache layer, or email service)
- A **Key Commands** placeholder `[TBD]` has been confirmed during architecture or implementation
- A **Non-Functional Requirements** Target column value was derived from requirements elicitation
- A **Repository Structure** placeholder has been resolved during Architecture
- A **Coding Standards** entry was `[TBD]` and is now determined
- **Constraints** — a previously unknown budget, timeline, or compliance requirement was surfaced and confirmed
- Any other `CLAUDE.md` section containing `[TBD]` or a placeholder where the current phase produced the answer

### Write-Back Format

When writing back a derived value to the Technology Stack table or similar flat tables, annotate the Notes column:

```
| Cloud Provider | AWS | — | Determined by Architecture Agent — Phase 4 |
| Email Service | SendGrid | Latest | Determined by Architecture Agent — Phase 4 |
| Cache | Redis | 7.x | Determined by Architecture Agent — Phase 4 |
```

For other sections (Key Commands, Repository Structure, Coding Standards), replace the `[TBD]` placeholder with the determined value and append a parenthetical note:
```
# Run dev server
python manage.py runserver  ← (Determined by Architecture Agent — Phase 4)
```

### Non-Negotiable

**The agent must not present the Human Gate until all derivable `[TBD]` entries in CLAUDE.md — entries for which the current phase produced the answer — have been resolved and written back.**

A `[TBD]` that cannot be resolved by the current phase must remain as `[TBD — Determined by [Agent] — Phase [N]]` so downstream agents know which phase will resolve it.

---

*This file governs how agents execute, log, and close out phases.*
*Companion file: `rules/RULE-BEHAVIOR.md` — governs pre-execution information gathering.*
*Do not modify without team review. Changes affect all 14 phase agents.*
