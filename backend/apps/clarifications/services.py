"""Clarification services (req #2).

An agent **asks** via `create_clarification` (from its `ask_human` tool, proxied over the
runner seam); the companion then polls `get_clarification` until it is answered. A human
**answers** via `answer_clarification` (the web app). Unlike a gate (which needs a specific
role), answering only requires the user be a **member of the project** — they are supplying
missing context, not authorizing a system-of-record write. No Temporal signal is sent: the
agent is blocked on the `ask_human` tool, whose companion-side handler is polling for this
answer and resumes the moment the status flips to ANSWERED (the model is idle on the open
tool call while it waits, so no cost accrues).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from mcp_platform_state import tools

from apps.clarifications.models import Clarification
from apps.runs.models import Run
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership


def question_signature(questions: list) -> str:
    """Stable hash of the question set, so a re-asked (re-dispatched) clarification reuses an
    existing one instead of creating a duplicate. Order-independent on the question id."""
    norm = sorted(
        (
            {
                "id": q.get("id"),
                "text": q.get("text", ""),
                "kind": q.get("kind", "text"),
                "required": bool(q.get("required", True)),
                "options": q.get("options"),
                # `tier` is part of the question's meaning (a re-classified question must not
                # dedupe onto its old tier), so it participates in the idempotency signature.
                "tier": q.get("tier"),
            }
            for q in (questions or [])
        ),
        key=lambda q: str(q["id"]),
    )
    return hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()


def _serialize(clar: Clarification) -> dict:
    return {
        "id": str(clar.id), "status": clar.status, "answers": clar.answers,
        "questions": clar.questions, "phase": clar.phase, "context": clar.context,
    }


def create_clarification(
    *, tenant_id: str, run_id: str, questions: list, context: str = "",
    phase: str = "", signature: str = "",
) -> dict:
    """Create (or reuse) a clarification for a run. **Idempotent by (run, signature)**: an
    existing clarification with the same question set — whether still pending or already
    answered — is returned as-is, so a re-asked question is never duplicated and an
    already-answered one returns its answer immediately (crash-recovery / re-dispatch)."""
    sig = signature or question_signature(questions)
    with tenant_context(tenant_id):
        run = Run.objects.select_related("work_item").get(id=run_id, tenant_id=tenant_id)
        existing = (
            Clarification.objects
            .filter(tenant_id=tenant_id, run_id=run_id, signature=sig)
            .order_by("created_at").first()
        )
        if existing is not None:
            return _serialize(existing)
        clar = Clarification.objects.create(
            tenant_id=tenant_id, run=run, work_item=run.work_item, phase=phase,
            questions=list(questions or []), context=context, signature=sig,
        )
        tools.log_event(
            tenant_id, "agent", "clarification.asked", "clarification", str(clar.id),
            {"run": str(run_id), "questions": [q.get("id") for q in (questions or [])]},
        )
        return _serialize(clar)


def get_clarification(*, tenant_id: str, clarification_id: str) -> dict:
    """Read a clarification's current status + answers (the companion's poll)."""
    with tenant_context(tenant_id):
        clar = Clarification.objects.get(id=clarification_id, tenant_id=tenant_id)
        return _serialize(clar)


class ClarificationError(Exception):
    """The clarification could not be answered (e.g. already answered, missing answers)."""


class ClarificationRoleError(ClarificationError):
    """The answering user is not a member of the clarification's project."""


def _missing_required(questions: list, answers: dict) -> list[str]:
    """Question ids that are required but have no non-empty answer. A `confirm` answer of
    False is still an answer (its str() is non-empty), so only blank/absent values count."""
    missing = []
    for q in questions or []:
        if not q.get("required", True):
            continue
        qid = q.get("id")
        if not str(answers.get(qid, "")).strip():
            missing.append(qid)
    return missing


def _apply_suggestion_defaults(questions: list, answers: dict) -> dict:
    """Fill each unanswered question that carries a `suggestion` (Tier-2/3) with that
    suggestion, so the agent always receives a concrete value even when the human left the
    pre-filled item untouched — and the recorded answers reflect what was actually used.
    A question the human DID answer (any non-blank value, including a `confirm` False) keeps
    the human's value; `suggestion` never overrides a real answer or a required Tier-1 item."""
    merged = dict(answers or {})
    for q in questions or []:
        if "suggestion" not in q:
            continue
        qid = q.get("id")
        if qid in merged and str(merged.get(qid, "")).strip() != "":
            continue  # human supplied a value — keep it
        merged[qid] = q.get("suggestion")
    return merged


def answer_clarification(
    *, tenant_id: str, clarification_id: str, user_id: str, answers: dict
) -> dict:
    """Record a human's answers to a pending clarification (after a project-membership
    check + a required-answer check). Unanswered Tier-2/3 items fall back to the agent's
    `suggestion`. Idempotent guard: a non-pending clarification raises."""
    answers = dict(answers or {})

    with tenant_context(tenant_id):
        clar = Clarification.objects.select_related("work_item").get(
            id=clarification_id, tenant_id=tenant_id
        )
        if clar.status != Clarification.Status.PENDING:
            raise ClarificationError(f"clarification already {clar.status}")

        is_member = Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=clar.work_item.project_id
        ).exists()
        if not is_member:
            raise ClarificationRoleError(
                f"user {user_id} is not a member of this project"
            )

        missing = _missing_required(clar.questions, answers)
        if missing:
            raise ClarificationError(f"missing required answer(s): {missing}")

        # Backfill untouched Tier-2/3 items from their suggestion (after the required check,
        # so a blank Tier-1 still fails rather than being silently defaulted).
        answers = _apply_suggestion_defaults(clar.questions, answers)

        clar.answers = answers
        clar.status = Clarification.Status.ANSWERED
        clar.answered_by_id = user_id
        clar.answered_at = datetime.now(UTC)
        clar.save(update_fields=["answers", "status", "answered_by", "answered_at",
                                 "updated_at"])

        tools.log_event(
            tenant_id, f"user:{user_id}", "clarification.answered", "clarification",
            str(clar.id), {"questions": [q.get("id") for q in (clar.questions or [])]},
        )
        return {"id": str(clar.id), "status": clar.status, "answers": clar.answers}
