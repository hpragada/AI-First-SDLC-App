# Truncation — full issue register, team decisions, and recommended fixes

**Status:** analysis + decisions recorded. **No code has been changed.** The team will choose
which items to implement and in what order.

**Date:** 2026-08-04
**Raised by:** a `Manifest truncated — implementation` line on the run console during the first
end-to-end brownfield implementation test.
**Scope:** every place in the platform where content is shortened before it reaches an agent or a
human reviewer — not only the Manifest Composer.

---

## 1. How this was measured

Everything below is measured, not estimated. The evidence run:

- Tenant `9f29e6f9-81b9-405b-8110-96383469d980`, project `SpendLog-Brownfield-Testing`
- Run `6a7ae08e-618f-4312-86b6-0d2737f4620c` — TASK-022 (WI-19 / ST-436), agent 07 implementation
- Recorded events:
  - `10:54:18 manifest.truncated {'phase': 'implementation', 'sections': ['Retrieved Knowledge']}`
  - `11:12:35 manifest.truncated {'phase': 'code_review', 'sections': ['Retrieved Knowledge']}`

The manifest was re-composed offline with the same inputs and each section measured:

| Section | Tokens used | Cap | Cut? |
|---|---|---|---|
| Project | 31 | 2000 | |
| Important Context | 7 | 2000 | |
| Current Work Item | 366 | 650 | |
| Relevant Artifacts | 997 | 1200 | |
| Recent Events | 443 | 600 | |
| **Retrieved Knowledge** | **1479** | **1500** | **cut — 2,478 retrieved** |
| Rules | 2028 | 3000 | |
| **Whole manifest** | **5,353** | — | |

**Allocated across all sections: 10,950 tokens. Actually used: 5,353. Unused: 5,597.** The one
section that overflowed was short by roughly 1,000 tokens while 5,597 sat idle beside it.

### A correction to an assumption in the code

`composer.py` marks `retrieved_knowledge` as `# unbounded growth — cap stays`. **That is wrong.**
Retrieval is fixed at `k=8` chunks (`mcp_platform_state/tools.py:323`) and chunks are packed to
~1,200 characters (`backend/apps/knowledge/index.py:25`), so the section has a permanent ceiling
of roughly **2,400 tokens**. A growing code index yields *better* eight chunks, never *more* of
them. The measured 2,478 and 2,575 sit exactly at that ceiling.

This matters: it was the reason the cap stayed at 1,500 while its neighbours were raised during
onboarding. Raising it does not open a hole, because `k=8` already closes it.

### Why "raise the caps 10–20%" was rejected

`retrieved_knowledge` is 1,500 and needs 2,478. **+20% gives 1,800 — still ~680 tokens short.**
A percentage increase would change nothing except the size of the loss. The onboarding caps were
raised to *measurements* ("measured 906, set 2000"), not by a percentage, and that remains the
right method.

---

## 2. Team decisions

| # | Decision | Chosen |
|---|---|---|
| **D1** | What is the promise? | **No silent loss.** Content may be shortened, but the agent is always told and can always fetch the rest. "Never truncate anything" was rejected as unachievable — the MCP transport's 1 MiB message limit and model context windows are hard walls. |
| **D2** | Does the "content omitted" note need a Rule? | **Yes — note + explicit mandatory rule in `# Rules`.** A note the agent may ignore is worth little; a rule makes acting on it required. |
| **D3** | Budget model | **Keep fixed per-section caps for now**, fixing the specific sections below. Elastic budgeting (sections borrow unused headroom) and scaling caps from the model's context window are recorded as future work, not this change. |
| **D4** | Over-long file in code review | **Team rejected all three options offered.** New direction: *when the agent can see that review context was truncated, it should be able to make a tool call and read the rest.* Confirmed possible — see T4. |
| **D4a** | Which agents get the new file-read tool | **Reviewer only (agent 08).** Requires splitting `_PLATFORM_TOOL_NAMES` into a base list plus per-agent extras; establishes least-privilege for future tools. No planning agent gains repository read access. |
| **D5** | Work item description | **The agent must read the full description; fix must be surgical.** Shape chosen: cap the metadata lines as today, render the **description whole, outside the cap** — it can never be cut. |
| **D6** | Secret findings | **If they are not all recorded, record them.** Confirmed they are not — see T5. Storage: **registered Artifact** (versioned, traceable, appears in Artifacts & Traceability) rather than a JSON blob on the run. |
| **D7** | What the human sees | **Console event only, no gate banner.** Keep `manifest.truncated` as the instrument for tuning caps with measurements, and fix the serializer so it names the section that was cut. No warning at the approval gate. |
| **D8** | Branch / sequencing | **Land as their own PR off `develop`**, not on top of the gate-rejection work currently uncommitted on `brownfield-agent-onboarding`. Mixing them makes both harder to review and harder to revert. |
| **D9** | Scope | **Log every identified issue first** (this document). The team will then choose what to fix. |

