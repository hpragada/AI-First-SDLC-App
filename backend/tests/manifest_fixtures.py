"""The manifest shapes the golden byte-equality test composes.

`tests/golden/manifest/*.md` was captured from the code as it stood BEFORE the elastic budget
existed; `test_manifest_budget.py` composes the same shapes today and asserts the bytes still
match. Regenerate deliberately with `UPDATE_MANIFEST_GOLDENS=1 pytest tests/test_manifest_budget.py`
— and read the diff before committing it, because a changed golden is the one signal that a
manifest somebody already relies on has moved.

That pairing is the safety net for the whole budget change. The promise is narrow and absolute:

    compose_manifest(..., total_budget=None)  renders exactly what it rendered before.

Every existing caller omits `total_budget`, so the goldens cover the entire pre-change surface —
including the cases that truncate, which is where a refactor of the renderers would show up first.

The shapes deliberately include the awkward ones rather than only the tidy ones: a context whose
optional keys are absent (the composer reads them with `.get(... ) or []`), a repo-scoped run, a
multi-repo project-level run, sections far over their cap, and a work item whose description is the
part that must survive whole (T2).
"""
from __future__ import annotations

# A paragraph that is cheap to repeat and easy to eyeball in a diff.
_LOREM = ("The leave policy applies to all permanent staff. Carryover is capped at five days "
          "and lapses on 31 March. ")


def _profile(**over) -> dict:
    p = {
        "name": "PeopleDesk", "track": "greenfield", "repo_topology": "single",
        "domain": "hr", "version": 3, "description": "leave and attendance",
        "tech_stack": {"backend": "django", "frontend": "react"},
        "coding_standards": {"python": "ruff"}, "nfrs": {"p95_ms": 300},
        "constraints": {"auth": "email + password only"}, "glossary": {"WI": "work item"},
        "important_context": "ALWAYS prefer retrieval over dumping the profile.",
    }
    p.update(over)
    return p


def _artifact(i: int, *, required: bool = False, **over) -> dict:
    a = {
        "id": f"a{i}", "type": "requirements", "version": 1, "phase": "requirements",
        "status": "published", "sor": "internal", "s3_key": f"s3://b/req{i}.md",
        "external_ref": None, "required": required,
    }
    a.update(over)
    return a


def _event(i: int, **over) -> dict:
    e = {"ts": f"2026-06-22T10:{i:02d}:00", "actor": "system", "action": "run.completed",
         "target_type": "run", "target_id": f"r{i}"}
    e.update(over)
    return e


def _work_item(**over) -> dict:
    wi = {
        "id": "wi-1", "type": "story", "state": "in_progress", "feature_stream": "leave",
        "parent_id": None, "depends_on": ["wi-0"], "repo_id": None, "takeover_flag": False,
        "title": "Leave policy configuration API and screen",
    }
    wi.update(over)
    return wi


def _clarification(n: int, *, answered: str) -> dict:
    return {
        "context": f"Round {n}",
        "questions": [{"id": f"q{n}a", "text": "What is the carryover cap?"},
                      {"id": f"q{n}b", "text": "Who approves a manager's leave?"}],
        "answers": {f"q{n}a": "Five days.", f"q{n}b": "The department head."},
        "answered_at": answered,
    }


def _round(n: int, *, direction: str) -> dict:
    return {"revision": n, "direction": direction, "reviewer": "lead", "at": f"2026-10-0{n}"}


#: name -> kwargs for `compose_manifest`. Ordered so a diff reads from simplest to hairiest.
CASES: dict[str, dict] = {}


def _case(name: str, **kwargs) -> None:
    kwargs.setdefault("rules", "RULE-BEHAVIOR: zero hallucination.\nRULE-EXECUTION: Tier 1 first.")
    CASES[name] = kwargs


# 1 — the plain single-repo run. Nothing optional, nothing over its cap.
_case("plain",
      context={"profile": _profile(), "relevant_artifacts": [_artifact(1)],
               "recent_events": [_event(1)], "retrieved_knowledge": []},
      work_item=_work_item(), phase="prd")

