"""Runs: each agent run = a Temporal workflow (non-negotiable #8)."""
from django.contrib.postgres.fields import ArrayField
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
        # A companion did not report before the timeout, so the run is PARKED for human
        # takeover — but NON-terminally (Bugs S.No 89). A companion that only slept can still
        # return and report; that report reconciles the run through the normal gate path.
        # Only an explicit human takeover (or a reported failure) makes it terminal.
        STALLED = "stalled", "Stalled"
        # A HUMAN stopped this run on purpose and means to come back to it. Deliberately NOT
        # reusing STALLED, which already carries two meanings (an error park, and a
        # companion-offline park) separated only by `outputs.resumable`. A third would have been
        # a bug rather than a shortcut: STALLED is excluded from the active-run guard in
        # orchestration/trigger.py precisely because re-triggering over a parked run is valid —
        # so a pause recorded as STALLED would have let the same phase be triggered again and put
        # TWO runs on one work item and one branch. PAUSED is in that guard; see the note there.
        PAUSED = "paused", "Paused"

    work_item = models.ForeignKey(
        "workitems.WorkItem", on_delete=models.CASCADE, related_name="runs"
    )
    agent_spec = models.ForeignKey(
        "registry.AgentSpec", on_delete=models.PROTECT, related_name="runs"
    )
    # Who triggered this run (the web-app user). Used to route the run to that user's enrolled
    # local companion (req #1 — every phase runs on the client's own Claude Code).
    triggered_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
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


class RunnerEnrollment(TenantScopedModel):
    """A developer-machine local-companion runner enrolled with the platform (Phase-2 §3).

    Scopes a companion to a tenant+project+repos; the companion connects *outbound* and
    authenticates with an enrollment token whose hash is stored here (never the secret —
    the token_ref/vault seam). RLS keeps a tenant's enrollments isolated."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="runner_enrollments"
    )
    developer = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL
    )
    label = models.CharField(max_length=255, blank=True)       # the dev's machine label
    enroll_token_hash = models.CharField(max_length=128, blank=True)
    repos = ArrayField(models.CharField(max_length=512), default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"runner:{self.label or self.id} ({self.status})"


class CodeIntelJob(TenantScopedModel):
    """A dispatched code-intelligence indexing job (Brownfield B4).

    Unlike an agent `Run`, this has NO WorkItem and NO AgentSpec — code intelligence is
    mechanical, repo-scoped analysis, not an agent reasoning task. So it rides its own dispatch
    channel instead of the Run/gate/Temporal machinery: the platform creates a PENDING job, the
    enrolled companion claims it, runs the built-in analyzer in a **read-only worktree** (the
    client's source never reaches the platform — non-negotiable #1), and reports the resulting
    index back (the server-side sink persists the `codebase_intelligence` artifact + knowledge
    chunk). RLS-isolated per tenant like every table (#6)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"
        INDEXED = "indexed", "Indexed"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="code_intel_jobs"
    )
    repo = models.ForeignKey(
        "projects.Repository", on_delete=models.CASCADE, related_name="code_intel_jobs"
    )
    # The companion this job was routed to (the triggering user's enrolled machine). Null = a
    # broadcast job any active companion for the tenant+project may claim (mirrors the Run path).
    enrollment = models.ForeignKey(
        "runs.RunnerEnrollment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    triggered_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    claimed_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=512, blank=True)

    def __str__(self) -> str:
        return f"codeintel:{self.id} ({self.status})"
