"""DRF serializers for the Phase-0 REST surface.

Read serializers are ModelSerializers (pointers + provenance, never artifact
bodies — #1/#3). Write paths that aren't plain model creates (tenant bootstrap,
phase trigger, gate decision) use explicit input serializers so validation is
visible and the view can hand clean kwargs to the domain service.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.base import Role
from apps.clarifications.models import Clarification
from apps.gates.models import Approval
from apps.integrations.models import DriftRecord, IntegrationConnection, SourceDocument
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectCIToken, ProjectProfile, Repository
from apps.registry.models import Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Invitation, Membership, Tenant
from apps.workitems.models import WorkItem


# ── Tenant ──────────────────────────────────────────────────────────
class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "config", "model_routing", "created_at"]
        read_only_fields = ["id", "created_at"]


# ── Auth (P4.7-T1/T2 — server sessions, DECISION-3) ─────────────────
class LoginSerializer(serializers.Serializer):
    """Input for POST /api/auth/login."""

    email = serializers.EmailField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False
    )


class SignupSerializer(serializers.Serializer):
    """Input for POST /api/auth/signup — creates a new tenant + its first admin."""

    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=8
    )
    org_name = serializers.CharField(max_length=255)


# ── Invitations + accept + reset (P4.7-T3) ──────────────────────────
class GrantSerializer(serializers.Serializer):
    """One queued membership on an invitation: a project + a role."""

    project_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=Role.choices)


class InvitationCreateSerializer(serializers.Serializer):
    """Input for POST /api/invitations/ (admin)."""

    email = serializers.EmailField()
    name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    grants = GrantSerializer(many=True, required=False, default=list)


class InvitationSerializer(serializers.ModelSerializer):
    """Read shape for an invitation (never exposes the token/hash)."""

    class Meta:
        model = Invitation
        fields = ["id", "email", "name", "status", "grants", "expires_at",
                  "accepted_at", "created_at"]
        read_only_fields = fields


class AcceptInvitationSerializer(serializers.Serializer):
    """Input for POST /api/auth/accept-invitation."""

    token = serializers.CharField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=8
    )
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class RequestResetSerializer(serializers.Serializer):
    """Input for POST /api/auth/request-reset."""

    email = serializers.EmailField()


class ResetSerializer(serializers.Serializer):
    """Input for POST /api/auth/reset."""

    token = serializers.CharField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=8
    )


# ── User & role management (P4.7-T4) ────────────────────────────────
class MembershipSerializer(serializers.ModelSerializer):
    """Read shape for a project-role grant."""

    user_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "project", "role", "created_at"]
        read_only_fields = fields


class MembershipCreateSerializer(serializers.Serializer):
    """Input for POST /api/projects/{id}/memberships/ (admin) — grant a role to a user."""

    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=Role.choices)


class ProjectCITokenSerializer(serializers.ModelSerializer):
    """Read shape for a CI ingest token — **metadata only**. The secret (and its hash) is never
    serialized; the raw token is returned once, separately, at issue time."""

    class Meta:
        model = ProjectCIToken
        fields = ["id", "label", "status", "last_used_at", "created_at"]
        read_only_fields = fields


class TenantAdminSerializer(serializers.Serializer):
    """Input for PATCH /api/users/{id}/ — flip the tenant-admin flag (admin)."""

    is_tenant_admin = serializers.BooleanField()


# ── Integrations + secret store (P4.7-T6, DECISION-4) ───────────────
class IntegrationSerializer(serializers.ModelSerializer):
    """Read shape for a connection (S-11 grid). Secret is never exposed — `configured` is the
    only signal a secret has been stored."""

    connector = serializers.CharField(read_only=True)  # slug (e.g. "confluence")
    vendor = serializers.SerializerMethodField()        # human label (e.g. "Confluence")
    status = serializers.SerializerMethodField()
    binding = serializers.JSONField(source="scopes", read_only=True)
    configured = serializers.BooleanField(source="is_configured", read_only=True)

    class Meta:
        model = IntegrationConnection
        fields = ["id", "capability", "connector", "vendor", "status", "configured",
                  "binding", "created_at"]
        read_only_fields = fields

    def get_vendor(self, obj) -> str:
        from apps.integrations.catalog import vendor_label

        return vendor_label(obj.capability, obj.connector)

    def get_status(self, obj) -> str:
        """UI status the S-11 grid understands: a failed health check → 'failed', a
        stored/usable credential → 'connected', otherwise 'not_connected'. (The raw
        `health` enum is unknown/healthy/degraded/down — the grid never spoke that.)"""
        if obj.health == IntegrationConnection.Health.DOWN:
            return "failed"
        if obj.is_configured:
            return "connected"
        return "not_connected"


class IntegrationCreateSerializer(serializers.Serializer):
    """Input for POST /api/integrations/ (admin). `secrets` is write-only end-to-end — never
    echoed back in any response."""

    capability = serializers.CharField()
    vendor = serializers.CharField()
    binding = serializers.DictField(required=False, default=dict)
    secrets = serializers.DictField(required=False, default=dict)


class IntegrationUpdateSerializer(serializers.Serializer):
    """Input for PATCH /api/integrations/{id}/ (admin). Every field is optional — only the
    keys actually supplied are changed; omitting `secrets` leaves the stored credential
    untouched (DECISION-4)."""

    vendor = serializers.CharField(required=False)
    binding = serializers.DictField(required=False)
    secrets = serializers.DictField(required=False)


class IntegrationTestCredentialsSerializer(serializers.Serializer):
    """Input for POST /api/integrations/test-credentials/ (admin) — test BEFORE saving (Bugs
    S.No 156). Same shape as create, but nothing is persisted: the credentials are probed on a
    throwaway in-memory connection and never written to the tenant."""

    capability = serializers.CharField()
    vendor = serializers.CharField()
    binding = serializers.DictField(required=False, default=dict)
    secrets = serializers.DictField(required=False, default=dict)


# ── Repositories (P4.7-T7) ────────────────────────────────────────────
class RepositoryCreateSerializer(serializers.Serializer):
    """Input for POST /api/projects/{id}/repositories/ (tech_lead/admin)."""

    name = serializers.CharField()
    role = serializers.CharField(required=False, default="")
    base_branch = serializers.CharField(required=False, default="main")
    # Manual "point 09b at a running app" URL (P3-09bR); optional at add time, editable later.
    preview_url = serializers.CharField(required=False, default="", allow_blank=True)


class RepositoryUpdateSerializer(serializers.Serializer):
    """Input for PATCH /api/projects/{id}/repositories/{rid}/ (tech_lead/admin). Only the fields
    provided are changed — currently the manual preview URL."""

    preview_url = serializers.CharField(required=False, allow_blank=True)


# ── Brownfield onboarding (P4.7-T8) ───────────────────────────────────
class CodeIntelDispatchSerializer(serializers.Serializer):
    """Input for POST /api/projects/{id}/code-intel/ (tech_lead/admin). B4: this endpoint now
    only **dispatches** an indexing job for a repo — it no longer accepts a client-supplied
    analysis result. The real index can arrive only from the companion report sink, so a
    fabricated `{"file_count": 99999}` from the web can no longer be persisted (B4-2)."""

    repo_id = serializers.CharField()
    user_id = serializers.CharField(required=False, allow_blank=True)


class _ConfluenceLinkSerializer(serializers.Serializer):
    """One row of the B3-4 "Link your existing docs" form: a Confluence page reference (full URL
    or bare page id), optionally with the lifecycle type the caller declares it as.

    `type` is OPTIONAL (S3-10). A linked page now declares its type at ADOPT, the way an uploaded
    file does, so the form no longer sends one — and requiring it here rejected the request before
    `link_confluence_pages`, which already defaults a missing type to `document`, ever saw it."""

    page = serializers.CharField()
    type = serializers.CharField(required=False, allow_blank=True)


class LinkConfluenceSerializer(serializers.Serializer):
    """Input for POST /api/projects/{id}/link-confluence/ (B3-4) — register user-provided
    Confluence pages as typed pointers. Validation of the type against the canonical set happens
    in the service (`link_confluence_pages`), so one bad row returns a per-row error, not a 400."""

    links = _ConfluenceLinkSerializer(many=True)


# ── API contracts & drift (P4.7-T9) ───────────────────────────────────
class DriftRecordSerializer(serializers.ModelSerializer):
    # Enrich each impacted entry with human-readable names so the UI never shows raw UUIDs
    # (Bugs S.No 120, Part C-2). Batched lookups — no N+1.
    impacted = serializers.SerializerMethodField()

    class Meta:
        model = DriftRecord
        fields = ["id", "project", "artifact", "kind", "required_role", "status",
                  "detail", "impacted", "decided_by", "decided_at", "comment", "created_at"]
        read_only_fields = fields

    def get_impacted(self, obj):
        from apps.projects.models import Repository
        from apps.registry.models import Artifact

        imps = obj.impacted or []
        node_ids = [i.get("node") for i in imps if i.get("node")]
        repo_ids = [i.get("repo_id") for i in imps if i.get("repo_id")]
        titles = {
            str(a.id): (a.title or a.type)
            for a in Artifact.objects.filter(id__in=node_ids, tenant_id=obj.tenant_id)
        } if node_ids else {}
        repos = {
            str(r.id): r.name
            for r in Repository.objects.filter(id__in=repo_ids, tenant_id=obj.tenant_id)
        } if repo_ids else {}
        return [
            {**i,
             "node_title": titles.get(str(i.get("node")), ""),
             "repo_name": repos.get(str(i.get("repo_id")), "")}
            for i in imps
        ]


class DriftDecisionSerializer(serializers.Serializer):
    """Input for POST /api/drift/{id}/decide/ — `user_id` is the pre-auth/runner fallback only
    (P4.7-T5 actor resolution)."""

    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    decision = serializers.ChoiceField(choices=["accept", "reject"])
    comment = serializers.CharField(required=False, allow_blank=True, default="")


# ── Project + Profile ───────────────────────────────────────────────
class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "track", "repo_topology", "status", "created_at"]
        # B0-2: repo_topology is DERIVED from the project's repo count (apps.projects.repos.
        # _recompute_topology reconciles it on every repo add/remove). The client must not be
        # able to assert it — otherwise a project persists as e.g. "multi" with zero repos.
        # Read-only means it's still returned to the client, just never written from a request.
        read_only_fields = ["id", "repo_topology", "created_at"]


class ProjectProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectProfile
        fields = [
            "id", "project", "description", "domain", "tech_stack", "coding_standards",
            "nfrs", "constraints", "glossary", "export_policy", "a11y", "important_context",
            "version",
        ]
        read_only_fields = ["id", "project", "version"]

    def validate_a11y(self, value):
        """Reject an accessibility policy the platform cannot honour, at the point of writing.

        This is the real guard (QA-08): a stored policy is read while a gate is opening and
        while defects are reconciled, and neither of those may fail — so a typo has to be caught
        here, with a 400 someone can read, rather than at 3am inside a workflow.
        """
        from apps.a11y.policy import A11yPolicyError, validate_policy

        try:
            validate_policy(value)
        except A11yPolicyError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        # The raw block is stored, not the resolved one: a project that has only set a target
        # should keep following the default severities if that default is ever revised.
        return value


# ── WorkItem ────────────────────────────────────────────────────────
class WorkItemSerializer(serializers.ModelSerializer):
    # Human key ("WI-42") + its raw number, so the UI never has to show the UUID.
    key = serializers.ReadOnlyField()

    class Meta:
        model = WorkItem
        fields = [
            "id", "key", "number", "project", "repo", "feature_stream", "title", "description",
            "type", "state", "parent", "depends_on", "assignee", "takeover_flag",
            "external_ref", "created_at",
        ]
        # external_ref is set by reconciliation (proposed→accepted), not by clients.
        read_only_fields = ["id", "key", "number", "project", "state", "external_ref", "created_at"]


class WorkItemPatchSerializer(serializers.ModelSerializer):
    """P4.8-T1 bucket-B gap A: edit surface for S-15/S-16 "Edit" — title/description/type,
    plus `repo` (Hybrid Option C: assign or redirect the work item's target repository —
    the reviewer's override at the gate, and the per-task redirect until build). Never
    state/parent/takeover_flag/external_ref (those change via their own actions)."""

    # RLS scopes this queryset to the tenant; the view additionally checks the repo is on
    # this work item's project. `allow_null` clears the assignment (fall back to default repo).
    repo = serializers.PrimaryKeyRelatedField(
        queryset=Repository.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = WorkItem
        fields = ["title", "description", "type", "repo"]


class TriggerSerializer(serializers.Serializer):
    """Input for the phase trigger (replaces the legacy slash command — §5)."""

    agent_key = serializers.CharField()
    gate_type = serializers.CharField(required=False, default="phase_gate")
    required_role = serializers.CharField(required=False, allow_null=True, default=None)
    # The triggering user (pre-auth). Routes the run to their enrolled local companion
    # (req #1 — execution_mode resolves to "companion" when they have one); omit for the
    # server-side fallback.
    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class BuildTriggerSerializer(serializers.Serializer):
    """Input for the build trigger — starts the implementation `BuildWorkflow` saga on a
    WorkItem (the REST surface for `orchestration.trigger.trigger_build`). `repo`/`base` default
    to the WorkItem's Repository; `agent_key` defaults to the implementation agent."""

    agent_key = serializers.CharField(required=False, default="07_implementation")
    repo = serializers.CharField(required=False, allow_null=True, default=None)
    base = serializers.CharField(required=False, allow_null=True, default=None)
    required_role = serializers.CharField(required=False, default="reviewer")
    # Same companion-routing semantics as TriggerSerializer: the build claims onto the
    # triggering user's enrolled local companion (/api/runner/work/).
    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)


