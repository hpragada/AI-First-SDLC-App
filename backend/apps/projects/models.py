"""Projects: Project, ProjectProfile (1:1), Repository (0..N)."""
from django.db import models

from apps.base import TenantScopedModel


class Project(TenantScopedModel):
    class Track(models.TextChoices):
        GREENFIELD = "greenfield", "Greenfield"
        BROWNFIELD = "brownfield", "Brownfield"

    class RepoTopology(models.TextChoices):
        SINGLE = "single", "Single"
        SPLIT = "split", "Split"
        MULTI = "multi", "Multi"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=255)
    track = models.CharField(max_length=16, choices=Track.choices, default=Track.GREENFIELD)
    repo_topology = models.CharField(
        max_length=16, choices=RepoTopology.choices, default=RepoTopology.SINGLE
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    def __str__(self) -> str:
        return self.name


class ProjectProfile(TenantScopedModel):
    """The migrated `CLAUDE.md` structure (becomes the composed manifest)."""

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="profile")
    description = models.TextField(blank=True)
    domain = models.CharField(max_length=255, blank=True)
    tech_stack = models.JSONField(default=dict, blank=True)
    coding_standards = models.JSONField(default=dict, blank=True)
    nfrs = models.JSONField(default=dict, blank=True)
    constraints = models.JSONField(default=dict, blank=True)
    glossary = models.JSONField(default=dict, blank=True)
    # Per-tenant theming (PG23/D10): design tokens + responsive breakpoints + brand, flowed
    # verbatim into the rendered manifest so design/implementation agents honor one theme —
    # no per-tenant code fork. e.g. {"brand","tokens":{...},"breakpoints":[375,768,1440]}.
    theme = models.JSONField(default=dict, blank=True)
    # Phase-scoped manual-export overrides (bare phase name -> capability | "internal").
    # Effective policy = integrations.export_policy.DEFAULT_EXPORT_POLICY overlaid with
    # this; empty dict = pure defaults. Exports are always user-triggered (team flow
    # decision 2026-07-07) — this only governs WHERE each phase's artifacts may go.
    export_policy = models.JSONField(default=dict, blank=True)
    # Preview-start config — the FALLBACK for single-serve-target projects (Repository.preview_start
    # is the primary home; the thing served is a repo). Same shape: how the companion brings the app
    # up from the worktree so 09b/E2E have a live target (D7). {command, port, health_path,
    # ready_timeout_s, ready_log}. Empty ⇒ no preview; a test-automation run then fails loud
    # (P3-09bR). See docs/PHASE_3_09B_RUNNABLE_SPEC.md §1.
    preview_start = models.JSONField(default=dict, blank=True)
    important_context = models.TextField(blank=True)
    version = models.IntegerField(default=1)


class Repository(TenantScopedModel):
    """A code repo a project targets. Light multi-repo (Phase 2): N per project, each with
    its own base branch + CodeHost connector. Full multi-repo (cross-repo DAG) is P4."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="repositories")
    name = models.CharField(max_length=512, blank=True)        # "owner/name"
    default_base = models.CharField(max_length=255, default="main")
    connector = models.CharField(max_length=64, blank=True)    # e.g. "github"
    role = models.CharField(max_length=64, blank=True)         # frontend/backend/service
    code_host_ref = models.CharField(max_length=512, blank=True)
    scopes = models.JSONField(default=dict, blank=True)
    stack_overrides = models.JSONField(default=dict, blank=True)
    # Preview-start config — PRIMARY home (the served thing is a repo: the frontend repo runs the
    # UI; a backend repo has no UI to preview). How the companion brings the app up from the
    # worktree so 09b's Live Application Exploration + E2E have a live target (D7):
    #   {"command": "npm run dev", "port": 5173, "health_path": "/",
    #    "ready_timeout_s": 120, "ready_log": "Local:"}   # health_path OR ready_log satisfies ready
    # Empty ⇒ no preview; a test-automation build then fails loud rather than run without locators
    # (P3-09bR). Resolution is repo-first then ProjectProfile.preview_start. Spec §1.
    preview_start = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)    # onboarding origin
    # The repo build PRs target when a work item doesn't pin one (S-13 "Set default";
    # P4.7-T7). The first repo registered on a project is default until reassigned.
    is_default = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name or f"{self.project_id}:{self.role}"
