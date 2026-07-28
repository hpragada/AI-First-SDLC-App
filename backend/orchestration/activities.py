"""Temporal activities (spec §5). All DB/engine/S3 side effects live here, never in
the workflow. Each activity is a thin @activity.defn wrapper over a sync *core* function
that is directly unit-testable; cores are idempotent by run_id so Temporal retries are safe.

`get_driver` / `get_object_store` are module-level factories so tests can swap in fakes.
Every DB touch runs inside `tenant_context` so RLS scopes it when the worker connects as
the non-superuser app role.
"""
from __future__ import annotations

import asyncio
import dataclasses
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from mcp_platform_state import tools
from temporalio import activity

from apps.gates.models import Approval
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem
from drivers import ClaudeDriver
from manifest import compose_manifest
from manifest.rules import get_prompt_rules
from storage import content_hash, s3_from_settings

from .types import AgentRunInput, PhaseReport


class WriteCompletenessError(Exception):
    """Rule 11: a run reached completion without registering an expected artifact."""


def _as_phase_report(report) -> PhaseReport:
    """Coerce a reported phase result to PhaseReport, whatever the caller handed us.

    Temporal converts an activity argument to the type its parameter is ANNOTATED with; an
    unannotated parameter arrives as the raw decoded JSON — a plain dict. `register_phase_result`
    was unannotated, so `getattr(report, "body", "")` read an attribute off a dict, found none,
    and silently returned the default: the companion's whole document became "" and its cost
    became 0.0. The activity is annotated now, so this is belt-and-braces (the cores are also
    called directly from tests and from the takeover path, which pass a real PhaseReport).
    """
    if isinstance(report, PhaseReport):
        return report
    if isinstance(report, dict):
        known = {f.name for f in dataclasses.fields(PhaseReport)}
        return PhaseReport(**{k: v for k, v in report.items() if k in known})
    # Anything else (an object with the right attributes) — read it the old way, defensively.
    return PhaseReport(
        status=getattr(report, "status", "ok") or "ok",
        body=getattr(report, "body", "") or "",
        cost_usd=float(getattr(report, "cost_usd", 0.0) or 0.0),
        message=getattr(report, "message", "") or "",
    )

_PLATFORM_TOOL_NAMES = [
    "get_context", "register_artifact", "stage_artifact_body", "get_artifact_body",
    "update_artifact", "add_trace_edge", "log_event",
    "list_work_items", "create_work_item", "transition_work_item", "get_artifact",
    "list_artifacts", "detect_drift",
    # Vision pipe (Part B): the document-vision agent reads a document's page images.
    "get_page_images",
]
PLATFORM_TOOLS = [f"mcp__platform-state__{name}" for name in _PLATFORM_TOOL_NAMES]


# ── injectable factories (tests monkeypatch these) ──────────────────
def get_driver():
    return ClaudeDriver()


def get_object_store():
    return s3_from_settings()


def load_rules() -> str:
    # Distilled prompt-enforced rules (RULE-BEHAVIOR / RULE-EXECUTION), AGENT_MIGRATION_SPEC §4.
    return get_prompt_rules()


def _now() -> datetime:
    return datetime.now(UTC)


def _load_agent_body(agent_spec_id: str, tenant_id: str) -> tuple[str, str]:
    """Read the migrated agent's body (+ model) to ship to the companion. Tolerant — an
    absent body is empty, not fatal. (Mirror of the build path's loader; kept local to avoid
    importing build_activities, which imports this module.)"""
    with tenant_context(tenant_id):
        spec = AgentSpec.objects.filter(id=agent_spec_id, tenant_id=tenant_id).first()
        body_ref = spec.body_ref if spec else ""
        model = spec.recommended_model if spec else ""
    if not body_ref:
        return "", model
    path = Path(body_ref)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / body_ref
    try:
        return path.read_text(encoding="utf-8"), model
    except OSError:
        return "", model


