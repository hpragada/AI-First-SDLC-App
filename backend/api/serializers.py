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
from apps.integrations.models import SourceDocument
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile
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


class TenantAdminSerializer(serializers.Serializer):
    """Input for PATCH /api/users/{id}/ — flip the tenant-admin flag (admin)."""

    is_tenant_admin = serializers.BooleanField()


# ── Project + Profile ───────────────────────────────────────────────
class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "track", "repo_topology", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProjectProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectProfile
        fields = [
            "id", "project", "description", "domain", "tech_stack", "coding_standards",
            "nfrs", "constraints", "glossary", "important_context", "version",
        ]
        read_only_fields = ["id", "project", "version"]


# ── WorkItem ────────────────────────────────────────────────────────
class WorkItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkItem
        fields = [
            "id", "project", "repo", "feature_stream", "title", "description",
            "type", "state", "parent", "depends_on", "assignee", "takeover_flag",
            "external_ref", "created_at",
        ]
        # external_ref is set by reconciliation (proposed→accepted), not by clients.
        read_only_fields = ["id", "project", "state", "external_ref", "created_at"]


class TriggerSerializer(serializers.Serializer):
    """Input for the phase trigger (replaces the legacy slash command — §5)."""

    agent_key = serializers.CharField()
    gate_type = serializers.CharField(required=False, default="phase_gate")
    required_role = serializers.CharField(required=False, allow_null=True, default=None)
    # The triggering user (pre-auth). Routes the run to their enrolled local companion
    # (req #1 — execution_mode resolves to "companion" when they have one); omit for the
    # server-side fallback.
    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)


# ── Run ─────────────────────────────────────────────────────────────
class RunSerializer(serializers.ModelSerializer):
    class Meta:
        model = Run
        fields = [
            "id", "work_item", "agent_spec", "engine", "model", "prompt_version",
            "temporal_workflow_id", "status", "cost_usd", "inputs", "outputs",
            "started_at", "ended_at", "created_at",
        ]
        read_only_fields = fields


# ── Artifact + TraceEdge ────────────────────────────────────────────
class ArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artifact
        # Pointer + provenance only; never the body (#1/#3).
        fields = [
            "id", "project", "repo", "run", "phase", "type", "status", "sor",
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
    class Meta:
        model = Event
        fields = ["id", "actor", "action", "target_type", "target_id", "ts", "payload"]
        read_only_fields = fields


# ── Approval / gate decision ────────────────────────────────────────
class ApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Approval
        fields = [
            "id", "run", "gate_type", "work_item", "required_role", "approver",
            "decision", "comment", "decided_at", "created_at",
        ]
        read_only_fields = fields


class GateDecisionSerializer(serializers.Serializer):
    """Input for deciding a gate (spec §6). `user_id` is the pre-auth/runner fallback only —
    under a session the actor is the authenticated user and this is ignored (P4.7-T5)."""

    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    # Reviewer's gate-checklist updates (e.g. WCAG criteria marked satisfied on the design
    # gate); a required-but-unsatisfied condition blocks an APPROVED decision (D6).
    conditions = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )


# ── Clarification / interactive Q&A (req #2) ────────────────────────
class ClarificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Clarification
        fields = [
            "id", "run", "work_item", "phase", "status", "questions", "answers",
            "context", "answered_by", "answered_at", "created_at",
        ]
        read_only_fields = fields


class ClarificationAnswerSerializer(serializers.Serializer):
    """Input for answering a clarification. `user_id` is the pre-auth/runner fallback only —
    under a session the actor is the authenticated user (P4.7-T5). `answers` maps each
    question id to the human's answer."""

    user_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    answers = serializers.DictField(required=False, default=dict)


# ── Brownfield-lite onboarding ──────────────────────────────────────
class SourceDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceDocument
        fields = [
            "id", "project", "filename", "mime", "status",
            "extracted_artifact_ids", "provenance", "created_at",
        ]
        read_only_fields = fields


class AdoptSerializer(serializers.Serializer):
    """Input for the onboarding review gate. `user_id` must hold product_owner."""

    user_id = serializers.UUIDField()
