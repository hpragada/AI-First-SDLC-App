"""Local-companion runner API (Phase-2 §3).

Two surfaces:
1. **Enrollment** (`/api/runners/…`, tenant-scoped via X-Tenant-ID like every P0 route):
   a developer enrolls a companion and gets a one-time token; can list/revoke.
2. **Remote Platform-State serving** (`/api/runner/state/<tool>/`, Runner-token auth): the
   build agent on the dev machine calls the platform-state tools over HTTP — **no DB on the
   dev machine**. The tenant is taken from the authenticated enrollment (server-side), never
   from the request body, so RLS scoping stays on the platform (#6). Only the build-phase
   tool subset is exposed (per-phase allowlist, PG12).
"""
from __future__ import annotations

from datetime import timedelta

from mcp_platform_state import tools
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import AGENT_CATALOG
from apps.runs.enrollment import (
    authenticate_runner,
    enroll_runner,
    last_disconnect,
    list_developer_enrollments,
    revoke_runner,
)
from apps.runs.models import Run, RunnerEnrollment
from apps.tenancy.auth import IsAuthenticatedMember, current_user
from apps.tenancy.context import tenant_context
from orchestration.build_report import BuildReportError, report_build

# A work claim is a *lease*. If the companion that claimed a run dies before reporting (crash,
# manual stop, laptop sleep), the run would otherwise stay "claimed" forever — status stuck at
# "running", no artifacts, no gate (Bugs.xlsx row 61 / RC-3). A later poll re-claims a run whose
# claim went stale (claimed_at older than this with no report).
#
# The lease detects a DEAD companion, so it must key off *liveness*, not task duration. It used
# to key off "time since the claim was stamped", which wrongly fired on a LIVE companion running
# a long phase (a genuine 19-min code review > this 15-min lease got re-claimed mid-flight →
# duplicate artifacts + a failed re-review → the merge gate opened blind — Bugs S.No 111, the
# S.No 110 follow-up). Fix: the heartbeat renews `claimed_at` while the companion is alive
# (_renew_claims_for), so a heartbeating companion's claim never goes stale no matter how long the
# phase runs, while a truly dead companion still gets re-claimed ~15 min after its LAST heartbeat.
CLAIM_LEASE = timedelta(minutes=15)

# The heartbeat renews the lease on *liveness*, which alone lets a wedged-but-heartbeating worker
# (agent hung, but the heartbeat thread still ticking) renew its claim forever — the run sits
# claimed, masked from recovery, until only the workflow's 2h report-timeout takeover (S.No 89)
# frees it (Bugs S.No 134). MAX_CLAIM_AGE caps how long a single continuous claim may be renewed:
# past it, the heartbeat STOPS renewing, so the lease ages out (CLAIM_LEASE) and the run is
# recoverable well before the 2h backstop. Set safely ABOVE the longest legitimate build so a
# healthy long build is never capped (which would reintroduce the S.No 111 mid-flight re-claim);
# the team confirmed builds stay well under 60 min.
MAX_CLAIM_AGE = timedelta(minutes=60)

# Build-phase platform-state tool allowlist (no detect_drift, no planning-only tools).
_BUILD_STATE_TOOLS = {
    "get_context": tools.get_context,
    "get_artifact": tools.get_artifact,
    "list_artifacts": tools.list_artifacts,
    "register_artifact": tools.register_artifact,
    "stage_artifact_body": tools.stage_artifact_body,
    "get_artifact_body": tools.get_artifact_body,
    # Vision pipe (onboarding_fidelity_plan Part B): read a document's stored page images so a
    # multimodal onboarding/vision agent can SEE what text extraction can't carry.
    "get_page_images": tools.get_page_images,
    # Reads an uploaded document's extracted text before any artifact exists for it — the vision
    # agent's counterpart to get_artifact_body when its work item names a source document.
    "get_source_extraction": tools.get_source_extraction,
    # Code review only (see `runner.REVIEW_ONLY_STATE_TOOLS`): read one file of the PR under
    # review, so a file too long to inline whole can still be reviewed whole. Reachable on this
    # route because the route is the transport; what gates an AGENT is its allowlist.
    "get_pr_file": tools.get_pr_file,
    "update_artifact": tools.update_artifact,
    "add_trace_edge": tools.add_trace_edge,
    "log_event": tools.log_event,
    "list_work_items": tools.list_work_items,
    "create_work_item": tools.create_work_item,
    "transition_work_item": tools.transition_work_item,
    # Agent-driven onboarding: 00_onboarding writes its gap report through the shared, shape-safe
    # writer (never a raw external_ref).
    "submit_gap_report": tools.submit_gap_report,
    # Accessibility judging (09c_a11y_judge, QA-02a): read the dispatched elements, read the
    # exact WCAG wording to judge them against, and report one validated verdict per element.
    "get_a11y_batch": tools.get_a11y_batch,
    "get_wcag_grounding": tools.get_wcag_grounding,
    "record_a11y_finding": tools.record_a11y_finding,
    # QA-11b: the judge's eyes — the captured crop of each element it must judge.
    "get_a11y_screenshots": tools.get_a11y_screenshots,
    # QA-11b: the COMPANION posts what the suite captured from the live application. Reachable
    # on this route because that is the channel the companion already authenticates on, but
    # deliberately NOT in the companion's engine tool grant (`runner.BUILD_STATE_TOOLS`) — an
    # agent able to write candidate bundles could describe a page instead of one having been
    # captured, and the whole point of a capture is that it is machine truth.
    "ingest_a11y_candidates": tools.ingest_a11y_candidates,
    # QA-17: the same channel for a baseline audit of an app the platform never built. The
    # companion opens the audit, visits the registered routes, posts each screen and closes it;
    # the platform decides what to visit and accounts for what came back. Companion-only for
    # the reason above — a capture is machine truth or it is nothing.
    "start_a11y_audit": tools.start_a11y_audit,
    # Read back the manifest for an audit the companion was handed, so a machine that
    # reconnects mid-audit never opens a second one to find out what to visit (task 8a).
    "get_a11y_audit": tools.get_a11y_audit,
    "ingest_a11y_audit_screen": tools.ingest_a11y_audit_screen,
    "finish_a11y_audit": tools.finish_a11y_audit,
    # Accessibility journeys (09d_a11y_journey, QA-20): read the frozen steps, report what
    # became of each one, and record up to eight verdicts per step. Unlike the capture tools
    # above these ARE an agent's grant — a journey result is a judgement about what happened
    # while operating the app, so it is the agent's to make, exactly like 09c's verdicts.
    "get_a11y_journey": tools.get_a11y_journey,
    "record_a11y_journey_step": tools.record_a11y_journey_step,
    "record_a11y_journey_finding": tools.record_a11y_journey_finding,
    "finish_a11y_journey": tools.finish_a11y_journey,
}