def _mcp_servers(tenant_id: str, project_id: str = "", run_id: str = "") -> dict:
    """Config the engine uses to launch the platform-state MCP server, with the tenant (and
    the project/run this launch is bound to) set from the control plane — the agent never
    passes a tenant, and needn't know the project/run id either (e.g. artifact registration
    fills them from here rather than asking the user, Bugs.xlsx row 25)."""
    repo_root = str(Path(__file__).resolve().parents[2])
    return {
        "platform-state": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_platform_state.server"],
            "env": {
                "PLATFORM_TENANT_ID": str(tenant_id),
                "PLATFORM_PROJECT_ID": str(project_id or ""),
                "PLATFORM_RUN_ID": str(run_id or ""),
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "DATABASE_URL": settings.DATABASES["default"].get("URL", ""),
                "PYTHONPATH": repo_root,
            },
        }
    }


# ── cores (idempotent by run_id) ────────────────────────────────────
def compose_manifest_core(inp: AgentRunInput) -> str:
    with tenant_context(inp.tenant_id):
        work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        # Pass the work item so context scopes per-repo when it targets one (D5).
        context = tools.get_context(
            inp.tenant_id, inp.project_id, inp.phase, work_item_id=inp.work_item_id)
        return compose_manifest(
            context=context, work_item=tools._work_item(work_item),
            phase=inp.phase, rules=load_rules(),
        )


_EXECUTED_STATES = {Run.Status.AWAITING_GATE, Run.Status.APPROVED, Run.Status.COMPLETED}


def classify_phase_failure(reason: str) -> str:
    """Turn a raw planning/review failure into a plain-language reason (Bugs S.No 146, planning
    path). Build failures already go through classify_build_failure; planning phases (including
    10_security) wrote the raw exception verbatim — e.g. a bare 'Command failed with exit code 1
    / Check stderr output for details' — so the run console showed no usable reason. An already
    specific message passes through unchanged (never lost)."""
    r = (reason or "").lower()
    if ("usage limit" in r or "usage_limit" in r or "rate limit" in r or "rate-limit" in r
            or "429" in r or "too many requests" in r or "overloaded" in r or "quota" in r):
        return ("The AI engine hit its usage or rate limit, so the phase could not finish. "
                "Wait for the limit to reset, then re-trigger the phase.")
    if ("failed to start claude code" in r or "claude code not found" in r
            or "open_process()" in r):
        return ("The AI engine (Claude Code) could not start on the companion — check the engine "
                "install on the dev machine, then re-trigger.")
    if ("exit code" in r or "command failed" in r or "processerror" in r
            or "engine stderr" in r):
        return ("The AI engine exited with an error before finishing the phase. The most common "
                "cause is a usage or rate limit; check the companion terminal for the engine "
                "output, then re-trigger.")
    if r.strip() in ("", "phase reported failed"):
        return "The phase agent failed without reporting a specific reason."
    return reason


