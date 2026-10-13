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
import logging
from datetime import UTC, datetime

from apps.clarifications.models import Clarification
from apps.ledger.models import Event
from apps.projects.models import Project, Repository
from apps.registry.models import Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


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
        "published_at": _dt(a.published_at),
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
def get_context(tenant_id, project_id, phase, work_item_id=None, repo_id=None,
                knowledge_chunks=None) -> dict:
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

    **How much knowledge to retrieve (truncation register T3).** `knowledge_chunks` is how many
    chunks to fetch, derived by the caller from the dispatched model's context window
    (`manifest.budget.chunks_for_budget`). It used to be a hardcoded eight while the composer then
    cut the rendered section to 1,500 tokens, so roughly a third of what retrieval had just ranked
    was binned on every dispatch and one chunk was cut mid-sentence. Omitting it keeps the old
    eight, so every caller that does not care is unaffected.
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
        # SUPERSEDED = a draft whose gate was rejected. It stays in the registry (it is the
        # record of what the agent wrote, and a revision's manifest cites it by id) but it is no
        # longer the project's answer for its type. Without this exclusion a rejected draft was
        # still served to every downstream phase as the authoritative artifact — the reviewer
        # said no and the platform kept handing it on, which is a far quieter failure than a
        # rejected run.
        base_qs = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id,
        ).exclude(status=Artifact.Status.SUPERSEDED)
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
        # Recent history, scoped to THIS project (Bugs S.No 230). It used to be scoped to the
        # whole workspace, so an agent could be handed the last 20 events from a project it has
        # nothing to do with — a different client's work, in a shared-database tenant.
        #
        # Clarification events are scoped tighter still, to this work item, and only when we
        # know which work item that is. A question is the one kind of event an agent reasons
        # FROM: seeing "a question was asked" with no answer beside it — belonging to another
        # work item, from a run that has since been deleted — is what was actually observed on a
        # brand-new work item, and is how an agent comes to believe something was already
        # settled when it was not. The answered clarifications replayed below are the honest
        # channel for that, and they carry their answers.
        #
        # Events written before this column existed carry no project and so fall out. That is
        # the intent: they are stale noise from runs nobody can trace any more.
        events_qs = (
            Event.objects.filter(tenant_id=tenant_id, project_id=project_id)
            .exclude(action__in=_MANIFEST_MUTED_ACTIONS)
        )
        if wi is not None:
            events_qs = events_qs.exclude(
                Q(target_type="clarification") & ~Q(work_item_id=wi.id)
            )
        else:
            events_qs = events_qs.exclude(target_type="clarification")
        events = events_qs.order_by("-ts")[:20]
        query = " ".join(filter(None, [phase, getattr(wi, "title", ""),
                                       getattr(wi, "description", "")]))
        # Answered clarifications for this work item are replayed into the manifest so a
        # re-dispatched run (e.g. after a companion restart) never re-asks (req #2 durability).
        # NEWEST FIRST (truncation T13): the section is capped and cut from the tail, so oldest-
        # first discarded the latest human decision and kept the stalest. On the 2026-08-05 run
        # the four answers that defined a pivot were exactly the ones that fell off the end.
        answered = (
            Clarification.objects.filter(
                tenant_id=tenant_id, work_item_id=wi.id,
                status=Clarification.Status.ANSWERED,
            ).order_by("-answered_at")
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
            "retrieved_knowledge": _retrieve_knowledge(
                tenant_id, project_id, query, chunks=knowledge_chunks),
            "answered_clarifications": [_clarification(c) for c in answered],
        }


def _retrieve_knowledge(tenant_id, project_id, query, chunks=None) -> list[dict]:
    """Knowledge-Index retrieval (Phase 4) — **project-scoped shared memory across repos**
    (D5), so a run in one repo can still retrieve another repo's knowledge + the shared
    contract. Best-effort: a retrieval hiccup never breaks context composition.

    `chunks` defaults to the eight this always fetched. The number is the caller's to choose
    because only the caller knows the run's token budget; what matters here is that whatever is
    fetched is whole — retrieval returns complete chunks and the composer now renders all of
    them, so nothing is ranked and then thrown away."""
    try:
        from apps.knowledge.index import retrieve

        from manifest.budget import MIN_CHUNKS

        return retrieve(tenant_id, project_id=project_id, query=query,
                        k=int(chunks or MIN_CHUNKS))
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


#: Where an artifact's STABLE identity lives on its pointer, per type, most trusted key first
#: (Bugs S.No 183).
#:
#: Artifact identity used to be the `title` the agent wrote — free text. A retried phase that
#: re-words a title by one character forked a second artifact at v1 beside the first instead of
#: superseding it. Worst on phases that register many artifacts at once (a security run files one
#: per finding), but the rule lives in the shared registration path, so every phase had it.
#:
#: The identifiers below already exist and are already used elsewhere: the security defect loop
#: reads `finding_id`/`id` off exactly these rows, and `apps.workitems.test_cases` matches test
#: cases on `tc_id`/`id`. Versioning simply never looked at them.
#:
#: `identity` is the deliberate escape hatch, honoured for every type: a caller that knows what
#: makes two registrations the same thing can say so outright.
#:
#: `code` is deliberately absent. Its title is machine-composed (`Code — {work item}`), so
#: title-versioning is already reliable there, and a build registers several `code` pointers per
#: run on purpose — the remediation cycles — which the build path distinguishes by PR ref, not by
#: version. Nothing about that needs changing and it is the one path not to disturb.
_IDENTITY_REF_KEYS: dict[str, tuple[str, ...]] = {
    "security_finding": ("identity", "finding_id", "id"),
    "test_case": ("identity", "tc_id", "id"),
}
_DEFAULT_IDENTITY_REF_KEYS: tuple[str, ...] = ("identity",)

