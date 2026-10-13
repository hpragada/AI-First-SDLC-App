"""Clarification — the control-plane interactive Q&A object (req #2).

When a phase agent needs information it lacks (a context gap, a process-step decision, a
pre-gate confirmation), it asks via the `ask_human` engine tool. That call creates a
`Clarification` here in the PENDING state and the engine blocks on the tool result — the
model generates nothing while it waits, so **no cost accrues** during the wait. A human
answers in the web app; the answer is recorded here and the waiting agent resumes in the
same session. This mirrors the gate `Approval` pattern: the engine never decides; a human
does, out of band (#2/#5).
"""
from django.db import models

from apps.base import TenantScopedModel


class Clarification(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ANSWERED = "answered", "Answered"
        CANCELLED = "cancelled", "Cancelled"

    run = models.ForeignKey(
        "runs.Run", on_delete=models.CASCADE, related_name="clarifications"
    )
    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, related_name="clarifications"
    )
    phase = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    # The questions the agent asked. Each item:
    # {id, text, kind: "text"|"choice"|"confirm", options?: [...], required: bool}.
    questions = models.JSONField(default=list, blank=True)
    # The human's answers, keyed by question id: {question_id: answer}.
    answers = models.JSONField(default=dict, blank=True)
    # Why the agent is asking (free text the agent supplies) — shown to the human for context.
    context = models.TextField(blank=True)
    # Stable hash of the question set, so a re-dispatched run reuses an existing answered
    # clarification instead of re-asking (idempotency / crash recovery).
    signature = models.CharField(max_length=64, blank=True, db_index=True)
    answered_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    answered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"clarification:{self.id} ({self.status})"
