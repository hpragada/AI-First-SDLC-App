"""CI results ingestion → the defect loopback (P3-09bX-3/4 / spec §4).

The client's CI runs the automated suite post-merge and posts its JUnit here. Post-merge results
are project-level regression, so there is no build Run to attach to: v1 attaches them to a stable
per-project **Regression container** WorkItem, and the *existing* `import_test_results` does the
rest (open a `defect` per failing test, close it when a later CI run reports it passing, quarantine
flaky). A JUnit case with no `TC-…` is counted + reported as `unmapped` — it never fabricates a
defect against a TC that doesn't exist. Per-story attribution via the traceability graph is a
flagged enhancement (spec §6); the TC-ID + evidence on each defect already identify the test.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

# The stable identity of a project's regression container — get-or-create keys on this so every CI
# post reconciles against the same WorkItem (its defect children open/close across CI runs).
_REGRESSION_STREAM = "__ci_regression__"


def regression_container(tenant_id, project_id):
    """The project's CI-regression container WorkItem (get-or-create; idempotent)."""
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        container, _ = WorkItem.objects.get_or_create(
            tenant_id=tenant_id, project_id=project_id,
            feature_stream=_REGRESSION_STREAM, type=WorkItem.Type.TASK,
            defaults={
                "title": "CI Regression",
                "description": "Container for defects opened by post-merge CI test runs.",
                "state": WorkItem.State.IN_PROGRESS,
                "external_ref": {"kind": "ci_regression"},
            },
        )
    return container


def ingest_ci_results(*, tenant_id, project_id, xml_text: str, execution_ref: str,
                      summary: str = "", commit_sha: str = "", branch: str = "",
                      environment: str = "") -> dict:
    """Parse a posted JUnit document and drive the defect loopback for a project's regression.

    Returns the import outcome + `unmapped` (JUnit cases carrying no TC-ID). `imported` is False
    when the body held no parseable `<testcase>` (malformed or empty) — the caller maps that to a
    4xx; a real report that simply passed still imports (and closes prior defects)."""
    from apps.quality.junit import parse_junit, summarize
    from apps.quality.services import import_test_results

    results = parse_junit(xml_text or "")
    if not results:
        # No parseable cases: never a green run (import would refuse it anyway) — say so.
        return {"imported": False, "status": "skipped",
                "reason": "no parseable test cases in the JUnit body",
                "execution_ref": execution_ref, "unmapped": []}

    container = regression_container(tenant_id, project_id)
    # A human-readable one-liner carrying the CI provenance for the run console / event.
    line = summary or summarize(results)
    provenance = ", ".join(p for p in (
        f"branch {branch}" if branch else "",
        f"commit {commit_sha[:12]}" if commit_sha else "",
        environment,
    ) if p)
    if provenance:
        line = f"{line} — {provenance}"

    out = import_test_results(
        tenant_id=tenant_id, project_id=project_id, work_item_id=str(container.id),
        run_id=None, results=results, summary=line, push_to_sor=False,
        execution_ref=execution_ref,
    )
    unmapped = sorted({r["test_ref"] for r in results if not r["test_ref"].startswith("TC-")})
    return {
        "imported": out["status"] != "skipped",
        "status": out["status"],
        "test_execution_id": out["test_execution_id"],
        "work_item_id": str(container.id),
        "defects_opened": out["defects_opened"],
        "defects_closed": out["defects_closed"],
        "flaky": out["flaky"],
        "quarantined": out["quarantined"],
        "unmapped": unmapped,
        "execution_ref": execution_ref,
    }