#: Types that register many DISTINCT rows sharing (phase, type) in one run. These are the ones
#: most exposed to title drift, so a registration with no stable identifier is worth a line in
#: the server log — a developer diagnostic, never anything a user sees.
_PER_ITEM_TYPES = frozenset({"adr", "test_case", "security_finding", "code_review",
                             "test_report"})


def _identity_ref(type, external_ref) -> tuple[str, object] | None:
    """The `(external_ref key, value)` that identifies this artifact, or None to use the title."""
    ref = external_ref or {}
    if not isinstance(ref, dict):
        return None
    for key in _IDENTITY_REF_KEYS.get(type, _DEFAULT_IDENTITY_REF_KEYS):
        value = ref.get(key)
        if value not in (None, ""):
            return key, value
    return None


def _assert_body_exists(s3_key, object_store=None) -> None:
    """Refuse a registration whose body is not actually in the object store.

    S.No 314. A pointer is a string the caller hands over, and nothing checked that anything
    was behind it. On 2026-10-05 an agent registered a feasibility report against a path one
    character off the real one: the row was flawless on every screen — title, type, version,
    content hash, "Waiting for approval" — and completely hollow. Nobody could have seen it.
    It was found only when a human approved the gate and the publish step walked the run's
    artifacts and hit it, by which point the decision had already been made and the whole
    phase wedged (S.No 315).

    Called from the MCP server's `register_artifact`, NOT from this function, and the seam is
    deliberate. The defect is an agent composing a key by hand from a manifest; platform code
    composes keys on the line below the `store.put` that created them (onboarding, a11y,
    quality), so checking those costs a storage round-trip per registration to re-answer a
    question their own code just answered. The agent boundary is where untrusted pointers
    enter, so it is where they are checked.

    Checked at REGISTRATION because that is the one moment the mistake is cheap: the agent is
    still running, is told plainly, and can stage the body again. Every later moment is
    somebody else's problem.

    A store that cannot answer is not treated as "missing" — `exists` raises on anything
    other than a real absence, and that travels, because refusing an artifact for a network
    blip would be its own kind of lie."""
    if not s3_key:
        return   # pointer-less registrations are legitimate: sor=git carries no body
    store = _obj_store(object_store)
    if not store.exists(s3_key):
        raise ValueError(
            f"no body found at {s3_key!r}, so this artifact would point at nothing. Stage the "
            "body first with stage_artifact_body and register with the s3_key and "
            "content_hash that call returned — do not compose the key by hand."
        )


def register_artifact(
    tenant_id, project_id, run_id, phase, type, sor,
    content_hash, s3_key=None, external_ref=None, repo_id=None, title="", supersedes=None,
    format=None, object_store=None,
) -> dict:
    """`format` declares what the staged body IS — "json", "yaml", "xml", "csv", "markdown"
    (the default when nothing is said). Bugs S.No 187: the preview announced every internal
    body as markdown whatever was in it, and there was no way for an agent to say otherwise,
    so the security phase's CycloneDX SBOM previewed as one unbroken run of characters. The
    platform can now also detect JSON on its own, but a declaration is better than a guess."""
    with tenant_context(tenant_id):
        project = Project.objects.get(id=project_id, tenant_id=tenant_id)
        # `supersedes` anchors this registration to an EXISTING artifact's identity (Part B fix 2).
        # Versioning keys on (project, phase, type, title), so a caller that means "this is the
        # next version of that document" had to reproduce all three strings exactly — and an agent
        # echoing a title back byte-for-byte is not something the platform can rely on. One
        # character of drift silently forks a second artifact instead of versioning the first.
        # Naming the target id instead makes the link explicit: the platform reads the identity
        # off the target rather than trusting the caller to restate it.
        superseded_ref = None
        if supersedes:
            target = Artifact.objects.get(id=supersedes, tenant_id=tenant_id)
            if str(target.project_id) != str(project.id):
                raise ValueError("supersedes must name an artifact in the same project")
            phase, type, title = target.phase, target.type, target.title
            # …and its identity too (S.No 183). `supersedes` means "this is the next version of
            # THAT row", so the version counter must key off the target's identity, not off
            # whatever pointer this registration happens to carry — otherwise naming the target
            # explicitly would still fork a v1, which is the exact failure `supersedes` exists
            # to prevent.
            superseded_ref = target.external_ref
        run = Run.objects.get(id=run_id, tenant_id=tenant_id) if run_id else None
        repo = (
            Repository.objects.get(id=repo_id, tenant_id=tenant_id) if repo_id else None
        )
        if sor not in Artifact.SoR.values:
            raise ValueError(f"invalid sor: {sor}")
        _assert_body_not_shared(tenant_id, run, type, s3_key, title)
        if format:
            # Recorded on the pointer alongside the other provenance — `_REF_POINTER_KEYS`
            # already lists "format", so it is never mistaken for the artifact's content.
            external_ref = {**(external_ref or {}), "format": str(format).lower()}
        # Version across re-registrations (Bugs.xlsx row 28.2): re-running a phase should yield
        # v2, v3, … of the SAME artifact. But per-item types (adr, test_case, security_finding,
        # code, code_review, test_report) register many DISTINCT rows sharing (phase, type) in one
        # run — versioning by (phase, type) alone falsely numbered them as supersessions of each
        # other (Bugs S.No 120, Part C-1). Scope the counter to the item's own identity so distinct
        # siblings each start at v1; fall back to (phase, type) for untitled singletons.
        #
        # Prefer a STABLE identifier off the pointer over the title (Bugs S.No 183). The title is
        # free text the agent wrote, so a retry that re-words it by one character used to fork a
        # duplicate at v1 instead of superseding — while `finding_id`, sitting on the very same
        # row and already read by the security defect loop, said plainly that it was the same
        # finding. Prefer-then-fall-back rather than *requiring* an identifier: raising here would
        # happen inside a live run and turn a duplicate artifact into a failed phase, which is a
        # worse outcome than the bug.
        version_filter = {"tenant_id": tenant_id, "project": project,
                          "phase": phase, "type": type}
        identity = _identity_ref(type, superseded_ref if supersedes else external_ref)
        if identity:
            version_filter[f"external_ref__{identity[0]}"] = identity[1]
        elif title:
            version_filter["title"] = title
        if supersedes and identity and (external_ref or {}).get(identity[0]) in (None, ""):
            # Carry the target's identity onto this version's own pointer, or the chain breaks at
            # the NEXT registration: this row would be v2 of that identity while carrying no
            # trace of it, and v3 would start over at v1.
            external_ref = {**(external_ref or {}), identity[0]: identity[1]}
        if identity is None and type in _PER_ITEM_TYPES:
            logger.info(
                "artifact registered with no stable identifier: type=%s phase=%s project=%s "
                "run=%s title=%r — versioning falls back to the title, so a re-run that re-words "
                "it will register a duplicate rather than a new version",
                type, phase, project_id, run_id, title,
            )
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
        _index_into_knowledge(tenant_id, project, artifact, repo)
        return _artifact(artifact)


