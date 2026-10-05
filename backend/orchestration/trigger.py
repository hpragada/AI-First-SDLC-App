"""Phase trigger (AGENT_MIGRATION_SPEC §5).

In the platform there are no slash commands: a legacy command becomes a *phase trigger* —
a UI/API action that creates a Run for a WorkItem and starts its AgentRunWorkflow. This
replaces the `commands/*.md` files. The workflow starter is injectable for testing.
"""
from __future__ import annotations

from dataclasses import dataclass

from mcp_platform_state import tools

from apps.labels import phase_label
from apps.registry.catalog import gate_role_for, reads_code
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .types import AgentRunInput


class TriggerError(Exception):
    """Could not start a phase run (e.g. no matching AgentSpec)."""


class ActiveRunError(TriggerError):
    """A run is already in progress for this work item (Bugs S.No 77, Case 2). The view maps
    this to HTTP 409 so the UI can offer 'wait / take over' rather than silently double-running."""


class NoCompanionError(TriggerError):
    """An onboarding agent was triggered but the user has no companion enrolled. These agents
    require the companion (00c reads a repo worktree; both use ask_human), so we FAIL CLOSED
    instead of falling back to a server-mode run that has neither tool. The view maps this to a
    'start your companion' message; onboarding keeps a deterministic/mechanical fallback."""


# Statuses that mean a run is still live for a work item — re-triggering while one of these is
# open would spawn a second concurrent run against the same branch/PR (Bugs S.No 77). STALLED is
# intentionally excluded: it is parked for human takeover (S.No 89) and a re-trigger is a valid
# restart there.
#
# PAUSED **is** included, and the difference is the whole reason it is a separate status. A parked
# run is one nobody chose — the machine went away, and starting again is the obvious recourse. A
# paused run is one somebody stopped on purpose and intends to resume: its workflow is alive and
# waiting, and its companion dispatch is held back from the claim queue. Allowing a re-trigger over
# it would hand the same work item a second run — two agents, one branch — and the user who pressed
# Pause would be the last person to expect it. They get the refusal below instead, which tells them
# the run is theirs to resume.
_ACTIVE_RUN_STATUSES = (
    Run.Status.PENDING,
    Run.Status.RUNNING,
    Run.Status.AWAITING_GATE,
    Run.Status.APPROVED,
    Run.Status.PAUSED,
)


def _guard_no_active_run(tenant_id: str, work_item_id: str) -> None:
    """Raise ActiveRunError if the work item already has a live run (must be called inside a
    tenant_context)."""
    active = (
        Run.objects.filter(
            tenant_id=tenant_id, work_item_id=work_item_id, status__in=_ACTIVE_RUN_STATUSES
        )
        .order_by("-created_at")
        .first()
    )
    if active is not None:
        # Screen Words group 5. This sentence goes straight onto Phases & Runs, so it starts with
        # a capital, names the state in the client's words and says what to do next. It used to
        # read "a run is already in progress for this work item (status: awaiting_gate)." — the
        # stored status in brackets, which is the platform's vocabulary, not the reader's. And it
        # said "wait for it to finish" about a run that was waiting on the reader, not working.
        from apps.labels import run_status_label

        # A PAUSED run gets its own sentence. The two below are both wrong for it: nobody needs to
        # "wait for it to finish" for a run that is not running, and the reader is not being told
        # about somebody else's problem — they paused it themselves, probably minutes ago. Say the
        # one thing they need, which is that the run is still theirs and resuming keeps the work.
        if active.status == Run.Status.PAUSED:
            raise ActiveRunError(
                "You paused this work item's run. Open it and resume it to carry on from where it "
                "stopped — starting a new one would throw away what it has already done."
            )
        waiting_at_gate = active.status == "awaiting_gate"
        next_step = (
            "Decide that gate, or take the run over, before starting another."
            if waiting_at_gate
            else "Wait for it to finish, or take it over, before starting another."
        )
        raise ActiveRunError(
            f"This work item already has a run, and it is "
            f"{run_status_label(active.status).lower()}. {next_step}"
        )


@dataclass
class TriggerResult:
    run_id: str
    workflow_id: str


def _default_workflow_starter(workflow_id: str, inp: AgentRunInput) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    from .workflows import AgentRunWorkflow

    async def _start() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        await client.start_workflow(
            AgentRunWorkflow.run, inp, id=workflow_id, task_queue=settings.TEMPORAL_TASK_QUEUE
        )

    asyncio.run(_start())