# ── Run ─────────────────────────────────────────────────────────────
class RunSerializer(serializers.ModelSerializer):
    # `agent_spec` is the AgentSpec primary key (a UUID). Also expose the AgentSpec's
    # human-facing key ("04_architecture") and phase label so the UI can show a readable
    # phase and re-trigger by key — never the UUID (Bugs.xlsx row 21: "no AgentSpec
    # registered for key '<uuid>'" came from re-triggering with the UUID).
    agent_key = serializers.SerializerMethodField()
    agent_phase = serializers.SerializerMethodField()

    class Meta:
        model = Run
        fields = [
            "id", "work_item", "agent_spec", "agent_key", "agent_phase", "engine", "model",
            "prompt_version", "temporal_workflow_id", "status", "cost_usd", "inputs",
            "outputs", "started_at", "ended_at", "created_at",
        ]
        read_only_fields = fields

    def get_agent_key(self, obj) -> str | None:
        return obj.agent_spec.key if obj.agent_spec_id else None

    def get_agent_phase(self, obj) -> str | None:
        if not obj.agent_spec_id:
            return None
        return obj.agent_spec.phase_label or obj.agent_spec.key


# ── Artifact + TraceEdge ────────────────────────────────────────────
class ArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact
        # Pointer + provenance only; never the body (#1/#3).
        fields = [
            "id", "project", "repo", "run", "phase", "type", "title", "status", "sor",
            "external_ref", "s3_key", "content_hash", "version", "created_at",
        ]
        read_only_fields = fields


class TraceEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TraceEdge
        fields = ["id", "from_artifact", "to_artifact", "rel", "created_at"]
        read_only_fields = fields


# ── Event ───────────────────────────────────────────────────────────
class EventSerializer(serializers.ModelSerializer):
    # The run console renders each event by `kind` (colour) + `message` (text). The Event row
    # only stores `action` + `payload`, so derive both here — without them every console line
    # rendered blank, which read as "the run shows no streaming content" (Bugs.xlsx row 21 iv).
    kind = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "actor", "action", "target_type", "target_id", "ts", "payload",
                  "kind", "message"]
        read_only_fields = fields

    def get_kind(self, obj) -> str:
        action = (obj.action or "").lower()
        if any(w in action for w in ("failed", "rejected", "error", "denied", "blocked", "secret")):
            return "err"
        # "empty" → phase.empty_result: the engine returned no final text. It rendered as
        # neutral info, the same colour as "Phase reported", so a blank phase document read as
        # routine progress in the console.
        if any(w in action for w in ("gate", "clarification", "takeover", "parked", "warning",
                                     "empty")):
            return "warn"
        if any(w in action for w in ("executed", "published", "merged", "approved", "registered", "resumed")):
            return "ok"
        return "info"

    def get_message(self, obj) -> str:
        label = (obj.action or "event").replace(".", " ").replace("_", " ").strip()
        label = label[:1].upper() + label[1:]
        payload = obj.payload or {}
        # `reason` covers build.failed/build.takeover (Bugs S.No 139 — the classified failure
        # reason); without it the console showed a bare "Build failed" with no explanation.
        for key in ("message", "detail", "error", "reason", "comment", "phase",
                    "execution_mode", "branch", "workflow_id"):
            value = payload.get(key)
            if value:
                return f"{label} — {value}"
        return label