#: Artifact types that are a RESULT, never knowledge — kept out of the Knowledge Index.
#:
#: **What this prevents, measured** (24 Aug). Every artifact with a body is indexed when it is
#: registered, and the index is then searched for whatever a run is about. So an accessibility
#: judging run searched for accessibility judging knowledge, and the closest match in the whole
#: project was **the previous accessibility judgement**. Its full body — findings table, gate
#: outcome, per-element verdicts — was pasted into the briefing of the run whose entire job was
#: to produce that document. Retrieval returned, among the top eight:
#:
#:     '**31. `#loans-table > tbody > tr:nth-of-type(3)` on `/loans/history`** — 1.4.1 …'
#:
#: which is one of the very elements that run had been asked to judge, with last time's answer
#: attached. That run recorded **zero** verdicts and reported "Gate outcome: PASS — 33 elements,
#: all pass", every word of it lifted from the document it had been handed. The platform's
#: completeness check caught it and refused to call the audit complete, but a check that catches
#: a fabricated answer is a worse position than never inviting one.
#:
#: It looked like the model being unreliable and it was not: the same agent judged 128 elements
#: correctly an hour later on another tenant, whose retrieval happened to return summaries
#: instead of a verdict table. Which of the eight you get is chance. Removing the source is not.
#:
#: **Why exclusion rather than a rule telling the agent to ignore it.** An agent cannot be
#: relied on to disregard a plausible, authoritative, on-topic answer sitting in its own
#: context — and it should not have to. These documents are also the wrong shape for an index:
#: each one is a statement about a single capture, superseded by the next run, so a project
#: accumulates contradictory copies of "the answer" that get retrieved by recency-blind search.
#:
#: They remain fully reachable on purpose — `list_artifacts(type=…)` then `get_artifact_body`,
#: which the manifest tells every agent about. An agent that has a REASON to read last week's
#: report can still ask for it by name. What it can no longer do is find it in its own pocket.
_NOT_KNOWLEDGE_TYPES = frozenset({
    "a11y_judge",        # the judge's own verdicts — the document that caused this
    "a11y_report",       # the merged findings for one capture
    "a11y_baseline",     # where the application stood after one audit
    "a11y_conformance",  # the signed statement; a claim, and never an input to making one
})

#: The same exclusion applied by PHASE, because a judging run writes TWO documents and the list
#: above only names one of them.
#:
#: Every `a11y_judge` run also registers an `assumption` note on its own reasoning — *"here is
#: how I mapped this axe rule to this criterion"*. `assumption` is a type most phases write and
#: most of those are worth retrieving, so it cannot be excluded by type without losing the rest.
#: When the verdicts were excluded on 25 August these notes were deliberately kept, on the
#: reasoning that a note about *how* to reason carries no answers.
#:
#: **Measured against the only samples that exist, that reasoning does not hold.** Both
#: `a11y_judge` notes in the shared database were indexed, and both contain this:
#:
#:     '4. **1.4.1 vs 1.4.3 independence** — … the `#hours-note` element exhibits exactly this
#:      combination.'
#:
#: — a live element on a page under audit, with its verdict on both criteria. Same class as the
#: findings table above, in a smaller package, retrieved by the same recency-blind search. Two
#: of two, so it is the norm and not an edge case.
#:
#: **And the channel refills itself.** Every judging run writes another note, so a tenant whose
#: index is emptied today is exposed again on its second run. That is what made the original
#: failure look intermittent and like an unreliable model: it is neither, it tracks how much of
#: its own previous work the project has accumulated.
#:
#: By phase rather than by type so it also covers whatever else these runs come to write,
#: without a third list to keep in step. `a11y_journey` joins it by the same argument rather
#: than by measurement — it has registered nothing yet anywhere, and waiting for it to bite is
#: the shape of failure this codebase keeps meeting. The pair matches `NEVER_AUTO_PUBLISHED_
#: PHASES` for the same underlying reason: run OUTPUT about one capture, superseded by the next
#: run, never an input to making it.
#:
#: **Deliberately narrow.** `a11y_report` and `a11y_baseline` are written under phase `testing`,
#: so the two lists overlap in nothing and both are load-bearing. Journey DEFINITIONS are
#: `testing`/`test_case` (`journeys._test_case_artifacts`) and stay indexed — this removes what a
#: run concluded, never what it was asked to walk.
_NOT_KNOWLEDGE_PHASES = frozenset({
    "a11y_judge",        # verdicts (above) plus the run's own reasoning note
    "a11y_journey",      # the same shape for a walked journey
})


