"""Platform-State tool implementations (spec §2).

Every tool is tenant-scoped two ways:
  1. explicit `tenant_id=` filters on every query/write (works under any DB role), and
  2. `tenant_context(tenant_id)` sets app.tenant_id so Postgres RLS is the backstop
     when running as the non-superuser app role.

These are plain functions (easily integration-tested); `server.py` exposes them as MCP
tools and injects the tenant from the launch context.
"""
from __future__ import annotations

from apps.clarifications.models import Clarification
from apps.ledger.models import Event
from apps.projects.models import Project, Repository
from apps.registry.models import Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem


# ── serialization (JSON-safe dicts) ─────────────────────────────────
def _dt(value):
    return value.isoformat() if value else None


def _artifact(a: Artifact) -> dict:
    return {
        "id": str(a.id),
        "tenant_id": str(a.tenant_id),
        "project_id": str(a.project_id),
        "repo_id": str(a.repo_id) if a.repo_id else None,
        "run_id": str(a.run_id) if a.run_id else None,
        "phase": a.phase,
        "type": a.type,
        "status": a.status,
        "sor": a.sor,
        "external_ref": a.external_ref,
        "s3_key": a.s3_key,
        "content_hash": a.content_hash,
        "version": a.version,
        "created_at": _dt(a.created_at),
        "updated_at": _dt(a.updated_at),
    }


def _work_item(w: WorkItem) -> dict:
    return {
        "id": str(w.id),
        "tenant_id": str(w.tenant_id),
        "project_id": str(w.project_id),
        "repo_id": str(w.repo_id) if w.repo_id else None,
        "feature_stream": w.feature_stream,
        "title": w.title,
        "description": w.description,
        "type": w.type,
        "state": w.state,
        "parent_id": str(w.parent_id) if w.parent_id else None,
        "depends_on": [str(x) for x in w.depends_on],
        "assignee_id": str(w.assignee_id) if w.assignee_id else None,
        "takeover_flag": w.takeover_flag,
        "external_ref": w.external_ref,
    }


def _event(e: Event) -> dict:
    return {
        "id": str(e.id),
        "actor": e.actor,
        "action": e.action,
        "target_type": e.target_type,
        "target_id": str(e.target_id) if e.target_id else None,
        "ts": _dt(e.ts),
        "payload": e.payload,
    }


def _edge(edge: TraceEdge) -> dict:
    return {
        "id": str(edge.id),
        "from_artifact_id": str(edge.from_artifact_id),
        "to_artifact_id": str(edge.to_artifact_id),
        "rel": edge.rel,
    }


def _repo(r: Repository) -> dict:
    """The repository a run targets — its identity, role, base branch, and per-repo stack
    overrides. Rendered into the manifest's `# Repository` section (per-repo scoping, D5)."""
    return {
        "repo_id": str(r.id),
        "name": r.name,
        "role": r.role,
        "default_base": r.default_base,
        "connector": r.connector,
        "stack_overrides": r.stack_overrides or {},
    }


def _clarification(c: Clarification) -> dict:
    """An answered clarification, replayed into the manifest so the agent reuses the human's
    answer instead of re-asking (req #2 durability)."""
    return {
        "phase": c.phase,
        "context": c.context,
        "questions": c.questions,
        "answers": c.answers,
    }


def _profile(project: Project) -> dict:
    p = getattr(project, "profile", None)
    return {
        "project_id": str(project.id),
        "name": project.name,
        "track": project.track,
        "repo_topology": project.repo_topology,
        "description": p.description if p else "",
        "domain": p.domain if p else "",
        "tech_stack": p.tech_stack if p else {},
        "coding_standards": p.coding_standards if p else {},
        "nfrs": p.nfrs if p else {},
        "constraints": p.constraints if p else {},
        "glossary": p.glossary if p else {},
        "theme": p.theme if p else {},
        "important_context": p.important_context if p else "",
        "version": p.version if p else 0,
    }


