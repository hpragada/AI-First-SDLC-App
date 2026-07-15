# AGENT_MIGRATION_SPEC.md — How the existing SDLC suite becomes the platform's intelligence

> **This answers: "How does Claude Code know how to use our agents, commands, and rules to build the system?"**
> The legacy v6 suite (in `/legacy_suite/`) is the **source intelligence** of the product. Claude Code does **not** invent agent logic — it **migrates** these files. This spec is the authoritative transformation guide. Read it before any agent-migration task.

> **Source of truth:** `/legacy_suite/` contains the v6 suite verbatim — 17 agents, 17 commands, 2 rules, the original `CLAUDE.md`, `settings.json`. (Confirm these are your latest v6 before migrating; swap in newer copies if the team has them.)

---

## 0. The two CLAUDE.md files (avoid confusion)
- **`/CLAUDE.md` (repo root)** — guides Claude Code while it *builds the platform*. Not migrated; it's build instructions.
- **`/legacy_suite/CLAUDE.md`** — was the *runtime context source* the old agents read. In the product this becomes the **Project Profile (DB record) + Composed Manifest (rendered per run → AGENTS.md)**. Migrate its *structure* (what fields it held) into the ProjectProfile model + Manifest Composer, not into a file.

---

## 1. What every agent contains (the universal skeleton)
Every legacy agent follows the same shape. Open any (e.g. `/legacy_suite/agents/03_prd_agent.md`) and you will see:
1. **YAML frontmatter** — name, description, tools, model.
2. **Role** — persona + **Evidence Base** (academic citations).
3. **Context Loading** — the *declared* inputs (currently local files / CLAUDE.md). **Note:** additional reads/writes are also embedded **inside Process steps** — those count too (see §2–§3).
4. **(optional) Step 0** — scope/tool confirmation gate.
5. **Process steps** — each using the **three-part teaching pattern**: *Framework callout (blockquote) → How-to execution → Failure-mode warning.*
6. **Output / "Write These Files"** — what it writes (currently local files).
7. **Quality Gate** — completion checks.
8. **Assumption Log** — `docs/assumptions/NN-*.md`.
9. **Post-Phase Writes table** — what it persists + writes back to CLAUDE.md.
10. **Human Gate** — currently "reply APPROVED".
11. **On-APPROVED block** — what happens next.

## 2. The reuse / rewrite rule — the 75 / 15 / 10 buckets, redefined (read this twice)

> **Critical clarification (do not skip).** The three buckets below are about the **kind of content**, NOT about *where in the file* it sits. The **15% REWRITE bucket is threaded throughout the agent — including inside Process steps** — it is *not* two bookend sections. "Verbatim" (the 75%) protects **reasoning**; it never protects a data reference. A migrated agent that still names a local file (`tasks.md`, `requirements.md`, `docs/...`) anywhere — frontmatter to last line — is a **FAILED migration** that breaks at runtime.

- **REUSE VERBATIM (~75%) — the REASONING.** Role, persona, Evidence Base, all framework callouts, how-to guidance, failure-mode warnings, decomposition logic, quality criteria, domain expertise, the three-part teaching pattern, the Quality Gate and assumption logic. This is the hard-won intelligence — **do not paraphrase, summarize, re-order, or "improve" it.** It becomes the agent's system-prompt body in `/agents/<key>/agent.md`. *Example (task-breakdown): "decompose each story into vertically-sliced tasks with explicit acceptance criteria; reject horizontal-slice anti-patterns" — stays exactly as written.*

- **REWRITE (~15%) — the DATA REFERENCES, wherever they appear (incl. mid-Process-step).** Every place the agent says *where* it reads an input or *where* it writes an output — a file path, a `read`/`write`, a `CLAUDE.md`/`docs/` mention, "the next task from `tasks.md`", "the user stories in `requirements.md`" — is rerouted to a platform source-of-truth via the §3 mapping. **This 15% is NOT a "Context Loading" header plus a "Post-Phase Writes" footer — it is scattered through the body. Follow the references into the Process steps.** *(Within a step: keep the verb and the judgment as 75%-verbatim; replace only the input-source and output-destination as 15%-rewrite.)*

- **REPLACE (~10%) — INVOCATION GLUE.** Frontmatter `tools`/`model` → AgentSpec metadata; the command file → a phase trigger (UI/API); the Human Gate text → control-plane Approval.

> The ~75 / ~15 / ~10 figures estimate **volume** (most words are reasoning), not **position**. Never read them as "the top and bottom are the 15% and the middle is the frozen 75%." The 15% (references) and the 75% (reasoning) are interleaved — often inside the very same sentence.

## 3. The data-reference rewrite — apply to EVERY reference, anywhere in the agent

There is no fixed "Context Loading section" to edit and stop. Sweep the whole agent and reroute **every** input/output reference using this canonical mapping. Same table for all 17 agents; no inventing targets.