def execute_agent_core(inp: AgentRunInput, manifest: str) -> dict:
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        existing = list(Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id))
        if existing and run.status in _EXECUTED_STATES:
            return {"artifact_ids": [str(a.id) for a in existing], "idempotent": True}
        run.status = Run.Status.RUNNING
        run.started_at = _now()
        run.save(update_fields=["status", "started_at", "updated_at"])
        agent_spec = AgentSpec.objects.get(id=inp.agent_spec_id, tenant_id=inp.tenant_id)
        work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)

    # Engine call is outside the tenant_context cursor (it may be long).
    driver = get_driver()
    try:
        result = asyncio.run(
            driver.run_planning_task(
                manifest=manifest, agent_spec=agent_spec,
                mcp_servers=_mcp_servers(inp.tenant_id, inp.project_id, inp.run_id),
                allowed_tools=PLATFORM_TOOLS,
                work_item=work_item,
            )
        )
    except Exception as exc:
        # Plain-language reason for the run console (Bugs S.No 146, planning path) — the raw
        # 'Command failed with exit code 1 / Check stderr' told the user nothing.
        error_message = classify_phase_failure(str(exc))
        with tenant_context(inp.tenant_id):
            run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
            run.status = Run.Status.FAILED
            run.ended_at = _now()
            run.outputs = {**(run.outputs or {}), "error": error_message}
            run.save(update_fields=["status", "outputs", "ended_at", "updated_at"])
            tools.log_event(
                inp.tenant_id, "orchestrator", "run.failed", "run", inp.run_id,
                {"error": error_message},
            )
        raise

    body = result.outputs.get("result") or result.outputs.get("text") or ""
    s3_key = f"drafts/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/{inp.phase}.md"
    get_object_store().put(s3_key, body)
    digest = content_hash(body.encode("utf-8"))

    artifact = tools.register_artifact(
        inp.tenant_id, inp.project_id, inp.run_id, inp.phase, inp.phase,
        "internal", digest, s3_key=s3_key,
    )
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.AWAITING_GATE
        run.cost_usd = Decimal(str(result.cost_usd))
        run.outputs = {
            "artifact_s3_key": s3_key, "content_hash": digest, "cost_usd": result.cost_usd,
        }
        run.ended_at = _now()
        run.save(update_fields=["status", "cost_usd", "outputs", "ended_at", "updated_at"])
        tools.log_event(
            inp.tenant_id, "orchestrator", "run.executed", "run", inp.run_id,
            {"artifact_id": artifact["id"]},
        )
    # After a Testing (09) run records its output, turn the `test_case` artifacts it registered
    # into child test_case WorkItems under the story, so Test Automation (09b) can run on each one
    # (P3-09b B3). Best-effort — a materialization hiccup must never fail the run that succeeded.
    if inp.phase == "testing":
        try:
            from apps.workitems.test_cases import materialize_test_cases

            materialize_test_cases(
                tenant_id=inp.tenant_id, project_id=inp.project_id,
                run_id=inp.run_id, story_id=inp.work_item_id)
        except Exception as exc:  # noqa: BLE001 — never break a completed run
            tools.log_event(inp.tenant_id, "orchestrator", "test_cases.materialize_failed",
                            "run", inp.run_id, {"error": str(exc)})
    return {"artifact_ids": [artifact["id"]], "cost_usd": result.cost_usd}


def open_gate_core(inp: AgentRunInput) -> str:
    from apps.gates.conditions import conditions_for_phase

    with tenant_context(inp.tenant_id):
        approval, created = Approval.objects.get_or_create(
            run_id=inp.run_id, gate_type=inp.gate_type, tenant_id=inp.tenant_id,
            defaults={
                "work_item_id": inp.work_item_id,
                "required_role": inp.required_role,
                "decision": Approval.Decision.PENDING,
                # Control-plane gate conditions (#2/#5): the WCAG checklist on the design
                # gate (D6), the blocking-test rule on the test gate (D9).
                "conditions": conditions_for_phase(inp.phase),
            },
        )
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        if run.status != Run.Status.AWAITING_GATE:
            run.status = Run.Status.AWAITING_GATE
            run.save(update_fields=["status", "updated_at"])
        if created:
            tools.log_event(
                inp.tenant_id, "orchestrator", "gate.opened", "approval", str(approval.id),
                {"required_role": inp.required_role},
            )
    return str(approval.id)


def publish_artifacts_core(inp: AgentRunInput) -> dict:
    """On APPROVED: snapshot to S3 and mark every artifact published-INTERNAL. External
    export is user-triggered (team flow decision, 2026-07-07) via POST
    /artifacts/{id}/publish/, governed by the project's phase-scoped export policy
    (integrations.export_policy) — gate approval never auto-pushes to a SoR. Idempotent —
    already-published artifacts are skipped."""
    store = get_object_store()
    with tenant_context(inp.tenant_id):
        artifacts = list(Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id))

    published: list[str] = []
    for artifact in artifacts:
        if artifact.status == Artifact.Status.PUBLISHED:
            published.append(str(artifact.id))
            continue

        if artifact.s3_key:  # immutable audit snapshot regardless of SoR
            snap = (
                f"snapshots/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/"
                f"{artifact.phase}.v{artifact.version}.md"
            )
            store.copy(artifact.s3_key, snap)

        tools.update_artifact(
            inp.tenant_id, str(artifact.id),
            status=Artifact.Status.PUBLISHED, sor=Artifact.SoR.INTERNAL,
        )
        published.append(str(artifact.id))

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.COMPLETED
        run.save(update_fields=["status", "updated_at"])
        # The Approval decision is recorded by the gate service (decide_gate, T9),
        # not here — that path owns the approver + decided_at.
        tools.log_event(
            inp.tenant_id, "orchestrator", "artifacts.published", "run", inp.run_id,
            {"artifact_ids": published},
        )
    return {"published": published}


