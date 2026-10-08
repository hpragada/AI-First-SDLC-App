"""BuildWorkflow activities (Phase-2 §4). Each is a thin @activity.defn over an idempotent
*core* (idempotent by run_id so Temporal retries are safe). Side effects only here, never in
the workflow. CodeHost goes through the capability seam (`get_capability`); the engine never
touches Git — the platform opens/merges the PR (D2).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from mcp_platform_state import tools
from temporalio import activity
from temporalio.exceptions import ApplicationError

from apps.gates.models import Approval
from apps.registry.models import Artifact
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .activities import _boundary, _now, compose_manifest_core, get_object_store
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


#: The commit check the platform owns on a build's head commit. `open_build_pr_core` sets it to
#: `pending`; every path that ENDS a build moves it to a terminal state via `_finish_build_status`.
_BUILD_STATUS_CONTEXT = "sdlc/build"
#: GitHub truncates a commit-status description past 140 characters.
_MAX_STATUS_DESCRIPTION = 140


def _build_head_sha(inp: BuildInput) -> str:
    """The commit this build's check hangs off, or "" when no commit exists.

    `open_build_pr_core` has `report.head_sha` in hand; none of the terminal paths do, so recover
    it the way the merge path recovers the PR ref — from the run's `code` artifact, which carries
    the sha in its PR ref and again in `content_hash`. Empty when nothing was ever pushed (a
    secret-blocked build, or a failure before the PR was opened): there is no commit to mark, and
    posting is correctly skipped rather than guessed at."""
    try:
        artifact = _code_artifact(inp)
    except Exception:      # noqa: BLE001 — status reporting never fails a build
        return ""
    if artifact is None:
        return ""
    return str((artifact.external_ref or {}).get("sha") or artifact.content_hash or "")


def _finish_build_status(inp: BuildInput, state: str, description: str) -> None:
    """Move `sdlc/build` off `pending` on a path that ends the build (Bugs S.No 132).

    Nothing used to finish this check: it was posted as `pending` when the PR opened and left
    there forever. Cosmetic while the check is optional — and a permanent block on EVERY merge the
    moment anyone makes it required on GitHub, because it could never reach green.

    Best-effort in the same shape as the `pending` post: a status that cannot be written must never
    fail a build that otherwise succeeded."""
    sha = _build_head_sha(inp)
    if not sha:
        return
    from integrations.registry import get_capability

    try:
        codehost = get_capability(inp.tenant_id, "codehost")
        codehost.set_commit_status(
            repo=inp.repo, sha=sha, state=state, context=_BUILD_STATUS_CONTEXT,
            description=description[:_MAX_STATUS_DESCRIPTION],
        )
    except Exception:      # noqa: BLE001 — status is best-effort
        pass


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


def run_a11y_ai_pass_core(inp: BuildInput) -> dict:
    """Ask the AI accessibility checks about what this build's suite captured (QA-12).

    The join point of the whole accessibility feature: the companion posted the captured screens
    straight to the platform during the build (QA-11b), and this is where they are handed to the
    judge. The merged report — rule findings and AI findings in one document — is published when
    the judgment run ends, not here, because its verdicts are still in flight.

    Three bounds, the first two copied deliberately from `import_build_test_results_core` so the
    accessibility pass runs exactly where the test loop runs and nowhere else:
      - **Only phases the catalog marks `imports_test_results`** (09b today). A 07 implementation
        build captures nothing and must not start a judgment run.
      - **Nothing captured ⇒ no-op.** `start_ai_pass` returns without dispatching, so a build
        that ran no accessibility case never starts an empty judgment.
      - **Never fails the build.** `start_ai_pass` swallows its own failures, and the workflow
        calls this best-effort besides. The capture is already stored; the pass can be run again
        against the same run without re-capturing a thing.
    """
    from apps.a11y.aipass import start_ai_pass
    from apps.registry.catalog import imports_test_results as _phase_imports
    from apps.registry.models import AgentSpec

    with tenant_context(inp.tenant_id):
        spec = AgentSpec.objects.filter(id=inp.agent_spec_id, tenant_id=inp.tenant_id).first()
    agent_key = spec.key if spec else ""
    if not _phase_imports(agent_key):
        return {"started": False, "reason": f"phase {agent_key!r} does not run accessibility "
                                            f"checks"}

    return start_ai_pass(
        tenant_id=inp.tenant_id, project_id=inp.project_id, run_id=inp.run_id,
        work_item_id=inp.work_item_id, title=inp.work_item_title or inp.work_item_key,
    )


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


def _link_stray_code_pointers(inp: BuildInput, pr_ref: dict | None) -> int:
    """Give every OTHER `code` pointer on this run the PR's url, so none of them previews blank.

    Each remediation cycle makes the implementation agent register a fresh pre-PR pointer. The
    first build's pointer gets reconciled (below), but by the second cycle a real PR row already
    exists, `open_build_pr_core` returns early as idempotent, and the new pointer is orphaned at
    birth — 21 such rows across 14 runs on the QA tenant. They are honest provenance of what that
    cycle changed, so they are kept, but with no `url` the preview page renders empty.

    Attaches **`url` only** — deliberately NOT `repo`/`number`. `_is_pr_ref` requires both, so
    these rows stay non-PR-refs and `_code_artifact`'s "prefer the row with a real PR ref"
    selection is completely unaffected. Adding the full ref would make several rows look like the
    opened PR and let the wrong one drive review/merge.

    Returns how many rows were linked (0 on the common path). Never raises: this is a cosmetic
    repair and must not fail a build that has a working PR.
    """
    url = (pr_ref or {}).get("url")
    if not url:
        return 0
    linked = 0
    try:
        with tenant_context(inp.tenant_id):
            strays = list(Artifact.objects.filter(
                run_id=inp.run_id, tenant_id=inp.tenant_id, type="code"))
        for art in strays:
            ref = art.external_ref or {}
            if _is_pr_ref(ref) or ref.get("url"):
                continue
            tools.update_artifact(inp.tenant_id, str(art.id),
                                  external_ref={**ref, "sor": "git", "url": url})
            linked += 1
    except Exception:      # noqa: BLE001 — provenance polish, never a build failure
        return linked
    return linked


def open_build_pr_core(inp: BuildInput, report: BuildReport) -> dict:
    """Open the draft PR for the companion-pushed branch and register/reconcile the `code`
    pointer. Idempotent — only an artifact that already carries a real PR ref (repo+number) is
    reused. The agent's pre-PR pointer is *reconciled* (updated with the PR), not skipped."""
    from integrations.registry import get_capability
    from integrations.types import CapabilityError

    existing = _code_artifact(inp)
    if existing is not None and _is_pr_ref(existing.external_ref):
        _link_stray_code_pointers(inp, existing.external_ref)
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
                                       context=_BUILD_STATUS_CONTEXT,
                                       description="Build in progress.")
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
    _finish_build_status(inp, "success", "Build merged.")
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
    _finish_build_status(inp, "failure", "The platform stopped this build and handed it to a "
                                         "person.")
    return {"status": "takeover"}


