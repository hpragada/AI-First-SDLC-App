"""AtlassianTaskTracker — the TaskTracker capability over Jira Cloud.

Jira REST v3. Bodies (description/comment) are Atlassian Document Format (ADF), which
v3 requires. Transitions are by workflow transition id, so `transition_issue` looks up
the transition whose target status matches the requested name. Returns vendor-free
ExternalRef/Issue/IssueHit so callers stay Jira-unaware (#9). The connector is bound to
one project (per-tenant); `fields` can override/extend any Jira field.
"""
from __future__ import annotations

from integrations.types import CapabilityError, ExternalRef, Issue, IssueHit

from .config import AtlassianConfig
from .rest import AtlassianRest, Transport

_SOR = "jira"


def _adf(text: str) -> dict:
    """Minimal Atlassian Document Format doc wrapping plain text."""
    paragraph: dict = {"type": "paragraph"}
    if text:
        paragraph["content"] = [{"type": "text", "text": text}]
    return {"type": "doc", "version": 1, "content": [paragraph]}


class AtlassianTaskTracker:
    def __init__(self, config: AtlassianConfig, project: str, transport: Transport | None = None):
        self._cfg = config
        self._project = project
        self._rest = AtlassianRest(config, transport)
        self._subtask_type: str | None = None

    def _browse(self, key: str) -> str:
        return f"{self._cfg.site_url}/browse/{key}"

    def subtask_type_name(self) -> str:
        """The project's sub-task issue-type NAME (varies: "Subtask" / "Sub-task"), resolved from
        Jira and cached. Reconcile creates a platform task under its story as a sub-task, because
        Jira rejects a standard Task parented to a Story (Bugs S.No 142). Falls back to "Subtask"
        if the lookup fails."""
        if self._subtask_type is None:
            try:
                meta = self._rest.request("GET", f"/rest/api/3/project/{self._project}")
                subs = [t["name"] for t in meta.get("issueTypes", []) if t.get("subtask")]
                self._subtask_type = subs[0] if subs else "Subtask"
            except Exception:
                self._subtask_type = "Subtask"
        return self._subtask_type

    # ── TaskTracker capability ──────────────────────────────────────
    def create_issue(self, *, kind: str, summary: str, description: str,
                     parent_ref: str | None = None, fields: dict | None = None) -> ExternalRef:
        f: dict = {
            "project": {"key": self._project},
            "summary": summary,
            "issuetype": {"name": kind},
            "description": _adf(description),
        }
        if parent_ref:
            f["parent"] = {"key": parent_ref}
        if fields:
            f.update(fields)
        data = self._rest.request("POST", "/rest/api/3/issue", body={"fields": f})
        key = data["key"]
        return ExternalRef(sor=_SOR, id=key, url=self._browse(key))

    def get_issue(self, *, issue_ref: str) -> Issue:
        data = self._rest.request(
            "GET", f"/rest/api/3/issue/{issue_ref}",
            query={"fields": "summary,status,issuetype,parent"},
        )
        f = data.get("fields") or {}
        parent = (f.get("parent") or {}).get("key")
        return Issue(
            key=data["key"], summary=f.get("summary", ""),
            status=(f.get("status") or {}).get("name", ""),
            issue_type=(f.get("issuetype") or {}).get("name", ""),
            url=self._browse(data["key"]), parent_ref=parent,
        )

    def available_transitions(self, *, issue_ref: str) -> list[str]:
        """Target status names reachable from the issue's current status (helper)."""
        data = self._rest.request("GET", f"/rest/api/3/issue/{issue_ref}/transitions")
        return [(t.get("to") or {}).get("name", "") for t in (data or {}).get("transitions", [])]

    def transition_issue(self, *, issue_ref: str, to_state: str) -> Issue:
        data = self._rest.request("GET", f"/rest/api/3/issue/{issue_ref}/transitions")
        tid = None
        for tr in (data or {}).get("transitions", []):
            names = {(tr.get("to") or {}).get("name", "").lower(), tr.get("name", "").lower()}
            if to_state.lower() in names:
                tid = tr["id"]
                break
        if tid is None:
            raise CapabilityError(f"no transition to {to_state!r} for {issue_ref}")
        self._rest.request(
            "POST", f"/rest/api/3/issue/{issue_ref}/transitions",
            body={"transition": {"id": tid}},
        )
        return self.get_issue(issue_ref=issue_ref)

    def add_comment(self, *, issue_ref: str, body: str) -> None:
        self._rest.request(
            "POST", f"/rest/api/3/issue/{issue_ref}/comment", body={"body": _adf(body)}
        )

    def delete_issue(self, *, issue_ref: str, delete_subtasks: bool = False) -> None:
        """Not part of the capability; used for test cleanup."""
        query = {"deleteSubtasks": "true"} if delete_subtasks else None
        self._rest.request("DELETE", f"/rest/api/3/issue/{issue_ref}", query=query)

    def search(self, *, jql: str) -> list[IssueHit]:
        data = self._rest.request(
            "POST", "/rest/api/3/search/jql",
            body={"jql": jql, "maxResults": 25, "fields": ["summary"]},
        )
        return [
            IssueHit(key=i["key"], summary=(i.get("fields") or {}).get("summary", ""))
            for i in (data or {}).get("issues", [])
        ]
