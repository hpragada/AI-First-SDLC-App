"""P3-09bR-1 — preview-start config resolution (repo-first → profile → empty)."""
import pytest

from apps.projects.models import Project, ProjectProfile, Repository
from apps.projects.preview_config import resolve_preview_start, resolve_preview_url
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


# ── Manual preview URL (P3-09bR follow-up) ──────────────────────────
def test_preview_url_empty_when_unset(world):
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web")
    assert resolve_preview_url(
        tenant_id=world["t"], project_id=world["p"], repo_name="acme/web") == ""


def test_preview_url_resolves_from_repository(world):
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web",
                   preview_url="http://127.0.0.1:5173")
    assert resolve_preview_url(
        tenant_id=world["t"], project_id=world["p"], repo_name="acme/web"
    ) == "http://127.0.0.1:5173"


def test_preview_url_does_not_leak_across_repos(world):
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web",
                   preview_url="http://127.0.0.1:5173")
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/api")
    # The api repo has its own (empty) URL — the web repo's must not leak in.
    assert resolve_preview_url(
        tenant_id=world["t"], project_id=world["p"], repo_name="acme/api") == ""
