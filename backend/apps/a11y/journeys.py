"""Which path through the app gets keyboard-tested, and where that path comes from (QA-20).

**A journey is a test case the platform already wrote and a human already reviewed** — team
decision D1. Agent 09 emits one `test_case` artifact per case, each carrying a `**Type:**`
line from a fixed vocabulary (`Functional / Integration / E2E / Performance / Security /
Accessibility`), and `E2E` is the platform's own word for "a complete user journey". SpendLog
already has one: *TC-031 — E2E: Complete Registration to First Expense to Dashboard Journey*.

The two alternatives were rejected for the same reason, and it is worth writing down because
both look reasonable:

  * **The `user_journey` artifact from the design phase.** It is a design document, written
    before the application existed, and it drifts the moment the build diverges from it.
    Walking it would keyboard-test a path the app may no longer have.
  * **The registered route list (QA-17).** A list of pages is not a journey. Every failure this
    task looks for happens *between* steps — focus moving, a dialog opening, a status message
    firing — so a route list loses the whole point while looking like it covers more.

Reusing the test case also means the keyboard walk follows the **same path the functional test
follows**, so a journey that changes changes in one place.

**Step parsing is this module's own, and differs from `integrations.export_tests` in two ways
that both matter here and neither of which matters there.**

  * *No synthetic fallback.* That module's last resort is a single made-up step ("Execute the
    test case as documented in the platform artifact") so an export always succeeds. Here a
    journey with no readable steps must NOT be walked at all: an agent handed one vague
    instruction will report *something*, and that something would enter the ledger as a real
    result. No steps means `is_walkable` is False and the caller says so out loud.
  * *A step index is not an action.* In a `| Step | Action | Expected |` table the shared
    parser accepts the `Step` column, which holds the row number. For an export that is merely
    unhelpful; here it would produce a journey whose steps are "1" and "2" for the agent to
    perform. `_table_steps` prefers a real action column and drops bare numbers.

Both are local rather than fixes to the shared parser, because that parser feeds the TestMgmt
export and changing it would change how every already-exported test reads in a client's
tracker.
"""
from __future__ import annotations

import re

from apps.tenancy.context import tenant_context
from apps.workitems.test_cases import declared_type
from integrations.types import A11yJourney, A11yJourneyStep

#: The `**Type:**` value that marks a test case as a journey. Agent 09's own vocabulary — see
#: `agents/09_testing/agent.md` ("Type: [Functional / Integration / E2E / ...]"). Matched
#: case-insensitively because the value is prose written by an agent, not an enum.
JOURNEY_TYPE = "e2e"

#: The artifact phase/type agent 09 registers test cases under.
TEST_CASE_PHASE = "testing"
TEST_CASE_TYPE = "test_case"

#: How many journeys one project may queue at once. A journey is an agent run driving a real
#: browser through every step — far more expensive than a batched element judgment — so the
#: cap is small and deliberate. Mirrors `dispatch.caps_for` in spirit: bounded work, and the
#: excess is *reported*, never silently dropped.
MAX_JOURNEYS = 10

#: `{{1,6}}` is doubled because this template goes through `str.format` — a single `{1,6}` is
#: read as a field name and raises rather than matching a heading.
_SECTION = r"^#{{1,6}}\s*{name}\s*$"
_STEP_LINE = re.compile(r"^\s*(?:step\s*)?(\d+)[.):]\s+(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+(.+?)\s*$", re.MULTILINE)
#: A route named inside a step ("navigate to /checkout"). Only used when the step names one —
#: guessing a route from prose would put a finding on the wrong screen, which is worse than
#: leaving it blank and letting the agent report where it actually was.
_ROUTE = re.compile(r"(?<![\w.])(/[A-Za-z0-9][-\w/]*)")

#: Bounds on what is read out of one body, so a runaway artifact cannot produce a journey with
#: ten thousand steps or a step the size of a page.
MAX_STEPS = 40
MAX_STEP_CHARS = 500
MAX_PRECONDITIONS = 20


class JourneyError(ValueError):
    """Asked for a journey that does not exist, or that cannot be walked."""


