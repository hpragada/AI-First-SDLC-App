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

#: Rows per Jira request. 100 is Jira Cloud's practical page maximum for this endpoint.
_PAGE_SIZE = 100
#: Runaway guard for a single `search` — high enough that no real backlog reaches it, low enough
#: that a pathological JQL can't page forever. Reaching it is reported, never silent (S3-15).
_SEARCH_LIMIT = 5000


def _adf(text: str) -> dict:
    """Minimal Atlassian Document Format doc wrapping plain text."""
    paragraph: dict = {"type": "paragraph"}
    if text:
        paragraph["content"] = [{"type": "text", "text": text}]
    return {"type": "doc", "version": 1, "content": [paragraph]}


#: ADF block types rendered as a markdown list item, and the bullet to use.
_ADF_LIST_MARK = {"bulletList": "- ", "orderedList": "1. "}


def _adf_to_text(node, _depth: int = 0) -> str:
    """Flatten an Atlassian Document Format body to readable markdown.

    Jira v3 returns descriptions as ADF, not a string — a nested tree of blocks. Reading it
    without this returns a dict, and `str()`-ing that would hand an agent a wall of JSON.

    Deliberately lossy but *faithful to the words*: headings, lists, code blocks, links, tables
    and line breaks survive as text, because a task's acceptance criteria are usually a bulleted
    list and losing the bullets loses the structure of the requirement. Panels/media/emoji
    degrade to their text content rather than disappearing silently. Anything unrecognised still
    has its children walked, so a node type Atlassian adds later costs formatting, never content.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_adf_to_text(n, _depth) for n in node)
    if not isinstance(node, dict):
        return ""

    kind = node.get("type")
    kids = node.get("content") or []

    if kind == "text":
        text = node.get("text", "")
        for mark in node.get("marks") or []:
            if mark.get("type") == "code":
                text = f"`{text}`"
            elif mark.get("type") == "link":
                href = (mark.get("attrs") or {}).get("href")
                if href:
                    text = f"[{text}]({href})"
        return text
    if kind in ("hardBreak", "rule"):
        return "\n"
    if kind == "mention":
        return (node.get("attrs") or {}).get("text") or ""
    if kind == "emoji":
        attrs = node.get("attrs") or {}
        return attrs.get("text") or attrs.get("shortName") or ""
    if kind == "inlineCard":
        return (node.get("attrs") or {}).get("url") or ""
    if kind == "codeBlock":
        lang = (node.get("attrs") or {}).get("language") or ""
        return f"\n```{lang}\n{_adf_to_text(kids, _depth)}\n```\n"
    if kind == "heading":
        level = (node.get("attrs") or {}).get("level") or 1
        return f"\n{'#' * int(level)} {_adf_to_text(kids, _depth).strip()}\n"
    if kind in _ADF_LIST_MARK:
        mark, indent = _ADF_LIST_MARK[kind], "  " * _depth
        items = [_adf_to_text(k, _depth + 1).strip() for k in kids]
        return "\n" + "\n".join(f"{indent}{mark}{i}" for i in items if i) + "\n"
    if kind == "listItem":
        return _adf_to_text(kids, _depth).strip()
    if kind in ("paragraph", "blockquote", "panel", "tableCell", "tableHeader"):
        body = _adf_to_text(kids, _depth).strip()
        return f"{body}\n" if body else ""
    if kind == "tableRow":
        cells = [_adf_to_text(k, _depth).strip().replace("\n", " ") for k in kids]
        return "| " + " | ".join(cells) + " |\n"

    return _adf_to_text(kids, _depth)


def _description_text(value) -> str:
    """A Jira description as text, whichever shape the field arrives in (ADF doc, or a plain
    string on older sites / some import paths)."""
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    return "\n".join(
        line.rstrip() for line in _adf_to_text(value).splitlines()
    ).strip()


class AtlassianTaskTracker:
    def __init__(self, config: AtlassianConfig, project: str, transport: Transport | None = None):
        self._cfg = config
        self._project = project
        self._rest = AtlassianRest(config, transport)
        self._subtask_type: str | None = None

    def ping(self) -> str:
        """Live reachability + auth check (Bugs S.No 156): who are we authenticated as? Cheap,
        read-only, and touches no project data — "Test connection" previously only proved the
        connector was constructible, so a wrong token or site URL still reported OK."""
        me = self._rest.request("GET", "/rest/api/3/myself") or {}
        who = me.get("displayName") or me.get("emailAddress") or "the account"
        return f"Signed in to Jira at {self._cfg.site_url} as {who}."

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
            # `description` is the issue's actual specification — for a brownfield import it is
            # the ONLY statement of what the work is. Omitting it from `fields` meant every
            # imported work item reached the build agent as a bare one-line title.
            query={"fields": "summary,status,issuetype,parent,description"},
        )
        f = data.get("fields") or {}
        parent = (f.get("parent") or {}).get("key")
        return Issue(
            key=data["key"], summary=f.get("summary", ""),
            status=(f.get("status") or {}).get("name", ""),
            issue_type=(f.get("issuetype") or {}).get("name", ""),
            url=self._browse(data["key"]), parent_ref=parent,
            description=_description_text(f.get("description")),
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
            raise CapabilityError(
                f"Jira won't let {issue_ref} move to that status from where it is now. "
                "Its workflow may need that step added."
            )
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

    def search(self, *, jql: str, limit: int = _SEARCH_LIMIT) -> list[IssueHit]:
        """Every issue matching `jql`, following Jira's paging to the end (S3-15).

        This used to send `maxResults: 25` and read one page. Jira answered with 25 rows and a
        `nextPageToken` nobody looked at, so a backlog import took the first 25 issues and
        reported success — on a real 68-issue project that silently dropped all 14 Epics and all
        15 Stories, keeping only subtasks. `limit` is a runaway guard, not a page size: callers
        that need to know whether it bit should compare against `count()`.
        """
        out: list[IssueHit] = []
        token: str | None = None
        while len(out) < limit:
            body: dict = {
                "jql": jql,
                "maxResults": min(_PAGE_SIZE, limit - len(out)),
                "fields": ["summary"],
            }
            if token:
                body["nextPageToken"] = token
            data = self._rest.request("POST", "/rest/api/3/search/jql", body=body) or {}
            for i in data.get("issues", []):
                out.append(
                    IssueHit(key=i["key"], summary=(i.get("fields") or {}).get("summary", ""))
                )
            token = data.get("nextPageToken")
            if not token:
                break
        return out

    def count(self, *, jql: str) -> int:
        """How many issues Jira says match `jql` — so an import can report "68 of 68" and notice
        when it didn't get everything. Returns -1 when Jira won't answer, which callers read as
        "unknown" rather than as zero."""
        try:
            data = self._rest.request(
                "POST", "/rest/api/3/search/approximate-count", body={"jql": jql}
            ) or {}
            return int(data.get("count", -1))
        except Exception:  # noqa: BLE001 — a missing count must never fail the import itself
            return -1
