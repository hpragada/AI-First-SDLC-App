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

from apps.a11y.journey import JOURNEY_PHASE as A11Y_JOURNEY_PHASE
from apps.a11y.judge import JUDGE_PHASE as A11Y_JUDGE_PHASE
from apps.gates.models import Approval
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem
from drivers import ClaudeDriver
from manifest import compose_manifest  # noqa: F401  (re-exported for callers/tests)
from manifest.budget import chunks_for_budget
from manifest.composer import TRUNCATION_MARKER, compose_manifest_with_report
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
# `ToolSearch` loads tools the CLI deferred out of the agent's initial context; without it a
# granted tool can be invisible to the agent (see `daemon.PLAN_ALLOWED_TOOLS` for the run that
# proved it). Schemas only, for tools already granted here — no widening.
#: Granted to the CODE REVIEW agent on top of the base list, and to no other agent. The base list
#: above is shared by every phase, so a tool added there becomes a capability for all of them;
#: reading a repository's files is 08's business alone.
_REVIEW_ONLY_TOOL_NAMES = ["get_pr_file"]

PLATFORM_TOOLS = [f"mcp__platform-state__{name}" for name in _PLATFORM_TOOL_NAMES] + ["ToolSearch"]
REVIEW_TOOLS = (
    [f"mcp__platform-state__{name}" for name in _PLATFORM_TOOL_NAMES + _REVIEW_ONLY_TOOL_NAMES]
    + ["ToolSearch"]
)


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
def _log_manifest_truncations(inp: AgentRunInput, manifest: str,
                              report: dict[str, dict[str, int]] | None = None) -> None:
    """Record which manifest sections were cut to fit their budget — never silently.

    Truncation used to leave no trace anywhere: not in the run's events, not on any screen. A
    section could lose real instructions and the only symptom would be an agent that seemed to
    have forgotten something, with nothing to point at. This makes the loss a fact you can query,
    which is also the data needed to tune the caps instead of guessing at them again.
    """
    cut: list[str] = []
    for block in manifest.split("\n# "):
        if not block.strip():
            continue
        name = block.splitlines()[0].strip().lstrip("# ").strip()
        if TRUNCATION_MARKER in block:
            cut.append(name)
    if not cut:
        return
    # What each section was ALLOWED and what it ASKED FOR. With a fixed cap, naming the section
    # was enough; with an allowance that moves, "Retrieved Knowledge was shortened" no longer
    # says whether it was starved or simply enormous — and that is the difference anyone tuning
    # this needs. Omitted when no budget was in play, so the payload stays as it was.
    # The whole allocation, not just the cut sections: nine small entries, and seeing what the
    # OTHER sections were holding is how you tell a starved section from a greedy neighbour.
    # (`cut` carries display headers like "Retrieved Knowledge"; the report is keyed by budget
    # field name, so matching the two up here would only invent a mapping that can drift.)
    payload: dict = {"sections": cut, "phase": inp.phase}
    if report:
        payload["budget"] = report
    tools.log_event(
        inp.tenant_id, "orchestrator", "manifest.truncated", "run", inp.run_id, payload,
    )


def _review_history(tenant_id: str, run_id: str) -> list[dict]:
    """The review conversation carried into this run by "Request changes".

    Read off the Run ROW rather than the input object on purpose. `compose_manifest_core` is
    duck-typed — `BuildInput` flows through it too (dispatch_build_core, dispatch_remediation_core,
    review_provider) — so any new attribute read off `inp` would raise AttributeError on every
    build dispatch. It also keeps a list that grows with each revision out of the Temporal payload.
    """
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).only("inputs").first()
    return list((run.inputs or {}).get("review_history") or []) if run else []


def _manifest_budget(inp: AgentRunInput) -> int:
    """This run's whole-manifest token budget, from the model that will actually read it.

    One indexed primary-key lookup, deliberately not cached. It sits beside `get_context`, which
    already costs several queries plus a ranking pass over every knowledge chunk in the project,
    so the cost is noise — and a process-level cache would go stale the moment the agent registry
    is re-seeded, trading a measurable correctness risk for an unmeasurable saving.

    The model is read from the AgentSpec ROW rather than carried on `inp`, and `agent_spec_id` is
    read with `getattr`: `compose_manifest_core` is duck-typed — `BuildInput` flows through it, and
    so does a bare SimpleNamespace — so ANY attribute assumed off `inp` is a dispatch-time
    AttributeError waiting to happen. `test_compose_manifest_survives_a_build_shaped_input` exists
    for exactly this and caught the first version of this function reading `inp.agent_spec_id`
    directly. An input that cannot name its agent simply gets the fallback budget, which is the
    size the platform used before any of this existed.
    """
    from apps.registry.models import AgentSpec
    from manifest.budget import total_for_model

    spec_id = getattr(inp, "agent_spec_id", None)
    model = ((AgentSpec.objects.filter(id=spec_id, tenant_id=inp.tenant_id)
              .values_list("recommended_model", flat=True).first()) if spec_id else "") or ""
    total, used_fallback = total_for_model(model)
    if used_fallback:
        # Never silent. An unrecognised model still composes a manifest exactly the size the
        # platform used to produce, but somebody has to learn that a new model needs a row —
        # otherwise the first sign is a client wondering why their briefings got smaller.
        tools.log_event(
            inp.tenant_id, "orchestrator", "manifest.model_unknown", "run", inp.run_id,
            {"model": model or "(not set)", "assumed_budget": total},
        )
    return total


def compose_manifest_core(inp: AgentRunInput) -> str:
    review_history = _review_history(inp.tenant_id, inp.run_id)
    with tenant_context(inp.tenant_id):
        work_item = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        total_budget = _manifest_budget(inp)
        # Retrieve what the budget can actually hold, rather than fetching a fixed eight chunks
        # and letting the composer bin a third of them (truncation register T3).
        context = tools.get_context(
            inp.tenant_id, inp.project_id, inp.phase, work_item_id=inp.work_item_id,
            knowledge_chunks=chunks_for_budget(total_budget))
        manifest, report = compose_manifest_with_report(
            context=context, work_item=tools._work_item(work_item),
            phase=inp.phase, rules=load_rules(), review_history=review_history,
            total_budget=total_budget,
        )
        _log_manifest_truncations(inp, manifest, report)
        return manifest


