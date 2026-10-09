"""DRF serializers for the Phase-0 REST surface.

Read serializers are ModelSerializers (pointers + provenance, never artifact
bodies — #1/#3). Write paths that aren't plain model creates (tenant bootstrap,
phase trigger, gate decision) use explicit input serializers so validation is
visible and the view can hand clean kwargs to the domain service.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
# 2026-10-09 (team-approved mockup 5): DRF's own "Ensure this field has at least 8 characters."
# reached the screen. A person reads the rule, not the field.
PASSWORD_WORDS = {"min_length": "Use at least 8 characters.", "blank": "Enter a password."}


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
        style={"input_type": "password"}, trim_whitespace=False, min_length=8,
        error_messages=PASSWORD_WORDS,
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

    # 2026-10-09: when the invite was last sent. A pending invite is only ever written by its
    # creation and by Resend, so its last write IS its last send.
    sent_at = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "email", "name", "status", "grants", "expires_at",
                  "accepted_at", "created_at", "sent_at"]
        read_only_fields = fields


class AcceptInvitationSerializer(serializers.Serializer):
    """Input for POST /api/auth/accept-invitation."""

    token = serializers.CharField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=8,
        error_messages=PASSWORD_WORDS,
    )
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class RequestResetSerializer(serializers.Serializer):
    """Input for POST /api/auth/request-reset."""

    email = serializers.EmailField()


class ResetSerializer(serializers.Serializer):
    """Input for POST /api/auth/reset."""

    token = serializers.CharField()
    password = serializers.CharField(
        style={"input_type": "password"}, trim_whitespace=False, min_length=8,
        error_messages=PASSWORD_WORDS,
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

    def validate_name(self, value: str) -> str:
        """A name of nothing but spaces was accepted, and then rendered as an empty switcher
        entry nobody could identify (Bugs S.No 211). Store it trimmed, and refuse an empty one —
        the Create button already blocks this in the UI, so only a direct API call reaches here."""
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Give the project a name.")
        return name


class ProjectProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectProfile
        fields = [
            "id", "project", "description", "domain", "tech_stack", "coding_standards",
            "nfrs", "constraints", "glossary", "export_policy", "a11y", "scan",
            "important_context", "version",
        ]
        read_only_fields = ["id", "project", "version"]

    def validate_description(self, value):
        """The briefing's one required field, enforced here as well as on the screen.

        The editor refused to save without a description and said nothing about it — the message
        it was meant to show had only ever been wired into the design gallery, so Save stopped
        silently and took every other edit on the page with it. The screen now says so, and the
        rule lives here too, in the same words, so a direct API call cannot blank the field the
        editor refuses to blank.

        Scoped to requests that actually SEND a description: the endpoint takes partial writes,
        and a future screen saving only the accessibility block should not have to restate the
        briefing. The editor always sends it, so the user-facing path is covered.
        """
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError(
                "A description is required — agents rely on it for every phase.")
        return text

    def validate_scan(self, value):
        """Bugs S.No 185: the registries a security scan may reach. Validated here, at the point
        of writing, for the same reason `a11y` is — it is read while a phase is being dispatched,
        and a typo must surface as a readable 400 rather than as a scan that quietly cannot
        install its tools."""
        if not value:
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("scan must be an object.")
        registries = value.get("registries", [])
        if not isinstance(registries, list) or not all(
            isinstance(h, str) and h.strip() and "/" not in h for h in registries
        ):
            raise serializers.ValidationError(
                "scan.registries must be a list of bare hostnames, e.g. "
                '["pypi.org", "files.pythonhosted.org"] — no scheme and no path.'
            )
        unknown = set(value) - {"registries"}
        if unknown:
            raise serializers.ValidationError(
                f"unknown scan setting(s): {', '.join(sorted(unknown))}")
        return value

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
    # ...and the same for the PARENT, which had no key of its own, so every screen that wanted to
    # name the parent had only `parent` — a UUID — and printed it: the board card's "↖" chip, and
    # the task and defect breadcrumbs, which showed the first eight characters and called it a
    # link. `key` promised above that the UI never has to show a UUID; this is the half of that
    # promise that was missing. Null when the item has no parent.
    parent_key = serializers.SerializerMethodField()

    def get_parent_key(self, obj) -> str | None:
        # `parent_id` rather than `parent`, so an item WITHOUT a parent costs no query at all.
        # With one, the view's `select_related("parent")` has already fetched it — see
        # `WorkItemViewSet.get_queryset`. Without that select_related this is one query per card,
        # and the board lists a whole project in a single response.
        return (obj.parent.key or None) if obj.parent_id else None

    class Meta:
        model = WorkItem
        fields = [
            "id", "key", "number", "project", "repo", "feature_stream", "title", "description",
            "type", "state", "parent", "parent_key", "depends_on", "assignee", "takeover_flag",
            "external_ref", "created_at",
        ]
        # external_ref is set by reconciliation (proposed→accepted), not by clients.
        read_only_fields = ["id", "key", "number", "project", "state", "external_ref",
                            "created_at", "parent_key"]


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


class WorkItemTransitionSerializer(serializers.Serializer):
    """Input for the human state transition (Bugs S.No 140).

    `to_state` is validated against the allowlist in `apps.workitems.cancel`, not here — the
    legal move depends on the state the item is currently in, which this cannot see.
    `reason` is required to cancel, and that too is checked there, so the message a person
    reads is written in one place.
    """

    to_state = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")
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
    # Whether Preview can show anything for this row. Computed server-side, next to
    # `read_artifact_preview` itself, so the two cannot drift — the rule has real subtleties (a
    # wireframe previews from `external_ref.states` with no `s3_key` of its own; Confluence/Jira
    # read through their connector) that a re-implementation in TypeScript would get wrong.
    previewable = serializers.SerializerMethodField()

    def get_previewable(self, obj) -> bool:
        from integrations.preview import artifact_has_preview

        return artifact_has_preview(obj)

    # Whether this row can be handed over as a FILE. Stricter than `previewable` and computed in
    # the same place for the same reason: a preview may legitimately be a link or a synthesised
    # summary, which a file may not - see `artifact_is_downloadable`.
    downloadable = serializers.SerializerMethodField()

    def get_downloadable(self, obj) -> bool:
        from integrations.preview import artifact_is_downloadable

        return artifact_is_downloadable(obj)

    # Was this document's gate already decided while it still sits unpublished? S.No 318.
    # Computed here rather than guessed on screen, because the screen holds only the artifact
    # and the answer lives on its run's approval.
    #
    # It exists because of what the two screens said to each other on 2026-10-05: six documents
    # reading "Waiting for approval" while Gates read "No gates need you". Each was truthful
    # about its own data and together they were nonsense - you were waiting for a decision that
    # could no longer be given, with no way to tell that from either screen.
    gate_decided = serializers.SerializerMethodField()

    def get_gate_decided(self, obj) -> bool:
        from apps.gates.models import Approval

        if obj.status == Artifact.Status.PUBLISHED or not obj.run_id:
            return False
        return Approval.objects.filter(
            tenant_id=obj.tenant_id, run_id=obj.run_id,
            decision=Approval.Decision.APPROVED,
        ).exists()

    class Meta:
        model = Artifact
        # Pointer + provenance only; never the body (#1/#3).
        fields = [
            "id", "project", "repo", "run", "phase", "type", "title", "status", "sor",
            "external_ref", "s3_key", "content_hash", "version", "created_at", "previewable",
            "downloadable", "gate_decided",
            # When it was published, as distinct from when it was drafted (Bugs S.No 224). Null
            # until it is published, which is what "not published" means.
            "published_at",
        ]
        read_only_fields = fields


class TraceEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TraceEdge
        fields = ["id", "from_artifact", "to_artifact", "rel", "created_at"]
        read_only_fields = fields


# ── Event wording ───────────────────────────────────────────────────
#
# One plain sentence per event action, for the run console.
#
# WHY THIS TABLE EXISTS. Every console line used to be built mechanically: take the internal
# action key, swap dots and underscores for spaces, capitalise the first letter, then append the
# first value found under message / detail / error / reason / comment / phase / execution_mode /
# branch / workflow_id. Seven actions had a real sentence. The other thirty-six were their own
# internal names — "Review parse mismatch", "Phase empty result", "Phase dispatched —
# 06_task_breakdown", "Run triggered — companion". The screen-words guard
# (tests/test_refusal_wording.py) could not have caught them: it reads source for literal strings,
# and none of those sentences existed as a literal anywhere. They were assembled at render time.
#
# THE TAIL IS OPT-IN, and that is the load-bearing half. Appending whatever the payload happened
# to hold looked harmless until you read the payloads: `test_cases.materialize_failed` carries
# `str(exc)`, so a Python exception reached a client's screen verbatim, and `phase.empty_result`
# carries a note written for whoever wrote the code ("companion reported ok but the engine
# returned no final text"). Removing the two obviously-machine keys would have left both. So an
# action now declares whether it has a tail and where that tail lives, and nothing else is ever
# appended — which makes the next leak impossible rather than merely absent, including from
# payload keys nobody has read yet.
#
# Some tails are COUNTED rather than copied: "attempt 3", "2 sections shortened". Those are the
# small functions below, and they are the reason a tail may be a callable.
#
# ADDING AN EVENT THAT A RUN OWNS? Add it here too, or tests/test_event_wording.py fails. That
# test is the whole point of the table: the thirty-seventh unworded action cannot arrive quietly.

#: Payload keys allowed to supply a tail. Each one was read at its call site and holds text
#: written for a person: `error`/`reason` are the CLASSIFIED failure causes (Bugs S.No 139),
#: `comment` is a reviewer's own words at a gate, `title` is a document's name. Anything else —
#: ids, branches, modes, statuses, exception text, agent keys — is not a sentence and is not here.
SAFE_TAIL_KEYS = frozenset({"error", "reason", "comment", "title"})

#: How long a tail may run before it is cut. A classified failure reason is a sentence or two; a
#: screen-wide one came from somewhere it should not have.
_TAIL_LIMIT = 200

#: Markers of a LOG EXCERPT rather than a sentence, checked on the two failure tails.
#:
#: Why this is needed even though both `run.failed` call sites now classify their cause through
#: `describe_phase_failure`: the ledger is append-only. Rows written before the classifier existed
#: are still there and still render, and one of them in the local database says
#: "Command failed with exit code 4294967295 (exit code: 4294967295)\nError output: Check stderr
#: output for details". No amount of care at the write site reaches a row written last month, so the
#: read side has to recognise one. Found by rendering every stored event rather than only the ones a
#: test invents.
#:
#: A classified cause is one sentence of plain prose. A log excerpt gives itself away twice over: it
#: runs to more than one line, and it names machinery. Both checks are on the raw text, before
#: whitespace is collapsed, because the line break is half the evidence.
_LOG_MARKERS = ("exit code", "traceback", "stderr", "stdout", "::", "errno", "activity task",
                "workflow task")

#: The two tails that come out of the failure CLASSIFIER, and are held to a stricter rule than the
#: rest. `describe_build_failure` ends with `return FailureText(rest, rest)` — "already a specific
#: message - kept, never lost" — so an unrecognised failure passes through verbatim. That is the
#: right call for the failure BANNER, which has "Technical details" underneath it to carry the raw
#: text; a console line has nowhere to put it. The local database holds
#: "pr/gate setup failed: Activity task failed", which is Temporal's words after an internal step
#: name, and it would otherwise have been the whole explanation a client was given.
_CLASSIFIED_KEYS = frozenset({"error", "reason"})

#: A classified cause is a clause of ordinary English: "the AI engine reached its usage limit",
#: "no changes to commit", "code review kept finding blocking issues". A slash or an arrow
#: belongs to a path, an internal step name or an error chain, and none of them has one.
#:
#: NOT a colon, though the obvious bad example has one. The park sites write their tail as
#: "stopped: <cause>" on purpose and the team's own test pins "Run paused — stopped: the AI engine
#: reached its usage limit" — so a colon rule would have thrown away a line somebody designed. That
#: test is what caught it. Checked only on the classifier's keys anyway: `comment` is a reviewer
#: typing to a colleague and may contain anything.
_MACHINE_PUNCTUATION = ("/", "->")


def _reads_as_prose(text: str, *, key: str = "") -> bool:
    if "\n" in text or "\r" in text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _LOG_MARKERS):
        return False
    if key in _CLASSIFIED_KEYS and any(mark in text for mark in _MACHINE_PUNCTUATION):
        return False
    return True


def _mode_tail(payload: dict) -> str:
    """Where this run is executing, in the words a client uses for it."""
    return {"companion": "on your machine", "server": "on the platform"}.get(
        str(payload.get("execution_mode") or ""), "")


def _claim_tail(payload: dict) -> str:
    """Only worth saying when the machine has taken this more than once."""
    count = payload.get("claim_count") or 0
    return f"attempt {count}" if isinstance(count, int) and count > 1 else ""


def _next_attempt_tail(payload: dict) -> str:
    """The attempt about to start. The payload does not carry the ceiling, so this does not
    claim one — "attempt 3 of 3" would be invented."""
    nxt = payload.get("next_attempt")
    return f"now on attempt {nxt}" if isinstance(nxt, int) else ""


def _revision_tail(payload: dict) -> str:
    revision = payload.get("revision")
    return f"revision {revision}" if revision else ""


def _findings_tail(payload: dict) -> str:
    """A review's outcome in numbers. "No problems found" is worth saying out loud — it is the
    reader's answer to "did it pass?", and a bare "Code review finished" does not give it."""
    found = payload.get("findings")
    blocking = payload.get("blocking")
    if not isinstance(found, int):
        return ""
    if found == 0:
        return "no problems found"
    said = "1 problem" if found == 1 else f"{found} problems"
    if isinstance(blocking, int) and blocking:
        said += f", {blocking} to fix before merging"
    return said