def _section(body: str, name: str) -> str:
    """The text under a `### <name>` heading, up to the next heading of any level.

    Scoped rather than whole-body on purpose: `Preconditions`, `Expected Result` and
    `Test Data` all contain numbered and bulleted lines, and a body-wide scrape would fold
    them into the step list. A journey whose "steps" include its own expected result would
    have the agent trying to *perform* an assertion.
    """
    start = re.search(_SECTION.format(name=re.escape(name)), body or "",
                      re.IGNORECASE | re.MULTILINE)
    if start is None:
        return ""
    rest = body[start.end():]
    nxt = re.search(r"^#{1,6}\s+\S", rest, re.MULTILINE)
    return rest[:nxt.start()] if nxt else rest


def is_journey(body: str) -> bool:
    """Whether this test case is a walkable journey, from its own `**Type:**` line.

    A case that declares no type is **not** treated as one. The vocabulary is agent 09's and
    every case it writes carries a type; a body without one is either hand-written or from
    another producer, and assuming "journey" about an unknown document is how a login-only
    smoke test ends up being walked as a critical path. `declared_type` is the platform's one
    reader of that line and lives in `apps.workitems.test_cases` (G2), which is where test
    cases are owned — this module asks it a question, it does not parse the line itself.
    """
    return JOURNEY_TYPE in declared_type(body).split()


def _route_in(text: str) -> str:
    match = _ROUTE.search(text or "")
    return match.group(1) if match else ""


#: Header words that name the column holding what to *do*. `step` is deliberately absent and
#: handled separately: in a `| Step | Action | Expected |` table it is the row NUMBER, and the
#: shared export parser accepts it as the action — which for an export is harmless and for a
#: journey produces steps called "1" and "2" that the agent would then try to perform.
_ACTION_HEADERS = ("action", "description", "instruction", "operation")
_BARE_NUMBER = re.compile(r"^\W*\d+\W*$")


def _table_steps(text: str) -> list[str]:
    """Actions from a GFM steps table, preferring a real action column over a step index.

    Deliberately a few lines here rather than a change to `integrations.export_tests`: that
    parser feeds the TestMgmt export, where taking the index column is merely unhelpful. Here
    it would be wrong, and widening the shared parser to fix this case would change what every
    existing exported test looks like in the client's tracker.
    """
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if "|" not in line or i + 1 >= len(lines) or "-" not in lines[i + 1]:
            continue
        header = [h.strip().lower() for h in line.strip().strip("|").split("|")]
        column = next((j for j, h in enumerate(header)
                       if any(word in h for word in _ACTION_HEADERS)), None)
        if column is None:
            column = next((j for j, h in enumerate(header) if h in ("step", "steps")), None)
        if column is None:
            continue
        found = []
        for row in lines[i + 2:]:
            if "|" not in row:
                break
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if column >= len(cells) or not cells[column]:
                continue
            # A cell that is only a number is an index that slipped through, never an action.
            if _BARE_NUMBER.match(cells[column]):
                continue
            found.append(cells[column])
        if found:
            return found
    return []


def parse_steps(body: str) -> list[A11yJourneyStep]:
    """The journey's steps, in the order the test case wrote them.

    Numbered lines under `Test Steps` first, then a steps table, then — only if neither
    section exists — numbered lines anywhere. No synthetic fallback: see the module docstring.
    """
    section = _section(body, "Test Steps") or _section(body, "Steps")
    numbered = [(int(m.group(1)), m.group(2)) for m in _STEP_LINE.finditer(section)]
    if not numbered:
        numbered = [(i, text) for i, text in enumerate(_table_steps(section or body or ""), 1)]
    if not numbered and not section:
        # Last resort *within the body*, never a made-up step: some producers write the steps
        # without a heading. Two or more, so a stray "1." in prose is not mistaken for a walk.
        found = [(int(m.group(1)), m.group(2)) for m in _STEP_LINE.finditer(body or "")]
        numbered = found if len(found) >= 2 else []

    steps: list[A11yJourneyStep] = []
    for position, (_, text) in enumerate(numbered[:MAX_STEPS], start=1):
        clean = " ".join(str(text).split())[:MAX_STEP_CHARS]
        if not clean:
            continue
        # Renumbered by position, not by the number in the text: a body that jumps 1, 2, 4 or
        # restarts at 1 would otherwise produce duplicate or missing step keys, and the step
        # number is what the reconciliation subtracts against.
        steps.append(A11yJourneyStep(number=position, text=clean, route=_route_in(clean)))
    return steps


def parse_preconditions(body: str) -> list[str]:
    section = _section(body, "Preconditions")
    found = [" ".join(m.group(1).split()) for m in _BULLET.finditer(section)]
    return [line[:MAX_STEP_CHARS] for line in found if line][:MAX_PRECONDITIONS]


