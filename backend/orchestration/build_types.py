"""BuildWorkflow payloads (Phase-2 §4). Django-free so the workflow sandbox can import
them without the ORM (same rule as `types.py`)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuildInput:
    """One build run = one BuildWorkflow. The companion runs the agent locally and reports
    back; the platform opens the PR and (on the merge gate) merges."""

    run_id: str
    tenant_id: str
    project_id: str
    work_item_id: str
    agent_spec_id: str
    work_item_key: str          # branch name + run prompt
    repo: str                   # "owner/name"
    base: str                   # base branch the worktree forks from
    # The work item's human title, for anything a PERSON reads: artifact titles and the PR title
    # (Bugs S.No 151). Never use work_item_key for display — it is a branch slug, and when the
    # item has no SoR id it falls back to "WI-<uuid8>", which is meaningless to a reader. Passed
    # in on the input (not read from the DB inside an activity) to keep activities deterministic.
    work_item_title: str = ""
    phase: str = "implementation"
    gate_type: str = "merge_gate"
    required_role: str = "reviewer"      # D6: the merge gate is a reviewer's call
    # If the companion (a laptop) never reports within this window, park for takeover.
    report_timeout_seconds: int = 7200
    # How long the review activity waits for the companion's 08 verdict before giving up and
    # falling through to the merge gate with no findings (Bugs S.No 110). Must comfortably
    # exceed a realistic FIRST review on a cold companion (engine cold-start + context
    # compaction can add several minutes) — 480s was too tight and skipped the remediation loop.
    review_timeout_seconds: int = 1800
    # 07<->08 remediation loop: cap re-review cycles before escalating (§5).
    max_remediation_cycles: int = 3
    # Which enrolled companion to dispatch to (the triggering user's), so the build is
    # claimable via /api/runner/work/ like a planning phase (req #1).
    enrollment_id: str | None = None
    # Bugs S.No 161: when remediation exhausts its cycles, the build auto-retries as a FRESH
    # run (new agent context, no compounding bad decisions) instead of hard-failing with no
    # recourse — `attempt` counts which try this is; auto-retry stops at `max_auto_attempts`
    # and parks for a human only then (mirrors the merge-conflict/park patterns already in this
    # workflow, so a human is the last resort, never the first response to one failure).
    attempt: int = 1
    max_auto_attempts: int = 2
    # A human-readable digest of what blocked prior attempts (file/line/severity/title), fed
    # into the next attempt's manifest so the agent doesn't walk into the same wall blind.
    prior_attempt_context: str = ""


@dataclass
class BuildReport:
    """What the companion posts back after running the build locally (signal payload)."""

    status: str = "ok"          # "ok" | "failed"
    branch: str = ""
    head_sha: str = ""
    changed_files: list = field(default_factory=list)
    message: str = ""
    # The suite's own JUnit results from the worktree (D4: the companion worktree executes
    # tests; results are imported on report). [{test_ref, status, evidence}] — a summary, never
    # result bodies (#1/#3). The companion reports what it found for EVERY build; the control
    # plane decides which phases actually import them (catalog `imports_test_results`), so the
    # companion stays dumb and the routing rule lives in one place.
    test_results: list = field(default_factory=list)
    test_summary: str = ""      # "12 passed, 1 failed" — for the run console / build message
    # QA-11b: one line saying what the accessibility capture took ("104 element(s) captured on
    # 6 screen(s)"), or "" when a phase captured nothing. The capture ITSELF never travels here
    # — the companion posts it straight to the platform, because a screen carries a full-page
    # PNG and this payload rides a Temporal signal.
    a11y_summary: str = ""
    # The companion-local preview URL the app was brought up on for a test-automation build (D7 /
    # P3-09bR): the live target 09b's Playwright explored. The platform records it on a `PreviewEnv`
    # and links it on the PR. "" for phases that bring no app up (07/11) or when no preview ran.
    preview_url: str = ""
    # The pre-push secret scan's findings, already redacted by the companion (kind + path + line +
    # a `conf***ow (24 chars)` preview — never the value). Previously these died in the companion's
    # process: `to_build_report` kept only a prose string capped at 8, so a 535-finding block told
    # the platform the count and 8 identities, and findings 9-535 existed nowhere (decision D6,
    # docs/truncation_issues_resolve.md §T5). Persisted on the run via `report_build`, so a block is
    # diagnosable after the fact and can seed the retry's prior-attempt context.
    # Bounded at `_MAX_CARRIED_FINDINGS` companion-side — this payload rides a Temporal signal.
    secret_findings: list = field(default_factory=list)
    # How the engine's run ENDED — "success", or an abnormal subtype like "error_max_turns".
    # "" means no ResultMessage arrived at all. The plan/review path has always inspected this;
    # the build path discarded it with the rest of `outputs`, so a build whose engine ended
    # abnormally but exited 0 was indistinguishable from a clean one.
    result_subtype: str = ""


def contains_nul(value) -> bool:
    """True if `value` is a str with a NUL (``\\x00``) — i.e. binary content that Postgres
    text/jsonb cannot store. Used to skip inlining binary PR files into a review manifest."""
    return isinstance(value, str) and "\x00" in value


def scrub_nul(value):
    """Recursively strip NUL (``\\x00``) from every string in a value (str / dict / list / tuple).

    Postgres text/jsonb cannot store ``\\u0000`` ("unsupported Unicode escape sequence — \\u0000
    cannot be converted to text"). Companion-reported text and PR diffs (09b commits Playwright
    report binaries: .png/.webm) can carry NUL, and any NUL written into a JSON column (run.inputs
    / run.outputs) fails the whole write and parks the run. Scrub it at the write boundaries so the
    run records cleanly. Only NUL is removed; every other byte is valid Postgres text. Django-free
    so the workflow sandbox and review provider can both import it."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: scrub_nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_nul(v) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub_nul(v) for v in value)
    return value


