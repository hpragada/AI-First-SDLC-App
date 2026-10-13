"""Projects: Project, ProjectProfile (1:1), Repository (0..N)."""
from django.db import models
from django.db.models.functions import Lower

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

    class Meta:
        constraints = [
            # Bugs S.No 211: nothing stopped two projects in one workspace sharing a name, so
            # every screen that names a project (the switcher, the board header, an invite) named
            # two different things identically and the wrong one could be worked on for days.
            #
            # Case-INSENSITIVE on purpose. "Billing Service" and "billing service" are the same
            # project to the person reading the switcher; a case-sensitive constraint would let
            # the confusing pair straight through while claiming to have solved it.
            #
            # Archived names stay reserved (no `condition=Q(status="active")`): un-archiving a
            # project whose name has since been taken by another is a worse surprise than being
            # asked to pick a different name. Recorded as a decision, not an oversight — making
            # it conditional later is a one-line change to a partial index.
            models.UniqueConstraint(
                Lower("name"), "tenant", name="uniq_tenant_project_name",
            )
        ]

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
    # Accessibility policy (QA-08): what this project aims at, and what stops the pipeline.
    # {"target": "wcag_2.2_aa", "gate": {"block_severities": [...], "min_confidence": 0.0,
    #  "block_on_incomplete_run": true, "design_checks": {"extra_criteria": []}}}. A policy
    # block rather than columns, like theme/export_policy/preview_start, so a later setting
    # needs no migration. Empty ⇒ apps.a11y.policy.default_policy() — never "unset behaviour".
    a11y = models.JSONField(default=dict, blank=True)
    # Security-scan provisioning (Bugs S.No 185): which package registries this project's
    # scanners may reach. The companion's egress allowlist is deliberately narrow — GitHub, the
    # Anthropic API and npm — and its own comment says the other ecosystems are left out because
    # "per-project declaration is what `extra_allowed_hosts` is for, and that path needs a
    # server-side way to declare them, which does not exist yet". This is that way.
    # {"registries": ["pypi.org", "files.pythonhosted.org"]}. Empty ⇒ the default allowlist,
    # byte-for-byte as today. A block rather than columns, like theme/export_policy/a11y, so a
    # later scan setting (tool list, severity floor) needs no second migration.
    scan = models.JSONField(default=dict, blank=True)
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
    # Preview URL — the manual "point at an already-running app" alternative to preview_start
    # (P3-09bR follow-up). When set, the companion explores THIS URL (a local dev server or a
    # staging site the user keeps running) instead of starting the app itself; auto-start via
    # preview_start is the fallback when this is blank. One URL per repo — running the suite against
    # many environments is a CI/run concern, not authoring. e.g. "http://127.0.0.1:5173".
    preview_url = models.CharField(max_length=512, blank=True, default="")
    provenance = models.JSONField(default=dict, blank=True)    # onboarding origin
    # The repo build PRs target when a work item doesn't pin one (S-13 "Set default";
    # P4.7-T7). The first repo registered on a project is default until reassigned.
    is_default = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name or f"{self.project_id}:{self.role}"


class ProjectCIToken(TenantScopedModel):
    """A per-project CI credential for pushing automated-test results (P3-09bX-1).

    The client's CI pipeline posts its JUnit results to the ingestion endpoint authenticated by
    this token; only the SHA-256 **hash** is stored (the secret is shown once on issue and never
    recoverable). Scoped to results ingestion **only** — deliberately NOT a runner enrollment token
    (CI is not a Claude Code companion). RLS keeps a tenant's tokens isolated (#6). Mirrors the
    RunnerEnrollment token shape (`Status` enum, hashed secret) for consistency."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="ci_tokens"
    )
    label = models.CharField(max_length=120, blank=True)      # e.g. "GitHub Actions"
    token_hash = models.CharField(max_length=128)             # SHA-256 hex; never the secret
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self) -> str:
        return f"ci-token:{self.label or self.id} ({self.status})"
