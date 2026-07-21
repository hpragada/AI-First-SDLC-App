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


@dataclass
class TokenBudget:
    """Per-section caps (in estimated tokens) + count caps for list sections."""

    project: int = 800
    important_context: int = 1500
    current_work_item: int = 300
    relevant_artifacts: int = 1200
    recent_events: int = 600
    retrieved_knowledge: int = 1500
    rules: int = 1500
    answered_clarifications: int = 1200
    max_artifacts: int = 20
    max_events: int = 15
    max_clarifications: int = 20


def estimate_tokens(text: str) -> int:
    return -(-len(text) // _CHARS_PER_TOKEN)  # ceil(len/4)


def _truncate(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + _TRUNCATED


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


def _render_artifacts(artifacts: list[dict], budget: TokenBudget) -> str:
    if not artifacts:
        return _section("Relevant Artifacts", "", budget.relevant_artifacts)
    shown = artifacts[: budget.max_artifacts]
    lines = [
        "Pointers only — fetch full bodies with the platform-state "
        "`get_artifact_body(artifact_id)` tool.",
        "",
    ]
    for a in shown:
        ptr = a.get("s3_key") or (
            json.dumps(a.get("external_ref")) if a.get("external_ref") else "—"
        )
        lines.append(
            f"- [{a.get('type')} v{a.get('version')}] {a.get('id')} — "
            f"phase={a.get('phase')}, status={a.get('status')}, sor={a.get('sor')}, ptr={ptr}"
        )
    if len(artifacts) > len(shown):
        lines.append(f"\n… {len(artifacts) - len(shown)} more not shown (budget).")
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
        _render_artifacts(context.get("relevant_artifacts") or [], budget),
        _render_events(context.get("recent_events") or [], budget),
        _render_knowledge(context.get("retrieved_knowledge") or [], budget),
        _render_rules(rules, budget),
    ]
    return "\n\n".join(sections).strip() + "\n"
