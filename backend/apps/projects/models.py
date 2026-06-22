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
    important_context = models.TextField(blank=True)
    version = models.IntegerField(default=1)


class Repository(TenantScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="repositories")
    role = models.CharField(max_length=64)
    code_host_ref = models.CharField(max_length=512, blank=True)
    stack_overrides = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"{self.project_id}:{self.role}"
