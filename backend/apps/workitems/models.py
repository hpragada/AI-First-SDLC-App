"""WorkItems: the per-WorkItem DAG (non-negotiable #4)."""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.base import TenantScopedModel


class WorkItem(TenantScopedModel):
    class Type(models.TextChoices):
        EPIC = "epic", "Epic"
        STORY = "story", "Story"
        TASK = "task", "Task"
        # A defect raised by the test/quality loop — a first-class child of the story it
        # regresses (the defect-loopback DAG sub-work, P3 D5).
        DEFECT = "defect", "Defect"
        # A test case — a first-class child of the story it verifies. Created from the Testing
        # phase (09) output or by hand; Test Automation (09b) runs on it to generate its script
        # (one TC per run). Sibling of DEFECT in the QA sub-DAG.
        TEST_CASE = "test_case", "Test Case"

    class State(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"
        # Bugs S.No 140: there was no way to close a task that cannot be built. A duplicate, a
        # defect nobody will fix, a task overtaken by a decision — the only options were to
        # mark it `done` (a lie the delivery report then repeats) or leave it open for ever
        # (which is how a board stops meaning anything). Finished and abandoned are different
        # facts, and a board that cannot tell them apart cannot be trusted for either.
        CANCELLED = "cancelled", "Cancelled"

    #: The states that mean "this item needs no more work". Everything that used to ask
    #: `state == DONE` was really asking this, and every one of those places would have read
    #: a cancelled item as still open — a cancelled defect would have held its gate shut for
    #: ever, and a cancelled task would still have offered a Retry button.
    #:
    #: DONE and CANCELLED are NOT interchangeable, and nothing here should ever collapse
    #: them: one says the work happened, the other says it never will. This set answers only
    #: "is there anything left to do", which is the question those sites were asking.
    TERMINAL_STATES = frozenset({State.DONE, State.CANCELLED})

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="work_items"
    )
    repo = models.ForeignKey(
        "projects.Repository", null=True, blank=True, on_delete=models.SET_NULL
    )
    feature_stream = models.CharField(max_length=255, blank=True)
    # Issue-shaped fields so a proposed item can be reconciled into a SoR issue (P1).
    title = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
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
    # Pointer to the SoR issue once reconciled (proposed→accepted), e.g. a Jira key (P1).
    external_ref = models.JSONField(null=True, blank=True)
    # Human-readable, per-project sequential display number. Renders as "WI-<number>" so users
    # never see the raw UUID (Bugs.xlsx: work items shown by raw UUID). Assigned on first save.
    number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "number"], name="uniq_workitem_number_per_project"
            )
        ]

    @property
    def key(self) -> str:
        """Human work-item key, e.g. "WI-42". Empty only until the first save assigns a number."""
        return f"WI-{self.number}" if self.number else ""

    def save(self, *args, **kwargs):
        # Assign the next per-project number on creation. Numbers are stable (never reused) so
        # the key stays a durable handle even if earlier items are deleted.
        if self.number is None and self.project_id:
            last = WorkItem.objects.filter(project_id=self.project_id).aggregate(
                m=models.Max("number")
            )["m"]
            self.number = (last or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.key or self.type}:{self.feature_stream or self.id}"