# The states a build agent may set on a WorkItem. An ALLOWLIST, not a blocklist (Bugs S.No 87).
#
# `done` was blocked first, because letting the engine set it bypassed the merge gate and left a
# WorkItem done, with no workitem.transitioned event, while its run was still in review — the
# "state=done while awaiting_gate" mislabel (non-negotiables #2/#5). But that left every OTHER
# state open: an agent could still promote an item to `accepted` (which is the reconciler's word
# for "this is now in the tracker", and would be a lie), push it back to `proposed` (erasing the
# fact that work had started), or park it in `blocked`/`in_review` — states no control-plane code
# writes, so nothing would ever move it out again.
#
# Exactly one transition is an agent's to make, and it is written down: 07_implementation moves
# the item to `in_progress` when it starts work (agents/07_implementation/agent.md, Step 1). Every
# other state belongs to the platform. Inverting the rule also means a state added later is
# refused by default rather than quietly permitted until somebody remembers to add it to a list —
# which is the failure this fix exists to end, not repeat.
#
# Enforced at the single agent/companion entry point. The orchestrator calls
# tools.transition_work_item in-process (not through this view), so the saga's own transitions —
# including the gated `done` — are unaffected.
_AGENT_ALLOWED_TRANSITIONS = {"in_progress"}


def _tenant_id(request) -> str:
    tid = getattr(request, "tenant_id", None)
    if not tid:
        from rest_framework.exceptions import ParseError

        raise ParseError("X-Tenant-ID header is required.")
    return str(tid)


def _renew_claims_for(runner) -> int:
    """Refresh `claimed_at=now` on every in-flight run this companion currently holds, so its
    claim lease (CLAIM_LEASE) tracks the companion's liveness, not the phase duration. Called on
    each heartbeat: a live companion keeps its claim fresh no matter how long the phase runs, so
    a long-but-healthy review is never re-claimed out from under it (Bugs S.No 111). A dead
    companion stops heartbeating, so its claim ages out and the run is recovered as before.

    Only `claimed`, still-in-flight (PENDING/RUNNING) runs are touched — a run that already
    reported or reached a gate is left alone, so this can never revive finished work."""
    from django.db import transaction
    from django.utils import timezone

    from apps.a11y.baseline import ABANDONABLE_STATUSES
    from apps.a11y.models import A11yBaselineAudit

    now_dt = timezone.now()
    now = now_dt.isoformat()
    # Bugs S.No 134: a claim first held before this cutoff has been renewed for too long without
    # finishing — stop renewing it so the lease can age out (a wedged worker can't renew forever).
    max_age_before = (now_dt - MAX_CLAIM_AGE).isoformat()
    renewed = 0
    with tenant_context(str(runner.tenant_id)), transaction.atomic():
        runs = (
            Run.objects.select_for_update(skip_locked=True)
            .filter(tenant_id=runner.tenant_id,
                    inputs__dispatch__enrollment_id=str(runner.id),
                    inputs__dispatch__status="claimed",
                    status__in=(Run.Status.PENDING, Run.Status.RUNNING))
        )
        for run in runs:
            inputs = dict(run.inputs or {})
            dispatch = dict(inputs.get("dispatch") or {})
            if dispatch.get("status") != "claimed":
                continue
            first_claimed_at = dispatch.get("first_claimed_at")
            if first_claimed_at and first_claimed_at < max_age_before:
                # Held (and renewed) past MAX_CLAIM_AGE without reporting — likely wedged. Stop
                # renewing; the lease now ages out so the run is recoverable (re-claim / S.No 89
                # takeover) instead of masked indefinitely by mere process liveness.
                continue
            dispatch["claimed_at"] = now
            inputs["dispatch"] = dispatch
            run.inputs = inputs
            run.save(update_fields=["inputs", "updated_at"])
            renewed += 1

        # The same lease, for the accessibility audits this companion is holding. Only the ones
        # it is actively CAPTURING: a `claimed` audit has captured nothing yet and its stale
        # claim is already handed to the next machine that asks, which beats renewing it.
        #
        # Until this,
        # NOTHING renewed an audit's claim: `claimed_at` was stamped once at claim and never
        # touched, so an audit's liveness was not actually being tracked at all. That was
        # survivable only because a claim goes stale unnoticed; it stops being survivable the
        # moment something acts on staleness, which `abandon_stale_audits` now does.
        #
        # Capped off `created_at` rather than a `first_claimed_at` column, which is what runs
        # use: an audit is claimed within a second of being created, so its own age is the same
        # measurement — and reaching for a column would mean a migration for a number already
        # in the row.
        audits = (
            A11yBaselineAudit.objects.select_for_update(skip_locked=True)
            .filter(tenant_id=runner.tenant_id, enrollment_id=runner.id,
                    status__in=ABANDONABLE_STATUSES,
                    created_at__gte=now_dt - MAX_CLAIM_AGE)
        )
        for audit in audits:
            audit.claimed_at = now_dt
            audit.save(update_fields=["claimed_at", "updated_at"])
            renewed += 1
    return renewed