def _index_into_knowledge(tenant_id, project, artifact, repo) -> None:
    """Chunk the newly-registered body into the Knowledge Index so downstream phases can
    retrieve it (B1).

    Registration and retrieval were two separate steps and only ONE of them had a tool. Agent
    bodies (00c, and the artifact instructions of every later phase) tell the agent to "index
    each artifact into the Knowledge Index" — but no such tool is exposed, so no agent has ever
    been able to. Measured live after run 98ab9a8c published seven code-intelligence artifacts:
    `KnowledgeChunk` rows for them = **0**. The entire point of the phase — intelligence that
    later agents retrieve instead of re-reading the codebase — leaked out here silently.

    So the platform does it, rather than asking the agent to remember: an artifact that carries
    a body is indexed at the moment it is registered. `index_artifact` is idempotent (it
    replaces that artifact's chunks), so a re-registration re-indexes cleanly rather than
    duplicating.

    Best-effort by design: retrieval is an accelerator, never a correctness gate. A missing
    body, an object-store hiccup or an un-decodable payload must not fail a registration the
    agent has already done the work for — it degrades to "not retrievable", which is exactly
    where we were before."""
    if not artifact.s3_key:
        return  # pointer-only artifact (external SoR) — nothing local to chunk
    if artifact.type in _NOT_KNOWLEDGE_TYPES:
        return  # a result, not knowledge — see the list's own note for what this cost us
    if artifact.phase in _NOT_KNOWLEDGE_PHASES:
        return  # run output whatever it is typed as — see `_NOT_KNOWLEDGE_PHASES`
    try:
        from apps.knowledge.index import index_artifact

        raw = _obj_store().get(artifact.s3_key)
        text = (raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw))
        text = text[:_MAX_BODY_READ_BYTES].strip()
        if not text:
            return
        index_artifact(
            tenant_id=tenant_id, project_id=project.id, artifact_id=artifact.id,
            text=text, repo_id=(repo.id if repo else None),
        )
    except Exception:  # noqa: BLE001 — see docstring: never fail a registration over retrieval
        logger.warning("knowledge indexing failed for artifact %s", artifact.id, exc_info=True)


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
    s3_key=None,
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
            # Stamp the moment it became published (Bugs S.No 224). Here rather than at each
            # caller because this is the choke point every `tools.*` status write goes through —
            # gate approval, the build's post-merge publish, the PR-merged webhook and both
            # onboarding paths all land on this line. Only on the TRANSITION into published, so
            # a later edit of an already-published artifact never re-dates its publication.
            if status == Artifact.Status.PUBLISHED and artifact.published_at is None:
                artifact.published_at = _now()
            artifact.status = status
        if sor is not None:
            if sor not in Artifact.SoR.values:
                raise ValueError(f"invalid sor: {sor}")
            artifact.sor = sor
        if external_ref is not None:
            artifact.external_ref = external_ref
        if content_hash is not None:
            artifact.content_hash = content_hash
        # Re-point an artifact at a newly staged body. `register_artifact` has always accepted
        # `s3_key`; update had no way to set it, so a caller that re-staged on a later cycle could
        # only ever create a second row or leave the first pointing at the old snapshot — and a
        # caller that staged nothing at registration time (the code_review path) had no way to
        # attach a body at all afterwards.
        if s3_key is not None:
            artifact.s3_key = s3_key
        if version is not None:
            artifact.version = version
        artifact.save()
        return _artifact(artifact)


def add_trace_edge(tenant_id, from_artifact_id, to_artifact_id, rel) -> dict:
    with tenant_context(tenant_id):
        if rel not in TraceEdge.Rel.values:
            # Name the vocabulary in the error (B2). The valid set lived only in the model
            # enum — never in the tool signature, never in a docstring, never in this message.
            # Live in run 98ab9a8c the agent guessed NINE values before landing on one that
            # stuck, then used that single value for every edge because it had no way to learn
            # the others. An error that says only "invalid" teaches nothing; one that lists the
            # alternatives ends the guessing on the first failure.
            raise ValueError(
                f"invalid rel: {rel!r}. Valid values: {', '.join(TraceEdge.Rel.values)}. "
                f"Meaning: 'derives' = this artifact was DERIVED from the other (the usual "
                f"choice for analysis/report → its source); 'implements' = code/design "
                f"fulfilling a specification; 'tests' = a test covering the target; "
                f"'deploys' = a deployment artifact shipping the target."
            )
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


def submit_gap_report(tenant_id, project_id, phases, resume_phase=None, blockers=None,
                      run_id=None) -> dict:
    """Agent-authored gap report (00_onboarding). Hands the agent's reasoned per-phase assessment
    to the shared normalizer+writer, which coerces it to the exact `external_ref` shape
    `read_gap_report` + the whole UI depend on — so a model typo can never degrade the screen.
    The bound `project_id`/`run_id` travel from the run; `tenant_id` is bound server-side.

    `run_id` is LOAD-BEARING (S5-3): the report used to be registered run-unbound, and both
    `verify_writes` and `publish_artifacts` filter on `run_id`. Unbound, the report counted as no
    write at all — an agent that assessed correctly and submitted once failed write-completeness —
    and it could never be published by its gate. Bound, it is the run's work product: the gate
    opens on it and approval publishes it."""
    from integrations.onboarding import submit_agent_gap_report

    return submit_agent_gap_report(
        tenant_id=tenant_id, project_id=project_id, phases=phases,
        resume_phase=resume_phase, blockers=blockers, run_id=run_id,
    )


