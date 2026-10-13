"""Client-facing words for the platform's internal keys.

Screen Words Sweep, groups 2/3/5. A refusal that reaches a person must not name a role as
`product_owner`, a status as `staged`, a capability as `docstore` or a phase as
`06_task_breakdown`. Those are storage keys; they mean nothing to the client whose screen
they land on, and the platform has a standing rule against printing them.

Everything here reads from the enum or the map that already defines the value, so there is
never a second copy to keep in step:

  - `role_label` reads `apps.base.Role.choices`, which already carries "Product Owner".
  - `artifact_status_label` mirrors the frontend's `artifactStatus.tsx` word-for-word, so a
    status cannot read one way in a banner and another way in the list behind it.

The fallback humanizes the raw token instead of guessing at a friendlier name: a key added
later reads a little stiffly rather than being labelled as something it is not.
"""
from apps.base import Role

_ROLE_LABELS = dict(Role.choices)


def humanize(token: str | None) -> str:
    """`task_breakdown` -> `Task breakdown`. Underscores out, first word capitalized."""
    if not token:
        return ""
    words = str(token).replace("_", " ").strip()
    return words[0].upper() + words[1:] if words else ""


def role_label(key: str | None) -> str:
    """"product_owner" -> "Product Owner". Unknown keys are title-cased, not invented."""
    if not key:
        return "a reviewer with the right role"
    known = _ROLE_LABELS.get(str(key))
    if known:
        return known
    return " ".join(w.capitalize() for w in str(key).split("_") if w)


# Mirrors frontend/src/features/observability/artifactStatus.tsx. `staged` is the one that
# matters: it means a named person has been asked to decide on this document, and the
# platform's own word for it says nothing about anyone having to act.
_ARTIFACT_STATUS_LABELS = {
    "published": "Published",
    "approved": "Approved",
    "staged": "Waiting for approval",
    "superseded": "Superseded",
    "draft": "Draft",
}


def artifact_status_label(status: str | None) -> str:
    return _ARTIFACT_STATUS_LABELS.get(str(status or ""), humanize(status))


# Capabilities, not vendors (#9). The vendor behind each one is whatever connector the
# tenant has bound, so it is deliberately not named here.
_CAPABILITY_LABELS = {
    "internal": "the platform",
    "docstore": "the documentation store",
    "tasktracker": "the task tracker",
    "testmgmt": "test management",
    "codehost": "the code host",
    "designtool": "the design tool",
}


def capability_label(capability: str | None) -> str:
    return _CAPABILITY_LABELS.get(str(capability or ""), humanize(capability))


# Mirrors the RUN_STATUS map in frontend/src/labels.ts. Both exist because both sides print
# these: the screens from the run row, the backend inside refusals like "this work item already
# has a run, and it is waiting for approval".
_RUN_STATUS_LABELS = {
    "pending": "Queued",
    "running": "Running",
    "awaiting_gate": "Waiting for approval",
    "approved": "Approved",
    "completed": "Completed",
    "rejected": "Changes requested",
    "failed": "Failed",
    # These two are kept deliberately unalike. `stalled` used to read "Paused — your machine
    # stopped reporting", which was a fair description until a run could genuinely be PAUSED by a
    # person, at which point two different states both said "Paused" and the one word no longer
    # told the reader whether anything was wrong. `stalled` is something that happened TO them;
    # `paused` is something they did.
    "stalled": "Stopped — your machine stopped reporting",
    "paused": "Paused by you",
}


def run_status_label(status: str | None) -> str:
    """Every member of `Run.Status`, taken from the enum rather than from memory — the first pass
    here guessed at the set, invented two statuses and missed `pending`, which is the one a
    refusal about a just-started run actually needs."""
    return _RUN_STATUS_LABELS.get(str(status or ""), humanize(status))


def work_item_state_label(state: str | None) -> str:
    """`in_progress` -> `In Progress`, from `WorkItem.State` — the board's own column names."""
    from apps.workitems.models import WorkItem

    return dict(WorkItem.State.choices).get(str(state or ""), humanize(state))


def work_item_type_label(wi_type: str | None) -> str:
    """`test_case` -> `Test Case`, from `WorkItem.Type`."""
    from apps.workitems.models import WorkItem

    return dict(WorkItem.Type.choices).get(str(wi_type or ""), humanize(wi_type))


# The words that are acronyms or have a set spelling. The backend catalog stores only snake-case
# keys (`prd`, `ux_design`, `cicd`) — the display names live in the frontend's PLANNING_PHASES —
# so plain title-casing produced "Prd", "Ux Design" and "Cicd" inside refusals. That was caught
# by the export-policy refusal reading "Prd documents can be published…". These words make the
# backend spell every phase exactly as frontend/src/types.ts does.
_PHASE_WORDS = {"prd": "PRD", "ux": "UX", "cicd": "CI/CD", "api": "API", "a11y": "Accessibility"}
# Whole names the frontend shows that can't be derived word by word from the key.
_PHASE_NAMES = {"intelligent_context_extractor": "Context Extraction"}


def phase_label(phase: str | None) -> str:
    """`06_task_breakdown` -> `Task Breakdown`, `03_prd` -> `PRD`, `11_cicd` -> `CI/CD` —
    spelled as the frontend phase catalog spells it."""
    if not phase:
        return ""
    bare = str(phase)
    # Strip the "NN[x]_" ordinal the agent keys carry.
    if "_" in bare:
        head, _, rest = bare.partition("_")
        if head[:1].isdigit():
            bare = rest
    if bare in _PHASE_NAMES:
        return _PHASE_NAMES[bare]
    return " ".join(
        _PHASE_WORDS.get(w.lower(), w.capitalize() if w.islower() else w)
        for w in bare.split("_") if w
    )