def _resolve_enrollment(tenant_id, project_id, user_id):
    """The triggering user's active companion for this project (req #1 — run on their own
    local Claude Code). None ⇒ no companion enrolled ⇒ server fallback.

    Selection (Bugs S.No 84): a user often has several ACTIVE enrollments for one project
    (each Connect Machine visit mints one), and only ONE of them is the token the running
    companion actually polls with. Picking purely by recency could dispatch to an enrollment
    that never connected — the live companion then long-polls /work/ into 204s forever and
    the run sticks in pending. So prefer, in order:
      1. the newest enrollment that is ONLINE (last_seen within ONLINE_THRESHOLD — it is
         heartbeating/polling right now);
      2. else the newest that has EVER checked in (a companion held that token at some point);
      3. else the newest overall (nothing has connected yet — e.g. the user triggers before
         starting the companion; the dispatch waits for it, same as before).
    """
    from django.utils import timezone

    from apps.runs.enrollment import ONLINE_THRESHOLD
    from apps.runs.models import RunnerEnrollment

    if not user_id:
        return None
    candidates = list(
        RunnerEnrollment.objects.filter(
            tenant_id=tenant_id, project_id=project_id, developer_id=user_id,
            status=RunnerEnrollment.Status.ACTIVE,
        )
        .order_by("-created_at")
    )
    if not candidates:
        return None
    cutoff = timezone.now() - ONLINE_THRESHOLD
    online = [e for e in candidates if e.last_seen and e.last_seen >= cutoff]
    if online:
        return online[0]
    seen = [e for e in candidates if e.last_seen]
    if seen:
        return seen[0]
    return candidates[0]


def companion_liveness_for(tenant_id, project_id, user_id) -> str:
    """Is the companion this user's phase would be dispatched TO alive? One of:

    - `"online"` — it called in within `ONLINE_THRESHOLD`; dispatch will be claimed.
    - `"stale"`  — it connected at some point and has since gone QUIET. This is the only
                   mistake of the four: work dispatched now is claimed by nobody, and the run
                   flips to RUNNING with `dispatch.status` still "pending", looking live until
                   the 2h takeover (S.No 89).
    - `"never"`  — an enrollment exists but nothing has ever held that token. NOT a mistake:
                   `_resolve_enrollment`'s selection rule supports this on purpose (its case 3
                   — "the user triggers before starting the companion; the dispatch waits for
                   it"), which is how onboarding works. Mint a token, trigger, then start the
                   machine.
    - `"none"`   — no enrollment for this user+project at all, so `trigger_phase` resolves to a
                   SERVER-mode run. Also legitimate: CI, tests, a project nobody has connected
                   a machine to.

    All four are kept apart because only `"stale"` may be refused, and each collapse breaks
    something real: `"never"` into `"stale"` blocks onboarding's trigger-then-connect flow,
    `"none"` into `"stale"` refuses the server fallback, and `"stale"` into `"online"` is the
    bug being fixed. The distinction between the two "no machine" cases is the whole reason this
    returns a word rather than a boolean.

    Deliberately built on `_resolve_enrollment` and `ONLINE_THRESHOLD` rather than its own query,
    so it answers about the *same* enrollment the dispatch will pick and against the *same*
    threshold the status pill shows. A second implementation here could disagree with either, and
    a guard that refuses work the pill calls fine (or vice versa) is worse than no guard.
    """
    from django.utils import timezone

    from apps.runs.enrollment import ONLINE_THRESHOLD
    from apps.tenancy.context import tenant_context

    # Inside the tenant's context, like every other enrollment lookup here: forced RLS hides
    # every row from a query with no tenant context, which would read as "nothing is online"
    # however many companions were connected (the bug fixed in `trigger_onboarding_agent`).
    with tenant_context(str(tenant_id)):
        enrollment = _resolve_enrollment(tenant_id, project_id, user_id)
    if enrollment is None:
        return "none"
    if not enrollment.last_seen:
        return "never"
    if (timezone.now() - enrollment.last_seen) <= ONLINE_THRESHOLD:
        return "online"
    return "stale"