def _serialize(e: RunnerEnrollment) -> dict:
    return {
        "id": str(e.id), "project_id": str(e.project_id), "label": e.label,
        "repos": e.repos, "status": e.status,
        "developer_id": str(e.developer_id) if e.developer_id else None,
        "last_seen": e.last_seen.isoformat() if e.last_seen else None,
    }


class RunnerEnrollmentView(APIView):
    """GET the caller's companion enrollments (P4.7-T11, backs S-05/S-06) / POST enroll a
    local-companion runner for this tenant."""

    def get_permissions(self):
        # GET only, and that is a DELIBERATE hold rather than an oversight.
        #
        # S.No 214 closed eight other anonymous writes, and the enrollment POST is genuinely the
        # ninth: it mints a credential that lets a machine claim and run this tenant's phases,
        # and enrollment tokens never expire. Gating it, however, breaks the documented CLI
        # onboarding path - `python -m runner.companion enroll --api-url ... --tenant T
        # --project P` (runner/README.md, Quick start step 1) sends only an X-Tenant-ID header
        # and a `developer_id` body param, with no session to present. There is no user-token
        # auth for it to use instead; giving it one is new capability, not a bug fix.
        #
        # So this is recorded against S.No 35, which already owns the redesign of the whole
        # Connect Machine flow, alongside the two findings filed there earlier: `revoke_runner`
        # revokes exactly one enrollment row and leaves that machine's other tokens ACTIVE, and
        # the token travels on the command line where any process listing reveals it. Whatever
        # replaces the token flow has to answer "how does a headless machine authenticate" once,
        # for all three - and closing this half first would break onboarding while solving none
        # of it.
        if self.request.method == "GET":
            return [IsAuthenticatedMember()]
        return super().get_permissions()

    def get(self, request):
        tenant_id = _tenant_id(request)
        user = current_user(request)
        return Response(
            list_developer_enrollments(tenant_id=tenant_id, developer_id=str(user.id))
        )

    def post(self, request):
        tenant_id = _tenant_id(request)
        project_id = request.data.get("project_id")
        if not project_id:
            return Response({"project_id": "required"}, status=status.HTTP_400_BAD_REQUEST)
        # Validate the project is in this tenant (scoped read).
        if not Project.objects.filter(id=project_id, tenant_id=tenant_id).exists():
            return Response({"project_id": "not found in tenant"},
                            status=status.HTTP_404_NOT_FOUND)
        # NOTE: no project-membership check here either, for the reason in `get_permissions`
        # above - the CLI path has no session to check a membership against. It belongs with the
        # S.No 35 redesign, not ahead of it.
        # The authenticated session user owns the enrollment; `developer_id` in the body is
        # only the pre-auth/runner/test fallback (mirrors `resolve_actor`, P4.7-T5).
        user = current_user(request)
        developer_id = str(user.id) if user is not None else request.data.get("developer_id")
        enrollment, token = enroll_runner(
            tenant_id=tenant_id, project_id=project_id,
            developer_id=developer_id,
            label=request.data.get("label", ""), repos=request.data.get("repos") or [],
        )
        body = _serialize(enrollment)
        body["token"] = token  # shown once — the companion stores it; only its hash persists
        return Response(body, status=status.HTTP_201_CREATED)


class RunnerRevokeView(APIView):
    """POST /api/runners/{id}/revoke/ — stop a companion's token from authenticating."""

    def get_permissions(self):
        # S.No 214: an ungated write sitting next to the one above. Revoking somebody else's
        # companion stops their phases from running, so it needs a session like everything else.
        # NOTE this changes WHO may call it, not what it does — the fact that it revokes exactly
        # one enrollment row and leaves the rest of that machine's tokens ACTIVE is recorded
        # against S.No 35, which owns the Connect Machine redesign, and is deliberately not
        # touched here.
        return [IsAuthenticatedMember()]

    def post(self, request, pk):
        tenant_id = _tenant_id(request)
        if not revoke_runner(tenant_id=tenant_id, enrollment_id=pk):
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"id": str(pk), "status": "revoked"})