def failure_reason(exc) -> str:
    """The human-meaningful message from a Temporal ActivityError (Bugs S.No 139): its `.cause`
    (the real ApplicationError / exception raised inside the activity — e.g. "merge conflict: …"
    or "GitHub POST …/pulls -> 422") rather than the generic "Activity task failed" wrapper that
    `str(ActivityError)` returns. Without this the classifier and the S.No 136 merge-conflict
    message never reach the user. Django-free so the workflow sandbox can import it."""
    return str(getattr(exc, "cause", None) or exc)


def is_activity_timeout(exc) -> bool:
    """True when an ActivityError was the activity RUNNING OUT OF TIME rather than the activity
    finding something wrong.

    They are different facts and they were producing the same sentence. On 31 August a run that
    had judged all 800 of its elements and reported `ok` was written up as
    `write-completeness check failed: activity StartToClose timeout` — which reads, to anyone
    opening the run console, as "the completeness check found a gap". It found nothing; it never
    got to the end of looking. On a capability whose whole promise is that nothing dispatched
    vanishes silently, a false alarm about that promise is expensive.

    Same detection shape as `is_merge_conflict` / `is_empty_build`: prefer the structured cause,
    fall back to the message. Duck-typed on the cause's class name rather than importing
    `temporalio.exceptions.TimeoutError`, which shadows the builtin at module scope and would
    make every other `except TimeoutError` in this file mean something else.
    """
    cause = getattr(exc, "cause", None)
    if type(cause).__name__ == "TimeoutError":
        return True
    return "timeout" in failure_reason(exc).lower()


def display_name(inp) -> str:
    """What a PERSON should see for this work item (Bugs S.No 151): its title, falling back to the
    key only when there is no title. Artifact names and the PR title used work_item_key, which is a
    BRANCH SLUG — and with no SoR id it degrades to "WI-85bb350f", so users saw an opaque uuid
    instead of the task they triggered. (Agent-authored artifacts already read well: the platform
    registers don't-recreate and never overwrites their title — this fixes the platform's own
    fallback naming.) Django-free so the workflow sandbox can import it."""
    return (getattr(inp, "work_item_title", "") or "").strip() or inp.work_item_key


