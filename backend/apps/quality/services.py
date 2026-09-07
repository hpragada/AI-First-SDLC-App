"""Test/Quality control-plane services (Phase 3 §5/§6).

The product intelligence of the test loop, reusing — never reinventing — the P2 machinery:

- `import_test_results` records a `TestExecution` + a `test_report` artifact (pointer/hash,
  #1/#3), optionally pushes to the Xray SoR (idempotently), detects **flaky** tests and
  quarantines them (D9 — excluded from the blocking gate), and drives the **defect loopback**
  (D5 — a failing test opens a child `defect` WorkItem, a now-passing one closes it), exactly
  like the 07↔08 remediation reconciliation.
- `select_impacted_tests` is **test-impact selection v1** (D9): a traceability-graph walk
  from a changed `code` artifact to the `test_case` artifacts that cover it.

Defects are first-class child WorkItems (#4); the test→code lineage is a `TraceEdge`.
"""
from __future__ import annotations

import hashlib
import json
import re

from django.db.models import Q
from mcp_platform_state import tools

from apps.registry.models import Artifact, TraceEdge
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .junit import summarize
from .models import TestExecution, TestQuarantine

_BLOCKING_FAIL = "FAIL"

#: How much of a failure's text stays on the stored row — and therefore goes to the tracker,
#: which imposes its own hard field limit (Jira caps a text field at 32,767 characters, and a
#: push that exceeds it fails, breaking the loop that opens and closes defects). The complete
#: text is never lost: it is the `test_report` artifact's body in the object store, and a row
#: that is shortened says where the rest is (QA-11a).
_ROW_EVIDENCE_CHARS = 2000


def _normalize(results: list) -> list[dict]:
    """Accept dicts or TestResult-likes → [{test_ref, status(UPPER), evidence}]."""
    out = []
    for r in results:
        if isinstance(r, dict):
            test_ref, status, evidence = r.get("test_ref"), r.get("status"), r.get("evidence", "")
        else:
            test_ref, status, evidence = r.test_ref, r.status, getattr(r, "evidence", "")
        if test_ref and status:
            out.append({"test_ref": test_ref, "status": status.upper(), "evidence": evidence})
    return out


def _rows_for_state(rows: list[dict], report_id: str | None) -> list[dict]:
    """The rows as they are stored and pushed to the tracker: full text where it fits, and
    where it does not, as much as fits followed by **where the rest is**.

    Deliberately not a "truncated" warning. Telling a reader their evidence was cut is a
    confession; naming the report that holds all of it is a destination — and nobody has to
    re-run anything to see it, which would be a different execution and therefore different
    evidence anyway.
    """
    out = []
    for row in rows:
        evidence = row.get("evidence") or ""
        if len(evidence) > _ROW_EVIDENCE_CHARS:
            pointer = (
                f"\n\nFull evidence: this run's test report (artifact {report_id})."
                if report_id else "\n\nFull evidence: this run's test report."
            )
            keep = max(0, _ROW_EVIDENCE_CHARS - len(pointer))
            evidence = evidence[:keep].rstrip() + pointer
        out.append({**row, "evidence": evidence})
    return out


def _detect_flaky(results: list[dict]) -> set[str]:
    """Flaky = a test that flips PASS/FAIL across reruns *within one execution* (D9): the same
    test_ref reports both PASS and FAIL in this import. (A single FAIL→PASS across separate
    imports is a legitimate fix — the defect loop closes it — not flakiness.)"""
    by_ref: dict[str, set[str]] = {}
    for r in results:
        by_ref.setdefault(r["test_ref"], set()).add(r["status"])
    return {ref for ref, statuses in by_ref.items() if {"PASS", "FAIL"} <= statuses}


def _passing(results: list[dict], quarantined: set[str]) -> set[str]:
    """Tests this execution reports as **passing**: reported, only ever PASS here, and not
    quarantined. Deliberately narrower than "not failing" — a test that simply did not run
    this cycle is neither passing nor failing, and a quarantined test's result is ambiguous
    by definition. `_reconcile_defects` closes on this set, never on absence."""
    by_ref: dict[str, set[str]] = {}
    for r in results:
        by_ref.setdefault(r["test_ref"], set()).add(r["status"])
    return {ref for ref, statuses in by_ref.items()
            if statuses == {"PASS"} and ref not in quarantined}