def transition_work_item_core(inp: AgentRunInput, to_state: str) -> dict:
    with tenant_context(inp.tenant_id):
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, to_state)
        tools.log_event(
            inp.tenant_id, "orchestrator", "workitem.transitioned", "work_item",
            inp.work_item_id, {"to_state": to_state},
        )
    return {"work_item_id": inp.work_item_id, "state": to_state}


def reject_run_core(inp: AgentRunInput, comment: str) -> dict:
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.REJECTED
        run.save(update_fields=["status", "updated_at"])
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        # Approval decision/comment recorded by the gate service (decide_gate, T9).
        tools.log_event(
            inp.tenant_id, "orchestrator", "run.rejected", "run", inp.run_id, {"comment": comment}
        )
    return {"status": "rejected"}


#: The hash of a body staged from no text at all. `register_phase_result_core` always stamps
#: the staged body's real digest, so an expected artifact carrying this is provably empty.
_EMPTY_BODY_HASH = content_hash(b"")

#: Phases whose real deliverable is a RICHER artifact than the platform's generic phase-typed
#: blob. verify_writes requires these instead of the bare phase type so a run that produced only
#: an empty/summary "<phase>" blob — but not the actual work product — fails loudly rather than
#: opening the gate on nothing (Bugs S.No 179). Security must ship its actual review document,
#: which the agent registers (stage_artifact_body → register_artifact) as `security_review`.
_PHASE_REQUIRED_ARTIFACTS = {
    "security": ["security_review"],
}


def verify_write_completeness_core(inp: AgentRunInput, expected_types: list[str]) -> dict:
    """Rule 11 (platform-enforced): before the gate opens, confirm the run actually registered
    the artifacts its phase was supposed to produce — **and that they say something**.

    An empty expected artifact is not a write. Run b0e6557b spent its whole turn budget
    registering 90 test cases and never wrote its phase document; the platform staged the empty
    draft, logged `phase.empty_result` — and then opened the gate anyway, inviting a human to
    approve a blank page. Presence was never the bar Rule 11 was reaching for; having something
    to review is.

    Only what we can know is judged: an artifact staged from the engine's text carries that
    text's digest, so an empty one is provable. A pointer-only artifact registered with a
    foreign hash makes no claim about its body and is left alone.
    """
    # Auto-apply runs (00e document vision, Part B) don't register a phase-typed artifact — they
    # re-register the TARGET document as a new version carrying its own type, then publish without
    # a gate. So the bar here is "the run actually produced content", not a phase-type match:
    # require at least one non-empty artifact this run, so an empty/failed vision pass can never
    # auto-publish nothing over the adopted document.
    if getattr(inp, "auto_approve", False):
        with tenant_context(inp.tenant_id):
            hashes = list(
                Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
                .values_list("content_hash", flat=True)
            )
        if not any(h and h != _EMPTY_BODY_HASH for h in hashes):
            raise WriteCompletenessError(
                f"run {inp.run_id} (auto-apply) registered no non-empty artifact — the vision "
                "pass produced nothing to apply, so nothing is published."
            )
        return {"present": ["non-empty artifact"], "expected": ["non-empty artifact"]}

    # Expand any phase whose real work product is a richer artifact (e.g. security → the actual
    # security_review, not the generic "security" blob the platform always auto-registers). Other
    # phases are unchanged (map returns the type itself).
    required_types: list[str] = []
    for t in expected_types:
        required_types.extend(_PHASE_REQUIRED_ARTIFACTS.get(t, [t]))
    expected_types = list(dict.fromkeys(required_types))  # dedupe, preserve order

    with tenant_context(inp.tenant_id):
        artifacts = list(
            Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
            .values_list("type", "content_hash")
        )
    present = {t for t, _ in artifacts}
    missing = [t for t in expected_types if t not in present]
    if missing:
        raise WriteCompletenessError(
            f"run {inp.run_id} reached the gate without expected artifact types {missing}"
        )
    empty = sorted({t for t, h in artifacts
                    if t in expected_types and h == _EMPTY_BODY_HASH})
    if empty:
        raise WriteCompletenessError(
            f"run {inp.run_id} produced an EMPTY {', '.join(empty)} document — the engine "
            f"returned no final text (commonly the turn budget spent before writing it). "
            f"There is nothing for a reviewer to approve, so no gate is opened; re-run the "
            f"phase. Everything it did register stays in the registry as drafts."
        )
    return {"present": sorted(present), "expected": list(expected_types)}


