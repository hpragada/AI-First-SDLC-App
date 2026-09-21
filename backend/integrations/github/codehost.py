"""GithubCodeHost — the CodeHost capability over GitHub Cloud (REST v3).

Owns the PR/merge/status/comment surface (branches are pushed by git in the runner's
worktree, Phase-2 D2). Returns vendor-free BranchRef/PullRequestRef/PullRequest so callers
stay GitHub-unaware (#9). Pointers only — bodies are read through, never copied (#1/#3).
`open_pull_request` is idempotent: an existing open PR for the head is returned, not
duplicated (register-don't-recreate, B1). `pr_ref` is the stable handle "owner/name#N".
"""
from __future__ import annotations

import base64

from integrations.types import (
    BranchRef,
    CapabilityError,
    PullRequest,
    PullRequestRef,
)

from .config import GithubConfig
from .rest import GithubRest

_SOR = "git"


def _split_pr_ref(pr_ref: str) -> tuple[str, int]:
    """"owner/name#123" -> ("owner/name", 123)."""
    repo, _, number = pr_ref.rpartition("#")
    if not repo or not number.isdigit():
        raise CapabilityError("That pull request reference isn't in the expected form.")
    return repo, int(number)


class GithubCodeHost:
    def __init__(self, config: GithubConfig, default_repo: str = "", transport=None):
        self._cfg = config
        self._default_repo = default_repo
        self._rest = GithubRest(config, transport)

    def ping(self) -> str:
        """Live reachability + auth check (Bugs S.No 156): who is this token? Cheap, read-only,
        and touches no repository — "Test connection" previously only proved the connector was
        constructible, so an expired or wrong-scope token still reported OK."""
        me = self._rest.request("GET", "/user") or {}
        who = me.get("login") or "the account"
        return f"Signed in to GitHub as {who}."

    def _repo(self, repo: str | None) -> str:
        repo = repo or self._default_repo
        if not repo:
            raise CapabilityError(
                "No repository was named, and the connection has no default repository. "
                "Add one in the connection settings."
            )
        return repo

    def _pr(self, repo: str, data: dict) -> PullRequest:
        head = (data.get("head") or {})
        base = (data.get("base") or {})
        return PullRequest(
            repo=repo, number=int(data["number"]), title=data.get("title", ""),
            state=data.get("state", ""), head=head.get("ref", ""), base=base.get("ref", ""),
            url=data.get("html_url", ""), sha=head.get("sha"),
            merged=bool(data.get("merged") or data.get("merged_at")),
            draft=bool(data.get("draft")),
            mergeable=data.get("mergeable"),
            mergeable_state=data.get("mergeable_state", ""),
        )

    # ── CodeHost capability ─────────────────────────────────────────
    def get_branch(self, *, repo: str | None = None, name: str) -> BranchRef | None:
        repo = self._repo(repo)
        try:
            data = self._rest.request("GET", f"/repos/{repo}/branches/{name}")
        except CapabilityError as exc:
            if exc.status == 404:
                return None
            raise
        sha = ((data or {}).get("commit") or {}).get("sha", "")
        return BranchRef(repo=repo, name=name, sha=sha,
                         url=f"{_html_base(repo)}/tree/{name}")

    def open_pull_request(self, *, repo: str | None = None, head: str, base: str,
                          title: str, body: str, draft: bool = True) -> PullRequestRef:
        repo = self._repo(repo)
        owner = repo.split("/", 1)[0]
        existing = self._rest.request(
            "GET", f"/repos/{repo}/pulls",
            query={"head": f"{owner}:{head}", "state": "open", "per_page": 1},
        )
        if existing:  # register-don't-recreate
            return self._ref(repo, existing[0])
        data = self._rest.request(
            "POST", f"/repos/{repo}/pulls",
            body={"title": title, "head": head, "base": base, "body": body, "draft": draft},
        )
        return self._ref(repo, data)

    def get_pull_request(self, *, pr_ref: str) -> PullRequest:
        repo, number = _split_pr_ref(pr_ref)
        data = self._rest.request("GET", f"/repos/{repo}/pulls/{number}")
        return self._pr(repo, data)

    def list_pr_files(self, *, pr_ref: str) -> list[str]:
        repo, number = _split_pr_ref(pr_ref)
        data = self._rest.request(
            "GET", f"/repos/{repo}/pulls/{number}/files", query={"per_page": 100}
        )
        return [f["filename"] for f in (data or [])]

    def set_commit_status(self, *, repo: str | None = None, sha: str, state: str,
                          context: str, description: str = "",
                          target_url: str | None = None) -> None:
        repo = self._repo(repo)
        self._rest.request(
            "POST", f"/repos/{repo}/statuses/{sha}",
            body={"state": state, "context": context, "description": description,
                  "target_url": target_url},
        )

    def add_pr_comment(self, *, pr_ref: str, body: str) -> None:
        repo, number = _split_pr_ref(pr_ref)
        self._rest.request(
            "POST", f"/repos/{repo}/issues/{number}/comments", body={"body": body}
        )

    def mark_ready_for_review(self, *, pr_ref: str) -> None:
        """Take a draft PR out of draft so it can be merged — GitHub refuses to merge a draft
        PR (HTTP 405). REST v3 cannot un-draft; only the GraphQL `markPullRequestReadyForReview`
        mutation can. Idempotent: a PR that is already ready is left untouched (safe on Temporal
        retries). After the mutation we re-read the PR (bounded retries) to absorb GitHub's brief
        eventual-consistency window before the caller attempts the merge."""
        import time

        repo, number = _split_pr_ref(pr_ref)
        data = self._rest.request("GET", f"/repos/{repo}/pulls/{number}")
        if not (data or {}).get("draft"):
            return
        node_id = (data or {}).get("node_id")
        if not node_id:
            raise CapabilityError(
                f"GitHub didn't recognise pull request {pr_ref}, so it couldn't be marked "
                "ready for review."
            )
        self._rest.graphql(
            "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id})"
            "{pullRequest{isDraft}}}",
            {"id": node_id},
        )
        # Confirm the un-draft has propagated to the REST view before returning (the merge
        # endpoint reads REST); a couple of short waits cover the propagation lag that otherwise
        # produces a spurious 405-on-merge right after un-drafting.
        for _ in range(5):
            fresh = self._rest.request("GET", f"/repos/{repo}/pulls/{number}")
            if not (fresh or {}).get("draft"):
                return
            time.sleep(1)

    def _read_pr_settled(self, repo: str, number: int, *, tries: int = 6,
                         delay: float = 1.0) -> dict:
        """Read a PR, waiting (bounded) for GitHub to finish computing `mergeable` — it is `null`
        for a brief window after the PR is opened or its branch mutated. Returns the last read
        even if it stays null (the caller treats null as 'unknown', not a conflict)."""
        import time

        data = self._rest.request("GET", f"/repos/{repo}/pulls/{number}")
        for _ in range(tries - 1):
            if (data or {}).get("mergeable") is not None:
                break
            time.sleep(delay)
            data = self._rest.request("GET", f"/repos/{repo}/pulls/{number}")
        return data or {}

    def update_branch(self, *, pr_ref: str) -> None:
        """Update the PR's head branch with the latest base (GitHub 'Update branch' — merges base
        into head) so a branch that is merely *behind* becomes mergeable (Bugs S.No 136).
        Idempotent: a 422 'already up to date' is a no-op, safe on Temporal retries."""
        repo, number = _split_pr_ref(pr_ref)
        try:
            self._rest.request("PUT", f"/repos/{repo}/pulls/{number}/update-branch")
        except CapabilityError as exc:
            if exc.status == 422:      # already up to date — nothing to do
                return
            raise

    def ensure_mergeable(self, *, pr_ref: str) -> PullRequest:
        """Resolve a PR's mergeability before the gated merge (Bugs S.No 136). If the branch is
        merely *behind* its base (base moved, no conflict), update it against base and re-check;
        return the PR with `mergeable`/`mergeable_state` resolved so the caller decides
        merge-vs-conflict instead of blindly PUT-merging a `dirty` PR into a raw 405."""
        repo, number = _split_pr_ref(pr_ref)
        data = self._read_pr_settled(repo, number)
        if (data or {}).get("mergeable_state") == "behind":
            self.update_branch(pr_ref=pr_ref)
            data = self._read_pr_settled(repo, number)
        return self._pr(repo, data)

    def merge_pull_request(self, *, pr_ref: str, method: str = "squash") -> PullRequest:
        repo, number = _split_pr_ref(pr_ref)
        self._rest.request(
            "PUT", f"/repos/{repo}/pulls/{number}/merge", body={"merge_method": method}
        )
        return self.get_pull_request(pr_ref=pr_ref)

    def get_file(self, *, repo: str | None = None, path: str, ref: str) -> str:
        repo = self._repo(repo)
        data = self._rest.request(
            "GET", f"/repos/{repo}/contents/{path}", query={"ref": ref}
        )
        raw = (data or {}).get("content", "")
        return base64.b64decode(raw).decode("utf-8", "replace") if raw else ""

    # ── test-cleanup helpers (not part of the capability) ───────────
    def close_pull_request(self, *, pr_ref: str) -> None:
        repo, number = _split_pr_ref(pr_ref)
        self._rest.request("PATCH", f"/repos/{repo}/pulls/{number}", body={"state": "closed"})

    def delete_ref(self, *, repo: str | None = None, branch: str) -> None:
        repo = self._repo(repo)
        self._rest.request("DELETE", f"/repos/{repo}/git/refs/heads/{branch}")

    # ── internals ───────────────────────────────────────────────────
    def _ref(self, repo: str, data: dict) -> PullRequestRef:
        head = (data.get("head") or {})
        return PullRequestRef(
            sor=_SOR, repo=repo, number=int(data["number"]), head=head.get("ref", ""),
            url=data.get("html_url", ""), sha=head.get("sha"),
        )


def _html_base(repo: str) -> str:
    return f"https://github.com/{repo}"
