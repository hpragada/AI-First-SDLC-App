"""Manifest Composer (spec §4).

Renders a `get_context()` result + the current work item into an ephemeral `AGENTS.md`
with a FIXED section order and a per-section token budget (prefer retrieval over dumping
the whole profile). Pure: dicts in, markdown string out — written per run, discarded after.

Section order (locked):
  # Project → [# Repository] → # Important Context → [# Reviewer Direction]
  → # Current Work Item → [# Answered Clarifications] → # Relevant Artifacts
  → # Recent Events → # Retrieved Knowledge → # Rules

`# Reviewer Direction` is rendered only when a human sent this phase back through the gate with
written direction ("Request changes"). It sits ABOVE every capped-and-growing section on purpose:
the artifact/event tail is what truncation eats, and an instruction the reviewer typed must never
be the thing that gets cut.

`# Answered Clarifications` is rendered only when the work item has answered clarifications —
prior human answers to the agent's questions, replayed so a re-dispatched run reuses them
instead of re-asking (req #2 durability).

`# Repository` is rendered only for a repo-scoped run (multi-repo, D5) — it names the repo
this run targets, its role, base branch, and per-repo stack overrides; the artifacts below are
already scoped to it (its own + project-shared + the cross-repo contract), while the registry
and Knowledge Index remain project-wide shared memory.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

# Rough heuristic: ~4 chars per token. Good enough to bound section sizes.
_CHARS_PER_TOKEN = 4
_TRUNCATED = "\n… [truncated to fit token budget]"
#: Public alias so callers can detect a cut section and report it (see activities.py).
TRUNCATION_MARKER = "[truncated to fit token budget]"


@dataclass
class TokenBudget:
    """Per-section caps (in estimated tokens) + count caps for list sections.

    **Cap what grows without bound; don't cap what we author.** Artifact lists, event history and
    retrieved knowledge grow with a project's age — those are what these caps exist for. `rules`
    and `project` do not: the rules are written by us and identical on every run, and a project
    profile is a page. Capping them the same way silently cut real instructions.

    Measured 2026-07-30 on a live ideation run: `rules` needed 1,706 tokens against a 1,500 cap
    and `project` needed 906 against 800, so BOTH were being truncated mid-sentence — the Project
    section stopped inside the user's constraints at "Authentication: Email + password only. No
    OTP, no". The whole manifest was 3,594 tokens, under 2% of the model's window: we were cutting
    a document that had no size problem at all. Raised with real headroom.

    **These are FLOORS, not ceilings, since 2026-10-07.** They are what a section is guaranteed,
    and `allocate()` hands out whatever the model's window affords above them — so the numbers
    below now answer "what must this section always have?" rather than "what may it never exceed?".
    Lower one and you take context away from an agent; the floors only ever move up.

    The note that used to sit here said these *should* one day scale from the model's window. They
    do. The total comes from `manifest.budget.total_for_model` and the caps stopped being the thing
    that decides what an agent reads.
    """

    project: int = 2000              # was 800  — user-authored profile, measured 906
    important_context: int = 2000    # was 1500 — user-authored, measured 651
    current_work_item: int = 650
    relevant_artifacts: int = 1200   # unbounded growth — cap stays
    recent_events: int = 600         # unbounded growth — cap stays
    retrieved_knowledge: int = 1500  # unbounded growth — cap stays
    rules: int = 3000                # was 1500 — WE author this, same every run; measured 1,706
    answered_clarifications: int = 1200
    # The review conversation. Human-authored like `project`/`important_context`, but unlike them
    # it DOES grow without bound — one more round every time a reviewer sends the phase back — so
    # it needs a cap. It is enforced differently: whole OLDEST rounds are dropped, and the current
    # direction is never cut. See `_render_review_direction`.
    review_direction: int = 3000
    max_artifacts: int = 20
    max_events: int = 15
    max_clarifications: int = 20


def estimate_tokens(text: str) -> int:
    return -(-len(text) // _CHARS_PER_TOKEN)  # ceil(len/4)


def _truncate(text: str, max_tokens: int) -> str:
    """Trim to the cap, cutting at a LINE boundary rather than mid-character.

    The character-exact cut left half-sentences an agent reads as complete: a real run's Project
    section ended "Authentication: Email + password only. No OTP, no" — the reader cannot tell
    that something was removed mid-thought, only that the constraint reads oddly. Backing up to
    the last newline costs at most one line and never presents a fragment as a whole statement.
    If the first line alone exceeds the cap there is no boundary to find, so the hard cut stands.
    """
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    cut = head.rfind("\n")
    if cut > 0:
        head = head[:cut]
    return head.rstrip() + _TRUNCATED


def _json_block(label: str, value: Any) -> str:
    return f"\n**{label}**:\n```json\n{json.dumps(value, indent=2, default=str)}\n```"


def _section(header: str, body: str, max_tokens: int, recovery: str = "") -> str:
    """One manifest section, trimmed to its allowance, saying how to get the rest if it was cut.

    `recovery` is the call that returns this section's content in full. It is appended ONLY when
    something was actually removed, so a section that fits reads exactly as it always did — and
    an agent is never told to go and fetch a thing it already has in front of it.

    The register's rule (D1/D2) is that content may be shortened but the loss is never silent and
    never final. A truncation marker alone met half of that: it said something had gone and left
    the reader with no way to act, which on a real run is indistinguishable from the content not
    existing. `# Relevant Artifacts` has always named its fallback call; this gives the same
    courtesy to every other section that has one.
    """
    body = body.strip() or "_none_"
    trimmed = _truncate(body, max_tokens)
    if recovery and TRUNCATION_MARKER in trimmed:
        trimmed = f"{trimmed}\n{recovery}"
    return f"# {header}\n\n{trimmed}"


# ── elastic budget ──────────────────────────────────────────────────
# The caps above are FLOORS, not ceilings. When the dispatched model's window affords more than
# the floors need, the spare is handed to the sections that are actually short — which on a real
# run is `retrieved_knowledge`, measured at 1,479 tokens against a 1,500 cap while 5,597 tokens
# sat idle in sections that needed a fraction of what they were allocated.

#: A cap so large nothing reaches it, used only to MEASURE a section's true demand. Never emitted.
_MEASURING_CAP = 1_000_000_000

#: Every budgeted section, in one fixed order so the allocation is a function of its inputs and
#: not of dict iteration. Keys are `TokenBudget` field names.
_CANONICAL_ORDER = (
    "rules", "project", "important_context", "review_direction", "current_work_item",
    "answered_clarifications", "relevant_artifacts", "recent_events", "retrieved_knowledge",
)

#: `current_work_item` never grows. Only its DESCRIPTION is exempt from the cap, deliberately
#: (T2, see `_render_work_item`); the metadata lines are bounded and repetitive, and a runaway
#: title must still be cut visibly rather than quietly granted ten thousand tokens.
_NON_ELASTIC = frozenset({"current_work_item"})

#: Spare is handed out in STRICT PRIORITY TIERS, not one proportional pass. Proportional-only
#: rewards the greediest grower: a project with five thousand events would soak up headroom that
#: `# Rules` needs for correctness, and rules are the one section with no recovery path at all —
#: no tool returns them, so a cut there is unrecoverable as well as silent.
_TIERS = (
    # We author these and they are identical on every run; their size is a reviewable constant.
    ("rules",),
    # Human-authored. Cutting what a person wrote is the expensive failure — it is what deleted a
    # reviewer's own instruction and a project's constraints before the 2026-07-30 measurement.
    ("project", "important_context", "review_direction"),
    # Grow with the project's age. These are what the caps were honestly for, and what this whole
    # change exists to stop cutting.
    ("relevant_artifacts", "recent_events", "retrieved_knowledge", "answered_clarifications"),
)

#: Ceiling as a multiple of the floor, for sections whose demand has no natural bound.
#: `project` and `important_context` are free-text an operator can paste anything into, so they
#: keep a real ceiling — generous for genuine steering, bounded against one pathological paste.
#: The growers are absent on purpose: each is ALREADY bounded by a count cap (20 artifacts,
#: 15 events, 20 clarifications, at most 24 retrieved chunks), so their demand cannot run away
#: and their ceiling is simply what they ask for.
_HARD_MAX_MULTIPLE = {"rules": 2, "project": 4, "important_context": 4, "review_direction": 2}


def allocate(total: int | None, floors: dict[str, int],
             demands: dict[str, int]) -> dict[str, int]:
    """Per-section allowances for one run. Pure, integer-only, order-independent.

    The invariant that matters, and the one a naive implementation gets wrong:

        allowance[s] >= floor[s]  for every s        and        Σ min(allowance, demand) <= total

    NOT `Σ allowance <= total` — a section that needs 31 tokens keeps its 2,000 floor while
    reserving only 31, which is the whole reason there is spare to hand out. Asserting the wrong
    form and then "fixing" it is how a section ends up below its floor, i.e. how this change would
    make a manifest SMALLER than it is today. That must be impossible, so it is a property test.

    `total=None` means no budget was supplied, and every section gets exactly its floor — the
    behaviour the platform had before this existed. Every caller outside production omits it, so
    that path is what the golden byte-equality test pins.
    """
    allowances = dict(floors)
    if total is None:
        return allowances
    # Charge a section only what it actually asks for, never its whole floor. Reserving the floor
    # regardless would make the fallback budget (10,000) smaller than the floors sum (10,950), so
    # spare would always be zero and an unrecognised model could never improve on today.
    reserved = sum(min(floors[s], demands.get(s, 0)) for s in floors)
    spare = total - reserved
    if spare <= 0:
        return allowances

    need: dict[str, int] = {}
    for section in _CANONICAL_ORDER:
        if section not in floors or section in _NON_ELASTIC:
            continue
        multiple = _HARD_MAX_MULTIPLE.get(section)
        ceiling = floors[section] * multiple if multiple else demands.get(section, 0)
        wanted = min(demands.get(section, 0), ceiling)
        if wanted > allowances[section]:
            need[section] = wanted - allowances[section]

    for tier in _TIERS:
        active = [s for s in tier if need.get(s, 0) > 0]
        while active and spare > 0:
            weight_total = sum(floors[s] for s in active)
            granted = 0
            for section in active:
                share = (spare * floors[section]) // weight_total   # integer only, never float
                take = min(need[section], share)
                allowances[section] += take
                need[section] -= take
                granted += take
            spare -= granted
            if granted == 0:
                # Only integer-flooring residue is left; hand it out one token at a time in
                # canonical order so the result stays deterministic, then stop.
                for section in active:
                    if spare <= 0:
                        break
                    if need[section] > 0:
                        allowances[section] += 1
                        need[section] -= 1
                        spare -= 1
                break
            active = [s for s in active if need[s] > 0]
    return allowances


#: How to get back what a cut removed, per section. Only sections with a REAL recovery path get
#: one. `# Rules` is absent on purpose: no tool returns the rules, which is exactly why their
#: size is guarded by a test instead. A sentence promising a call that does not exist is worse
#: than silence - the reviewer's "fetch the PR via the platform tools" cost a whole review that
#: way, by telling an agent to do something no granted tool could do.
_RECOVERY = {
    "project": "_Shortened. Call `get_context()` for the project profile in full._",
    "important_context": "_Shortened. Call `get_context()` for this steering text in full._",
    "recent_events": "_Shortened. Call `get_context()` for the full recent-event list._",
    "answered_clarifications":
        "_Shortened. Call `get_context()` for every answered clarification._",
    "retrieved_knowledge":
        "_Shortened. Call `get_context()` for every retrieved knowledge chunk._",
}


# ── section renderers ───────────────────────────────────────────────
def _render_project(profile: dict, budget: TokenBudget) -> str:
    lines = [
        f"- name: {profile.get('name', '')}",
        f"- track: {profile.get('track', '')}",
        f"- repo_topology: {profile.get('repo_topology', '')}",
        f"- domain: {profile.get('domain', '')}",
        f"- profile_version: {profile.get('version', 0)}",
    ]
    if profile.get("description"):
        lines.append(f"- description: {profile['description']}")
    # `theme` flows verbatim (PG23/D10): per-tenant tokens + responsive breakpoints, so
    # design/implementation agents honor one theme without a per-tenant code fork.
    for key in ("tech_stack", "coding_standards", "nfrs", "constraints", "glossary", "theme"):
        value = profile.get(key)
        if value:
            lines.append(_json_block(key, value))
    return _section("Project", "\n".join(lines), budget.project,
                    _RECOVERY["project"])


def _render_repository(repo: dict, budget: TokenBudget) -> str:
    """Per-repo scoping (D5): which repo this run targets + its role/base/overrides."""
    lines = [
        f"- name: {repo.get('name', '')}",
        f"- role: {repo.get('role', '')}",
        f"- default_base: {repo.get('default_base', '')}",
        f"- repo_id: {repo.get('repo_id', '')}",
        "",
        "Artifacts below are scoped to this repo (its own + project-shared + the cross-repo "
        "`api_contract`). The registry, traceability, and Knowledge Index are project-wide "
        "shared memory across all repos.",
    ]
    if repo.get("stack_overrides"):
        lines.append(_json_block("stack_overrides", repo["stack_overrides"]))
    return _section("Repository", "\n".join(lines), budget.project)


def _render_repositories(repositories: list, budget: TokenBudget) -> str:
    """Multi-repo assignment options (D5, Hybrid Option C): the project's repos + roles, for a
    project-level planning run (e.g. Task Breakdown) that assigns each work item to a repo.
    Rendered only when the run is NOT scoped to a single repo and the project has >1 repo."""
    lines = [
        "This project spans multiple repositories. When you create work items, assign each to "
        "the repository that best fits its nature (match the item to a repo `role`), and pass "
        "the chosen `repo_id`. Give a one-line rationale and a confidence (high | low). Your "
        "assignment is a draft the reviewer confirms or overrides at the gate.",
        "",
    ]
    for r in repositories:
        lines.append(
            f"- repo_id: `{r.get('repo_id', '')}` · role: **{r.get('role', '') or '—'}** · "
            f"name: {r.get('name', '')} · base: {r.get('default_base', '')}"
            + ("  (default)" if r.get("is_default") else "")
        )
    return _section("Repositories", "\n".join(lines), budget.project)


def _render_important_context(profile: dict, budget: TokenBudget) -> str:
    # Verbatim — this is the operator's hand-written steering text.
    return _section(
        "Important Context", profile.get("important_context", ""),
        budget.important_context, _RECOVERY["important_context"],
    )


def _render_work_item(work_item: dict, phase: str, budget: TokenBudget) -> str:
    """The task itself. **The description is rendered whole, outside the cap** (truncation
    register T2).

    Same reasoning as `_render_review_direction` one function down: `_truncate` cuts from the END,
    and the end of a description is exactly where the acceptance criteria are written. So the
    failure mode was never "the agent gets a shorter brief" — it was "the agent gets a brief whose
    REQUIREMENTS have been removed, and nothing tells it or the human". A build agent then produces
    plausible code that misses the actual requirement and the review agent has nothing to check it
    against; that is the machinery behind the CORS miss on TASK-006 (S.No 243), which survived 18
    days and 29 further tasks. Measured on a live run, an ordinary task (TASK-022) already rendered
    at 366 tokens — 56% of the 650 cap — so this was not a distant edge case.

    This is not an open door. The description is ONE field from the system of record, hard-bounded
    by Jira at 32,767 characters; it does not grow with the project's age the way
    `relevant_artifacts`, `recent_events` and `retrieved_knowledge` do, which is why their caps
    must stay. The metadata lines keep the cap — they are bounded and repetitive, and cutting them
    is harmless. When nothing overflows, the output is byte-identical to before.
    """
    wi = work_item or {}
    lines = [
        f"- id: {wi.get('id', '')}",
        f"- phase: {phase}",
        f"- type: {wi.get('type', '')}",
        f"- state: {wi.get('state', '')}",
        f"- feature_stream: {wi.get('feature_stream', '')}",
    ]
    # Title + description carry what the item IS — for a test_case WI the description holds the
    # TC spec/steps the agent automates (manual path); for any type it grounds the run. (An auto
    # test case also gets its full TC-XXX block as a `test_case` artifact under Relevant Artifacts.)
    if wi.get("title"):
        lines.append(f"- title: {wi['title']}")
    description = str(wi.get("description") or "")
    description_line = f"- description: {description}" if description else ""
    at = len(lines)         # where the description sits in the established ordering
    # For an auto-materialized test case, point the agent at ITS specific `test_case` artifact —
    # get_context's artifacts are project/repo-scoped (not per-WI), so this pointer is how 09b
    # knows which TC is this run's. Fetch its full spec with get_artifact_body (P3-09b B3/B4).
    ref = wi.get("external_ref") or {}
    if ref.get("test_case_artifact_id"):
        tc = ref.get("tc_id", "")
        lines.append(f"- test_case: {tc} — get_artifact_body({ref['test_case_artifact_id']})")
    if wi.get("parent_id"):
        lines.append(f"- parent_id: {wi['parent_id']}")
    if wi.get("depends_on"):
        lines.append(f"- depends_on: {', '.join(str(x) for x in wi['depends_on'])}")
    if wi.get("repo_id"):
        lines.append(f"- repo_id: {wi['repo_id']}")
    if wi.get("takeover_flag"):
        lines.append("- takeover_flag: true")

    parts = lines[:at] + ([description_line] if description_line else []) + lines[at:]
    body = "\n".join(parts)
    if estimate_tokens(body) <= budget.current_work_item:
        return _section("Current Work Item", body, budget.current_work_item)
    # Over budget: cap the metadata (which carries the "… truncated" marker, so the cut is never
    # silent) and re-attach the description whole. It moves to the end in this case only.
    trimmed = _truncate("\n".join(lines), budget.current_work_item)
    return f"# Current Work Item\n\n{trimmed}" + (f"\n{description_line}"
                                                  if description_line else "")


def _render_clarifications(clarifications: list[dict], budget: TokenBudget) -> str:
    """Prior human answers to the agent's questions (req #2 durability). Replayed so a
    re-dispatched run reuses the answer instead of re-asking via `ask_human`.

    Arrives newest first (T13). The same set of questions answered twice is shown once, keeping
    the newest answer (T9): on run `5b4a1bab` a duplicate gate had left the identical ten
    questions answered twice, and the replay alone pushed this section over its cap. Keyed on the
    sorted question ids, so it covers any duplicate that reaches the table however it got there.
    """
    unique: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for c in clarifications:
        ids = tuple(sorted(str(q.get("id")) for q in (c.get("questions") or [])))
        if ids and ids in seen:
            continue
        seen.add(ids)
        unique.append(c)
    clarifications = unique
    shown = clarifications[: budget.max_clarifications]
    lines = [
        "Questions you already asked were answered by a human — **use these answers; do "
        "NOT ask them again**:",
        "",
        "> These answers may come from an EARLIER run of this phase (they persist on the work "
        "item, which is how a re-dispatched run avoids re-asking). If the project has changed "
        "since — new documents adopted, a repository added, a source disconnected — an answer "
        "about *scope* may no longer hold. Trust it unless the evidence in front of you "
        "contradicts it; when it does, say so and ask once rather than reasoning from a stale "
        "answer.",
        "",
    ]
    for c in shown:
        if c.get("context"):
            lines.append(f"_{c['context']}_")
        answers = c.get("answers") or {}
        for q in c.get("questions") or []:
            qid = q.get("id")
            lines.append(f"- {q.get('text', qid)} → **{answers.get(qid, '—')}**")
        lines.append("")
    if len(clarifications) > len(shown):
        lines.append(f"… {len(clarifications) - len(shown)} more not shown (budget).")
    return _section("Answered Clarifications", "\n".join(lines),
                    budget.answered_clarifications,
                    _RECOVERY["answered_clarifications"])


def _render_round(entry: dict, *, current: bool) -> list[str]:
    """One round of the review conversation: what the reviewer asked for, and — for a past
    round — what the agent produced in response, named so it can be re-read on demand."""
    if current:
        lines = ["## What the reviewer wants changed (authoritative)", "",
                 str(entry.get("direction") or "").strip(), ""]
        return lines
    who = entry.get("approver") or "a reviewer"
    when = entry.get("decided_at") or ""
    lines = [f"### Revision {entry.get('revision')} — sent back by {who} {when}".rstrip(), "",
             str(entry.get("direction") or "").strip(), ""]
    produced = entry.get("artifacts") or []
    if produced:
        lines.append("What you produced that round (superseded — call `get_artifact_body` on an "
                     "id to re-read one):")
        for a in produced:
            title = a.get("title") or a.get("type")
            lines.append(f"- {title} [{a.get('type')} v{a.get('version')}] — {a.get('id')}")
        lines.append("")
    return lines


def _render_review_direction(history: list[dict], budget: TokenBudget) -> str:
    """The review conversation for this phase: the CURRENT direction first, then every earlier
    round with the artifacts it produced.

    Deliberately NOT `_truncate`d. That helper cuts from the end, which here would silently
    swallow the newest — i.e. the authoritative — instruction, and a half-read instruction is the
    worst failure this section has. Instead the CURRENT direction is always rendered whole and
    whole OLDEST rounds are dropped until the section fits, with a line saying how many went.
    """
    if not history:
        return ""
    current, earlier = history[-1], history[:-1]
    head = [
        f"You have been through {len(history)} review "
        f"{'round' if len(history) == 1 else 'rounds'} on this phase. Address the direction "
        "below in full. It outranks your default approach and any earlier answered "
        "clarification it contradicts; where it does contradict one, say so in your output "
        "rather than silently choosing. Do not undo what an earlier round asked for unless the "
        "current direction says to.",
        "",
    ]
    body = _render_round(current, current=True)
    if earlier:
        tail_head = ["## Earlier rounds (oldest first)", ""]
        rounds = [_render_round(e, current=False) for e in earlier]
        dropped = 0
        while rounds:
            candidate = "\n".join(head + body + tail_head
                                  + ([f"_{dropped} earlier round(s) omitted to fit._", ""]
                                     if dropped else [])
                                  + [ln for r in rounds for ln in r])
            if estimate_tokens(candidate) <= budget.review_direction:
                break
            rounds.pop(0)          # drop the OLDEST round, never the current direction
            dropped += 1
        if rounds or dropped:
            body = body + tail_head
            if dropped:
                body += [f"_{dropped} earlier round(s) omitted to fit._", ""]
            body += [ln for r in rounds for ln in r]
    return "# Reviewer Direction\n\n" + "\n".join(head + body).rstrip()


def _artifact_ptr_line(a: dict) -> str:
    ptr = a.get("s3_key") or (
        json.dumps(a.get("external_ref")) if a.get("external_ref") else "—"
    )
    return (
        f"- [{a.get('type')} v{a.get('version')}] {a.get('id')} — "
        f"phase={a.get('phase')}, status={a.get('status')}, sor={a.get('sor')}, ptr={ptr}"
    )


def _render_artifacts(
    artifacts: list[dict], budget: TokenBudget, missing_required: list[str] | None = None
) -> str:
    """Render required-first (Bugs S.No 190). The agent's declared inputs (`required: True`) are
    always shown and never truncated by the count budget; only the situational tail is capped.
    Missing declared inputs are named as a gap, and the fetch-by-type fallback (S.No 191) is
    stated before the tail so it survives any token-budget truncation of the section."""
    required = [a for a in artifacts if a.get("required")]
    tail = [a for a in artifacts if not a.get("required")]
    missing_required = missing_required or []
    if not artifacts and not missing_required:
        return _section("Relevant Artifacts", "", budget.relevant_artifacts)
    lines = [
        "Pointers only — fetch full bodies with the platform-state "
        "`get_artifact_body(artifact_id)` tool.",
        "",
    ]
    if required:
        lines.append(
            "**Required inputs for this phase** (your declared upstream dependencies — always "
            "the latest version):"
        )
        lines += [_artifact_ptr_line(a) for a in required]
        lines.append("")
    if missing_required:
        lines.append(
            "**Declared inputs NOT found** (the producing phase may not have run yet — treat as "
            "a gap per `# Rules`): " + ", ".join(f"`{t}`" for t in missing_required)
        )
        lines.append("")
    lines.append(
        "Need an artifact that isn't listed here? Fetch it precisely by type with "
        '`list_artifacts(type="<artifact_type>")`, then `get_artifact_body(id)`.'
    )
    if tail:
        shown = tail[: budget.max_artifacts]
        lines.append("")
        lines.append("**Other recent artifacts** (situational):")
        lines += [_artifact_ptr_line(a) for a in shown]
        if len(tail) > len(shown):
            lines.append(f"… {len(tail) - len(shown)} more not shown (budget).")
    return _section("Relevant Artifacts", "\n".join(lines), budget.relevant_artifacts)


def _render_events(events: list[dict], budget: TokenBudget) -> str:
    if not events:
        return _section("Recent Events", "", budget.recent_events)
    shown = events[: budget.max_events]
    lines = [
        f"- {e.get('ts', '')} · {e.get('actor', '')} · {e.get('action', '')} "
        f"→ {e.get('target_type', '')}:{e.get('target_id', '')}"
        for e in shown
    ]
    if len(events) > len(shown):
        lines.append(f"\n… {len(events) - len(shown)} more not shown (budget).")
    return _section("Recent Events", "\n".join(lines), budget.recent_events,
                    _RECOVERY["recent_events"])


def _render_knowledge(knowledge: list[dict], budget: TokenBudget) -> str:
    if not knowledge:
        return _section(
            "Retrieved Knowledge", "_none (Knowledge Index is Phase 4)_",
            budget.retrieved_knowledge,
        )
    lines = [f"- {k.get('text', json.dumps(k, default=str))}" for k in knowledge]
    return _section("Retrieved Knowledge", "\n".join(lines),
                    budget.retrieved_knowledge,
                    _RECOVERY["retrieved_knowledge"])


def _render_rules(rules: str, budget: TokenBudget) -> str:
    body = rules.strip() or "_(distilled RULE-BEHAVIOR / RULE-EXECUTION wired in P0-T10a)_"
    return _section("Rules", body, budget.rules)


# ── public API ──────────────────────────────────────────────────────
def compose_manifest(
    *,
    context: dict,
    work_item: dict,
    phase: str,
    rules: str = "",
    budget: TokenBudget | None = None,
    review_history: list[dict] | None = None,
    total_budget: int | None = None,
) -> str:
    """Render the composed AGENTS.md. `context` is a `get_context()` result.

    `total_budget` is the whole manifest's allowance, derived from the dispatched model's context
    window (`manifest.budget.total_for_model`). Omit it and every section gets exactly the fixed
    cap it always had — which is what every caller outside the orchestrator does, and why this
    parameter could be added without moving a single existing manifest.

    `review_history` is the phase's review conversation (see `_render_review_direction`); empty or
    None renders nothing at all, so a manifest for a phase nobody has sent back is byte-identical
    to what it was before this parameter existed."""
    return compose_manifest_with_report(
        context=context, work_item=work_item, phase=phase, rules=rules, budget=budget,
        review_history=review_history, total_budget=total_budget,
    )[0]


def compose_manifest_with_report(
    *,
    context: dict,
    work_item: dict,
    phase: str,
    rules: str = "",
    budget: TokenBudget | None = None,
    review_history: list[dict] | None = None,
    total_budget: int | None = None,
) -> tuple[str, dict[str, dict[str, int]]]:
    """`compose_manifest`, plus what each section was allowed and what it asked for.

    The report exists because the truncation event used to say only WHICH section was cut. With a
    fixed cap that was enough; with an allowance that moves, "Retrieved Knowledge was shortened"
    no longer says whether the section was starved or simply enormous, and that is exactly the
    difference somebody tuning this needs to see.
    """
    budget = budget or TokenBudget()

    # Measure, then allocate, then render. The first pass uses a cap nothing can reach, so every
    # section reports what it would WANT; it is a measurement and is never emitted.
    #
    # This is deliberately render-twice rather than splitting all ten renderers into a measuring
    # half and a truncating half. Reading them settled it: the split would have touched every
    # renderer — the single likeliest way to move a byte that nobody intended to move — while the
    # usual objection to rendering twice does not hold here. The one renderer with a loop
    # (`_render_review_direction`) breaks out of it on the first iteration when the cap is
    # unreachable, so the measuring pass costs one join, not a quadratic one. And the two
    # renderers that change LAYOUT when over budget are measured, discarded, and then rendered
    # again against the real allowance, which is the layout that ships.
    if total_budget is None:
        allowances = {}
    else:
        measured = _compose_sections(
            context, work_item, phase, rules, _measuring(budget), review_history)
        demands: dict[str, int] = {}
        for key, text in measured:
            # `project` is claimed by `# Project` AND by `# Repository`/`# Repositories`, which
            # share one cap today. Take the larger rather than the sum, or the floor is counted
            # twice and the total is silently shifted by 2,000 tokens.
            demands[key] = max(demands.get(key, 0), estimate_tokens(text))
        floors = {k: getattr(budget, k) for k in _CANONICAL_ORDER if k in demands}
        allowances = allocate(total_budget, floors, demands)
        budget = replace(budget, **allowances)

    sections = _compose_sections(context, work_item, phase, rules, budget, review_history)
    manifest = "\n\n".join(text for _, text in sections).strip() + "\n"
    report = {
        key: {"allowance": getattr(budget, key), "demand": estimate_tokens(text)}
        for key, text in sections
    }
    return manifest, report


def _measuring(budget: TokenBudget) -> TokenBudget:
    """The same budget with every TOKEN cap raised out of reach, COUNT caps untouched.

    The counts (20 artifacts, 15 events, 20 clarifications) are not elastic and must bound the
    measurement too — otherwise a project with a thousand artifacts would report a demand for a
    section that is never going to render a thousand artifacts.
    """
    return replace(budget, **{k: _MEASURING_CAP for k in _CANONICAL_ORDER})


def _compose_sections(
    context: dict, work_item: dict, phase: str, rules: str,
    budget: TokenBudget, review_history: list[dict] | None,
) -> list[tuple[str, str]]:
    """`(budget key, rendered section)` in the locked order. The single place that decides which
    optional sections are present, so the measuring pass and the real pass can never disagree."""
    profile = context.get("profile") or {}
    repo = context.get("repo")
    repositories = context.get("repositories") or []
    sections: list[tuple[str, str]] = [("project", _render_project(profile, budget))]
    if repo:  # only for a repo-scoped (multi-repo) run — single-repo manifests omit it
        sections.append(("project", _render_repository(repo, budget)))
    elif len(repositories) > 1:
        # project-level run (no single repo) on a multi-repo project — list the assignment
        # options so Task Breakdown can route each work item to the right repo (Option C).
        sections.append(("project", _render_repositories(repositories, budget)))
    sections.append(("important_context", _render_important_context(profile, budget)))
    direction = _render_review_direction(review_history or [], budget)
    if direction:  # only when a reviewer sent this phase back with written direction
        sections.append(("review_direction", direction))
    sections.append(("current_work_item", _render_work_item(work_item, phase, budget)))
    clarifications = context.get("answered_clarifications") or []
    if clarifications:  # only when prior answers exist (req #2 durability) — else omitted
        sections.append(("answered_clarifications", _render_clarifications(clarifications, budget)))
    sections += [
        ("relevant_artifacts", _render_artifacts(
            context.get("relevant_artifacts") or [], budget,
            missing_required=context.get("missing_required_artifacts") or [],
        )),
        ("recent_events", _render_events(context.get("recent_events") or [], budget)),
        ("retrieved_knowledge",
         _render_knowledge(context.get("retrieved_knowledge") or [], budget)),
        ("rules", _render_rules(rules, budget)),
    ]
    return sections
