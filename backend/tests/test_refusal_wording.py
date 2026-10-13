"""Screen Words group 5 — the guard that stops a new developer-text refusal reaching a client.

The sweep found ~60 messages written for whoever wrote the code: lower-case starts, quoted values,
internal keys, raw ids. Rewriting them is only half the job; without a check, the sixty-first
arrives next month. So this scans the source of the modules whose refusals are reachable through
the screens and fails on the patterns that made the old ones unusable.

**What this can and cannot do.** It reads source text, not behaviour, so it cannot know whether a
given string ever reaches a screen. That means it is deliberately scoped:

  - only the files listed in `REACHABLE`, which are the ones the sweep established a normal user
    can provoke. Adding a file here is how you opt its messages in.
  - only the exception types that become an HTTP response a person reads.

A string this flags is not automatically a bug — it is a message nobody has decided about yet.
`# noqa: CLIENT-TEXT` on the line records that decision (with a reason), and is honest in a way
that silently widening the patterns would not be.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

#: Modules whose refusals the sweep established are reachable through the UI. Each entry is a
#: promise that these messages are read by clients, not only by developers.
REACHABLE = [
    # The REST layer itself.
    "api/views.py",
    # Services the REST layer calls, whose refusals it passes straight through.
    "orchestration/trigger.py",
    "orchestration/takeover.py",
    "apps/clarifications/services.py",
    "apps/workitems/cancel.py",
    "apps/gates/services.py",
    "apps/integrations/services.py",
    "apps/projects/repos.py",
    "apps/tenancy/services.py",
    "integrations/drift.py",
    "integrations/extract.py",
    "integrations/onboarding.py",
    "integrations/api_contract.py",
    "integrations/registry.py",
    # Connectors. A failed publish or "Test connection" shows their message on screen.
    "integrations/atlassian/docstore.py",
    "integrations/atlassian/rest.py",
    "integrations/atlassian/tasktracker.py",
    "integrations/figma/designsource.py",
    "integrations/figma/rest.py",
    "integrations/github/codehost.py",
    "integrations/github/rest.py",
    "integrations/xray/rest.py",
    "integrations/xray/testmgmt.py",
    # The accessibility product (Screen Words group 8, team decision 2026-09-21: same rules, this
    # batch). A tester reaches these by pasting a page list, running an audit, reviewing a finding,
    # recording a journey or signing the conformance statement.
    "apps/a11y/routes.py",
    "apps/a11y/baseline.py",
    "apps/a11y/review.py",
    "apps/a11y/journeys.py",
    "apps/a11y/conformance.py",
]
# Deliberately NOT listed, so nobody adds them thinking they were forgotten:
#   - api/runner_views.py — the companion's API, not the browser's. Its callers are the companion
#     daemon and the agent running inside it, and several of its messages are INSTRUCTIONS the
#     agent reads ("the only state you may set is: in_review … done happens only after the merge
#     gate"). Rewriting those as client prose would weaken what the agent is told. The rest land in
#     the companion's terminal log, read by the developer running it — worth a pass of their own,
#     but a different audience from the screens this group is about.
#     Team decision 2026-09-21 (Option A): these stay as they are. Text read by the companion and
#     by the developer running it may be technical; only what reaches a client's screen is held
#     to this check.
#   - apps/a11y/journey.py — its raises answer the agent walking a journey, through its MCP tools,
#     and name those tools on purpose. What the journeys PANEL shows comes from the module's
#     reason constants, which `test_the_journey_panel_reasons_read_as_sentences` checks below.
#   - apps/a11y/policy.py — its messages are about the policy file's own settings
#     (`gate.min_confidence`), read by the admin who wrote that file; naming the setting is the fix.
#   - management commands (apps/*/management/commands) — a developer's terminal, not a screen.
#   - orchestration/*activities*, build_report, phase_report, review_provider — they run inside
#     Temporal workers; a failure there becomes a run's recorded outcome, not a REST refusal.
#     CORRECTED 2026-10-05: this entry used to end "…which the run console presents through its own
#     copy". There was no such copy. The console built every line by mangling the internal action
#     key and appending the first value it found in the payload, so these modules' events DID reach
#     a client's screen as "Review parse mismatch" and worse. The exclusion itself still stands —
#     these are not REST refusals and this file's patterns do not fit them — but the surface is now
#     guarded by `tests/test_event_wording.py`, which checks every event a run owns has a sentence.
#   - ValueError / KeyError / NotImplementedError guards in models and dataclasses — programmer
#     errors that surface as a 500, which the screens already turn into one plain sentence.

#: The exception classes whose argument becomes a sentence on a screen. Anything raised as a
#: different class is a developer-facing fault and is left alone.
CLIENT_FACING = {
    "ValidationError", "NotFound", "ParseError", "PermissionDenied",
    "TriggerError", "ActiveRunError", "NoCompanionError", "ResumeError", "TakeoverError",
    "ClarificationError", "ClarificationRoleError",
    "DriftError", "DriftRoleError", "ExtractionError",
    "OnboardingError", "OnboardingRoleError",
    "GateError", "GateRoleError", "GateConditionsError",
    "IntegrationError", "RepositoryError", "ApiContractError",
    "InvitationError", "ResetError", "RoleError", "SignupError",
    "CapabilityError", "CapabilityUnavailable",
    # The accessibility product (group 8).
    "RouteError", "BaselineError", "ReviewError", "ReviewRoleError", "ReviewLockError",
    "JourneyRunError", "JourneyRoleError", "JourneyError",
    "ConformanceError", "ConformanceRoleError",
}

#: Module helpers that raise one of the classes above for their caller — `_reject("…")` in the
#: accessibility modules. A raise hidden behind one of these is still a refusal a person reads.
REJECT_HELPERS = {"_reject"}

ALLOW = "noqa: CLIENT-TEXT"

# The stored keys that must never appear inside a sentence. Each one was found on a real screen.
INTERNAL_KEYS = re.compile(
    r"\b("
    r"agent_key|to_state|from_state|required_role|work_item_id|run_id|tenant_id|project_id"
    r"|awaiting_gate|needs_answer|in_progress|in_review|test_case|pointer_hash"
    r"|product_owner|tech_lead|qa_lead|security_engineer|release_manager"
    r"|docstore|tasktracker|testmgmt|s3_key|drift_id|clarification_id"
    r")\b"
)

# "user 7f3c…", "(status: running)", "'x.zip'" — the three shapes the sweep found most often.
NAMES_AN_ID = re.compile(
    r"\b(user|run|item|artifact|document|tenant|project)\s+\{\}", re.IGNORECASE)
PARENTHETICAL_STATE = re.compile(r"\(\s*(status|state|kind)\s*:", re.IGNORECASE)
# `{!r}` is repr-interpolation (puts quotes round a raw value); `'{}'` / `"{}"` is the same thing
# done by hand. Both echo a value back at a reader who cannot act on it.
QUOTES_A_VALUE = re.compile(r"\{!r\}|'\{\}'|\"\{\}\"")


def _literal(node: ast.AST) -> str | None:
    """The full text of a string argument, including an f-string's literal parts and a
    concatenation split across source lines."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                # An OPAQUE marker, never the expression source. `f"...{phase_label(agent_key)}"`
                # is a key going correctly THROUGH a label function; scanning the expression
                # flagged that as printing `agent_key`, i.e. it failed the fix it was asking for.
                # What the reader sees is the function's output, which this cannot know — so the
                # position is recorded and its contents are not judged. `!r` is kept, because
                # repr-interpolation puts quotes around a raw value and that IS visible.
                out.append("{!r}" if part.conversion == ord("r") else "{}")
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _client_messages(path: Path) -> list[tuple[int, str]]:
    """Every string raised as a client-facing exception in one module, with its line number."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # A failure RESULT: `{"ok": False, "detail": "…"}` — the shape "Test connection" returns
        # and the screen shows verbatim. It is neither raised nor a Response, so the first version
        # of this scan missed "No connector registered for docstore:notion." entirely.
        if isinstance(node, ast.Dict) and _is_failure_result(node):
            if not any(ALLOW in lines[i] for i in range(node.lineno - 1,
                       min(getattr(node, "end_lineno", node.lineno), len(lines)))):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == "detail":
                        found.extend((node.lineno, text) for text in _sentences(value))
            continue
        # A refusal returned rather than raised: `Response({"detail": "…"}, status=4xx)`. Only the
        # error keys are read, so an ordinary success payload is never mistaken for a message.
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Response":
            if node.args and isinstance(node.args[0], ast.Dict) and _is_error_status(node):
                start = node.lineno - 1
                end = min(getattr(node, "end_lineno", node.lineno), len(lines))
                if any(ALLOW in lines[i] for i in range(start, end)):
                    continue
                for key, value in zip(node.args[0].keys, node.args[0].values, strict=True):
                    if isinstance(key, ast.Constant) and key.value in ("detail", "error", "reason"):
                        found.extend((node.lineno, text) for text in _sentences(value))
            continue
        if (isinstance(node, ast.Call) and getattr(node.func, "id", "") in REJECT_HELPERS):
            start = node.lineno - 1
            end = min(getattr(node, "end_lineno", node.lineno), len(lines))
            if not any(ALLOW in lines[i] for i in range(start, end)):
                for arg in node.args:
                    found.extend((node.lineno, text) for text in _sentences(arg))
            continue
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        call = node.exc
        if not isinstance(call, ast.Call):
            continue
        name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(
            call.func, "id", "")
        if name not in CLIENT_FACING:
            continue

        # The raise may span several lines; an allow-marker anywhere in it opts the whole thing out.
        start = node.lineno - 1
        end = min(getattr(node, "end_lineno", node.lineno), len(lines))
        if any(ALLOW in lines[i] for i in range(start, end)):
            continue

        for arg in call.args:
            found.extend((node.lineno, text) for text in _sentences(arg))
    return found


def _is_failure_result(node: ast.Dict) -> bool:
    """True for a dict literal carrying `"ok": False` — a failed check's result, not a payload."""
    for key, value in zip(node.keys, node.values, strict=True):
        if (isinstance(key, ast.Constant) and key.value == "ok"
                and isinstance(value, ast.Constant) and value.value is False):
            return True
    return False


