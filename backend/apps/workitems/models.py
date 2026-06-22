"""WorkItems: the per-WorkItem DAG (non-negotiable #4)."""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.base import TenantScopedModel


class WorkItem(TenantScopedModel):
    class Type(models.TextChoices):
        EPIC = "epic", "Epic"
        STORY = "story", "Story"
        TASK = "task", "Task"

    class State(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="work_items"
    )
    repo = models.ForeignKey(
        "projects.Repository", null=True, blank=True, on_delete=models.SET_NULL
    )
    feature_stream = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.STORY)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PROPOSED)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    # DAG dependencies — list of WorkItem ids (non-negotiable #4).
    depends_on = ArrayField(models.UUIDField(), default=list, blank=True)
    assignee = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    takeover_flag = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.type}:{self.feature_stream or self.id}"
