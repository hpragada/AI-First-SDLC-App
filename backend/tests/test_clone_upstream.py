"""E1 — cross-tenant upstream clone (multi-repo test enabler). Copies upstream artifacts +
bodies + trace edges into a new tenant, excludes downstream (Task Breakdown/build) outputs,
and never touches the source."""
import pytest

from apps.projects.management.commands.clone_upstream import clone_upstream_core
from apps.projects.models import Project
from apps.registry.models import Artifact, TraceEdge
from apps.tenancy.models import Tenant
from storage.object_store import InMemoryObjectStore


@pytest.fixture
def world(db):
    src_t = Tenant.objects.create(name="Source")
    src_p = Project.objects.create(tenant=src_t, name="App")
    store = InMemoryObjectStore()
    reqs = Artifact.objects.create(tenant=src_t, project=src_p, phase="requirements",
                                   type="requirements", sor="internal",
                                   s3_key="drafts/s/req.md", content_hash="h1")
    store.put("drafts/s/req.md", b"REQUIREMENTS BODY")
    ux = Artifact.objects.create(tenant=src_t, project=src_p, phase="ux_design",
                                 type="ux_design", sor="internal",
                                 s3_key="drafts/s/ux.html", content_hash="h2")
    store.put("drafts/s/ux.html", b"<html>UX</html>")
    # downstream — must be EXCLUDED from the clone
    Artifact.objects.create(tenant=src_t, project=src_p, phase="task_breakdown",
                            type="backlog", sor="internal", s3_key="drafts/s/backlog.md",
                            content_hash="h3")
    TraceEdge.objects.create(tenant=src_t, from_artifact=ux, to_artifact=reqs, rel="derives")

    dst_t = Tenant.objects.create(name="Target")
    dst_p = Project.objects.create(tenant=dst_t, name="AppMulti")
    return {"src_t": src_t, "src_p": src_p, "dst_t": dst_t, "dst_p": dst_p,
            "store": store, "ux": ux}


def _call(w, dry_run=False):
    return clone_upstream_core(
        from_tenant_id=w["src_t"].id, from_project_id=w["src_p"].id,
        to_tenant_id=w["dst_t"].id, to_project_id=w["dst_p"].id,
        store=w["store"], dry_run=dry_run,
    )


def test_dry_run_reports_without_writing(world):
    r = _call(world, dry_run=True)
    assert r["to_copy"] == 2 and r["skipped_downstream"] == 1 and r["dry_run"] is True
    assert Artifact.objects.filter(tenant=world["dst_t"]).count() == 0  # nothing written


def test_clone_copies_upstream_bodies_edges_and_leaves_source_intact(world):
    r = _call(world)
    assert r["artifacts_copied"] == 2 and r["bodies_copied"] == 2 and r["edges_copied"] == 1
    assert r["body_copy_failures"] == 0

    # target has ONLY the upstream artifacts (backlog excluded)
    types = set(Artifact.objects.filter(tenant=world["dst_t"], project=world["dst_p"])
                .values_list("type", flat=True))
    assert types == {"requirements", "ux_design"}

    # cloned artifact: fresh s3 key, body copied, repo/run cleared, content_hash preserved
    new_ux = Artifact.objects.get(tenant=world["dst_t"], type="ux_design")
    assert new_ux.s3_key and new_ux.s3_key != world["ux"].s3_key
    assert new_ux.repo_id is None and new_ux.run_id is None
    assert new_ux.content_hash == "h2"
    assert world["store"].get(new_ux.s3_key) == b"<html>UX</html>"

    # trace edge re-linked in the target
    assert TraceEdge.objects.filter(tenant=world["dst_t"]).count() == 1

    # SOURCE is untouched (still 3 artifacts + 1 edge, original keys intact)
    assert Artifact.objects.filter(tenant=world["src_t"]).count() == 3
    assert TraceEdge.objects.filter(tenant=world["src_t"]).count() == 1
    assert world["store"].get("drafts/s/ux.html") == b"<html>UX</html>"