def _is_error_status(call: ast.Call) -> bool:
    """True when a `Response(...)` is sent with a 4xx/5xx status — written either as a number or
    as DRF's `status.HTTP_4xx_…` names. A Response with no status is a 200 and is not a refusal."""
    for kw in call.keywords:
        if kw.arg != "status":
            continue
        v = kw.value
        if isinstance(v, ast.Constant) and isinstance(v.value, int):
            return v.value >= 400
        text = ast.unparse(v)
        return bool(re.search(r"HTTP_[45]\d\d", text))
    return False


def _sentences(node: ast.AST) -> list[str]:
    """The whole message strings in one argument.

    Takes the OUTERMOST string at each position rather than walking every node: an f-string and a
    split concatenation are one sentence, and `ast.walk` reported each of their literal fragments
    as a message of its own — so `"work item {id} not found"` was flagged three times, twice for
    fragments that begin mid-sentence and could never start with a capital.

    Descends only into the containers DRF accepts, so `ValidationError({"to_state": ["…"]})` is
    read but nothing else is guessed at.
    """
    text = _literal(node)
    if text is not None:
        return [text] if text.strip() else []
    if isinstance(node, ast.Dict):
        return [s for value in node.values for s in _sentences(value)]
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return [s for el in node.elts for s in _sentences(el)]
    return []