# Where the companion writes the engine's own output (runner/companion/enginelog.py). Named in
# the failure reason so "check the companion terminal" is never again the only pointer we can give.
_ENGINE_LOG_NAME = "companion-engine.log"
#: Claude Code announces a usage limit as `Claude AI usage limit reached|<unix-epoch>` — the epoch
#: is when it resets, which is exactly what a human needs and what we used to throw away.
_USAGE_RESET = re.compile(r"usage limit reached\s*\|\s*(\d{9,11})", re.IGNORECASE)
_EXIT_CODE = re.compile(r"exit code:?\s*(\d+)", re.IGNORECASE)
#: The engine's captured output, appended by `ClaudeDriver._with_stderr_tail` / `_with_progress`.
_ENGINE_DETAIL_MARKERS = ("Engine output (tail):", "Engine stderr (tail):",
                          "Engine progress before the failure:")
_MAX_ENGINE_DETAIL = 2000


def _usage_reset_hint(reason: str) -> str:
    """"Resets at 14:30 UTC." — or nothing when the notice carried no timestamp."""
    match = _USAGE_RESET.search(reason or "")
    if not match:
        return ""
    try:
        when = datetime.fromtimestamp(int(match.group(1)), tz=UTC)
    except (ValueError, OverflowError, OSError):
        return ""
    return f"It resets at {when:%Y-%m-%d %H:%M} UTC. "


def _exit_code_hint(reason: str) -> str:
    match = _EXIT_CODE.search(reason or "")
    return f" (exit code {match.group(1)})" if match else ""


def _engine_detail(reason: str) -> str:
    """The engine's own words out of the raw reason — the part worth showing a human.

    Falls back to the whole raw string rather than dropping it: an unrecognised shape is still
    better evidence than a sentence we invented."""
    text = reason or ""
    starts = [text.find(m) for m in _ENGINE_DETAIL_MARKERS]
    first = min((i for i in starts if i >= 0), default=-1)
    detail = (text[first:] if first >= 0 else text).strip()
    return detail[:_MAX_ENGINE_DETAIL] if detail else "(the engine produced no output)"


#: Internal prefixes the workflow puts on a reason to say WHICH step failed. They are for us -
#: the reader gets the step in words - so they are matched and stripped, never shown.
_STEP_PREFIXES = {
    "pr/gate setup failed:": "open",
    "merge failed:": "merge",
    "code review did not complete:": "review",
}
#: A clock-style reset from the engine's session notice: "resets 1:20am (Asia/Kolkata)".
_CLOCK_RESET = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2}(?::\d{2})?\s*[ap]m)(?:\s*\(([^)]+)\))?",
                          re.IGNORECASE)
