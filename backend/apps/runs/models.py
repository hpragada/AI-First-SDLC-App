"""Runs: each agent run = a Temporal workflow (non-negotiable #8)."""
from django.db import models

from apps.base import TenantScopedModel


class Run(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        AWAITING_GATE = "awaiting_gate", "Awaiting Gate"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        FAILED = "failed", "Failed"
        COMPLETED = "completed", "Completed"

    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, related_name="runs"
    )
    agent_spec = models.ForeignKey(
        "registry.AgentSpec", on_delete=models.PROTECT, related_name="runs"
    )
    engine = models.CharField(max_length=32, default="claude")
    model = models.CharField(max_length=64, blank=True)
    prompt_version = models.CharField(max_length=64, blank=True)
    temporal_workflow_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    inputs = models.JSONField(default=dict, blank=True)
    outputs = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"run:{self.id} ({self.status})"