def get_a11y_batch(tenant_id, run_id, start=0) -> dict:
    """The elements this accessibility judgment run must judge (09c_a11y_judge, QA-02a).

    `dispatch` decided what needed judging and attached it to the run; this is that list, one
    screen at a time. Each element carries the short `id` the judge echoes back to
    `record_a11y_finding` — the internal content hash never leaves the platform, because a
    model copying 64 hex characters back is one typo away from filing a verdict against a
    different element.

    Paged: `start` is a flat element index, and `next_start` carries the next one until it comes
    back null. `total_elements` is the whole run on every page — that is the contract to check
    yourself against, not the size of the page in your hand."""
    from apps.a11y.judge import batch_for_run

    return batch_for_run(tenant_id, run_id, start=start)


def get_wcag_grounding(tenant_id, criteria) -> dict:
    """The exact WCAG 2.2 wording for these criteria, plus the glossary terms they lean on.

    The judge decides against the standard's own words, not its recollection of them — and
    against W3C's definitions of the terms those words hinge on ("non-text content",
    "cognitive function test"), which read as ordinary English without them. `tenant_id` is
    accepted for signature symmetry and unused: the standard is one platform-wide copy that
    no tenant may amend (QA-04)."""
    from apps.a11y.judge import grounding_for

    return grounding_for(criteria)


def record_a11y_finding(tenant_id, element_id, criteria, verdict, confidence, evidence,
                        suggested_fix="", run_id=None, project_id=None) -> dict:
    """Record ONE accessibility verdict for ONE element of the dispatched batch (QA-02a).

    Hands the agent's judgement to the shared validator+writer, which coerces what is safely
    coercible and rejects the rest with a message the agent can act on — so a model typo can
    never degrade a conformance report. The checker is read from the batch rather than taken
    from the agent, so a call cannot mislabel which check it was.

    `criteria` is a LIST (team decision D-A11Y-2): one broken thing can breach more than one
    requirement — a `div` dressed as a button breaks 1.3.1 *and* 4.1.2 — and one fix repairs
    both. Report the ones that actually apply, never the whole set by reflex.

    `run_id` is LOAD-BEARING: it is how the element is found and how the verdict is stamped
    with the model that produced it."""
    from apps.a11y.judge import record_finding

    return record_finding(
        tenant_id=tenant_id, run_id=run_id, element_id=element_id, criteria=criteria,
        verdict=verdict, confidence=confidence, evidence=evidence,
        suggested_fix=suggested_fix, project_id=project_id,
    )


def get_a11y_screenshots(tenant_id, run_id, start=0, object_store=None) -> dict:
    """SEE the elements this judgment run must judge (QA-11b).

    The batch carries a `screenshot_ref` per element, which is a pointer and not a picture.
    This reads those crops from the object store, downscales them to a vision-sane size and
    hands them back as image data — the same pipe `get_page_images` uses for a document's
    pages, because it is the same problem.

    Without it the `color` check could never answer: 1.4.1 asks whether meaning is carried by
    colour alone, which is a question about what a thing looks like. Each image is labelled
    with the element's own `id`, so a verdict is filed against the element that was seen.

    Paginated — a few elements per call, with `next_start` until the last batch. Elements with
    no captured image are not returned as blanks; they are listed in `unseen` with the reason,
    which is what the judge quotes when it records `uncertain`.
    """
    from apps.a11y.judge import screenshot_pointers

    pointers, unseen = screenshot_pointers(tenant_id, run_id)
    window = _build_page_image_window(pointers, _obj_store(object_store), start)
    window["unseen"] = unseen
    return window


def ingest_a11y_candidates(tenant_id, project_id, screen, run_id=None) -> dict:
    """Store one captured screen's accessibility candidate bundles (QA-11b).

    Called by the **companion**, not by an agent: the capture is machine truth written by the
    suite's own run against the live application, and the companion collects it from the
    worktree before teardown. It is deliberately absent from the companion's engine tool grant
    — an agent able to write candidate bundles could describe a page instead of one having
    been captured.

    One screen per call. A screen carries a full-page PNG, and ten of those in one request body
    is past what the request layer accepts.
    """
    from apps.a11y.ingest import ingest_screen

    return ingest_screen(tenant_id=tenant_id, project_id=project_id, screen=screen,
                         run_id=run_id)


def start_a11y_audit(tenant_id, project_id, base_url="", routes=None) -> dict:
    """Open a baseline accessibility audit and return the manifest to visit (QA-17).

    Called by the **companion**, for the same reason `ingest_a11y_candidates` is: the app under
    audit runs on a machine the platform cannot reach, so the visiting happens there. The
    platform decides *what* to visit (the project's registered routes) and reconciles what comes
    back; it never opens a page itself.

    `routes` overrides the registry for a one-off pass. Omitted — the normal case — the
    project's enabled routes are used, and an empty registry is refused rather than producing an
    audit of nothing that would read as an application with nothing wrong.
    """
    from apps.a11y.baseline import audit_manifest, start_baseline_audit

    audit = start_baseline_audit(tenant_id=tenant_id, project_id=project_id,
                                 base_url=base_url, routes=routes)
    return {"audit_id": str(audit.id), "status": audit.status,
            "manifest": audit_manifest(audit)}


def ingest_a11y_audit_screen(tenant_id, audit_id, screen) -> dict:
    """Store one screen captured for a baseline audit (QA-17). One screen per call.

    The audit's own bucket, not a run's — see `apps.a11y.models.A11yBaselineAudit`. Companion
    only, and deliberately absent from the engine tool grant for the same reason its sibling is:
    an agent able to write a capture could describe a page instead of one having been visited.
    """
    from apps.a11y.baseline import ingest_audit_capture
    import json as _json

    return ingest_audit_capture(tenant_id=tenant_id, audit_id=audit_id,
                                text=_json.dumps(screen))


