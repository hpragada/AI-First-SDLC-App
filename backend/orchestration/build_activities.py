"""BuildWorkflow activities (Phase-2 §4). Each is a thin @activity.defn over an idempotent
*core* (idempotent by run_id so Temporal retries are safe). Side effects only here, never in
the workflow. CodeHost goes through the capability seam (`get_capability`); the engine never
touches Git — the platform opens/merges the PR (D2).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from mcp_platform_state import tools
from temporalio import activity
from temporalio.exceptions import ApplicationError

from apps.gates.models import Approval
from apps.registry.models import Artifact
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .activities import _boundary, compose_manifest_core, get_object_store
from .build_types import BuildInput, BuildReport, display_name


def _load_agent_body(agent_spec_id: str, tenant_id: str) -> tuple[str, str]:
    """Read the migrated build agent's body (+ model) to ship to the companion. Tolerant —
    the agent is migrated in §8; an absent body is empty, not fatal, so dispatch works now."""
    from apps.registry.models import AgentSpec

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


# ── cores (idempotent by run_id) ────────────────────────────────────
def dispatch_build_core(inp: BuildInput) -> dict:
    """Assemble the self-contained BuildTask payload (manifest + agent body) for the companion
    to fetch, mark the run RUNNING, and announce the dispatch. Idempotent."""
    from django.conf import settings

    manifest = compose_manifest_core(inp)            # duck-typed: reads work_item/project/phase
    # Bugs S.No 161: an auto-retried attempt (after the prior attempt exhausted its remediation
    # cycles) carries forward what blocked it, so the fresh agent context doesn't walk into the
    # same wall blind — still fully automated, just a smarter retry instead of a blind one.
    if inp.attempt > 1 and inp.prior_attempt_context:
        manifest = (
            f"{manifest}\n\n## Prior attempt (#{inp.attempt - 1}) failed code review\n"
            f"{inp.prior_attempt_context}\n"
        )
    agent_body, model = _load_agent_body(inp.agent_spec_id, inp.tenant_id)
    payload = {
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "work_item_key": inp.work_item_key,
        "repo": inp.repo, "base": inp.base, "phase": inp.phase,
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
    }
    # Ship the preview-start config ONLY for the phase that brings the app up (09b Live App
    # Exploration + E2E, D7) — mirrors the companion's phase-gated Playwright wiring. The
    # companion turns an empty config into a fail-loud; 07/11 builds never carry it.
    if inp.phase == "test_automation":
        from apps.projects.preview_config import resolve_preview_start, resolve_preview_url

        # Manual "point at a running app" URL takes precedence in the companion; auto-start
        # (preview_start) is the fallback. Ship both — the companion picks (P3-09bR follow-up).
        payload["preview_url"] = resolve_preview_url(
            tenant_id=inp.tenant_id, project_id=inp.project_id, repo_name=inp.repo)
        payload["preview_start"] = resolve_preview_start(
            tenant_id=inp.tenant_id, project_id=inp.project_id, repo_name=inp.repo)
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        # Carry the WorkItem title/type so the companion derives a meaningful Conventional-Commit
        # message (the platform owns the commit, D2 — the agent never runs git).
        wi = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        payload["work_item_title"] = wi.title
        payload["work_item_type"] = wi.type
        run.inputs = {
            **(run.inputs or {}),
            "build_task": payload,
            # Claim block so the companion daemon can pull this build via /api/runner/work/
            # (same seam as planning); the manual /builds/<run>/ fetch still works too.
            "dispatch": {"kind": "build", "enrollment_id": inp.enrollment_id,
                         "status": "pending"},
        }
        if run.status not in (Run.Status.RUNNING, Run.Status.AWAITING_GATE, Run.Status.COMPLETED):
            run.status = Run.Status.RUNNING
        run.save(update_fields=["inputs", "status", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.dispatched", "run", inp.run_id,
                        {"repo": inp.repo, "work_item": inp.work_item_key})
    return {"dispatched": True}


def _code_artifact(inp: BuildInput) -> Artifact | None:
    """The run's `code` artifact — the opened PR. A remediation build makes the implementation
    agent re-register a fresh *pre-PR* pointer (branch/files, no PR ref) on the SAME run, so a
    run can carry >1 `code` row; `.first()` is non-deterministic (no Meta ordering) and could
    return the pre-PR pointer, making review/merge fail with "no opened PR". Prefer the artifact
    that already carries a real PR ref (repo+number); fall back to the oldest otherwise."""
    with tenant_context(inp.tenant_id):
        arts = list(
            Artifact.objects
            .filter(run_id=inp.run_id, tenant_id=inp.tenant_id, type="code")
            .order_by("created_at")
        )
    return next((a for a in arts if _is_pr_ref(a.external_ref)), arts[0] if arts else None)


def _is_pr_ref(ref) -> bool:
    """True once a real PR has been opened for the code artifact — a PR ref carries repo + number.
    The implementation agent registers a *pre-PR* code pointer (branch/files, no PR yet, per its
    §Output contract); that is NOT an opened PR and must not short-circuit open_build_pr."""
    return bool(ref) and "repo" in ref and "number" in ref


def import_build_test_results_core(inp: BuildInput, report: BuildReport) -> dict:
    """Feed the build's own worktree suite results into the test loop (D4).

    This is the seam that closes §8's loop: the companion ran the suite in the worktree and
    reported its JUnit results, and here they become a `TestExecution` + `test_report` and
    drive the defect loopback (a failing test opens a `defect` child WorkItem; a passing one
    closes it) and the flaky quarantine.

    Three deliberate bounds:
      - **Only phases the catalog marks `imports_test_results`** (09b today). §5's loopback is
        about the TEST phase's failing tests — a red unit test in 07's implementation build
        fails that build as it always has, without opening defects.
      - **No results ⇒ no-op.** `import_test_results` refuses an empty set, so a build that ran
        no tests never registers a green execution nor closes a defect it said nothing about.
      - **Internal only** (`push_to_sor=False`). Pushing results to Xray is a user-triggered
        export (team decision 2026-07-07), never an automatic side-effect of a build report.

    Idempotent: `import_test_results` upserts the execution by (run, work_item), so a Temporal
    retry — or the remediation loop re-reporting — updates the same row rather than duplicating.
    """
    from apps.quality.services import import_test_results
    from apps.registry.catalog import imports_test_results as _phase_imports
    from apps.registry.models import AgentSpec

    results = list(report.test_results or [])
    if not results:
        return {"imported": False, "reason": "no test results reported"}

    with tenant_context(inp.tenant_id):
        spec = AgentSpec.objects.filter(id=inp.agent_spec_id, tenant_id=inp.tenant_id).first()
    agent_key = spec.key if spec else ""
    if not _phase_imports(agent_key):
        return {"imported": False, "reason": f"phase {agent_key!r} does not import test results"}

    out = import_test_results(
        tenant_id=inp.tenant_id, project_id=inp.project_id, work_item_id=inp.work_item_id,
        run_id=inp.run_id, results=results, summary=report.test_summary, push_to_sor=False,
    )
    return {"imported": out["status"] != "skipped", "status": out["status"],
            "defects_opened": out["defects_opened"], "defects_closed": out["defects_closed"],
            "flaky": out["flaky"]}


def provision_preview_core(inp: BuildInput, report: BuildReport) -> dict:
    """Record the companion-local preview env the build reported and link it on the PR (D7 /
    P3-09bR-5). No-op unless the build reported a preview URL (only 09b brings an app up).

    v1 lifetime note: the app PROCESS is ephemeral to the agent run — the companion tears it down
    when its build finishes (P3-09bR-2) — so this records the exploration URL as provenance + a PR
    link, and is the seam a persistent per-PR env (P5 cloud provider, behind `PreviewEnv.provider`)
    drops into without changing callers. Idempotent: `provision_preview` upserts by (work_item,
    pr_ref), so a Resume that retries the PR/gate block re-links rather than duplicating."""
    url = getattr(report, "preview_url", "") or ""
    if not url:
        return {"provisioned": False}
    from apps.quality.preview import provision_preview

    code = _code_artifact(inp)
    pr_ref = (f"{code.external_ref['repo']}#{code.external_ref['number']}"
              if code is not None and _is_pr_ref(code.external_ref) else "")
    out = provision_preview(
        tenant_id=inp.tenant_id, project_id=inp.project_id, work_item_id=inp.work_item_id,
        run_id=inp.run_id, pr_ref=pr_ref, url=url)
    return {"provisioned": True, "preview_id": out["preview_id"], "url": url, "pr_ref": pr_ref}


def teardown_preview_core(inp: BuildInput) -> dict:
    """Mark the run's preview env torn down at a terminal build state (merge/close or compensation,
    P3-09bR-5). Best-effort + idempotent — a no-op when no preview was recorded (07/11)."""
    from apps.quality.preview import teardown_preview_for_run

    return teardown_preview_for_run(
        tenant_id=inp.tenant_id, project_id=inp.project_id,
        work_item_id=inp.work_item_id, run_id=inp.run_id)


def open_build_pr_core(inp: BuildInput, report: BuildReport) -> dict:
    """Open the draft PR for the companion-pushed branch and register/reconcile the `code`
    pointer. Idempotent — only an artifact that already carries a real PR ref (repo+number) is
    reused. The agent's pre-PR pointer is *reconciled* (updated with the PR), not skipped."""
    from integrations.registry import get_capability
    from integrations.types import CapabilityError

    existing = _code_artifact(inp)
    if existing is not None and _is_pr_ref(existing.external_ref):
        return {"pr": existing.external_ref, "artifact_id": str(existing.id), "idempotent": True}

    # Bugs S.No 139: an empty build — the agent produced no changes, so nothing was committed or
    # pushed — cannot become a PR (GitHub 422 "no commits between base and head"). Fail fast with
    # a clear, non-retryable reason instead of a cryptic 422 after 3 wasted retries. This is the
    # expected outcome for a redundant task whose work already landed on the base.
    if not (report.head_sha or report.changed_files):
        raise ApplicationError(
            "empty build: the agent produced no changes, so there is nothing to open a pull "
            "request for",
            type="EmptyBuild", non_retryable=True,
        )

    codehost = get_capability(inp.tenant_id, "codehost")
    try:
        ref = codehost.open_pull_request(
            repo=inp.repo, head=report.branch, base=inp.base,
            # The PR title is read by humans in GitHub — use the task's title, not the branch slug
            # (Bugs S.No 151). The key still identifies the branch in the body.
            title=f"{display_name(inp)}: build",
            body=f"Build for {display_name(inp)} ({inp.work_item_key}).\n\n"
                 f"WorkItem {inp.work_item_id}.",
            draft=True,
        )
    except CapabilityError as exc:
        if exc.status == 422:      # no commits between base and head — an empty diff
            raise ApplicationError(
                "empty build: no commits between the base and the build branch (no changes to "
                "open a pull request for)",
                type="EmptyBuild", non_retryable=True,
            ) from exc
        raise
    external_ref = {"sor": "git", "repo": ref.repo, "number": ref.number,
                    "head": ref.head, "url": ref.url, "sha": ref.sha}
    if existing is not None:
        # Reconcile the agent's pre-PR code pointer with the PR the platform just opened
        # (register-don't-recreate) so downstream review/merge read a real PR ref.
        tools.update_artifact(inp.tenant_id, str(existing.id), external_ref=external_ref,
                              content_hash=report.head_sha or "", status=Artifact.Status.STAGED)
        artifact_id = str(existing.id)
    else:
        artifact = tools.register_artifact(
            inp.tenant_id, inp.project_id, inp.run_id, inp.phase, "code", "git",
            content_hash=report.head_sha or "", external_ref=external_ref,
            title=f"Code — {display_name(inp)}",
        )
        tools.update_artifact(inp.tenant_id, artifact["id"], status=Artifact.Status.STAGED)
        artifact_id = artifact["id"]
    if report.head_sha:
        try:
            codehost.set_commit_status(repo=inp.repo, sha=report.head_sha, state="pending",
                                       context="sdlc/build")
        except Exception:  # noqa: BLE001 — status is best-effort
            pass
    with tenant_context(inp.tenant_id):
        tools.log_event(inp.tenant_id, "orchestrator", "build.pr_opened", "run", inp.run_id,
                        {"pr": ref.url, "artifact_id": artifact_id})
    return {"pr": external_ref, "artifact_id": artifact_id}


