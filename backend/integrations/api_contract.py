"""API-Contract artifact + cross-repo DAG edges (Phase 4 §5 / D4-D5) — the service behind
the migrated 00b Context Bridge.

The cross-repo contract is a single **versioned `api_contract` registry artifact**, read
read-through — never a copied file (it replaces the legacy CONTEXT-BRIDGE). The provider repo's
Export registers / version-bumps it (semver in `external_ref`, idempotent on an unchanged body);
each bump resets it to *draft* for the architect gate (#5). Consumer repos read it read-through
and record a cross-repo **`implements`** `TraceEdge` (an edge across `repo_id`) so contract drift
can compute its change-impact across every consumer. Cross-repo WorkItem dependencies use
`WorkItem.depends_on` across `repo_id`. No new tables — `Artifact.repo`/`version`/`external_ref`,
`TraceEdge.IMPLEMENTS`, and `WorkItem.depends_on` already exist.
"""
from __future__ import annotations

from mcp_platform_state import tools


class ApiContractError(Exception):
    """The API-Contract operation could not proceed."""


def _object_store(injected):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


_CHANGE = {"major", "minor", "patch"}


def _bump(semver: str, change: str) -> str:
    """Semver bump per the 00b version policy (breaking→major, additive→minor, fix→patch)."""
    try:
        major, minor, patch = (int(x) for x in str(semver).split("."))
    except (ValueError, AttributeError):
        major, minor, patch = 1, 0, 0
    if change == "major":
        return f"{major + 1}.0.0"
    if change == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