def get_a11y_audit(tenant_id, audit_id) -> dict:
    """The manifest for an audit this machine was handed (task 8a).

    The claim already carries one, but a companion that reconnects mid-audit — or retries a
    pass — must be able to ask again rather than start a second audit to get a manifest. The
    frozen route list is the audit's own, so asking twice can never widen or narrow what it was
    asked to visit.
    """
    from apps.a11y.baseline import audit_snapshot

    return audit_snapshot(tenant_id=tenant_id, audit_id=audit_id)


def finish_a11y_audit(tenant_id, audit_id, reason: str = "") -> dict:
    """Close a baseline audit: account for every route asked for, then ask the AI checks (QA-17).

    The reconciliation is the part that matters. A route that never reported is recorded as
    unreachable with that as its reason, so an audit that covered 38 of 50 screens says so
    instead of reading as a complete pass over an application with fewer problems than it has.

    `reason` is the auditing machine's own account of why nothing came back — no browser
    installed in the project folder, most often. It replaces the generic explanation, which
    blames the application and would send someone to check a server nothing ever contacted.
    Ignored when anything was captured: a stated reason cannot overrule a real result.
    """
    from apps.a11y.baseline import finish_baseline_audit

    return finish_baseline_audit(tenant_id=tenant_id, audit_id=audit_id, reason=reason)


def get_a11y_journey(tenant_id, run_id) -> dict:
    """The journey this run must operate with a keyboard (09d_a11y_journey, QA-20).

    Your contract, read once at the start. `steps` are frozen — the numbering here is what you
    report against, NOT the numbering printed in the test case body, because a body that jumps
    1, 2, 4 would otherwise leave a step nobody can file against. `total_steps` is the count to
    check yourself against before you finish.

    `checks` names the eight questions and the WCAG criterion each one owns. A verdict may name
    only the criteria its own check owns; anything else is rejected.
    """
    from apps.a11y.journey import journey_for_run

    return journey_for_run(tenant_id, run_id)


def record_a11y_journey_step(tenant_id, run_id, step, outcome, reason="") -> dict:
    """Record what became of ONE step: `walked` or `blocked` (QA-20).

    Call this for **every** step, including the ones that went fine — the platform cannot tell
    "I walked it and it was clean" from "I never got there" unless you say which.

    `blocked` means you reached this step and could not go on; `reason` is what stopped you, in
    your own words ("the login form rejected the seeded account"). Everything after a blocked
    step is untested and will be recorded as such — that is correct and expected, and far better
    than a guess. There is no `not_reached` here: the platform writes that itself for steps you
    never mention, because a run that stopped early cannot report that it stopped.
    """
    from apps.a11y.journey import record_step

    return record_step(tenant_id=tenant_id, run_id=run_id, number=step,
                       outcome=outcome, reason=reason)


def record_a11y_journey_finding(tenant_id, run_id, step, checker, verdict, confidence, evidence,
                                criteria=None, suggested_fix="", route="", selector="",
                                measurement=None) -> dict:
    """Record ONE check's answer about ONE step of the journey (QA-20).

    One call per (step, check) you can answer. `checker` is one of the eight from
    `get_a11y_journey().checks`; leave `criteria` unset and the check's own criterion is used.

    A confident **pass** is recorded as a pass and stored as no finding — its absence next run is
    how a fixed problem is recognised. A **fail** needs `evidence` a developer can act on. If you
    could not tell, say `uncertain`: it routes to a person and is a first-class answer here, not
    a failure to answer. Never report a verdict for a step you did not reach — record the step as
    `blocked` instead.

    `selector` is optional: some of these checks are about a screen rather than one element
    ("focus order on this page"), and inventing an element for them would file the finding
    against something that is not what is wrong.

    **`measurement` — two of these checks have a half that can be read rather than judged.**
    Run the probe named in your agent body and pass back exactly what it returned:

      * `focus_visible` → `{"outline_style", "outline_width", "box_shadow"}`, read with the
        element focused. Values come from `getComputedStyle`, verbatim.
      * `status` → `{"live_region_count"}`, the number of live regions on the screen.

    Report the raw values and nothing else — do not decide what they mean and do not adjust your
    verdict to match them. The platform applies the rule, and where the reading proves a failure
    that ruling stands over your verdict; where it proves nothing, your verdict is untouched.
    Omit `measurement` entirely if you could not run the probe.
    """
    from apps.a11y.journey import record_journey_finding

    return record_journey_finding(
        tenant_id=tenant_id, run_id=run_id, step=step, checker=checker, criteria=criteria,
        verdict=verdict, confidence=confidence, evidence=evidence,
        suggested_fix=suggested_fix, route=route, selector=selector, measurement=measurement,
    )


def finish_a11y_journey(tenant_id, run_id) -> dict:
    """Close the journey pass: account for every step, then report (QA-20).

    The reconciliation is the part that matters, exactly as it is for a baseline audit. Every
    frozen step you never reported on is recorded as *not reached* — so a journey that walked
    two of six steps says so, instead of reading as a keyboard-clean journey.
    """
    from apps.a11y.journey import finish_journey

    return finish_journey(tenant_id=tenant_id, run_id=run_id)