# ── Approval / gate decision ────────────────────────────────────────
class ApprovalSerializer(serializers.ModelSerializer):
    # Approver's display name so the UI can show who decided a gate instead of a raw user id.
    approver_name = serializers.SerializerMethodField()
    # The agent phase that opened this gate (the run's agent key, e.g. "06_task_breakdown").
    # The UI keys phase-specific gate panels on this — notably the repo-assignment review, which
    # must render ONLY on the Task Breakdown gate, never resurface on a later merge/phase gate
    # whose sibling tasks still carry their planner repo_assignment (Bugs S.No 106 follow-up).
    phase = serializers.SerializerMethodField()
    # If this merge gate was RE-OPENED because the merge hit a conflict (Bugs S.No 141 / ENH-2),
    # surface the conflict so the gate panel can explain WHY the user is being asked to approve
    # again (resolve in GitHub, then re-approve to retry the merge — no rebuild). None otherwise.
    merge_conflict = serializers.SerializerMethodField()
    # The work item's own title, so a gate can name itself without the client cross-referencing
    # the work-item LIST — which deliberately hides carriers, and so rendered an onboarding gate
    # as a bare id fragment (or, before the project filter moved server-side, dropped it entirely).
    work_item_title = serializers.SerializerMethodField()

    class Meta:
        model = Approval
        fields = [
            "id", "run", "gate_type", "phase", "work_item", "work_item_title", "required_role",
            "approver", "approver_name", "decision", "comment", "decided_at", "created_at",
            "merge_conflict",
        ]
        read_only_fields = fields

    def get_approver_name(self, obj) -> str | None:
        return obj.approver.name if obj.approver_id else None

    def get_phase(self, obj) -> str | None:
        spec = getattr(obj.run, "agent_spec", None)
        return getattr(spec, "key", None) if spec is not None else None

    def get_work_item_title(self, obj) -> str | None:
        return getattr(obj.work_item, "title", None) or None

    def get_merge_conflict(self, obj) -> str | None:
        # Only relevant while the gate is still pending (a re-opened, awaiting-retry merge gate).
        if obj.decision != Approval.Decision.PENDING:
            return None
        outputs = getattr(obj.run, "outputs", None) or {}
        conflict = outputs.get("merge_conflict")
        if not conflict:
            return None
        return conflict if isinstance(conflict, str) else conflict.get("reason") or str(conflict)