def _quarantine(tenant_id, project_id, test_refs: set[str], reason: str) -> None:
    with tenant_context(tenant_id):
        for ref in test_refs:
            _, created = TestQuarantine.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, test_ref=ref,
                defaults={"active": True, "reason": reason},
            )
            if created:
                # Event.target_id is a UUID — the test ref lives in the payload (#3 convention).
                tools.log_event(tenant_id, "quality", "test.quarantined",
                                "test_quarantine", None, {"test_ref": ref, "reason": reason})


def _latest_code_artifact_id(tenant_id, work_item_id) -> str | None:
    with tenant_context(tenant_id):
        code = (
            Artifact.objects.filter(
                tenant_id=tenant_id, type="code", run__work_item_id=work_item_id)
            .order_by("-created_at").first()
        )
        return str(code.id) if code else None


def import_test_results(
    *, tenant_id, project_id, work_item_id, run_id=None, results: list,
    summary: str = "", push_to_sor: bool = False, get_capability=None, execution_ref: str = "",
) -> dict:
    """Record an execution, detect/quarantine flaky tests, register the test_report artifact,
    optionally push to the SoR (idempotent), and reconcile the defect loopback."""
    rows = _normalize(results)
    if not rows:
        # An empty report is NOT a green run. Registering one would record a passing execution
        # for a build that ran no tests — and, before the `_passing` rule below, would have
        # closed every open defect. Import nothing; say so.
        return {"test_execution_id": None, "test_report_id": None, "status": "skipped",
                "flaky": [], "quarantined": [], "defects_opened": [], "defects_closed": [],
                "external_ref": None, "note": "no test results reported"}

    # Flaky detection → quarantine (excluded from the blocking gate).
    flaky = _detect_flaky(rows)
    if flaky:
        _quarantine(tenant_id, project_id, flaky, "status flipped across reruns")

    with tenant_context(tenant_id):
        quarantined = set(
            TestQuarantine.objects.filter(
                tenant_id=tenant_id, project_id=project_id, active=True
            ).values_list("test_ref", flat=True)
        )

    # A blocking failure = a FAIL on a test that is NOT quarantined.
    failing = {
        r["test_ref"] for r in rows
        if r["status"] == _BLOCKING_FAIL and r["test_ref"] not in quarantined
    }
    passing = _passing(rows, quarantined)
    overall = TestExecution.Status.FAILED if failing else TestExecution.Status.PASSED

    # File the full results FIRST — body to the object store, pointer on the artifact (#1/#3).
    # Order is the whole point: everything below stores or forwards a *bounded* copy, so the
    # complete text has to be filed before anything shortens it. Doing this last (as it was
    # until QA-11a) is why evidence could only ever be as long as a database column allowed.
    report_id = _register_test_report(tenant_id, project_id, run_id, rows)
    code_id = _latest_code_artifact_id(tenant_id, work_item_id)
    if code_id:
        tools.add_trace_edge(tenant_id, report_id, code_id, "tests")
    rows = _rows_for_state(rows, report_id)

    # Optional SoR push (idempotent via the prior execution ref).
    external_ref = None
    if push_to_sor:
        external_ref = _push_to_sor(tenant_id, project_id, work_item_id, rows, summary,
                                    get_capability)

    # Record / update the TestExecution. Idempotent by (run, work_item) for the build path; by
    # (work_item, execution_ref) for a run-less CI import (P3-09bX-5) — a re-post of the same CI
    # run updates the same row rather than stacking duplicate executions. Only a truly anonymous
    # import (no run, no execution_ref) falls back to an unconditional create.
    with tenant_context(tenant_id):
        defaults = {"status": overall, "results": rows, "flaky": bool(flaky),
                    "project_id": project_id, "external_ref": external_ref,
                    "execution_ref": execution_ref}
        if run_id:
            execution, _ = TestExecution.objects.update_or_create(
                tenant_id=tenant_id, run_id=run_id, work_item_id=work_item_id,
                defaults=defaults,
            )
        elif execution_ref:
            execution, _ = TestExecution.objects.update_or_create(
                tenant_id=tenant_id, work_item_id=work_item_id, execution_ref=execution_ref,
                defaults=defaults,
            )
        else:
            execution = TestExecution.objects.create(
                tenant_id=tenant_id, work_item_id=work_item_id, **defaults
            )

    # Defect loopback: open defects for failing tests, close those whose test now passes.
    opened, closed = _reconcile_defects(tenant_id, project_id, work_item_id, failing, passing,
                                        report_id)

    with tenant_context(tenant_id):
        tools.log_event(tenant_id, "quality", "tests.imported", "test_execution",
                        str(execution.id),
                        {"status": overall, "failing": len(failing), "flaky": sorted(flaky)})
    return {
        "test_execution_id": str(execution.id),
        "test_report_id": report_id,
        "status": overall,
        "flaky": sorted(flaky),
        "quarantined": sorted(quarantined),
        "defects_opened": opened,
        "defects_closed": closed,
        "external_ref": external_ref,
    }


