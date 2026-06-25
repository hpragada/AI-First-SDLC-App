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

from django.db.models import Q
from mcp_platform_state import tools

from apps.registry.models import Artifact, TraceEdge
from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

from .models import TestExecution, TestQuarantine

_BLOCKING_FAIL = "FAIL"


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


def _detect_flaky(results: list[dict]) -> set[str]:
    """Flaky = a test that flips PASS/FAIL across reruns *within one execution* (D9): the same
    test_ref reports both PASS and FAIL in this import. (A single FAIL→PASS across separate
    imports is a legitimate fix — the defect loop closes it — not flakiness.)"""
    by_ref: dict[str, set[str]] = {}
    for r in results:
        by_ref.setdefault(r["test_ref"], set()).add(r["status"])
    return {ref for ref, statuses in by_ref.items() if {"PASS", "FAIL"} <= statuses}


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
    summary: str = "", push_to_sor: bool = False, get_capability=None,
) -> dict:
    """Record an execution, detect/quarantine flaky tests, register the test_report artifact,
    optionally push to the SoR (idempotent), and reconcile the defect loopback."""
    rows = _normalize(results)

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
    overall = TestExecution.Status.FAILED if failing else TestExecution.Status.PASSED

    # Optional SoR push (idempotent via the prior execution ref).
    external_ref = None
    if push_to_sor:
        external_ref = _push_to_sor(tenant_id, project_id, work_item_id, rows, summary,
                                    get_capability)

    # Record / update the TestExecution (idempotent by run+work_item when a run is given).
    with tenant_context(tenant_id):
        defaults = {"status": overall, "results": rows, "flaky": bool(flaky),
                    "project_id": project_id, "external_ref": external_ref}
        if run_id:
            execution, _ = TestExecution.objects.update_or_create(
                tenant_id=tenant_id, run_id=run_id, work_item_id=work_item_id,
                defaults=defaults,
            )
        else:
            execution = TestExecution.objects.create(
                tenant_id=tenant_id, work_item_id=work_item_id, **defaults
            )

    # Register the test_report artifact (pointer/hash) + lineage to the code under test.
    report_id = _register_test_report(tenant_id, project_id, run_id, rows)
    code_id = _latest_code_artifact_id(tenant_id, work_item_id)
    if code_id:
        tools.add_trace_edge(tenant_id, report_id, code_id, "tests")

    # Defect loopback: open defects for failing tests, close those now resolved.
    opened, closed = _reconcile_defects(tenant_id, project_id, work_item_id, failing, report_id)

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


def _register_test_report(tenant_id, project_id, run_id, rows: list[dict]) -> str:
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    if run_id:
        with tenant_context(tenant_id):
            existing = Artifact.objects.filter(
                tenant_id=tenant_id, run_id=run_id, type="test_report").first()
        if existing:
            tools.update_artifact(tenant_id, str(existing.id), content_hash=digest)
            return str(existing.id)
    created = tools.register_artifact(
        tenant_id, project_id, run_id, "testing", "test_report", "internal",
        content_hash=digest,
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


def _reconcile_defects(tenant_id, project_id, work_item_id, failing: set[str],
                       report_id: str) -> tuple[list, list]:
    """Open a `defect` child WorkItem per failing test, close those whose test now passes —
    the same open/close reconciliation as the 07↔08 remediation loop."""
    opened, closed = [], []
    with tenant_context(tenant_id):
        story = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        children = WorkItem.objects.filter(
            tenant_id=tenant_id, parent_id=work_item_id, type=WorkItem.Type.DEFECT)
        existing = {(c.external_ref or {}).get("test_ref"): c for c in children
                    if (c.external_ref or {}).get("test_ref")}
        # Close defects whose test is no longer failing.
        for test_ref, child in existing.items():
            if test_ref not in failing and child.state != WorkItem.State.DONE:
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
                    external_ref={"defect": f"DEF-{test_ref}", "test_ref": test_ref,
                                  "severity": "critical", "test_report": report_id},
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
            if fid not in blocking and child.state != WorkItem.State.DONE:
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
