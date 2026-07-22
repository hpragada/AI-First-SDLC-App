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

from .activities import (
    PLATFORM_TOOLS,
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
# How much of each changed file to ship to the reviewer (keep the prompt bounded).
_MAX_FILE_CHARS = 16000

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


class ReviewContractError(RuntimeError):
    """The 08 review output signalled blocking findings but they could not be parsed (the
    machine-readable json verdict was missing or malformed). Raised so the build FAILS CLOSED —
    the merge gate is never opened on an unreviewed downgrade (Bugs S.No 114)."""


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


def parse_and_guard(body: str | None, *, tenant_id, run_id) -> list[Finding]:
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

        manifest = self._build_review_manifest(inp, pr_ref)
        driver = self._driver_factory()
        result = asyncio.run(driver.run_review_task(
            manifest=manifest, agent_spec=spec,
            mcp_servers=_mcp_servers(inp.tenant_id, inp.project_id, inp.run_id),
            allowed_tools=PLATFORM_TOOLS, work_item=work_item,
        ))
        body = result.outputs.get("result") or result.outputs.get("text") or ""
        return parse_and_guard(body, tenant_id=inp.tenant_id, run_id=inp.run_id)

    # ── manifest assembly ───────────────────────────────────────────
    def _build_review_manifest(self, inp: BuildInput, pr_ref: str) -> str:
        review_inp = AgentRunInput(
            run_id=inp.run_id, tenant_id=inp.tenant_id, project_id=inp.project_id,
            work_item_id=inp.work_item_id, agent_spec_id=inp.agent_spec_id, phase=_REVIEW_PHASE,
        )
        base = self._compose_manifest(review_inp)
        return f"{base}\n\n{self._render_pr_section(inp, pr_ref)}"

    def _render_pr_section(self, inp: BuildInput, pr_ref: str) -> str:
        """Read the PR's changed files **through** the CodeHost capability (never copied as a
        source of truth) and inline them so the reviewer reasons over the actual diff."""
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
                if len(content) > _MAX_FILE_CHARS:
                    content = content[:_MAX_FILE_CHARS] + "\n… (truncated)"
                lines += [f"## {path}", "```", content, "```", ""]
        except Exception:  # noqa: BLE001 — degrade to ref-only; the reviewer can fetch via tools
            lines.append("(diff unavailable — fetch the PR via the platform tools)")
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
        run.inputs, run.outputs = inputs, outputs
        run.save(update_fields=["inputs", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "review.dispatched", "run", inp.run_id, {})


def _read_review_body(inp) -> str | None:
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        return (run.outputs or {}).get("review_body")


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


def record_review_report(*, tenant_id, run_id, body, status="ok") -> dict:
    """The companion posts its 08 verdict here; the provider's poll picks it up + parses it."""
    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        run.outputs = {**(run.outputs or {}), "review_body": body or "", "review_status": status}
        run.save(update_fields=["outputs", "updated_at"])
        tools.log_event(tenant_id, "companion", "review.reported", "run", str(run_id),
                        {"status": status})
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
        if spec is None:
            return []  # 08 not seeded → no findings (loop falls through to the merge gate)
        manifest = self._manifest._build_review_manifest(inp, pr_ref)
        agent_body, model = _load_agent_body(str(spec.id), inp.tenant_id)
        self._dispatch(inp, manifest=manifest, agent_body=agent_body, model=model)
        timeout = float(getattr(inp, "review_timeout_seconds", None) or self._timeout)
        body = self._poll(inp, sleep=self._sleep, poll_interval=self._poll_interval,
                          timeout=timeout)
        if body is None:
            return []  # review timed out → no findings; human merge gate still applies (S.No 110)
        return parse_and_guard(body, tenant_id=inp.tenant_id, run_id=inp.run_id)


def build_companion_provider() -> CompanionReviewProvider:
    return CompanionReviewProvider()
