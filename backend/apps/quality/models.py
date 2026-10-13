"""Test/Quality plane models (Phase 3 §3) — all RLS-aware (#6).

- TestExecution: the platform-side record of a companion test run (results summary +
  pointer to the Xray execution); flaky-flagged when a test flips across reruns.
- TestQuarantine: the flaky-quarantine register — a quarantined test is excluded from the
  blocking test gate (never silently blocks a merge, never silently passes).
- PreviewEnv: the per-PR ephemeral preview env (companion-local seam, D7) — provisioned
  from the worktree, linked on the PR, torn down on close.

Bodies/results live in Xray / the runner; state keeps only pointers + summaries (#1/#3).
"""
from django.db import models

from apps.base import TenantScopedModel


class TestExecution(TenantScopedModel):
    __test__ = False  # not a pytest test class

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="test_executions"
    )
    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, related_name="test_executions"
    )
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="test_executions",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Per-test summary [{test_ref, status, evidence}] — a summary, not copied result bodies.
    results = models.JSONField(default=list, blank=True)
    external_ref = models.JSONField(null=True, blank=True)   # the Xray execution pointer
    flaky = models.BooleanField(default=False)
    # The external execution identity for a run-less import (a CI run id / commit sha, P3-09bX-5):
    # CI results carry no platform Run, so idempotency keys on (work_item, execution_ref) instead
    # of (run, work_item). Blank for the build-report path, which still keys on the run.
    execution_ref = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return f"test_exec:{self.id} ({self.status})"


class TestQuarantine(TenantScopedModel):
    """A flaky test excluded from the blocking test gate (D9)."""

    __test__ = False  # not a pytest test class

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="test_quarantine"
    )
    test_ref = models.CharField(max_length=255)
    reason = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "project", "test_ref"), name="uniq_tenant_project_test_quarantine"
            )
        ]

    def __str__(self) -> str:
        return f"quarantine:{self.test_ref} (active={self.active})"


class PreviewEnv(TenantScopedModel):
    class Status(models.TextChoices):
        PROVISIONING = "provisioning", "Provisioning"
        READY = "ready", "Ready"
        TORN_DOWN = "torn_down", "Torn Down"
        FAILED = "failed", "Failed"

    class Provider(models.TextChoices):
        COMPANION_LOCAL = "companion_local", "Companion Local"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="preview_envs"
    )
    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, related_name="preview_envs"
    )
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="preview_envs"
    )
    pr_ref = models.CharField(max_length=255, blank=True)    # "owner/name#N"
    url = models.CharField(max_length=1024, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PROVISIONING
    )
    provider = models.CharField(
        max_length=32, choices=Provider.choices, default=Provider.COMPANION_LOCAL
    )

    def __str__(self) -> str:
        return f"preview:{self.id} ({self.status})"
