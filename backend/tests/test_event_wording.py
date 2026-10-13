"""The guard on what the run console says — Section 4, the message sweep.

Sibling to `test_refusal_wording.py`, which guards a different shape of message and could never
have caught these. That file scans `raise` statements for developer text; a console line is not
raised anywhere and did not exist as a literal at all. `EventSerializer.get_message` built each one
at render time by mangling the internal action key and appending the first value it found in the
payload, so a client watching their own run read lines like:

    Phase dispatched — 06_task_breakdown
    Review parse mismatch — review demands changes but no blocking findings parsed
    Test cases materialize failed — IntegrityError('duplicate key value violates …')
    Run triggered — companion

`test_refusal_wording.py`'s exclusion list said the Temporal activity layer was safe because "a
failure there becomes a run's recorded outcome, which the run console presents through its own
copy". There was no such copy. This file is it.

What it does: walks the backend for every `log_event(...)` call that records an event against a
RUN — the only events any screen fetches — and holds each one to the same rules the refusals are
held to, plus the two that are specific to this surface:

  - every such action must have a sentence (so the thirty-seventh cannot arrive unworded);
  - a tail may only come from a payload key that was read and found to hold words for a person.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from api.serializers import EVENT_SENTENCES, SAFE_TAIL_KEYS, EventWords
from tests.test_refusal_wording import INTERNAL_KEYS, PARENTHETICAL_STATE

REPO = Path(__file__).resolve().parent.parent.parent

#: Where events are written from. `mcp_platform_state` is in here on purpose: the agent's own
#: `register_artifact` tool logs `artifact.registered` against the run, so an agent writes a line
#: on a client's screen.
SOURCES = [REPO / "backend", REPO / "mcp_platform_state"]


def _run_targeted_actions() -> dict[str, str]:
    """Every action recorded against a run, mapped to where it is logged.

    Reads the call rather than the database: an action that fires once a quarter still has to have
    a sentence, and no fixture would cover it.

    `log_event(tenant, actor, action, target_type, target_id, payload)` — so this wants the third
    and fourth arguments, both string literals at every call site. A call whose action or target is
    computed would be invisible here; `test_no_event_action_is_built_dynamically` fails if one
    appears, rather than letting it slip past unnoticed.
    """
    found: dict[str, str] = {}
    for root in SOURCES:
        for path in root.rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in f"/{rel}" or "/migrations/" in rel:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
                    node.func, "id", "")
                if name != "log_event" or len(node.args) < 4:
                    continue
                action, target = node.args[2], node.args[3]
                if not (isinstance(action, ast.Constant) and isinstance(target, ast.Constant)):
                    continue
                if target.value == "run":
                    found[action.value] = f"{rel}:{action.lineno}"
    return found


RUN_ACTIONS = _run_targeted_actions()

# A line that is only its own action key with the punctuation taken out — the exact failure this
# file exists to stop. "phase.empty_result" -> "phase empty result".
#
# Only for keys carrying an UNDERSCORE, and that is a real distinction rather than a loophole. A
# two-word dotted key often flattens into ordinary English by luck: `run.paused` gives "Run paused",
# which is exactly what the team chose to call it, and failing that would be the check marking a
# good sentence wrong. An underscore never flattens into English — it is a compound somebody wrote
# for a machine, and "Phase empty result" or "Review parse mismatch" is always the old defect.
def _is_the_key_in_disguise(action: str, sentence: str) -> bool:
    if "_" not in action:
        return False
    flattened = action.replace(".", " ").replace("_", " ").strip().lower()
    return sentence.strip().lower() == flattened


def test_the_scan_found_the_console_s_events():
    """A guard on the guard. If the scan silently matched nothing — a renamed helper, a moved
    package — every assertion below would pass by vacuum."""
    assert len(RUN_ACTIONS) > 35, f"only found {len(RUN_ACTIONS)}; the scan is probably broken"
    assert "run.triggered" in RUN_ACTIONS and "build.failed" in RUN_ACTIONS


@pytest.mark.parametrize("action", sorted(RUN_ACTIONS))
def test_every_event_a_run_owns_has_a_sentence(action):
    """THE test. Adding an event to a run without adding its words fails here.

    If this fails for something you have just added: put a line in `EVENT_SENTENCES` in
    `api/serializers.py` saying what happened, in the words a client would use. Not the action key.
    """
    assert action in EVENT_SENTENCES, (
        f"{action} is recorded against a run at {RUN_ACTIONS[action]} and so reaches the run "
        f"console, but has no sentence in EVENT_SENTENCES — it would be shown as its own "
        f"internal name."
    )


@pytest.mark.parametrize("action,words", sorted(EVENT_SENTENCES.items()))
def test_each_sentence_reads_as_a_sentence(action: str, words: EventWords):
    said = words.sentence
    assert said, f"{action} has an empty sentence"
    assert said[0].isupper(), f"{action}: a line on a screen starts with a capital — {said!r}"
    assert not _is_the_key_in_disguise(action, said), (
        f"{action}: {said!r} is the action key with its punctuation removed, which is what this "
        f"whole table replaces."
    )
    assert not INTERNAL_KEYS.search(said), f"{action}: a stored key is in the sentence — {said!r}"
    assert not PARENTHETICAL_STATE.search(said), f"{action}: {said!r} echoes a stored state"
    assert "_" not in said, f"{action}: an underscore means a machine word got through — {said!r}"
    assert len(said) < 180, f"{action}: too long for a console line — {said!r}"


@pytest.mark.parametrize("action,words", sorted(EVENT_SENTENCES.items()))
def test_a_tail_comes_only_from_a_key_that_holds_words(action: str, words: EventWords):
    """The half that stops the next leak.

    A tail is either computed, or copied from a key somebody read. `workflow_id`, `execution_mode`,
    `branch`, `phase`, `detail` and `message` were all in the old fallback chain and none of them
    holds a sentence for a client: the first four are machine values, and `message` carries
    `str(exc)` on one action and a developer's note on another.
    """
    if words.tail is None or callable(words.tail):
        return
    assert words.tail in SAFE_TAIL_KEYS, (
        f"{action} appends payload[{words.tail!r}], which is not a key that was checked for "
        f"client wording. Add it to SAFE_TAIL_KEYS only after reading every call site that "
        f"writes it."
    )


def test_a_run_s_events_are_never_logged_under_a_computed_action():
    """What keeps the scan above complete.

    Three call sites do build an action name at runtime — `drift.{kind}.detected`, and the two that
    choose between a pair of names — and all three record against a drift record or a work item,
    neither of which any screen fetches. That is allowed. What is not allowed is a computed action
    on a RUN, because it would be invisible to the scan and would reach the console unworded.

    ONE HOLE THIS CANNOT CLOSE, recorded rather than papered over: `mcp_platform_state/server.py`
    exposes `log_event` to the agent as a tool, so an agent may write any action against any target,
    including a run. Nothing static can check that. It is why `get_message` keeps a fallback that
    humanises an unknown key instead of rendering a blank line.
    """
    offenders = []
    for root in SOURCES:
        for path in root.rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in f"/{rel}" or "/migrations/" in rel:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
                    node.func, "id", "")
                if name != "log_event" or len(node.args) < 4:
                    continue
                action, target = node.args[2], node.args[3]
                targets_a_run = isinstance(target, ast.Constant) and target.value == "run"
                if targets_a_run and not isinstance(action, ast.Constant):
                    offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        f"a run's event is logged under a computed action name, so no check can know what it says: "
        f"{offenders}"
    )


# ── the specific lines that were wrong ──────────────────────────────
def _said(action: str, payload: dict) -> str:
    """What the console would show, without a database row."""
    from api.serializers import EventSerializer

    class _Row:
        pass

    row = _Row()
    row.action, row.payload = action, payload
    return EventSerializer().get_message(row)


def test_a_dispatched_phase_does_not_print_the_agent_key():
    """`phase.dispatched` carries `phase="06_task_breakdown"`, and `phase` was sixth in the old
    fallback chain. The heading above the console already names the phase in words."""
    said = _said("phase.dispatched", {"phase": "06_task_breakdown", "enrollment_id": "abc"})

    assert said == "Sent to your machine"
    assert "06" not in said and "_" not in said


def test_a_triggered_run_does_not_print_a_workflow_id():
    """`workflow_id` was last in the chain, so it was the catch-all: any action whose payload held
    nothing else ended with a Temporal identifier that references nothing a person can look up."""
    said = _said("run.triggered", {"agent_key": "06_task_breakdown",
                                   "workflow_id": "agent-run-3f9a1b2c-dead-beef",
                                   "execution_mode": "companion"})

    assert said == "Started — on your machine"
    assert "3f9a" not in said and "agent-run" not in said


def test_a_failed_test_case_build_does_not_print_the_exception():
    """The worst of them. The call site logs `{"error": str(exc)}` inside a bare except, so a
    database driver's exception text was shown to a client as the explanation."""
    said = _said("test_cases.materialize_failed",
                 {"error": "IntegrityError('duplicate key value violates unique constraint')"})

    assert said == "The test cases couldn't be created from this plan"
    assert "IntegrityError" not in said


