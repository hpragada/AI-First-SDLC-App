"""Materialize test-case WorkItems from a Testing (09) run's `test_case` artifacts (P3-09b, B3).

Test cases are first-class child WorkItems of the story they verify (a sibling of `defect`). The
Testing agent registers one `test_case` artifact per test case (`one TC = one register_artifact`);
this turns each of those into a child `test_case` WorkItem under the story so Test Automation (09b)
can run on it (one TC per run) — via the ordinary phase-trigger flow, no special path.

Idempotent by (story, tc_id): a re-run of 09_testing registers NEW artifacts, so we match on the
stable TC-ID under the same story and repoint the existing WI rather than duplicating it. The WI
keeps a pointer to its specific `test_case` artifact in `external_ref` — `get_context` is
project/repo-scoped (not per-WI), so the pointer is how 09b knows WHICH test case is its run's.
"""
from __future__ import annotations

import re

_TC_ID = re.compile(r"(?<![A-Za-z0-9])TC[-_ ]?(\d+)", re.IGNORECASE)

#: The two lines agent 09's test-case template writes about a case itself (its Step 5 format):
#: `**Type:** Functional` and `**Priority:** High`. **This module is the ONE reader of them.**
#: `apps.a11y.journeys` (which asks "is this an E2E journey?") and this materialiser both come
#: here, because two parsers for one line is two formats and the second is always the one nobody
#: remembers to update. `apps.quality.services` keeps its own severity function — that one adds
#: a fail-safe "unknown means Critical" which is right for a defect and would be a lie on a
#: screen — but shares the pattern below.
_TYPE_LINE = re.compile(r"^\s*\*{0,2}Type:?\*{0,2}\s*:?\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_PRIORITY_LINE = re.compile(
    r"^\s*\*{0,2}Priority:?\*{0,2}\s*:?\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE
)


def _declared(pattern, body: str) -> str:
    """One declared field from a test case body, lowercased, or `""` when it does not say.

    A case that declares nothing is **not** given a default. The template ships placeholders —
    `[Functional / Integration / E2E / ...]`, `[Critical / High / Medium / Low]` — and a body
    still carrying one has declared nothing at all; reading it as a value would put the word
    "Functional" on a case nobody classified. On a compliance screen an invented answer is
    worse than a blank one.
    """
    match = pattern.search(body or "")
    if match is None:
        return ""
    value = match.group(1).strip().strip("*").strip()
    if value.startswith("[") and "/" in value:
        return ""
    return value.lower()


def declared_type(body: str) -> str:
    """The test case's own `**Type:**` value, lowercased, or `""` when it does not say."""
    return _declared(_TYPE_LINE, body)


def declared_priority(body: str) -> str:
    """The test case's own `**Priority:**` value, lowercased, or `""` when it does not say."""
    return _declared(_PRIORITY_LINE, body)


def declared_fields(artifact) -> dict:
    """`{type, priority}` for a `test_case` artifact — structured first, body only if needed.

    The same two-step `apps.quality.services._test_case_severity` uses, and in the same order
    for the same reason: `external_ref` is free and authoritative where the producer filled it
    in, and the body costs an object-store read. Absent stays absent — see `_declared`.
    """
    ref = artifact.external_ref or {}
    fields = {
        "type": str(ref.get("type") or "").strip().lower(),
        "priority": str(ref.get("priority") or "").strip().lower(),
    }
    if all(fields.values()):
        return fields

    from integrations.preview import internal_draft_body

    body = internal_draft_body(artifact) or ""     # best-effort read-through; "" if unreadable
    fields["type"] = fields["type"] or declared_type(body)
    fields["priority"] = fields["priority"] or declared_priority(body)
    return fields


def _tc_id_of(artifact) -> str:
    """The stable TC-ID for a `test_case` artifact — from `external_ref` (the keys the Testing
    agent / export path stamp) or its title (`TC-014 — …`). Digits are preserved as written
    (`TC009` → `TC-009`), never re-padded. Empty string if none is discoverable."""
    ref = artifact.external_ref or {}
    for key in ("tc_id", "id"):
        val = ref.get(key)
        if val:
            return str(val)
    export = ref.get("export") or {}
    if export.get("id"):
        return str(export["id"])
    m = _TC_ID.search(artifact.title or "")
    return f"TC-{m.group(1)}" if m else ""


def materialize_test_cases(*, tenant_id, project_id, run_id, story_id) -> dict:
    """Create/refresh child `test_case` WorkItems from the `test_case` artifacts a Testing run
    registered. Returns `{created, updated, skipped}`. No-op (0/0/0) when the story is gone or the
    run registered no test cases."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    created = updated = skipped = 0
    with tenant_context(tenant_id):
        story = WorkItem.objects.filter(id=story_id, tenant_id=tenant_id).first()
        if story is None:
            return {"created": 0, "updated": 0, "skipped": 0}

        artifacts = (
            Artifact.objects
            .filter(tenant_id=tenant_id, project_id=project_id, run_id=run_id, type="test_case")
            .order_by("created_at")
        )
        for art in artifacts:
            tc_id = _tc_id_of(art)
            if not tc_id:
                # A test case with no discoverable TC-ID can't be idempotently tracked; skip it
                # rather than spawn an unmatchable duplicate on the next run.
                skipped += 1
                continue

            # `type` and `priority` are what the case says about itself, carried onto the work
            # item so the platform can SHOW them (G2). Until now only the pointer was copied,
            # and the Test cases screen read `priority` off the work item where nothing ever
            # wrote it — while defect severity read the same fact off the artifact, where it
            # lives. Absent keys are omitted rather than written blank, so an existing item is
            # never overwritten with nothing by a re-run that could not read the body.
            ref = {"test_case_artifact_id": str(art.id), "tc_id": tc_id}
            ref.update({k: v for k, v in declared_fields(art).items() if v})
            existing = (
                WorkItem.objects
                .filter(tenant_id=tenant_id, project_id=project_id, parent_id=story.id,
                        type=WorkItem.Type.TEST_CASE, external_ref__tc_id=tc_id)
                .first()
            )
            if existing is not None:
                existing.title = art.title or existing.title
                existing.external_ref = {**(existing.external_ref or {}), **ref}
                existing.save(update_fields=["title", "external_ref", "updated_at"])
                updated += 1
            else:
                WorkItem.objects.create(
                    tenant_id=tenant_id, project_id=project_id, parent=story,
                    type=WorkItem.Type.TEST_CASE, title=art.title or tc_id,
                    feature_stream=story.feature_stream, repo_id=story.repo_id,
                    external_ref=ref,
                )
                created += 1
    return {"created": created, "updated": updated, "skipped": skipped}


# The catalog key of the Test Automation phase — the run that automates a test case (P3-09b).
TEST_AUTOMATION_KEY = "09b_test_automation"


def automation_status_for(work_item) -> str:
    """A test_case WI's automation status, from its latest Test Automation (09b) run:
    `ready` (a script was generated — run executed/gated/merged), `generating` (a run is in
    flight), or `not_automated` (no run yet, or the last one failed and can be retried). Drives
    the coverage list (B6)."""
    from apps.runs.models import Run

    run = (
        work_item.runs
        .filter(agent_spec__key=TEST_AUTOMATION_KEY)
        .order_by("-created_at")
        .first()
    )
    if run is None:
        return "not_automated"
    if run.status in (Run.Status.PENDING, Run.Status.RUNNING):
        return "generating"
    if run.status in (Run.Status.AWAITING_GATE, Run.Status.APPROVED, Run.Status.COMPLETED):
        return "ready"
    return "not_automated"      # failed / stalled → retryable