# ── companion execution of planning/review (req #1) ─────────────────
# These mirror the build saga's dispatch→report seam for planning: the platform composes
# the manifest, dispatches a self-contained task the companion fetches and runs LOCALLY (the
# client's own logged-in Claude Code, no API key), then registers the reported result. State
# (S3 body + registry pointer) stays server-side. Used only when execution_mode == "companion".
def dispatch_phase_core(inp: AgentRunInput, manifest: str) -> dict:
    """Stash the self-contained phase task (manifest + agent body) for the companion to claim
    + run, and mark the run dispatched. Idempotent by run_id."""
    from django.conf import settings

    agent_body, model = _load_agent_body(inp.agent_spec_id, inp.tenant_id)
    payload = {
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "phase": inp.phase, "kind": "plan",
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
    }
    # Repo-scoped planning (catalog `reads_code`, e.g. 10_security): tell the companion which
    # repo to check out READ-ONLY so the agent can scan real source. `kind` stays "plan" (the
    # companion must NOT enter the build path); the presence of `repo` + `reads_code` is the
    # discriminator. Absent for every other planning phase → payload identical to today.
    if inp.repo:
        payload["repo"] = inp.repo
        payload["base"] = inp.base or "main"
        payload["reads_code"] = True
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.inputs = {
            **(run.inputs or {}),
            "phase_task": payload,
            "dispatch": {"kind": "plan", "enrollment_id": inp.enrollment_id,
                         "status": "pending"},
        }
        if run.status not in (Run.Status.RUNNING, Run.Status.AWAITING_GATE,
                              Run.Status.COMPLETED):
            run.status = Run.Status.RUNNING
            run.started_at = run.started_at or _now()
        run.save(update_fields=["inputs", "status", "started_at", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "phase.dispatched", "run", inp.run_id,
                        {"phase": inp.phase, "enrollment_id": inp.enrollment_id})
    return {"dispatched": True}


def _phase_artifact_title(inp: AgentRunInput) -> str:
    """A human name for the phase's own document — "Testing — Add login".

    The platform registers this artifact itself, and did so titleless: every UI surface then
    had to fall back to humanizing the bare type (S.No 120), and a phase document is precisely
    the artifact a reviewer opens at the gate. `register_artifact`'s own contract says ALWAYS
    pass a title; the platform must hold itself to what it tells agents.
    """
    label = (inp.phase or "phase").replace("_", " ").strip().capitalize()
    with tenant_context(inp.tenant_id):
        work_item_title = (
            WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id)
            .values_list("title", flat=True).first() or ""
        )
    return f"{label} — {work_item_title}" if work_item_title else label