---

## 3. The issue register

"**Silent**" means the content is cut and nobody downstream is told — not the agent, not the
reviewer.

### Tier 1 — silent loss of content an agent needs

---

#### T1 · `get_artifact_body` caps at 400 KB and cannot be paged
**Where:** `mcp_platform_state/tools.py:695` (`_MAX_BODY_READ_BYTES`), `tools.py:727`,
`backend/integrations/preview.py:238` (`_cap_body`)
**Silent?** No — the response carries `truncated: true` and `full_bytes`. **But unrecoverable:
there is no way to fetch the remainder.**

The two sibling tools handle this correctly: `get_source_extraction` takes a `start` offset
(`tools.py:837`) and `get_page_images` returns `next_start` (`tools.py:917`). This one has no
offset parameter at all.

**Impact:** the sharpest issue for a greenfield client. A long PRD, architecture document or test
plan is exactly the artifact that exceeds 400 KB, and every downstream phase reads it through this
call.

**Recommended fix:** add a `start` offset and return `next_start`, mirroring
`get_source_extraction` exactly. Established pattern, same file, low risk.

---

#### T2 · `current_work_item` capped at 650 tokens — cuts the work item description
**Where:** `backend/manifest/composer.py:61` (budget), `composer.py:174` (`_render_work_item`)
**Silent?** Yes. **Decision: D5.**

Holds the work item's full description — text imported from Jira, whose length nobody on the team
controls. Its only recovery path (`list_work_items()`) returns the entire backlog to recover one
field, and nothing signposts it.

**Impact:** TASK-022 measured 366 tokens — **56% of the cap already**. Acceptance criteria are
conventionally written at the *end* of a description, which is precisely the part a cut removes.
A build agent working from a description whose acceptance criteria were silently removed will
produce plausible code that misses the actual requirement.

**Recommended fix (D5, confirmed):** in `_render_work_item`, keep the metadata lines (id, type,
state, parent, repo, …) under the existing 650 cap, and render the **description whole, outside
the cap**. Copies the pattern already proven on `# Reviewer Direction` — protect the authoritative
part, cap the rest.

*Why this is safe rather than an open door:* it is a single field from the system of record,
bounded by Jira at 32,767 characters, and it is the definition of the task the agent is being
asked to build. Cutting it is never the right trade.

*Cost:* one renderer function. No new tool, no MCP change, no Temporal payload change, no
migration. Manifests whose description already fits stay byte-identical.

---

#### T3 · `retrieved_knowledge` capped at 1,500 against a ~2,500 ceiling
**Where:** `backend/manifest/composer.py:64`, `composer.py:369` (`_render_knowledge`),
`mcp_platform_state/tools.py:323` (`k=8`)
**Silent?** Yes — chunks carry an `artifact_id` but only `text` is rendered, so a dropped chunk
leaves no trace.

The issue that raised this whole review. Retrieval fetches 8 chunks (~2,500 tokens), the cap keeps
~1,500, and the rest is discarded — including one chunk cut mid-sentence. On the evidence run the
lost chunks were the architecture-decision table, a design decision, the CI-gates note and the
module-communities map.

