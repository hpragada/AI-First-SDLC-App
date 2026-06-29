"""Clarification answer service (req #2).

A human answers a pending Clarification in the web app. Unlike a gate (which needs a
specific role), answering a clarification only requires the user be a **member of the
project** — they are supplying missing context, not authorizing a system-of-record write.
We validate that every *required* question has an answer, record it, and log the event. No
Temporal signal is sent: the agent is blocked on the `ask_human` tool, whose companion-side
handler is polling for this answer and resumes the moment the status flips to ANSWERED.
"""
from __future__ import annotations

from datetime import UTC, datetime

from mcp_platform_state import tools

from apps.clarifications.models import Clarification
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership


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


def answer_clarification(
    *, tenant_id: str, clarification_id: str, user_id: str, answers: dict
) -> dict:
    """Record a human's answers to a pending clarification (after a project-membership
    check + a required-answer check). Idempotent guard: a non-pending clarification raises."""
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
