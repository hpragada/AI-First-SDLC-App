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
    """Stable hash of the question set — the identity used to dedupe a re-ask.

    **Hashes the question IDS ONLY, deliberately.** It used to hash the prose too (`text`,
    `options`) plus `kind`/`required`/`tier`, which made the signature survive only a
    BYTE-IDENTICAL re-ask — and prose is the one part of a question a language model
    regenerates differently every time.

    Run 75adb0ec proved the cost. The ideation agent emitted two `ask_human` calls in one turn
    (against the single-call rule); the second sat queued behind the first for 37 minutes and
    fired one second after the human answered. All ten ids matched and nine of ten texts were
    byte-identical — but ONE question had dropped a seven-word parenthetical, so the hash
    differed, dedupe missed, and the human was asked the same ten questions a second time. The
    net that exists precisely to make that invisible was anchored to the volatile part.

    Ids are the stable identity everywhere else in this module: `answers` is keyed by id, and
    `_missing_required` looks questions up by id. The signature now agrees with them.

    `tier` STAYS in the hash, and that is not an oversight. A Tier-3 question carries the
    agent's `suggestion` and is auto-accepted when the human leaves it alone; a Tier-1 question
    demands a decision. If the agent re-classifies the same gap from Tier 3 up to Tier 1,
    deduping it would hand back the auto-accepted default as though a human had chosen it —
    silently converting "nobody looked at this" into "the human decided". Tier is a structured
    value, so unlike prose it cannot drift by rewording. A missing tier normalises to 1, the
    same rule the UI applies (`tierOf`), so an omitted field can't fork the signature either.

    The trade: an agent that reuses an id set at the same tiers for genuinely DIFFERENT
    questions within one run gets the earlier answers instead of asking again. Judged far less
    likely than prose drift (which is observed, not hypothetical) — and `create_clarification`
    logs an event when it dedupes across changed text, so it is visible rather than silent.

    A question with no id falls back to its text, so id-less questions don't all collapse onto
    one another.
    """
    identity = sorted({
        (str(q.get("id") or q.get("text", "")), 2 if q.get("tier") == 2 else
         3 if q.get("tier") == 3 else 1)
        for q in (questions or [])
    })
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _reworded_question_ids(stored: list, asked: list) -> list[str]:
    """Ids present in BOTH sets whose wording (text or options) differs — i.e. the drift the
    id-only signature now forgives. Returns [] when the re-ask is byte-identical."""
    by_id = {str(q.get("id")): q for q in (stored or [])}
    out = []
    for q in asked or []:
        prior = by_id.get(str(q.get("id")))
        if prior is None:
            continue
        if (prior.get("text", "") != q.get("text", "")
                or prior.get("options") != q.get("options")):
            out.append(str(q.get("id")))
    return out


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
            # Deduped. If the WORDING changed (same ids, different text/options), say so in the
            # ledger: the human is being spared a repeat, but a silent absorb would hide both
            # the agent's double-ask and any drift in what it means to be asking. Never fatal —
            # the dedupe is the point; this is only the record of it.
            drifted = _reworded_question_ids(existing.questions, questions)
            if drifted:
                tools.log_event(
                    tenant_id, "orchestrator", "clarification.reask_deduped", "clarification",
                    str(existing.id),
                    {"run": str(run_id), "status": existing.status,
                     "reworded": drifted, "phase": phase},
                )
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
            # Screen Words group 5. Two people opening the same question is ordinary, not an
            # error to report in stored words: "clarification already answered" told the second
            # person nothing about what to do, and "clarification already cancelled" read as a
            # fault. The answered history is where the answer now lives, so point there.
            if clar.status == Clarification.Status.CANCELLED:
                raise ClarificationError(
                    "This question was withdrawn — the phase no longer needs it."
                )
            raise ClarificationError(
                "Someone already answered this question. You can see their answer in the "
                "answered history."
            )

        is_member = Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=clar.work_item.project_id
        ).exists()
        if not is_member:
            # Screen Words group 5: the internal user id said nothing to the person reading it.
            raise ClarificationRoleError(
                "You're not a member of this project, so you can't answer its questions. "
                "Ask an admin to add you."
            )

        missing = _missing_required(clar.questions, answers)
        if missing:
            # Screen Words group 5. This printed a Python list of question IDS —
            # "missing required answer(s): ['q1', 'q3']" — which named nothing on screen. The
            # count is the part a person can act on; the form marks which ones.
            raise ClarificationError(
                f"{len(missing)} required question{'' if len(missing) == 1 else 's'} "
                f"{'has' if len(missing) == 1 else 'have'} no answer yet."
            )

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
