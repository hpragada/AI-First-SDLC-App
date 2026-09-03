"""Demo seed (P0-T13) — a tenant + user + project + profile + agent specs + a work
item, enough to drive the whole acceptance slice from the UI.

Idempotent: keyed on a *fixed* demo tenant id so it can be re-run safely (and so the
RLS bootstrap has an id to set `app.tenant_id` to before the first insert — the same
chicken-and-egg the API's create_tenant solves). Every write is scoped to the demo
tenant's context so it works under the non-superuser app role with RLS enforced.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem

# Stable ids so re-running the seed updates in place instead of duplicating.
DEMO_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
DEMO_USER_EMAIL = "demo@demo.test"
DEMO_USER_PASSWORD = "demo12345"  # local-dev only; not a secret
DEMO_PROJECT_NAME = "Demo Project"
DEMO_FEATURE_STREAM = "Greenfield MVP"

# The demo user holds the roles the planning gates require (01–03 → product_owner,
# 04 → architect) so the gate-approval screen works end to end out of the box.
_DEMO_ROLES = ["product_owner", "architect"]

_PROFILE_DEFAULTS = {
    "description": "A demo greenfield project for exercising the planning slice.",
    "domain": "Internal tooling",
    "important_context": (
        "This is a demonstration project seeded for the Phase-0 acceptance slice. "
        "Goal: take one idea through ideation → requirements → PRD → architecture, "
        "each gated by a human, with all state in the platform and artifact drafts in S3."
    ),
    # Per-tenant theming (PG23/D10): tokens + responsive breakpoints flow into the manifest.
    "theme": {
        "brand": "default",
        "tokens": {
            "primary-action": "#2563eb",
            "surface": "#ffffff",
            "neutral-900": "#0f172a",
        },
        "breakpoints": [375, 768, 1440],
    },
}


@dataclass
class SeedResult:
    tenant_id: str
    user_id: str
    user_email: str
    project_id: str
    work_item_id: str
    agent_spec_count: int
    connection_count: int
    created: bool  # True if the tenant row was created on this run


def seed_demo() -> SeedResult:
    """Create (or refresh) the demo data. Safe to run repeatedly."""
    with tenant_context(DEMO_TENANT_ID):
        tenant = Tenant.objects.filter(id=DEMO_TENANT_ID).first()
        created = tenant is None
        if tenant is None:
            tenant = Tenant(id=DEMO_TENANT_ID, tenant_id=DEMO_TENANT_ID, name="Demo Tenant")
            tenant.save(force_insert=True)

        # Demo user (create_user hashes the password; reuse if already seeded).
        user = User.objects.filter(email=DEMO_USER_EMAIL).first()
        if user is None:
            user = User.objects.create_user(
                email=DEMO_USER_EMAIL, name="Demo User", tenant=tenant,
                password=DEMO_USER_PASSWORD,
            )

        project, _ = Project.objects.get_or_create(
            tenant=tenant, name=DEMO_PROJECT_NAME,
            defaults={"track": Project.Track.GREENFIELD,
                      "repo_topology": Project.RepoTopology.SINGLE},
        )

        for role in _DEMO_ROLES:
            Membership.objects.get_or_create(
                tenant=tenant, user=user, project=project, role=role
            )

        ProjectProfile.objects.update_or_create(
            tenant=tenant, project=project, defaults=_PROFILE_DEFAULTS
        )

        work_item, _ = WorkItem.objects.get_or_create(
            tenant=tenant, project=project, feature_stream=DEMO_FEATURE_STREAM,
            defaults={"type": WorkItem.Type.STORY, "state": WorkItem.State.PROPOSED},
        )

        seed_agent_specs(tenant)
        spec_count = AgentSpec.objects.filter(tenant=tenant).count()

        # Atlassian connectors for the demo tenant (creds resolve via .env settings).
        from django.conf import settings

        connections = [
            ("docstore", "confluence", {"space_key": settings.CONFLUENCE_SPACE_KEY},
             "settings:atlassian"),
            ("tasktracker", "jira", {"project_key": settings.JIRA_PROJECT_KEY},
             "settings:atlassian"),
            # CodeHost (Phase 2) — repo scope is per-connection; creds resolve via .env.
            ("codehost", "github",
             {"repo": settings.GITHUB_REPO, "default_base": settings.GITHUB_DEFAULT_BASE},
             "settings:github"),
            # DesignSource (Phase 3) — Figma file_key scope; creds resolve via .env.
            ("designsource", "figma",
             {"file_key": settings.FIGMA_FILE_KEY}, "settings:figma"),
            # TestMgmt (Phase 3) — Xray project scope; creds resolve via .env.
            ("testmgmt", "xray",
             {"project_key": settings.XRAY_PROJECT_KEY}, "settings:xray"),
            # CodeIntel (Phase 4) — built-in SOTA analyzer (no creds); Repowise is optional.
            ("codeintel", "builtin", {}, "builtin"),
            # A11yAI (accessibility QA) — the platform's own judge; judgment runs through the
            # ExecutionDriver, so there is no key to resolve. Seeded like codeintel so the
            # capability is available without an onboarding step nobody could complete.
            ("a11yai", "builtin", {}, "builtin"),
        ]
        for capability, connector, scopes, token_ref in connections:
            IntegrationConnection.objects.update_or_create(
                tenant=tenant, capability=capability, connector=connector,
                defaults={"scopes": scopes, "token_ref": token_ref,
                          "health": IntegrationConnection.Health.UNKNOWN},
            )
        connection_count = IntegrationConnection.objects.filter(tenant=tenant).count()

        return SeedResult(
            tenant_id=str(tenant.id), user_id=str(user.id), user_email=user.email,
            project_id=str(project.id), work_item_id=str(work_item.id),
            agent_spec_count=spec_count, connection_count=connection_count, created=created,
        )