_EXECUTED_STATES = {Run.Status.AWAITING_GATE, Run.Status.APPROVED, Run.Status.COMPLETED}


def _technical_detail(raw: str, sentence: str) -> str:
    from .build_activities import _technical_detail as detail

    return detail(raw, sentence)


def describe_phase_failure(reason: str, *, phase: str = "", parked: bool = False):
    """A planning/review phase's failure, said the way a build's is (run-console wording fix,
    2026-09-21, option A — team: "apply the same fix to the agent runs too").

    Same sentences as `describe_build_failure`, naming the phase ("The PRD phase stopped
    because …"). The engine's raw output is NOT in the sentence: callers keep it as
    `outputs.error_detail`, shown under a closed "Technical details" (Bugs S.No 146 kept)."""
    from apps.labels import phase_label

    from .build_activities import describe_build_failure

    what = f"The {phase_label(phase)} phase" if phase else "The phase"
    return describe_build_failure(reason, subject="build", parked=parked, what=what)


def classify_phase_failure(reason: str, *, phase: str = "", parked: bool = False) -> str:
    """The banner sentence for a phase failure — see `describe_phase_failure`."""
    return describe_phase_failure(reason, phase=phase, parked=parked).sentence


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
        said = describe_phase_failure(str(exc), phase=inp.phase)
        error_message = said.sentence
        with tenant_context(inp.tenant_id):
            run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
            run.status = Run.Status.FAILED
            run.ended_at = _now()
            run.outputs = {**(run.outputs or {}), "error": error_message,
                           "error_detail": _technical_detail(str(exc), error_message)}
            run.save(update_fields=["status", "outputs", "ended_at", "updated_at"])
            tools.log_event(
                inp.tenant_id, "orchestrator", "run.failed", "run", inp.run_id,
                {"error": said.cause},
            )
        recover_unread_document_core(inp)  # a failed vision pass must not leave a document empty
        raise

    body = result.outputs.get("result") or result.outputs.get("text") or ""
    s3_key = f"drafts/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/{inp.phase}.md"
    get_object_store().put(s3_key, body)
    digest = content_hash(body.encode("utf-8"))

    artifact = tools.register_artifact(
        inp.tenant_id, inp.project_id, inp.run_id, inp.phase, inp.phase,
        "internal", digest, s3_key=s3_key,
        external_ref={"source": PHASE_REPORT_SOURCE},   # platform-made, not agent-made
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
                # gate (D6), the blocking-test rule on the test gate (D9). The project is
                # passed so the design checklist can honour the project's accessibility
                # policy (QA-08) — without it, every project gets the default questions.
                "conditions": conditions_for_phase(
                    inp.phase, tenant_id=inp.tenant_id, project_id=inp.project_id),
            },
        )
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        if run.status != Run.Status.AWAITING_GATE:
            run.status = Run.Status.AWAITING_GATE
            run.save(update_fields=["status", "updated_at"])
        # A gate is now open on what this run drafted, so those drafts are no longer drafts
        # nobody has looked at: they are waiting on a named person (Bugs S.No 218). Opening a
        # gate used to leave them reading "Draft", indistinguishable from work nobody had asked
        # anyone to review. `staged` is the status that already exists for exactly this — the
        # build path sets it when it opens a PR — and the screen now calls it "Waiting for
        # approval".
        #
        # DRAFT only, so nothing already approved, published or superseded is ever moved
        # backwards, and a retried activity finds nothing left to change. Both ways out of the
        # gate still work on a staged row: approval publishes the run's artifacts whatever their
        # status (`publish_artifacts_core`), and a rejection supersedes everything not published
        # (`reject_run_core`).
        Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id, status=Artifact.Status.DRAFT,
        ).update(status=Artifact.Status.STAGED, updated_at=_now())
        if created:
            tools.log_event(
                inp.tenant_id, "orchestrator", "gate.opened", "approval", str(approval.id),
                {"required_role": inp.required_role},
            )
    return str(approval.id)


#: Phases whose artifacts are NEVER marked published by this activity, however the run ended.
#:
#: **What went wrong.** Publishing happens on gate APPROVAL, which is the platform’s whole
#: story: published means a named human approved this and it is the project’s answer. A run
#: started with `auto_approve` has no gate, and this activity runs anyway — which is correct for
#: the one case it was built for (document vision, 00e: the human had already adopted the
#: document those pages came from, so a second gate would ask them the same question twice).
#:
#: The accessibility judging and keyboard-journey runs set `auto_approve` for a different and
#: good reason — nobody is watching their carrier work item, and a gate there would hang the
#: audit forever waiting on an approval nobody knows to give — and inherited the publishing with
#: it, without inheriting the justification. Measured on 25 August across two tenants: **every**
#: artifact of every judging run, marked published, approved by nobody. The `assumption` rows are
#: the ones a person notices; the judging documents are marked as run output on screen and so
#: wore a disguise.
#:
#: They stay DRAFT, which is what they are: kept, readable, previewable, still handed to later
#: phases (`get_context` excludes only rejected work), and awaiting the human step. For
#: accessibility that step is signing the conformance statement, which sets APPROVED on its own
#: document and is the only signature in this capability that means anything.
NEVER_AUTO_PUBLISHED_PHASES = frozenset({"a11y_judge", "a11y_journey"})