class RunnerLastDisconnectView(APIView):
    """GET /api/runners/last-disconnect/?project_id= — when the caller's machine was last
    disconnected from that project, so Connect Machine can say so on any later visit."""

    def get_permissions(self):
        return [IsAuthenticatedMember()]

    def get(self, request):
        project_id = request.query_params.get("project_id")
        if not project_id:
            return Response({"project_id": "required"}, status=status.HTTP_400_BAD_REQUEST)
        user = current_user(request)
        return Response({"disconnected_at": last_disconnect(
            tenant_id=_tenant_id(request), developer_id=str(user.id), project_id=project_id)})


class RunnerStateView(APIView):
    """POST /api/runner/state/<tool>/ — a build agent's platform-state call, Runner-token
    authenticated. The tenant is the enrollment's (server-side), not from the body."""

    authentication_classes: list = []   # Runner-token auth is handled explicitly below
    permission_classes: list = []

    def post(self, request, tool):
        runner = self._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        fn = _BUILD_STATE_TOOLS.get(tool)
        if fn is None:
            return Response({"detail": f"tool '{tool}' is not in the build allowlist"},
                            status=status.HTTP_403_FORBIDDEN)
        args = request.data if isinstance(request.data, dict) else {}
        # Guard: an agent may only move a WorkItem to `in_progress`. Every other state is the
        # control plane's to set — `done` after an approved merge gate, `accepted` by the
        # reconciler when the item really reaches the tracker (#2/#5).
        if (tool == "transition_work_item"
                and args.get("to_state") not in _AGENT_ALLOWED_TRANSITIONS):
            allowed = ", ".join(sorted(_AGENT_ALLOWED_TRANSITIONS))
            return Response(
                {"detail": f"transition to '{args.get('to_state')}' is not permitted from a build "
                           f"agent — the only state you may set is: {allowed}. Everything else, "
                           "including marking the item done, is the platform's to decide (done "
                           "happens only after the merge gate is approved)."},
                status=status.HTTP_403_FORBIDDEN)
        # Guard: a pointer an agent hands over must lead somewhere (S.No 314). THIS is the
        # boundary a companion's agent actually comes through — `/api/runner/state/…` — not the
        # stdio MCP server, which only serves the in-worker path. The 2026-10-05 failure came in
        # here: a feasibility report registered against a key the agent had composed by hand,
        # one character off, with the body sitting safely at the real one. The row looked
        # flawless on every screen and the phase wedged at publish time.
        #
        # Checked at registration because it is the only moment the mistake is cheap: the agent
        # is still running and the ValueError below reaches it as a readable 400 it can act on.
        if tool == "register_artifact" and args.get("s3_key"):
            from mcp_platform_state.tools import _assert_body_exists

            try:
                _assert_body_exists(args["s3_key"])
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = fn(str(runner.tenant_id), **args)   # tenant bound server-side
        except TypeError as exc:
            return Response({"detail": f"bad arguments: {exc}"},
                            status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            # A rejected VALUE is a caller error, not a platform fault (B2). The state tools
            # raise ValueError for exactly that — an unknown `rel`, `status` or `sor`. Only
            # TypeError was mapped, so every one of those surfaced to the agent as a 500.
            # An agent reading "500" concludes the platform is broken and retries the same call;
            # reading "400: invalid rel … valid values: …" it corrects itself on the first try.
            # Live in run 98ab9a8c that distinction cost nine wasted round trips.
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"result": result})

    @staticmethod
    def _resolve_runner(request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Runner "):
            return None
        token = auth[len("Runner "):].strip()
        return authenticate_runner(tenant_id=request.headers.get("X-Tenant-ID"), token=token)


class RunnerBuildFetchView(APIView):
    """GET /api/runner/builds/<run_id>/ — the companion fetches its dispatched BuildTask
    (manifest + agent body). The companion fills in its own runner token before running."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, run_id):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        with tenant_context(str(runner.tenant_id)):
            run = Run.objects.filter(id=run_id, tenant_id=runner.tenant_id).first()
        if run is None:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = (run.inputs or {}).get("build_task")
        if not payload:
            return Response({"detail": "no build task dispatched"},
                            status=status.HTTP_409_CONFLICT)
        return Response(payload)


class RunnerClarificationCreateView(APIView):
    """POST /api/runner/clarifications/ — an agent (via its `ask_human` tool) opens a
    clarification for its run. Runner-token authenticated; tenant bound from the enrollment
    (never the body). Idempotent by question signature, so a re-ask reuses the same one."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        from apps.clarifications.services import create_clarification

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        data = request.data if isinstance(request.data, dict) else {}
        run_id = data.get("run_id")
        if not run_id:
            return Response({"detail": "run_id is required"},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            result = create_clarification(
                tenant_id=str(runner.tenant_id), run_id=str(run_id),
                questions=data.get("questions") or [], context=data.get("context", ""),
                phase=data.get("phase", ""), signature=data.get("signature", ""),
            )
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_201_CREATED)


class RunnerClarificationPollView(APIView):
    """GET /api/runner/clarifications/<id>/ — the companion polls its clarification until the
    human answers it in the web app. While polling, the agent is idle on the open tool call,
    so no engine cost accrues during the wait."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, clarification_id):
        from apps.clarifications.models import Clarification
        from apps.clarifications.services import get_clarification

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        try:
            result = get_clarification(
                tenant_id=str(runner.tenant_id), clarification_id=str(clarification_id))
        except Clarification.DoesNotExist:
            return Response({"detail": "clarification not found"},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(result)


#: The security phase's LABEL, not its agent key — a dispatch payload carries labels
#: (`AgentRunInput.phase` is set from `spec.phase_label`). Read from the catalog rather than
#: written out, so renaming the phase there cannot silently switch this branch off.
SECURITY_PHASE = next(
    (a.phase_label for a in AGENT_CATALOG if a.key == "10_security"), "security")


def _phase_extras(run, payload: dict):
    """The dispatched task, plus what its phase needs and the generic dispatch could not carry.

    Returns the payload, or **`None` meaning "not ready — do not hand this out yet"**.

    **Why this exists rather than a wider dispatch payload.** `dispatch_phase_core` builds one
    payload shape for every phase in the platform, from `AgentRunInput`. Growing either of them
    an accessibility-shaped field would put one feature's vocabulary into the seam every phase
    crosses — the same objection `aipass._remember_source_run` records for the judging pass, and
    it applies with more force to a Temporal input, where a signature change is a versioning
    problem as well as a design one. So the phase-specific fact is read here, once, for the one
    phase that needs it, and every other phase's payload is byte-identical to before.

    **The keyboard journey (G6a) needs the address of the application it is walking**, and it
    needs it before the agent starts, not after: the companion passes it to the browser as the
    only origin that may be opened, which happens while the MCP servers are being wired.

    **`None` closes a real race.** `start_journey_check` triggers the run and writes the journey
    row immediately afterwards — it cannot write it first, because the row is keyed by the run id
    the trigger returns. The window is tiny (the run only becomes claimable once a Temporal
    activity has composed the manifest and dispatched it, which is far slower than one INSERT),
    but "tiny" is not "closed": a companion that claimed inside it would start an agent whose
    first tool call fails with "no accessibility journey is attached to this run". Deferring for
    one poll turns a rare, confusing failure into about a second of waiting.

    **The security phase (Bugs S.No 185) needs its package registries reachable**, and likewise
    before the agent starts: the companion builds the egress allowlist once, at task setup, and
    a scanner that cannot reach PyPI cannot be installed at all. `extra_allowed_hosts` has been a
    field on the companion's task and honoured by its guardrails all along — nothing on the
    server ever populated it, which is exactly the "does not exist yet" the guardrails comment
    names. A project that declares no registries gets a payload identical to today's.
    """
    from apps.a11y.journey import JOURNEY_PHASE

    if payload.get("phase") == SECURITY_PHASE:
        profile = ProjectProfile.objects.filter(
            tenant_id=run.tenant_id, project_id=run.work_item.project_id).only("scan").first()
        registries = [
            h.strip() for h in ((profile.scan if profile else {}) or {}).get("registries", [])
            if isinstance(h, str) and h.strip()
        ]
        if not registries:
            return payload
        existing = list(payload.get("extra_allowed_hosts") or [])
        merged = existing + [h for h in registries if h not in existing]
        return {**payload, "extra_allowed_hosts": merged}

    if payload.get("phase") != JOURNEY_PHASE:
        return payload

    from apps.a11y.models import A11yJourneyRun

    row = (A11yJourneyRun.objects
           .filter(tenant_id=run.tenant_id, run_id=run.id)
           .only("base_url").first())
    if row is None:
        return None
    return {**payload, "app_base_url": row.base_url}


class RunnerWorkClaimView(APIView):
    """GET /api/runner/work/ — the companion daemon claims the next phase/build task dispatched
    to its enrollment. Atomically flips the run's dispatch to `claimed` (skip-locked so two
    daemons never grab the same run), returns `{kind, run_id, payload}`, or 204 when idle."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        from django.db import transaction
        from django.db.models import Q
        from django.utils import timezone

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        now = timezone.now()
        stale_before = (now - CLAIM_LEASE).isoformat()   # ISO8601 UTC sorts chronologically
        with tenant_context(tid), transaction.atomic():
            # A poll may claim a fresh `pending` dispatch OR re-claim one that a dead companion
            # left `claimed` past its lease (RC-3). Staleness is checked in Python on the ISO
            # claimed_at so we lean only on the proven exact JSON-key lookups in the query.
            #
            # Two kinds of dispatch are claimable by this runner:
            #   1. OWNED — dispatch.enrollment_id == this runner's id (the normal routed case:
            #      trigger resolved the triggering user's companion and pinned it).
            #   2. BROADCAST — dispatch.enrollment_id is null. A trigger issued while no companion
            #      was enrolled/available (e.g. the S.No 161 remediation auto-retry, which fires
            #      with no triggering user, or a user who triggers before starting their
            #      companion) stamps a null enrollment. Nothing matched enrollment_id, so the run
            #      sat RUNNING+unclaimable forever and blocked new triggers for the WorkItem (S.No
            #      169-adjacent build-dispatch binding bug). Let ANY active companion for the same
            #      tenant+project claim it and bind itself on claim, so the run self-heals the
            #      moment a companion is available. `=None` matches the JSON-null we store; the
            #      __isnull covers a dispatch that omitted the key entirely. Broadcast is scoped to
            #      the runner's project (via work_item) so a companion never steals another
            #      project's work; skip_locked + bind-on-claim keep it claimed exactly once.
            owned = Q(inputs__dispatch__enrollment_id=str(runner.id))
            broadcast = (
                Q(work_item__project_id=runner.project_id)
                & (Q(inputs__dispatch__enrollment_id=None)
                   | Q(inputs__dispatch__enrollment_id__isnull=True))
            )
            candidates = (
                Run.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tid)
                .filter(owned | broadcast)
                .filter(Q(inputs__dispatch__status="pending")
                        | Q(inputs__dispatch__status="claimed"))
                .order_by("created_at")
            )
            run = None
            reclaimed = False
            for cand in candidates:
                dispatch = (cand.inputs or {}).get("dispatch") or {}
                st = dispatch.get("status")
                if st == "pending":
                    run = cand
                    break
                claimed_at = dispatch.get("claimed_at")
                # Re-claim ONLY a still-in-flight run whose companion went silent past the
                # lease. Never re-run one that already reached a gate or a terminal state — a
                # long phase that just reported (dispatch flips to "reported" synchronously in
                # report_phase) or was gated/approved must not be re-run (the duplicate-v2
                # regression combined a stale lease with an already-finished phase).
                if (st == "claimed" and claimed_at and claimed_at < stale_before
                        and cand.status in (Run.Status.PENDING, Run.Status.RUNNING)):
                    run, reclaimed = cand, True
                    break
            if run is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            inputs = dict(run.inputs or {})
            dispatch = dict(inputs.get("dispatch") or {})
            kind = dispatch.get("kind", "plan")
            key = {"plan": "phase_task", "review": "review_task",
                   "build": "build_task"}.get(kind, "phase_task")
            payload = _phase_extras(run, inputs.get(key) or {})
            # Resolved BEFORE the claim is written, so a task that is not ready to run is not
            # marked claimed. See `_phase_extras`: today the only "not ready" case is a journey
            # dispatched microseconds before its row was written, and one more poll — about a
            # second — is all it needs. Nothing has been saved yet, so the run simply stays
            # pending and the next poll picks it up.
            if payload is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            # Bind a BROADCAST (null-enrollment) dispatch to the claiming runner so it is now
            # OWNED — subsequent polls, heartbeat claim-renewal and lease-reclaim all key off
            # enrollment_id, and only this companion should carry it from here.
            if dispatch.get("enrollment_id") in (None, ""):
                dispatch["enrollment_id"] = str(runner.id)
            dispatch["status"] = "claimed"
            dispatch["claimed_at"] = now.isoformat()
            # Bugs S.No 134: mark when THIS continuous claim started (reset on every fresh claim /
            # re-claim, never touched by heartbeat renewal) so the renewal cap can bound a claim
            # that is renewed forever without progressing.
            dispatch["first_claimed_at"] = now.isoformat()
            dispatch["claim_count"] = int(dispatch.get("claim_count") or 0) + 1
            inputs["dispatch"] = dispatch
            run.inputs = inputs
            run.save(update_fields=["inputs", "updated_at"])
            if reclaimed:
                tools.log_event(tid, "companion", "phase.reclaimed", "run", str(run.id),
                                {"claim_count": dispatch["claim_count"]})
            return Response({"kind": kind, "run_id": str(run.id), "payload": payload})