ALL_MESSAGES = [
    (rel, line, text)
    for rel in REACHABLE
    for line, text in _client_messages(BACKEND / rel)
]


def test_the_scanner_actually_found_something():
    """A scanner that silently matches nothing passes for ever and guards nothing. If a module is
    renamed or its raises are restructured, this is what says so."""
    assert ALL_MESSAGES, f"no client-facing messages found in {REACHABLE} — the scan is broken"
    covered = {rel for rel, _, _ in ALL_MESSAGES}
    assert covered == set(REACHABLE), f"found no messages in: {sorted(set(REACHABLE) - covered)}"


@pytest.mark.parametrize("rel,line,text", ALL_MESSAGES, ids=lambda v: str(v)[:40])
def test_a_refusal_starts_like_a_sentence(rel, line, text):
    first = text.lstrip()[:1]
    # A message that begins with interpolation is fine — its first word comes from a label.
    if not first or first in "{" or not first.isalpha():
        return
    assert first.isupper(), (
        f"{rel}:{line} starts lower-case, so it reads as a fragment mid-page: {text!r}"
    )


@pytest.mark.parametrize("rel,line,text", ALL_MESSAGES, ids=lambda v: str(v)[:40])
def test_a_refusal_names_no_internal_key(rel, line, text):
    hit = INTERNAL_KEYS.search(text)
    assert not hit, (
        f"{rel}:{line} prints the stored key {hit.group(0)!r}, which means nothing to the person "
        f"reading it — put it through apps.labels: {text!r}"
    )


@pytest.mark.parametrize("rel,line,text", ALL_MESSAGES, ids=lambda v: str(v)[:40])
def test_a_refusal_quotes_no_raw_value_or_id(rel, line, text):
    assert not NAMES_AN_ID.search(text), (
        f"{rel}:{line} names an internal id, which the reader cannot act on: {text!r}"
    )
    assert not PARENTHETICAL_STATE.search(text), (
        f"{rel}:{line} puts a stored state in brackets; say it in words instead: {text!r}"
    )
    assert not QUOTES_A_VALUE.search(text), (
        f"{rel}:{line} quotes a raw value; name the thing rather than echoing it: {text!r}"
    )


def test_the_journey_panel_reasons_read_as_sentences():
    """Group 8: the journeys panel shows these constants as its "why not" line. They are not
    raised, so the scan above cannot see them; this holds them to the same three rules."""
    from apps.a11y import journey

    names = ["NO_JOURNEY_AGENT", "NO_COMPANION", "NO_JOURNEY", "DISPATCH_FAILED", "ALREADY_WALKING",
             "NOT_THE_REVIEWER", "NO_ADDRESS", "RUN_ENDED_UNFINISHED", "NO_REASON_GIVEN",
             "NOT_ASKED", "NOTHING_TO_REPORT"]
    for name in names:
        text = getattr(journey, name)
        first = text.lstrip()[:1]
        assert first == "{" or first.isupper(), f"journey.{name} starts lower-case: {text!r}"
        assert not INTERNAL_KEYS.search(text), f"journey.{name} names a stored key: {text!r}"
        assert not QUOTES_A_VALUE.search(text), f"journey.{name} quotes a raw value: {text!r}"