def publish_artifacts_core(inp: AgentRunInput) -> dict:
    """On APPROVED: snapshot to S3 and mark every artifact published-INTERNAL. External
    export is user-triggered (team flow decision, 2026-07-07) via POST
    /artifacts/{id}/publish/, governed by the project's phase-scoped export policy
    (integrations.export_policy) — gate approval never auto-pushes to a SoR. Idempotent —
    already-published artifacts are skipped.

    Except for `NEVER_AUTO_PUBLISHED_PHASES`, which are left as they are and named in the event
    rather than passed over in silence — see that constant for what publishing them cost.
    """
    store = get_object_store()
    with tenant_context(inp.tenant_id):
        artifacts = list(Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id))

    published: list[str] = []
    left_draft: list[str] = []
    #: Artifacts the gate approved that could NOT be published, with the reason. Distinct from
    #: `left_draft`, which is a deliberate policy decision — these are failures.
    failed: list[dict] = []
    for artifact in artifacts:
        if artifact.phase in NEVER_AUTO_PUBLISHED_PHASES:
            # Not a skip-if-already-done: this is a decision, and it is recorded as one. A run
            # that quietly did less than its name says is the shape of failure this codebase
            # keeps meeting.
            left_draft.append(str(artifact.id))
            continue
        if artifact.status == Artifact.Status.PUBLISHED:
            published.append(str(artifact.id))
            continue

        if artifact.s3_key:  # immutable audit snapshot regardless of SoR
            # Keyed by ARTIFACT, not by phase. It used to be `{artifact.phase}.v{version}.md`,
            # and every artifact of a phase shares that phase and (on a first run) that
            # version — so a seven-artifact ideation wrote seven snapshots over the top of
            # each other and kept ONE (S.No 316). Silent: no error, no warning, just six
            # missing files in the record that is supposed to prove what a human approved.
            snap = (
                f"snapshots/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/"
                f"{artifact.phase}.{artifact.id}.v{artifact.version}.md"
            )
            try:
                store.copy(artifact.s3_key, snap)
            except Exception as exc:  # noqa: BLE001 — see below
                # ONE artifact's snapshot failing must not abort the other six (S.No 315).
                # This loop is not a transaction, so an exception here used to leave the run
                # half-published AND unfinished: the gate was decided, the gate was gone from
                # the screen, and no control existed anywhere that would publish the rest.
                # Temporal then retried the activity forever, failing identically each time.
                # The human's decision was real and the other artifacts are fine — honour it,
                # and record precisely what was left behind.
                failed.append({"id": str(artifact.id), "title": artifact.title,
                               "reason": f"{type(exc).__name__}: {exc}"})
                continue

        tools.update_artifact(
            inp.tenant_id, str(artifact.id),
            status=Artifact.Status.PUBLISHED, sor=Artifact.SoR.INTERNAL,
        )
        published.append(str(artifact.id))

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.COMPLETED
        # Stamp the end (S4-25/S5-26). Only the FAILURE paths set this, so every successful run in
        # the system carried `ended_at = NULL` — no duration could be shown anywhere, and nobody
        # could see a phase getting slower over time. The oddity that failures were timed and
        # successes were not is what makes it read as an omission rather than a decision.
        run.ended_at = _now()
        run.save(update_fields=["status", "ended_at", "updated_at"])
        # The Approval decision is recorded by the gate service (decide_gate, T9),
        # not here — that path owns the approver + decided_at.
        tools.log_event(
            inp.tenant_id, "orchestrator", "artifacts.published", "run", inp.run_id,
            {"artifact_ids": published, "left_draft": left_draft, "failed": failed},
        )
        if failed:
            # A SECOND event, on the run, so this is visible where people actually look
            # instead of only in a worker container's log — which is where the 2026-10-05
            # failure hid while the screens showed nothing wrong anywhere (S.No 315).
            tools.log_event(
                inp.tenant_id, "orchestrator", "artifacts.publish_failed", "run", inp.run_id,
                {"count": len(failed), "artifacts": failed},
            )
    # A vision run's artifact IS the document's artifact — link it back, or the document would
    # stay pointing at nothing (see link_vision_artifact_core).
    link_vision_artifact_core(inp)
    return {"published": published, "left_draft": left_draft, "failed": failed}


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
        # Stamp when it ended. Rejection is terminal exactly like publish (:publish_artifacts_core)
        # and failure (:fail_run_core), both of which stamp it — this path was the last one that
        # did not, so no screen could show a rejected run's duration.
        run.ended_at = _now()
        run.save(update_fields=["status", "ended_at", "updated_at"])
        # The drafts this run produced are no longer the project's answer for their type. They are
        # NOT deleted — they are what the agent actually wrote, a revision's manifest cites them by
        # id, and the run console still lists them — but `get_context` must stop serving them
        # downstream as authoritative. A rejected artifact that keeps being handed to later phases
        # is a quieter failure than a rejected run.
        superseded = Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id,
        ).exclude(status=Artifact.Status.PUBLISHED).update(
            status=Artifact.Status.SUPERSEDED, updated_at=_now(),
        )
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        # Approval decision/comment recorded by the gate service (decide_gate, T9).
        tools.log_event(
            inp.tenant_id, "orchestrator", "run.rejected", "run", inp.run_id,
            {"comment": comment, "superseded_artifacts": superseded},
        )
    return {"status": "rejected", "superseded_artifacts": superseded}


def build_review_round(tenant_id: str, run_id: str, direction: str) -> dict:
    """One entry in the review conversation: what the reviewer asked for on this run, and what
    the run had produced when they asked. Shared by the planning and build revise paths."""
    with tenant_context(tenant_id):
        approval = (
            Approval.objects.filter(run_id=run_id, tenant_id=tenant_id)
            .select_related("approver").order_by("-decided_at").first()
        )
        approver = getattr(getattr(approval, "approver", None), "email", "") or (
            getattr(approval, "required_role", "") or "a reviewer")
        produced = [
            {"id": str(a.id), "type": a.type, "title": a.title, "version": a.version}
            for a in Artifact.objects.filter(run_id=run_id, tenant_id=tenant_id)
            .order_by("type", "title")
        ]
    decided = getattr(approval, "decided_at", None)
    return {
        "run_id": str(run_id),
        "direction": direction or getattr(approval, "comment", "") or "",
        "decided_at": decided.strftime("%Y-%m-%d") if decided else "",
        "approver": approver,
        "artifacts": produced,
    }


