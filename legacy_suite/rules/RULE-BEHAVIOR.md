# RULE-BEHAVIOR.md — Pre-Execution Behavioral Rules

> **Authority:** This file defines the universal pre-execution behavioral contract for all phase agents (01–14).
> **Companion File:** `rules/RULE-EXECUTION.md` — read both files before any phase work begins.
> **Override Priority:** These rules take precedence over any individual agent's default behavior.
> **Mandatory:** Both rule files are pre-loaded via the CLAUDE.md preamble. Every agent applies all rules from the moment CLAUDE.md is read — no per-agent re-reading required.

---

## Rule 0 — Rules Are Pre-Loaded

Both rule files (`RULE-BEHAVIOR.md` and `RULE-EXECUTION.md`) are loaded via the mandatory preamble at the top of `CLAUDE.md`. Every phase agent begins execution with both rule files already applied. There is no need to re-read the rule files within an agent's context loading steps.

**Confirmation check:** Before executing any phase work, confirm internally: "Have I applied all rules from RULE-BEHAVIOR.md and RULE-EXECUTION.md?" If not — stop, read both files, then proceed.

---

## Rule 1 — Pre-Execution Context Gap Scan

Before executing **any** phase work, every agent must perform a structured gap scan across all inputs the phase requires.

### Step 1A — Inventory Required Inputs

List every piece of information your phase needs to produce accurate, non-hallucinated output. This includes information from CLAUDE.md, prior phase artifacts, the codebase, and any domain-specific knowledge the phase depends on.

### Step 1B — Classify Every Gap Into One of Three Tiers

For every piece of required information that is **missing or ambiguous** in the available context, classify it:

| Tier | Name | When to Use | Required Action |
|------|------|-------------|-----------------|
| **Tier 1** | MUST ASK | Business decisions, strategic choices, and user-specific knowledge that cannot be derived from any available context. These are impactful decisions where a wrong assumption causes rework downstream. | **STOP. Ask the user. Do not proceed without an answer.** |
| **Tier 2** | SUGGEST & CONFIRM | Information the user may not have a ready answer for, but where the agent can form an informed suggestion based on context or industry knowledge. | **Present the suggestion with rationale. Ask for confirmation or adjustment. Do not assume YES silently.** |
| **Tier 3** | HIGH-CONFIDENCE INFERENCE | Industry-standard conventions, universally accepted technical patterns, and facts that can be derived from the declared stack or context with very high certainty. Incorrect on < 5% of projects. | **Proceed, but log the inference explicitly in the Assumption Log.** |

### Step 1C — Front-Load ALL Questions Before Starting Work

Collect every Tier 1 and Tier 2 gap identified across the **entire phase** in a single scan. Present all questions together as one grouped block **before beginning any phase work**. Do not ask questions mid-execution.

**The only exception:** If an unexpected gap is discovered mid-execution that was not detectable from a cold scan of the context, see Rule 6 (RULE-EXECUTION.md) for the mid-phase protocol.

**Tier 1 Trigger List — always classify these as Tier 1, never infer:**
Competitors, target geography, business model, pricing and monetisation, compliance requirements, third-party integrations, KPI thresholds, team structure, budget constraints, feature priority decisions, release scope, security posture, deployment approvals, alerting thresholds, and any irreversible decisions.

---

## Rule 2 — Question Format

When questions must be presented to the user, use this format:

```
📋 CONTEXT GAP CHECK — [Phase Name]

Before I begin [phase description], I need your input on [N] item(s).
Context files available: [list what was read]. The following could not be determined from them.

── REQUIRED (Business Decisions) ──────────────────────────

1. [Clear, specific question — one information gap per question]
   Options:
   a) [Context-aware option derived from available info]
   b) [Alternative option]
   c) Other — please specify: ___

2. [Next question]
   Options:
   a) ...
   b) ...
   c) Other — please specify: ___

── SUGGESTIONS (Please confirm or adjust) ──────────────────

3. [Statement of the agent's suggestion]
   Reasoning: [One sentence explaining why this suggestion makes sense given available context]
   → Accept this suggestion? YES / NO
     If NO — please specify your preference: ___

────────────────────────────────────────────────────────────
Please answer all REQUIRED items. Suggestions can be accepted with a simple "yes" or adjusted with your answer.
I will not proceed until all REQUIRED items are answered.
```