# ── tools (spec §2 signatures; tenant_id is the bound scope) ─────────
def get_context(tenant_id, project_id, phase, work_item_id=None, repo_id=None) -> dict:
    """Inputs the Manifest Composer renders, incl. Knowledge-Index retrieval (Phase 4).

    **Per-repo scoping (D5).** When the run targets a repo (explicit `repo_id`, else the work
    item's repo), `relevant_artifacts` is scoped to that repo: its own artifacts **+** the
    repo-agnostic project-level ones (no repo) **+** the shared cross-repo `api_contract`
    (always in scope, whatever repo authored it). The registry, traceability, and the
    Knowledge Index stay **project-scoped shared memory across repos** — knowledge retrieval
    is project-wide, never siloed per repo. Single-repo / repo-less runs are unchanged.
    """
    from django.db.models import Q

    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        wi = (
            WorkItem.objects.filter(id=work_item_id, tenant_id=tenant_id).first()
            if work_item_id else None
        )
        scope_repo_id = repo_id or (wi.repo_id if wi else None)
        repo = (
            Repository.objects.filter(id=scope_repo_id, tenant_id=tenant_id).first()
            if scope_repo_id else None
        )

        artifacts_qs = Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if repo is not None:
            # this repo + repo-agnostic project artifacts + the shared cross-repo contract
            artifacts_qs = artifacts_qs.filter(
                Q(repo_id=repo.id) | Q(repo_id__isnull=True) | Q(type="api_contract")
            )
        artifacts = artifacts_qs.order_by("-created_at")[:50]
        events = Event.objects.filter(tenant_id=tenant_id).order_by("-ts")[:20]
        query = " ".join(filter(None, [phase, getattr(wi, "title", ""),
                                       getattr(wi, "description", "")]))
        # Answered clarifications for this work item are replayed into the manifest so a
        # re-dispatched run (e.g. after a companion restart) never re-asks (req #2 durability).
        answered = (
            Clarification.objects.filter(
                tenant_id=tenant_id, work_item_id=wi.id,
                status=Clarification.Status.ANSWERED,
            ).order_by("answered_at")
            if wi is not None else []
        )
        return {
            "profile": _profile(project),
            "repo": _repo(repo) if repo is not None else None,
            # Knowledge Index = project-scoped shared memory (D5) — retrieve across all repos.
            "relevant_artifacts": [_artifact(a) for a in artifacts],
            "recent_events": [_event(e) for e in events],
            "retrieved_knowledge": _retrieve_knowledge(tenant_id, project_id, query),
            "answered_clarifications": [_clarification(c) for c in answered],
        }


def _retrieve_knowledge(tenant_id, project_id, query) -> list[dict]:
    """Knowledge-Index retrieval (Phase 4) — **project-scoped shared memory across repos**
    (D5), so a run in one repo can still retrieve another repo's knowledge + the shared
    contract. Best-effort: a retrieval hiccup never breaks context composition."""
    try:
        from apps.knowledge.index import retrieve

        return retrieve(tenant_id, project_id=project_id, query=query, k=8)
    except Exception:  # noqa: BLE001
        return []