#: How an event's target resolves to the project — and, where the target has one, the work item
#: — that it belongs to (Bugs S.No 230). `(app.Model, project path, work-item path)`, as ORM
#: lookups from that target's own model.
#:
#: Resolved here, once, rather than threaded through the hundred-odd `log_event` call sites. Most
#: of those callers do have the ids to hand, but editing every one of them — half of them inside
#: the build and orchestration paths — is a large diff with real regression risk for a fact the
#: platform can look up itself.
#:
#: Several target types resolve to a project and no work item, because they genuinely have none:
#: a repository, a code-index job and an accessibility conformance statement all belong to a
#: project directly. And three types carry no id at all — `branch` and `commit` deliberately pass
#: None (the ref lives in the payload), and one caller passes a runtime value for `target_type` —
#: so anything absent from this table simply resolves to nothing.
_EVENT_SCOPE: dict[str, tuple[str, str, str | None]] = {
    "run": ("runs.Run", "work_item__project_id", "work_item_id"),
    "work_item": ("workitems.WorkItem", "project_id", "id"),
    "approval": ("gates.Approval", "work_item__project_id", "work_item_id"),
    "clarification": ("clarifications.Clarification", "work_item__project_id", "work_item_id"),
    # An artifact's run is nullable, so its work item may legitimately be unknown.
    "artifact": ("registry.Artifact", "project_id", "run__work_item_id"),
    "repository": ("projects.Repository", "project_id", None),
    "source_document": ("integrations.SourceDocument", "project_id", None),
    "drift_record": ("integrations.DriftRecord", "project_id", None),
    "test_execution": ("quality.TestExecution", "project_id", "work_item_id"),
    "test_quarantine": ("quality.TestQuarantine", "project_id", None),
    "preview_env": ("quality.PreviewEnv", "project_id", "work_item_id"),
    "code_intel_job": ("runs.CodeIntelJob", "project_id", None),
    "a11y_finding": ("a11y.A11yFinding", "project_id", None),
    "a11y_conformance": ("a11y.A11yConformanceStatement", "project_id", None),
    "a11y_audit": ("a11y.A11yBaselineAudit", "project_id", None),
}


def _event_scope(tenant_id, target_type, target_id) -> tuple[str | None, str | None]:
    """The `(project_id, work_item_id)` an event belongs to, or `(None, None)`.

    Never raises, and that is the point: appending to the ledger must not acquire a new way to
    fail. Several call sites are best-effort error paths where an exception here would turn a
    logging no-op into the failure being logged about, and `target_id` is a UUID column that
    three target types never populate.
    """
    if target_type == "project":
        return (str(target_id), None) if target_id else (None, None)
    scope = _EVENT_SCOPE.get(target_type)
    if scope is None or not target_id:
        return None, None
    model_path, project_path, work_item_path = scope
    try:
        from django.apps import apps as django_apps

        model = django_apps.get_model(model_path)
        paths = [project_path] + ([work_item_path] if work_item_path else [])
        row = (
            model.objects.filter(id=target_id, tenant_id=tenant_id)
            .values_list(*paths)
            .first()
        )
        if row is None:
            return None, None
        project = str(row[0]) if row[0] else None
        work_item = str(row[1]) if work_item_path and row[1] else None
        return project, work_item
    except Exception:      # noqa: BLE001 — an event must always be recordable
        logger.debug("could not scope event target %s:%s", target_type, target_id,
                     exc_info=True)
        return None, None


def log_event(tenant_id, actor, action, target_type, target_id, payload=None,
              project_id=None, work_item_id=None) -> dict:
    """Append one event to the ledger.

    `project_id`/`work_item_id` are optional: a caller that already knows them can say so, and
    anything left unsaid is resolved from the target (S.No 230). They are what lets the agent
    briefing show a run its OWN project's history instead of the whole workspace's.
    """
    with tenant_context(tenant_id):
        if project_id is None and work_item_id is None:
            project_id, work_item_id = _event_scope(tenant_id, target_type, target_id)
        event = Event.objects.create(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload or {},
            project_id=project_id,
            work_item_id=work_item_id,
        )
        return _event(event)


def list_work_items(tenant_id, project_id, state=None) -> list[dict]:
    """The project's backlog as an agent sees it. Carrier work items are excluded (S5-27): they
    are internal plumbing that only exists to host an onboarding/vision run, never backlog a human
    authored — and they are `epic`s, so an agent assessing "does this project have a backlog?"
    counted the platform's own scaffolding as the answer. Same exclusion the user-facing backlog
    list already applies (api WorkItemViewSet)."""
    from integrations.onboarding import carrier_q

    with tenant_context(tenant_id):
        qs = WorkItem.objects.filter(
            tenant_id=tenant_id, project_id=project_id).exclude(carrier_q())
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
        # Bugs S.No 140. A person cancelled this item, and every automated caller of this
        # function forces a state without asking what the item's current one is: a merged PR
        # webhook would flip it to `done`, a rejected gate or a failed build would flip it back
        # to `in_progress`. Any of those silently un-cancels a decision a human made, and the
        # board would show work nobody intends to do.
        #
        # Skipped rather than raised. These callers are Temporal activities; raising here would
        # fail the workflow over a state change that was never important to it. The skip is
        # recorded so it is visible in the ledger rather than merely quiet, and the unchanged
        # item is returned so a caller that checks can tell nothing moved.
        if work_item.state == WorkItem.State.CANCELLED and to_state != WorkItem.State.CANCELLED:
            log_event(tenant_id, "orchestrator", "workitem.transition_skipped", "work_item",
                      str(work_item.id),
                      {"to_state": to_state, "from_state": work_item.state,
                       "reason": "the item is cancelled — only a person can reopen it"})
            return _work_item(work_item)
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


