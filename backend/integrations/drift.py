"""Live drift detection + the drift gate (Phase 4 §6 / D6).

Two v1 detectors (semantic/AST diffing deferred):
  1. **Contract drift** — a registered `api_contract` diverges from its consumers (a semver
     bump, or the provider repo's HEAD moving past the contract's `source_commit`).
  2. **Pointer/hash drift** — a registered SoR artifact's external content changed since we
     indexed it, caught by a read-through **content-hash mismatch** against the stored hash.

On detection we write a **`DriftRecord`** + an Event and compute **change-impact via the
traceability graph** (every downstream artifact/repo reachable from the changed node). The
record is decided by a control-plane gate, `decide_drift` — **architect** for contract,
**tech_lead** for pointer/hash — the `Approval`-analog for run-less changes. Nothing is
silently applied to a system of record: **accept** reconciles (re-index / move the pointer),
**reject** flags for revert. Built on the P2 signed-webhook reconcile; it does not reopen it.
"""
from __future__ import annotations

from mcp_platform_state import tools


class DriftError(Exception):
    """A drift operation could not proceed."""


class DriftRoleError(DriftError):
    """The deciding user lacks the required role for the drift gate."""


# ── change-impact via the traceability graph ────────────────────────
def change_impact(tenant_id, artifact_id, *, max_nodes: int = 200) -> list[dict]:
    """Everything downstream of the changed node — the transitive set of artifacts that point
    **into** it (consumers `implements` a contract; outputs `derives` from a source; tests
    `tests` code). Spans repos (a from-node may live in another repo). Capped + cycle-safe."""
    from apps.registry.models import TraceEdge
    from apps.tenancy.context import tenant_context

    impacted: list[dict] = []
    seen: set[str] = {str(artifact_id)}
    frontier = [str(artifact_id)]
    with tenant_context(tenant_id):
        while frontier and len(impacted) < max_nodes:
            current = frontier.pop()
            edges = (
                TraceEdge.objects.filter(tenant_id=tenant_id, to_artifact_id=current)
                .select_related("from_artifact")
            )
            for e in edges:
                a = e.from_artifact
                if str(a.id) in seen:
                    continue
                seen.add(str(a.id))
                impacted.append({"artifact_id": str(a.id), "type": a.type, "rel": e.rel,
                                 "repo_id": str(a.repo_id) if a.repo_id else None})
                frontier.append(str(a.id))
    return impacted


def _open_drift(tenant_id, project_id, artifact_id, kind, required_role, detail) -> tuple:
    """Open (or refresh) the single OPEN DriftRecord for (artifact, kind), with change-impact."""
    from apps.integrations.models import DriftRecord
    from apps.tenancy.context import tenant_context

    impacted = change_impact(tenant_id, artifact_id)
    with tenant_context(tenant_id):
        rec = DriftRecord.objects.filter(
            tenant_id=tenant_id, artifact_id=artifact_id, kind=kind,
            status=DriftRecord.Status.OPEN).first()
        if rec is None:
            rec = DriftRecord.objects.create(
                tenant_id=tenant_id, project_id=project_id, artifact_id=artifact_id,
                kind=kind, required_role=required_role, detail=detail, impacted=impacted)
            created = True
        else:
            rec.detail = detail
            rec.impacted = impacted
            rec.save(update_fields=["detail", "impacted", "updated_at"])
            created = False
    tools.log_event(
        tenant_id, "drift", f"drift.{kind}.detected" if created else f"drift.{kind}.refreshed",
        "drift_record", str(rec.id),
        {"artifact_id": str(artifact_id), "impacted": len(impacted), **detail})
    return rec, created


def _result(rec, created) -> dict:
    return {"drift": True, "drift_id": str(rec.id), "kind": rec.kind, "created": created,
            "required_role": rec.required_role, "impacted": rec.impacted,
            "status": rec.status}


# ── detectors ───────────────────────────────────────────────────────
def detect_pointer_hash_drift(*, tenant_id, artifact_id, observed_hash) -> dict:
    """Read-through hash check: if a registered artifact's current external content hash differs
    from the stored hash, open a **pointer/hash** drift (tech_lead). No mismatch → no drift."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        art = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        project_id, stored, sor = str(art.project_id), art.content_hash, art.sor
    if not observed_hash or observed_hash == stored:
        return {"drift": False, "artifact_id": str(artifact_id)}
    rec, created = _open_drift(
        tenant_id, project_id, str(artifact_id), "pointer_hash", "tech_lead",
        {"stored_hash": stored, "observed_hash": observed_hash, "sor": sor})
    return _result(rec, created)


def detect_contract_drift(*, tenant_id, contract_artifact_id, new_semver=None,
                          source="contract_bump") -> dict:
    """A registered `api_contract` diverged from its consumers → open a **contract** drift
    (architect), with the impacted consumers computed from the `implements` traceability."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        art = Artifact.objects.get(id=contract_artifact_id, tenant_id=tenant_id)
        if art.type != "api_contract":
            # Screen Words group 5. Reached through the push webhook rather than by a person, so
            # this is the one message here a client is unlikely to meet — but it is worded
            # for one anyway, because "unlikely" is not a guarantee and the cost is a sentence.
            raise DriftError(
                "That document isn't an API contract, so contract drift doesn't apply to it."
            )
        project_id = str(art.project_id)
        semver = new_semver or (art.external_ref or {}).get("semver")
    rec, created = _open_drift(
        tenant_id, project_id, str(contract_artifact_id), "contract", "architect",
        {"semver": semver, "source": source})
    return _result(rec, created)