def register_artifact(
    tenant_id, project_id, run_id, phase, type, sor,
    content_hash, s3_key=None, external_ref=None, repo_id=None,
) -> dict:
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        run = Run.objects.get(id=run_id, tenant_id=tenant_id) if run_id else None
        repo = (
            Repository.objects.get(id=repo_id, tenant_id=tenant_id) if repo_id else None
        )
        if sor not in Artifact.SoR.values:
            raise ValueError(f"invalid sor: {sor}")
        # Version across re-registrations (Bugs.xlsx row 28.2): a fresh row per run/remediation
        # loop shares (project, phase, type) with its predecessors. Number it one past the
        # highest existing sibling so re-running a phase yields v2, v3, … instead of another v1.
        # Only the integer counter — still a pointer row, no content stored (#1/#3).
        last = (
            Artifact.objects.filter(
                tenant_id=tenant_id, project=project, phase=phase, type=type
            )
            .order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        artifact = Artifact.objects.create(
            tenant_id=tenant_id,
            project=project,
            run=run,
            repo=repo,
            phase=phase,
            type=type,
            sor=sor,
            content_hash=content_hash or "",
            s3_key=s3_key or "",
            external_ref=external_ref,
            version=(last or 0) + 1,
        )
        return _artifact(artifact)


def update_artifact(
    tenant_id, artifact_id, status=None, sor=None,
    external_ref=None, content_hash=None, version=None,
) -> dict:
    with tenant_context(tenant_id):
        artifact = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        if status is not None:
            if status not in Artifact.Status.values:
                raise ValueError(f"invalid status: {status}")
            artifact.status = status
        if sor is not None:
            if sor not in Artifact.SoR.values:
                raise ValueError(f"invalid sor: {sor}")
            artifact.sor = sor
        if external_ref is not None:
            artifact.external_ref = external_ref
        if content_hash is not None:
            artifact.content_hash = content_hash
        if version is not None:
            artifact.version = version
        artifact.save()
        return _artifact(artifact)


def add_trace_edge(tenant_id, from_artifact_id, to_artifact_id, rel) -> dict:
    with tenant_context(tenant_id):
        if rel not in TraceEdge.Rel.values:
            raise ValueError(f"invalid rel: {rel}")
        # Validate both endpoints belong to the tenant.
        Artifact.objects.get(id=from_artifact_id, tenant_id=tenant_id)
        Artifact.objects.get(id=to_artifact_id, tenant_id=tenant_id)
        edge = TraceEdge.objects.create(
            tenant_id=tenant_id,
            from_artifact_id=from_artifact_id,
            to_artifact_id=to_artifact_id,
            rel=rel,
        )
        return _edge(edge)


def log_event(tenant_id, actor, action, target_type, target_id, payload=None) -> dict:
    with tenant_context(tenant_id):
        event = Event.objects.create(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload or {},
        )
        return _event(event)


def list_work_items(tenant_id, project_id, state=None) -> list[dict]:
    with tenant_context(tenant_id):
        qs = WorkItem.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if state is not None:
            if state not in WorkItem.State.values:
                raise ValueError(f"invalid state: {state}")
            qs = qs.filter(state=state)
        return [_work_item(w) for w in qs.order_by("created_at")]


def create_work_item(
    tenant_id, project_id, type, title, description="",
    parent_id=None, feature_stream="", depends_on=None,
) -> dict:
    """Propose a WorkItem (state=proposed) — the backlog the Task-Breakdown agent emits.
    Reconciliation later pushes proposed→accepted into the TaskTracker SoR (#5/B1)."""
    with tenant_context(tenant_id):
        if type not in WorkItem.Type.values:
            raise ValueError(f"invalid type: {type}")
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        parent = (
            WorkItem.objects.get(id=parent_id, tenant_id=tenant_id) if parent_id else None
        )
        work_item = WorkItem.objects.create(
            tenant_id=tenant_id, project=project, type=type, title=title,
            description=description or "", feature_stream=feature_stream or "",
            parent=parent, depends_on=depends_on or [],
            state=WorkItem.State.PROPOSED,
        )
        return _work_item(work_item)


def transition_work_item(tenant_id, work_item_id, to_state) -> dict:
    with tenant_context(tenant_id):
        if to_state not in WorkItem.State.values:
            raise ValueError(f"invalid state: {to_state}")
        work_item = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        work_item.state = to_state
        work_item.save(update_fields=["state", "updated_at"])
        return _work_item(work_item)


def get_artifact(tenant_id, artifact_id) -> dict:
    with tenant_context(tenant_id):
        return _artifact(Artifact.objects.get(id=artifact_id, tenant_id=tenant_id))


def list_artifacts(tenant_id, project_id, phase=None, status=None) -> list[dict]:
    with tenant_context(tenant_id):
        qs = Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if phase is not None:
            qs = qs.filter(phase=phase)
        if status is not None:
            if status not in Artifact.Status.values:
                raise ValueError(f"invalid status: {status}")
            qs = qs.filter(status=status)
        return [_artifact(a) for a in qs.order_by("-created_at")]


def detect_drift(tenant_id, artifact_id) -> dict:
    """P0 stub — always drift=False. Real comparison vs the SoR arrives in Phase 4."""
    with tenant_context(tenant_id):
        artifact = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        return {
            "drift": False,
            "current_version": artifact.version,
            "registered_version": artifact.version,
        }