def _current(tenant_id, project_id):
    """The canonical (latest-version) api_contract artifact for the project, or None."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        return (
            Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, type="api_contract")
            .order_by("-version").first()
        )


def _ensure_derives(tenant_id, contract_id, source_artifact_ids):
    """Link the contract to the source artifacts it was extracted from (deduped)."""
    from apps.registry.models import TraceEdge
    from apps.tenancy.context import tenant_context

    for sid in source_artifact_ids or []:
        with tenant_context(tenant_id):
            exists = TraceEdge.objects.filter(
                tenant_id=tenant_id, from_artifact_id=contract_id,
                to_artifact_id=sid, rel="derives").exists()
        if not exists:
            tools.add_trace_edge(tenant_id, contract_id, sid, "derives")


# ── Export: register / version-bump the contract (provider repo) ────
def export_api_contract(*, tenant_id, project_id, body, change="minor",
                        provider_repo_id=None, source_commit=None, target=None,
                        source_artifact_ids=None, object_store=None) -> dict:
    """Register or version-bump the single `api_contract` artifact (D4). Idempotent on an
    unchanged body; otherwise bumps semver per `change` and resets the artifact to *draft*
    so the architect gate re-approves the new version (gate-then-publish, #5)."""
    if change not in _CHANGE:
        raise ApiContractError("That isn't a kind of contract change the platform recognises.")
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from storage import content_hash

    store = _object_store(object_store)
    digest = content_hash(body.encode("utf-8"))
    with tenant_context(tenant_id):
        Project.objects.get(id=project_id, tenant_id=tenant_id)  # validate + scope
    body_key = f"api_contract/{tenant_id}/{project_id}/contract.md"
    existing = _current(tenant_id, project_id)

    if existing is None:
        store.put(body_key, body)
        art = tools.register_artifact(
            tenant_id, project_id, None, phase="context_bridge", type="api_contract",
            sor="internal", content_hash=digest, s3_key=body_key, repo_id=provider_repo_id,
            external_ref={"semver": "1.0.0", "provider_repo_id": provider_repo_id,
                          "source_commit": source_commit, "target": target},
        )
        _ensure_derives(tenant_id, art["id"], source_artifact_ids)
        tools.log_event(tenant_id, "context_bridge", "api_contract.exported", "artifact",
                        art["id"], {"semver": "1.0.0", "version": 1})
        return {"artifact_id": art["id"], "semver": "1.0.0", "version": 1,
                "bumped": True, "created": True}

    ref = existing.external_ref or {}
    if existing.content_hash == digest:  # unchanged → idempotent, no bump
        return {"artifact_id": str(existing.id), "semver": ref.get("semver", "1.0.0"),
                "version": existing.version, "bumped": False, "created": False,
                "idempotent": True}

    old_semver = ref.get("semver", "1.0.0")
    new_semver = _bump(old_semver, change)
    store.put(body_key, body)
    new_ref = dict(ref)
    new_ref.update({"semver": new_semver, "supersedes": old_semver,
                    "provider_repo_id": provider_repo_id or ref.get("provider_repo_id"),
                    "source_commit": source_commit, "target": target or ref.get("target")})
    tools.update_artifact(tenant_id, str(existing.id), status="draft", content_hash=digest,
                          version=existing.version + 1, external_ref=new_ref)
    _ensure_derives(tenant_id, str(existing.id), source_artifact_ids)
    tools.log_event(tenant_id, "context_bridge", "api_contract.exported", "artifact",
                    str(existing.id), {"semver": new_semver, "supersedes": old_semver,
                                       "version": existing.version + 1, "change": change})
    return {"artifact_id": str(existing.id), "semver": new_semver,
            "version": existing.version + 1, "bumped": True, "created": False, "change": change}


# ── Read-through: consumers read the current contract ───────────────
def read_api_contract(*, tenant_id, project_id) -> dict | None:
    """Read-through the current `api_contract` artifact (the consumer's authoritative source).
    Returns None when no contract is registered yet."""
    cur = _current(tenant_id, project_id)
    return tools.get_artifact(tenant_id, str(cur.id)) if cur is not None else None


# ── Cross-repo DAG edges ────────────────────────────────────────────
def record_implements(*, tenant_id, from_artifact_id, project_id=None,
                      contract_artifact_id=None) -> dict:
    """Record a cross-repo `implements` edge: a consumer's implementing artifact → the
    `api_contract`. Idempotent. Resolves the current contract when no id is given."""
    from apps.registry.models import Artifact, TraceEdge
    from apps.tenancy.context import tenant_context

    if contract_artifact_id is None:
        if project_id is None:
            raise ApiContractError("Say which project, or which contract, this applies to.")
        cur = _current(tenant_id, project_id)
        if cur is None:
            raise ApiContractError(
                "This project has no API contract yet, so there is nothing to implement "
                "against."
            )
        contract_artifact_id = str(cur.id)

    with tenant_context(tenant_id):
        # validate both endpoints belong to the tenant (mirrors add_trace_edge)
        Artifact.objects.get(id=from_artifact_id, tenant_id=tenant_id)
        Artifact.objects.get(id=contract_artifact_id, tenant_id=tenant_id)
        _edge, created = TraceEdge.objects.get_or_create(
            tenant_id=tenant_id, from_artifact_id=from_artifact_id,
            to_artifact_id=contract_artifact_id, rel="implements")
    if created:
        tools.log_event(tenant_id, "context_bridge", "api_contract.implemented", "artifact",
                        contract_artifact_id, {"by": str(from_artifact_id)})
    return {"contract_artifact_id": contract_artifact_id,
            "from_artifact_id": str(from_artifact_id), "created": created}


def cross_repo_dependents(*, tenant_id, contract_artifact_id) -> list[dict]:
    """The consumers implementing a contract — the cross-repo change-impact set (drift input).
    Traverses the `implements` edges into the contract, surfacing each consumer's repo."""
    from apps.registry.models import TraceEdge
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        edges = (
            TraceEdge.objects.filter(
                tenant_id=tenant_id, to_artifact_id=contract_artifact_id, rel="implements")
            .select_related("from_artifact")
        )
        return [{"artifact_id": str(e.from_artifact_id), "type": e.from_artifact.type,
                 "repo_id": str(e.from_artifact.repo_id) if e.from_artifact.repo_id else None,
                 "project_id": str(e.from_artifact.project_id)} for e in edges]


# ── REST layer (P4.7-T9, backs S-27) ─────────────────────────────────
def list_api_contracts(*, tenant_id, project_id) -> list[dict]:
    """List view for S-27's Contracts tab. Today exactly one versioned `api_contract`
    artifact exists per project (D4) — a project with none registered yet returns `[]`."""
    from apps.projects.models import Repository
    from apps.tenancy.context import tenant_context

    cur = _current(tenant_id, project_id)
    if cur is None:
        return []
    ref = cur.external_ref or {}
    provider_repo_id = ref.get("provider_repo_id")
    provider_repo = None
    if provider_repo_id:
        with tenant_context(tenant_id):
            repo = Repository.objects.filter(id=provider_repo_id, tenant_id=tenant_id).first()
        provider_repo = repo.name if repo else None
    return [{
        "artifact_id": str(cur.id), "name": ref.get("target") or "API Contract",
        "version": cur.version, "semver": ref.get("semver"),
        "provider_repo": provider_repo, "status": cur.status,
    }]


def read_api_contract_body(*, tenant_id, project_id, artifact_id, object_store=None) -> dict | None:
    """Read-through the contract's rendered body (S-27 "View" → S-29 preview) from S3 — the
    artifact row is a pointer + hash, never the body (#1/#3). Only the **current** body is ever
    available: each version bump overwrites the same S3 key (D4), so a superseded semver has no
    separate snapshot to read through. `None` when `artifact_id` isn't this project's contract."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    store = _object_store(object_store)
    with tenant_context(tenant_id):
        art = Artifact.objects.filter(
            id=artifact_id, tenant_id=tenant_id, project_id=project_id, type="api_contract"
        ).first()
    if art is None:
        return None
    ref = art.external_ref or {}
    body = store.get(art.s3_key).decode("utf-8") if art.s3_key else ""
    return {
        "artifact_id": str(art.id), "semver": ref.get("semver"), "version": art.version,
        "status": art.status, "provider_repo_id": ref.get("provider_repo_id"), "body": body,
    }


def add_work_item_dependency(*, tenant_id, work_item_id, depends_on_id) -> dict:
    """Record a cross-repo WorkItem dependency via `depends_on` (an edge across repo_id).
    Idempotent; validates both work items belong to the tenant."""
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        wi = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        dep = WorkItem.objects.get(id=depends_on_id, tenant_id=tenant_id)
        added = dep.id not in wi.depends_on
        if added:
            wi.depends_on = [*wi.depends_on, dep.id]
            wi.save(update_fields=["depends_on", "updated_at"])
    return {"work_item_id": str(work_item_id), "depends_on_id": str(depends_on_id),
            "added": added}