**Mitigating:** retrieval is ranked best-first (`apps/knowledge/index.py:138`), so the cut drops
the *least* relevant chunks. And on a build run the agent has the repository in its worktree —
these chunks are summaries *about* code it can read directly.

**Recommended fix — two parts:**

1. **Budget-aware retrieval.** Pass the token budget into `retrieve()` and return whole chunks
   until it is full. Today the platform finds and ranks 8 chunks and then bins a third of that
   work. Nothing is fetched-then-discarded, and no chunk is ever cut mid-sentence. *This is the
   fix that removes the problem properly; the cap number then never needs to move.*
2. **Pointer line (D1/D2).** Name what was left out and how to get it: *"3 further knowledge
   chunks matched — call `get_context()` to read them in full."*

---

### Tier 2 — visible but unrecoverable

---

#### T4 · Code review reads at most 16,000 characters per file
**Where:** `backend/orchestration/review_provider.py:46` (`_MAX_FILE_CHARS`),
`review_provider.py:249`
**Silent?** No — appends `… (truncated)`. **But unrecoverable, and the review still reports as a
completed review.** **Decision: D4 + D4a.**

**Impact:** a file longer than 16,000 characters has its tail unreviewed with nothing marking the
gap. More likely on greenfield, where the agent writes large files from scratch.

**A live bug found in the same code path.** When the PR read fails, the fallback instruction is
(`review_provider.py:253`):

> `(diff unavailable — fetch the PR via the platform tools)`

**That instruction is impossible to follow.** The granted tool list
(`backend/orchestration/activities.py:63`) is:

```
get_context, register_artifact, stage_artifact_body, get_artifact_body,
update_artifact, add_trace_edge, log_event, list_work_items,
create_work_item, transition_work_item, get_artifact, list_artifacts,
detect_drift, get_page_images
```

There is **no tool that can read a file from a repository or a PR**. If the PR read ever fails,
the reviewer is told to do something it cannot do, and will most likely review nothing while
reporting a completed review.