def _waited_tail(payload: dict) -> str:
    seconds = payload.get("waited_seconds")
    if not isinstance(seconds, int) or seconds < 60:
        return ""
    minutes = seconds // 60
    return f"after {minutes} minute" + ("s" if minutes != 1 else "")


def _publish_failed_tail(payload: dict) -> str:
    """"2 documents affected." — the count, never the internal ids the payload also carries."""
    count = payload.get("count")
    if not isinstance(count, int) or count <= 0:
        return ""
    return "1 document affected" if count == 1 else f"{count} documents affected"


def _assumed_budget_tail(payload: dict) -> str:
    """"10,000 words of room assumed." — never the raw model id.

    The model name is in the payload for whoever queries the events, and it belongs there. It does
    not belong on a client's screen: `claude-sonnet-4-6` is a machine name that answers a question
    the reader did not ask, and the standing rule is that engine internals stay off these lines.
    """
    budget = payload.get("assumed_budget")
    if not isinstance(budget, int) or budget <= 0:
        return ""
    return f"{budget:,} words of room assumed"


def _sections_tail(payload: dict) -> str:
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        return ""
    count = len(sections)
    return f"{count} section shortened" if count == 1 else f"{count} sections shortened"


def _criteria_tail(payload: dict) -> str:
    problems = payload.get("problems")
    total = payload.get("criteria")
    if not isinstance(problems, list) or not problems or not isinstance(total, int):
        return ""
    return f"{len(problems)} of {total} not shown as checked"