def _report_body(rows: list[dict]) -> str:
    """The run's results as a readable document — every failure's evidence, in full.

    This is the body the `test_report` artifact never had (QA-11a). Until it existed, the only
    place a failure's text could live was a database column, a column has to be bounded, and so
    the evidence a developer needs was cut to a couple of thousand characters at the moment it
    was parsed. Bodies belong in the object store (#1/#3); this builds one.
    """
    failing = [r for r in rows if r["status"] == _BLOCKING_FAIL]
    other = [r for r in rows if r["status"] != _BLOCKING_FAIL]
    lines = [
        "# Test report",
        "",
        f"{summarize(rows)} — {len(rows)} result(s).",
        "",
    ]
    if failing:
        lines.append("## Failures")
        lines.append("")
        for row in failing:
            lines.append(f"### {row['test_ref']}")
            lines.append("")
            evidence = row.get("evidence") or ""
            if evidence:
                # Fenced so a message containing markdown (or an HTML snippet from a scanner)
                # renders as what it is rather than being interpreted.
                lines.extend(["```", evidence, "```", ""])
            else:
                lines.extend(["_No evidence was reported for this failure._", ""])
    if other:
        lines.append("## Other results")
        lines.append("")
        lines.extend(f"- `{row['test_ref']}` — {row['status']}" for row in other)
        lines.append("")
    return "\n".join(lines)


def _register_test_report(tenant_id, project_id, run_id, rows: list[dict]) -> str:
    """Register (or update) the run's `test_report` artifact, with its full body staged.

    Best-effort on the body: if the object store is unreachable the artifact is still
    registered from the hash alone, exactly as before. A test import must never fail because
    the evidence could not be filed — the defect loopback is what a red suite depends on.
    """
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    body = _report_body(rows)
    staged = None
    try:
        # The key is deterministic per (tenant, project, run, phase, filename), so a re-import
        # of the same run overwrites its own snapshot instead of accumulating copies.
        staged = tools.stage_artifact_body(
            tenant_id, project_id, run_id, "testing", "test-report.md", body,
            content_type="text/markdown",
        )
    except Exception:  # noqa: BLE001 — see the docstring: never fail an import over the body
        staged = None

    if run_id:
        with tenant_context(tenant_id):
            existing = Artifact.objects.filter(
                tenant_id=tenant_id, run_id=run_id, type="test_report").first()
        if existing:
            # `update_artifact` carries no `s3_key`, and it does not need one: the staged key is
            # deterministic, so re-staging above replaced the body behind the pointer this row
            # already holds. Only the hash has to move.
            tools.update_artifact(
                tenant_id, str(existing.id),
                content_hash=(staged or {}).get("content_hash") or digest,
            )
            return str(existing.id)
    created = tools.register_artifact(
        tenant_id, project_id, run_id, "testing", "test_report", "internal",
        content_hash=(staged or {}).get("content_hash") or digest,
        s3_key=(staged or {}).get("s3_key"),
    )
    return created["id"]


def _push_to_sor(tenant_id, project_id, work_item_id, rows, summary, get_capability):
    from integrations.types import TestExecutionImport, TestResult

    if get_capability is None:
        from integrations.registry import get_capability as _gc
        get_capability = _gc
    with tenant_context(tenant_id):
        wi = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        work_item_ref = (wi.external_ref or {}).get("id") or str(wi.id)
        prior = (
            TestExecution.objects.filter(tenant_id=tenant_id, work_item_id=work_item_id)
            .exclude(external_ref=None).order_by("-created_at").first()
        )
    execution_ref = (prior.external_ref or {}).get("id") if prior else None
    tm = get_capability(tenant_id, "testmgmt")
    ref = tm.import_results(execution=TestExecutionImport(
        project=tm._project if hasattr(tm, "_project") else "",
        work_item_ref=work_item_ref, summary=summary, execution_ref=execution_ref,
        results=[TestResult(test_ref=r["test_ref"], status=r["status"],
                            evidence=r["evidence"]) for r in rows],
    ))
    return {"sor": ref.sor, "id": ref.id, "url": ref.url}


