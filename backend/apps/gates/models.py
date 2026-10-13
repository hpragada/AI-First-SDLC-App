"""Gates: Approval — control-plane gate (never in engine hooks — #2, #5)."""
from django.db import models

from apps.base import Role, TenantScopedModel


class Approval(TenantScopedModel):
    class Decision(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    run = models.ForeignKey("runs.Run", on_delete=models.CASCADE, related_name="approvals")
    gate_type = models.CharField(max_length=64, default="phase_gate")
    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, related_name="approvals"
    )
    required_role = models.CharField(max_length=32, choices=Role.choices)
    approver = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    decision = models.CharField(
        max_length=16, choices=Decision.choices, default=Decision.PENDING
    )
    comment = models.TextField(blank=True)
    # Gate conditions a control-plane checklist must satisfy before APPROVED (#2/#5, D6):
    # the a11y/WCAG gate seeds the WCAG 2.2 AA criteria here; a required-but-unsatisfied
    # condition blocks approval. Each item: {key, label, required, satisfied}.
    conditions = models.JSONField(default=list, blank=True)
    # Set when the pull request this gate is about was merged OUTSIDE the platform - somebody
    # merged it on GitHub (Bugs S.No 88). Records {merged_by, merged_at, pr_ref, detected_by}.
    #
    # NULLABLE on purpose. An older release that does not know this column simply omits it from
    # its INSERT and Postgres accepts NULL, so a rolling deploy cannot break in the shape that
    # caused S.No 185 (a NOT NULL column with no database-level default).
    #
    # It is a NOTE, never a decision. Nothing in the platform approves a gate: this only tells
    # the reviewer what already happened so they can acknowledge it. That containment is what
    # makes it safe for a webhook to write - see the sender note in integrations/webhooks.py.
    external_merge = models.JSONField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"approval:{self.id} ({self.decision})"