def is_empty_build(exc) -> bool:
    """True when an ActivityError was an EMPTY BUILD — the agent produced no changes, so there is
    nothing to open a PR for (raised by open_build_pr_core). This is NOT resumable (Bugs S.No 157):
    parking it for a retry would fail identically forever, because no amount of waiting makes a
    diff appear. It stays a terminal, clearly-explained failure. Same detection shape as
    is_merge_conflict: prefer the structured ApplicationError `type`, fall back to the message."""
    cause = getattr(exc, "cause", None)
    if getattr(cause, "type", "") == "EmptyBuild":
        return True
    return "empty build" in failure_reason(exc).lower()


#: Signatures of "the AI engine went away", as opposed to "the build genuinely failed". Kept in
#: sync with the engine branches of `classify_build_failure`.
_ENGINE_EXIT_MARKERS = (
    "exit code", "command failed", "processerror", "engine stderr", "engine output",
    "usage limit", "usage_limit", "rate limit", "too many requests", "overloaded", "quota",
    "failed to start claude code", "claude code not found",
)


def is_engine_exit(message: str) -> bool:
    """True when a companion-reported failure was the ENGINE dying rather than the build failing.

    This is the one recoverable-looking failure the build had no recourse for. A secret block
    auto-retries, remediation-exhaustion auto-retries, a merge error parks — an engine exit called
    `mark_build_failed` and returned, which closes the Temporal history for good. On TASK-014 that
    destroyed a run that already had a working PR and a completed code review, for a failure that
    had nothing to do with either.

    Deliberately narrow. An EMPTY BUILD must stay terminal (`is_empty_build`): waiting does not
    make a diff appear, and offering a Resume that cannot work is worse than a clear failure. A
    secret block is excluded too — it has its own bounded auto-retry, which is the better answer
    there because the agent needs a fresh attempt, not the same one resumed.
    """
    text = (message or "").lower()
    if "secret scan" in text or "empty build" in text or "no changes" in text:
        return False
    return any(marker in text for marker in _ENGINE_EXIT_MARKERS)


def is_review_failed(exc) -> bool:
    """True when an ActivityError was a REVIEW THAT NEVER RAN — the companion reported the 08
    review as failed (the engine died before posting a verdict), rather than the review returning
    findings the build must act on.

    Resumable like a merge error, and for the same reason: the branch, the PR and the imported
    test results are all still good; only the review needs re-running, and whatever stopped the
    engine (a usage limit, most often) is a matter of waiting rather than of rebuilding. Same
    detection shape as `is_empty_build`/`is_merge_conflict` — prefer the structured
    ApplicationError `type`, fall back to the message."""
    cause = getattr(exc, "cause", None)
    if getattr(cause, "type", "") == "ReviewFailed":
        return True
    return "code review did not complete" in failure_reason(exc).lower()


def is_merge_conflict(exc) -> bool:
    """True when an ActivityError was a MERGE CONFLICT (Bugs S.No 141 / ENH-2), so the build can
    re-open the merge gate for a resolve-then-retry instead of failing. Prefers the structured
    ApplicationError `type` ("MergeConflict", set by merge_build_pr_core) and falls back to the
    message text — robust whether or not Temporal preserved the typed cause."""
    cause = getattr(exc, "cause", None)
    if getattr(cause, "type", "") == "MergeConflict":
        return True
    return "merge conflict" in failure_reason(exc).lower()


#: Phases whose write-completeness check does REAL WORK, not a presence check, and so cannot
#: live inside the one-minute activity timeout the check normally gets.
#:
#: `a11y_judge` is the case that proved it. Its branch of `verify_write_completeness_core` does
#: two things beyond looking an artifact up: it records an `uncertain` verdict for every
#: dispatched element the judge never answered — up to a full batch of them, one database write
#: each against a remote server — and then publishes the merged report and closes the audit.
#: On the first live run that ran past sixty seconds and Temporal cancelled it mid-way: 81 of
#: 144 fallbacks were written and 63 elements silently got none, which is precisely the
#: "nothing dispatched may vanish from a conformance report" guarantee the branch exists to
#: keep. The work is the same class the workflow already gives five minutes to elsewhere
#: (publish, register_phase_result); one minute was sized for the check it USED to be.
#:
#: Kept here rather than imported from `apps.a11y` because the workflow module is deliberately
#: Django-free — see the note at the top of this file.
LONG_VERIFY_PHASES = frozenset({"a11y_judge", "a11y_journey"})