def _resolve_work_item_repo(
    *, tenant_id, project_id, work_item, repo=None, base=None
) -> tuple[str | None, str]:
    """Resolve (repo_name, base_branch) for a work item. Shared by `trigger_build` and the
    `reads_code` planning path so the two can never drift.

    - Prefers the work item's pinned Repository, then the passed-in overrides, then the
      project's single default repo.
    - Multi-repo + unpinned ⇒ raises TriggerError (ambiguous — the repo is chosen by the
      planner and confirmed at the Task Breakdown gate; never silently default it).
    - Returns repo=None only when the project has NO repository at all (a doc-only project);
      the caller decides whether that is fatal (build) or a graceful degrade (security scan)."""
    repo = repo or (work_item.repo.name if work_item.repo else None)
    base = base or (work_item.repo.default_base if work_item.repo else None)
    if not repo:
        from apps.projects.models import Repository

        project_repos = Repository.objects.filter(
            tenant_id=tenant_id, project_id=project_id
        )
        # Multi-repo (D5 / Hybrid Option C): NEVER silently default an unpinned work item —
        # its repo is chosen by the planner and confirmed at the Task Breakdown gate.
        if project_repos.count() > 1:
            # Screen Words group 5: capital, and "repo" spelled out as the word the screen uses.
            raise TriggerError(
                "This work item hasn't been assigned a repository, and the project has more "
                "than one. Choose its repository on the work item, or confirm the assignment "
                "at the Task Breakdown gate, before running this phase."
            )
        # Single-repo: fall back to the project's default repository (S-13).
        default_repo = project_repos.filter(is_default=True).first()
        if default_repo is not None:
            repo = default_repo.name
            base = base or default_repo.default_base
    return repo, (base or "main")


def trigger_phase(
    *,
    tenant_id: str,
    project_id: str,
    work_item_id: str,
    agent_key: str,
    gate_type: str = "phase_gate",
    required_role: str | None = None,
    triggered_by: str | None = None,
    execution_mode: str | None = None,
    auto_approve: bool = False,
    review_history: list[dict] | None = None,
    revision_of: str | None = None,
    report_timeout_seconds: int | None = None,
    verify_timeout_seconds: int | None = None,
    workflow_starter=None,
) -> TriggerResult:
    """Start an agent run for a work item and kick off its Temporal workflow. The phase runs
    on the triggering user's enrolled local companion when one exists (`execution_mode`
    auto-resolves to "companion"), else server-side (the CI/test fallback).

    `auto_approve` (Part B, 00e) publishes the run's result without a human gate — default False,
    so every normal phase still opens its review gate unchanged.

    `review_history` / `revision_of` are set only when a reviewer pressed "Request changes" on this
    phase's gate: the accumulated review conversation, and the run this one revises. They are
    persisted on `Run.inputs` (NOT on the Temporal payload) and read back by the manifest composer,
    so the revising agent sees every round's direction and what it produced in response.

    **`report_timeout_seconds` / `verify_timeout_seconds` let a caller size its own deadlines.**
    Both were fixed constants shared by every phase, and both fired on work that was going
    perfectly well: the report deadline at two hours on a judging pass that needed two and a
    quarter, and the write-completeness budget at five minutes on a check with 800 elements to
    account for. A phase that knows how much work it is handing over is the only thing that can
    know how long that work should take, so it may now say. `None` keeps the dataclass defaults,
    which is every caller but one — nothing else changes behaviour."""
    workflow_starter = workflow_starter or _default_workflow_starter

    with tenant_context(tenant_id):
        spec = (
            AgentSpec.objects.filter(tenant_id=tenant_id, key=agent_key)
            .order_by("-semver")
            .first()
        )
        if spec is None:
            # Screen Words group 5: named a Python class and quoted the key. A phase that is not
            # registered is a setup problem the reader can act on, said in those terms.
            raise TriggerError(
                f"{phase_label(agent_key)} isn't set up for this workspace yet, so it "
                "can't be run. An admin can add it from the agent registry."
            )
        work_item = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        _guard_no_active_run(tenant_id, work_item_id)

        phase = spec.phase_label or agent_key
        role = required_role or gate_role_for(agent_key)
        # Repo-scoped planning phases (catalog `reads_code`, e.g. 10_security) get a READ-ONLY
        # worktree so the agent can scan real source. Every other planning phase resolves no
        # repo → repo/base stay None → dispatch/companion behaviour is byte-identical to today.
        # A doc-only project (no repository) degrades to manifest-only rather than failing.
        repo: str | None = None
        base: str | None = None
        if reads_code(agent_key):
            repo, base = _resolve_work_item_repo(
                tenant_id=tenant_id, project_id=project_id, work_item=work_item
            )
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
        mode = execution_mode or ("companion" if enrollment is not None else "server")
        run = Run.objects.create(
            tenant_id=tenant_id, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            prompt_version=spec.prompt_version, status=Run.Status.PENDING,
            triggered_by_id=triggered_by,
            inputs=({"review_history": review_history, "revision_of": revision_of,
                     "revision": len(review_history) + 1} if review_history else {}),
        )
        workflow_id = f"agent-run-{run.id}"
        run.temporal_workflow_id = workflow_id
        run.save(update_fields=["temporal_workflow_id", "updated_at"])

        # Only pass the deadlines a caller actually chose, so an unset one keeps the dataclass
        # default rather than this function having to restate it (a second copy of a default is
        # a second place for it to drift).
        deadlines = {
            k: v for k, v in (("report_timeout_seconds", report_timeout_seconds),
                              ("verify_timeout_seconds", verify_timeout_seconds))
            if v is not None
        }
        inp = AgentRunInput(
            run_id=str(run.id), tenant_id=str(tenant_id), project_id=str(project_id),
            work_item_id=str(work_item_id), agent_spec_id=str(spec.id), phase=phase,
            gate_type=gate_type, required_role=role, execution_mode=mode,
            enrollment_id=str(enrollment.id) if enrollment is not None else None,
            repo=repo, base=base, auto_approve=auto_approve, **deadlines,
        )
        event_payload = {
            "agent_key": agent_key, "workflow_id": workflow_id, "execution_mode": mode,
        }
        if repo:
            event_payload["repo"] = repo
        tools.log_event(
            tenant_id, "platform", "run.triggered", "run", str(run.id), event_payload,
        )

    workflow_starter(workflow_id, inp)
    return TriggerResult(run_id=str(run.id), workflow_id=workflow_id)


