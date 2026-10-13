"""Bugs S.No 224 — "published this week" must count by publish date, not by draft date.

The dashboard's count and its recent-publishes list both filtered on `created_at`, which is when
the AGENT DRAFTED the artifact. Drafting and publishing are separated by a review gate, so they
are routinely days apart: something drafted eight days ago and published this morning never
appeared in a list of this week's publishes, while something drafted today and never published
did. There was no publish timestamp on the record at all — `updated_at` is `auto_now`, so it moves
on any later edit and cannot stand in.

`published_at` is stamped at the one choke point every `tools.*` status write goes through, and
at each exit of the manual publish endpoint. Only on the TRANSITION into published, so a
re-export never re-dates history into the current week.
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from mcp_platform_state import tools
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform", track="greenfield",
                                     repo_topology="single")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    user = User.objects.create_user(email="sarah@acme.com", name="Sarah", tenant=t,
                                    password="s3cret-pass!")
    Membership.objects.create(tenant=t, user=user, project=project, role="product_owner")
    return {"t": t, "project": project, "wi": wi, "run": run, "user": user}


def _artifact(world, *, title="PRD — Checkout", status=Artifact.Status.DRAFT, created_days_ago=0):
    art = Artifact.objects.create(
        tenant=world["t"], project=world["project"], run=world["run"], phase="03_prd",
        type="prd", sor="internal", title=title, status=status, content_hash="h",
        s3_key="k",
    )
    if created_days_ago:
        # `created_at` is auto_now_add, so it can only be moved by a queryset update.
        Artifact.objects.filter(id=art.id).update(
            created_at=timezone.now() - timedelta(days=created_days_ago))
        art.refresh_from_db()
    return art


def _client(world):
    client = APIClient()
    r = client.post("/api/auth/login/", {"email": "sarah@acme.com",
                                         "password": "s3cret-pass!"}, format="json")
    assert r.status_code == 200, r.data
    return client


# ── the stamp ───────────────────────────────────────────────────────
def test_a_fresh_artifact_has_no_publish_date(world):
    assert _artifact(world).published_at is None


def test_publishing_through_the_tool_stamps_the_date(world):
    art = _artifact(world)
    before = timezone.now()

    tools.update_artifact(str(world["t"].id), str(art.id), status=Artifact.Status.PUBLISHED)

    art.refresh_from_db()
    assert art.published_at is not None and art.published_at >= before


def test_a_later_edit_never_re_dates_a_publication(world):
    art = _artifact(world)
    tools.update_artifact(str(world["t"].id), str(art.id), status=Artifact.Status.PUBLISHED)
    art.refresh_from_db()
    first = art.published_at

    tools.update_artifact(str(world["t"].id), str(art.id), content_hash="h2")
    tools.update_artifact(str(world["t"].id), str(art.id), status=Artifact.Status.PUBLISHED)

    art.refresh_from_db()
    assert art.published_at == first


def test_moving_to_a_non_published_status_never_stamps(world):
    art = _artifact(world)
    tools.update_artifact(str(world["t"].id), str(art.id), status=Artifact.Status.APPROVED)
    art.refresh_from_db()
    assert art.published_at is None


def test_the_manual_publish_endpoint_stamps_the_date(world):
    art = _artifact(world, status=Artifact.Status.APPROVED)
    client = _client(world)

    r = client.post(f"/api/artifacts/{art.id}/publish/", {"target_capability": "internal"},
                    format="json")

    assert r.status_code == 200, r.data
    art.refresh_from_db()
    assert art.status == Artifact.Status.PUBLISHED and art.published_at is not None


def test_re_publishing_keeps_the_original_date(world):
    """A re-export must not silently move an old publication into this week."""
    art = _artifact(world, status=Artifact.Status.APPROVED)
    client = _client(world)
    client.post(f"/api/artifacts/{art.id}/publish/", {"target_capability": "internal"},
                format="json")
    art.refresh_from_db()
    first = art.published_at

    client.post(f"/api/artifacts/{art.id}/publish/", {"target_capability": "internal"},
                format="json")

    art.refresh_from_db()
    assert art.published_at == first


# ── what the dashboard now counts ───────────────────────────────────
def _dashboard(world):
    client = _client(world)
    r = client.get(f"/api/projects/{world['project'].id}/dashboard/")
    assert r.status_code == 200, r.data
    return r.data


def test_something_drafted_last_week_and_published_today_is_counted(world):
    """The reported symptom. On `created_at` this row was invisible in a list of this week's
    publishes even though publishing it today is the event being counted."""
    art = _artifact(world, status=Artifact.Status.APPROVED, created_days_ago=8)
    tools.update_artifact(str(world["t"].id), str(art.id), status=Artifact.Status.PUBLISHED)

    data = _dashboard(world)

    assert data["health"]["published_week"] == 1
    assert [p["artifact_id"] for p in data["recent_publishes"]] == [str(art.id)]


def test_something_drafted_today_but_never_published_is_not_counted(world):
    _artifact(world, status=Artifact.Status.APPROVED)

    data = _dashboard(world)

    assert data["health"]["published_week"] == 0
    assert data["recent_publishes"] == []


def test_a_publication_older_than_the_window_drops_out(world):
    art = _artifact(world)
    tools.update_artifact(str(world["t"].id), str(art.id), status=Artifact.Status.PUBLISHED)
    Artifact.objects.filter(id=art.id).update(
        published_at=timezone.now() - timedelta(days=9))

    data = _dashboard(world)

    assert data["health"]["published_week"] == 0


def test_recent_publishes_are_ordered_by_when_they_were_published(world):
    older = _artifact(world, title="PRD — Login")
    newer = _artifact(world, title="PRD — Checkout", created_days_ago=6)
    tools.update_artifact(str(world["t"].id), str(older.id), status=Artifact.Status.PUBLISHED)
    tools.update_artifact(str(world["t"].id), str(newer.id), status=Artifact.Status.PUBLISHED)

    data = _dashboard(world)

    # `newer` was drafted first but published last, so it leads — on `created_at` ordering the
    # list read the other way round.
    assert [p["artifact_id"] for p in data["recent_publishes"]] == [str(newer.id), str(older.id)]