#: What a build keeps when it pauses - said by the platform so the screen never guesses.
BUILD_KEPT = "the build, branch and pull request are kept"


@dataclass(frozen=True)
class FailureText:
    """A failure said two ways (run-console wording fix, 2026-09-21, option A).

    `sentence` is the banner: what stopped, why, and what to do. `cause` is the short phrase for a
    one-line log entry. Neither carries the raw engine output or an HTTP call - that is stored
    separately (`outputs.error_detail`) and shown under "Technical details", closed by default."""
    sentence: str
    cause: str


def _split_step(reason: str) -> tuple[str, str]:
    """(step, rest): the internal step prefix, if any, and the reason without it."""
    text = (reason or "").strip()
    for prefix, step in _STEP_PREFIXES.items():
        if text.lower().startswith(prefix):
            return step, text[len(prefix):].strip()
    return "", text


def _reset_hint(reason: str) -> str:
    """' (resets 1:20AM, Asia/Kolkata)' / ' (resets 2026-09-21 14:30 UTC)' - or nothing."""
    match = _USAGE_RESET.search(reason or "")
    if match:
        try:
            when = datetime.fromtimestamp(int(match.group(1)), tz=UTC)
            return f" (resets {when:%Y-%m-%d %H:%M} UTC)"
        except (ValueError, OverflowError, OSError):
            pass
    match = _CLOCK_RESET.search(reason or "")
    if match:
        clock = match.group(1).replace(" ", "").upper()
        clock = clock[:-2] + " " + clock[-2:]
        zone = f", {match.group(2)}" if match.group(2) else ""
        return f" (resets {clock}{zone})"
    return ""


def describe_build_failure(reason: str, *, subject: str = "", parked: bool = True,
                           what: str = "") -> FailureText:
    """Map a raw failure reason to what the reader is told (Bugs S.No 139, 146, 266).

    `subject` is "review" when the code REVIEW stopped and "build" otherwise; when omitted it is
    read from the workflow's step prefix. `what` names the thing that stopped for a caller
    that is not a build ("The PRD phase" — the agent-run path). `parked` says whether the run
    can be resumed - a failed
    run cannot, so it is never told to press Resume.

    What changed on 2026-09-21: the engine's raw output and HTTP calls used to be pasted into this
    sentence; a review that died was reported as a failed BUILD (and, on a usage limit, as a review
    that had "already completed"); a rejected GitHub token (401) and the engine's "session limit"
    notice were not recognised at all. The raw text is now kept apart by the caller."""
    step, rest = _split_step(reason)
    subject = subject or ("review" if step == "review" else "build")
    what = what or ("The code review" if subject == "review" else "The build")
    unreviewed = " The code has not been reviewed yet." if subject == "review" else ""
    again = ("Resume to run the review again." if subject == "review"
             else "Resume to carry on from the step that stopped.")
    # Padded so a status code matches at the very start or end too ("403 branch protection").
    r = f" {(rest or '').lower()} "

    if "secret scan" in r or "secret_blocked" in r:
        return FailureText(rest, "secret scan blocked the push")  # already redacted (S.No 130)
    if ("usage limit" in r or "usage_limit" in r or "session limit" in r or "rate limit" in r
            or "rate-limit" in r or "429" in r or "too many requests" in r or "overloaded" in r
            or "quota" in r or "hit your limit" in r):
        when = _reset_hint(rest)
        tail = ("Resume once the limit resets." if parked
                else "Start it again once the limit resets.")
        return FailureText(
            f"{what} stopped because the AI engine reached its usage limit{when}.{unreviewed} "
            f"{tail}", "the AI engine reached its usage limit")
    if ("failed to start claude code" in r or "claude code not found" in r
            or "open_process()" in r):
        return FailureText(
            f"{what} couldn't start because the AI engine didn't start on your machine. Check "
            "the AI engine is installed there, then " + ("Resume." if parked else "try again."),
            "the AI engine couldn't start")
    if "-> 401" in r or " 401 " in r or "unauthorized" in r:
        github = "github" in r
        host = "GitHub" if github else "The code host"
        where = {"merge": "the pull request couldn't be merged",
                 "open": "the pull request couldn't be opened"}.get(
                     step, "the platform couldn't reach the repository")
        tail = ", then Resume." if parked else ", then try again."
        return FailureText(
            f"{host} didn't accept the access token, so {where}. Ask your admin to reconnect "
            f"{'GitHub' if github else 'it'} in Integrations{tail}",
            f"{host} didn't accept the access token")
    if ("merge conflict" in r or "mergeable_state" in r or "dirty" in r
            or "-> 405" in r or " 405 " in r or "merge_conflict" in r):
        return FailureText("Merge conflict: the branch conflicts with its base and needs manual "
                           "resolution before it can be merged.", "merge conflict")
    if "-> 403" in r or " 403 " in r or "permission" in r or "forbidden" in r:
        return FailureText("Permission denied: the GitHub token lacks access, or a branch "
                           "protection rule blocked the action.", "permission denied")
    if "remediation cycles exhausted" in r:
        return FailureText("Remediation exhausted: code review kept finding blocking issues "
                           "after the maximum retry cycles.",
                           "code review kept finding blocking issues")
    if "no changes" in r or "empty build" in r or "nothing to commit" in r:
        return FailureText("Empty build: the agent produced no changes to commit.",
                           "no changes to commit")
    # Generic engine exit (S.No 146) - only what is known; the engine's own words are under
    # "Technical details", never guessed at here.
    if ("exit code" in r or "command failed" in r or "processerror" in r
            or "engine stderr" in r or "engine output" in r):
        tail = f"{unreviewed} {again}" if parked else unreviewed
        return FailureText(
            f"{what} stopped because the AI engine closed before it finished.{tail}".rstrip(),
            "the AI engine closed before it finished")
    if subject == "review" and (not r.strip() or "reported no reason" in r):
        tail = f"{unreviewed} {again}" if parked else unreviewed
        return FailureText("The code review stopped before it finished, and no reason was "
                           f"reported.{tail}".rstrip(), "no reason was reported")
    if r.strip() in ("", "build reported failed", "remediation build failed",
                     "phase reported failed"):
        return FailureText(f"{what} stopped without reporting a specific reason.",
                           "no reason was reported")
    if step:
        # An unrecognised failure at a step we know: name the step; the rest is in the details.
        doing = {"open": "opening the pull request", "merge": "merging",
                 "review": "reviewing the code"}[step]
        tail = f"{unreviewed} {again}" if parked else unreviewed
        return FailureText(f"{what} stopped on an unexpected error while {doing}.{tail}".rstrip(),
                           "an unexpected error")
    return FailureText(rest, rest)  # already a specific message - kept, never lost


