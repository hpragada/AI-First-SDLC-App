"""AgentReviewProvider — the migrated Code Review agent (08) behind the review seam (§5/§6).

`run_code_review_core` (build_activities) reviews a PR through `get_review_provider().review()`.
The default is a no-findings stub until 08 is migrated; this module is the real provider: it
runs the migrated 08 body (eleven dimensions) through the `ExecutionDriver`, feeding it the PR
under review (read through the CodeHost capability, never copied — D2/#1) plus the platform
context, and parses the agent's structured verdict into `Finding`s. Severity → REM class:
critical→`REM-C`, warning→`REM-W` (both blocking), suggestion→`REM-S` (non-blocking). The loop
machinery (child WorkItems + TraceEdges + remediation) is unchanged — only the findings source.

Registered at worker startup via `set_review_provider`; the driver/codehost/compose hooks are
injectable so the parse + run path is testable without the network.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import TYPE_CHECKING

from mcp_platform_state import tools

from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem
from manifest.budget import MIN_PR_FILE_CHARS, pr_file_chars, total_for_model

from .activities import (
    REVIEW_TOOLS,
    _load_agent_body,
    _mcp_servers,
    compose_manifest_core,
    get_driver,
)
from .build_activities import _BLOCKING, Finding
from .build_types import contains_nul, scrub_nul
from .types import AgentRunInput

if TYPE_CHECKING:
    from .build_types import BuildInput

_REVIEW_AGENT_KEY = "08_code_review"
_REVIEW_PHASE = "code_review"


def _review_budget(spec) -> int:
    """The reviewer's manifest budget, from the 08 spec the caller already loaded.

    Taken from the spec rather than re-queried: both providers fetch it before composing, and the
    model that will read this briefing is the reviewer's, not the build agent's that produced the
    PR. No row, no model, no guess - the fallback is the size the platform always used.
    """
    total, _ = total_for_model(getattr(spec, "recommended_model", "") or "")
    return total

# critical/warning are blocking (become remediation child WorkItems); suggestion is not.
_SEVERITY_ALIASES = {
    "critical": "critical", "blocker": "critical", "blocking": "critical",
    "warning": "warning", "warn": "warning", "major": "warning",
    "suggestion": "suggestion", "minor": "suggestion", "info": "suggestion", "nit": "suggestion",
}
_REM_PREFIX = {"critical": "REM-C", "warning": "REM-W", "suggestion": "REM-S"}
# The migrated 08 body ends with exactly one fenced ```json block (its machine-readable verdict).
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
# A body that signals blocking findings in prose even when the json verdict is missing/malformed:
# a blocking REM id (REM-C1/REM-W1) or an explicit CHANGES_REQUIRED verdict word. Used by the
# fail-closed guard so a mis-formatted verdict can never be silently downgraded to "0 blocking".
_BLOCKING_REM = re.compile(r"\bREM-[CW]\d+\b")
_CHANGES_REQUIRED = re.compile(r"CHANGES[_ ]REQUIRED", re.IGNORECASE)
# A machine-verdict `status` that itself demands changes (negative verdict). "APPROVED" does not
# match; "CHANGES_REQUIRED"/"rejected"/"blocked"/"failed" do. Used so the fail-closed guard trusts
# a present, parseable *approved* verdict instead of firing on prose that merely names a RESOLVED
# REM id in the review narrative (Bugs S.No 114 false-positive).
_NEGATIVE_STATUS = re.compile(r"chang|reject|denied?|blocked|fail", re.IGNORECASE)
# Acceptance criteria in the shape agent 06 authors them: markdown checkbox lines under an
# "Acceptance Criteria:" heading (agents/06_task_breakdown/agent.md worked examples).
_CRITERIA_HEADING = re.compile(r"^[-*#>\s]*acceptance\s+criteria\s*:?\s*$", re.IGNORECASE)
_CRITERION_LINE = re.compile(r"^\s*[-*]\s*\[[ xX]?\]\s*(.+?)\s*$")
#: The only per-criterion verdicts the review contract accepts.
_CRITERION_VERDICTS = ("met", "not_met", "not_verifiable")


class ReviewContractError(RuntimeError):
    """The 08 review output signalled blocking findings but they could not be parsed (the
    machine-readable json verdict was missing or malformed). Raised so the build FAILS CLOSED —
    the merge gate is never opened on an unreviewed downgrade (Bugs S.No 114)."""


class ReviewUnavailableError(RuntimeError):
    """The companion reported the review as FAILED — the engine died before posting a verdict,
    so there is no review at all (not a review with nothing to say).

    Separate from `ReviewContractError` on purpose. That one means "a review happened and its
    verdict would not parse"; this one means "no review happened". Both fail closed, but only
    this one is worth parking for a human to Resume once the engine is available again, and
    conflating them would change the S.No 114 path's retry behaviour.

    A review that merely TIMED OUT is deliberately NOT this: no report is posted at all, the
    body stays absent, and `poll_review_body` keeps returning None → zero findings with the
    human merge gate still standing (Bugs S.No 110). Only an explicit `failed` status lands
    here."""


def _normalize_severity(value) -> str | None:
    return _SEVERITY_ALIASES.get(str(value or "").strip().lower())


def _extract_verdict(text: str) -> dict | None:
    """The reviewer's machine verdict: scan ALL fenced ```json blocks and take the LAST one that
    parses AND looks like a verdict (has `status` or `findings`) — robust to illustrative json
    earlier in the body and to a trailing prose summary the agent may append after the block."""
    for block in reversed(_JSON_BLOCK.findall(text or "")):
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and ("findings" in data or "status" in data):
            return data
    return None


def _looks_blocking(text: str) -> bool:
    """True if the body indicates blocking findings independently of the json verdict — a blocking
    REM id or an explicit CHANGES_REQUIRED verdict. The prose fail-closed signal (Bugs S.No 114),
    used ONLY when there is no parseable machine verdict — a REM id in prose can be a RESOLVED
    finding the review is merely narrating, not an active blocker."""
    t = text or ""
    return bool(_BLOCKING_REM.search(t) or _CHANGES_REQUIRED.search(t))


def _verdict_demands_changes(verdict: dict | None) -> bool:
    """True when a parseable machine verdict is present AND its own `status` is a negative verdict
    (changes-required/rejected/blocked/failed). A present verdict is the contract: trust its status
    rather than the prose, so a clean APPROVED verdict that merely *names* a resolved REM id in its
    narrative is not mistaken for an active blocker (Bugs S.No 114 false-positive)."""
    if verdict is None:
        return False
    return bool(_NEGATIVE_STATUS.search(str(verdict.get("status") or "")))


def parse_findings(text: str) -> list[Finding]:
    """Extract the reviewer's ```json verdict block and map it to `Finding`s.

    Trusts the agent's `rem` id where present (so a still-open finding keeps its id across
    re-review cycles — the loop keys child WorkItems by it); synthesizes a stable-by-order id
    otherwise. Unknown/missing severities and malformed JSON are dropped, not raised."""
    data = _extract_verdict(text)
    if data is None:
        return []

    findings: list[Finding] = []
    counters = {"critical": 0, "warning": 0, "suggestion": 0}
    for item in data.get("findings", []) or []:
        if not isinstance(item, dict):
            continue
        severity = _normalize_severity(item.get("severity"))
        if severity is None:
            continue
        counters[severity] += 1
        rem = str(item.get("rem") or "").strip() or f"{_REM_PREFIX[severity]}{counters[severity]}"
        try:
            line = int(item.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        findings.append(Finding(
            rem=rem, severity=severity, title=str(item.get("title") or rem),
            file=str(item.get("file") or ""), line=line,
            # Carry the reviewer's own words through (Bugs S.No 147). These used to be dropped
            # here, so no amount of good review writing could ever reach the remediation board.
            problem=str(item.get("problem") or "").strip(),
            fix=str(item.get("fix") or "").strip(),
            category=str(item.get("category") or "").strip(),
        ))
    return findings


def extract_acceptance_criteria(description: str | None) -> list[str]:
    """The work item's acceptance criteria, verbatim, as agent 06 writes them: `- [ ] Given …
    when … then …` lines under an `Acceptance Criteria:` heading.

    Returns `[]` for anything it cannot parse — an imported Jira item, a free-form description,
    a description with no criteria at all. That is deliberate, and it is what makes the guard
    below safe to fail closed: **a fail-closed rule that fires on input it does not understand is
    worse than the bug it was written for.**
    """
    criteria: list[str] = []
    collecting = False
    for raw in (description or "").splitlines():
        if _CRITERIA_HEADING.match(raw):
            collecting = True
            continue
        if not collecting:
            continue
        if not raw.strip():
            continue                        # a blank line inside the list does not end it
        match = _CRITERION_LINE.match(raw)
        if match:
            criteria.append(match.group(1).strip())
        else:
            collecting = False              # any other prose does end it
    return criteria


def guard_acceptance_criteria(body: str | None, criteria: list[str], *, tenant_id, run_id,
                              findings: list[Finding]) -> None:
    """Bugs S.No 243: an APPROVING 08 review must show, per criterion, that it checked it.

    The row files this as "the review agent is never given the acceptance criteria". That is not
    what happens — the work item goes to the manifest composer and its description is rendered
    into `# Current Work Item`, and the agent body has carried "Step 4a — Acceptance Criteria
    Cross-Reference" all along. The real gap is the OUTPUT CONTRACT: nothing ever required a
    per-criterion verdict, so `{"status": "APPROVED", "findings": []}` is indistinguishable from a
    review that performed step 4a and one that only skimmed the diff.

    That is how TASK-006 shipped three of its four requirements. The missing one was CORS; the
    review passed, the merge gate was approved, and because nothing in the pipeline opens a
    browser it stayed invisible for 18 days and 29 further tasks. The requirement had been stated
    twice — FOUND-003 and TASK-006 — and missed both times, which makes it systematic rather than
    a slip.

    Two deliberate limits keep this from blocking good work:

    * **Nothing to check → no check.** When no criteria could be extracted the guard does not
      fire at all. See `extract_acceptance_criteria`.
    * **Already going back → no check.** When the review carries blocking findings the merge gate
      does not open anyway, so the criteria table is not what decides this round.
    """
    if any(f.severity in _BLOCKING for f in findings):
        return
    if not criteria:
        # Worth seeing in the event log — it is the population this guard cannot protect — but
        # never a reason to fail a review.
        return
    verdict = _extract_verdict(body or "")
    entries = [e for e in ((verdict or {}).get("acceptance_criteria") or [])
               if isinstance(e, dict)]
    problems: list[str] = []
    if len(entries) < len(criteria):
        problems.append(
            f"the work item states {len(criteria)} acceptance criteria but the verdict carries "
            f"{len(entries)}"
        )
    for i, entry in enumerate(entries, 1):
        value = str(entry.get("verdict") or "").strip().lower()
        if value not in _CRITERION_VERDICTS:
            problems.append(
                f"criterion {i} has verdict {entry.get('verdict')!r}; expected one of "
                f"{', '.join(_CRITERION_VERDICTS)}"
            )
        elif value == "not_met":
            problems.append(
                f"criterion {i} is not_met, but the review raised no blocking finding for it — an "
                "unmet requirement cannot ride through on an approving verdict"
            )
        if not str(entry.get("evidence") or "").strip():
            problems.append(f"criterion {i} cites no evidence (a file:line or a test name)")
    if not problems:
        return
    with tenant_context(tenant_id):
        tools.log_event(
            tenant_id, "orchestrator", "review.acceptance_criteria_unverified", "run", str(run_id),
            {"criteria": len(criteria), "entries": len(entries), "problems": problems},
        )
    raise ReviewContractError(
        "08 approved the PR without showing it checked the work item's acceptance criteria: "
        + "; ".join(problems)
        + " — failing closed so the merge gate is not opened on a requirement nobody verified"
    )


def parse_and_guard(body: str | None, *, tenant_id, run_id,
                    acceptance_criteria: list[str] | None = None) -> list[Finding]:
    """Parse the verdict AND fail closed on a *genuine* contract downgrade (Bugs S.No 114).

    The remediation loop keys off the parsed blocking findings, so treating a review that really
    demanded changes as "0 blocking" would open the merge gate on an unreviewed downgrade. Fail
    closed when no blocking findings parse AND the review genuinely demands changes — meaning
    either (a) there is NO parseable machine verdict but the prose signals blocking (the agent put
    its prose last instead of the json block, or emitted a malformed/empty findings array), or
    (b) a parseable verdict IS present and its own `status` demands changes yet no blocking
    findings parsed (an in-JSON downgrade).

    Crucially, a present + parseable + *approved* verdict is authoritative: its narrative may name
    a RESOLVED REM id (e.g. "REM-W1 — RESOLVED") which the prose heuristic would otherwise mistake
    for an active blocker and fail a clean APPROVED review (Bugs S.No 114 false-positive). An empty
    body (review timeout) has no blocking signal → returns [] (the human merge gate still applies,
    S.No 110)."""
    findings = parse_findings(body or "")
    has_blocking = any(f.severity in _BLOCKING for f in findings)
    verdict = _extract_verdict(body or "")
    demands_changes = _verdict_demands_changes(verdict) or (
        verdict is None and _looks_blocking(body or "")
    )
    if not has_blocking and demands_changes:
        with tenant_context(tenant_id):
            tools.log_event(
                tenant_id, "orchestrator", "review.parse_mismatch", "run", str(run_id),
                {"reason": "review demands changes but no blocking findings parsed",
                 "has_json_verdict": verdict is not None,
                 "verdict_status": str((verdict or {}).get("status") or "")},
            )
        raise ReviewContractError(
            "08 review demanded changes but no blocking findings could be parsed (the machine "
            "verdict was missing/malformed, or its status demands changes with an empty/downgraded "
            "findings array); failing closed so the merge gate is not opened on an unreviewed "
            "downgrade"
        )
    guard_acceptance_criteria(body, acceptance_criteria or [], tenant_id=tenant_id, run_id=run_id,
                              findings=findings)
    return findings


class AgentReviewProvider:
    """Runs the migrated 08 agent over a PR and returns its structured findings."""

    def __init__(self, *, driver_factory=None, get_capability=None, compose_manifest=None) -> None:
        self._driver_factory = driver_factory or get_driver
        self._get_capability = get_capability or _default_get_capability
        self._compose_manifest = compose_manifest or compose_manifest_core

    def review(self, inp: BuildInput, pr_ref: str) -> list[Finding]:
        with tenant_context(inp.tenant_id):
            spec = (
                AgentSpec.objects.filter(tenant_id=inp.tenant_id, key=_REVIEW_AGENT_KEY)
                .order_by("-semver").first()
            )
            work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        if spec is None:
            # 08 not seeded for this tenant → no findings (the loop falls through to the gate).
            return []

        manifest = self._build_review_manifest(inp, pr_ref, spec=spec)
        driver = self._driver_factory()
        result = asyncio.run(driver.run_review_task(
            manifest=manifest, agent_spec=spec,
            mcp_servers=_mcp_servers(inp.tenant_id, inp.project_id, inp.run_id),
            allowed_tools=REVIEW_TOOLS, work_item=work_item,
        ))
        body = result.outputs.get("result") or result.outputs.get("text") or ""
        return parse_and_guard(
            body, tenant_id=inp.tenant_id, run_id=inp.run_id,
            acceptance_criteria=extract_acceptance_criteria(work_item.description),
        )

    # ── manifest assembly ───────────────────────────────────────────
    def _build_review_manifest(self, inp: BuildInput, pr_ref: str, *, spec=None) -> str:
        """The reviewer's briefing: the composed manifest, then the PR, then anything still open.

        `spec` is the 08 AgentSpec the caller has ALREADY loaded. It matters because the manifest
        is composed from `agent_spec_id`, and this method used to pass `inp.agent_spec_id` — the
        BUILD agent's spec (07) — while the run it feeds executes as 08. Harmless while nothing
        read the spec, but the manifest budget is now derived from the spec's model, so composing
        with 07's id would size the reviewer's briefing from the wrong agent's model. Both
        providers hold the right spec before they call this; they just never passed it.
        """
        review_inp = AgentRunInput(
            run_id=inp.run_id, tenant_id=inp.tenant_id, project_id=inp.project_id,
            work_item_id=inp.work_item_id,
            agent_spec_id=str(spec.id) if spec is not None else inp.agent_spec_id,
            phase=_REVIEW_PHASE,
        )
        base = self._compose_manifest(review_inp)
        parts = [base, self._render_pr_section(
            inp, pr_ref, max_file_chars=pr_file_chars(_review_budget(spec)))]
        open_section = _render_open_findings(inp)
        if open_section:
            parts.append(open_section)
        return "\n\n".join(parts)

    def _render_pr_section(self, inp: BuildInput, pr_ref: str, *,
                           max_file_chars: int = MIN_PR_FILE_CHARS) -> str:
        """Read the PR's changed files **through** the CodeHost capability (never copied as a
        source of truth) and inline them so the reviewer reasons over the actual diff.

        `max_file_chars` comes from this run's manifest budget and is never below what was
        inlined before, so a review can only ever see more of a file than it used to."""
        lines = ["# Pull Request Under Review", f"Ref: {pr_ref}", ""]
        try:
            codehost = self._get_capability(inp.tenant_id, "codehost")
            files = list(codehost.list_pr_files(pr_ref=pr_ref))
            pr = codehost.get_pull_request(pr_ref=pr_ref)
            ref = pr.sha or pr.head or inp.base
            lines.append(f"Changed files ({len(files)}): " + ", ".join(files))
            lines.append("")
            for path in files:
                try:
                    content = codehost.get_file(repo=pr.repo, path=path, ref=ref)
                except Exception:  # noqa: BLE001 — a single unreadable file must not fail review
                    continue
                # Skip binary files (a NUL byte marks binary). 09b commits Playwright report
                # artifacts (.png/.webm under playwright-report/) into the PR; inlining their
                # bytes both wrecks the review and — since this manifest is stored in the JSON
                # run.inputs — hits Postgres' "\\u0000 cannot be converted to text" and parks the
                # run. A reviewer can't read binary anyway, so note it and move on.
                if contains_nul(content):
                    lines += [f"## {path}", "(binary file — omitted from review)", ""]
                    continue
                if len(content) > max_file_chars:
                    # Name the offset and the call that returns the rest. A bare
                    # "(truncated)" told the agent something was missing and gave it no way
                    # to act, so the tail of a long file went unreviewed while the review
                    # still reported as a completed review.
                    content = (
                        content[:max_file_chars]
                        + f"\n… (truncated at {max_file_chars:,} of "
                          f"{len(content):,} chars — call "
                          f'get_pr_file(path=\"{path}\", start={max_file_chars}) for the rest)'
                    )
                lines += [f"## {path}", "```", content, "```", ""]
        except Exception:  # noqa: BLE001 — degrade to ref-only; the reviewer can fetch via tools
            # Now a true instruction. Until `get_pr_file` existed, no tool in any grant
            # list could read a file from a repository, so this line asked the reviewer
            # for something it could not do and the review proceeded on nothing.
            lines.append(
                "(diff unavailable — read each changed file with "
                f'get_pr_file(pr_ref=\"{pr_ref}\", path=\"<path>\"))')
        return "\n".join(lines)


def _render_open_findings(inp: BuildInput) -> str:
    """The REM ids this review already has open, so the agent can honour its own id contract.

    The 08 body is told: *"On a re-review, reuse the same `rem` id for a finding that is still
    open, and omit any finding that is now resolved"* — the platform keys the remediation board
    off `rem`. But the review manifest never carried the previous cycle's ids, so the agent had
    nothing to reuse and simply renumbered from 1 each time. `REM-W1` then meant a different
    problem every cycle, and the board tracked the label instead of the finding.

    Empty string on the first cycle (nothing open yet) so the section only appears when it says
    something, and on any error — a missing section must never fail a review."""
    try:
        with tenant_context(inp.tenant_id):
            children = WorkItem.objects.filter(
                tenant_id=inp.tenant_id, parent_id=inp.work_item_id,
                type=WorkItem.Type.TASK, state=WorkItem.State.IN_PROGRESS)
            open_items = [(c.external_ref or {}, c.title) for c in children
                          if (c.external_ref or {}).get("rem")]
    except Exception:  # noqa: BLE001 — context for the reviewer, never a reason to fail one
        return ""
    if not open_items:
        return ""
    lines = [
        "# Findings Already Open From Your Previous Review",
        "",
        "These ids are live on the remediation board. Re-use the SAME `rem` id for any finding "
        "below that is still not fixed, and simply OMIT the ones the latest commits resolved — "
        "omitting one is how you mark it resolved. Give a genuinely NEW problem a new id that "
        "does not appear in this list. Do not renumber from 1: these ids are what the "
        "implementation agent is briefed from, so a reused id must still mean the same problem.",
        "",
    ]
    for ref, title in sorted(open_items, key=lambda it: str(it[0].get("rem") or "")):
        loc = f"{ref.get('file') or '?'}:{ref.get('line') or 0}"
        lines.append(f"- **{ref.get('rem')}** ({ref.get('severity')}) — {title}  [{loc}]")
    return "\n".join(lines)


def _default_get_capability(tenant_id: str, capability: str):
    from integrations.registry import get_capability

    return get_capability(tenant_id, capability)


def build_default_provider() -> AgentReviewProvider:
    return AgentReviewProvider()


# ── review-as-dispatch (run 08 on the user's companion — req #1) ────
def dispatch_review_task(inp, *, manifest: str, agent_body: str, model: str = "") -> None:
    """Stash the review task (PR-diff manifest + 08 body) and a `dispatch` claim block so the
    companion pulls it via /api/runner/work/, and clear any prior cycle's review body."""
    from django.conf import settings

    # Defense-in-depth: even with binary files skipped in the manifest, scrub NUL from the whole
    # payload before it lands in the JSON run.inputs column, so no stray NUL from any source can
    # fail the write and park the run (see build_types.scrub_nul).
    payload = scrub_nul({
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "phase": _REVIEW_PHASE, "kind": "review",
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
    })
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        inputs = dict(run.inputs or {})
        inputs["review_task"] = payload
        inputs["dispatch"] = {"kind": "review", "status": "pending",
                              "enrollment_id": getattr(inp, "enrollment_id", None)}
        outputs = dict(run.outputs or {})
        outputs.pop("review_body", None)
        # Clear the PRIOR cycle's outcome with it. These are read to decide whether a review
        # ran at all, so leaving a stale `failed` behind would make every later cycle — the
        # re-review after remediation, and the Resume after a parked engine failure — raise on
        # a review that actually succeeded, parking the run in a loop it could never leave.
        outputs.pop("review_status", None)
        outputs.pop("review_error", None)
        run.inputs, run.outputs = inputs, outputs
        run.save(update_fields=["inputs", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "review.dispatched", "run", inp.run_id, {})


def _read_review_body(inp) -> str | None:
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        return (run.outputs or {}).get("review_body")


def _read_review_failure(inp) -> str | None:
    """The recorded cause when the companion reported the review as FAILED, else None.

    Returns a non-empty reason even when the companion sent no message, so a caller can always
    distinguish "reported failed" from "reported nothing" — an empty string would read as the
    latter."""
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        outputs = run.outputs or {}
    if outputs.get("review_status") != "failed":
        return None
    return (outputs.get("review_error") or "").strip() or "the companion reported no reason"


def poll_review_body(inp, *, sleep, poll_interval: float, timeout: float) -> str | None:
    """Poll the run for the companion's posted review body. Returns None on timeout (treated
    as no findings — the human merge gate still applies, so the build never hangs).

    On timeout it does one final read before giving up (Bugs S.No 110): the 08 verdict
    frequently lands moments after the last poll tick, and a report picked up here still drives
    the remediation loop instead of being orphaned in run.outputs while the gate opens blind."""
    waited = 0.0
    while True:
        body = _read_review_body(inp)
        if body is not None:
            return body
        if waited >= timeout:
            body = _read_review_body(inp)  # final grace read before declaring a timeout
            if body is not None:
                return body
            with tenant_context(inp.tenant_id):
                tools.log_event(inp.tenant_id, "orchestrator", "review.timeout", "run",
                                inp.run_id, {"waited_seconds": int(waited)})
            return None
        sleep(poll_interval)
        waited += poll_interval


def record_review_report(*, tenant_id, run_id, body, status="ok", message="") -> dict:
    """The companion posts its 08 verdict here; the provider's poll picks it up + parses it.

    `message` is the companion's diagnostic for a report that is NOT ok — the engine's exit
    reason, the stderr tail, whatever `_run_engine_phase` caught. It used to be dropped on the
    floor here, which is why a failed review left the platform with a `failed` status, an empty
    body, and no recorded cause anywhere (the only surviving copy was the companion's local
    engine log). It is scrubbed of NUL bytes for the same reason the dispatch payload is —
    Postgres refuses them in a json column and the write would park the run instead."""
    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        error = scrub_nul(message or "")
        run.outputs = {**(run.outputs or {}), "review_body": body or "",
                       "review_status": status, "review_error": error}
        run.save(update_fields=["outputs", "updated_at"])
        payload = {"status": status}
        if status == "failed":
            # The run console prints this event as a line; it used to print the engine's raw
            # output ("Command failed with exit code 1 …"). The line gets the cause in words,
            # the raw text is kept under `technical` for the ledger (run-console fix 2026-09-21).
            from .build_activities import describe_build_failure

            payload["reason"] = describe_build_failure(error, subject="review",
                                                       parked=True).cause
            payload["technical"] = error[:500]
        tools.log_event(tenant_id, "companion", "review.reported", "run", str(run_id), payload)
    return {"run_id": str(run_id), "recorded": True}


class CompanionReviewProvider:
    """The 08 review run on the user's enrolled companion (local Claude Code), not the server.
    Builds the same PR-diff manifest as AgentReviewProvider, dispatches it, then polls for the
    findings the companion posts back — review's counterpart of running planning/build locally."""

    def __init__(self, *, get_capability=None, compose_manifest=None, dispatch=None, poll=None,
                 poll_interval: float = 3.0, timeout: float = 1800.0, sleep=None) -> None:
        self._manifest = AgentReviewProvider(
            get_capability=get_capability, compose_manifest=compose_manifest)
        self._dispatch = dispatch or dispatch_review_task
        self._poll = poll or poll_review_body
        self._poll_interval = poll_interval
        self._timeout = timeout  # fallback; a per-run inp.review_timeout_seconds wins (S.No 110)
        self._sleep = sleep or time.sleep

    def review(self, inp: BuildInput, pr_ref: str) -> list[Finding]:
        with tenant_context(inp.tenant_id):
            spec = (
                AgentSpec.objects.filter(tenant_id=inp.tenant_id, key=_REVIEW_AGENT_KEY)
                .order_by("-semver").first()
            )
            work_item = WorkItem.objects.filter(
                id=inp.work_item_id, tenant_id=inp.tenant_id).first()
        if spec is None:
            return []  # 08 not seeded → no findings (loop falls through to the merge gate)
        manifest = self._manifest._build_review_manifest(inp, pr_ref, spec=spec)
        agent_body, model = _load_agent_body(str(spec.id), inp.tenant_id)
        self._dispatch(inp, manifest=manifest, agent_body=agent_body, model=model)
        timeout = float(getattr(inp, "review_timeout_seconds", None) or self._timeout)
        body = self._poll(inp, sleep=self._sleep, poll_interval=self._poll_interval,
                          timeout=timeout)
        if body is None:
            return []  # review timed out → no findings; human merge gate still applies (S.No 110)
        # A FAILED report is not a verdict. The companion posts `{"status": "failed"}` with no
        # body when the engine dies mid-review, and `body or ""` stored that as an empty string —
        # which is not None, so the poll accepted it, `parse_and_guard("")` found nothing to
        # block on, and the merge gate opened over an artifact reading "No findings were raised
        # in this review cycle." A review that never ran must never read as a clean one.
        failure = _read_review_failure(inp)
        if failure is not None:
            raise ReviewUnavailableError(f"code review did not complete: {failure}")
        return parse_and_guard(
            body, tenant_id=inp.tenant_id, run_id=inp.run_id,
            acceptance_criteria=extract_acceptance_criteria(
                work_item.description if work_item else ""),
        )


def build_companion_provider() -> CompanionReviewProvider:
    return CompanionReviewProvider()