def get_artifact_body(tenant_id, artifact_id, state=None, object_store=None,
                      start=0) -> dict:
    """Read-through the actual body of an artifact — the read-half agents need to consume
    content (e.g. the implementation agent reading a screen's wireframe HTML), since
    `get_artifact` returns pointers only. For a multi-state wireframe (external_ref.states),
    pass `state` (e.g. "state-1-default") to fetch ONE state; omit it to get the default/
    primary body plus the list of available state names. One state per call stays within the
    MCP token budget. Never copies the body onto the row (#1/#3).

    A body larger than the read cap comes back one window at a time: `next_start` is the offset to
    pass on the next call, and is None on the last window. Before this, an oversized body was
    flagged `truncated` and the rest was simply unreachable — which is why a long PRD could not
    be read in full by any downstream phase."""
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
            max_bytes=_MAX_BODY_READ_BYTES, start=start)


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
#: Set to the SAME ceiling a single artifact body reads at (`_MAX_BODY_READ_BYTES`, 400 KB) —
#: the limit the greenfield build path arrived at when it hit this identical wall. A payload does
#: not travel once: the companion decodes what the platform sends and the MCP layer re-encodes it
#: for the stdio hop, with a summary and JSON envelope riding along, so the figure that leaves
#: here is not the figure that arrives. 400 KB is the size proven to survive that round trip;
#: anything more generous is guesswork dressed up as headroom.
_MAX_VISION_PAYLOAD_BYTES = _MAX_BODY_READ_BYTES

#: Long edges tried, in order, for a page too heavy to fit even on its own — each step is
#: attempted until the encoded result is inside the budget. A slightly softer render the model can
#: still read beats a failed run and no render at all; a dense screenshot may need several steps.
_VISION_FALLBACK_STEPS = (1000, 800, 640, 480)


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
            # First page of the call and already over budget: shrink until it actually fits.
            # Re-encoding ONCE at a fixed size was not enough — a dense wireframe screenshot is
            # still over the limit at 1000px, and including it anyway put the whole message past
            # what the transport accepts, killing the run. Text pages never reached this branch,
            # so only image-heavy documents failed. Step down until it fits, and if even the
            # smallest rendering doesn't, skip the page with a note rather than take the run down
            # — one unreadable page costs a page; an oversized message costs the document.
            for px in _VISION_FALLBACK_STEPS:
                encoded = base64.b64encode(
                    downscale_image_for_vision(raw, max_px=px)
                ).decode("ascii")
                if len(encoded) <= budget:
                    break
            else:
                consumed += 1
                out.append({
                    "name": pi.get("name"), "page": pi.get("page"), "mime": "image/png",
                    "error": "this page could not be sent small enough to read; "
                             "note it as [unreadable page] rather than guessing its content",
                })
                continue
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


#: How much of one repository file a single `get_pr_file` call returns. Shares the body-read cap
#: because it rides the same MCP message, whose transport rejects anything over 1 MiB.
_MAX_PR_FILE_READ_BYTES = _MAX_BODY_READ_BYTES


def get_pr_file(tenant_id, pr_ref, path, start=0, project_id=None) -> dict:
    """Read one file from a pull request, a window at a time. **Reviewer only.**

    The review agent reasons over the diff the platform inlines into its briefing, and a file
    longer than the inline window had its tail cut — while the review still reported as a
    completed review. Worse, the briefing's own fallback line told the agent to "fetch the PR via
    the platform tools" when **no granted tool could read a repository file at all**; an agent
    that hit it was being asked to do something impossible, and reviewed nothing instead.

    This is the tool that line always assumed. Read-only: it fetches through the CodeHost
    capability (never GitHub directly, so a different host stays swappable) and writes nothing.

    `pr_ref` is the stable "owner/name#N" handle from the briefing. Paginate exactly like
    `get_source_extraction`: call again with `start=<next_start>` until `next_start` is null.
    """
    from integrations.registry import get_capability

    start = max(0, int(start or 0))
    with tenant_context(tenant_id):
        try:
            codehost = get_capability(tenant_id, "codehost")
            pr = codehost.get_pull_request(pr_ref=str(pr_ref))
            ref = getattr(pr, "sha", None) or getattr(pr, "head", None) or ""
            content = codehost.get_file(repo=getattr(pr, "repo", None), path=str(path), ref=ref)
        except Exception as exc:  # noqa: BLE001 — a read failure is an answer, never a crash
            # Say which file and why. A reviewer that cannot read a file must be able to report
            # that honestly rather than guess at its contents or silently skip it.
            return {"path": str(path), "body": "", "total_bytes": 0, "start": start,
                    "next_start": None,
                    "error": f"could not read '{path}' from {pr_ref}: {exc}"}

    # Slice by BYTE, like `get_source_extraction`, so one window is bounded regardless of what the
    # characters cost; a split multi-byte character is dropped by "replace" at the seam and the
    # next window resumes from the byte offset, so the file itself loses nothing.
    raw = (content or "").encode("utf-8")
    chunk = raw[start:start + _MAX_PR_FILE_READ_BYTES]
    nxt = start + len(chunk)
    return {"path": str(path), "body": chunk.decode("utf-8", "replace"),
            "total_bytes": len(raw), "start": start,
            "next_start": nxt if nxt < len(raw) else None}


def get_source_extraction(tenant_id, source_document_id, start=0, object_store=None) -> dict:
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
        raw = _obj_store(object_store).get(key)
    except Exception as exc:  # noqa: BLE001
        return {"body": "", "filename": filename, "title": title, "fidelity": fidelity,
                "error": f"the extraction could not be read: {exc}"}
    # PAGINATED, not truncated. One message still cannot exceed what the agent transport accepts,
    # so a long extraction has to be split — but splitting is not the same as discarding. Cutting
    # at the cap would mean a client's own specification silently arrives 60% read, and an
    # onboarding built on 60% of a document is wrong in a way nobody can see. The agent reads on
    # with `start=<next_start>` until `next_start` is null and receives every byte.
    # Sliced on a byte boundary and decoded with "replace", so a multi-byte character landing on
    # the seam costs one glyph rather than derailing the decode.
    start = max(0, int(start or 0))
    chunk = raw[start:start + _MAX_BODY_READ_BYTES]
    nxt = start + len(chunk)
    return {"body": chunk.decode("utf-8", "replace"), "filename": filename, "title": title,
            "fidelity": fidelity, "total_bytes": len(raw), "start": start,
            "next_start": nxt if nxt < len(raw) else None}


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