#: Onboarding agents whose output a human must approve before the platform acts on it, so they run
#: GATED rather than headless. Only the gap report qualifies: it is a judgement about the client's
#: project (phase statuses + the resume point), not a mechanical index like 00c's.
_GATED_ONBOARDING_AGENTS = ("00_onboarding",)


def trigger_onboarding_agent(
    *, tenant_id, project_id, agent_key, repo_id=None, triggered_by=None, workflow_starter=None,
) -> TriggerResult:
    """Run an onboarding agent (00c code intelligence / 00_onboarding assessment) against the
    per-project carrier work item, on the triggering user's companion.

    Fail-closed on execution mode: these agents need the companion (00c reads a repo worktree;
    both use ask_human), so with no companion enrolled we raise `NoCompanionError` rather than
    let `trigger_phase` silently fall back to a server-mode run that has neither tool. The REST
    caller catches this and keeps the deterministic/mechanical path as the fallback.

    HEADLESS (`auto_approve=True`) for **Index code** (00c): it is a setup step, not a lifecycle
    phase a reviewer signs off, and its run is hosted on a carrier work item hidden from the
    backlog. The Onboarding hub reports its progress and links to what it produced, which IS the
    review surface. Same reasoning as the 00e vision path. Publishes INTERNAL only — external
    export to a SoR stays user-triggered (#5).

    GATED (`auto_approve=False`) for **Gap report** (00_onboarding), team decision 2026-08-03.
    Unlike 00c, this agent's output is a JUDGEMENT about the client's project — which phases are
    done, where to resume — that a Product Owner must own before the pipeline acts on it. The
    original "a gate here could never be found" reasoning does not hold for it: only the *backlog*
    and *Phases & Runs* hide carriers; `ApprovalViewSet` and the dashboard's pending-gates query do
    not, so the gate surfaces in Gates and on the dashboard the moment it opens. Approval is also
    what publishes the report — `publish_artifacts` runs on the approved path, and the report is
    bound to its run (S5-3), so the gate is the report's one and only publish route."""
    from integrations.onboarding import ensure_onboarding_work_item

    # Inside the tenant's context, like every other enrollment lookup (see trigger_code_intel):
    # forced row-level security hides every enrollment row from a query with no tenant context,
    # so this resolved to None however many companions were connected — and the agent path
    # silently fell back to the deterministic one every single time.
    with tenant_context(tenant_id):
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
    if enrollment is None:
        raise NoCompanionError(
            "This step runs on your local companion — it reads your code and can ask you "
            "questions. Start your companion for this project, then try again."
        )
    work_item = ensure_onboarding_work_item(
        tenant_id=tenant_id, project_id=project_id, repo_id=repo_id
    )
    return trigger_phase(
        tenant_id=tenant_id, project_id=project_id, work_item_id=str(work_item.id),
        agent_key=agent_key, triggered_by=triggered_by, execution_mode="companion",
        auto_approve=agent_key not in _GATED_ONBOARDING_AGENTS,
        workflow_starter=workflow_starter,
    )


