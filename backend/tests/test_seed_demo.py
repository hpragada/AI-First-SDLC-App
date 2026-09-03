"""P0-T13 — demo seed: creates the full slice and is safe to re-run."""
import pytest

from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project, ProjectProfile
from apps.projects.seed import DEMO_TENANT_ID, seed_demo
from apps.registry.catalog import ACTIVE_AGENT_CATALOG
from apps.registry.models import AgentSpec
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


@pytest.mark.django_db
def test_seed_demo_creates_full_slice():
    r = seed_demo()
    assert r.created is True
    assert r.tenant_id == str(DEMO_TENANT_ID)
    assert Tenant.objects.filter(id=DEMO_TENANT_ID).exists()
    assert r.agent_spec_count == len(ACTIVE_AGENT_CATALOG)  # retired 00d not seeded

    project = Project.objects.get(id=r.project_id)
    assert project.track == Project.Track.GREENFIELD
    assert ProjectProfile.objects.filter(project=project).exists()
    assert WorkItem.objects.filter(id=r.work_item_id).exists()

    user = User.objects.get(id=r.user_id)
    roles = set(
        Membership.objects.filter(user=user, project=project).values_list("role", flat=True)
    )
    assert {"product_owner", "architect"} <= roles

    assert r.connection_count == 7
    caps = set(
        IntegrationConnection.objects.filter(tenant_id=DEMO_TENANT_ID)
        .values_list("capability", "connector")
    )
    assert caps == {("docstore", "confluence"), ("tasktracker", "jira"),
                    ("codehost", "github"), ("designsource", "figma"),
                    ("testmgmt", "xray"), ("codeintel", "builtin"),
                    ("a11yai", "builtin")}


@pytest.mark.django_db
def test_seed_demo_is_idempotent():
    first = seed_demo()
    second = seed_demo()

    assert second.created is False
    assert second.tenant_id == first.tenant_id
    assert second.project_id == first.project_id
    assert second.work_item_id == first.work_item_id
    assert second.user_id == first.user_id

    # No duplication on the second run.
    assert Tenant.objects.filter(id=DEMO_TENANT_ID).count() == 1
    assert Project.objects.filter(id=first.project_id).count() == 1
    assert ProjectProfile.objects.filter(project_id=first.project_id).count() == 1
    assert WorkItem.objects.filter(id=first.work_item_id).count() == 1
    assert AgentSpec.objects.filter(tenant_id=DEMO_TENANT_ID).count() == \
        len(ACTIVE_AGENT_CATALOG)
    assert Membership.objects.filter(user_id=first.user_id).count() == 2
    assert IntegrationConnection.objects.filter(tenant_id=DEMO_TENANT_ID).count() == 7