# 2 — optional keys ABSENT, not empty. `test_multi_repo`'s own factory omits these, so the
#     present-set computation has to tolerate it exactly as `.get(...) or []` does today.
_case("sparse_context",
      context={"profile": _profile()},
      work_item=_work_item(), phase="ideation")

# 3 — repo-scoped run: renders `# Repository`, which caps against `budget.project`.
_case("repo_scoped",
      context={"profile": _profile(repo_topology="multi"),
               "repo": {"id": "r1", "name": "peopledesk-api", "role": "backend",
                        "base_branch": "main", "is_default": True, "stack": {"lang": "python"}},
               "relevant_artifacts": [_artifact(1, required=True), _artifact(2)],
               "recent_events": [_event(1), _event(2)], "retrieved_knowledge": []},
      work_item=_work_item(repo_id="r1"), phase="implementation")

# 4 — multi-repo PROJECT-level run: renders `# Repositories`, the other consumer of that same cap.
#     Both shapes are here because mis-counting that shared floor is the double-count trap.
_case("multi_repo_project_level",
      context={"profile": _profile(repo_topology="multi"),
               "repositories": [
                   {"id": "r1", "name": "peopledesk-api", "role": "backend", "is_default": True},
                   {"id": "r2", "name": "peopledesk-web", "role": "frontend", "is_default": False},
               ],
               "relevant_artifacts": [_artifact(1)], "recent_events": [_event(1)],
               "retrieved_knowledge": []},
      work_item=_work_item(), phase="task_breakdown")

# 5 — answered clarifications + retrieved knowledge present.
_case("clarifications_and_knowledge",
      context={"profile": _profile(),
               "relevant_artifacts": [_artifact(1)], "recent_events": [_event(1)],
               "answered_clarifications": [_clarification(2, answered="2026-10-02T09:00:00"),
                                           _clarification(1, answered="2026-10-01T09:00:00")],
               "retrieved_knowledge": [
                   {"text": _LOREM * 3, "artifact_id": "a1", "repo_id": None,
                    "source": "artifact", "score": 0.9},
                   {"text": _LOREM * 3, "artifact_id": "a2", "repo_id": None,
                    "source": "artifact", "score": 0.7},
               ]},
      work_item=_work_item(), phase="implementation")

# 6 — `# Retrieved Knowledge` OVER its 1,500-token cap: eight chunks at ~1,200 chars is the exact
#     shape that truncates on every real dispatch (T3). This golden is the one that proves the
#     pre-change loss was real, and it must keep truncating while `total_budget=None`.
_case("knowledge_over_cap",
      context={"profile": _profile(),
               "relevant_artifacts": [_artifact(1)], "recent_events": [_event(1)],
               "retrieved_knowledge": [
                   {"text": _LOREM * 12, "artifact_id": f"a{i}", "repo_id": None,
                    "source": "artifact", "score": 1.0 - i / 10}
                   for i in range(8)
               ]},
      work_item=_work_item(), phase="code_review")

# 7 — the T2 shape: a long description whose ACCEPTANCE CRITERIA live at its end. The metadata
#     obeys the cap; the description must come through whole.
_case("long_description",
      context={"profile": _profile(), "relevant_artifacts": [_artifact(1)],
               "recent_events": [_event(1)], "retrieved_knowledge": []},
      work_item=_work_item(
          description=(_LOREM * 200)
          + "\n\nAcceptance criteria:\n- CORS must allow the web origin."),
      phase="implementation")

# 8 — reviewer direction present, several rounds, plus crowded growing sections. The review
#     renderer drops whole OLDEST rounds rather than cutting, and sits above everything capped.
_case("review_direction_and_crowding",
      context={"profile": _profile(important_context=_LOREM * 40),
               "relevant_artifacts": [_artifact(i, required=i < 3) for i in range(30)],
               "missing_required_artifacts": ["architecture"],
               "recent_events": [_event(i) for i in range(25)],
               "retrieved_knowledge": [
                   {"text": _LOREM * 4, "artifact_id": f"a{i}", "repo_id": None,
                    "source": "artifact", "score": 0.5} for i in range(4)
               ]},
      work_item=_work_item(), phase="implementation",
      review_history=[_round(n, direction=_LOREM * 20) for n in range(1, 6)])
