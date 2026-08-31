"""Workflow/activity payloads. Deliberately Django-free so the workflow sandbox
can import them without pulling in the ORM."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentRunInput:
    """One agent run = one AgentRunWorkflow (spec §5)."""

    run_id: str
    tenant_id: str
    project_id: str
    work_item_id: str
    agent_spec_id: str
    phase: str
    gate_type: str = "phase_gate"
    required_role: str = "product_owner"
    # Where the engine runs (req #1). "companion" = the user's local Claude Code via their
    # enrolled companion (the real path; set by trigger_phase when an enrollment exists);
    # "server" = the in-worker ClaudeDriver (the CI/test/headless fallback). The dataclass
    # default stays "server" so existing tests that build the input directly are unchanged.
    execution_mode: str = "server"
    # Which enrolled companion to dispatch to (the triggering user's), when companion mode.
    enrollment_id: str | None = None
    # If the companion never reports within this window, park the run for human takeover.
    #
    # **A default, not a rule.** Every phase used to inherit this number silently because
    # `trigger_phase` never set it, so a planning phase that takes four minutes and an
    # accessibility judging pass that takes two and a quarter HOURS were given the same two
    # hours. On 31 August it fired at 7,200 s to the second on a companion that was demonstrably
    # alive — a verdict had landed seconds earlier and another landed seconds after — and the run
    # went on to finish normally sixteen minutes later. Nothing broke, but the screen said the
    # machine was offline, and the obvious response to "offline" is the one click that would have
    # ended the run fifteen verdicts from the end. A caller that can size its own work now says
    # so; see `a11y.dispatch` for the only one that currently does.
    report_timeout_seconds: int = 7200
    # How long the write-completeness check may take. One minute is right for what that check
    # usually is — look one artifact up and confirm it has a body. For the phases in
    # LONG_VERIFY_PHASES it is not that check at all: it writes a fallback verdict for every
    # unanswered element, one database round trip each, then publishes the merged report and
    # closes the audit. Cancelled part-way it leaves exactly the accounting it exists to
    # guarantee half-done — 81 of 144 fallbacks written and 63 elements silently given none, the
    # first time, at sixty seconds. It was raised to a flat five minutes, and at 800 elements
    # five minutes is the new sixty seconds.
    #
    # So the caller sizes it, for the same reason and in the same shape as the field above. The
    # default is the old flat five minutes, so any caller that does not set it is unchanged.
    # **Deploy the worker before the API**: an input carrying a field the worker's dataclass does
    # not have yet fails to deserialize.
    verify_timeout_seconds: int = 300
    # Repo-scoped PLANNING phases (catalog `reads_code`, e.g. 10_security) carry the target
    # repo + base branch so the companion can check out a READ-ONLY worktree to scan the real
    # source. None for every other planning phase → no worktree, behaviour unchanged. This is
    # NOT the build path (no commit/push/PR); the run still rides AgentRunWorkflow.
    repo: str | None = None
    base: str | None = None
    # Auto-apply (no human gate). Default False → every existing phase is byte-identical: it
    # opens a gate and waits for a human decision. True only for the document-vision agent (00e,
    # Part B): the human already adopted the document these pages came from, so the faithful
    # transcription is published automatically instead of waiting on a second gate. The workflow
    # branches on this after write-completeness; nothing else changes.
    auto_approve: bool = False


@dataclass
class GateDecision:
    """Payload of the `gate_decision` signal."""

    decision: str  # "approved" | "rejected"
    approver_id: str | None = None
    comment: str = ""
    # "Request changes": a rejection the reviewer wants ACTED ON rather than just recorded. The
    # workflow rejects the run as usual and then re-runs the phase with `comment` as authoritative
    # direction. Defaults False, so an old-shape signal payload (no key) replays as a plain
    # rejection — but a NEW api signalling an OLD worker fails to deserialize, so deploy the
    # worker first. This flag is the only workflow-payload change the revision feature needs:
    # the direction itself travels in `Run.inputs["review_history"]`, not in a Temporal payload.
    revise: bool = False


@dataclass
class PhaseReport:
    """What the companion posts back after running a planning/review phase locally (the
    `phase_reported` signal payload). The artifact body travels here; the platform writes it
    to S3 and registers the pointer (state stays server-side)."""

    status: str = "ok"          # "ok" | "failed"
    body: str = ""              # the phase's produced text (becomes the draft artifact)
    cost_usd: float = 0.0
    message: str = ""