**Recommended fix (D4, confirmed):** a narrow, read-only MCP tool
`get_pr_file(pr_ref, path, start=0)` returning a window plus `next_start`, routed **through the
CodeHost capability** — never GitHub directly (non-negotiable #9). The plumbing already exists:
`_render_pr_section` reads every changed file via `codehost.get_file(repo, path, ref)`
(`review_provider.py:238`); it is simply not exposed to the agent.

The truncation marker then becomes actionable:

> `… (truncated at 16,000 of 47,300 chars — call get_pr_file(path="src/x.ts", start=16000) for the rest)`

**Scope (D4a, confirmed): reviewer only.** `_PLATFORM_TOOL_NAMES` is a single list shared by every
agent, so this requires splitting it into a base list plus per-agent extras. That is the larger
part of the work, and it establishes least-privilege for every future tool.

---

#### T5 · Secret-scan findings are lost at the companion/platform boundary
**Where:** `runner/companion/runner.py:526` (`_MAX_REPORTED_FINDINGS = 8`), `runner.py:491`,
`runner.py:543` (`to_build_report`)
**Silent?** Partly — the true count survives, the identities do not. **Decision: D6.**

**Two corrections to the original premise:**

1. **A secret block never reaches a merge gate.** A hit makes the build **fail**
   (`runner.py:546`): nothing is pushed, no PR opens, the work item returns to `in_progress` and
   triage opens. There is no merge gate at which to show or hide anything.
2. **The findings are not recorded.** The companion holds all of them, redacted —
   `out["secret_findings"] = [asdict(f) for f in secret_findings]` (`runner.py:491`) — but
   `to_build_report` **drops the list entirely** (`runner.py:550`), keeping only a prose string:

```python
return {"status": "failed", "branch": ...,
        "message": f"secret scan blocked the push: {len(findings)} finding(s): {detail}"}
```

`detail` is the capped-at-8 rendering. **On a build with 30 findings the platform receives the
true count (30) but the identity of only 8. Findings 9–30 exist nowhere on the platform** — no
artifact, no run output, no event payload. They live only in the companion's process memory and
die with it.

Note: all findings are **already redacted** at the companion (kind + `path:line` + redacted
preview, never the raw value), so recording them stores no live secret.

**Recommended fix (D6, confirmed):** carry the full redacted list across in the report payload and
persist it as a **registered Artifact** (e.g. type `secret_findings`, body in S3, pointer in the
registry, linked by trace edge to the build). The 8-line cap then stays exactly as it is, becoming
a *display* limit over data that is safely stored — which is what the cap was always intended to
be.

---

#### T6 · Test-failure evidence capped at 2,000 characters
**Where:** `backend/apps/quality/junit.py:34` (`_MAX_EVIDENCE`)
**Silent?** Not verified.

A long stack trace or assertion diff is cut. Affects a human debugging a failed test gate more
than it affects an agent.

**Recommended fix:** low priority. Raise if the team sees it bite in practice.

---

### Tier 3 — silent but currently low-pressure

---

#### T7 · Code index makes only the first 20,000 characters of each file searchable
**Where:** `backend/integrations/codeintel/builtin.py:79` (`_SEARCH_TEXT_PER_FILE`),
`builtin.py:339`
**Silent?** Yes.

Notable because **the same file already does this correctly elsewhere**: `_scan` records
`skipped_files` by extension (`builtin.py:405`, `builtin.py:426`) precisely so the agent can
declare what it could not read — its own quality gate requires "any skipped files recorded as
assumptions". But a file that is *partially* indexed is not reported the same way. A 60,000-
character legacy file is two-thirds invisible to search and nothing says so.

Related and working as designed: `_MAX_BYTES = 1_000_000` (`builtin.py:76`) skips whole files that
are too large — and **does** report them via `skipped_files`.

**Recommended fix:** report partially-indexed files alongside `skipped_files`, reusing the
mechanism already there. Brownfield-only.

---

#### T8 · `project` and `important_context`, 2,000 tokens each
**Where:** `backend/manifest/composer.py:59-60`
**Silent?** Yes.

Both genuinely unbounded — `important_context` is a free-text box an operator can paste anything
into. Currently 31 and 7 tokens on the evidence run, so nowhere near the cap. Recovery exists via
`get_context()` (which returns the raw, untruncated profile — `mcp_platform_state/tools.py:296`)
but is unsignposted.

**Recommended fix:** pointer line (D1/D2). **No cap change** — these are the sections where an
unbounded paste is a real risk, so the ceiling should stay.

---

#### T9 · `answered_clarifications`, 1,200 tokens / 20 items
**Where:** `backend/manifest/composer.py:66`, `composer.py:74`
**Silent?** Yes. Recoverable via `get_context()`.

Matters after several clarification rounds on one work item.

**Recommended fix:** pointer line (D1/D2).

---

#### T10 · `rules`, 3,000 tokens — the only section with no recovery path at all
**Where:** `backend/manifest/composer.py:65`
**Silent?** Yes, and unrecoverable — there is no tool that returns the rules.

Currently safe: we author them, they are identical on every run, and they measure 2,028. The risk
is entirely future — someone adds a rule, crosses 3,000, and rules are silently cut on every run
of every phase thereafter.

**Recommended fix:** a test asserting the composed rules fit the cap, so a future addition fails CI
instead of quietly truncating. Cheap and permanent. **Note:** D2 adds a new rule to this section,
which makes the test more valuable, not less.

---

#### T11 · Bounded and working as designed — no action
- `recent_events` — 600 tokens / 15 items (`composer.py:63`, `:73`); recoverable via
  `get_context()`.
- `_MAX_POINTER_STR = 300` (`mcp_platform_state/tools.py:62`) — `_lean_ref` drops large values by
  design; fetchable via `get_artifact_body`.
- `review_direction` — 3,000 tokens (`composer.py:71`); already correct, see §4.

---

#### T12 · MCP transport rejects messages over 1 MiB
**Where:** protocol limit; documented at `mcp_platform_state/tools.py:767`.

Hard, not tunable. The vision path already handles it by downscaling and paging, with byte-bounded
windows and `_VISION_FALLBACK_STEPS`.

**Informational — this is the reason D1 chose "no silent loss" over "never truncate".** Some
ceiling always exists; the achievable promise is that crossing it is never invisible.

---

## 4. Patterns the codebase already gets right

Every fix above applies an existing pattern somewhere it was missed. None requires a new concept.

| Pattern | Where | Copy it for |
|---|---|---|
| Drop whole units, never cut characters; protect the authoritative part | `# Reviewer Direction`, `composer.py:262` | T2, T3 |
| Name what was dropped + state the recovery call *before* the droppable tail | `# Relevant Artifacts`, `composer.py:328` | T3, T8, T9 |
| Paginate with `start` / `next_start` | `get_source_extraction` `tools.py:837`, `get_page_images` `tools.py:917` | T1, T4 |
| Report what could not be read | `skipped_files`, `codeintel/builtin.py:405` | T7 |
| Surface a partial import in the UI | onboarding `truncated` flag, `OnboardingHub.tsx:117` | reference for D7 |

---

## 5. Reporting fix (D7)

The run console currently prints `Manifest truncated — implementation` — the **phase**, not the
section — because `EventSerializer.get_message` walks a fixed key order
(`backend/api/serializers.py:458`) and hits `phase` before it would reach `sections`:

```python
for key in ("message", "detail", "error", "reason", "comment", "phase",
            "execution_mode", "branch", "workflow_id"):
```

The section names are already in the payload. Adding `sections` ahead of `phase` makes the console
read `Manifest truncated — Retrieved Knowledge`.

**Without this, every truncation costs somebody a database query to interpret** — it cost two
during this investigation.

**No gate banner (D7).** After these fixes a shortening has no consequence, so warning a reviewer
about it is noise that trains people to ignore banners. The event stays as the instrument for
tuning caps with measurements rather than guesses.

---

## 6. Recorded as future work (not part of this change)

- **Elastic budget (D3).** A manifest total with per-section floors, sections borrowing unused
  headroom. The evidence run makes the case: 5,597 tokens idle while one section was 1,000 short.
  Right end state; changes every manifest, so it deserves its own PR.
- **Scale caps from the model's context window.** Already flagged `FUTURE` in the composer
  docstring (`composer.py:55`). Becomes real when model selection is exposed to users — a fixed
  1,500 means very different things on a small model and a large one.
- **T6** test-evidence cap, if it bites.

---

## 7. Suggested implementation order

Grouped by blast radius, per D8 (own PR off `develop`).

**Group A — the minimum that delivers D1 for a greenfield client**
1. T3 budget-aware retrieval + pointer line
2. T2 description never truncated
3. T1 `get_artifact_body` pagination
4. D2 the mandatory rule in `# Rules`, plus T10's rules-fit-the-cap test
5. D7 serializer key order

**Group B — the review path (larger; introduces per-agent tool scoping)**
6. T4 `get_pr_file` tool + splitting `_PLATFORM_TOOL_NAMES` (D4a, reviewer only)

**Group C — independent, can land separately**
7. T5 secret findings recorded as an artifact (D6)
8. T7 partially-indexed files reported (brownfield-only)
9. T8 / T9 pointer lines

**Deployment notes**
- Group A touches `backend/manifest/composer.py`, which is **shared greenfield/brownfield code**.
  Standing constraint: no brownfield change may disturb the greenfield journey. Every change in
  Group A is designed to leave manifests byte-identical when nothing was being truncated — that
  property should be asserted by test, not assumed.
- T4 changes the tool grant list, which is read at dispatch. No migration.
- T5 adds an artifact type; check whether it needs a choices-only migration.
- None of Group A changes a Temporal payload, so no worker-before-API ordering is required.

---

## 8. What has NOT been done

Nothing in this document has been implemented. No file was modified to produce it. The evidence
run `6a7ae08e` completed normally — it registered a `code` artifact, opened
`https://github.com/TARUN51/medslot-single-repo/pull/36`, and proceeded to code review — with the
`Retrieved Knowledge` truncation described in T3 in effect.