**Rules for writing questions:**
- One question per information gap — never combine two gaps into one question
- Pre-populate options from available context
- For Tier 2 suggestions, always lead with the suggestion and reasoning
- Do not ask about information already explicitly present in any context file

---

## Rule 3 — Zero Hallucination Policy

**The agent MUST NOT:**
- Fabricate competitor names, market sizes, stakeholder names, pricing data, regulatory requirements, or any business-specific fact
- Assume a business or product decision has been made when it is not explicitly stated
- Present generic industry data as project-specific data without explicitly labelling it as a benchmark
- Silently proceed past any Tier 1 gap
- Use phrasing like "I'll assume..." or "Typically, teams choose..." to bypass a question that should be asked

**The agent MUST:**
- Anchor every factual claim to its source: CLAUDE.md, a specific phase artifact, the codebase, or a clearly labelled external benchmark
- Label all Tier 3 inferences inline and in the Assumption Log: `[Inferred: <statement> — based on <source/convention>]`
- Label industry benchmarks explicitly: `[Industry benchmark — not project-specific. Confirm with your team.]`
- When uncertain whether something is Tier 1 or Tier 3 — **default to Tier 1 and ask**

---

## Rule 7 — Context Source Hierarchy

When deriving any piece of information, always use the highest available source. Never skip a source level.

| Priority | Source | Trust Level |
|----------|--------|-------------|
| 1 | User's direct answer from this session's question block | Highest — use as-is |
| 2 | `CLAUDE.md` | Project source of truth |
| 3 | Phase artifacts from prior phases (`docs/ideation/`, `docs/requirements/`, etc.) | Approved and human-gated |
| 4 | Codebase (if exists — from Repowise or direct read) | Ground truth for existing systems |
| 5 | Industry standards and conventions | Tier 3 only — always labelled |
| 6 | Agent's internal knowledge | Tier 3 only — always labelled |

Never use Priority 5 or 6 as a substitute for Priority 1–4 on Tier 1 items.

---

## Rule 9 — What NOT to Ask

To avoid unnecessary friction, do NOT ask the user about:
- Information already explicitly present in any context file at any priority level
- Pure technical conventions with universal consensus and no business impact
- Details that will be determined by a downstream phase
- Cosmetic or stylistic choices with no downstream dependency
- Questions that another agent in a downstream phase will ask more appropriately

If in doubt: ask once, at the most relevant phase. Do not ask the same question twice across phases.

---

## Rule 10 — Missing Prerequisite Artifacts Protocol

When a required context directory or file is not found at the expected path, do NOT stop silently, skip the gap, or proceed without acknowledgment.

**Triggers:**
- **Scenario A:** Entire prerequisite phase directory is missing (phase was never run)
- **Scenario B:** Directory exists but expected files are absent or empty

Both trigger:

```
⚠️ MISSING PREREQUISITE CONTEXT — [Current Phase Name]

The following expected context was not found:
- [path/to/missing/directory or file] — [what it was expected to contain and why it matters]

This context was expected from [Phase X — Phase Name], which may not yet be complete.

How would you like to proceed?

1. Complete the prerequisite phase first
   → Run /sdlc:[command] and return here once all artifacts are approved.

2. Continue without it
   → I will treat all missing information as Tier 1 gaps in the Context Gap Scan (Rule 1).

Please reply with 1 or 2.
```

- If **Option 1:** Stop immediately. Confirm which command to run. Wait.
- If **Option 2:** Proceed to Rule 1 gap scan. All missing information classified as Tier 1. Do not infer.

Rule 10 and the Rule 1 gap scan operate together regardless of which option is chosen.

---

*This file governs how agents gather and validate information before any phase work begins.*
*Companion file: `rules/RULE-EXECUTION.md` — governs execution, logging, and phase completion.*
*Do not modify without team review. Changes affect all 14 phase agents.*