@dataclass(frozen=True)
class EventWords:
    """What a run's console says for one action.

    `tail` is a payload key from SAFE_TAIL_KEYS, or a function of the payload, or None for the
    great majority — a line that needs no tail is the normal case, not an omission.
    """

    sentence: str
    tail: str | Callable[[dict], str] | None = None

    def resolve_tail(self, payload: dict) -> str:
        if self.tail is None:
            return ""
        raw = self.tail(payload) if callable(self.tail) else payload.get(self.tail)
        text = str(raw).strip() if raw else ""
        if not text:
            return ""
        # A copied tail must read as prose. A computed one is ours and needs no vetting.
        if not callable(self.tail) and not _reads_as_prose(text, key=self.tail):
            return ""
        # A newline would split the line in two on the screen; payload text is written by agents
        # and by exception strings, so this is not hypothetical.
        text = " ".join(text.split())
        return text[: _TAIL_LIMIT - 1] + "…" if len(text) > _TAIL_LIMIT else text


#: action -> what the console says. Every action a RUN owns must appear here.
EVENT_SENTENCES: dict[str, EventWords] = {
    # ── Starting and sending ────────────────────────────────────────
    "run.triggered": EventWords("Started", _mode_tail),
    "build.triggered": EventWords("Build started"),
    "phase.dispatched": EventWords("Sent to your machine"),
    "build.dispatched": EventWords("Build sent to your machine"),
    "phase.reclaimed": EventWords("Your machine picked this up again", _claim_tail),
    "build.revision_dispatched": EventWords("Changes sent back to your machine"),
    "build.remediation_dispatched": EventWords("Review fixes sent to your machine"),
    # ── Progress and results ───────────────────────────────────────
    "phase.reported": EventWords("Your machine reported back"),
    "build.reported": EventWords("Your machine finished the build and reported back"),
    "run.executed": EventWords("Finished"),
    # The title, never the payload's own `message`: that one is the artifact TYPE joined to the
    # title ("prd — PRD — Spend Export"), and the type is a stored key.
    "artifact.registered": EventWords("Draft saved", "title"),
    "artifacts.published": EventWords("Published to your tools"),
    # Added with the publish loop in `a0082fd` and left without a sentence, so it would have
    # reached the console as "Artifacts publish failed" — the internal name, on a client's screen.
    # The companion guard (`test_every_event_a_run_owns_has_a_sentence`) is exactly what caught it.
    "artifacts.publish_failed": EventWords(
        "Some documents could not be published to your tools", _publish_failed_tail),
    "build.pr_opened": EventWords("Pull request opened"),
    "build.merged": EventWords("Merged"),
    "build.reviewed": EventWords("Code review finished", _findings_tail),
    "review.dispatched": EventWords("Code review started"),
    # NOT "Code review finished", which is what `build.reviewed` says. The two fire seconds apart —
    # the machine sends its findings, then the platform records them — and giving both the same
    # sentence printed it twice in a row on a real console, which reads as a glitch and loses the
    # difference. Found by looking at a real run rather than at the table.
    #
    # `reason` is only set when the review STOPPED, and is classified when it is. Paired with the
    # sentence swap in `get_message`, a stopped review reads "Code review stopped — the AI engine
    # closed before it finished".
    "review.reported": EventWords("Your machine sent its code review back", "reason"),
    # ── Waiting for a person ───────────────────────────────────────
    # The next five keep the wording the team chose on 2026-09-21 and in the pause batch. Moved
    # here unchanged — re-opening settled copy is not this batch's business.
    # The two PARKED lines keep their `reason`, which holds the classified cause of the stop
    # ("stopped: the AI engine reached its usage limit") and not the raw fault — that goes to
    # `error_detail`, which nothing here reads. A park with no explanation is the shape Bugs S.No
    # 146 was about: the reader is told their run has halted and not why.
    "run.parked": EventWords("Run paused", "reason"),
    "build.parked": EventWords("Build paused", "reason"),
    # `run.paused` is a PERSON pausing, so there is nothing to explain — they know why.
    "run.paused": EventWords("Run paused"),
    "run.pause_signal_failed": EventWords(
        "Paused — your machine won't be given new work, but the step already running may still "
        "finish"
    ),
    "run.resume_signal_failed": EventWords("Resumed — your machine can pick this up again"),
    "run.resumed": EventWords("Picked up again"),
    "phase.takeover": EventWords("Waiting for you — nothing was heard back in time"),
    "build.takeover": EventWords("Build waiting for you — nothing was heard back in time"),
    # `comment` is the reviewer's own words at the gate, which is the one thing the reader wants.
    "run.rejected": EventWords("Changes requested at the review gate", "comment"),
    "build.rejected": EventWords("Build changes requested at the review gate", "comment"),
    "run.revision_requested": EventWords(
        "Changes requested — a new attempt was started", _revision_tail),
    "build.merge_conflict": EventWords(
        "Merge hit a conflict — resolve it in GitHub, then approve again"),
    # ── Something went wrong ───────────────────────────────────────
    # `error` and `reason` here are the CLASSIFIED cause, not the raw fault: the call sites put the
    # technical text in `error_detail`, which nothing on this screen reads. Keeping these two is
    # the reason the tail is opt-in rather than removed — without them a reader sees "Build
    # stopped" and is never told why (Bugs S.No 139).
    "run.failed": EventWords("Stopped after a problem", "error"),
    "build.failed": EventWords("Build stopped", "reason"),
    "run.revision_failed": EventWords("The new attempt couldn't be started", "reason"),
    "phase.empty_result": EventWords(
        "The agent finished without writing anything — the draft is empty"),
    "test_cases.materialize_failed": EventWords(
        "The test cases couldn't be created from this plan"),
    "review.timeout": EventWords("The code review didn't finish in time", _waited_tail),
    "review.parse_mismatch": EventWords(
        "The review asked for changes but didn't say which — it is being retried"),
    "review.acceptance_criteria_unverified": EventWords(
        "The review didn't show it checked this task's acceptance criteria", _criteria_tail),
    "run.worker_stalled": EventWords("Your machine stopped reporting back"),
    "build.secret_blocked_retry": EventWords(
        "A password or key was found before pushing — starting over", _next_attempt_tail),
    "build.remediation_exhausted_retry": EventWords(
        "Review fixes ran out of attempts — starting over", _next_attempt_tail),
    # ── Housekeeping ───────────────────────────────────────────────
    "manifest.truncated": EventWords(
        "The agent's briefing was shortened to fit", _sections_tail),
    # The engine model carried no known context window, so the briefing was sized to the platform's
    # long-standing assumption. Worth a line on the console: nothing is wrong with the run, but the
    # agent is working from a smaller briefing than its model could have held, and the cure is one
    # row in the model table rather than anything the reader can do.
    "manifest.model_unknown": EventWords(
        "The briefing was sized for an unfamiliar engine", _assumed_budget_tail),
    "run.reconciled": EventWords("Put back in step with your machine"),
    "run.worker_recovered": EventWords("Your machine started reporting again"),
}


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
        if any(w in action for w in ("executed", "published", "merged", "approved",
                                     "registered", "resumed")):
            return "ok"
        return "info"

    def get_message(self, obj) -> str:
        """One sentence for the run console. See EVENT_SENTENCES above for the whole vocabulary.

        Nothing is composed from the action key any more, and nothing is appended that the action
        did not ask for — the two habits that put "Phase dispatched — 06_task_breakdown" and a raw
        Python exception on a client's screen.
        """
        payload = obj.payload or {}
        words = EVENT_SENTENCES.get(obj.action or "")
        if words is None:
            # Either a historical row whose action no longer exists, or one added without a
            # sentence — which tests/test_event_wording.py fails on, so it should not reach here.
            # Humanising the key is still better than a blank line: an empty console read as
            # "this run has nothing to show" (Bugs.xlsx row 21 iv).
            label = (obj.action or "event").replace(".", " ").replace("_", " ").strip()
            return label[:1].upper() + label[1:]
        sentence = words.sentence
        # The one line whose wording depends on its payload rather than its action: a review that
        # reports FAILED is a review that stopped, not a report that arrived (2026-09-21).
        if obj.action == "review.reported" and payload.get("status") == "failed":
            sentence = "Code review stopped"
        tail = words.resolve_tail(payload)
        return f"{sentence} — {tail}" if tail else sentence