def retrigger_revision_core(inp: AgentRunInput, direction: str) -> dict:
    """"Request changes": start a fresh run of this phase carrying the reviewer's direction.

    Runs from the WORKFLOW, after `reject_run`, and that ordering is load-bearing. Doing it from
    the REST layer instead would race: `decide_gate` returns 200 as soon as it has signalled, while
    the run is still AWAITING_GATE — which IS in `_ACTIVE_RUN_STATUSES` — so `_guard_no_active_run`
    would reject the new run with a 409. Here the run is already REJECTED, which is not in that
    set, and Temporal guarantees the activity order.

    Idempotent, because Temporal will retry an activity whose completion was lost. The guard is a
    lookup for a run that already revises this one, not a flag we set afterwards: a flag written
    after the trigger leaves a window where a retry creates a SECOND run and then dies on
    `_guard_no_active_run` against the run it just made.
    """
    from .trigger import ActiveRunError, trigger_phase

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        existing = (run.outputs or {}).get("revision_run_id")
        if not existing:
            already = (
                Run.objects.filter(tenant_id=inp.tenant_id, inputs__revision_of=str(inp.run_id))
                .order_by("created_at").values_list("id", flat=True).first()
            )
            existing = str(already) if already else None
        if existing:
            return {"revision_run_id": existing, "reused": True}
        history = list((run.inputs or {}).get("review_history") or [])
        spec = AgentSpec.objects.get(id=inp.agent_spec_id, tenant_id=inp.tenant_id)
        agent_key = spec.key
        # Carry the triggering user forward so the revision resolves the SAME companion (req #1).
        triggered_by = str(run.triggered_by_id) if run.triggered_by_id else None

    round_entry = build_review_round(inp.tenant_id, inp.run_id, direction)
    round_entry["revision"] = len(history) + 1
    history = history + [round_entry]

    try:
        result = trigger_phase(
            tenant_id=inp.tenant_id, project_id=inp.project_id, work_item_id=inp.work_item_id,
            agent_key=agent_key, gate_type=inp.gate_type, required_role=inp.required_role,
            triggered_by=triggered_by, review_history=history, revision_of=str(inp.run_id),
        )
    except ActiveRunError:
        # Another run for this work item started in the gap. Do not queue behind it and do not
        # fail the (already terminal) rejected run — say so and let the reviewer re-ask.
        with tenant_context(inp.tenant_id):
            tools.log_event(inp.tenant_id, "orchestrator", "run.revision_failed", "run",
                            inp.run_id, {"reason": "another run is already active"})
        return {"revision_run_id": None, "reason": "another run is already active"}

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.outputs = {**(run.outputs or {}), "revision_run_id": result.run_id}
        run.save(update_fields=["outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "run.revision_requested", "run",
                        inp.run_id, {"revision_run_id": result.run_id,
                                     "revision": round_entry["revision"]})
    return {"revision_run_id": result.run_id, "revision": round_entry["revision"]}


#: The hash of a body staged from no text at all. `register_phase_result_core` always stamps
#: the staged body's real digest, so an expected artifact carrying this is provably empty.
_EMPTY_BODY_HASH = content_hash(b"")

#: `external_ref["source"]` on the artifact the PLATFORM files from the engine's final message,
#: distinguishing it from every artifact an agent registered through `register_artifact`. Written
#: at both sinks (companion `register_phase_result_core` and direct `execute_phase`) and read by
#: `verify_write_completeness_core`. Changing this string breaks that check silently — the marker
#: is a contract between the two, not a label.
PHASE_REPORT_SOURCE = "phase_report"

#: Phases whose real deliverable is a RICHER artifact than the platform's generic phase-typed
#: blob. verify_writes requires these instead of the bare phase type so a run that produced only
#: an empty/summary "<phase>" blob — but not the actual work product — fails loudly rather than
#: opening the gate on nothing (Bugs S.No 179). Security must ship its actual review document,
#: which the agent registers (stage_artifact_body → register_artifact) as `security_review`.
_PHASE_REQUIRED_ARTIFACTS = {
    "security": ["security_review"],
    # Onboarding's deliverable is the gap report the agent submits, not the generic "onboarding"
    # blob holding its closing message. Without this line a run whose agent never called
    # `submit_gap_report` — the exact failure S5-1 describes, where the prompt pointed at no tool —
    # completed quietly with nothing for the user to read. Now it fails loudly and says so.
    "onboarding": ["gap_report"],
}

#: How much of the previous version's text an auto-applied (vision) version must still carry.
#: 00e is instructed to reproduce the extraction it read AND add what the pictures hold, so a
#: faithful pass grows the body; a pass that comes back materially SHORTER has dropped prose it
#: was meant to keep (Part B fix 1). The 10% slack absorbs honest reformatting — collapsed
#: whitespace, a rebuilt table, dropped page-furniture — without licensing real loss.
_VISION_MIN_RETAINED_RATIO = 0.9


def _prior_version(artifact):
    """The version this artifact supersedes: the newest sibling registered before it under the
    same identity (`register_artifact` versions on project+phase+type+title). Returns None for a
    first registration — nothing to compare against, so nothing to guard."""
    return (
        Artifact.objects
        .filter(tenant_id=artifact.tenant_id, project_id=artifact.project_id,
                phase=artifact.phase, type=artifact.type, title=artifact.title)
        .exclude(id=artifact.id)
        .filter(version__lt=artifact.version)
        .order_by("-version")
        .first()
    )


def _assert_no_content_loss(inp: AgentRunInput, object_store=None) -> None:
    """Auto-applied versions publish with no human gate, so the platform — not a reviewer — is
    the last line of defence against a bad transcription (Part B fix 1).

    00e re-registers an adopted document as a new version that must contain the original
    extracted text PLUS the diagrams/screenshots the extraction missed. That contract lives in
    the agent's prompt, and a prompt is not a guarantee: a pass that returned only the diagram
    transcriptions would satisfy the non-empty check above, publish over the adopted document,
    and silently drop the document's prose from every downstream read (get_context serves the
    newest version). Compare the new body against the one it supersedes and refuse to publish a
    version that shrank — the run fails loudly and the adopted v1 stays live and readable.

    Deliberately conservative: only bodies we can actually read on both sides are judged. A
    missing pointer, an unreadable object, or a first registration makes no claim we can test,
    so it passes rather than blocking adoption on an unrelated storage hiccup.
    """
    store = object_store          # built lazily: a run with nothing to compare touches no S3
    # The baseline is whatever the transcription was supposed to preserve. Usually that's the
    # previous version of the same artifact. For a document whose artifact this run is CREATING
    # there is no previous version — the thing it must not lose is the extraction staged at
    # upload, so that is measured instead. Either way the guard has something real to hold.
    baseline_key = None
    source_document_id = _vision_source_document(inp)
    if source_document_id:
        from apps.integrations.models import SourceDocument

        with tenant_context(inp.tenant_id):
            src = SourceDocument.objects.filter(
                id=source_document_id, tenant_id=inp.tenant_id).first()
        baseline_key = ((src.provenance or {}).get("extracted_s3_key") if src else None)
    with tenant_context(inp.tenant_id):
        new_artifacts = list(
            Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
            # The platform registers a phase-typed artifact for EVERY run, holding the agent's
            # closing message rather than the document (register_phase_result_core). Measuring
            # that against the document's text compares two unrelated things — a short, perfectly
            # normal sign-off would read as catastrophic content loss and fail a good run. Only
            # what the agent registered as the document itself is judged.
            .exclude(type=inp.phase)
        )
        pairs = [(a, _prior_version(a)) for a in new_artifacts]
    for artifact, prior in pairs:
        prior_key = prior.s3_key if prior is not None else baseline_key
        if not artifact.s3_key or not prior_key:
            continue
        if store is None:
            store = s3_from_settings()
        try:
            new_len = len(store.get(artifact.s3_key))
            prior_len = len(store.get(prior_key))
        except Exception:  # noqa: BLE001 — unreadable body proves nothing; don't block on it
            continue
        if prior_len == 0:
            continue
        if new_len < prior_len * _VISION_MIN_RETAINED_RATIO:
            kept = ("the version it replaces" if prior is not None
                    else "the text already extracted from the document")
            raise WriteCompletenessError(
                f"run {inp.run_id} (auto-apply) produced a shorter rendering of "
                f"'{artifact.title or artifact.type}' than {kept} "
                f"({new_len} bytes vs {prior_len}) — the new version dropped content it was "
                "meant to keep, so it is not published."
            )


def _no_agent_artifact_reason(inp: AgentRunInput) -> str:
    """Explain a run that registered nothing of its own, from EVIDENCE rather than a guess.

    The first version of this message asserted one cause — "the agent's write tools being
    absent from its context" — because that was the cause of the run it was written for
    (2026-07-30, §4b: `ToolSearch` denylisted, so granted tools were deferred out of reach).
    Run fad927a2 had a different one: its write tools were fine and `ask_human` broke, so the
    message sent the reader hunting the wrong subsystem entirely.

    A pending clarification on the run is decisive and free to check: it means the agent DID
    reach its tools, asked, and never got an answer — and Rule 1 then forbids it writing
    anything. Say that, and point at the recovery that actually works.
    """
    from apps.clarifications.models import Clarification

    base = (
        f"run {inp.run_id} registered no artifacts of its own — the only thing recorded is "
        f"the platform's copy of the engine's final message, so whatever the agent produced "
        f"was never saved as a reviewable artifact. No gate is opened. "
    )
    with tenant_context(inp.tenant_id):
        pending = list(
            Clarification.objects.filter(
                run_id=inp.run_id, tenant_id=inp.tenant_id,
                status=Clarification.Status.PENDING,
            ).values_list("id", flat=True)[:1]
        )
    if pending:
        return base + (
            f"The agent asked a clarification ({pending[0]}) that is still unanswered, so it "
            f"stopped before producing anything — Rule 1 forbids writing artifacts until the "
            f"answers come back. This is NOT a tooling failure. Answer the clarification, then "
            f"re-run the phase: answered clarifications are replayed into the new run's "
            f"manifest, so it will not ask again."
        )
    return base + (
        "Re-run the phase. Check the run's tool calls: no `register_artifact` at all points at "
        "the agent's write tools being absent from its context; calls that were made and "
        "failed point at the platform-state MCP server."
    )


def verify_write_completeness_core(
    inp: AgentRunInput, expected_types: list[str], object_store=None,
) -> dict:
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
    # The accessibility judge (09c, QA-02a) writes verdicts, not artifacts, so "did it register
    # a document?" is the wrong question for it entirely — and it runs auto-apply, so without
    # this branch the check below would fail every judgment run. Its own bar is coverage: every
    # element dispatched to it must have been reported on. Checked FIRST so the phase is decided
    # before the artifact-shaped rules get a chance to answer for it.
    if inp.phase == A11Y_JUDGE_PHASE:
        from apps.a11y.aipass import finish_ai_pass
        from apps.a11y.judge import verify_judgment_completeness

        try:
            counts = verify_judgment_completeness(
                tenant_id=inp.tenant_id, project_id=inp.project_id, run_id=inp.run_id)
        finally:
            # QA-12: the merged report is published whether or not the judging was complete.
            # `finally`, not "after", because an incomplete run raises above — and that is
            # precisely the run whose report matters most: its unjudged elements have just been
            # recorded as `uncertain` for a human, and without a report nobody can see them.
            # The report itself says the check was incomplete (D-A11Y-3).
            finish_ai_pass(tenant_id=inp.tenant_id, judge_run_id=inp.run_id)
        return {"present": [f"{counts['judged']} judged"],
                "expected": [f"{counts['dispatched']} dispatched"]}

    # The keyboard journey (09d, QA-20/G6a) writes step outcomes and verdicts, not artifacts —
    # the same shape as the judge above, and it needs its own branch for the same reason: without
    # one, a journey that walked a whole application perfectly would reach this check, be asked
    # for an `a11y_journey` document it was never meant to write, and park the run.
    #
    # **An incomplete journey is not a failed one, and this branch must never make it look like
    # one.** A walk blocked at step 3 of 6 has three steps nothing was reported about, and that
    # is the honest, expected, valuable outcome — the whole point of freezing the step list is
    # to be able to say it. So the counts are reported and nothing is raised. What the platform
    # does insist on is that the pass is CLOSED, which is the line below.
    if inp.phase == A11Y_JOURNEY_PHASE:
        from apps.a11y.journey import close_unfinished_journey, verify_journey_completeness

        try:
            counts = verify_journey_completeness(
                tenant_id=inp.tenant_id, run_id=inp.run_id)
        finally:
            # `finally` for the same reason as the judge's: the run whose accounting matters
            # most is the one that did not finish cleanly.
            close_unfinished_journey(tenant_id=inp.tenant_id, run_id=inp.run_id)
        return {"present": [f"{counts['reported']} steps reported"],
                "expected": [f"{counts['asked']} steps asked"]}

    # Auto-apply runs (00e document vision, Part B) don't register a phase-typed artifact — they
    # re-register the TARGET document as a new version carrying its own type, then publish without
    # a gate. So the bar here is "the run actually produced content", not a phase-type match:
    # require at least one non-empty artifact this run, so an empty/failed vision pass can never
    # auto-publish nothing over the adopted document.
    if getattr(inp, "auto_approve", False):
        with tenant_context(inp.tenant_id):
            hashes = list(
                Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
                # Excluding the phase blob the platform registers for every run: it always
                # exists and always holds SOMETHING (the agent's closing message), so counting
                # it made this check unfailable. A pass where the agent registered no document
                # at all — because its tools were missing, say — read as a success.
                .exclude(type=inp.phase)
                .values_list("content_hash", flat=True)
            )
        if not any(h and h != _EMPTY_BODY_HASH for h in hashes):
            raise WriteCompletenessError(
                f"run {inp.run_id} (auto-apply) registered no document — the vision pass "
                "produced nothing to apply, so nothing is published."
            )
        # Non-empty is not enough when there is no human gate: it must also not have LOST the
        # content it supersedes (Part B fix 1).
        _assert_no_content_loss(inp, object_store)
        return {"present": ["non-empty artifact"], "expected": ["non-empty artifact"]}

    # Expand any phase whose real work product is a richer artifact (e.g. security → the actual
    # security_review, not the generic "security" blob the platform always auto-registers). Other
    # phases are unchanged (map returns the type itself).
    required_types: list[str] = []
    for t in expected_types:
        required_types.extend(_PHASE_REQUIRED_ARTIFACTS.get(t, [t]))
    expected_types = list(dict.fromkeys(required_types))  # dedupe, preserve order

    with tenant_context(inp.tenant_id):
        rows = list(
            Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
            .values_list("type", "content_hash", "external_ref")
        )
    artifacts = [(t, h) for t, h, _ in rows]

    # The agent must have registered something ITSELF. The platform always files the engine's
    # final message as a phase-named artifact, so a run where the agent did nothing still
    # arrived here with exactly the artifact type this check looks for — non-empty, because the
    # text was real. That is how a run whose platform tools were unreachable produced a tidy
    # "ideation" document containing the agent's clarification QUESTIONS and opened a review
    # gate on it (2026-07-30). Presence of the platform's own row proves only that the engine
    # said something. Evidence for the bar: across 47 successful runs spanning 13 phases the
    # minimum artifact count was 2 — the sink's plus at least one the agent registered — never 1.
    agent_made = [t for t, _, ref in rows if (ref or {}).get("source") != PHASE_REPORT_SOURCE]
    if rows and not agent_made:
        raise WriteCompletenessError(_no_agent_artifact_reason(inp))
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
    from integrations.onboarding import CARRIER_SOURCES

    label = (inp.phase or "phase").replace("_", " ").strip().capitalize()
    with tenant_context(inp.tenant_id):
        wi = (
            WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id)
            .values("title", "external_ref").first() or {}
        )
    work_item_title = wi.get("title") or ""
    if not work_item_title:
        return label
    # A CARRIER work item is already named for what it is — the uploaded file for a vision run
    # ("09_Security.pdf"), or the step itself for an onboarding run ("Onboarding — project
    # assessment"). Prefixing the phase there either renames the user's own file into platform
    # vocabulary, or stutters: "Onboarding — Onboarding — project assessment".
    #
    # This used to key off `auto_approve`, which worked only by coincidence — every carrier run
    # happened to be headless. The moment the gap report became gated (team decision 2026-08-03)
    # the coincidence broke and the stutter appeared on the very artifact a reviewer opens at the
    # gate. Key off what actually matters: whether the work item is a carrier.
    if (wi.get("external_ref") or {}).get("source") in CARRIER_SOURCES:
        return work_item_title
    return f"{label} — {work_item_title}"


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
            # Stamp WHO made this: the platform, from the engine's final message — not the agent
            # via register_artifact. `verify_write_completeness` needs to tell them apart, because
            # this row is the very type it checks for, so the platform was manufacturing the
            # evidence its own check looked for (see PHASE_REPORT_SOURCE).
            external_ref={"source": PHASE_REPORT_SOURCE},
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
        if report.message or not body:
            # An "ok" report that carries a message means the engine did NOT end cleanly — it ran
            # out of turns, or returned no final text. The companion sends that message precisely
            # so the platform can say so; it used to be recorded only when the body was ALSO
            # empty, so a run truncated part-way through — with text on the floor and half its
            # work done — reported as an unqualified success (S5-25). A partial assessment that
            # looks complete is the dangerous shape: nothing downstream can tell it apart.
            tools.log_event(
                inp.tenant_id, "orchestrator", "phase.empty_result", "run", inp.run_id,
                {"phase": inp.phase, "body_empty": not body,
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
    happens only on an explicit human takeover (`abandon_run`) or a reported failure.

    **The reason text is load-bearing, and the old one was dangerous.** It said "companion
    offline", which is a DETECTION — a statement that the machine has been looked at and found
    gone. Nothing here looks at the machine. All that has happened is that a deadline expired,
    and on 31 August it expired at 7,200 seconds to the second on a companion that was
    demonstrably alive: a verdict landed seconds before it fired and another landed seconds
    after, and the run reported normally sixteen minutes later. The natural response to the word
    "offline" is to press *take over*, which is the one signal that turns this soft park into a
    terminal failure — it would have ended that run fifteen verdicts from the end, and the only
    thing that saved it was somebody deciding not to click. So the event now says what actually
    happened, names the budget it was measured against, and states the thing the code already
    does: the run is still waiting, and a late report still completes it."""
    budget = int(getattr(inp, "report_timeout_seconds", 0) or 0)
    with tenant_context(inp.tenant_id):
        WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id).update(
            takeover_flag=True)
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.STALLED)
        tools.log_event(inp.tenant_id, "orchestrator", "phase.takeover", "run", inp.run_id,
                        {"reason": (
                            f"no report arrived within this phase's budget of "
                            f"{budget // 60} minute(s). The machine has NOT been checked and may "
                            f"still be working — this run is still waiting, and it completes on "
                            f"its own if the report arrives. Take it over only to stop it."),
                         "report_timeout_seconds": budget,
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
    Parking always records the reason. Idempotent.

    The reason used to be stored exactly as raised — the only failure path that was never
    rewritten for the reader. It now reads like a paused build's (run-console fix, 2026-09-21)."""
    raw = reason
    said = describe_phase_failure(raw, phase=inp.phase, parked=True)
    reason = said.sentence
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.STALLED
        run.outputs = {**(run.outputs or {}), "error": reason,
                       "error_detail": _technical_detail(raw, reason),
                       "resume_from": resume_from, "resumable": True}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "run.parked", "run", inp.run_id,
                        {"reason": f"stopped: {said.cause}", "resume_from": resume_from,
                         "resumable": True})
    return {"status": "parked", "reason": reason, "resume_from": resume_from}


def pause_run_state(tenant_id: str, run_id: str, paused_by: str, resume_from: str,
                    kept: str = "") -> dict:
    """Record that a human stopped this run on purpose and means to come back to it. The park twin
    of `park_run_core`, with three deliberate differences.

    1. **Status PAUSED, not STALLED.** See the comment on `Run.Status.PAUSED`: STALLED is excluded
       from the re-trigger guard, so recording a pause as STALLED would have let the same phase be
       started again and put two runs on one work item and one branch.
    2. **No `error`.** Nothing went wrong, so nothing is written to the field the console reads
       for a failure reason — a paused run that printed an error would be telling the reader that
       their own decision was a fault.
    3. **The dispatch is held back.** `inputs.dispatch.status` becomes "paused", and the claim
       endpoint only offers `pending` or `claimed` work (`api/runner_views.py`), so a companion is
       never handed this run while it is paused. That is the only control we have over a
       pull-only companion, and it is what makes a pause pressed before the work is claimed
       complete.

    What this does NOT do is interrupt an agent already working: there is no channel to the
    companion, and a terminated run once kept writing for 49 minutes. The workflow picks the pause
    up at its next checkpoint; the dialog says so.

    Keyed on ids rather than on a workflow input dataclass because **the API calls this too**: the
    endpoint has to hold the dispatch back synchronously, while the workflow is still blocked
    waiting for a report. One definition of what "paused" means on a run, so the two cannot drift.

    Idempotent. `kept` is the build path's sentence about what survives.
    """
    from django.utils import timezone

    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        inputs = {**(run.inputs or {})}
        dispatch = dict(inputs.get("dispatch") or {})
        was_claimed = dispatch.get("status") == "claimed"
        if dispatch:
            # Remember what it was so Resume restores exactly that rather than a guess.
            dispatch["paused_from"] = dispatch.get("status")
            dispatch["status"] = "paused"
            inputs["dispatch"] = dispatch
        outputs = {**(run.outputs or {}),
                   "paused": {"by": paused_by, "at": timezone.now().isoformat(),
                              "was_claimed": was_claimed},
                   "resume_from": resume_from, "resumable": True}
        if kept:
            outputs["kept"] = kept
        run.status = Run.Status.PAUSED
        run.inputs = inputs
        run.outputs = outputs
        run.save(update_fields=["status", "inputs", "outputs", "updated_at"])
        tools.log_event(tenant_id, "orchestrator", "run.paused", "run", run_id,
                        {"paused_by": paused_by, "resume_from": resume_from,
                         "was_claimed": was_claimed, "resumable": True})
    return {"status": "paused", "resume_from": resume_from, "was_claimed": was_claimed}


def resume_run_state(tenant_id: str, run_id: str, extra_keys: tuple = ()) -> dict:
    """Un-park or un-pause a run: clear the markers, release a held-back dispatch, back to RUNNING.

    Shared by the error-park resume (Bugs S.No 157) and the deliberate pause, because the workflow
    waits on the same `resume_run` signal either way and the console offers one Resume. A resume
    that cleared only half the markers would leave a run that looks running and is never handed to
    anybody. Idempotent. Keyed on ids for the same reason as `pause_run_state`."""
    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        outputs = {**(run.outputs or {})}
        resume_from = outputs.get("resume_from", "")
        for key in ("error", "error_detail", "resume_from", "resumable", "paused") + tuple(
                extra_keys):
            outputs.pop(key, None)
        inputs = {**(run.inputs or {})}
        dispatch = dict(inputs.get("dispatch") or {})
        if dispatch.get("status") == "paused":
            # Put the dispatch back in the claim queue the pause held it out of, and drop the stale
            # claim stamp so the lease-reclaim branch does not mistake this for a dead companion.
            dispatch["status"] = "pending"
            dispatch.pop("paused_from", None)
            dispatch.pop("claimed_at", None)
            inputs["dispatch"] = dispatch
        run.status = Run.Status.RUNNING
        run.inputs = inputs
        run.outputs = outputs
        run.save(update_fields=["status", "inputs", "outputs", "updated_at"])
        tools.log_event(tenant_id, "orchestrator", "run.resumed", "run", run_id,
                        {"resume_from": resume_from})
    return {"status": "resumed", "resume_from": resume_from}


def pause_run_core(inp: AgentRunInput, paused_by: str, resume_from: str) -> dict:
    """Activity seam over `pause_run_state` (which the API also calls)."""
    return pause_run_state(inp.tenant_id, inp.run_id, paused_by, resume_from)


def resume_run_state_core(inp: AgentRunInput) -> dict:
    """Activity seam over `resume_run_state` (which the API also calls)."""
    return resume_run_state(inp.tenant_id, inp.run_id)


def _vision_source_document(inp: AgentRunInput):
    """The source document a vision run is transcribing, or None if this isn't a vision run."""
    if not getattr(inp, "auto_approve", False):
        return None
    with tenant_context(inp.tenant_id):
        wi = WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id).first()
    ref = (wi.external_ref or {}) if wi is not None else {}
    if ref.get("source") != "vision_carrier":
        return None
    return ref.get("source_document_id")