def open_merge_gate_core(inp: BuildInput) -> str:
    """Open the merge gate (a reviewer Approval) — the gated SoR write is the merge (#5/#8)."""
    with tenant_context(inp.tenant_id):
        approval, created = Approval.objects.get_or_create(
            run_id=inp.run_id, gate_type=inp.gate_type, tenant_id=inp.tenant_id,
            defaults={"work_item_id": inp.work_item_id, "required_role": inp.required_role,
                      "decision": Approval.Decision.PENDING},
        )
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        if run.status != Run.Status.AWAITING_GATE:
            run.status = Run.Status.AWAITING_GATE
            run.save(update_fields=["status", "updated_at"])
        if created:
            tools.log_event(inp.tenant_id, "orchestrator", "gate.opened", "approval",
                            str(approval.id), {"required_role": inp.required_role,
                                               "gate": "merge"})
    return str(approval.id)


def reopen_merge_gate_core(inp: BuildInput, reason: str) -> dict:
    """Bugs S.No 141 (ENH-2): the merge hit a CONFLICT — re-open the merge gate for a
    resolve-then-retry instead of ending the whole build. Reset the reviewer Approval to PENDING,
    keep the run AWAITING_GATE, and record the conflict reason so the UI can tell the reviewer to
    resolve it in GitHub then approve again to retry the merge. The branch/PR are left as-is (the
    human resolves the conflict there); nothing is rebuilt. Idempotent (safe on Temporal retries):
    resetting an already-pending Approval + a merged/awaiting run is a no-op."""
    classified = classify_build_failure(reason)
    with tenant_context(inp.tenant_id):
        Approval.objects.filter(
            run_id=inp.run_id, gate_type=inp.gate_type, tenant_id=inp.tenant_id
        ).update(decision=Approval.Decision.PENDING, approver=None, decided_at=None)
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.AWAITING_GATE
        run.outputs = {**(run.outputs or {}), "merge_conflict": classified}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.merge_conflict", "run", inp.run_id,
                        {"reason": classified, "action": "merge gate re-opened for retry"})
    return {"status": "merge_conflict_reopened", "reason": classified}


