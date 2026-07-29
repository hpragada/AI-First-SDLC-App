"""Platform-State tool implementations (spec §2).

Every tool is tenant-scoped two ways:
  1. explicit `tenant_id=` filters on every query/write (works under any DB role), and
  2. `tenant_context(tenant_id)` sets app.tenant_id so Postgres RLS is the backstop
     when running as the non-superuser app role.

These are plain functions (easily integration-tested); `server.py` exposes them as MCP
tools and injects the tenant from the launch context.
"""
from __future__ import annotations

import base64

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
        "title": a.title,
        "status": a.status,
        "sor": a.sor,
        "external_ref": a.external_ref,
        "s3_key": a.s3_key,
        "content_hash": a.content_hash,
        "version": a.version,
        "created_at": _dt(a.created_at),
        "updated_at": _dt(a.updated_at),
    }


# external_ref keys that are small pointers/metadata (safe to inline in a LIST of artifacts).
# Everything else an agent stuffed into external_ref is CONTENT (structured bodies, inline HTML,
# long prose) — fetched on demand via get_artifact / get_artifact_body, never dumped into a
# 50-artifact listing where it blows the MCP token budget (#1/#3: list = pointers, not bodies).
_POINTER_REF_KEYS = {
    "id", "key", "url", "title", "sor", "format", "project", "project_id", "run_id",
    "work_item_id", "repo_id", "space", "space_key", "screen_id", "screen_name", "route",
    "persona", "status", "count",
}
_MAX_POINTER_STR = 300


def _lean_ref(ref):
    """Reduce an external_ref to pointers only, so listing many artifacts stays small. Keeps
    known small metadata keys and, for multi-state wireframes, the states' name+s3_key+hash
    (already pointers) — drops every large/structured value (fetch it via get_artifact_body)."""
    if not isinstance(ref, dict):
        return ref
    out = {}
    for k, v in ref.items():
        if k == "states" and isinstance(v, list):
            out["states"] = [
                {kk: sv.get(kk) for kk in ("name", "s3_key", "content_hash") if kk in sv}
                for sv in v if isinstance(sv, dict)
            ]
        elif (k in _POINTER_REF_KEYS and isinstance(v, (str, int, float, bool))
              and len(str(v)) <= _MAX_POINTER_STR):
            out[k] = v
    return out


def _artifact_pointer(a: Artifact) -> dict:
    """Pointer-only view for get_context / list_artifacts (many artifacts at once). Same shape
    as _artifact but with the body content stripped out of external_ref so the aggregate stays
    within the MCP token budget; agents fetch bodies on demand with get_artifact_body."""
    d = _artifact(a)
    d["external_ref"] = _lean_ref(a.external_ref)
    return d


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
        "is_default": r.is_default,
        "stack_overrides": r.stack_overrides or {},
    }