def _technical_detail(raw: str, sentence: str) -> str:
    """The raw failure behind a sentence, for "Technical details" — or "" when the sentence IS
    the raw text (a specific message passed through), so the same words never show twice."""
    raw = (raw or "").strip()
    return "" if raw == (sentence or "").strip() else raw[:4000]


def classify_build_failure(reason: str, *, subject: str = "", parked: bool = True) -> str:
    """The banner sentence for a failure - see `describe_build_failure`."""
    return describe_build_failure(reason, subject=subject, parked=parked).sentence


def handle_secret_block_core(inp: BuildInput, reason: str, findings: list | None = None) -> dict:
    """A pre-push secret block used to be a dead end. The build failed, the branch was never
    pushed, the companion tore the worktree down, and the agent was never told what tripped — so
    the only way forward was a human re-trigger with a brand-new agent context and no memory of
    it. That is the same shape as remediation-exhaustion (S.No 161), and it gets the same answer:
    ONE bounded auto-retry seeded with what blocked the last attempt, then a terminal failure.

    Deliberately a fresh run rather than an in-place fix: nothing was pushed and the worktree is
    already gone (`runner.teardown_worktree`), so there is no branch for the agent to correct. A
    new attempt that KNOWS what tripped is the most that is available — and is enough, because the
    findings name the file, the line, and the redacted shape.

    The redacted previews are safe to carry into the next prompt: they are `conf***ow (24 chars)`,
    never the value (`guardrails._redact`). If a finding is a real credential, the agent is being
    told the location and that it must not be committed — not the secret itself.
    """
    findings = findings or []
    if findings:
        digest = "\n".join(
            f"- [{f.get('kind', 'secret')}] {f.get('path', '?')}:{f.get('line', 0)}"
            f" — {f.get('preview', '')}"
            for f in findings
        )
    else:
        digest = reason

    if inp.attempt < inp.max_auto_attempts:
        from .trigger import trigger_build

        prior_context = (
            (f"{inp.prior_attempt_context}\n\n" if inp.prior_attempt_context else "")
            + f"Attempt {inp.attempt} was BLOCKED by the pre-push secret scan, so nothing was "
              "committed or pushed. The scan flags string literals that look like credentials "
              "(the value shown is redacted — only its first/last characters and length):\n"
            + f"{digest}\n"
              "Do not commit a literal credential anywhere, including CI workflow and compose "
              "files. Read every secret from an environment variable instead, and put a named "
              "placeholder — not a value — in the env-example. If one of these is not a secret, "
              "the value still must not be a committed literal."
        )
        with tenant_context(inp.tenant_id):
            run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
            triggered_by_id = str(run.triggered_by_id) if run.triggered_by_id else None
            run.status = Run.Status.FAILED
            run.outputs = {
                **(run.outputs or {}),
                "error": (f"Secret scan blocked the push on attempt {inp.attempt}/"
                          f"{inp.max_auto_attempts} — auto-retrying with a fresh agent attempt."),
                "secret_findings": findings,
            }
            run.save(update_fields=["status", "outputs", "updated_at"])
            tools.log_event(inp.tenant_id, "orchestrator", "build.secret_blocked_retry",
                            "run", inp.run_id,
                            {"attempt": inp.attempt, "next_attempt": inp.attempt + 1,
                             "finding_count": len(findings)})
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

    # Auto-retries exhausted — terminal, exactly as before this change. A secret block does NOT
    # park for a human resume: parking resumes mid-workflow, and there is no branch to resume onto.
    return {"action": "failed", "reason": reason}


