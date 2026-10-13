"""XrayTestMgmt — the TestMgmt capability over Xray Cloud (REST import + GraphQL).

Returns vendor-free ExternalRef / TestCase / IssueHit so callers stay Xray-unaware (#9).
Pointers only — test bodies/results live in Xray, never copied into platform state (#1/#3).
`create_test` is idempotent by summary (register-don't-recreate); `import_results` is
idempotent via `execution.execution_ref` (updates the same execution, never duplicates).
"""
from __future__ import annotations

from integrations.types import (
    CapabilityError,
    ExternalRef,
    IssueHit,
    TestCase,
    TestExecutionImport,
    TestStep,
)

from .config import XrayConfig
from .rest import XrayRest

_SOR = "xray"
# Vendor-free PASS/FAIL/SKIP -> Xray status names.
_STATUS = {"PASS": "PASSED", "FAIL": "FAILED", "SKIP": "SKIPPED"}


def _jira_field(jira: list, name: str) -> str:
    """Pull a named field out of Xray GraphQL's `jira(fields:[...])` list/dict shape."""
    if isinstance(jira, dict):
        return jira.get(name, "")
    for item in jira or []:
        if isinstance(item, dict) and name in item:
            return item[name]
    return ""


class XrayTestMgmt:
    def __init__(self, config: XrayConfig, project: str = "", transport=None):
        self._cfg = config
        self._project = project
        self._rest = XrayRest(config, transport)

    def _project_key(self, project: str | None) -> str:
        project = project or self._project
        if not project:
            raise CapabilityError(
                "No test-management project was named, and the connection has no default. "
                "Add one in the connection settings."
            )
        return project

    def _graphql(self, query: str, variables: dict) -> dict:
        data = self._rest.request(
            "POST", "/api/v2/graphql", body={"query": query, "variables": variables}
        )
        return ((data or {}).get("data") or {})

    def _issue_url(self, key: str) -> str:
        return f"{self._cfg.api_url}/browse/{key}" if key else ""

    # ── TestMgmt capability ─────────────────────────────────────────
    def create_test(self, *, project: str | None = None, summary: str,
                    steps: list[TestStep], fields: dict | None = None) -> ExternalRef:
        project = self._project_key(project)
        existing = self._find_by_summary(project, summary)
        if existing:                                  # register-don't-recreate (idempotent)
            return existing
        query = (
            "mutation($jira: JSON!, $steps: [CreateStepInput]) { "
            "createTest(testType: {name: \"Manual\"}, steps: $steps, jira: {fields: $jira}) "
            "{ test { issueId jira(fields: [\"key\"]) } warnings } }"
        )
        variables = {
            "jira": {"summary": summary, "project": {"key": project}, **(fields or {})},
            "steps": [{"action": s.action, "data": s.data, "result": s.expected} for s in steps],
        }
        test = (self._graphql(query, variables).get("createTest") or {}).get("test") or {}
        key = _jira_field(test.get("jira"), "key") or test.get("issueId", "")
        return ExternalRef(sor=_SOR, id=key, url=self._issue_url(key))

    def get_test(self, *, test_ref: str) -> TestCase:
        query = (
            "query($jql: String!) { getTests(jql: $jql, limit: 1) { results { "
            "issueId steps { action data result } jira(fields: [\"key\",\"summary\",\"status\"]) "
            "} } }"
        )
        results = (self._graphql(query, {"jql": f"key = {test_ref}"}).get("getTests") or {}).get(
            "results"
        ) or []
        if not results:
            raise CapabilityError(
                f"Test {test_ref} wasn't found in test management. It may have been "
                "deleted there.",
                status=404,
            )
        t = results[0]
        steps = [
            TestStep(action=s.get("action", ""), data=s.get("data", ""),
                     expected=s.get("result", ""))
            for s in (t.get("steps") or [])
        ]
        key = _jira_field(t.get("jira"), "key") or test_ref
        return TestCase(
            key=key, summary=_jira_field(t.get("jira"), "summary"), steps=steps,
            status=_jira_field(t.get("jira"), "status"), url=self._issue_url(key),
        )

    def import_results(self, *, execution: TestExecutionImport) -> ExternalRef:
        body: dict = {
            "info": {"summary": execution.summary or f"Run for {execution.work_item_ref}",
                     "project": execution.project},
            "tests": [
                {"testKey": r.test_ref, "status": _STATUS.get(r.status.upper(), r.status.upper()),
                 "comment": r.evidence}
                for r in execution.results
            ],
        }
        if execution.execution_ref:                   # idempotent: update the same execution
            body["testExecutionKey"] = execution.execution_ref
        data = self._rest.request("POST", "/api/v2/import/execution", body=body) or {}
        key = data.get("key") or execution.execution_ref or ""
        return ExternalRef(sor=_SOR, id=key, url=data.get("self", self._issue_url(key)))

    def link_defect(self, *, test_ref: str, defect_ref: str) -> None:
        # Associate a defect issue with the test via Xray GraphQL (best-effort linkage; the
        # platform's authoritative linkage is the defect WorkItem + TraceEdge).
        query = (
            "mutation($issueId: String!, $defects: [String]!) { "
            "addDefectsToTest(issueId: $issueId, defects: $defects) { addedDefects warnings } }"
        )
        self._graphql(query, {"issueId": test_ref, "defects": [defect_ref]})

    def search(self, *, jql: str) -> list[IssueHit]:
        query = (
            "query($jql: String!) { getTests(jql: $jql, limit: 100) { results { "
            "jira(fields: [\"key\",\"summary\"]) } } }"
        )
        results = (self._graphql(query, {"jql": jql}).get("getTests") or {}).get("results") or []
        hits = []
        for t in results:
            key = _jira_field(t.get("jira"), "key")
            if key:
                hits.append(IssueHit(key=key, summary=_jira_field(t.get("jira"), "summary")))
        return hits

    # ── internals ───────────────────────────────────────────────────
    def _find_by_summary(self, project: str, summary: str) -> ExternalRef | None:
        safe = summary.replace('"', '\\"')
        for hit in self.search(jql=f'project = "{project}" AND summary ~ "{safe}"'):
            if hit.summary == summary:                # exact match only — never a fuzzy dup
                return ExternalRef(sor=_SOR, id=hit.key, url=self._issue_url(hit.key))
        return None