_SEVERITIES = ("critical", "high", "medium", "low")
# A failing test we cannot trace back to a registered case keeps the old blanket severity:
# fail-safe (never silently minor), and the honest answer when the priority is unknown.
_UNKNOWN_SEVERITY = "critical"

# `**Priority:** High` / `Priority: [Critical / High / …]` on its own line in a TC body.
_PRIORITY_IN_BODY = re.compile(
    rf"^\W*priority\W+({'|'.join(_SEVERITIES)})\b", re.IGNORECASE | re.MULTILINE
)


def _test_case_artifact(tenant_id, project_id, test_ref):
    r"""The `test_case` artifact a result's `test_ref` names, or None.

    Matched on every ref the testing agent / publish path actually records: the TC-ID in
    `external_ref` (`tc_id`/`id` — the same keys `export_tests._summary_for` reads), the SoR
    key stamped by the manual export (`external_ref.export.id`, which is what `import_results`
    reports back as `test_ref`), or a `TC-014 — …` title. The title match is word-bounded
    (Postgres ARE `\y`) so `TC-1` never matches `TC-14`.
    """
    with tenant_context(tenant_id):
        return (
            Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, type="test_case",
            )
            .filter(
                Q(external_ref__tc_id=test_ref)
                | Q(external_ref__id=test_ref)
                | Q(external_ref__export__id=test_ref)
                | Q(title__iregex=rf"^{re.escape(test_ref)}\y")
            )
            .select_related("run")
            .order_by("-created_at")
            .first()
        )


def _test_case_severity(tenant_id, project_id, test_ref) -> str:
    """Defect severity = the failing test case's Priority.

    09 Step 10: "severity = same as the original test case priority (Critical test fails =
    Critical defect)". Read the case's structured `external_ref.priority` first, then its
    body. Unknown → Critical (fail-safe). Without this every failing test — however trivial —
    opened a Critical defect, and a defect queue that cries critical at everything is one
    nobody triages.
    """
    artifact = _test_case_artifact(tenant_id, project_id, test_ref)
    if artifact is None:
        return _UNKNOWN_SEVERITY
    priority = str((artifact.external_ref or {}).get("priority") or "").strip().lower()
    if priority in _SEVERITIES:
        return priority
    from integrations.preview import internal_draft_body

    with tenant_context(tenant_id):
        body = internal_draft_body(artifact)      # best-effort read-through; "" if unreadable
    match = _PRIORITY_IN_BODY.search(body or "")
    return match.group(1).lower() if match else _UNKNOWN_SEVERITY


def _reconcile_defects(tenant_id, project_id, work_item_id, failing: set[str],
                       passing: set[str], report_id: str) -> tuple[list, list]:
    """Open a `defect` child WorkItem per failing test, close those whose test now passes —
    the same open/close reconciliation as the 07↔08 remediation loop.

    Closing keys off `passing` (the test was RUN and reported PASS), never off "absent from
    `failing`". The difference is not academic: a partial run — which is exactly what
    test-impact selection (D9) produces — reports nothing about the tests it skipped, and
    treating that silence as success would close their defects and turn the gate green on a
    suite nobody ran.
    """
    opened, closed = [], []
    with tenant_context(tenant_id):
        story = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        children = WorkItem.objects.filter(
            tenant_id=tenant_id, parent_id=work_item_id, type=WorkItem.Type.DEFECT)
        existing = {(c.external_ref or {}).get("test_ref"): c for c in children
                    if (c.external_ref or {}).get("test_ref")}
        # Close only defects whose test this execution actually reported as passing.
        for test_ref, child in existing.items():
            # `not in TERMINAL_STATES`, not `!= DONE` (S.No 140): a defect somebody
            # cancelled is not an open defect waiting to be closed by a passing test, and
            # flipping it to `done` would rewrite "we decided not to fix this" as "fixed".
            if test_ref in passing and child.state not in WorkItem.TERMINAL_STATES:
                child.state = WorkItem.State.DONE
                child.save(update_fields=["state", "updated_at"])
                tools.log_event(tenant_id, "quality", "defect.resolved", "work_item",
                                str(child.id), {"test_ref": test_ref})
                closed.append(str(child.id))
        # Open (or reopen) a defect for each failing test.
        for test_ref in sorted(failing):
            child = existing.get(test_ref)
            if child is None:
                child = WorkItem.objects.create(
                    tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT,
                    parent=story, title=f"Failing test {test_ref}",
                    state=WorkItem.State.IN_PROGRESS,
                    external_ref={
                        "defect": f"DEF-{test_ref}", "test_ref": test_ref,
                        "severity": _test_case_severity(tenant_id, project_id, test_ref),
                        "test_report": report_id,
                    },
                )
                tools.log_event(tenant_id, "quality", "defect.opened", "work_item",
                                str(child.id), {"test_ref": test_ref})
                opened.append(str(child.id))
            elif child.state == WorkItem.State.DONE:
                child.state = WorkItem.State.IN_PROGRESS
                child.save(update_fields=["state", "updated_at"])
                opened.append(str(child.id))
    return opened, closed