# ── Approval / gate decision ────────────────────────────────────────
class ApprovalSerializer(serializers.ModelSerializer):
    # Approver's display name so the UI can show who decided a gate instead of a raw user id.
    approver_name = serializers.SerializerMethodField()
    # The agent phase that opened this gate (the run's agent key, e.g. "06_task_breakdown").
    # The UI keys phase-specific gate panels on this — notably the repo-assignment review, which
    # must render ONLY on the Task Breakdown gate, never resurface on a later merge/phase gate
    # whose sibling tasks still carry their planner repo_assignment (Bugs S.No 106 follow-up).
    phase = serializers.SerializerMethodField()
    # The same run's phase LABEL — a DIFFERENT vocabulary, and the reason this field exists.
    #
    # `phase` above returns the agent KEY (`06_task_breakdown`, `00c_intelligent_context_extractor`)
    # and must keep doing so: the phase-specific gate panels key on it. `Artifact.phase` stores the
    # catalog's phase LABEL (`task_breakdown`, `context_extraction`). So a client holding an
    # approval and asking `/artifacts?phase=<approval.phase>` gets ZERO rows — a silent empty list,
    # which is worse than the wrong-but-populated list it would replace.
    #
    # The client-side workaround was to strip the `NN_` prefix. Measured against the whole catalog
    # that is right for 10 of 11 agents and WRONG for `00c_intelligent_context_extractor`, whose
    # label is `context_extraction`, not `intelligent_context_extractor`. Rather than fix the
    # heuristic, serve the fact: the platform already knows both. Mirrors
    # `RunSerializer.get_agent_phase` verbatim.
    phase_label = serializers.SerializerMethodField()
    # If this merge gate was RE-OPENED because the merge hit a conflict (Bugs S.No 141 / ENH-2),
    # surface the conflict so the gate panel can explain WHY the user is being asked to approve
    # again (resolve in GitHub, then re-approve to retry the merge — no rebuild). None otherwise.
    merge_conflict = serializers.SerializerMethodField()
    # The work item's own title, so a gate can name itself without the client cross-referencing
    # the work-item LIST — which deliberately hides carriers, and so rendered an onboarding gate
    # as a bare id fragment (or, before the project filter moved server-side, dropped it entirely).
    work_item_title = serializers.SerializerMethodField()
    # Set when this gate's pull request was already merged outside the platform - somebody
    # merged it on GitHub (Bugs S.No 88). {merged_by, merged_at, pr_ref, detected_by}, or None.
    # A NOTE, not a decision: the reviewer still approves, they just finally know what they are
    # approving. Only meaningful while the gate is pending, like merge_conflict above.
    external_merge = serializers.SerializerMethodField()
    # True while nobody is serving the code version this gate's run is pinned to (Bugs S.No
    # 246). The approval itself still lands - `decide_gate` writes the row and signals Temporal
    # either way - so this is only about TIMING, and the screen says so rather than pretending
    # the click did nothing. Pending-only, like the two above, so the notice closes itself the
    # moment the gate is decided.
    run_paused = serializers.SerializerMethodField()

    class Meta:
        model = Approval
        fields = [
            "id", "run", "gate_type", "phase", "phase_label", "work_item", "work_item_title",
            "required_role", "approver", "approver_name", "decision", "comment", "decided_at",
            "created_at", "merge_conflict", "external_merge", "run_paused",
        ]
        read_only_fields = fields

    def get_approver_name(self, obj) -> str | None:
        return obj.approver.name if obj.approver_id else None

    def get_phase(self, obj) -> str | None:
        spec = getattr(obj.run, "agent_spec", None)
        return getattr(spec, "key", None) if spec is not None else None

    def get_phase_label(self, obj) -> str | None:
        spec = getattr(obj.run, "agent_spec", None)
        if spec is None:
            return None
        return spec.phase_label or spec.key

    def get_work_item_title(self, obj) -> str | None:
        return getattr(obj.work_item, "title", None) or None

    def get_external_merge(self, obj) -> dict | None:
        if obj.decision != Approval.Decision.PENDING:
            return None
        return obj.external_merge or None

    def get_run_paused(self, obj) -> bool:
        if obj.decision != Approval.Decision.PENDING:
            return False
        outputs = getattr(obj.run, "outputs", None) or {}
        return bool(outputs.get("worker_stalled"))

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
    # The READABLE key — "WI-3". The clarifications screen had only the internal id and the
    # title, so it drew eight characters of a uuid beside every question. A key is what the
    # work item exists to be referred to by; a uuid fragment is not something anyone can use.
    work_item_key = serializers.SerializerMethodField()

    class Meta:
        model = Clarification
        fields = [
            "id", "run", "run_status", "work_item", "work_item_title", "work_item_key",
            "phase", "status",
            "questions", "answers", "context", "answered_by", "answered_by_name",
            "answered_at", "created_at",
        ]
        read_only_fields = fields

    def get_answered_by_name(self, obj) -> str | None:
        return obj.answered_by.name if obj.answered_by_id else None

    def get_work_item_title(self, obj) -> str | None:
        return getattr(obj.work_item, "title", None) if obj.work_item_id else None

    def get_work_item_key(self, obj) -> str | None:
        """None for a run on a hidden carrier work item, which has no key — the screen then
        shows the title alone rather than falling back to an identifier."""
        return getattr(obj.work_item, "key", None) if obj.work_item_id else None


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