def test_an_empty_phase_result_does_not_print_the_developer_s_note():
    """This payload's `message` is a note to whoever wrote the code, and `message` was FIRST in the
    chain — so it beat even the three real sentences that existed."""
    said = _said("phase.empty_result",
                 {"phase": "05_testing", "body_empty": True,
                  "message": "companion reported ok but the engine returned no final text; "
                             "the staged phase draft is empty"})

    assert said == "The agent finished without writing anything — the draft is empty"
    assert "companion reported ok" not in said


def test_a_classified_failure_reason_is_still_shown():
    """The reason the tail was made opt-in rather than deleted. Bugs S.No 139 put the classified
    cause here on purpose; without it a reader sees "Build stopped" and is never told why."""
    assert _said("build.failed", {"reason": "Claude usage limit reached"}) == (
        "Build stopped — Claude usage limit reached")
    assert _said("run.failed", {"error": "The agent ran out of time"}) == (
        "Stopped after a problem — The agent ran out of time")


def test_a_reviewer_s_own_words_are_still_shown():
    """A gate rejection's `comment` is the reviewer writing to the person who will fix it."""
    said = _said("run.rejected", {"comment": "The export is missing the date column",
                                  "superseded_artifacts": ["x"]})

    assert said == "Changes requested at the review gate — The export is missing the date column"