_SECURITY_BLOCKING = {"critical", "high"}


def record_security_findings(
    *, tenant_id, project_id, work_item_id, findings: list, review_artifact_id=None,
) -> dict:
    """Security defect loopback (D8): open a `defect` child WorkItem for each open Critical/High
    `security_finding` and close those now resolved — the same open/close reconciliation as the
    test loop, keyed by finding id and scoped to security defects so it never touches test
    defects. Criticals/Highs must clear before the security gate is grantable.

    `findings`: [{id, severity, title, ...}]. Standalone — does not reopen the P2 build saga."""
    blocking = {
        f["id"]: f for f in findings
        if str(f.get("severity", "")).lower() in _SECURITY_BLOCKING and f.get("id")
    }
    opened, closed = [], []
    with tenant_context(tenant_id):
        story = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        children = WorkItem.objects.filter(
            tenant_id=tenant_id, parent_id=work_item_id, type=WorkItem.Type.DEFECT)
        # Only security defects (external_ref.finding); test defects (test_ref) are untouched.
        existing = {(c.external_ref or {}).get("finding"): c for c in children
                    if (c.external_ref or {}).get("finding")}
        for fid, child in existing.items():
            # See the note in the test loop above — a cancelled security defect stays
            # cancelled rather than being reported as resolved.
            if fid not in blocking and child.state not in WorkItem.TERMINAL_STATES:
                child.state = WorkItem.State.DONE
                child.save(update_fields=["state", "updated_at"])
                tools.log_event(tenant_id, "security", "security.defect.resolved", "work_item",
                                str(child.id), {"finding": fid})
                closed.append(str(child.id))
        for fid in sorted(blocking):
            finding = blocking[fid]
            child = existing.get(fid)
            if child is None:
                child = WorkItem.objects.create(
                    tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT,
                    parent=story, title=f"Security: {finding.get('title') or fid}",
                    state=WorkItem.State.IN_PROGRESS,
                    external_ref={"defect": f"DEF-{fid}", "finding": fid, "kind": "security",
                                  "severity": str(finding.get("severity", "")).lower(),
                                  "security_review": review_artifact_id},
                )
                tools.log_event(tenant_id, "security", "security.defect.opened", "work_item",
                                str(child.id), {"finding": fid,
                                                "severity": finding.get("severity")})
                opened.append(str(child.id))
            elif child.state == WorkItem.State.DONE:
                child.state = WorkItem.State.IN_PROGRESS
                child.save(update_fields=["state", "updated_at"])
                opened.append(str(child.id))
    return {"opened": opened, "closed": closed, "blocking": sorted(blocking)}


def select_impacted_tests(tenant_id, *, code_artifact_id: str) -> list[str]:
    """Test-impact selection v1 (D9): the `test_case` artifacts covering a changed `code`
    artifact, found by walking the traceability graph — directly linked tests plus tests that
    share an upstream artifact (e.g. the same requirement) with the code. No coverage-map
    instrumentation; a graph walk, honest about its bound."""
    with tenant_context(tenant_id):
        out = TraceEdge.objects.filter(
            tenant_id=tenant_id, from_artifact_id=code_artifact_id
        ).values_list("to_artifact_id", flat=True)
        inc = TraceEdge.objects.filter(
            tenant_id=tenant_id, to_artifact_id=code_artifact_id
        ).values_list("from_artifact_id", flat=True)
        targets = {str(x) for x in out} | {str(x) for x in inc} | {str(code_artifact_id)}

        edges = TraceEdge.objects.filter(tenant_id=tenant_id).filter(
            Q(from_artifact_id__in=targets) | Q(to_artifact_id__in=targets)
        )
        endpoints: set[str] = set()
        for e in edges:
            endpoints.add(str(e.from_artifact_id))
            endpoints.add(str(e.to_artifact_id))
        endpoints.discard(str(code_artifact_id))

        test_cases = Artifact.objects.filter(
            tenant_id=tenant_id, id__in=endpoints, type="test_case"
        ).values_list("id", flat=True)
        return sorted(str(i) for i in test_cases)