def link_vision_artifact_core(inp: AgentRunInput) -> dict:
    """Point the source document at the artifact its vision run just registered.

    Since an upload no longer registers anything, the vision run is what creates the document's
    artifact — and the document has to end up pointing at it, or the UI and the gap report would
    both see an adopted document with nothing behind it. Only ever links, never creates.
    """
    source_document_id = _vision_source_document(inp)
    if not source_document_id:
        return {"linked": None}
    from apps.integrations.models import SourceDocument

    with tenant_context(inp.tenant_id):
        src = SourceDocument.objects.filter(
            id=source_document_id, tenant_id=inp.tenant_id).first()
        if src is None or list(src.extracted_artifact_ids or []):
            return {"linked": None}          # gone, or already linked — leave it alone
        registered = list(
            Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id)
            .order_by("created_at").values_list("id", flat=True)
        )
        if not registered:
            return {"linked": None}
        src.extracted_artifact_ids = [str(registered[0])]
        src.save(update_fields=["extracted_artifact_ids", "updated_at"])
    return {"linked": str(registered[0])}


def recover_unread_document_core(inp: AgentRunInput) -> dict:
    """A vision run failed — make sure its document still ends up with its extracted text.

    The document was adopted the moment the user clicked; the vision pass was only meant to make
    its pages legible. Since the artifact is now created by that run, a failure would otherwise
    leave the document adopted with nothing in the registry — invisible to the gap report and to
    the user. Registering the plain extraction is the honest floor: less than the user hoped for,
    never nothing. Idempotent, so a run that failed after registering its own artifact is left be.
    """
    source_document_id = _vision_source_document(inp)
    if not source_document_id:
        return {"recovered": None}
    from integrations.onboarding import register_extracted_artifact

    # Drop whatever the failed run registered but never got to publish — a transcription the
    # guard rejected, or a half-written one. It is not the document's content and must not sit in
    # the registry looking like a second copy of it; the run's error explains what went wrong.
    # The run's own phase artifact is kept: it holds the agent's closing message, which is what
    # the run console shows and the only account of WHY the pass failed.
    with tenant_context(inp.tenant_id):
        Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id,
        ).exclude(status=Artifact.Status.PUBLISHED).exclude(type=inp.phase).delete()
    try:
        artifact_id = register_extracted_artifact(
            tenant_id=inp.tenant_id, source_document_id=source_document_id)
    except Exception as exc:  # noqa: BLE001 — recovery must never mask the original failure
        tools.log_event(inp.tenant_id, "orchestrator", "document_vision.recovery_failed",
                        "source_document", source_document_id, {"error": str(exc)[:300]})
        return {"recovered": None}
    tools.log_event(inp.tenant_id, "orchestrator", "document_vision.recovered",
                    "source_document", source_document_id, {"artifact_id": artifact_id})
    return {"recovered": artifact_id}