def register_phase_result_core(inp: AgentRunInput, report) -> dict:
    """Register the companion's reported phase result: write the body to S3, register the
    draft artifact (pointer), record cost, clear the dispatch claim. Idempotent — an existing
    artifact for this run/phase **with a staged body** is reused (safe Temporal retries).

    Bugs.xlsx row 59: agents register pointer-only artifacts mid-run (content_hash, no
    s3_key). When the agent's own registration matched (run, type==phase), the old guard
    returned early and the body was NEVER staged to S3 — every artifact of the run ended
    body-less and preview 404'd. Now the body is always staged, and an agent-registered
    phase artifact gets its s3_key backfilled instead of blocking the staging step.

    Bugs.xlsx S.No 160: `report` arrived here as a dict (see `_as_phase_report`), so reading it
    with getattr silently yielded ""/0.0 — the companion's entire document was dropped on the
    floor and its cost misreported as zero. Read it through the coercion, never with getattr."""
    report = _as_phase_report(report)
    with tenant_context(inp.tenant_id):
        existing = Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id, type=inp.phase).first()
    if existing is not None and existing.s3_key:
        # True retry: the body was already staged and pointed at — nothing left to do.
        return {"artifact_ids": [str(existing.id)], "idempotent": True}

    body = report.body or ""
    cost = float(report.cost_usd or 0.0)
    s3_key = f"drafts/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/{inp.phase}.md"
    get_object_store().put(s3_key, body)
    digest = content_hash(body.encode("utf-8"))
    if existing is not None:
        # The agent registered the phase artifact itself (pointer-only). Attach the staged
        # draft so the pointer + hash reference a real body (still S3, never the DB — #1/#3),
        # and give it a name if the agent left it untitled.
        with tenant_context(inp.tenant_id):
            fields = ["s3_key", "content_hash", "updated_at"]
            existing.s3_key = s3_key
            existing.content_hash = digest
            if not existing.title:
                existing.title = _phase_artifact_title(inp)
                fields.append("title")
            existing.save(update_fields=fields)
        artifact = {"id": str(existing.id)}
    else:
        artifact = tools.register_artifact(
            inp.tenant_id, inp.project_id, inp.run_id, inp.phase, inp.phase,
            "internal", digest, s3_key=s3_key, title=_phase_artifact_title(inp),
        )
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.cost_usd = Decimal(str(cost))
        # MERGE, never overwrite: report_phase stored the companion's raw report under
        # outputs["report"] just before this activity — it is preview's documented last
        # fallback and must survive result registration.
        run.outputs = {**(run.outputs or {}), "artifact_s3_key": s3_key,
                       "content_hash": digest, "cost_usd": cost}
        dispatch = dict((run.inputs or {}).get("dispatch") or {})
        if dispatch:
            dispatch["status"] = "reported"
            run.inputs = {**(run.inputs or {}), "dispatch": dispatch}
        run.save(update_fields=["cost_usd", "outputs", "inputs", "updated_at"])
        # Reconcile a parked/STALLED run (Bugs S.No 89): a companion that went offline then
        # returned and reported successfully un-parks the WorkItem — the run flows on to its
        # gate (open_gate sets AWAITING_GATE), so the takeover flag must not linger.
        WorkItem.objects.filter(
            id=inp.work_item_id, tenant_id=inp.tenant_id, takeover_flag=True
        ).update(takeover_flag=False)
        tools.log_event(inp.tenant_id, "orchestrator", "run.executed", "run", inp.run_id,
                        {"artifact_id": artifact["id"]})
        if not body:
            # An "ok" report with no text means the engine ended without producing the phase
            # document (e.g. max-turns). Don't hide it behind a blank preview at gate time —
            # make it visible in the run's event stream.
            tools.log_event(
                inp.tenant_id, "orchestrator", "phase.empty_result", "run", inp.run_id,
                {"phase": inp.phase,
                 "message": report.message or
                 "companion reported ok but the engine returned no final text; "
                 "the staged phase draft is empty"})
    # Bugs S.No 177 — security defect loopback: turn Critical/High security_finding artifacts
    # this run registered into `defect` child WorkItems so findings become trackable work.
    # Advisory gate stays (team decision) — this only surfaces findings, it does NOT block the
    # gate. No-op for every other phase and when the run produced no structured findings.
    if inp.phase == "security":
        _record_security_findings_from_run(inp)
    return {"artifact_ids": [artifact["id"]], "cost_usd": cost}