def mark_build_failed_core(inp: BuildInput, reason: str) -> dict:
    """Dead-letter / failed-build compensation: flag the run failed, return the WorkItem to
    in_progress (the branch/draft PR are left for human disposition — register-don't-recreate).
    The reason is classified (S.No 139) and stored on `run.outputs.error` — where the run
    console reads the failure line — as well as the build.failed event payload."""
    raw = reason
    said = describe_build_failure(raw, parked=False)
    reason = said.sentence
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.FAILED
        # `error` is the sentence the console shows; `error_detail` is the raw text behind it,
        # shown under "Technical details" (closed) — kept, never pasted into the sentence.
        run.outputs = {**(run.outputs or {}), "error": reason,
                       "error_detail": _technical_detail(raw, reason)}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        tools.log_event(inp.tenant_id, "orchestrator", "build.failed", "run", inp.run_id,
                        {"reason": said.cause})
    _finish_build_status(inp, "failure", reason)
    return {"status": "build_failed", "reason": reason}


def _close_remediation_board(inp: BuildInput, why: str) -> int:
    """Close every open remediation child of this WorkItem, and say why in the ledger.

    Used when an attempt ends and the next one must not inherit its board. Closes rather than
    deletes: the items are the previous attempt's record (#3 — the registry and ledger are
    provenance). Returns how many were closed."""
    closed = 0
    with tenant_context(inp.tenant_id):
        open_items = WorkItem.objects.filter(
            tenant_id=inp.tenant_id, parent_id=inp.work_item_id, type=WorkItem.Type.TASK,
            state=WorkItem.State.IN_PROGRESS)
        for child in open_items:
            rem = (child.external_ref or {}).get("rem")
            if not rem:                       # not a remediation item — leave it alone
                continue
            child.state = WorkItem.State.DONE
            child.save(update_fields=["state", "updated_at"])
            tools.log_event(inp.tenant_id, "code_review", "remediation.closed",
                            "work_item", str(child.id), {"rem": rem, "reason": why})
            closed += 1
    return closed


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
        # A fresh attempt starts with a fresh board. The remediation children hang off the
        # WorkItem, not the run, so without this the retry inherits THIS attempt's items — and
        # since a stale item is only ever refreshed when the new reviewer happens to reuse its
        # id, the retry can open mis-briefed on its very first cycle. That is exactly how WI-87's
        # second run was doomed before it began: it inherited "COMPOFF_EXPIRED" from run 1 and
        # never once saw the finding it was actually being blocked on. The items are CLOSED, not
        # deleted — they are the previous attempt's record, and `prior_context` above already
        # carries their substance forward to the new agent.
        _close_remediation_board(inp, "attempt_exhausted")
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
                            "run", inp.run_id,
                            {"attempt": inp.attempt, "next_attempt": inp.attempt + 1})
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
    raw = reason
    # The step being resumed says what stopped — the review, or the build — so the wording never
    # depends on matching the message text (S.No 266 used to be recognised by its words alone).
    subject = "review" if resume_from == "run_code_review" else ""
    said = describe_build_failure(raw, subject=subject, parked=True)
    reason = said.sentence
    stopped = "code review stopped" if subject == "review" else "stopped"
    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.STALLED
        run.outputs = {**(run.outputs or {}), "error": reason,
                       "error_detail": _technical_detail(raw, reason), "kept": BUILD_KEPT,
                       "resume_from": resume_from, "resumable": True}
        run.save(update_fields=["status", "outputs", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.parked", "run", inp.run_id,
                        {"reason": f"{stopped}: {said.cause}", "resume_from": resume_from,
                         "resumable": True})
    return {"status": "parked", "reason": reason, "resume_from": resume_from}


def pause_build_core(inp: BuildInput, paused_by: str, resume_from: str) -> dict:
    """Activity seam over `activities.pause_run_state`, with the build's `kept` sentence.

    `kept` is written here and not on the plan path because a paused build is exactly the case where
    the reader wants telling that the build, the branch and the pull request all survive — the same
    sentence a parked build already shows, and more true of a deliberate pause than of a failure."""
    from .activities import pause_run_state

    return pause_run_state(inp.tenant_id, inp.run_id, paused_by, resume_from, kept=BUILD_KEPT)


def resume_build_core(inp: BuildInput) -> dict:
    """Activity seam over `activities.resume_run_state`, also clearing the build's `kept`."""
    from .activities import resume_run_state

    return resume_run_state(inp.tenant_id, inp.run_id, extra_keys=("kept",))


def reject_build_core(inp: BuildInput, comment: str) -> dict:
    """Rejected at the merge gate: fail the run, hand the work item back, supersede the drafts.

    The supersede half is Bugs S.No 218. The planning path has always done this
    (`activities.reject_run_core`) and the build path never did, so a rejected build left its
    `code` artifact sitting at STAGED — the status the platform uses for "waiting at a gate" —
    forever. That was invisible while STAGED was displayed as the machine word "Staged"; once it
    reads "Waiting for approval" on screen, leaving it there would have the platform state
    something false about work a human has already turned down.

    Same rule as the planning path: PUBLISHED artifacts are untouched (a rejected remediation
    cycle must not un-publish an earlier merged one), nothing is deleted, and `get_context` stops
    serving the rest downstream as authoritative."""
    with tenant_context(inp.tenant_id):
        Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).update(
            status=Run.Status.REJECTED
        )
        superseded = Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id,
        ).exclude(status=Artifact.Status.PUBLISHED).update(
            status=Artifact.Status.SUPERSEDED, updated_at=_now(),
        )
        tools.transition_work_item(inp.tenant_id, inp.work_item_id, WorkItem.State.IN_PROGRESS)
        tools.log_event(inp.tenant_id, "orchestrator", "build.rejected", "run", inp.run_id,
                        {"comment": comment, "superseded_artifacts": superseded})
    _finish_build_status(inp, "failure", "Changes were rejected at the merge gate.")
    return {"status": "rejected", "superseded_artifacts": superseded}


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
#: The phase a code_review artifact belongs to — its OWN phase, not the build phase that produced
#: the code under review. `BuildInput.phase` is "implementation", which is why the platform's
#: registrations filed 11 reviews under the wrong phase while every reviewer-registered one used
#: this value.
_REVIEW_PHASE = "code_review"