# ── webhook → drift (the live path; built on the P2 reconcile) ──────
def detect_push_contract_drift(*, tenant_id, repo, head_sha) -> list[dict]:
    """A signed `push` to a **provider** repo whose HEAD moved past a registered contract's
    `source_commit` means the code drifted from the contract → open contract drift. Returns the
    drift results (possibly empty). Called from the webhook reconcile after the pointer moves."""
    from apps.projects.models import Repository
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    if not repo or not head_sha:
        return []
    with tenant_context(tenant_id):
        repo_ids = list(
            Repository.objects.filter(tenant_id=tenant_id, name=repo).values_list("id", flat=True))
        if not repo_ids:
            return []
        contracts = list(Artifact.objects.filter(
            tenant_id=tenant_id, type="api_contract"))
    repo_id_set = {str(r) for r in repo_ids}
    out = []
    for art in contracts:
        ref = art.external_ref or {}
        provider = str(ref.get("provider_repo_id") or "")
        if provider in repo_id_set and ref.get("source_commit") != head_sha:
            out.append(detect_contract_drift(
                tenant_id=tenant_id, contract_artifact_id=str(art.id),
                new_semver=ref.get("semver"), source=f"push:{head_sha}"))
    return out


# ── the drift gate (control-plane, run-less Approval-analog) ────────
def decide_drift(*, tenant_id, drift_id, user_id, decision, comment="") -> dict:
    """Decide a drift gate. `decision` is "accept" or "reject". Requires the record's role
    (architect / tech_lead) on the project. Idempotent once decided. **accept** reconciles
    (pointer/hash → re-index to the observed hash); **reject** flags for revert — never a
    silent write to a system of record."""
    from django.utils import timezone

    from apps.integrations.models import DriftRecord
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import Membership

    if decision not in ("accept", "reject"):
        # Screen Words group 5: echoed the rejected value back. The two choices the screen
        # offers are the useful thing to say.
        raise DriftError("A drift decision has to be either accept or reject.")
    with tenant_context(tenant_id):
        rec = DriftRecord.objects.get(id=drift_id, tenant_id=tenant_id)
        if rec.status != DriftRecord.Status.OPEN:
            return {"drift_id": str(rec.id), "status": rec.status, "idempotent": True}
        has_role = Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=rec.project_id,
            role=rec.required_role).exists()
        if not has_role:
            # Screen Words group 3. This sentence reaches the person who clicked Accept, so it
            # names the role rather than its key and drops the internal user id — which told
            # the reader nothing about themselves and everything about our storage.
            from apps.labels import role_label

            raise DriftRoleError(
                f"Only a {role_label(rec.required_role)} on this project can decide this drift.")
        new_status = (DriftRecord.Status.ACCEPTED if decision == "accept"
                      else DriftRecord.Status.REJECTED)
        rec.status = new_status
        rec.decided_by_id = user_id
        rec.decided_at = timezone.now()
        rec.comment = comment
        rec.save(update_fields=["status", "decided_by", "decided_at", "comment", "updated_at"])
        kind, artifact_id, detail = rec.kind, str(rec.artifact_id), rec.detail

    if new_status == DriftRecord.Status.ACCEPTED and kind == "pointer_hash":
        # reconcile: the external change is adopted — re-index the pointer to the new hash
        tools.update_artifact(tenant_id, artifact_id,
                              content_hash=(detail or {}).get("observed_hash", ""))
    action = "drift.accepted" if new_status == DriftRecord.Status.ACCEPTED else "drift.rejected"
    tools.log_event(tenant_id, f"user:{user_id}", action, "drift_record", str(drift_id),
                    {"kind": kind, "decision": decision,
                     "reconciled": new_status == DriftRecord.Status.ACCEPTED})
    return {"drift_id": str(drift_id), "status": new_status, "kind": kind}


def open_drift_records(*, tenant_id, project_id) -> list[dict]:
    """The open drift gates for a project (the review queue)."""
    from apps.integrations.models import DriftRecord
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        return [
            {"drift_id": str(r.id), "kind": r.kind, "required_role": r.required_role,
             "artifact_id": str(r.artifact_id), "impacted": r.impacted, "detail": r.detail}
            for r in DriftRecord.objects.filter(
                tenant_id=tenant_id, project_id=project_id,
                status=DriftRecord.Status.OPEN).order_by("-created_at")
        ]


# ── REST layer (P4.7-T9, backs S-27) ─────────────────────────────────
def drift_queue(*, tenant_id, project_id) -> list[dict]:
    """The open drift queue (S-27 "Drift queue" tab), reshaped from `open_drift_records` to
    the REST wire contract: `id` (not `drift_id`); each impacted consumer keyed `node`/`repo_id`
    (the cross-repo change-impact set)."""
    records = open_drift_records(tenant_id=tenant_id, project_id=project_id)
    return [
        {"id": r["drift_id"], "kind": r["kind"], "required_role": r["required_role"],
         "detail": r["detail"],
         "impacted": [{"node": i["artifact_id"], "repo_id": i["repo_id"], "type": i["type"]}
                     for i in r["impacted"]]}
        for r in records
    ]