def merge_build_pr_core(inp: BuildInput) -> dict:
    """On approval, merge the PR (the gated SoR write). Idempotent — an already-merged PR is
    a no-op; the code artifact becomes published and the run completes."""
    from integrations.registry import get_capability

    artifact = _code_artifact(inp)
    if artifact is None or not artifact.external_ref:
        raise RuntimeError(f"no code artifact/PR to merge for run {inp.run_id}")
    ref = artifact.external_ref
    pr_ref = f"{ref['repo']}#{ref['number']}"
    codehost = get_capability(inp.tenant_id, "codehost")
    pr = codehost.get_pull_request(pr_ref=pr_ref)
    if not pr.merged:
        # The PR was opened as a draft (draft during the 07<->08 review loop guards against a
        # premature human merge). GitHub refuses to merge a draft PR (HTTP 405), so take it out
        # of draft now that the merge gate is approved — the one legitimate moment to un-draft.
        if pr.draft:
            codehost.mark_ready_for_review(pr_ref=pr_ref)
        # Bugs S.No 136: never merge a stale/conflicted branch as-is (that raises a raw 405).
        # If the branch is merely *behind* its base, update it against base first; then if it is
        # a true conflict ("dirty"), fail the gate with a clear reason instead of a cryptic 405.
        # `ensure_mergeable` is a no-op for an already-clean PR (idempotent on Temporal retries).
        if hasattr(codehost, "ensure_mergeable"):
            pr = codehost.ensure_mergeable(pr_ref=pr_ref)
            if pr.mergeable is False or pr.mergeable_state == "dirty":
                # Not transient — fail fast (non-retryable) rather than burning 3 retries on a
                # conflict. The workflow routes this to mark_build_failed, whose classifier turns
                # it into the plain-language "merge conflict" reason (Bugs S.No 139).
                raise ApplicationError(
                    "merge conflict: the branch conflicts with its base and needs manual "
                    "resolution",
                    type="MergeConflict",
                    non_retryable=True,
                )
        pr = codehost.merge_pull_request(pr_ref=pr_ref)
    with tenant_context(inp.tenant_id):
        tools.log_event(inp.tenant_id, "orchestrator", "build.merged", "run", inp.run_id,
                        {"pr": pr_ref})
    # Publishing every artifact + completing the run is publish_build_artifacts_core's job
    # (Bugs S.No 152) — this activity only performs the gated SoR write.
    return {"merged": True, "pr_ref": pr_ref}