def _review_body_for_artifact(inp: BuildInput, findings: list) -> str:
    """The document the `code_review` artifact points at.

    Prefer the reviewer's own prose — the platform already receives and stores it on
    `run.outputs["review_body"]` (24,702 characters on the run that surfaced this bug), and it is
    what a human actually wants to read. Fall back to rendering the structured findings when a
    reviewer returned findings without prose, so the artifact is never left pointing at nothing —
    which is the whole defect being fixed here. Never returns empty: an empty body would 404 in
    `read_artifact_preview` exactly as before."""
    with tenant_context(inp.tenant_id):
        run = Run.objects.filter(id=inp.run_id, tenant_id=inp.tenant_id).only("outputs").first()
    outputs = ((run.outputs if run else None) or {})
    prose = outputs.get("review_body") or ""
    if prose.strip():
        return prose
    header = f"# Code Review — {display_name(inp)}\n"
    # A FAILED review has no prose and no findings, which used to render as the same
    # "No findings were raised" as a genuinely clean one — a review that never happened,
    # presented to the approver as a review that found nothing. The guard in
    # `run_code_review_core` means this should no longer be reachable for the companion
    # provider; it stays because the artifact must be honest on its own, whatever the caller.
    if outputs.get("review_status") == "failed":
        # The approver reads this, so it says why in words; the engine's raw error stays on the
        # run (`review_error`) and in the log, not in the document (run-console fix, 2026-09-21).
        why = describe_build_failure(outputs.get("review_error") or "", subject="review",
                                     parked=False).sentence
        return (header + "\n**This review did not complete, so the code was not reviewed.**\n\n"
                f"{why}\n")
    if not findings:
        return header + "\nNo findings were raised in this review cycle.\n"
    lines = [header]
    for f in findings:
        loc = f"{f.file or '?'}:{f.line or 0}"
        lines.append(f"\n## {f.rem} — {f.severity}\n\n**{f.title}**  \n`{loc}`\n")
        # Same prose the remediation WorkItem gets (S.No 147), so the artifact and the board
        # say the same thing rather than each rendering findings their own way.
        detail = _remediation_description(f).strip()
        if detail:
            lines.append(f"\n{detail}\n")
    return "".join(lines)


