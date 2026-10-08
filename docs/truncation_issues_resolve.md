# Truncation — full issue register, team decisions, and recommended fixes

**Status: CLOSED 2026-10-07.** Every item in this register is built. T5 2026-08-17, T2 2026-09-03,
T9 + T13 2026-09-21, T6 (undated, in the test-report work), and the remaining six — T1, T3, T4, T7,
T8, T10 — on 2026-10-07, together with the two items §6 had recorded as future work: the elastic
budget (D3) and scaling the caps from the model's context window. Each entry carries its own build
note, so this header is a pointer, not the record.

**Why the last six landed in one pass.** The team's reading was that the mechanism existed to
protect a model's context window, that the window had grown roughly fivefold since the caps were
written, and that nothing in the platform had noticed. That was correct, and worse than they
thought: **no cap anywhere read a model's window at all.** The caps were sized on 2026-06-22
against an assumed 200,000 tokens. The floor model in use is `claude-sonnet-4-6` at ~1,000,000, so
the whole manifest at its theoretical maximum (15,150 tokens) is 1.5% of the window and a measured
one (5,353) is half a percent. We were deleting what an agent needed to protect a budget that had
not been scarce for months.

**The single most frequent truncation in the product was T3, and it was never touched.** Retrieval
fetched 8 chunks of ~1,200 characters (~2,400 tokens) into a section capped at 1,500, so ~37% was
discarded on every dispatch that retrieved a full set, one chunk cut mid-sentence. That is
arithmetic, not an edge case, which is why a QA pass saw `Manifest truncated` on almost every
phase — seven times in one run, alternating implementation and code_review.

It survived three rounds of this register because of **one wrong comment**: `retrieved_knowledge`
was marked `# unbounded growth — cap stays`. It is not unbounded; `k=8` closes it. §1 of this
document said so on 2026-08-04 and the comment was never corrected, so each time the caps were
revisited this one was passed over as the section that had to keep its cap.

**What the fix was NOT.** No cap was raised. That was rejected with arithmetic on 2026-08-04
(1,500 + 20% is still ~680 short of 2,478) and the standard has held through all eleven items:
every one removed the reason the cap bit, or made crossing it recoverable. The caps are now floors
under a total derived from the dispatched model, retrieval fetches only what will be rendered, and
the three tier-2 issues became paginated reads instead of final losses.

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

**BUILT 2026-10-07 — exactly as recommended.** `get_artifact_body(artifact_id, state=None,
start=0)` now returns `total_bytes`, `start` and `next_start`, with `next_start` null on the last
window. `_cap_body` does the slicing, so all three of its branches (state hit, default body +
state menu, plain internal) paginate identically; `truncated` and `full_bytes` are kept and mean
what they always meant — there is more after this window — so every caller that does not pass an
offset sees the payload it saw before.

`start` is declared on the MCP wrapper signature as well as on the function, because FastMCP builds
the agent-facing schema from the wrapper and **silently drops** a parameter missing from it (the
trap `test_a_declared_format_survives_the_tool_an_agent_actually_calls` already pins). The
companion proxy carries it too, or the tool would page on the server path and not on the one the
companion actually uses.

Tests: `test_truncation_recovery.py` reassembles a document from its windows and asserts the result
is byte-identical to the original; that a body which fits is unchanged and reports
`truncated: False`; and that a window boundary landing inside a multi-byte character does not break
the read — a client whose requirements are written in Hindi must not hit a decode error on page
two. No test exercised `get_source_extraction`'s pagination either, so that gap closes with it.

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

**BUILT 2026-09-03 — exactly as recommended above, no deviation.** `_render_work_item`
(`composer.py`) now assembles the metadata lines, caps THOSE at the existing 650-token
`current_work_item` budget, and re-attaches the description whole. Ordering is preserved: when the
whole section fits, the output is byte-identical to before, and there is a test asserting that
rather than assuming it. When the metadata does overflow it is cut with the usual
`[truncated to fit token budget]` marker — so the one cut that can still happen is never silent —
and the description follows it intact.