def _repo_brief(r: Repository) -> dict:
    """A project's repo as an assignment *option* (Task Breakdown reads these to pick a repo
    per work item). Lean — identity + role + base + default flag, no stack overrides."""
    return {
        "repo_id": str(r.id),
        "name": r.name,
        "role": r.role,
        "default_base": r.default_base,
        "is_default": r.is_default,
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


#: Actions that belong in the run console but NOT in an agent's `# Recent Events`.
#: `artifact.registered` fires once per artifact — a run that registers 90 test cases would
#: otherwise fill the whole 20-event window of the NEXT run's manifest with the previous run's
#: bookkeeping, pushing out the gate decisions and phase transitions that actually inform an
#: agent. It is also pure duplication there: `# Relevant Artifacts` already lists every
#: artifact. The ledger keeps them; the manifest just doesn't repeat them.
_MANIFEST_MUTED_ACTIONS = {"artifact.registered"}

#: How many recent artifacts to include as the "situational tail" — peripheral awareness on top
#: of an agent's guaranteed required tier (Bugs S.No 190). The required inputs are always present
#: and never counted against this; only this recency window is capped.
_SITUATIONAL_TAIL = 12


# ── tools (spec §2 signatures; tenant_id is the bound scope) ─────────
def get_context(tenant_id, project_id, phase, work_item_id=None, repo_id=None) -> dict:
    """Inputs the Manifest Composer renders, incl. Knowledge-Index retrieval (Phase 4).

    **Dependency-driven artifacts (Bugs S.No 190).** `relevant_artifacts` is a *required tier*
    (the latest version of each type the running agent declares in its catalog `needs_artifacts`,
    resolved from `phase`) that is always present and never evicted, followed by a small capped
    situational-recency tail. Each pointer carries `required: bool`; `missing_required_artifacts`
    lists declared types with no artifact yet. Anything else the agent pulls on demand by type
    via `list_artifacts(type=…)` → `get_artifact_body`.

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

        # All repos on the project — the assignment *options* a project-level planning run
        # (e.g. Task Breakdown) classifies each work item against. Empty for single-repo/
        # no-repo projects; the agent then leaves repo unset and the default repo is used.
        all_repos = Repository.objects.filter(
            tenant_id=tenant_id, project_id=project_id
        ).order_by("-is_default", "role", "name")

        # Dependency-driven selection (Bugs S.No 190). Replaces the old "newest 50 → cap 20"
        # recency slice, which could evict an agent's oldest-but-required upstream inputs.
        from apps.registry.catalog import needs_artifacts_for

        needs = needs_artifacts_for(phase)
        base_qs = Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if repo is not None:
            # this repo + repo-agnostic project artifacts + the shared cross-repo contract
            base_qs = base_qs.filter(
                Q(repo_id=repo.id) | Q(repo_id__isnull=True) | Q(type="api_contract")
            )
        # Required tier: the latest version of each declared upstream type is ALWAYS injected
        # and never evicted, so a late phase gets its named inputs regardless of how many newer
        # artifacts exist. A declared type with no artifact yet is surfaced (missing_types) so
        # the agent treats it as a gap per # Rules instead of silently proceeding.
        required, required_ids, missing_types = [], set(), []
        for t in needs:
            a = base_qs.filter(type=t).order_by("-version", "-created_at").first()
            if a is not None:
                required.append(a)
                required_ids.add(a.id)
            else:
                missing_types.append(t)
        # Situational tail: a small recency window for peripheral awareness, excluding anything
        # already pinned in the required tier and capped (team-approved: keep a safe tail).
        tail = list(
            base_qs.exclude(id__in=required_ids).order_by("-created_at")[:_SITUATIONAL_TAIL]
        )
        artifacts = required + tail
        events = (
            Event.objects.filter(tenant_id=tenant_id)
            .exclude(action__in=_MANIFEST_MUTED_ACTIONS)
            .order_by("-ts")[:20]
        )
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
            # The project's repos as assignment options (D5 multi-repo) — Task Breakdown reads
            # these to pick a repo per work item; the reviewer confirms at the gate.
            "repositories": [_repo_brief(r) for r in all_repos],
            # Knowledge Index = project-scoped shared memory (D5) — retrieve across all repos.
            # Pointers only (bodies fetched via get_artifact_body) so many artifacts with large
            # external_ref bodies don't blow the MCP token budget (Bugs.xlsx row 69).
            "relevant_artifacts": [
                {**_artifact_pointer(a), "required": a.id in required_ids} for a in artifacts
            ],
            # Declared inputs with no artifact yet — the composer renders these as a named gap.
            "missing_required_artifacts": missing_types,
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


#: Types whose every artifact MUST own its body. A `test_case` is exported to the TestMgmt SoR
#: one issue per artifact (`export_tests.parse_test_case` reads the body for that issue's
#: summary + steps), so two test cases sharing a body is not a cosmetic problem: `create_test`
#: is idempotent BY SUMMARY, so a batch body gives every artifact in it the same summary and the
#: whole batch silently collapses into ONE Xray issue with the batch's merged steps — 23 test
#: cases exported as 1, all marked published. Deliberately narrow: types that legitimately share
#: or omit a body (e.g. a wireframe's per-state keys in external_ref) are not listed.
_OWN_BODY_REQUIRED_TYPES = {"test_case"}


def _assert_body_not_shared(tenant_id, run, type, s3_key, title) -> None:
    """Fail loud when a per-item artifact points at a body another sibling already claimed.

    Scoped to a *different title* on purpose: re-registering the SAME test case (v2 of
    "TC-001 — …") legitimately reuses its own body — the version counter is title-scoped for
    exactly that reason — while TC-002 pointing at TC-001's body is the defect.
    """
    if not s3_key or run is None or type not in _OWN_BODY_REQUIRED_TYPES:
        return
    clash = (
        Artifact.objects.filter(tenant_id=tenant_id, run=run, type=type, s3_key=s3_key)
        .exclude(title=title or "")
        .order_by("created_at")            # name the body's ORIGINAL owner, not an arbitrary
        .values_list("title", flat=True)   # sibling (Artifact has no Meta ordering)
        .first()
    )
    if clash is not None:
        raise ValueError(
            f"{type} body is already claimed by another artifact in this run: s3_key "
            f"{s3_key!r} belongs to {clash!r}. Every {type} must own its body — stage one "
            f"body per {type} (one stage_artifact_body call each, named for that item alone, "
            f"e.g. 'tc-001' then 'tc-002') and register each with the s3_key and content_hash "
            f"that call returned. Batching several {type}s into one body collapses them into a "
            f"single test in the test-management system."
        )


def register_artifact(
    tenant_id, project_id, run_id, phase, type, sor,
    content_hash, s3_key=None, external_ref=None, repo_id=None, title="", supersedes=None,
) -> dict:
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        # `supersedes` anchors this registration to an EXISTING artifact's identity (Part B fix 2).
        # Versioning keys on (project, phase, type, title), so a caller that means "this is the
        # next version of that document" had to reproduce all three strings exactly — and an agent
        # echoing a title back byte-for-byte is not something the platform can rely on. One
        # character of drift silently forks a second artifact instead of versioning the first.
        # Naming the target id instead makes the link explicit: the platform reads the identity
        # off the target rather than trusting the caller to restate it.
        if supersedes:
            target = Artifact.objects.get(id=supersedes, tenant_id=tenant_id)
            if str(target.project_id) != str(project.id):
                raise ValueError("supersedes must name an artifact in the same project")
            phase, type, title = target.phase, target.type, target.title
        run = Run.objects.get(id=run_id, tenant_id=tenant_id) if run_id else None
        repo = (
            Repository.objects.get(id=repo_id, tenant_id=tenant_id) if repo_id else None
        )
        if sor not in Artifact.SoR.values:
            raise ValueError(f"invalid sor: {sor}")
        _assert_body_not_shared(tenant_id, run, type, s3_key, title)
        # Version across re-registrations (Bugs.xlsx row 28.2): re-running a phase should yield
        # v2, v3, … of the SAME artifact. But per-item types (adr, test_case, security_finding,
        # code, code_review, test_report) register many DISTINCT rows sharing (phase, type) in one
        # run — versioning by (phase, type) alone falsely numbered them as supersessions of each
        # other (Bugs S.No 120, Part C-1). Scope the counter to the human `title` when present so
        # distinct siblings each start at v1; fall back to (phase, type) for untitled/singletons.
        version_filter = {"tenant_id": tenant_id, "project": project,
                          "phase": phase, "type": type}
        if title:
            version_filter["title"] = title
        last = (
            Artifact.objects.filter(**version_filter)
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
            title=title or "",
            sor=sor,
            content_hash=content_hash or "",
            s3_key=s3_key or "",
            external_ref=external_ref,
            version=(last or 0) + 1,
        )
        _log_artifact_registered(tenant_id, run, artifact)
        return _artifact(artifact)


def _log_artifact_registered(tenant_id, run, artifact) -> None:
    """Stream the agent's progress to the run console.

    Until this existed only orchestrator-level events reached the ledger, so a phase went
    silent between `phase.dispatched` and `phase.reported` — 25 minutes and 90 artifacts of
    nothing, during which a user cannot tell a working run from a dead one (and killed healthy
    runs to find out).

    **Targeted at the RUN, not the artifact**, because that is what the console streams
    (`?target_type=run&target_id=…`); an artifact-targeted event would be invisible there,
    which is the whole point. The artifact id travels in the payload instead — the same
    convention `test.quarantined` uses for a non-UUID subject.

    `payload["message"]` is pre-rendered because the event serializer looks for `message`
    first and has no `type`/`title` key, so without it every line would read a bare "Artifact
    registered". Structured `type`/`title`/`artifact_id` ride along for machine consumers.
    """
    if run is None:
        return          # no run ⇒ no console to stream to; the row's own provenance stands
    label = " — ".join(p for p in (artifact.type, artifact.title) if p)
    log_event(
        tenant_id, "agent", "artifact.registered", "run", str(run.id),
        {"artifact_id": str(artifact.id), "type": artifact.type,
         "title": artifact.title, "phase": artifact.phase, "message": label},
    )


def update_artifact(
    tenant_id, artifact_id, status=None, sor=None,
    external_ref=None, content_hash=None, version=None, title=None, type=None,
) -> dict:
    with tenant_context(tenant_id):
        artifact = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        if title is not None:
            artifact.title = title
        # Reclassify an artifact's lifecycle type. Used by the onboarding adopt gate to turn a
        # generic extracted `document` into its declared type (requirements/prd/architecture/…)
        # so the gap report recognises it as phase evidence (Brownfield B2-1). Type is free-text
        # (no DB enum), so no validation constraint here — callers pass a canonical value.
        if type is not None:
            artifact.type = type
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


def submit_gap_report(tenant_id, project_id, phases, resume_phase=None, blockers=None) -> dict:
    """Agent-authored gap report (00_onboarding). Hands the agent's reasoned per-phase assessment
    to the shared normalizer+writer, which coerces it to the exact `external_ref` shape
    `read_gap_report` + the whole UI depend on — so a model typo can never degrade the screen.
    The bound `project_id` travels from the run; `tenant_id` is bound server-side."""
    from integrations.onboarding import submit_agent_gap_report

    return submit_agent_gap_report(
        tenant_id=tenant_id, project_id=project_id, phases=phases,
        resume_phase=resume_phase, blockers=blockers,
    )


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
    repo_id=None, assignment_rationale="", assignment_confidence="",
) -> dict:
    """Propose a WorkItem (state=proposed) — the backlog the Task-Breakdown agent emits.
    Reconciliation later pushes proposed→accepted into the TaskTracker SoR (#5/B1).

    Multi-repo (D5, Hybrid Option C): `repo_id` pins the work item to one of the project's
    repositories (chosen from get_context's `repositories`). Optional — single-repo / repo-less
    projects leave it unset and the default repo is used at build time. The agent's choice is a
    *draft*: `assignment_rationale` / `assignment_confidence` are stored on
    `external_ref.repo_assignment` so the reviewer can confirm or override it at the Task
    Breakdown gate before it is locked for implementation.
    """
    with tenant_context(tenant_id):
        if type not in WorkItem.Type.values:
            raise ValueError(f"invalid type: {type}")
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        parent = (
            WorkItem.objects.get(id=parent_id, tenant_id=tenant_id) if parent_id else None
        )
        repo = None
        if repo_id:
            repo = Repository.objects.filter(
                id=repo_id, tenant_id=tenant_id, project_id=project_id
            ).first()
            if repo is None:
                raise ValueError(f"repo {repo_id} is not a repository on this project")
        external_ref: dict = {}
        if repo is not None or assignment_rationale or assignment_confidence:
            external_ref["repo_assignment"] = {
                "suggested_repo_id": str(repo.id) if repo is not None else None,
                "rationale": assignment_rationale or "",
                "confidence": assignment_confidence or "",
                "source": "agent",
            }
        # Idempotent re-run (Bugs S.No 77): re-dispatching Task Breakdown must REPLACE the prior
        # draft backlog, not duplicate it. Dedupe on the natural key among PROPOSED items only —
        # never touch items already accepted / in-progress / done (that is locked work). An
        # existing proposed match is updated in place (keeps its number); otherwise create fresh.
        existing = WorkItem.objects.filter(
            tenant_id=tenant_id, project=project, type=type, title=title,
            parent=parent, state=WorkItem.State.PROPOSED,
        ).first()
        if existing is not None:
            existing.description = description or ""
            existing.feature_stream = feature_stream or ""
            existing.depends_on = depends_on or []
            existing.repo = repo
            existing.external_ref = external_ref
            existing.save(update_fields=[
                "description", "feature_stream", "depends_on", "repo",
                "external_ref", "updated_at",
            ])
            return _work_item(existing)
        work_item = WorkItem.objects.create(
            tenant_id=tenant_id, project=project, type=type, title=title,
            description=description or "", feature_stream=feature_stream or "",
            parent=parent, depends_on=depends_on or [], repo=repo,
            external_ref=external_ref,
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
    from django.core.exceptions import ValidationError

    with tenant_context(tenant_id):
        try:
            return _artifact(Artifact.objects.get(id=artifact_id, tenant_id=tenant_id))
        except (Artifact.DoesNotExist, ValidationError):
            return {"error": f"no artifact '{artifact_id}' — pass the full id (a UUID) "
                             "from list_artifacts / get_context, not a shortened one."}


import re as _re  # noqa: E402

# object bodies too large to ride the MCP call are staged here first, then referenced by
# pointer from register_artifact (#1/#3: bodies live in the object store, state stays pointers).
_SAFE_FILENAME = _re.compile(r"[^A-Za-z0-9._-]+")
# read-through of a single body is capped so one screen-state never blows the MCP token
# budget — agents fetch one state per call (get_artifact_body(state=...)).
_MAX_BODY_READ_BYTES = 400_000


def _obj_store(injected=None):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


def stage_artifact_body(
    tenant_id, project_id, run_id, phase, filename, body,
    content_type="text/html", object_store=None,
) -> dict:
    """Persist a DRAFT artifact body to the object store and return its pointer
    (`s3_key`, `content_hash`, `bytes`). This is the write-half the pointers-only
    `register_artifact` deliberately lacks: an agent stages each large body here (e.g. one
    self-contained HTML wireframe state), then references the returned `s3_key` from
    `register_artifact`. Bodies live in the object store, never in the DB/state (#1/#3), and
    the draft key is run/phase-scoped so a re-run overwrites its own snapshot. Call once per
    document — one HTML state per call keeps every call well under the MCP token budget."""
    from storage.object_store import content_hash as _content_hash

    store = _obj_store(object_store)
    safe = _SAFE_FILENAME.sub("-", str(filename)).strip("-") or "body"
    key = f"drafts/{tenant_id}/{project_id}/{run_id or 'norun'}/{phase or 'phase'}/{safe}"
    data = body if isinstance(body, bytes) else str(body).encode("utf-8")
    store.put(key, data, content_type=content_type)
    return {"s3_key": key, "content_hash": _content_hash(data), "bytes": len(data)}


def get_artifact_body(tenant_id, artifact_id, state=None, object_store=None) -> dict:
    """Read-through the actual body of an artifact — the read-half agents need to consume
    content (e.g. the implementation agent reading a screen's wireframe HTML), since
    `get_artifact` returns pointers only. For a multi-state wireframe (external_ref.states),
    pass `state` (e.g. "state-1-default") to fetch ONE state; omit it to get the default/
    primary body plus the list of available state names. One state per call stays within the
    MCP token budget. Never copies the body onto the row (#1/#3)."""
    from django.core.exceptions import ValidationError
    from integrations.preview import artifact_body_for_agent

    with tenant_context(tenant_id):
        try:
            artifact = Artifact.objects.select_related("run").get(
                id=artifact_id, tenant_id=tenant_id)
        except (Artifact.DoesNotExist, ValidationError):
            return {"body": "", "content_type": "", "available_states": [],
                    "error": f"no artifact '{artifact_id}' — pass the full id (a UUID) from "
                             "list_artifacts / get_context, not a shortened one."}
        return artifact_body_for_agent(
            artifact, state=state, object_store=object_store,
            max_bytes=_MAX_BODY_READ_BYTES)


# How many page images one get_page_images call returns — a small window so a many-page upload
# is read page-by-page (like get_artifact_body's one-state-per-call), keeping each MCP payload
# well within budget. The vision agent pages through with `next_start`.
_MAX_VISION_IMAGES_PER_CALL = 4

#: Hard ceiling on ONE call's encoded image payload. The MCP stdio transport rejects any message
#: over 1 MiB, and four lossless page renders at full vision resolution sail past that once
#: base64 has added its third — the read failed with "JSON message exceeded maximum buffer size"
#: and took the whole run with it. Bounding the window by COUNT alone could never prevent that,
#: because page weight varies wildly (a dense diagram outweighs a title page many times over), so
#: the window is bounded by bytes as well and simply returns fewer pages when they are heavy.
#: Left well under the limit: the rest of the JSON envelope and the summary text ride along too.
_MAX_VISION_PAYLOAD_BYTES = 700_000

#: Long edge for a page that is too heavy even on its own. Re-encoding it smaller keeps the pipe
#: moving — a slightly softer render the model can still read beats a failed run and no render.
_VISION_FALLBACK_MAX_PX = 1000


def _build_page_image_window(pages: list, store, start: int) -> dict:
    """Pure assembly (no DB): take the ordered `page_images` pointers, read one small window's
    bytes from the object store, downscale each to a vision-sane size, and base64-encode them.
    Split out from get_page_images so the fetch/downscale/pagination is unit-testable with an
    in-memory store, while the DB read stays in get_page_images."""
    from integrations.extract import downscale_image_for_vision

    total = len(pages)
    start = max(0, int(start or 0))
    out: list = []
    budget = _MAX_VISION_PAYLOAD_BYTES
    consumed = 0            # pages taken from `start`, however few fit — drives next_start
    for pi in pages[start:start + _MAX_VISION_IMAGES_PER_CALL]:
        key = pi.get("s3_key") if isinstance(pi, dict) else None
        if not key:
            consumed += 1
            continue
        try:
            raw = store.get(key)
        except Exception:  # noqa: BLE001 — one missing object must not fail the whole read
            consumed += 1
            continue
        encoded = base64.b64encode(downscale_image_for_vision(raw)).decode("ascii")
        if len(encoded) > budget:
            if out:
                break       # doesn't fit alongside what we have — it leads the next call
            # First page of the call and already over budget: send it smaller rather than
            # stall the read on a page that can never fit at full size.
            encoded = base64.b64encode(
                downscale_image_for_vision(raw, max_px=_VISION_FALLBACK_MAX_PX)
            ).decode("ascii")
        budget -= len(encoded)
        consumed += 1
        out.append({
            "name": pi.get("name"),
            "page": pi.get("page"),
            "mime": "image/png",
            "data_base64": encoded,
        })
        if budget <= 0:
            break
    nxt = start + max(1, consumed)      # never return the same start twice → no infinite paging
    return {"images": out, "total": total, "start": start, "returned": len(out),
            "next_start": nxt if nxt < total else None}


def get_source_extraction(tenant_id, source_document_id, object_store=None) -> dict:
    """Read the text a document's upload already extracted, before any artifact exists for it.

    The vision agent must preserve this text and add what the pages hold — but for a document
    uploaded after artifacts moved to adopt time there is no artifact yet to read it from
    (`get_artifact_body` needs one). The extraction is staged in the object store at upload
    regardless, so this serves it straight from the source document.
    """
    from apps.integrations.models import SourceDocument

    with tenant_context(tenant_id):
        src = SourceDocument.objects.filter(id=source_document_id, tenant_id=tenant_id).first()
        if src is None:
            return {"body": "", "error": f"no source document '{source_document_id}'"}
        prov = src.provenance or {}
        key, filename = prov.get("extracted_s3_key"), src.filename
        title, fidelity = prov.get("title") or "", prov.get("fidelity") or ""
    if not key:
        return {"body": "", "filename": filename, "title": title, "fidelity": fidelity,
                "error": "this document has no staged extraction"}
    try:
        body = _obj_store(object_store).get(key).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return {"body": "", "filename": filename, "title": title, "fidelity": fidelity,
                "error": f"the extraction could not be read: {exc}"}
    return {"body": body, "filename": filename, "title": title, "fidelity": fidelity}


def page_images_for(tenant_id, subject_id):
    """The preserved page renders for a document, wherever they live.

    They are stored on the SOURCE DOCUMENT from the adopt-time-registration change onward: an
    upload no longer mints an artifact, so the pages have to belong to something that exists from
    the moment the file lands. Documents uploaded before that change keep them on the artifact
    they were registered with, so both locations are read — `subject_id` may be either a source
    document or an artifact, and callers don't have to know which era a document came from.

    Returns (pages, found) so a caller can tell "no images" from "no such subject".
    """
    from django.core.exceptions import ValidationError

    from apps.integrations.models import SourceDocument

    with tenant_context(tenant_id):
        try:
            src = SourceDocument.objects.filter(id=subject_id, tenant_id=tenant_id).first()
        except (ValidationError, ValueError):
            src = None
        if src is not None:
            pages = (src.provenance or {}).get("page_images")
            if pages is None:
                # Pre-change document: the pages went onto the artifact the upload registered.
                aids = list(src.extracted_artifact_ids or [])
                art = (
                    Artifact.objects.filter(id=aids[0], tenant_id=tenant_id).first()
                    if aids else None
                )
                pages = ((art.external_ref or {}).get("page_images") if art else None) or []
            return list(pages), True
        try:
            artifact = Artifact.objects.filter(id=subject_id, tenant_id=tenant_id).first()
        except (ValidationError, ValueError):
            artifact = None
        if artifact is None:
            return [], False
        return list((artifact.external_ref or {}).get("page_images") or []), True


def get_page_images(tenant_id, artifact_id, start=0, object_store=None) -> dict:
    """Return the stored page / embedded images of a document artifact as base64 PNG blocks — the
    vision pipe (onboarding_fidelity_plan Part B). Text extraction can't carry diagrams,
    screenshots, wireframes, scanned pages, or tables-as-pictures; those were rendered and kept at
    ingest as `external_ref.page_images` pointers. This reads their bytes from the object store
    (never copied onto the row — #1/#3), downscales each to a vision-sane size, and hands them
    back for a multimodal agent to SEE.

    Paginated: returns up to a few images from `start`, plus `total` and `next_start` (null on the
    last batch) — call again until `next_start` is null. JSON-safe (base64) so it rides the same
    HTTP proxy the companion uses; the MCP layer turns each into an image content block.

    `artifact_id` accepts either the SOURCE DOCUMENT id or an artifact id. Vision now runs before
    any artifact exists for the document — the upload no longer registers one — so the run is
    pointed at the source document; older documents that do have an upload-time artifact still
    resolve through it."""
    pages, found = page_images_for(tenant_id, artifact_id)
    if not found:
        return {"images": [], "total": 0, "start": start, "returned": 0, "next_start": None,
                "error": f"no document or artifact '{artifact_id}' — pass the full id (a UUID) "
                         "named in your work item, or from list_artifacts / get_context."}
    return _build_page_image_window(pages, _obj_store(object_store), start)


def list_artifacts(tenant_id, project_id, phase=None, status=None, type=None) -> list[dict]:
    """List artifact pointers, optionally filtered by `phase`, `status`, and/or `type`. The
    `type` filter (Bugs S.No 191) is how an agent accurately pulls a specific upstream input on
    demand — e.g. `list_artifacts(type="architecture")` returns the architecture pointer(s),
    newest first, then `get_artifact_body(id)` fetches the body. This is the on-demand companion
    to get_context's guaranteed required tier (S.No 190)."""
    with tenant_context(tenant_id):
        qs = Artifact.objects.filter(tenant_id=tenant_id, project_id=project_id)
        if phase is not None:
            qs = qs.filter(phase=phase)
        if type is not None:
            qs = qs.filter(type=type)
        if status is not None:
            if status not in Artifact.Status.values:
                raise ValueError(f"invalid status: {status}")
            qs = qs.filter(status=status)
        # Pointers only — a listing must never carry bodies (Bugs.xlsx row 69). Fetch a body
        # on demand with get_artifact_body(id) using the full id returned here.
        return [_artifact_pointer(a) for a in qs.order_by("-created_at")]


def detect_drift(tenant_id, artifact_id) -> dict:
    """P0 stub — always drift=False. Real comparison vs the SoR arrives in Phase 4."""
    with tenant_context(tenant_id):
        artifact = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        return {
            "drift": False,
            "current_version": artifact.version,
            "registered_version": artifact.version,
        }