def run_code_review_core(inp: BuildInput) -> dict:
    """Review the PR (08), record a `code_review` artifact, and reconcile **remediation
    child WorkItems** (one per REM-C/REM-W): open new findings, close resolved ones. Returns
    the count of open blocking findings — the loop continues while it is > 0."""
    code = _code_artifact(inp)
    if code is None or not _is_pr_ref(code.external_ref):
        raise RuntimeError(f"no opened PR to review for run {inp.run_id}")
    pr_ref = f"{code.external_ref['repo']}#{code.external_ref['number']}"

    # Imported here, not at module scope: review_provider imports from this module.
    from .review_provider import ReviewUnavailableError

    try:
        findings = list(get_review_provider().review(inp, pr_ref))
    except ReviewUnavailableError as exc:
        # NON-RETRYABLE on purpose. The usual cause is the engine hitting a usage limit, which no
        # amount of immediate retrying fixes — Temporal's retry would just re-dispatch the review
        # into the same wall and burn the budget. The workflow parks instead, so a human resumes
        # when the engine is available again and nothing already built is thrown away.
        raise ApplicationError(str(exc), type="ReviewFailed", non_retryable=True) from exc
    blocking = {f.rem: f for f in findings if f.severity in _BLOCKING}

    # STAGE THE BODY. This artifact is `sor="internal"` — "Platform only" — so unlike a `code`
    # pointer (sor="git", whose content lives in the PR and must never be copied here, #1/#3),
    # there is no system of record to read it back from. If the body is not written to the object
    # store it exists NOWHERE reachable, and Preview 404s: "artifact has no body to preview".
    # That is exactly what happened — every code_review artifact this function ever registered was
    # a pointer to nothing, while the review text sat unused on `run.outputs["review_body"]`.
    # Re-staged every cycle (the key is run/phase-scoped, so a cycle overwrites its own snapshot)
    # so the artifact always resolves to the latest review rather than a stale first pass.
    body = _review_body_for_artifact(inp, findings)
    staged = tools.stage_artifact_body(
        inp.tenant_id, inp.project_id, inp.run_id, _REVIEW_PHASE,
        filename="code-review.md", body=body, content_type="text/markdown",
        # Through the module's injectable factory (same seam publish/merge use), so this is
        # unit-testable without a live object store.
        object_store=get_object_store(),
    )
    with tenant_context(inp.tenant_id):
        review_art = Artifact.objects.filter(
            run_id=inp.run_id, tenant_id=inp.tenant_id, type="code_review").first()
    if review_art is None:
        created = tools.register_artifact(
            # `_REVIEW_PHASE`, not `inp.phase`: inp is the BUILD input, so its phase is
            # "implementation" and the review filed under the phase that produced the code
            # rather than its own. Every review registered by the reviewer itself already uses
            # "code_review"; this makes the platform's own registration agree with it.
            inp.tenant_id, inp.project_id, inp.run_id, _REVIEW_PHASE, "code_review", "internal",
            content_hash=staged["content_hash"], s3_key=staged["s3_key"],
            title=f"Code Review — {display_name(inp)}")
        review_art_id = created["id"]
        tools.add_trace_edge(inp.tenant_id, review_art_id, str(code.id), "tests")
    else:
        tools.update_artifact(inp.tenant_id, str(review_art.id),
                              content_hash=staged["content_hash"], s3_key=staged["s3_key"])
        review_art_id = str(review_art.id)

    with tenant_context(inp.tenant_id):
        story = WorkItem.objects.get(id=inp.work_item_id, tenant_id=inp.tenant_id)
        children = WorkItem.objects.filter(
            tenant_id=inp.tenant_id, parent_id=inp.work_item_id, type=WorkItem.Type.TASK)
        # Cancelled items are left out of the map entirely (S.No 140), which is stronger than
        # not closing them. A `rem` id is a POSITION in one review's output, not an identity
        # (see the long note in the refresh branch below): if the same id comes back next cycle
        # meaning a DIFFERENT finding, a cancelled row holding that id would either be dragged
        # back to `in_progress` by the refresh, or silently block the new finding from getting
        # an item at all. Treating it as absent keeps the cancellation AND lets the real
        # finding through on its own row.
        existing = {(c.external_ref or {}).get("rem"): c for c in children
                    if (c.external_ref or {}).get("rem")
                    and c.state != WorkItem.State.CANCELLED}
        # Close remediation items whose finding is gone (resolved by the last build).
        for rem, child in existing.items():
            # A cancelled remediation item is left alone (S.No 140).
            if rem not in blocking and child.state not in WorkItem.TERMINAL_STATES:
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
            else:
                # REFRESH IT. A `rem` id is a POSITION in one review's output ("the first
                # warning this round"), not a stable identity — the reviewer renumbers from 1
                # every cycle and is never shown the ids it used last time, so the moment the
                # finding set changes shape, REM-W1 silently means a different problem.
                # This branch used to flip `state` only, freezing title/description/file/line at
                # whatever cycle 1 said. `dispatch_remediation_core` briefs agent 07 from exactly
                # those fields, so the loop then spent every remaining cycle asking 07 to re-fix
                # something it had already fixed while the reviewer blocked on something 07 was
                # never told about — unwinnable by construction, and the cause of every
                # remediation-exhausted build (8/8 across both tenants; WI-87 burned 20 review
                # cycles and 15 rebuilds over 26 hours against a board last written in minute 20).
                # Rewriting from the CURRENT finding makes the brief true of this cycle whatever
                # the id happens to mean, which is what actually breaks the deadlock.
                retargeted = (child.title != (finding.title or rem)
                              or (child.external_ref or {}).get("file") != finding.file)
                child.title = finding.title or rem
                child.description = _remediation_description(finding)
                child.external_ref = {**(child.external_ref or {}), "rem": rem,
                                      "severity": finding.severity,
                                      "file": finding.file, "line": finding.line}
                child.state = WorkItem.State.IN_PROGRESS
                child.save(update_fields=["title", "description", "external_ref",
                                          "state", "updated_at"])
                if retargeted:
                    # Say so in the ledger: "same id, different finding" is the signature of the
                    # collision above, and it was invisible while the console showed only counts.
                    tools.log_event(inp.tenant_id, "code_review", "remediation.retargeted",
                                    "work_item", str(child.id),
                                    {"rem": rem, "severity": finding.severity,
                                     "file": finding.file, "title": finding.title})
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
    idea as the reviewer's PR-diff section. The agent fixes these on the SAME branch.

    **Deliberately uncapped, and it should stay that way.** This was reviewed when the manifest
    budget was built, as one of the sections appended outside it. Giving it a cap would have
    introduced a truncation that does not exist today, and of the worst possible kind: this list
    IS the instruction set — the findings the agent must fix — so a cut tail silently drops work
    the review has already demanded, and the next cycle reports it unfixed. That is the same
    failure as cutting a work item's acceptance criteria (register T2), which cost eighteen days.
    Its size is bounded by the number of open findings on one work item, which the remediation
    loop already limits; it is not a section that grows with the project's age.
    """
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
    from dataclasses import replace

    from django.conf import settings

    from manifest.budget import review_direction_tokens
    from manifest.composer import TokenBudget, _render_review_direction

    from .activities import _manifest_budget, build_review_round

    with tenant_context(inp.tenant_id):
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        history = list((run.inputs or {}).get("review_history") or [])
    entry = build_review_round(inp.tenant_id, inp.run_id, direction)
    entry["revision"] = len(history) + 1
    history = history + [entry]

    # Same renderer the planning path uses, so a reviewer's direction reads identically to an
    # agent whichever workflow it arrives through — and now the same BUDGET too. It used to pass
    # a bare default, which quietly made this the one section in the product that could not grow
    # with the model: every other path went elastic while the words a human had just typed stayed
    # capped at 3,000 on the one path whose entire purpose is to deliver them.
    base = TokenBudget()
    direction_budget = replace(
        base, review_direction=review_direction_tokens(_manifest_budget(inp),
                                                       base.review_direction))
    manifest = (f"{compose_manifest_core(inp)}\n\n"
                f"{_render_review_direction(history, direction_budget)}")
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


@activity.defn(name="run_a11y_ai_pass")
def run_a11y_ai_pass_activity(inp: BuildInput) -> dict:
    return _boundary(run_a11y_ai_pass_core, inp)


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


@activity.defn(name="handle_secret_block")
def handle_secret_block_activity(inp: BuildInput, reason: str, findings: list) -> dict:
    return _boundary(handle_secret_block_core, inp, reason, findings)


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


@activity.defn(name="pause_build")
def pause_build_activity(inp: BuildInput, paused_by: str, resume_from: str) -> dict:
    return _boundary(pause_build_core, inp, paused_by, resume_from)


@activity.defn(name="resume_build")
def resume_build_activity(inp: BuildInput) -> dict:
    return _boundary(resume_build_core, inp)


BUILD_ACTIVITIES = [
    dispatch_build_activity,
    open_build_pr_activity,
    import_build_test_results_activity,
    run_a11y_ai_pass_activity,
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
    handle_secret_block_activity,
    reject_build_activity,
    reopen_merge_gate_activity,
    publish_build_artifacts_activity,
    park_build_activity,
    pause_build_activity,
    resume_build_activity,
]


# Convenience for the report path (used by the report service when building the signal).
def report_to_dict(report: BuildReport) -> dict:
    return asdict(report)