class RunnerHeartbeatView(APIView):
    """POST /api/runner/heartbeat/ — the companion pings this on a fixed cadence so the platform
    keeps the enrollment "online" even while a phase is running. The serve loop runs each phase
    synchronously (it is busy in run_task and not polling /work/), so without an independent
    heartbeat `last_seen` goes stale mid-phase and the UI falsely flips to "offline / daemon
    stopped" and disables triggers (Bugs.xlsx row 61 / RC-2). Resolving the runner refreshes
    last_seen; the body is otherwise trivial."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        from django.utils import timezone

        from apps.a11y.baseline import abandon_stale_audits

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        renewed = _renew_claims_for(runner)
        # Renew first, THEN sweep — otherwise a companion could close the very audit it is
        # holding. An accessibility audit is captured by a machine this server cannot see, so
        # the machine going away (closed, restarted, laptop shut) left the audit in `capturing`
        # for ever: the claim lease only ever offered `pending` and stale `claimed` back, so
        # nothing recovered it, nothing failed it, and the screen went on saying "Visiting
        # pages" about a machine that no longer existed. Swept here because a rebooted companion
        # says hello within seconds of coming back, and because a heartbeat is already a write.
        closed = abandon_stale_audits(
            tenant_id=str(runner.tenant_id), project_id=str(runner.project_id),
            stale_before=timezone.now() - CLAIM_LEASE)
        return Response({"ok": True, "claims_renewed": renewed, "audits_closed": len(closed),
                         "last_seen": runner.last_seen.isoformat() if runner.last_seen else None})


class RunnerPhaseFetchView(APIView):
    """GET /api/runner/phases/<run_id>/ — the companion fetches its dispatched phase task
    (manifest + agent body), mirroring the build fetch."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, run_id):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        with tenant_context(str(runner.tenant_id)):
            run = Run.objects.filter(id=run_id, tenant_id=runner.tenant_id).first()
        if run is None:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        payload = (run.inputs or {}).get("phase_task")
        if not payload:
            return Response({"detail": "no phase task dispatched"},
                            status=status.HTTP_409_CONFLICT)
        with tenant_context(str(runner.tenant_id)):
            payload = _phase_extras(run, payload)
        # The re-fetch path, so the same phase extras and the same not-ready answer as the claim
        # (see `_phase_extras`). 409 rather than a payload missing its address: this endpoint is
        # asked for one named run, so "come back in a moment" is the honest answer and the
        # companion's existing retry already handles it.
        if payload is None:
            return Response({"detail": "the phase task is not ready yet; retry"},
                            status=status.HTTP_409_CONFLICT)
        return Response(payload)