def test_a_historical_log_excerpt_is_not_shown_as_the_reason():
    """Both `run.failed` call sites classify their cause today. The LEDGER IS APPEND-ONLY, so rows
    written before the classifier existed still render — and one in the local database says exactly
    this. Found by rendering every stored event, which is not something a test would have invented.

    A log excerpt gives itself away twice: more than one line, and it names machinery."""
    raw = ("Command failed with exit code 4294967295 (exit code: 4294967295)" + chr(10)
           + "Error output: Check stderr output for details")
    said = _said("run.failed", {"error": raw})

    assert said == "Stopped after a problem", f"a log excerpt reached the screen: {said!r}"

    # One line, but still a log line.
    assert _said("build.failed", {"reason": "process exited with exit code 1"}) == "Build stopped"
    assert _said("run.failed", {"error": "Traceback (most recent call last)"}) == (
        "Stopped after a problem")
    # And the classified sentence it replaced still comes through.
    assert _said("run.failed", {"error": "The PRD phase stopped because the AI engine reached "
                                         "its usage limit. Resume once the limit resets."}) == (
        "Stopped after a problem — The PRD phase stopped because the AI engine reached its usage "
        "limit. Resume once the limit resets.")


def test_an_unrecognised_failure_is_not_explained_with_temporal_s_words():
    """`describe_build_failure` ends with "already a specific message - kept, never lost" and passes
    an unrecognised failure through verbatim. Right for the failure BANNER, which has "Technical
    details" beneath it; a console line has nowhere to put the raw text. The local database holds
    this exact string, which is an internal step name followed by Temporal's own error."""
    assert _said("build.failed", {"reason": "pr/gate setup failed: Activity task failed"}) == (
        "Build stopped")

    # The classified causes this is protecting, all of which still come through.
    for cause in ("the AI engine reached its usage limit", "no changes to commit",
                  "code review kept finding blocking issues", "secret scan blocked the push",
                  "an unexpected error", "no reason was reported"):
        assert _said("build.failed", {"reason": cause}) == f"Build stopped — {cause}"


def test_a_colon_is_not_evidence_of_machinery():
    """The park sites write their tail as "stopped: <cause>" deliberately, and the team's own test
    pins the line it makes. A colon rule looked tidy and would have deleted a designed sentence."""
    assert _said("run.parked", {"reason": "stopped: the AI engine reached its usage limit"}) == (
        "Run paused — stopped: the AI engine reached its usage limit")

    # And a reviewer typing to a colleague may write whatever they like.
    note = "Two things: the date column, and the totals row"
    assert _said("run.rejected", {"comment": note}) == (
        f"Changes requested at the review gate — {note}")