_VISION_AGENT_KEY = "00e_document_vision"


def trigger_vision(
    *, tenant_id, project_id, source_document_id, artifact_id, filename,
    triggered_by=None, workflow_starter=None, target_type=None, title=None,
) -> TriggerResult:
    """Run the document-vision agent (00e) on the user's companion for ONE adopted document
    (Part B). Reads the document's preserved page images and re-registers it as a faithful new
    version, published automatically (no gate — the human already adopted these pages).

    Fail-closed like `trigger_onboarding_agent`: vision runs the engine on the companion
    subscription, so with no companion enrolled we raise `NoCompanionError` (the adopt hook
    catches it and simply skips — the document stays adopted with its extracted text)."""
    from integrations.onboarding import ensure_vision_work_item

    # Inside the tenant's context — see the same fix in trigger_onboarding_agent above.
    with tenant_context(tenant_id):
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
    if enrollment is None:
        raise NoCompanionError(
            # "Your machine", not "companion" — the rest of the product calls it that ("Connect
            # your machine"), and a first-time brownfield user has never met the other word.
            "Your machine isn't connected, so the diagrams in this document weren't read. "
            "Connect your machine and adopt this document again."
        )
    work_item = ensure_vision_work_item(
        tenant_id=tenant_id, project_id=project_id, source_document_id=source_document_id,
        artifact_id=artifact_id, filename=filename, target_type=target_type, title=title,
    )
    return trigger_phase(
        tenant_id=tenant_id, project_id=project_id, work_item_id=str(work_item.id),
        agent_key=_VISION_AGENT_KEY, triggered_by=triggered_by, execution_mode="companion",
        auto_approve=True, workflow_starter=workflow_starter,
    )


def trigger_code_intel(*, tenant_id, project_id, repo_id, triggered_by=None) -> dict:
    """Dispatch a code-intelligence indexing job to the triggering user's enrolled companion (B4).

    Creates a PENDING `CodeIntelJob`; the companion claims it, runs the built-in analyzer in a
    read-only worktree, and reports the index back (the report sink persists the artifact). No
    WorkItem/AgentSpec/Temporal — code intelligence is mechanical, repo-scoped analysis, not an
    agent run, so it rides its own dispatch channel (Option C) instead of the Run/gate machinery.
    Enrollment is resolved like the Run path: the triggering user's active companion, else a
    broadcast job any active companion for the tenant+project may claim."""
    from apps.projects.models import Project, Repository
    from apps.runs.models import CodeIntelJob

    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        repo = Repository.objects.get(id=repo_id, tenant_id=tenant_id, project_id=project_id)
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
        job = CodeIntelJob.objects.create(
            tenant_id=tenant_id, project=project, repo=repo,
            enrollment=enrollment, triggered_by_id=triggered_by,
            status=CodeIntelJob.Status.PENDING,
        )
        tools.log_event(
            tenant_id, "platform", "code_intel.dispatched", "code_intel_job", str(job.id),
            {"repo": repo.name,
             "enrollment_id": str(enrollment.id) if enrollment is not None else None},
        )
    return {"job_id": str(job.id), "repo_id": str(repo.id), "status": "dispatched"}


def _default_build_starter(workflow_id: str, inp) -> None:
    import asyncio

    from django.conf import settings
    from temporalio.client import Client

    from .build_workflow import BuildWorkflow

    async def _start() -> None:
        client = await Client.connect(
            settings.TEMPORAL_HOST, namespace=settings.TEMPORAL_NAMESPACE
        )
        await client.start_workflow(
            BuildWorkflow.run, inp, id=workflow_id, task_queue=settings.TEMPORAL_TASK_QUEUE
        )

    asyncio.run(_start())