class RunnerPhaseReportView(APIView):
    """POST /api/runner/phases/<run_id>/report/ — the companion reports its phase result;
    resumes the AgentRunWorkflow via the phase_reported signal."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, run_id):
        from orchestration.phase_report import PhaseReportError, report_phase

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        args = request.data if isinstance(request.data, dict) else {}
        try:
            out = report_phase(tenant_id=str(runner.tenant_id), run_id=str(run_id), report=args)
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        except PhaseReportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class RunnerReviewReportView(APIView):
    """POST /api/runner/reviews/<run_id>/report/ — the companion posts its 08 review verdict;
    the server-side CompanionReviewProvider's poll picks it up and parses the findings."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, run_id):
        from orchestration.review_provider import record_review_report

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        args = request.data if isinstance(request.data, dict) else {}
        try:
            out = record_review_report(
                tenant_id=str(runner.tenant_id), run_id=str(run_id),
                body=args.get("body", ""), status=args.get("status", "ok"),
                # The companion sends its diagnostic here on a failed report. Dropping it left
                # the platform knowing a review failed but never why — the cause survived only
                # in the companion's local engine log.
                message=args.get("message", ""))
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(out)


class RunnerBuildReportView(APIView):
    """POST /api/runner/builds/<run_id>/report/ — the companion reports its build result;
    resumes the BuildWorkflow via the build_reported signal."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, run_id):
        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        args = request.data if isinstance(request.data, dict) else {}
        try:
            out = report_build(tenant_id=str(runner.tenant_id), run_id=str(run_id), report=args)
        except Run.DoesNotExist:
            return Response({"detail": "run not found"}, status=status.HTTP_404_NOT_FOUND)
        except BuildReportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


class RunnerCodeIntelClaimView(APIView):
    """GET /api/runner/code-intel/ — the companion claims the next pending code-intel job
    dispatched to its enrollment (Brownfield B4). Separate from the Run claim path (/work/) so
    the proven plan/review/build dispatch is untouched. Skip-locked so two daemons never grab the
    same job; a job a dead companion left `claimed` past the lease is re-claimable. Returns
    `{job_id, repo, base}` or 204 when idle."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        from django.db import transaction
        from django.db.models import Q
        from django.utils import timezone

        from apps.runs.models import CodeIntelJob

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        now = timezone.now()
        stale_before = now - CLAIM_LEASE
        with tenant_context(tid), transaction.atomic():
            # OWNED (routed here) OR BROADCAST (null enrollment, same project) — mirrors the Run
            # claim's self-healing so a job dispatched before a companion is up still runs.
            owned = Q(enrollment_id=runner.id)
            broadcast = Q(project_id=runner.project_id) & Q(enrollment__isnull=True)
            candidates = (
                CodeIntelJob.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tid)
                .filter(owned | broadcast)
                .filter(Q(status=CodeIntelJob.Status.PENDING)
                        | Q(status=CodeIntelJob.Status.CLAIMED))
                .order_by("created_at")
            )
            job = None
            for cand in candidates:
                if cand.status == CodeIntelJob.Status.PENDING:
                    job = cand
                    break
                if (cand.status == CodeIntelJob.Status.CLAIMED
                        and cand.claimed_at is not None and cand.claimed_at < stale_before):
                    job = cand   # a dead companion's stale claim → re-claim
                    break
            if job is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            if job.enrollment_id is None:
                job.enrollment_id = runner.id          # bind broadcast → owned on claim
            job.status = CodeIntelJob.Status.CLAIMED
            job.claimed_at = now
            job.save(update_fields=["enrollment", "status", "claimed_at", "updated_at"])
            return Response({
                "job_id": str(job.id),
                "repo": job.repo.name,
                "base": job.repo.default_base or "main",
            })


