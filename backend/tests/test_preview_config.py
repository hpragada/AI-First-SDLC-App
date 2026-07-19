"""P3-09bR-1 — preview-start config resolution (repo-first → profile → empty)."""
import pytest

from apps.projects.models import Project, ProjectProfile, Repository
from apps.projects.preview_config import resolve_preview_start
from apps.projects.repos import add_repository
from apps.tenancy.models import Tenant


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    return {"t": str(t.id), "p": str(p.id)}


def test_resolve_empty_when_nothing_configured(world):
    assert resolve_preview_start(
        tenant_id=world["t"], project_id=world["p"], repo_name="acme/web") == {}


def test_resolve_prefers_repository_over_profile(world):
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web", role="frontend")
    repo = Repository.objects.get(project_id=world["p"], name="acme/web")
    repo.preview_start = {"command": "npm run dev", "port": 5173}
    repo.save(update_fields=["preview_start"])
    ProjectProfile.objects.create(
        tenant_id=world["t"], project_id=world["p"],
        preview_start={"command": "make serve", "port": 8000})

    out = resolve_preview_start(tenant_id=world["t"], project_id=world["p"], repo_name="acme/web")
    assert out == {"command": "npm run dev", "port": 5173}      # repo wins


def test_resolve_falls_back_to_profile(world):
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web")  # no preview_start
    ProjectProfile.objects.create(
        tenant_id=world["t"], project_id=world["p"],
        preview_start={"command": "make serve", "port": 8000})

    out = resolve_preview_start(tenant_id=world["t"], project_id=world["p"], repo_name="acme/web")
    assert out == {"command": "make serve", "port": 8000}


def test_resolve_ignores_other_repos_config(world):
    # A different repo's preview_start must not leak to the one being built.
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web", role="frontend")
    other = Repository.objects.get(project_id=world["p"], name="acme/web")
    other.preview_start = {"command": "npm run dev", "port": 5173}
    other.save(update_fields=["preview_start"])

    # The backend repo has no config and no profile fallback → empty (caller handles fail-loud).
    assert resolve_preview_start(
        tenant_id=world["t"], project_id=world["p"], repo_name="acme/api") == {}