def publish_build_artifacts_core(inp: BuildInput) -> dict:
    """After the merge gate is approved and the PR is merged, publish EVERY artifact of the run —
    the mirror of the planning path's publish_artifacts_core (Bugs S.No 152).

    The build path had no publish step at all: merge_build_pr published only the single `code`
    artifact, so the Assumptions and Code Review artifacts stayed DRAFT forever even though their
    gate was approved. That was a gap, not a decision — nothing marks them un-publishable
    ("internal" is their SoR, not a lifecycle status, and the planning path publishes internal-SoR
    artifacts too).

    Only `status` changes: each artifact already carries its correct SoR from registration (code →
    git, review → internal), and overwriting that would clobber the PR pointer's sor=git.
    Idempotent — already-published artifacts are skipped, so Temporal retries/replays are safe."""
    store = get_object_store()
    with tenant_context(inp.tenant_id):
        artifacts = list(Artifact.objects.filter(run_id=inp.run_id, tenant_id=inp.tenant_id))

    published: list[str] = []
    for artifact in artifacts:
        if artifact.status == Artifact.Status.PUBLISHED:
            published.append(str(artifact.id))
            continue
        if artifact.s3_key:      # immutable audit snapshot, as on the planning path
            snap = (
                f"snapshots/{inp.tenant_id}/{inp.project_id}/{inp.run_id}/"
                f"{artifact.phase}.v{artifact.version}.md"
            )
            store.copy(artifact.s3_key, snap)
        tools.update_artifact(inp.tenant_id, str(artifact.id),
                              status=Artifact.Status.PUBLISHED)
        published.append(str(artifact.id))

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.COMPLETED
        run.save(update_fields=["status", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "artifacts.published", "run", inp.run_id,
                        {"artifact_ids": published})
    return {"published": published}


def transition_build_work_item_core(inp: BuildInput, to_state: str) -> dict:
    with tenant_context(inp.tenant_id):
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, to_state)
        tools.log_event(inp.tenant_id, "orchestrator", "workitem.transitioned", "work_item",
                        inp.work_item_id, {"to_state": to_state})
    return {"work_item_id": inp.work_item_id, "state": to_state}


def mark_takeover_core(inp: BuildInput) -> dict:
    """Offline-runner path (PG10): the companion never reported → park the WorkItem for human
    takeover and flag the run failed (never silently hang)."""
    with tenant_context(inp.tenant_id):
        WorkItem.objects.filter(id=inp.work_item_id, tenant_id=inp.tenant_id).update(
            takeover_flag=True
        )
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.FAILED
        )
        tools.log_event(inp.tenant_id, "orchestrator", "build.takeover", "run", inp.run_id,
                        {"reason": "runner offline / no report before timeout"})
    return {"status": "takeover"}


def classify_build_failure(reason: str) -> str:
    """Map a raw failure reason / exception string to a single plain-language, classified reason
    (Bugs S.No 139). The build.failed reason was populated inconsistently across paths — a bare
    'build reported failed', a hardcoded 'remediation cycles exhausted', or a raw Temporal
    exception string ('merge failed: ActivityError...'). This normalizes them so the user sees
    *why* it failed. An already-good, specific message (e.g. the S.No 130 secret-scan message)
    passes through unchanged; an unrecognized specific message is kept, never lost."""
    r = (reason or "").lower()
    if "secret scan" in r or "secret_blocked" in r:
        return reason  # already a classified, redacted message (S.No 130) — keep it
    # Engine (Claude Code) failures — Bugs S.No 146. Checked before the merge/permission paths
    # (different signatures). The usage/rate-limit case is the most common and is transient: the
    # engine's stderr tail (now captured by the driver) carries the notice.
    if ("usage limit" in r or "usage_limit" in r or "rate limit" in r or "rate-limit" in r
            or "429" in r or "too many requests" in r or "overloaded" in r or "quota" in r):
        return ("The AI engine hit its usage or rate limit, so the build could not finish. "
                "Wait for the limit to reset, then retry the build (no rebuild of earlier work "
                "is needed once resume lands).")
    if ("failed to start claude code" in r or "claude code not found" in r
            or "open_process()" in r):
        return ("The AI engine (Claude Code) could not start on the companion — check the engine "
                "install and dependencies on the dev machine, then retry.")
    if ("merge conflict" in r or "mergeable_state" in r or "dirty" in r
            or "-> 405" in r or " 405 " in r or "merge_conflict" in r):
        return ("Merge conflict: the branch conflicts with its base and needs manual "
                "resolution before it can be merged.")
    if "-> 403" in r or " 403 " in r or "permission" in r or "forbidden" in r:
        return ("Permission denied: the GitHub token lacks access, or a branch protection "
                "rule blocked the action.")
    if "remediation cycles exhausted" in r:
        return ("Remediation exhausted: code review kept finding blocking issues after the "
                "maximum retry cycles.")
    if "no changes" in r or "empty build" in r or "nothing to commit" in r:
        return "Empty build: the agent produced no changes to commit."
    # Generic engine exit (Bugs S.No 146) — kept after the specific usage-limit/launch checks so a
    # bare non-zero exit still reads clearly instead of as a raw "Command failed with exit code 1".
    if ("exit code" in r or "command failed" in r or "processerror" in r
            or "engine stderr" in r):
        return ("The AI engine exited with an error before finishing the build. The most common "
                "cause is a usage/rate limit; check the companion terminal for the engine output, "
                "then retry.")
    if r.strip() in ("", "build reported failed", "remediation build failed"):
        return "The build agent failed without reporting a specific reason."
    return reason  # a specific message we don't need to reclassify


def mark_build_failed_core(inp: BuildInput, reason: str) -> dict:
    """Dead-letter / failed-build compensation: flag the run failed, return the WorkItem to
    in_progress (the branch/draft PR are left for human disposition — register-don't-recreate).
    The reason is classified (S.No 139) and stored on `run.outputs.error` — where the run
    console reads the failure line — as well as the build.failed event payload."""
    reason = classify_build_failure(reason)
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.FAILED
        run.outputs = {**(run.outputs or {}), "error": reason}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        tools.log_event(inp.tenant_id, "orchestrator", "build.failed", "run", inp.run_id,
                        {"reason": reason})
    return {"status": "build_failed", "reason": reason}


