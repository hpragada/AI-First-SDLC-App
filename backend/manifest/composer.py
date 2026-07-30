"""Manifest Composer (spec §4).

Renders a `get_context()` result + the current work item into an ephemeral `AGENTS.md`
with a FIXED section order and a per-section token budget (prefer retrieval over dumping
the whole profile). Pure: dicts in, markdown string out — written per run, discarded after.

Section order (locked):
  # Project → [# Repository] → # Important Context → # Current Work Item
  → [# Answered Clarifications] → # Relevant Artifacts → # Recent Events
  → # Retrieved Knowledge → # Rules

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
from dataclasses import dataclass
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

    Worst case if every section fills its cap is ~12,150 tokens (~6% of a 200k window); a typical
    run is closer to 3,600. FUTURE: when model selection is exposed to users these should scale
    from the chosen model's context window rather than being fixed — see the brownfield doc.
    """

    project: int = 2000              # was 800  — user-authored profile, measured 906
    important_context: int = 2000    # was 1500 — user-authored, measured 651
    current_work_item: int = 650
    relevant_artifacts: int = 1200   # unbounded growth — cap stays
    recent_events: int = 600         # unbounded growth — cap stays
    retrieved_knowledge: int = 1500  # unbounded growth — cap stays
    rules: int = 3000                # was 1500 — WE author this, same every run; measured 1,706
    answered_clarifications: int = 1200
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


def _section(header: str, body: str, max_tokens: int) -> str:
    body = body.strip() or "_none_"
    return f"# {header}\n\n{_truncate(body, max_tokens)}"


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
    return _section("Project", "\n".join(lines), budget.project)


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
        "Important Context", profile.get("important_context", ""), budget.important_context
    )


def _render_work_item(work_item: dict, phase: str, budget: TokenBudget) -> str:
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
    if wi.get("description"):
        lines.append(f"- description: {wi['description']}")
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
    return _section("Current Work Item", "\n".join(lines), budget.current_work_item)


def _render_clarifications(clarifications: list[dict], budget: TokenBudget) -> str:
    """Prior human answers to the agent's questions (req #2 durability). Replayed so a
    re-dispatched run reuses the answer instead of re-asking via `ask_human`."""
    shown = clarifications[: budget.max_clarifications]
    lines = [
        "Questions you already asked were answered by a human — **use these answers; do "
        "NOT ask them again**:",
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
    return _section("Answered Clarifications", "\n".join(lines), budget.answered_clarifications)


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
    return _section("Recent Events", "\n".join(lines), budget.recent_events)


def _render_knowledge(knowledge: list[dict], budget: TokenBudget) -> str:
    if not knowledge:
        return _section(
            "Retrieved Knowledge", "_none (Knowledge Index is Phase 4)_",
            budget.retrieved_knowledge,
        )
    lines = [f"- {k.get('text', json.dumps(k, default=str))}" for k in knowledge]
    return _section("Retrieved Knowledge", "\n".join(lines), budget.retrieved_knowledge)


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
) -> str:
    """Render the composed AGENTS.md. `context` is a `get_context()` result."""
    budget = budget or TokenBudget()
    profile = context.get("profile") or {}
    repo = context.get("repo")
    repositories = context.get("repositories") or []
    sections = [_render_project(profile, budget)]
    if repo:  # only for a repo-scoped (multi-repo) run — single-repo manifests omit it
        sections.append(_render_repository(repo, budget))
    elif len(repositories) > 1:
        # project-level run (no single repo) on a multi-repo project — list the assignment
        # options so Task Breakdown can route each work item to the right repo (Option C).
        sections.append(_render_repositories(repositories, budget))
    sections += [
        _render_important_context(profile, budget),
        _render_work_item(work_item, phase, budget),
    ]
    clarifications = context.get("answered_clarifications") or []
    if clarifications:  # only when prior answers exist (req #2 durability) — else omitted
        sections.append(_render_clarifications(clarifications, budget))
    sections += [
        _render_artifacts(
            context.get("relevant_artifacts") or [], budget,
            missing_required=context.get("missing_required_artifacts") or [],
        ),
        _render_events(context.get("recent_events") or [], budget),
        _render_knowledge(context.get("retrieved_knowledge") or [], budget),
        _render_rules(rules, budget),
    ]
    return "\n\n".join(sections).strip() + "\n"