class RunnerA11yAuditClaimView(APIView):
    """GET /api/runner/a11y-audits/ — the companion claims the next audit waiting for a machine
    (task 8a). Separate from the Run claim path (/work/) and from code intelligence, for the same
    reason each of those is separate: a baseline audit needs no engine and no work item, it needs
    a browser and an address only this machine can reach.

    Skip-locked so two companions never take the same audit. A companion that RESTARTS picks
    its own audit back up once the lease has passed — the common failure — but another machine
    never takes it over: an audit belongs to the machine that can reach the running application,
    and a colleague's machine may not have it up at all, so handing it across would produce a
    report saying every page was unreachable. A stalled audit is visible with the time it was
    claimed, and running again opens a fresh one.

    Returns `{audit_id, project_id, repo, repo_reason, manifest}` or 204 when idle.

    `repo` is the repository the audit must run FROM — the browser and the scanner are resolved
    out of that project's own `node_modules`, so without a local clone of it there is nowhere to
    run. It is the same repository the address came from, deliberately: two rules for "which
    project is this" could point at different ones and audit an application from inside another's
    folder.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        from django.db import transaction
        from django.db.models import Q
        from django.utils import timezone

        from apps.a11y.baseline import abandon_stale_audits, audit_manifest
        from apps.a11y.models import A11yBaselineAudit
        from apps.projects.preview_config import resolve_audit_repo

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        now = timezone.now()
        stale_before = now - CLAIM_LEASE
        # Before looking for work, close anything a dead machine left mid-capture. Here as well
        # as on the heartbeat because a companion started fresh (rather than resumed) asks for
        # work before it has heartbeated, and because an audit still showing as running is the
        # first thing its owner sees when they come back to the screen.
        abandon_stale_audits(tenant_id=tid, project_id=str(runner.project_id),
                             stale_before=stale_before)
        with tenant_context(tid), transaction.atomic():
            owned = Q(enrollment_id=runner.id)
            broadcast = Q(project_id=runner.project_id) & Q(enrollment__isnull=True)
            candidates = (
                A11yBaselineAudit.objects.select_for_update(skip_locked=True)
                .filter(tenant_id=tid)
                .filter(owned | broadcast)
                .filter(Q(status=A11yBaselineAudit.Status.PENDING)
                        | Q(status=A11yBaselineAudit.Status.CLAIMED))
                .order_by("created_at")
            )
            audit = None
            for cand in candidates:
                if cand.status == A11yBaselineAudit.Status.PENDING:
                    audit = cand
                    break
                if (cand.status == A11yBaselineAudit.Status.CLAIMED
                        and cand.claimed_at is not None and cand.claimed_at < stale_before):
                    audit = cand   # a dead companion's stale claim -> re-claim
                    break
            if audit is None:
                return Response(status=status.HTTP_204_NO_CONTENT)
            if audit.enrollment_id is None:
                audit.enrollment_id = runner.id        # bind broadcast -> owned on claim
            audit.status = A11yBaselineAudit.Status.CLAIMED
            audit.claimed_at = now
            audit.save(update_fields=["enrollment", "status", "claimed_at", "updated_at"])
            repo = resolve_audit_repo(tenant_id=tid, project_id=str(audit.project_id))
            return Response({
                "audit_id": str(audit.id),
                "project_id": str(audit.project_id),
                # Handed over WITH its problem rather than withheld. The companion closes the
                # audit with this as the stated reason, so the failure is on the record and the
                # screen says what to set — an audit silently never claimed would just sit
                # there looking like a machine that had not got to it yet.
                "repo": repo.name,
                "repo_reason": repo.reason,
                "manifest": audit_manifest(audit),
            })


class RunnerCodeIntelReportView(APIView):
    """POST /api/runner/code-intel/<job_id>/report/ — the companion reports its code-intel result
    (B4). The server-side sink persists the `codebase_intelligence` artifact + Knowledge-Index
    chunk (`record_code_intel_index`). Only this companion-authenticated path can write a real
    index — the web dispatch endpoint no longer accepts one (B4-2). `{status:"failed", error}`
    marks the job failed without persisting anything."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, job_id):
        from apps.runs.models import CodeIntelJob
        from integrations.onboarding import record_code_intel_index

        runner = RunnerStateView._resolve_runner(request)
        if runner is None:
            return Response({"detail": "invalid or missing Runner token"},
                            status=status.HTTP_401_UNAUTHORIZED)
        tid = str(runner.tenant_id)
        args = request.data if isinstance(request.data, dict) else {}
        with tenant_context(tid):
            job = CodeIntelJob.objects.filter(id=job_id, tenant_id=tid).first()
        if job is None:
            return Response({"detail": "job not found"}, status=status.HTTP_404_NOT_FOUND)

        if args.get("status") == "failed":
            with tenant_context(tid):
                job.status = CodeIntelJob.Status.FAILED
                job.error = str(args.get("error", ""))[:512]
                job.save(update_fields=["status", "error", "updated_at"])
            return Response({"status": "failed"})

        index = args.get("index") if isinstance(args.get("index"), dict) else {}
        out = record_code_intel_index(
            tenant_id=tid, project_id=str(job.project_id), repo_id=str(job.repo_id),
            index=index, summary=args.get("summary", ""))
        with tenant_context(tid):
            job.status = CodeIntelJob.Status.INDEXED
            job.result = {"artifact_id": out.get("artifact_id")}
            job.save(update_fields=["status", "result", "updated_at"])
        return Response(out)