def handle_remediation_exhausted_core(inp: BuildInput) -> dict:
    """Bugs S.No 161: remediation exhausting its cycles used to be a dead end — hard-fail, no
    diagnostics, no recourse; the only path forward was a blind re-trigger with a brand-new
    agent context and zero memory of what went wrong. This is inconsistent with how every OTHER
    recoverable failure in this workflow behaves (merge conflicts re-open the gate, other merge
    errors park) — remediation-exhaustion was the one path with no second chance.

    Two-tier response, both reusing existing patterns instead of inventing new ones:
    1. Auto-retry (attempt < max_auto_attempts): mark this run terminally failed, then start a
       FRESH run/workflow for the same WorkItem — new agent context, no compounding bad
       decisions — seeded with a readable digest of what blocked the last attempt (from the
       `review_cycles` this loop persisted). Still fully automated: no human involved.
    2. Auto-retries exhausted too: park (the same `park_build` used for merge errors) so a human
       is the LAST resort, not the first response to one failed review cycle.
    """
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        cycles = (run.outputs or {}).get("review_cycles", [])
    last_blocking = cycles[-1]["blocking"] if cycles else []
    if last_blocking:
        findings_summary = "\n".join(
            f"- [{f.get('severity', '?')}] {f.get('title') or f.get('rem', '')} "
            f"({f.get('file', '?')}:{f.get('line', '?')})"
            for f in last_blocking
        )
    else:
        findings_summary = "(no finding detail was captured for the last review cycle)"

    if inp.attempt < inp.max_auto_attempts:
        from .trigger import trigger_build

        prior_context = (
            (f"{inp.prior_attempt_context}\n\n" if inp.prior_attempt_context else "")
            + f"Attempt {inp.attempt} failed code review after {inp.max_remediation_cycles} "
              f"remediation cycles. Blocking findings on the last cycle:\n{findings_summary}\n"
              "Avoid repeating these specific issues."
        )
        with tenant_context(inp.tenant_id):
            run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
            triggered_by_id = str(run.triggered_by_id) if run.triggered_by_id else None
            run.status = Run.Status.FAILED
            run.outputs = {
                **(run.outputs or {}),
                "error": (f"Remediation exhausted on attempt {inp.attempt}/"
                          f"{inp.max_auto_attempts} — auto-retrying with a fresh agent attempt."),
            }
            run.save(update_fields=["status", "outputs", "updated_at"])
            tools.log_event(inp.tenant_id, "orchestrator", "build.remediation_exhausted_retry",
                            "run", inp.run_id, {"attempt": inp.attempt, "next_attempt": inp.attempt + 1})
        # Carry the original trigger's user forward so the retry resolves the SAME companion
        # (req #1) instead of dispatching with a null enrollment. A null-enrollment retry was the
        # main way a build got stuck RUNNING+unclaimable (the broadcast-claim fix in
        # RunnerWorkClaimView now recovers it either way, but a routed retry is the correct path).
        result = trigger_build(
            tenant_id=inp.tenant_id, project_id=inp.project_id, work_item_id=inp.work_item_id,
            repo=inp.repo, base=inp.base, work_item_key=inp.work_item_key,
            required_role=inp.required_role, triggered_by=triggered_by_id,
            attempt=inp.attempt + 1, prior_attempt_context=prior_context,
        )
        with tenant_context(inp.tenant_id):
            run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
            run.outputs = {**(run.outputs or {}), "retry_run_id": result.run_id}
            run.save(update_fields=["outputs", "updated_at"])
        return {"action": "retried", "retry_run_id": result.run_id}

    reason = (f"remediation cycles exhausted after {inp.max_auto_attempts} auto-retried "
              f"attempts — blocking findings on the last cycle:\n{findings_summary}")
    return {"action": "park", "reason": reason}


def park_build_core(inp: BuildInput, reason: str, resume_from: str) -> dict:
    """Bugs S.No 157: an error mid-build PARKS the run instead of killing it. Previously any such
    error ran mark_build_failed and RETURNED, which closes the Temporal history for good — a closed
    workflow cannot be signalled, so the only way forward was a brand-new run that rebuilt
    everything from step 1. Parking marks the run STALLED (non-terminal, exactly like the S.No 89
    report-timeout park) and records a classified reason + the step to resume from, while the
    workflow stays ALIVE waiting for `resume_run` or `abandon_run`.

    The WorkItem is deliberately NOT transitioned: it is already in_progress, which stays true for
    a paused build (mark_build_failed's transition belongs to the terminal path — the abandon
    branch still runs it). Idempotent: parking an already-parked run rewrites the same fields."""
    reason = classify_build_failure(reason)
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.STALLED
        run.outputs = {**(run.outputs or {}), "error": reason,
                       "resume_from": resume_from, "resumable": True}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.parked", "run", inp.run_id,
                        {"reason": reason, "resume_from": resume_from, "resumable": True})
    return {"status": "parked", "reason": reason, "resume_from": resume_from}


def resume_build_core(inp: BuildInput) -> dict:
    """Bugs S.No 157: a human resumed a parked build — un-park it (back to RUNNING) and clear the
    park markers so the console stops showing a stale failure. Idempotent."""
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        outputs = {**(run.outputs or {})}
        resume_from = outputs.get("resume_from", "")
        for key in ("error", "resume_from", "resumable"):
            outputs.pop(key, None)
        run.status = Run.Status.RUNNING
        run.outputs = outputs
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.resumed", "run", inp.run_id,
                        {"resume_from": resume_from})
    return {"status": "resumed", "resume_from": resume_from}


def reject_build_core(inp: BuildInput, comment: str) -> dict:
    with tenant_context(inp.tenant_id):
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.REJECTED
        )
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        tools.log_event(inp.tenant_id, "orchestrator", "build.rejected", "run", inp.run_id,
                        {"comment": comment})
    return {"status": "rejected"}


# ── code review + remediation loop (07<->08, build phases §5) ───────
@dataclass
class Finding:
    """One code-review finding. REM-C/REM-W are blocking (become remediation child
    WorkItems); REM-S (suggestion) is non-blocking and excluded from the loop."""

    rem: str                 # "REM-C1" | "REM-W1" | "REM-S1"
    severity: str            # "critical" | "warning" | "suggestion"
    title: str = ""
    file: str = ""
    line: int = 0
    # What the review actually SAID (Bugs S.No 147). Without these the remediation WorkItem is a
    # bare title with an empty body: the reviewer explains the problem and the fix, and the
    # platform used to drop both on the floor, so the board read as terse and un-actionable.
    problem: str = ""        # what is wrong, and why it matters
    fix: str = ""            # what to do about it
    category: str = ""       # which review dimension raised it (e.g. "security")