Three tests pin it (`test_manifest_composer.py`): the byte-identical short case; a ~9,000-token
description whose trailing acceptance criteria survive; and runaway metadata still being capped
while the description survives the cut.

**This is half of the fix for Bugs.xlsx S.No 243** (the CORS requirement that shipped unbuilt and
stayed invisible for 18 days). T2 was the reason the acceptance criteria could vanish before any
agent read them; the other half — requiring agent 08 to show a per-criterion verdict — is the
`guard_acceptance_criteria` work in the same batch. Neither alone is sufficient: without T2 the
review agent has nothing to check against, and without the verdict contract nothing proves it
looked.

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

**BUILT 2026-10-07 — part 1 as recommended, part 2 generalised.** Retrieval is now budget-aware:
`get_context(..., knowledge_chunks=N)` passes the count down to `retrieve()`, and the orchestrator
derives N from the run's budget (`manifest.budget.chunks_for_budget`) as
`clamp(budget // 8 // 300, 8, 24)`. Eight is the floor, never the rule — this change may only ever
give an agent more context than it had. Twenty-four is the ceiling, because retrieval is ranked
best-first and the fortieth chunk competes for attention with the first.

Nothing is fetched and then discarded: the provisional knowledge allowance that sizes retrieval and
the allocator's ceiling for that section are the same number by construction, and a grower's
ceiling is its own demand. `test_nothing_retrieved_is_ever_discarded` renders the exact failing
shape — eight chunks over the old cap — and asserts eight chunks out and no truncation marker.

`token_count` was already stored on every chunk at index time and thrown away on the way out; it is
carried now rather than re-estimated.

The pointer line became a general mechanism rather than a knowledge-only one — see T8.

**And the comment that caused this is corrected.** `retrieved_knowledge` no longer claims to be
unbounded growth; it says what §1 established, that `k` closes it.

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

