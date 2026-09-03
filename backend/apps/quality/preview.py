"""Ephemeral preview env per PR — the companion-local seam (Phase 3 §6, D7).

A preview env is a temporary running copy of the app built from the PR branch, so a reviewer
can exercise the real feature and the E2E tests have a live target. In local-companion mode
the honest v1 is **companion-local**: the companion brings the app up from the worktree and
reports the local URL; the platform records the `PreviewEnv`, links it on the PR (a CodeHost
comment), and tears it down on close. A real cloud per-PR env is the P5 cloud workstream —
it drops in behind `PreviewEnv.provider` without changing callers.
"""
from __future__ import annotations

from mcp_platform_state import tools

from apps.tenancy.context import tenant_context

from .models import PreviewEnv


def provision_preview(
    *, tenant_id, project_id, work_item_id, run_id=None, pr_ref: str = "", url: str = "",
    get_capability=None, post_comment: bool = True,
) -> dict:
    """Record a companion-local preview env as ready and link it on the PR (best-effort)."""
    with tenant_context(tenant_id):
        preview, _ = PreviewEnv.objects.update_or_create(
            tenant_id=tenant_id, project_id=project_id, work_item_id=work_item_id,
            pr_ref=pr_ref,
            defaults={"run_id": run_id, "url": url,
                      "status": PreviewEnv.Status.READY,
                      "provider": PreviewEnv.Provider.COMPANION_LOCAL},
        )
        tools.log_event(tenant_id, "quality", "preview.ready", "preview_env",
                        str(preview.id), {"url": url, "pr_ref": pr_ref})

    if post_comment and pr_ref and url:
        _comment_on_pr(tenant_id, pr_ref, url, get_capability)
    return {"preview_id": str(preview.id), "status": preview.status, "url": url}


def teardown_preview(*, tenant_id, preview_id) -> dict:
    """Tear the preview env down (on PR merge/close or saga compensation)."""
    with tenant_context(tenant_id):
        preview = PreviewEnv.objects.get(id=preview_id, tenant_id=tenant_id)
        preview.status = PreviewEnv.Status.TORN_DOWN
        preview.save(update_fields=["status", "updated_at"])
        tools.log_event(tenant_id, "quality", "preview.torn_down", "preview_env",
                        str(preview.id), {})
    return {"preview_id": str(preview.id), "status": preview.status}


def teardown_preview_for_run(*, tenant_id, project_id, work_item_id, run_id=None) -> dict:
    """Tear down the build's preview env, located by work item (+ run). Best-effort and idempotent:
    a no-op when nothing is READY (07/11, or already torn down). The BuildWorkflow calls this at
    terminal states without tracking the preview_id itself (P3-09bR-5)."""
    with tenant_context(tenant_id):
        qs = PreviewEnv.objects.filter(
            tenant_id=tenant_id, project_id=project_id, work_item_id=work_item_id,
            status=PreviewEnv.Status.READY)
        if run_id:
            qs = qs.filter(run_id=run_id)
        preview = qs.order_by("-created_at").first()
        if preview is None:
            return {"torn_down": False}
    teardown_preview(tenant_id=tenant_id, preview_id=preview.id)
    return {"torn_down": True, "preview_id": str(preview.id)}


def _comment_on_pr(tenant_id, pr_ref: str, url: str, get_capability) -> None:
    if get_capability is None:
        from integrations.registry import get_capability as _gc
        get_capability = _gc
    try:
        codehost = get_capability(tenant_id, "codehost")
        codehost.add_pr_comment(pr_ref=pr_ref, body=f"🚀 Preview env ready: {url}")
    except Exception:  # noqa: BLE001 — linking is best-effort; the env is already recorded
        pass