def trigger_build(
    *,
    tenant_id: str,
    project_id: str,
    work_item_id: str,
    agent_key: str = "07_implementation",
    repo: str | None = None,
    base: str | None = None,
    work_item_key: str | None = None,
    required_role: str = "reviewer",
    triggered_by: str | None = None,
    workflow_starter=None,
    # Bugs S.No 161: an auto-retry after remediation exhaustion passes these through so the new
    # run's manifest carries what blocked the prior attempt (see BuildInput / dispatch_build_core).
    attempt: int = 1,
    prior_attempt_context: str = "",
) -> TriggerResult:
    """Start a BuildWorkflow for a WorkItem (resolves repo/base from its Repository). The build
    runs on the triggering user's enrolled companion (claimable via /api/runner/work/)."""
    from .build_types import BuildInput

    workflow_starter = workflow_starter or _default_build_starter

    with tenant_context(tenant_id):
        spec = (
            AgentSpec.objects.filter(tenant_id=tenant_id, key=agent_key)
            .order_by("-semver").first()
        )
        if spec is None:
            # Screen Words group 5: named a Python class and quoted the key. A phase that is not
            # registered is a setup problem the reader can act on, said in those terms.
            raise TriggerError(
                f"{phase_label(agent_key)} isn't set up for this workspace yet, so it "
                "can't be run. An admin can add it from the agent registry."
            )
        work_item = WorkItem.objects.select_related("repo").get(
            id=work_item_id, tenant_id=tenant_id
        )
        _guard_no_active_run(tenant_id, work_item_id)
        # Shared with the reads_code planning path (_resolve_work_item_repo): pinned repo →
        # overrides → single default; multi-repo unpinned raises. A build additionally requires
        # a repo (fail-closed below); a security scan tolerates None (degrades to doc-only).
        repo, base = _resolve_work_item_repo(
            tenant_id=tenant_id, project_id=project_id, work_item=work_item, repo=repo, base=base
        )
        if not repo:
            # Screen Words group 5: capital, and it names the screen the reader needs.
            raise TriggerError(
                "This build has no repository to work in. Connect one on the project's "
                "Repositories screen, or choose one on the work item, then try again."
            )
        work_item_key = (
            work_item_key or (work_item.external_ref or {}).get("id")
            or f"WI-{str(work_item.id)[:8]}"
        )
        enrollment = _resolve_enrollment(tenant_id, project_id, triggered_by)
        run = Run.objects.create(
            tenant_id=tenant_id, work_item=work_item, agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            prompt_version=spec.prompt_version, status=Run.Status.PENDING,
            triggered_by_id=triggered_by,
        )
        workflow_id = f"build-run-{run.id}"
        run.temporal_workflow_id = workflow_id
        run.save(update_fields=["temporal_workflow_id", "updated_at"])

        inp = BuildInput(
            run_id=str(run.id), tenant_id=str(tenant_id), project_id=str(project_id),
            work_item_id=str(work_item_id), agent_spec_id=str(spec.id),
            # The phase label from the catalog (via the spec), NOT the "implementation" default:
            # a build can ride any build agent (07_implementation / 09b_test_automation /
            # 11_cicd), and hardcoding "implementation" mislabeled 09b/CICD runs — their dispatch
            # payload, RUNNER_PHASE, composed manifest and `code` artifact all read the wrong
            # phase. Mirror trigger_phase (`spec.phase_label or agent_key`) so the one catalog
            # value drives both trigger paths and can never drift.
            phase=spec.phase_label or agent_key,
            work_item_key=work_item_key, repo=repo, base=base, required_role=required_role,
            # The human title, for what a PERSON reads (Bugs S.No 151) — artifact + PR titles.
            work_item_title=work_item.title or "",
            enrollment_id=str(enrollment.id) if enrollment is not None else None,
            attempt=attempt, prior_attempt_context=prior_attempt_context,
        )
        tools.log_event(
            tenant_id, "platform", "build.triggered", "run", str(run.id),
            {"workflow_id": workflow_id, "repo": repo, "work_item_key": work_item_key},
        )

    workflow_starter(workflow_id, inp)
    return TriggerResult(run_id=str(run.id), workflow_id=workflow_id)