**BUILT 2026-10-07 — as decided in D4/D4a, with one correction to the scope above.**
`get_pr_file(pr_ref, path, start=0)` is a read-only tool routed through the **CodeHost capability**
(never GitHub directly, per non-negotiable #9), paginated on the `get_source_extraction` pattern. A
file it cannot read returns an `error` naming the file rather than an empty body: "this file is
empty" is a far more damaging answer to a reviewer than "I could not open this file" — one invites
a verdict, the other blocks it.

The truncation marker is now actionable and names the offset:
`… (truncated at 50,000 of 147,300 chars — call get_pr_file(path="src/x.ts", start=50000) for the
rest)`. And the per-file window is derived from the run's budget rather than fixed at 16,000, with
16,000 as a **floor** — a budget-derived number coming out lower would mean this change had made a
code review read less of the code, which is the one direction it must never move.

**The live bug in this section is fixed.** The fallback line now names a call that exists.

**The scope correction.** D4a assumed `_PLATFORM_TOOL_NAMES` was the list the reviewer gets. It is
not. `worker.py` registers `CompanionReviewProvider`, so **code review runs on the enrolled
companion**, with `PLAN_ALLOWED_TOOLS` built from `BUILD_STATE_TOOLS` — a different list entirely.
The split therefore had to happen twice, and the tool wired on four surfaces (implementation, MCP
server, companion proxy + state route, and both grant lists) or it would have been invisible or
unreachable. Both splits are base-plus-extras, as D4a intended: `REVIEW_TOOLS` and
`REVIEW_ALLOWED_TOOLS` are supersets of the base lists, asserted as such by test, so the reviewer
gains a tool and no planning agent does.

**One further thing this depended on, found while building it.**
`test_review_task_is_sandboxed_to_platform_tools` asserted `ToolSearch` was DENIED to the reviewer.
It had been failing since 2026-07-30, when ToolSearch was deliberately removed from the denylist
after run `457f65e1` — where blocking it made granted platform-state tools invisible and the agent
wrote 39,417 characters of deliverables as prose instead of calling them. Had anyone "fixed" that
test by making the code match it, **`get_pr_file` would have been granted and unreachable**, which
is the same failure this item exists to end. The test now asserts the opposite, with the run id in
a comment so it is not flipped back.

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

**BUILT 2026-08-17 — with one deliberate simplification, flagged rather than done silently.**
The list now travels (`BuildReport.secret_findings`, bounded at `_MAX_CARRIED_FINDINGS = 50`
because the report rides a Temporal signal) and is persisted — but on **`run.outputs`**, not as a
registered Artifact. Two reasons: the payload is a handful of short redacted dicts, not a
document, so an S3 body plus a registry pointer plus a trace edge is heavier machinery than the
data warrants; and `run.outputs` is where the directly analogous diagnostic (`review_cycles`)
already lives, so this follows an existing precedent instead of adding a new artifact type. The
8-line prose cap stays exactly as described above — a display limit over stored data.
If the team wants the findings surfaced in Artifacts & Traceability rather than only on the run,
promoting them to a registered artifact is a small follow-up on top of what now exists.

The findings also now feed the recourse, which is the part T5 could not have: a block triggers one
bounded auto-retry seeded with them (`handle_secret_block_core`), so the agent is told what
tripped instead of the run dying with the knowledge trapped in the companion's memory.

**Correction to point 1 above:** "triage opens" was taken from the Phase-2 spec's wording, but no
triage object is created anywhere — `mark_build_failed_core` logs `build.failed` and returns the
work item to `in_progress`. The spec has been corrected (§6) rather than left promising something
that was never built.

---

#### T6 · Test-failure evidence capped at 2,000 characters
**Where:** `backend/apps/quality/junit.py:34` (`_MAX_EVIDENCE`)
**Silent?** Not verified.

A long stack trace or assertion diff is cut. Affects a human debugging a failed test gate more
than it affects an agent.

**Recommended fix:** low priority. Raise if the team sees it bite in practice.

**Already built, and the model for everything else here.** The cap was not raised: the full text is
parsed and filed as the run's `test_report` artifact body in the object store, and the short summary
that stays on the row — and goes to Jira, which **fails the push** above 32,767 characters and
breaks the defect loop — is bounded in `apps.quality.services` where that limit actually exists. A
shortened row says where the rest is. What remains in `junit.py` is `_MAX_EVIDENCE = 256_000`, a
runaway-log guard: a single test whose failure text passes a quarter of a megabyte is emitting a
log, not evidence. Its comment states the standard this register has held to since — *"raising this
number is not how you fix a truncated report"*.

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

**BUILT 2026-10-07 — as recommended, and it was worse than recorded here.** `index_report` and
`get_overview` now carry `partially_indexed_files` beside `skipped_files`.

The extra finding: past the whole-repo `_SEARCH_TEXT_BUDGET`, remaining files get **no searchable
text at all**, and that was recorded only as one repo-wide boolean with no test. Those files are
named too, as `unsearchable_files`. A count cannot be written down as an assumption; a list can.

`search_text_complete` now accounts for partially-indexed files as well, so the summary boolean can
no longer claim a clean read while individual files are two-thirds invisible. Both agent-facing
docstrings in `codeintel_mcp.py` — which already taught the `skipped_files` habit — say plainly
that a search missing a term in one of these files is **not** evidence the codebase lacks it.

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

**BUILT 2026-10-07 — pointer line, no cap change, and generalised past these two sections.**
`_section()` takes a `recovery` sentence and appends it **only when something was actually
removed**, so a section that fits reads exactly as it always did and an agent is never told to go
and fetch what is already in front of it. `project`, `important_context`, `recent_events`,
`answered_clarifications` and `retrieved_knowledge` all carry one.

`# Rules` deliberately does not, because no tool returns the rules — a sentence promising a call
that does not exist is worse than silence, which is precisely what the reviewer's "fetch the PR via
the platform tools" turned out to cost (T4). T10's size test guards that section instead.

Their ceilings stay. These are the two sections a free-text paste can fill, so under the elastic
budget they sit in the human-text tier with a hard ceiling of 4x their floor: generous for genuine
steering, bounded against one pathological paste.

---

#### T9 · `answered_clarifications`, 1,200 tokens / 20 items — **observed live 2026-08-05**

> **Built 2026-09-21.** `_render_clarifications` now shows a set of questions once, keeping the
> newest answer, keyed on the sorted question ids. Test:
> `test_the_same_questions_answered_twice_are_replayed_once_with_the_newest_answer`.

**Where:** `backend/manifest/composer.py:66`, `composer.py:74`, ordering at
`mcp_platform_state/tools.py:293`
**Silent?** Yes. Recoverable via `get_context()`.

No longer hypothetical. Run `5b4a1bab` (tenant `d6a89745`, WI-1) logged `manifest.truncated` for
this section on dispatch. Reconstructed as of that moment: **1,496 tokens against the 1,200 cap.**

**The cause was not size — it was a duplicate.** Three answered clarification records exist on that
work item:

| Answered | Questions | Ids |
|---|---|---|
| 07:33:42 | 10 | current_process, leave_entitlements, carryover_cap, half_day, manager_on_leave, probation_leave, announcements, office_locations, leave_cancellation, notifications |
| 07:44:13 | 10 | **the identical ten** |
| 11:27:32 | 4 | saas_target_segment, saas_pricing_model, saas_geographic_scope, saas_hosting_model |

The first two are the duplicate gate WP1 fixed. Both were answered, so both persist, and the
composer replays the same ten questions twice. Pulling the tail of what the agent actually received
confirms the cut lands **midway through the second copy**, after `manager_on_leave` — so nothing
unique was lost on this run and the output was unharmed. Deduplicated, the same content measures
**823 tokens and does not truncate at all**.

**WP1 stops new duplicates being created; it does nothing about records already in the table.** The
two rows above will inflate every future manifest for this work item.

**Recommended fix:** dedupe on replay in `_render_clarifications` — key on the sorted question ids,
keep the most recent answer. Cheap, defensive, and it covers any duplicate that ever reaches the
table regardless of how it got there. Pointer line (D1/D2) still applies on top.

---

#### T13 · The section is ordered oldest-first and truncates from the tail — **the newest human answer is always the first thing lost**

> **Built 2026-09-21.** `get_context` now orders answered clarifications newest first
> (`-answered_at`), so an overflow drops the oldest context. Test:
> `test_answered_clarifications_come_newest_first`.

**Where:** `mcp_platform_state/tools.py:293` (`.order_by("answered_at")`),
`backend/manifest/composer.py:81` (`_truncate` keeps the head)
**Silent?** Yes.

Found while measuring T9, and more serious than T9 itself. Answers are rendered oldest first and the
cap cuts from the end, so overflow discards **the most recent decisions and keeps the stalest ones**.

Measured on the same work item as it stands after the SaaS pivot: the section is 1,813 tokens against
the 1,200 cap, and the four ids that fall off the end are exactly
`saas_target_segment`, `saas_pricing_model`, `saas_geographic_scope`, `saas_hosting_model` — the
answers that define the new direction. A re-dispatch of that run (round 3, or a companion restart)
would hand the agent the superseded internal-tool Q&A **twice** and none of the pivot answers.

Not hit yet only because the current run received those answers live through `ask_human`, in
conversation, rather than through the manifest.

**Recommended fix:** order newest-first for this section, so if it ever does overflow the loss is old
context rather than the latest human decision. Combine with the T9 dedupe — together they bring this
work item to ~1,140 tokens, under the cap, with no cap change at all.

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

**BUILT 2026-10-07 — exactly as recommended.**
`test_the_rules_we_author_fit_their_budget_with_room_to_spare` asserts the authored rules fit inside
90% of their budget. They measure 2,183 tokens against 3,000.

The margin is deliberate: failing only at 100% would mean the rule that crosses the line is also the
rule nobody can see was lost. The existing `test_composer_renders_distilled_rules_in_rules_section`
could never have caught this — both strings it looks for sit near the top, so it passes happily with
the whole end of the rules missing, and the file is append-only in practice.

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

## 6. Recorded as future work — **both built 2026-10-07**

- **Elastic budget (D3). BUILT.** `composer.allocate()` gives every section its old cap as a FLOOR
  and shares the spare. A section is charged only `min(floor, demand)`, so one needing 31 tokens
  reserves 31 rather than its whole 2,000 — the evidence run's 5,597 idle tokens become available
  to the section that was 1,000 short. Spare is distributed in strict priority tiers, not one
  proportional pass, so a project with thousands of events cannot soak up headroom that `# Rules`
  needs for correctness; `# Rules` is the one section with no recovery path at all.

  `total=None` returns the floors untouched, which is the path every caller outside the
  orchestrator takes, so **the output is byte-identical to before** — pinned by a golden set of
  eight manifests including the cases that truncate. The allocator is pure, integer-only and
  order-independent, with a property test over randomised inputs (including zero and negative
  totals) asserting no section ever lands below its floor. That is the single outcome that must be
  impossible, because the tempting invariant `sum(allowance) <= total` is FALSE here and "fixing"
  it by clamping is exactly how a section would end up smaller than it is today.

- **Scale caps from the model's context window. BUILT.** `manifest/budget.py` is the first
  model-to-metadata map in the repo. The total is 5% of the dispatched model's window, capped at
  60,000 tokens; an unrecognised model falls back to **200,000 — the exact assumption the original
  caps were built on**, so an unfamiliar engine reproduces the platform's long-standing behaviour
  rather than inventing a number, and logs an event saying it did. The `FUTURE:` note in the
  composer docstring is deleted, because it is done.

  The ceiling is deliberate. "Nothing is lost" and "use the whole window" are different goals and
  only the first is worth having: the manifest is not the only thing in an agent's context, and a
  larger briefing costs latency and attention on every dispatch — seven of them in one remediation
  loop. On `claude-sonnet-4-6` the budget is 50,000 against a 15,150 worst case, over three times
  the room needed for nothing to be cut.

- **T6** test-evidence cap — already correct; see its entry above.

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

**Nothing. The register is closed (2026-10-07).** All thirteen items are built, and so are the two
pieces §6 had recorded as future work.

*History, kept because it is the useful part. This section has been wrong twice. It said "nothing
in this document has been implemented", which was true the day it was written and false from 17
August; that was corrected on 2026-09-17. It then listed T3 as the one outstanding item for six
weeks — the item that was firing on **every single dispatch**, while the register's own §1 already
contained the measurement proving its cap was wrong. The lesson the team drew is the one worth
keeping: a register is only as good as the pass that re-reads it against the code, and a comment in
the source (`# unbounded growth — cap stays`) outlived three readings of a document that
contradicted it.*

**Carried forward, outside this register:**

- The truncation event's section splitter divides on `"\n# "`, so a markdown heading inside a work
  item's description or a knowledge chunk is mis-attributed as a section name. Pre-existing, found
  while adding the allocation report, deliberately not fixed here — widening this change for it
  would have bought nothing the team asked for.
- `_render_remediation_section` and `_render_open_findings` are appended outside the manifest budget
  and stay **uncapped on purpose**. They were reviewed as part of this work: both are instruction
  sets — the findings an agent must fix — so capping them would introduce a truncation that does not
  exist today, of the worst kind. Cutting the tail of a list of required fixes is the same failure
  as cutting a work item's acceptance criteria (T2), which cost eighteen days. Their size is bounded
  by the open findings on one work item, not by a project's age.