def _record_security_findings_from_run(inp: AgentRunInput) -> dict:
    """Read the `security_finding` artifacts this security run registered and drive the defect
    loopback (`record_security_findings`) so open Critical/High findings open (and resolved ones
    close) `defect` child WorkItems. Findings carry their id + severity in the artifact's
    `external_ref` (the agent registers them structured — agents/10_security/agent.md). A finding
    without a structured id+severity is skipped rather than guessed, so nothing is fabricated;
    if none carry structure the loopback simply does nothing."""
    from apps.quality.services import record_security_findings

    with tenant_context(inp.tenant_id):
        rows = list(
            Artifact.objects.filter(
                run_id=inp.run_id, tenant_id=inp.tenant_id, type="security_finding"
            ).values("title", "external_ref")
        )
        review_id = (
            Artifact.objects.filter(
                run_id=inp.run_id, tenant_id=inp.tenant_id, type="security_review"
            ).values_list("id", flat=True).first()
        )
    findings = []
    for r in rows:
        ext = r.get("external_ref") or {}
        fid = ext.get("finding_id") or ext.get("id")
        sev = ext.get("severity")
        if fid and sev:
            findings.append(
                {"id": str(fid), "severity": str(sev), "title": r.get("title") or str(fid)}
            )
    if not findings:
        return {"opened": [], "closed": [], "blocking": []}
    return record_security_findings(
        tenant_id=inp.tenant_id, project_id=inp.project_id, work_item_id=inp.work_item_id,
        findings=findings, review_artifact_id=str(review_id) if review_id else None,
    )


def mark_phase_takeover_core(inp: AgentRunInput) -> dict:
    """Offline-companion path: the companion did not report before the timeout → park the
    WorkItem for human takeover. The run is marked STALLED, NOT terminal FAILED (Bugs S.No 89):
    a companion that only slept can still return and report, and that late report reconciles
    the run through the normal gate path (the workflow stays alive waiting). Terminal failure
    happens only on an explicit human takeover (`abandon_run`) or a reported failure."""
    with tenant_context(inp.tenant_id):
        WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id).update(
            takeover_flag=True)
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.STALLED)
        tools.log_event(inp.tenant_id, "orchestrator", "phase.takeover", "run", inp.run_id,
                        {"reason": "companion offline / no report before timeout",
                         "reconcilable": True})
    return {"status": "takeover"}


def park_run_core(inp: AgentRunInput, reason: str, resume_from: str) -> dict:
    """Bugs S.No 157: an error mid-phase PARKS the run instead of killing it, so a human can
    resume from the failed step rather than re-running the whole phase. Marks the run STALLED
    (non-terminal — the same park S.No 89 uses for a report timeout) with a reason + the step to
    resume from, while the workflow stays ALIVE waiting for `resume_run` or `abandon_run`.

    Also closes a silent-failure gap: `verify_writes` runs with maximum_attempts=1, so when it
    raised, the workflow crashed BEFORE any fail_run — nothing ever wrote `run.outputs.error`, and
    the run console (which reads exactly that field) showed a failed run with no reason at all.
    Parking always records the reason. Idempotent."""
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.STALLED
        run.outputs = {**(run.outputs or {}), "error": reason,
                       "resume_from": resume_from, "resumable": True}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "run.parked", "run", inp.run_id,
                        {"reason": reason, "resume_from": resume_from, "resumable": True})
    return {"status": "parked", "reason": reason, "resume_from": resume_from}


def resume_run_state_core(inp: AgentRunInput) -> dict:
    """Bugs S.No 157: a human resumed a parked phase run — un-park it and clear the park markers
    so the console stops showing a stale failure. Idempotent."""
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        outputs = {**(run.outputs or {})}
        resume_from = outputs.get("resume_from", "")
        for key in ("error", "resume_from", "resumable"):
            outputs.pop(key, None)
        run.status = Run.Status.RUNNING
        run.outputs = outputs
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "run.resumed", "run", inp.run_id,
                        {"resume_from": resume_from})
    return {"status": "resumed", "resume_from": resume_from}


