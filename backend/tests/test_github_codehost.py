"""P2 — CodeHost capability over GitHub (REST v3).

Unit tests drive the connector through a fake transport (request shaping, response
parsing, idempotency, pr_ref handling) with no network. A registry test proves per-tenant
selection. A live test (skips without creds) does a real round-trip and self-cleans.
"""
import base64
import uuid

import pytest

from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant
from integrations.capabilities import CodeHost
from integrations.github.codehost import GithubCodeHost
from integrations.github.config import GithubConfig
from integrations.registry import get_capability
from integrations.types import CapabilityError


class _Recorder:
    """A Transport stub: routes via a handler(method, url, body) and records calls."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[tuple] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        return self._handler(method, url, body)

    def methods(self) -> list[str]:
        return [m for m, _u, _b in self.calls]


def _codehost(handler, repo="acme/api"):
    rec = _Recorder(handler)
    cfg = GithubConfig(api_url="https://api.github.com", token="t")
    return GithubCodeHost(cfg, default_repo=repo, transport=rec), rec


_PR = {"number": 7, "html_url": "https://github.com/acme/api/pull/7",
       "head": {"ref": "feature/ST-1", "sha": "abc123"}, "base": {"ref": "develop"},
       "state": "open", "title": "t", "draft": True}


# ── open_pull_request (idempotent) ──────────────────────────────────
def test_open_pull_request_creates_when_none_open():
    def handler(method, url, body):
        if method == "GET" and "/pulls" in url:
            return 200, []                       # no existing open PR for the head
        if method == "POST" and url.endswith("/pulls"):
            return 201, _PR
        raise AssertionError(url)

    ch, rec = _codehost(handler)
    ref = ch.open_pull_request(repo="acme/api", head="feature/ST-1", base="develop",
                               title="t", body="b")
    assert ref.number == 7 and ref.head == "feature/ST-1" and ref.sha == "abc123"
    assert ref.url.endswith("/pull/7") and ref.pr_ref == "acme/api#7"
    assert "POST" in rec.methods()


def test_open_pull_request_is_idempotent_when_one_exists():
    def handler(method, url, body):
        if method == "GET" and "/pulls" in url:
            return 200, [_PR]                    # register-don't-recreate
        raise AssertionError(f"must not create: {method} {url}")

    ch, rec = _codehost(handler)
    ref = ch.open_pull_request(repo="acme/api", head="feature/ST-1", base="develop",
                               title="t", body="b")
    assert ref.number == 7
    assert "POST" not in rec.methods()           # never called create


# ── read-through ────────────────────────────────────────────────────
def test_get_pull_request_parses_fields():
    merged = {**_PR, "state": "closed", "merged": True}
    ch, _ = _codehost(lambda m, u, b: (200, merged))
    pr = ch.get_pull_request(pr_ref="acme/api#7")
    assert pr.number == 7 and pr.state == "closed" and pr.merged is True
    assert pr.head == "feature/ST-1" and pr.base == "develop" and pr.repo == "acme/api"


def test_get_branch_returns_none_on_404():
    ch, _ = _codehost(lambda m, u, b: (404, {"message": "Not Found"}))
    assert ch.get_branch(name="missing") is None


def test_get_branch_returns_ref_on_200():
    ch, _ = _codehost(lambda m, u, b: (200, {"name": "develop", "commit": {"sha": "deadbeef"}}))
    branch = ch.get_branch(name="develop")
    assert branch.sha == "deadbeef" and branch.repo == "acme/api" and branch.name == "develop"


def test_list_pr_files():
    ch, _ = _codehost(lambda m, u, b: (200, [{"filename": "a.py"}, {"filename": "b.py"}]))
    assert ch.list_pr_files(pr_ref="acme/api#7") == ["a.py", "b.py"]


def test_get_file_decodes_base64():
    encoded = base64.b64encode(b"hello world").decode()
    ch, _ = _codehost(lambda m, u, b: (200, {"content": encoded}))
    assert ch.get_file(repo="acme/api", path="README.md", ref="develop") == "hello world"


# ── writes ──────────────────────────────────────────────────────────
def test_set_commit_status_posts_to_the_sha():
    ch, rec = _codehost(lambda m, u, b: (201, {}))
    ch.set_commit_status(repo="acme/api", sha="abc123", state="success", context="ci/build")
    method, url, body = rec.calls[-1]
    assert method == "POST" and url.endswith("/statuses/abc123")
    assert body["state"] == "success" and body["context"] == "ci/build"


def test_add_pr_comment_posts_to_issue_comments():
    ch, rec = _codehost(lambda m, u, b: (201, {}))
    ch.add_pr_comment(pr_ref="acme/api#7", body="looks good")
    method, url, body = rec.calls[-1]
    assert method == "POST" and url.endswith("/issues/7/comments") and body["body"] == "looks good"


def test_merge_pull_request_merges_then_reads_back():
    def handler(method, url, body):
        if method == "PUT" and url.endswith("/merge"):
            assert body["merge_method"] == "squash"
            return 200, {"merged": True, "sha": "m1"}
        if method == "GET" and "/pulls/7" in url:
            return 200, {**_PR, "state": "closed", "merged": True}
        raise AssertionError(url)

    ch, rec = _codehost(handler)
    pr = ch.merge_pull_request(pr_ref="acme/api#7")
    assert pr.merged is True and "PUT" in rec.methods()


def test_malformed_pr_ref_raises():
    ch, _ = _codehost(lambda m, u, b: (200, {}))
    with pytest.raises(CapabilityError):
        ch.get_pull_request(pr_ref="not-a-ref")


def test_no_repo_and_no_default_raises():
    ch, _ = _codehost(lambda m, u, b: (200, {}), repo="")
    with pytest.raises(CapabilityError):
        ch.get_branch(name="develop")


# ── per-tenant selection (the #9 seam) ──────────────────────────────
def test_get_capability_resolves_codehost_to_github(db):
    tenant = Tenant.objects.create(name="Acme")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="codehost", connector="github",
        scopes={"repo": "acme/api", "default_base": "develop"}, token_ref="settings:github",
    )
    ch = get_capability(tenant.id, "codehost")
    assert isinstance(ch, CodeHost)              # behind the vendor-free Protocol
    assert ch._default_repo == "acme/api"        # bound from the connection's scopes


# ── live round-trip against real GitHub (runs only with creds) ──────
def _live():
    from django.conf import settings

    cfg = GithubConfig.from_settings()
    repo = settings.GITHUB_REPO
    base = settings.GITHUB_DEFAULT_BASE or "main"
    return (cfg, repo, base) if (cfg.configured and repo) else None


@pytest.mark.skipif(_live() is None, reason="GitHub creds/repo not configured in .env")
def test_github_codehost_live_pr_roundtrip():
    from integrations.github.rest import GithubRest

    cfg, repo, base = _live()
    ch = GithubCodeHost(cfg, default_repo=repo)
    rest = GithubRest(cfg)
    marker = uuid.uuid4().hex[:8]
    branch = f"feature/codehost-smoke-{marker}"
    pr_ref = None
    try:
        # Setup (the companion's job in production): branch off base + a one-file commit.
        base_sha = rest.request("GET", f"/repos/{repo}/git/ref/heads/{base}")["object"]["sha"]
        rest.request("POST", f"/repos/{repo}/git/refs",
                     body={"ref": f"refs/heads/{branch}", "sha": base_sha})
        rest.request("PUT", f"/repos/{repo}/contents/smoke-{marker}.md",
                     body={"message": f"smoke {marker}", "branch": branch,
                           "content": base64.b64encode(b"# smoke\n").decode()})

        assert ch.get_branch(name=branch) is not None
        ref = ch.open_pull_request(head=branch, base=base,
                                   title=f"smoke {marker}", body="codehost smoke")
        pr_ref = ref.pr_ref
        # Idempotent: a second open returns the same PR.
        again = ch.open_pull_request(head=branch, base=base, title="x", body="y")
        assert again.number == ref.number

        pr = ch.get_pull_request(pr_ref=pr_ref)
        assert pr.state == "open" and pr.head == branch
        assert any(f.startswith(f"smoke-{marker}") for f in ch.list_pr_files(pr_ref=pr_ref))
        ch.set_commit_status(repo=repo, sha=ref.sha, state="success", context="codehost-smoke")
        ch.add_pr_comment(pr_ref=pr_ref, body="smoke comment")
    finally:
        if pr_ref:
            try:
                ch.close_pull_request(pr_ref=pr_ref)
            except Exception:  # noqa: BLE001
                pass
        try:
            ch.delete_ref(branch=branch)
        except Exception:  # noqa: BLE001
            pass