class GateDecisionSerializer(serializers.Serializer):
    """Input for deciding a gate (spec §6). `user_id` is the pre-auth/runner fallback only —
    under a session the actor is the authenticated user and this is ignored (P4.7-T5)."""

    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    # Bounded because this text now travels into a composed manifest. Left unbounded it could
    # push past the section's token budget, and a HALF-READ instruction is the worst outcome this
    # feature has — the agent would follow part of it and nobody could see which part.
    comment = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=8000,
    )
    # Reviewer's gate-checklist updates (e.g. WCAG criteria marked satisfied on the design
    # gate); a required-but-unsatisfied condition blocks an APPROVED decision (D6).
    conditions = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    # "Request changes": reject AND re-run the phase with `comment` as authoritative direction.
    revise = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs.get("revise"):
            if attrs.get("decision") != "rejected":
                raise serializers.ValidationError(
                    {"revise": "only a rejection can request changes"})
            if not (attrs.get("comment") or "").strip():
                raise serializers.ValidationError(
                    {"comment": "say what you want changed — the agent re-runs on this text"})
        return attrs


# ── Clarification / interactive Q&A (req #2) ────────────────────────
class ClarificationSerializer(serializers.ModelSerializer):
    # Whether anyone is still listening. A clarification blocks the agent on its `ask_human`
    # tool, and answering resumes THAT session — but only while the session exists. If the run
    # already ended (failed/stalled/completed), the poller is gone and no answer can resume
    # anything, yet the screen still said "answering resumes the run in the same session".
    # Run fad927a2 sat exactly there. The clarification is deliberately left PENDING and
    # answerable — `answer_clarification` rejects any other status, and an answered one is
    # replayed into a re-run's manifest — so the answer is still worth giving; the UI just has
    # to stop promising the wrong thing.
    run_status = serializers.CharField(source="run.status", read_only=True)
    # Who answered, and what they answered ABOUT — both for the history view, which reads back
    # months later. `answered_by` alone is a raw user id, and the work item was only ever
    # resolvable by cross-referencing the backlog. Mirrors `approver_name` / `work_item_title`
    # on ApprovalSerializer so the two history screens can say the same things the same way.
    answered_by_name = serializers.SerializerMethodField()
    work_item_title = serializers.SerializerMethodField()

    class Meta:
        model = Clarification
        fields = [
            "id", "run", "run_status", "work_item", "work_item_title", "phase", "status",
            "questions", "answers", "context", "answered_by", "answered_by_name",
            "answered_at", "created_at",
        ]
        read_only_fields = fields

    def get_answered_by_name(self, obj) -> str | None:
        return obj.answered_by.name if obj.answered_by_id else None

    def get_work_item_title(self, obj) -> str | None:
        return getattr(obj.work_item, "title", None) if obj.work_item_id else None