def fail_run_core(inp: AgentRunInput, reason: str) -> dict:
    """A companion reported a failed phase → flag the run failed (the body, if any, is on the
    report). Mirrors the execute_agent failure path."""
    # Plain-language reason for the run console (Bugs S.No 146, planning path): the companion
    # reports the raw engine error (e.g. 'Command failed with exit code 1'); classify it here so
    # a security/planning failure reads like a build failure does, not as a raw exit code.
    reason = classify_phase_failure(reason)
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.FAILED
        run.ended_at = _now()
        run.outputs = {**(run.outputs or {}), "error": reason}
        run.save(update_fields=["status", "outputs", "ended_at", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "run.failed", "run", inp.run_id,
                        {"error": reason})
    return {"status": "failed"}


# ── activity wrappers (sync → run in the worker's thread pool) ──────
# Activities run in worker threads with no request/response cycle, so close the
# thread's Django connection at the boundary — otherwise long-running workers (and
# multi-activity tests) leak a DB connection per thread. Reopened lazily next use.
def _boundary(core, *args):
    from django.db import connection

    try:
        return core(*args)
    finally:
        connection.close()


@activity.defn(name="compose_manifest")
def compose_manifest_activity(inp: AgentRunInput) -> str:
    return _boundary(compose_manifest_core, inp)


@activity.defn(name="execute_agent")
def execute_agent_activity(inp: AgentRunInput, manifest: str) -> dict:
    return _boundary(execute_agent_core, inp, manifest)


@activity.defn(name="open_gate")
def open_gate_activity(inp: AgentRunInput) -> str:
    return _boundary(open_gate_core, inp)


@activity.defn(name="publish_artifacts")
def publish_artifacts_activity(inp: AgentRunInput) -> dict:
    return _boundary(publish_artifacts_core, inp)


@activity.defn(name="transition_work_item")
def transition_work_item_activity(inp: AgentRunInput, to_state: str) -> dict:
    return _boundary(transition_work_item_core, inp, to_state)


@activity.defn(name="reject_run")
def reject_run_activity(inp: AgentRunInput, comment: str) -> dict:
    return _boundary(reject_run_core, inp, comment)


@activity.defn(name="verify_writes")
def verify_writes_activity(inp: AgentRunInput, expected_types: list[str]) -> dict:
    return _boundary(verify_write_completeness_core, inp, expected_types)


@activity.defn(name="dispatch_phase")
def dispatch_phase_activity(inp: AgentRunInput, manifest: str) -> dict:
    return _boundary(dispatch_phase_core, inp, manifest)


@activity.defn(name="register_phase_result")
def register_phase_result_activity(inp: AgentRunInput, report: PhaseReport) -> dict:
    # The annotation is load-bearing (Bugs.xlsx S.No 160): Temporal converts an activity arg to
    # its parameter's annotated type, and hands an UNANNOTATED one back as a plain dict. Without
    # it, `report` arrived as a dict and every attribute read silently returned a default.
    return _boundary(register_phase_result_core, inp, report)


@activity.defn(name="mark_phase_takeover")
def mark_phase_takeover_activity(inp: AgentRunInput) -> dict:
    return _boundary(mark_phase_takeover_core, inp)


@activity.defn(name="fail_run")
def fail_run_activity(inp: AgentRunInput, reason: str) -> dict:
    return _boundary(fail_run_core, inp, reason)


@activity.defn(name="park_run")
def park_run_activity(inp: AgentRunInput, reason: str, resume_from: str) -> dict:
    return _boundary(park_run_core, inp, reason, resume_from)


@activity.defn(name="resume_run_state")
def resume_run_state_activity(inp: AgentRunInput) -> dict:
    return _boundary(resume_run_state_core, inp)


ALL_ACTIVITIES = [
    compose_manifest_activity,
    execute_agent_activity,
    open_gate_activity,
    publish_artifacts_activity,
    transition_work_item_activity,
    reject_run_activity,
    verify_writes_activity,
    dispatch_phase_activity,
    register_phase_result_activity,
    mark_phase_takeover_activity,
    fail_run_activity,
    park_run_activity,
    resume_run_state_activity,
]