def journey_from(artifact, body: str) -> A11yJourney:
    """One `test_case` artifact + its body → the journey to walk. Never raises."""
    from integrations.export_tests import _summary_for

    ref = artifact.external_ref or {}
    test_ref = str(ref.get("tc_id") or ref.get("id") or ref.get("test_ref") or "").strip()
    return A11yJourney(
        test_ref=test_ref,
        title=(artifact.title or _summary_for(artifact, body or "")).strip(),
        steps=tuple(parse_steps(body or "")),
        preconditions=tuple(parse_preconditions(body or "")),
        artifact_id=str(artifact.id),
    )


def _stated_type(artifact) -> str:
    """The `Type:` a producer stamped on the artifact itself, or `""` when it did not (G6b).

    **Why not `test_cases.declared_fields`**, which is the platform's reader of this pair: it
    falls back to the artifact's BODY when the stamp is missing, which is right for its callers
    and wrong here — this module then reads the same body again for the steps. So the cheap half
    is read directly and the fallback stays this module's own `is_journey(body)`.

    What this buys: a project with ninety test cases and three journeys used to cost ninety
    object-store reads to find the three. Where the Testing agent stamped the type — which it
    does — the other eighty-seven are now skipped without being opened. Where it did not, the
    body is read exactly as before, so this is never worse.
    """
    return str((artifact.external_ref or {}).get("type") or "").strip().lower()


def _test_case_artifacts(tenant_id, project_id) -> list:
    """The newest version of every test-case artifact in the project."""
    from apps.registry.models import Artifact

    with tenant_context(tenant_id):
        rows = list(
            Artifact.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    phase=TEST_CASE_PHASE, type=TEST_CASE_TYPE)
            .order_by("title", "-version", "-created_at")
        )
    newest: dict[str, object] = {}
    for row in rows:
        newest.setdefault(row.title or str(row.id), row)
    return list(newest.values())


def journeys_for_project(tenant_id, project_id, *, object_store=None) -> dict:
    """Every walkable journey in a project, plus what was found and rejected.

    Returns `{"journeys": [...], "skipped": [...], "over_cap": [...]}` rather than a bare list.
    "We found no journeys" and "we found four and could not read three of them" are different
    facts about a project, and a caller that only ever sees a list cannot tell them apart —
    which is how an app with no keyboard coverage comes to look like an app with no keyboard
    problems.
    """
    from mcp_platform_state import tools

    journeys: list[A11yJourney] = []
    skipped: list[dict] = []
    over_cap: list[str] = []
    for artifact in _test_case_artifacts(tenant_id, project_id):
        # A case the producer stamped as something other than E2E is not a journey and its body
        # is never opened. Only an unstamped case costs a read to find that out.
        stated = _stated_type(artifact)
        if stated and JOURNEY_TYPE not in stated.split():
            continue
        read = tools.get_artifact_body(tenant_id, str(artifact.id), object_store=object_store)
        body = (read or {}).get("body") or ""
        if not body.strip():
            skipped.append({"artifact_id": str(artifact.id), "title": artifact.title,
                            "reason": (read or {}).get("error")
                            or "the test case has no readable body"})
            continue
        if not is_journey(body):
            continue
        journey = journey_from(artifact, body)
        if not journey.is_walkable:
            skipped.append({"artifact_id": str(artifact.id), "title": artifact.title,
                            "test_ref": journey.test_ref,
                            "reason": "the test case declares Type: E2E but no steps could be "
                                      "read from it, so there is no journey to walk"})
            continue
        if len(journeys) >= MAX_JOURNEYS:
            over_cap.append(journey.test_ref or journey.title)
            continue
        journeys.append(journey)
    return {"journeys": journeys, "skipped": skipped, "over_cap": sorted(over_cap)}


def journey_for(tenant_id, project_id, test_ref: str, *, object_store=None) -> A11yJourney:
    """One named journey. Raises `JourneyError` naming what was available instead."""
    wanted = (test_ref or "").strip().lower()
    found = journeys_for_project(tenant_id, project_id, object_store=object_store)
    for journey in found["journeys"]:
        if journey.test_ref.lower() == wanted or journey.title.lower().startswith(wanted):
            return journey
    available = ", ".join(j.test_ref or j.title for j in found["journeys"]) or "none"
    raise JourneyError(
        f"No journey {test_ref} can be walked in this project. The ones that can: {available}."
    )