_SEVERITY_LEAD = {
    "critical": "This must be fixed before the code can merge.",
    "warning": "This should be fixed before the code can merge.",
    "suggestion": "Worth improving, but it is not blocking the merge.",
}


def _remediation_description(finding: Finding) -> str:
    """Compose the remediation WorkItem's body from what the review actually said (Bugs S.No 147).

    Remediation items read as terse and machine-generated because the platform created them with a
    title and NO description at all — every word of the reviewer's explanation was discarded before
    it got here. The reader is a developer, so this keeps the technical nuance (file:line, severity,
    dimension) but leads with plain language: what's wrong, why it matters, what to do."""
    parts: list[str] = [_SEVERITY_LEAD.get(finding.severity, "")]
    if finding.problem:
        parts.append(f"**What's wrong**\n\n{finding.problem}")
    if finding.fix:
        parts.append(f"**What to do**\n\n{finding.fix}")

    where = []
    if finding.file:
        where.append(f"`{finding.file}`" + (f" line {finding.line}" if finding.line else ""))
    if finding.category:
        where.append(f"raised by the **{finding.category}** review check")
    where.append(f"severity **{finding.severity}** (`{finding.rem}`)")
    parts.append("**Where**\n\n" + " · ".join(where))

    if not finding.problem and not finding.fix:
        # The reviewer gave only a title — say so plainly rather than implying a fuller brief.
        parts.append("_The code review did not provide further detail — open the Code Review "
                     "artifact for the full context._")
    return "\n\n".join(p for p in parts if p)


class _NoFindingsReviewProvider:
    """Default reviewer until agent 08 is migrated (§8): finds nothing, so the loop passes
    straight to the merge gate. The real 08 review (eleven dimensions, REM classification)
    plugs in here via `set_review_provider` — the loop machinery does not change."""

    def review(self, inp: BuildInput, pr_ref: str) -> list:
        return []


_REVIEW_PROVIDER = _NoFindingsReviewProvider()


def get_review_provider():
    return _REVIEW_PROVIDER


def set_review_provider(provider) -> None:
    """Wire the reviewer (the migrated 08 agent in §8; a scripted stub in tests)."""
    global _REVIEW_PROVIDER
    _REVIEW_PROVIDER = provider


_BLOCKING = {"critical", "warning"}