def fail_run_core(inp: AgentRunInput, reason: str) -> dict:
    """A companion reported a failed phase → flag the run failed (the body, if any, is on the
    report). Mirrors the execute_agent failure path."""
    # Plain-language reason for the run console (Bugs S.No 146, planning path): the companion
    # reports the raw engine error (e.g. 'Command failed with exit code 1'); classify it here so
    # a security/planning failure reads like a build failure does, not as a raw exit code.
    raw = reason
    said = describe_phase_failure(raw, phase=inp.phase)
    reason = said.sentence
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.FAILED
        run.ended_at = _now()
        run.outputs = {**(run.outputs or {}), "error": reason,
                       "error_detail": _technical_detail(raw, reason)}
        run.save(update_fields=["status", "outputs", "ended_at", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "run.failed", "run", inp.run_id,
                        {"error": said.cause})
    recover_unread_document_core(inp)   # a failed vision pass must not leave a document empty
    # …and a failed journey pass must not leave a walk saying it is still walking (G6a). This is
    # the path a crashed agent takes, and it never reaches the write-completeness check above,
    # so the closure has to be on both. A no-op for every phase that has no journey.
    from apps.a11y.journey import close_unfinished_journey

    close_unfinished_journey(tenant_id=inp.tenant_id, run_id=inp.run_id, reason=reason)
    # …and a failed JUDGING pass must not leave an audit saying it is still checking. Same
    # reasoning as the line above and the same blind spot: this path returns before
    # `verify_writes`, which is where the judge's accounting lives — file every element the run
    # never answered as `uncertain`, publish the merged report, complete the audit. Without
    # this, an engine that lost its session mid-judgment left the audit reading "Checking what
    # was found" for ever and its unanswered elements recorded nowhere. A no-op for every phase
    # that judged nothing.
    from apps.a11y.aipass import close_unfinished_ai_pass

    close_unfinished_ai_pass(tenant_id=inp.tenant_id, run_id=inp.run_id)
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


@activity.defn(name="retrigger_revision")
def retrigger_revision_activity(inp: AgentRunInput, direction: str) -> dict:
    return _boundary(retrigger_revision_core, inp, direction)


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


@activity.defn(name="pause_run")
def pause_run_activity(inp: AgentRunInput, paused_by: str, resume_from: str) -> dict:
    return _boundary(pause_run_core, inp, paused_by, resume_from)


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
    retrigger_revision_activity,
    verify_writes_activity,
    dispatch_phase_activity,
    register_phase_result_activity,
    mark_phase_takeover_activity,
    fail_run_activity,
    park_run_activity,
    pause_run_activity,
    resume_run_state_activity,
]
