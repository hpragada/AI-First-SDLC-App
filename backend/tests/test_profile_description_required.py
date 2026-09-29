"""F2 — the project profile's description is required, and the platform says so.

The editor refused to save without a description and said nothing at all: the sentence explaining
it had only ever been wired into the design gallery, so Save stopped on its first line, no field
turned red, and every other edit on the page was stuck with it. On a brand-new project — which
lands on this screen straight from Create Project — setup simply never continued.

The team chose to keep the field required and say so. The rule lives on the server as well as the
screen, in the same words, so a direct API call cannot blank the field the editor refuses to blank.
It applies only to requests that actually SEND a description: the endpoint takes partial writes,
and a screen saving only the accessibility block should not have to restate the briefing.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectProfile
from apps.tenancy.models import Membership, Tenant, User

PASSWORD = "profile-pass!"
MESSAGE = "A description is required — agents rely on it for every phase."


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Checkout")
    # Writing the briefing steers every agent that runs on the project, so it takes the same role
    # as managing repositories (S.No 214).
    lead = User.objects.create_user(email="lead@acme.com", name="Lead", tenant=t,
                                    password=PASSWORD)
    Membership.objects.create(tenant=t, user=lead, project=project, role="tech_lead")
    return {"t": t, "project": project}


def _client(world):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": "lead@acme.com", "password": PASSWORD},
                       format="json").status_code == 200
    return client


def _put(world, body):
    return _client(world).put(
        f"/api/projects/{world['project'].id}/profile/", body, format="json",
        HTTP_X_TENANT_ID=str(world["t"].id),
    )


def test_a_blank_description_is_refused_in_the_words_the_screen_uses(world):
    resp = _put(world, {"description": "", "domain": "Personal finance"})
    assert resp.status_code == 400
    assert MESSAGE in str(resp.data["description"][0])
    assert not ProjectProfile.objects.filter(project=world["project"]).exists()


def test_whitespace_is_not_a_description(world):
    assert _put(world, {"description": "   "}).status_code == 400


def test_a_real_description_saves_and_is_trimmed(world):
    resp = _put(world, {"description": "  Expense tracking for individuals.  ",
                        "domain": "Personal finance"})
    assert resp.status_code == 201
    profile = ProjectProfile.objects.get(project=world["project"])
    assert profile.description == "Expense tracking for individuals."
    assert profile.domain == "Personal finance"


def test_a_partial_write_that_never_mentions_the_description_still_works(world):
    """The rule is about blanking the field, not about restating it: a later screen saving one
    other block must not be forced to send the whole briefing back."""
    ProjectProfile.objects.create(tenant=world["t"], project=world["project"],
                                  description="Expense tracking.", important_context="ctx")
    resp = _put(world, {"domain": "Personal finance"})
    assert resp.status_code == 200
    profile = ProjectProfile.objects.get(project=world["project"])
    assert profile.description == "Expense tracking."
    assert profile.domain == "Personal finance"


def test_an_existing_description_cannot_be_wiped(world):
    ProjectProfile.objects.create(tenant=world["t"], project=world["project"],
                                  description="Expense tracking.")
    assert _put(world, {"description": ""}).status_code == 400
    assert ProjectProfile.objects.get(project=world["project"]).description == "Expense tracking."