| Legacy reference (may appear ANYWHERE, incl. mid-Process-step) | Rewrite to |
|---|---|
| reads a prior-phase doc — `requirements.md`, `prd.md`, `architecture.md`, user journeys/stories, ADRs | `platform-state.get_context(...)` (already in the manifest) or `get_artifact(artifact_id)` for the specific input |
| "read the next task / the task from `tasks.md`" | the **WorkItem / issue key passed into the run**; fetch via `tasktracker.get_issue(key)` (Phase 1+) or `get_work_item(id)` |
| "the current design / screens" | `designsource.get_design_context()` + `get_variable_defs()` — the **current** Figma (Phase 3) |
| reads the codebase / repo | the **companion worktree** (the Phase-2 local-companion build runner's working tree) + `codeintel.*` (Repowise) where applicable |
| writes a doc — `prd.md`, `tasks.md`, test cases, review notes, etc. | write body to S3 (draft) → `register_artifact(type, sor, s3_key, content_hash, title)` → `add_trace_edge(input→output, rel)` → `log_event(...)`. **Always pass a human-readable `title`** — a short, context-carrying name a person can tell apart from its siblings (e.g. `"Wireframe — Login Page"`, `"ADR-003 — Event Sourcing"`, `"TC-014 — Login rejects a bad password"`). A bare `type` is not enough when a phase registers several of the same type; the `title` is what every UI surface displays and how the platform distinguishes per-item artifacts (Bugs S.No 120). |
| creates epics/stories/sprints | `tasktracker.create_*` (Jira, Phase 1) + `register_artifact` |
| publishes a doc/page | `docstore.create_page/update_page` (Confluence, Phase 1) on **gate APPROVED only** |
| "update `CLAUDE.md`" / write-back to project context | `register_artifact` + `log_event` (the registry/ledger ARE the project context now) |
| assumption log `docs/assumptions/NN-*.md` | an `assumption`-type artifact via `register_artifact` |
| Human Gate ("reply APPROVED") | **remove** — the Temporal workflow opens a control-plane `Approval(required_role)` |

**Rule of thumb for Claude Code:** *if a step's reasoning says "look at X" or "produce Y," keep the reasoning word-for-word and replace only the X-source and Y-destination with the platform equivalent above.* The verb and the judgment stay; the location changes.

### Worked examples — reasoning frozen, reference rerouted (mid-step)

**06 Task Breakdown — a Process step:**
- *Before:* "For each user story in `requirements.md`, decompose into vertically-sliced tasks with acceptance criteria… write the resulting tasks to `tasks.md`."
- *After:* "For each user story **[from `get_context()` / the requirements artifact]**, decompose into vertically-sliced tasks with acceptance criteria… **[create the tasks via `tasktracker.create_story/subtask` and `register_artifact`]**." — the decomposition logic and anti-pattern warnings are untouched; only the source and sink moved.

**07 Implementation — a Process step:**
- *Before:* "Read the next task from `tasks.md`, implement it, mark it complete in `tasks.md`."
- *After:* "**[Take the WorkItem/issue key passed into this run; fetch it via `tasktracker.get_issue(key)`]**, implement it **[in the companion worktree]**, **[`register_artifact` the code pointer + `log_event`]**." — "implement it" and all the how-to/quality guidance around it stay verbatim. **The agent never calls GitHub directly (Phase-2 D2):** the platform/companion commits, pushes the branch, and opens the PR via `codehost.*`; the merge is gate-only.

These two are just illustrations. **The reference sweep (§8) applies the same treatment to every agent** — 04 reading the PRD, 09 reading acceptance criteria, 10 reading the codebase + dependencies, 08 reading the PR diff, and so on.

## 4. How the RULES migrate (RULE-BEHAVIOR.md + RULE-EXECUTION.md)
The rules split into two destinations:
- **Prompt-enforced rules → Manifest `# Rules` section.** The reasoning rules (Rule 0 pre-load, Rule 1 three-tier gap scan, Rule 2 question format, Rule 3 zero-hallucination, Rule 7 source hierarchy, Rule 9 what-not-to-ask) are distilled into the manifest every run so the agent obeys them.
- **Platform-enforced rules → control-plane logic, not prompt.** Rule 8 gate compliance → the Approval/Temporal gate. Rule 11 phase-completion + Universal Write Completeness Scan → a workflow post-step that verifies all expected `register_artifact` calls happened. Rule 12 derived-context write-back → automatic (every run writes to registry/ledger). Rule 5 assumption log → an `assumption`-type artifact registered like any other.

**Deliverable:** a `rules/` module in `backend/manifest/` holding the distilled prompt-rules text, plus the enforcement hooks in `orchestration/`. The original rule files stay in `/legacy_suite/rules/` as the source.

## 5. How the COMMANDS migrate (17 command files + settings.json)
Legacy `commands/*.md` (e.g. `implement.md`) just point Claude Code at an agent. In the platform there are no slash commands — **a command becomes a phase trigger**:
- Each command → an **AgentSpec** row + a **UI/API action** that creates/advances a WorkItem and starts the agent's Temporal run.
- `settings.json` (agent/command registry, model mappings) → **seed data** for the AgentSpec Registry + tenant/engine config. Migrate the *mappings*, not the file.
- **Fix during migration** (known v6 inconsistencies): `security.md`→`10-security-agent.md` (hyphen), `prd.md`→`03_prd_agent.md` (underscore), the `cicd` settings pointer, agent 10's hyphen naming, 09b's pinned model string, mixed line endings. Normalize all agent keys to a single convention (recommend `NN_name`).

## 6. Advanced flows — preserve these behaviors
- **07 Implementation ↔ 08 Code Review (Remediation loop):** REM-C/REM-W items become WorkItem sub-tasks + TraceEdges; the loop is modeled as the workflow re-running 07 with a remediation manifest until 08 passes. Preserve the loop logic from the agent bodies.
- **09 Testing → 09b Test Automation:** TC-XXX specs become test artifacts; 09b's Playwright-MCP locator discovery + Page Object Model logic is preserved; results flow to Xray (Phase 3).
- **00c Intelligent Context Extractor (Repowise, MCP :7337, 8 tools):** becomes the CodeIntel connector + onboarding (Phase 4). Client-facing name stays "Intelligent Context Extractor".
- **00b Context Bridge:** its job (share cross-repo API contract) becomes the **API-Contract artifact** in the registry (Phase 4) — not a copied file.
- **00d Context Snapshot:** session continuity is now the platform DB + Temporal resumable runs; **00d is largely retired** — migrate only any unique reconciliation logic, otherwise mark obsolete.

## 7. Agent → Phase → Work mapping (the migration schedule)
Each agent is migrated in the phase where its dependencies (SoR, runner, connector) exist. The **reasoning** is ready now; the **data references** (which may sit anywhere in the body — see §2–§3) are rerouted to the targets below as each phase's connectors come online.

| Agent | Migrate in | Reads (after) | Writes (after) | Gate role |
|---|---|---|---|---|
| 01 Ideation | **P0** | get_context | ideation artifact (internal) | product_owner |
| 02 Requirements | **P0** | get_context | requirements artifact | product_owner |
| 03 PRD | **P0** | requirements | prd artifact | product_owner |
| 04 Architecture | **P0** | prd | architecture/ADR artifact | architect |
| 06 Task Breakdown | **P1** | prd, architecture | epics/stories → **Jira** | tech_lead |
| (onboarding-lite) | **P1** | static files / Atlassian | registered/internal artifacts | product_owner |
| 07 Implementation | **P2** | story (Jira), design | code (companion worktree) → **PR (GitHub)** | tech_lead |
| 08 Code Review | **P2** | PR diff | review + remediation items | reviewer |
| 11 CI/CD | **P2** | repo | pipeline config | devops |
| 12 Deployment | **P2** | build | deployment + release artifact | devops |
| 05 UX Design | **P3** | prd, requirements | screens → **Figma** / wireframes | designer |
| 09 Testing | **P3** | prd, code | test cases → **Xray** | qa_lead |
| 09b Test Automation | **P3** | test cases | automated tests + results | qa_lead |
| 10 Security | **P3** | code, deps | security findings + SBOM | security_engineer |
| 00c Intelligence | **P4** | repo(s) | code-intel + Knowledge Index | tech_lead |
| 00 Onboarding (full) | **P4** | all SoRs + intel | registered artifacts + gap report | product_owner |
| 00b Context Bridge | **P4** | repos | API-Contract artifact | architect |
| 00d Snapshot | **P4** | — | (mostly retired) | — |
| 13 Monitoring | **P6** | *(build new — never existed)* | monitoring artifacts | devops |
| 14 Retrospective | **P6** | *(build new — never existed)* | retro artifacts | tech_lead |

> 10 Security placement and 11/12 (CI/CD, Deployment) are the two adjustable judgment calls — move security to P2 if you want security gating before merge; move 11/12 to a dedicated deploy phase if preferred. Everything else is dependency-locked.

## 8. Per-agent migration checklist (apply to each)
1. Copy the legacy body; keep all **reasoning** (Role/Evidence/Process how-to/teaching pattern/Quality-Gate) **verbatim**.
2. **REFERENCE SWEEP (mandatory, hard gate).** Scan the **entire** body top to bottom — frontmatter, every Process step, outputs, assumption log, gate. For **every** input/output reference (every file path, every `read`/`write`, every `tasks.md`/`requirements.md`/`docs/`/`CLAUDE.md` mention, every "the current X"), reroute it via the §3 table. **Reasoning stays word-for-word; only the source/destination changes.**
3. **Verify the sweep:** `grep` the migrated `/agents/<key>/agent.md` for `.md`, `docs/`, `tasks.md`, `CLAUDE.md`, "reply APPROVED". **Any hit = FAILED migration → fix before saving.** (Allowed exception: prose that references the platform, not a local file.)
4. Strip the Human Gate text (gate handled by the workflow).
5. Save to `/agents/<key>/agent.md`; create the `AgentSpec` (key, semver=1.0.0, prompt_version, body_ref, recommended_engine=claude, recommended_model, phase_label).
6. Register the phase trigger (UI/API) replacing its command file.
7. Write a test: a run composes a manifest, executes, reads its inputs **from the platform** (not a file), registers the expected artifact(s), and opens the correct gate.
8. Tick the agent's box in `BUILD_PLAN.md`.