class ClarificationAnswerSerializer(serializers.Serializer):
    """Input for answering a clarification. `user_id` is the pre-auth/runner fallback only —
    under a session the actor is the authenticated user (P4.7-T5). `answers` maps each
    question id to the human's answer."""

    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    answers = serializers.DictField(required=False, default=dict)


# ── Brownfield-lite onboarding ──────────────────────────────────────
class SourceDocumentSerializer(serializers.ModelSerializer):
    # A3/A4: whether the original file can be viewed, the captured page images (name+page only —
    # never the S3 key), and the derived extraction fidelity for an honest status badge.
    has_original = serializers.SerializerMethodField()
    page_images = serializers.SerializerMethodField()
    fidelity = serializers.SerializerMethodField()
    # Part B fix 4: the standing state of this document's vision pass, so a run that failed after
    # it was dispatched is visible on every page load — not only in the adopt response that
    # started it. Absent (null) when no vision run exists for the document.
    vision = serializers.SerializerMethodField()

    class Meta:
        model = SourceDocument
        fields = [
            "id", "project", "filename", "mime", "status",
            "extracted_artifact_ids", "provenance", "created_at",
            "has_original", "page_images", "fidelity", "vision",
        ]
        read_only_fields = fields

    def _vision_map(self) -> dict:
        """Built once for the whole list (two queries total), then shared by every row — a
        per-row lookup would turn a 20-document page into 40 queries."""
        holder = self.parent if self.parent is not None else self
        cached = getattr(holder, "_vision_cache", None)
        if cached is not None:
            return cached
        instance = holder.instance
        docs = list(instance) if hasattr(instance, "__iter__") else [instance]
        docs = [d for d in docs if d is not None]
        out: dict = {}
        by_project: dict = {}
        for d in docs:
            by_project.setdefault((str(d.tenant_id), str(d.project_id)), []).append(str(d.id))
        from integrations.onboarding import vision_states_for_documents

        for (tenant_id, project_id), ids in by_project.items():
            try:
                out.update(vision_states_for_documents(
                    tenant_id=tenant_id, project_id=project_id, source_document_ids=ids,
                ))
            except Exception:  # noqa: BLE001 — a status extra must never break the document list
                continue
        holder._vision_cache = out
        return out

    def get_vision(self, obj) -> dict | None:
        return self._vision_map().get(str(obj.id))

    def get_has_original(self, obj) -> bool:
        return bool(obj.s3_key)

    def get_fidelity(self, obj) -> str:
        # 'text' (real body) · 'images_only' (needs AI read) · 'empty' · '' (pre-A4 rows).
        return (obj.provenance or {}).get("fidelity", "")

    def get_page_images(self, obj) -> list:
        # Resolved through the shared helper so it works both for documents that keep their pages
        # on the document (uploads since artifacts moved to adopt time) and older ones that keep
        # them on the artifact the upload registered. Never leaks the S3 key.
        from mcp_platform_state.tools import page_images_for

        imgs, _found = page_images_for(str(obj.tenant_id), str(obj.id))
        return [{"name": im.get("name"), "page": im.get("page")} for im in imgs]


class AdoptSerializer(serializers.Serializer):
    """Input for the onboarding review gate. The acting user is the session user (P4.7-T5);
    `user_id` is an optional pre-auth/test fallback. `target_type` (Brownfield B2-1) classifies
    the uploaded document into its lifecycle type so the gap report recognises it as evidence."""

    user_id = serializers.UUIDField(required=False)
    target_type = serializers.CharField(required=False, allow_blank=True)