def run_code_review_core(inp: BuildInput) -> dict:
    """Review the PR (08), record a `code_review` artifact, and reconcile **remediation
    child WorkItems** (one per REM-C/REM-W): open new findings, close resolved ones. Returns
    the count of open blocking findings — the loop continues while it is > 0."""
    code = _code_artifact(inp)
    if code is None or not _is_pr_ref(code.external_ref):
        raise RuntimeError(f"no opened PR to review for run {inp.run_id}")
    pr_ref = f"{code.external_ref['repo']}#{code.external_ref['number']}"

    findings = list(get_review_provider().review(inp, pr_ref))
    blocking = {f.rem: f for f in findings if f.severity in _BLOCKING}
    digest = hashlib.sha256(
        json.dumps([asdict(f) for f in findings], sort_keys=True).encode()
    ).hexdigest()

    with tenant_context(inp.tenant_id):
        review_art = Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id, type="code_review").first()
    if review_art is None:
        created = tools.register_artifact(
            inp.tenant_id, inp.project_id, inp.run_id, inp.phase, "code_review", "internal",
            content_hash=digest, title=f"Code Review — {display_name(inp)}")
        review_art_id = created["id"]
        tools.add_trace_edge(inp.tenant_id, review_art_id, str(code.id), "tests")
    else:
        tools.update_artifact(inp.tenant_id, str(review_art.id), content_hash=digest)
        review_art_id = str(review_art.id)

    with tenant_context(inp.tenant_id):
        story = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        children = WorkItem.objects.filter(
            tenant_id=inp.tenant_id, parent_id=inp.work_item_id, type=WorkItem.Type.TASK)
        existing = {(c.external_ref or {}).get("rem"): c for c in children
                    if (c.external_ref or {}).get("rem")}
        # Close remediation items whose finding is gone (resolved by the last build).
        for rem, child in existing.items():
            if rem not in blocking and child.state != WorkItem.State.DONE:
                child.state = WorkItem.State.DONE
                child.save(update_fields=["state", "updated_at"])
                tools.log_event(inp.tenant_id, "code_review", "remediation.resolved",
                                "work_item", str(child.id), {"rem": rem})
        # Open (or reopen) a child WorkItem for each current blocking finding.
        for rem, finding in blocking.items():
            child = existing.get(rem)
            if child is None:
                child = WorkItem.objects.create(
                    tenant_id=inp.tenant_id, project_id=inp.project_id,
                    type=WorkItem.Type.TASK, parent=story, title=finding.title or rem,
                    # A real, readable brief — not a bare title (Bugs S.No 147).
                    description=_remediation_description(finding),
                    state=WorkItem.State.IN_PROGRESS,
                    external_ref={"rem": rem, "severity": finding.severity,
                                  "file": finding.file, "line": finding.line},
                )
                tools.log_event(inp.tenant_id, "code_review", "remediation.opened",
                                "work_item", str(child.id),
                                {"rem": rem, "severity": finding.severity})
            elif child.state == WorkItem.State.DONE:
                child.state = WorkItem.State.IN_PROGRESS
                child.save(update_fields=["state", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.reviewed", "run", inp.run_id,
                        {"findings": len(findings), "blocking": len(blocking)})
        # Bugs S.No 161: persist the actual blocking-finding text (not just counts) so a
        # remediation-exhausted build has real diagnostic content to seed its auto-retry with,
        # instead of the counts-only history the run console showed before (2 -> 1 -> 3 -> 3
        # blocking with zero visibility into what those findings actually were).
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        cycles = list((run.outputs or {}).get("review_cycles", []))
        cycles.append({
            "blocking": [
                {"rem": f.rem, "severity": f.severity, "title": f.title,
                 "file": f.file, "line": f.line}
                for f in blocking.values()
            ],
            "blocking_count": len(blocking), "findings_count": len(findings),
        })
        run.outputs = {**(run.outputs or {}), "review_cycles": cycles}
        run.save(update_fields=["outputs", "updated_at"])
    return {"open_blocking": len(blocking), "findings": len(findings),
            "review_artifact_id": review_art_id}


def _render_remediation_section(brief: list[dict]) -> str:
    """Render the open REM findings as a manifest section the 07 agent re-runs against — same
    idea as the reviewer's PR-diff section. The agent fixes these on the SAME branch."""
    lines = ["# Remediation Items",
             "The code review returned blocking findings. Address EACH of the following on the "
             "current branch (do not open a new PR — push fixes to the existing one), then report:",
             ""]
    for f in brief:
        loc = f"{f.get('file') or '?'}:{f.get('line') or 0}"
        lines.append(f"- **{f.get('rem')}** ({f.get('severity')}) — {f.get('title')}  [{loc}]")
        # Include the reviewer's problem/fix detail, indented under its item (Bugs S.No 147) —
        # 07 was previously asked to fix each finding from its one-line title alone.
        for detail in (f.get("description") or "").splitlines():
            lines.append(f"  {detail}" if detail.strip() else "")
    return "\n".join(lines)


def dispatch_remediation_core(inp: BuildInput) -> dict:
    """Re-dispatch the build to the companion in remediation mode: the open REM brief is folded
    into the 07 agent's manifest and a fresh `build_task` + pending `dispatch` claim block are
    armed so the companion pulls it via /api/runner/work/ (exactly like the initial build), runs
    07 against the findings on the SAME branch, and reports back. Without re-arming `dispatch`
    the companion would have nothing to claim and the loop would hang → takeover (Bugs S.No 115).
    Idempotent by run_id."""
    from django.conf import settings

    with tenant_context(inp.tenant_id):
        open_items = WorkItem.objects.filter(
            tenant_id=inp.tenant_id, parent_id=inp.work_item_id, type=WorkItem.Type.TASK,
            state=WorkItem.State.IN_PROGRESS)
        brief = [{"rem": (c.external_ref or {}).get("rem"), "title": c.title,
                  "severity": (c.external_ref or {}).get("severity"),
                  "file": (c.external_ref or {}).get("file"),
                  "line": (c.external_ref or {}).get("line"),
                  # The reviewer's own explanation (Bugs S.No 147) — agent 07 was being asked to
                  # fix findings from a one-line title, with the problem/fix detail discarded.
                  "description": c.description or ""} for c in open_items]

    manifest = f"{compose_manifest_core(inp)}\n\n{_render_remediation_section(brief)}"
    agent_body, model = _load_agent_body(inp.agent_spec_id, inp.tenant_id)
    payload = {
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "work_item_key": inp.work_item_key,
        "repo": inp.repo, "base": inp.base, "phase": inp.phase,
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
        "remediation": True,
    }
    # A 09b remediation re-runs the test-automation agent, which brings the app up again — so it
    # needs the same preview target as the initial dispatch. Without this the fix-build fails loud
    # with "no preview target for this repo". Phase-gated exactly like dispatch_build (07/11 never
    # carry it).
    if inp.phase == "test_automation":
        from apps.projects.preview_config import resolve_preview_start, resolve_preview_url

        payload["preview_url"] = resolve_preview_url(
            tenant_id=inp.tenant_id, project_id=inp.project_id, repo_name=inp.repo)
        payload["preview_start"] = resolve_preview_start(
            tenant_id=inp.tenant_id, project_id=inp.project_id, repo_name=inp.repo)
    with tenant_context(inp.tenant_id):
        wi = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        payload["work_item_title"] = wi.title
        payload["work_item_type"] = wi.type
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.inputs = {
            **(run.inputs or {}),
            "remediation": {"items": brief},
            "build_task": payload,
            # Re-arm the claim block so the companion can pull the remediation build (S.No 115).
            "dispatch": {"kind": "build", "enrollment_id": inp.enrollment_id,
                         "status": "pending"},
        }
        run.status = Run.Status.RUNNING
        run.save(update_fields=["inputs", "status", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.remediation_dispatched", "run",
                        inp.run_id, {"items": len(brief)})
    return {"dispatched": True, "items": len(brief)}


def dispatch_reviewer_revision_core(inp: BuildInput, direction: str) -> dict:
    """"Request changes" on the MERGE gate: re-dispatch the build with the reviewer's written
    direction folded into 07's manifest.

    Unlike the planning path this does NOT start a new run. At the merge gate the branch is pushed
    and the draft PR is open; a fresh build would cut a second branch, open a second PR and orphan
    the first (nothing closes it). So the revision rides the SAME run, branch and PR — the shape
    `dispatch_remediation_core` already established for review findings.

    The review conversation accumulates on this one run's `Run.inputs["review_history"]`, and it is
    written HERE, before the Approval is reset — reopening the gate lets the next decision
    overwrite `Approval.comment`, so the reviewer's earlier words would otherwise be lost.
    """
    from django.conf import settings

    from manifest.composer import TokenBudget, _render_review_direction

    from .activities import build_review_round

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        history = list((run.inputs or {}).get("review_history") or [])
    entry = build_review_round(inp.tenant_id, inp.run_id, direction)
    entry["revision"] = len(history) + 1
    history = history + [entry]

    # Same renderer the planning path uses, so a reviewer's direction reads identically to an
    # agent whichever workflow it arrives through.
    manifest = (f"{compose_manifest_core(inp)}\n\n"
                f"{_render_review_direction(history, TokenBudget())}")
    agent_body, model = _load_agent_body(inp.agent_spec_id, inp.tenant_id)
    payload = {
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "work_item_key": inp.work_item_key,
        "repo": inp.repo, "base": inp.base, "phase": inp.phase,
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
        "remediation": True,        # same shape as a remediation build: same branch, no re-clone
    }
    if inp.phase == "test_automation":
        from apps.projects.preview_config import resolve_preview_start, resolve_preview_url

        payload["preview_url"] = resolve_preview_url(
            tenant_id=inp.tenant_id, project_id=inp.project_id, repo_name=inp.repo)
        payload["preview_start"] = resolve_preview_start(
            tenant_id=inp.tenant_id, project_id=inp.project_id, repo_name=inp.repo)
    with tenant_context(inp.tenant_id):
        wi = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        payload["work_item_title"] = wi.title
        payload["work_item_type"] = wi.type
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.inputs = {
            **(run.inputs or {}),
            "review_history": history,
            "build_task": payload,
            # Re-arm the claim block or the companion has nothing to pull and the loop hangs
            # until takeover (the S.No 115 failure).
            "dispatch": {"kind": "build", "enrollment_id": inp.enrollment_id,
                         "status": "pending"},
        }
        run.status = Run.Status.RUNNING
        run.save(update_fields=["inputs", "status", "updated_at"])
        # Reset the gate to PENDING now. `open_merge_gate` is get_or_create and will NOT reset a
        # decided Approval, so without this the reviewer's next decision is refused with
        # "approval already decided" and they are locked out of their own gate for good.
        Approval.objects.filter(
            run_id=inp.run_id, gate_type=inp.gate_type, tenant_id=inp.tenant_id,
        ).update(decision=Approval.Decision.PENDING, approver=None, decided_at=None)
        tools.log_event(inp.tenant_id, "orchestrator", "build.revision_dispatched", "run",
                        inp.run_id, {"revision": entry["revision"]})
    return {"dispatched": True, "revision": entry["revision"]}


# ── activity wrappers (close the DB connection at the boundary) ─────
@activity.defn(name="dispatch_build")
def dispatch_build_activity(inp: BuildInput) -> dict:
    return _boundary(dispatch_build_core, inp)


@activity.defn(name="open_build_pr")
def open_build_pr_activity(inp: BuildInput, report: BuildReport) -> dict:
    return _boundary(open_build_pr_core, inp, report)


@activity.defn(name="import_build_test_results")
def import_build_test_results_activity(inp: BuildInput, report: BuildReport) -> dict:
    return _boundary(import_build_test_results_core, inp, report)


@activity.defn(name="provision_preview")
def provision_preview_activity(inp: BuildInput, report: BuildReport) -> dict:
    return _boundary(provision_preview_core, inp, report)


@activity.defn(name="teardown_preview")
def teardown_preview_activity(inp: BuildInput) -> dict:
    return _boundary(teardown_preview_core, inp)


@activity.defn(name="open_merge_gate")
def open_merge_gate_activity(inp: BuildInput) -> str:
    return _boundary(open_merge_gate_core, inp)


@activity.defn(name="run_code_review")
def run_code_review_activity(inp: BuildInput) -> dict:
    return _boundary(run_code_review_core, inp)


@activity.defn(name="dispatch_remediation")
def dispatch_remediation_activity(inp: BuildInput) -> dict:
    return _boundary(dispatch_remediation_core, inp)


@activity.defn(name="dispatch_reviewer_revision")
def dispatch_reviewer_revision_activity(inp: BuildInput, direction: str) -> dict:
    return _boundary(dispatch_reviewer_revision_core, inp, direction)


@activity.defn(name="merge_build_pr")
def merge_build_pr_activity(inp: BuildInput) -> dict:
    return _boundary(merge_build_pr_core, inp)


@activity.defn(name="transition_build_work_item")
def transition_build_work_item_activity(inp: BuildInput, to_state: str) -> dict:
    return _boundary(transition_build_work_item_core, inp, to_state)


@activity.defn(name="mark_takeover")
def mark_takeover_activity(inp: BuildInput) -> dict:
    return _boundary(mark_takeover_core, inp)


@activity.defn(name="mark_build_failed")
def mark_build_failed_activity(inp: BuildInput, reason: str) -> dict:
    return _boundary(mark_build_failed_core, inp, reason)


@activity.defn(name="handle_remediation_exhausted")
def handle_remediation_exhausted_activity(inp: BuildInput) -> dict:
    return _boundary(handle_remediation_exhausted_core, inp)


@activity.defn(name="reject_build")
def reject_build_activity(inp: BuildInput, comment: str) -> dict:
    return _boundary(reject_build_core, inp, comment)


@activity.defn(name="reopen_merge_gate")
def reopen_merge_gate_activity(inp: BuildInput, reason: str) -> dict:
    return _boundary(reopen_merge_gate_core, inp, reason)


@activity.defn(name="publish_build_artifacts")
def publish_build_artifacts_activity(inp: BuildInput) -> dict:
    return _boundary(publish_build_artifacts_core, inp)


@activity.defn(name="park_build")
def park_build_activity(inp: BuildInput, reason: str, resume_from: str) -> dict:
    return _boundary(park_build_core, inp, reason, resume_from)


@activity.defn(name="resume_build")
def resume_build_activity(inp: BuildInput) -> dict:
    return _boundary(resume_build_core, inp)


BUILD_ACTIVITIES = [
    dispatch_build_activity,
    open_build_pr_activity,
    import_build_test_results_activity,
    provision_preview_activity,
    teardown_preview_activity,
    run_code_review_activity,
    dispatch_remediation_activity,
    dispatch_reviewer_revision_activity,
    open_merge_gate_activity,
    merge_build_pr_activity,
    transition_build_work_item_activity,
    mark_takeover_activity,
    mark_build_failed_activity,
    handle_remediation_exhausted_activity,
    reject_build_activity,
    reopen_merge_gate_activity,
    publish_build_artifacts_activity,
    park_build_activity,
    resume_build_activity,
]


# Convenience for the report path (used by the report service when building the signal).
def report_to_dict(report: BuildReport) -> dict:
    return asdict(report)
