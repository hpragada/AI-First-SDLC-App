"""The four accessibility AI checkers (QA-03) — what each one looks at, and what a
complete answer from it has to contain.

QA-02a built the judge and the tool it writes through; this package supplies the two halves
that were deliberately left out of it:

  * `rules`  — **which elements each checker applies to.** The judge must not be handed every
    node on a page: with ~10 screens per run that is the difference between a viable check and
    exhausting the subscription on `<div>`s that were never going to fail anything.
  * `schema` — **what a failure has to say to be usable.** A `fail` a developer cannot act on
    is not a finding, it is an accusation.

**Where the task text and the code disagree** (recorded in `TASK_BACKLOG_QA.md`, same
correction as QA-02): the task names `backend/a11y/checkers/`. Every module in this codebase
lives under `backend/apps/`, and a Django app has to be registered in `INSTALLED_APPS`, so the
real path is `backend/apps/a11y/checkers/`. The task also specifies "a prompt plus a Pydantic
schema the model must fill" — correction R4 already replaced that: the prompts live in the
`09c_a11y_judge` agent body and the schema is enforced by `record_a11y_finding`, because there
is no direct model call anywhere on this path (#7).

**One copy of the rules, held here** (team decision D-A11Y-6, 2026-08-14). Selection has to run
where the rendered page is — on the developer's own machine, in the companion — because that is
the only place a DOM and a screenshot exist, and because cropping an image per element is only
worth doing for elements that were actually selected. So the companion imports this module
rather than carrying its own copy, exactly as `runner/companion/testresults.py` imports the
platform's one JUnit parser: the companion knows *where* to look, the platform owns *what*
counts. Two copies of a compliance rule set is two rule sets.

Nothing here imports Django, on purpose — the companion adds `backend/` to its path at build
time and must be able to import these rules without a settings module.
"""
from __future__ import annotations

from .rules import (
    CHECKERS,
    HELD_BACK_SELECTION_RULES,
    SELECTION_RULES,
    STYLE_KEYS,
    CapturedElement,
    SelectionRule,
    checkers_for,
    describe_rules,
    explain,
    select,
    settled,
    to_candidate,
)
from .schema import AnswerIncomplete, requirements_for, verify_answer

__all__ = [
    "CHECKERS",
    "HELD_BACK_SELECTION_RULES",
    "SELECTION_RULES",
    "STYLE_KEYS",
    "AnswerIncomplete",
    "CapturedElement",
    "SelectionRule",
    "checkers_for",
    "describe_rules",
    "explain",
    "requirements_for",
    "select",
    "settled",
    "to_candidate",
    "verify_answer",
]