def test_a_tail_cannot_break_the_line_in_two():
    """A console line is one line, and payload text is written by agents and by exception strings,
    so a newline in it is not hypothetical. A copied tail carrying one is refused outright (it is
    a log excerpt — see the test above); the collapsing below is the second line of defence, and it
    is what a computed tail and a one-line value go through."""
    assert _said("build.failed", {"reason": "first line\nsecond line\r\nthird"}) == "Build stopped"

    said = _said("run.rejected", {"comment": "  needs the  date column  "})

    assert "\n" not in said and "\r" not in said
    assert said == "Changes requested at the review gate — needs the date column"


def test_a_very_long_tail_is_cut():
    said = _said("build.failed", {"reason": "x" * 5000})

    assert len(said) < 230


def test_a_review_that_failed_reads_as_stopped():
    """Wording the team chose on 2026-09-21: a failed review report is a review that STOPPED, not
    a report that arrived. The one line whose words depend on its payload."""
    assert _said("review.reported", {"status": "failed"}) == "Code review stopped"
    assert _said("review.reported", {"status": "ok"}) == "Your machine sent its code review back"


def test_two_events_seconds_apart_do_not_say_the_same_thing():
    """`review.reported` (the machine sends its findings) and `build.reviewed` (the platform records
    them) fire seconds apart. Both were first given "Code review finished", which printed the same
    line twice on a real console and threw away the difference between them. A table reads fine and
    a console does not — this was found by opening one."""
    sent = _said("review.reported", {"status": "ok"})
    recorded = _said("build.reviewed", {"findings": 6, "blocking": 2})

    assert sent != recorded
    assert sent == "Your machine sent its code review back"
    assert recorded == "Code review finished — 6 problems, 2 to fix before merging"


def test_counted_tails_say_something_or_nothing():
    """The computed tails degrade to no tail rather than to "attempt None"."""
    assert _said("build.reviewed", {"findings": 0, "blocking": 0}) == (
        "Code review finished — no problems found")
    assert _said("build.reviewed", {"findings": 3, "blocking": 1}) == (
        "Code review finished — 3 problems, 1 to fix before merging")
    assert _said("build.reviewed", {}) == "Code review finished"
    assert _said("phase.reclaimed", {"claim_count": 1}) == "Your machine picked this up again"
    assert _said("phase.reclaimed", {"claim_count": 3}) == (
        "Your machine picked this up again — attempt 3")
    assert _said("manifest.truncated", {"sections": ["Repository map"], "phase": "01_prd"}) == (
        "The agent's briefing was shortened to fit — 1 section shortened")
    assert _said("review.timeout", {"waited_seconds": 1800}) == (
        "The code review didn't finish in time — after 30 minutes")


def test_an_unknown_action_still_shows_something():
    """A historical row whose action no longer exists must not render a blank line — an empty
    console read as "this run has nothing to show" (Bugs.xlsx row 21 iv)."""
    assert _said("some.retired_action", {}) == "Some retired action"
    assert _said("", {}) == "Event"


def test_the_budget_events_read_as_sentences_and_never_name_the_engine():
    """Three lines added with the manifest budget work, all three readable by a client.

    `artifacts.publish_failed` is the one worth remembering: it was added with the publish-loop
    fix and never given a sentence, so it would have reached the run console as "Artifacts publish
    failed" — the internal name, on a client's screen. The scan above is what caught it, which is
    the whole reason that guard exists.

    The engine's model id stays OUT of the visible line. It is in the payload for anyone querying
    events, which is where a machine name belongs; on screen it answers a question the reader did
    not ask and cannot act on.
    """
    assert _said("artifacts.publish_failed", {"count": 1, "artifacts": ["a1"]}) == (
        "Some documents could not be published to your tools — 1 document affected")
    assert _said("artifacts.publish_failed", {"count": 4, "artifacts": []}) == (
        "Some documents could not be published to your tools — 4 documents affected")
    assert _said("artifacts.publish_failed", {}) == (
        "Some documents could not be published to your tools")

    line = _said("manifest.model_unknown",
                 {"model": "claude-sonnet-4-6", "assumed_budget": 10_000})
    assert line == "The briefing was sized for an unfamiliar engine — 10,000 words of room assumed"
    assert "claude" not in line
    assert _said("manifest.model_unknown", {}) == (
        "The briefing was sized for an unfamiliar engine")
