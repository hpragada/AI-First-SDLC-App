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

from .activities import _boundary, compose_manifest_core
from .build_types import BuildInput, BuildReport


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
    agent_body, model = _load_agent_body(inp.agent_spec_id, inp.tenant_id)
    payload = {
        "run_id": inp.run_id, "tenant_id": inp.tenant_id, "project_id": inp.project_id,
        "work_item_id": inp.work_item_id, "work_item_key": inp.work_item_key,
        "repo": inp.repo, "base": inp.base, "phase": inp.phase,
        "manifest": manifest, "agent_body": agent_body, "model": model,
        "api_url": getattr(settings, "PLATFORM_API_URL", ""),
    }
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
            title=f"{inp.work_item_key}: build", body=f"Build for WorkItem {inp.work_item_id}.",
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
            title=f"Code — {inp.work_item_key}",
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
        tools.update_artifact(inp.tenant_id, str(artifact.id), status=Artifact.Status.PUBLISHED)
        run = Run.objects.get(id=inp.run_id, tenant_id=inp.tenant_id)
        run.status = Run.Status.COMPLETED
        run.save(update_fields=["status", "updated_at"])
        tools.log_event(inp.tenant_id, "orchestrator", "build.merged", "run", inp.run_id,
                        {"pr": pr_ref})
    return {"merged": True, "pr_ref": pr_ref}


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
            content_hash=digest, title=f"Code Review — {inp.work_item_key}")
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
                  "line": (c.external_ref or {}).get("line")} for c in open_items]

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


# ── activity wrappers (close the DB connection at the boundary) ─────
@activity.defn(name="dispatch_build")
def dispatch_build_activity(inp: BuildInput) -> dict:
    return _boundary(dispatch_build_core, inp)


@activity.defn(name="open_build_pr")
def open_build_pr_activity(inp: BuildInput, report: BuildReport) -> dict:
    return _boundary(open_build_pr_core, inp, report)


@activity.defn(name="open_merge_gate")
def open_merge_gate_activity(inp: BuildInput) -> str:
    return _boundary(open_merge_gate_core, inp)


@activity.defn(name="run_code_review")
def run_code_review_activity(inp: BuildInput) -> dict:
    return _boundary(run_code_review_core, inp)


@activity.defn(name="dispatch_remediation")
def dispatch_remediation_activity(inp: BuildInput) -> dict:
    return _boundary(dispatch_remediation_core, inp)


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


@activity.defn(name="reject_build")
def reject_build_activity(inp: BuildInput, comment: str) -> dict:
    return _boundary(reject_build_core, inp, comment)


@activity.defn(name="reopen_merge_gate")
def reopen_merge_gate_activity(inp: BuildInput, reason: str) -> dict:
    return _boundary(reopen_merge_gate_core, inp, reason)


BUILD_ACTIVITIES = [
    dispatch_build_activity,
    open_build_pr_activity,
    run_code_review_activity,
    dispatch_remediation_activity,
    open_merge_gate_activity,
    merge_build_pr_activity,
    transition_build_work_item_activity,
    mark_takeover_activity,
    mark_build_failed_activity,
    reject_build_activity,
    reopen_merge_gate_activity,
]


# Convenience for the report path (used by the report service when building the signal).
def report_to_dict(report: BuildReport) -> dict:
    return asdict(report)
