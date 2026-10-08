"""Where a hard limit is real, what it leaves out must be fetchable — and reachable by the agent.

Truncation register, tier 2: the issues where the loss was never silent but was always final.
`get_artifact_body` said `truncated: true` and offered no way to read the remainder; the code
reviewer was told its diff was cut and had no tool that could read a repository file; the code
index said content search was incomplete without naming a single file it had failed to read.

Three different screens of the same mistake: telling somebody what they have lost is only half of
not losing it. These tests pin the other half.
"""
from __future__ import annotations

import pytest

# ── T1 · reading an artifact body a window at a time ────────────────

def _body_payload(text: str, *, max_bytes: int, start: int = 0) -> dict:
    from integrations.preview import _cap_body

    return _cap_body({"body": text}, max_bytes, start)


def test_a_long_body_can_be_read_to_the_end_one_window_at_a_time():
    """Before this, the remainder was simply unreachable — there was no offset parameter at all.

    It is the sharpest form of the problem on a greenfield project: a long PRD or architecture
    document is exactly what exceeds the read cap, and every downstream phase reads it through
    this one call. Both sibling tools (`get_source_extraction`, `get_page_images`) had paginated
    for months; this one never gained it.
    """
    text = "".join(f"line {i}\n" for i in range(5_000))
    window, collected, start = 400, [], 0
    # Generously bounded rather than `while True`: a paging bug should fail the test, not hang it.
    for _ in range(10 * (len(text) // window + 2)):
        page = _body_payload(text, max_bytes=window, start=start)
        collected.append(page["body"])
        assert page["start"] == start
        assert page["total_bytes"] == len(text.encode("utf-8"))
        if page["next_start"] is None:
            break
        assert page["next_start"] > start, "a window that does not advance would loop forever"
        start = page["next_start"]
    assert "".join(collected) == text, "the pages do not reassemble into the original document"


def test_the_last_window_says_it_is_the_last():
    """`next_start` is None only at the end — the signal an agent stops on."""
    assert _body_payload("short", max_bytes=400)["next_start"] is None
    assert _body_payload("x" * 1_000, max_bytes=400)["next_start"] == 400


def test_a_body_that_fits_reads_exactly_as_it_always_did():
    """Back-compat for every caller that never passes an offset — the SBOM preview among them.

    `truncated` and `full_bytes` keep their meaning: there is more after this window. That is what
    they always meant, so nothing downstream has to learn a new contract.
    """
    payload = _body_payload("a small document", max_bytes=400)
    assert payload["body"] == "a small document"
    assert payload["truncated"] is False
    assert "full_bytes" not in payload


def test_a_window_boundary_inside_a_character_does_not_break_the_read():
    """Windows are sized in BYTES, so a boundary can land mid-character on non-Latin text.

    The partial character at the seam is dropped rather than raising, and the next window resumes
    from the byte offset — so the document itself loses nothing. A client whose requirements are
    written in Hindi or Japanese must not hit a decode error on page two.
    """
    text = "हिन्दी " * 500
    start, pages = 0, []
    for _ in range(200):
        page = _body_payload(text, max_bytes=101, start=start)   # odd size: lands mid-character
        pages.append(page["body"])
        if page["next_start"] is None:
            break
        start = page["next_start"]
    assert len("".join(pages)) >= len(text) - 200, "far too much was lost at the seams"


# ── T4 · reading a pull request's file ──────────────────────────────

class _FakePR:
    repo, sha, head = "acme/app", "abc123", "feature/x"


class _FakeCodeHost:
    """Only the three calls `get_pr_file` makes. Routed through the capability, never GitHub."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list[tuple] = []

    def get_pull_request(self, *, pr_ref):
        self.calls.append(("get_pull_request", pr_ref))
        return _FakePR()

    def get_file(self, *, repo, path, ref):
        self.calls.append(("get_file", repo, path, ref))
        return self._content


@pytest.fixture
def tenant(db):
    from apps.tenancy.models import Tenant

    return Tenant.objects.create(name="Acme")


def _patch_codehost(monkeypatch, host):
    import integrations.registry as registry

    monkeypatch.setattr(registry, "get_capability", lambda tenant_id, capability: host)


def test_the_reviewer_can_read_a_file_the_diff_only_showed_part_of(tenant, monkeypatch):
    """The tool the manifest's own fallback line had been promising all along.

    That line told the agent to "fetch the PR via the platform tools" when **no granted tool could
    read a repository file at all**. An agent that hit it was asked to do something impossible,
    and most likely reviewed nothing while reporting a completed review.
    """
    from mcp_platform_state import tools

    content = "".join(f"const x{i} = {i};\n" for i in range(5_000))
    host = _FakeCodeHost(content)
    _patch_codehost(monkeypatch, host)

    collected, start = [], 0
    for _ in range(100):
        page = tools.get_pr_file(str(tenant.id), "acme/app#7", "src/x.ts", start=start)
        assert "error" not in page
        collected.append(page["body"])
        if page["next_start"] is None:
            break
        start = page["next_start"]
    assert "".join(collected) == content
    assert ("get_file", "acme/app", "src/x.ts", "abc123") in host.calls


def test_a_file_that_cannot_be_read_says_so_instead_of_pretending(tenant, monkeypatch):
    """A reviewer that cannot read a file must be able to report that honestly.

    Returning an empty body would read as an empty file, and "this file is empty" is a far more
    damaging answer than "I could not open this file" — one invites a verdict, the other blocks it.
    """
    from mcp_platform_state import tools

    class _Broken(_FakeCodeHost):
        def get_file(self, **kw):
            raise RuntimeError("404 not found")

    _patch_codehost(monkeypatch, _Broken(""))
    page = tools.get_pr_file(str(tenant.id), "acme/app#7", "src/gone.ts")
    assert page["body"] == ""
    assert "src/gone.ts" in page["error"]
    assert page["next_start"] is None


# ── T4 · and only the reviewer may hold it ──────────────────────────

def test_the_pr_reader_is_granted_to_the_code_reviewer_and_to_nobody_else():
    """Least privilege, on both paths an agent can run on.

    The grant lists were one flat list shared by every agent, so a tool added for one became a
    capability for all of them. Reading a repository's files is agent 08's business alone: a
    planning agent with it would be a wider sandbox than the guardrails describe.
    """
    from runner.companion.daemon import PLAN_ALLOWED_TOOLS, REVIEW_ALLOWED_TOOLS

    from orchestration.activities import PLATFORM_TOOLS, REVIEW_TOOLS

    tool = "mcp__platform-state__get_pr_file"
    assert tool in REVIEW_TOOLS and tool not in PLATFORM_TOOLS
    assert tool in REVIEW_ALLOWED_TOOLS and tool not in PLAN_ALLOWED_TOOLS
    # The reviewer keeps everything the base grants; this adds, never replaces.
    assert set(PLATFORM_TOOLS) < set(REVIEW_TOOLS)
    assert set(PLAN_ALLOWED_TOOLS) < set(REVIEW_ALLOWED_TOOLS)


def test_the_reviewer_can_actually_see_the_tool_it_is_granted():
    """Granting a tool is not the same as the agent being able to call it.

    `ToolSearch` is the only mechanism that loads deferred tool schemas back into context, and it
    is deliberately NOT in the review denylist: run `457f65e1` had every platform-state tool
    granted and the agent reported them "not present in my available tool context", then wrote
    39,417 characters of deliverables as prose. A `get_pr_file` nobody can see is a `get_pr_file`
    that does not exist.
    """
    from orchestration.activities import REVIEW_TOOLS

    assert "ToolSearch" in REVIEW_TOOLS


# ── T7 · naming what the code index could only partly read ──────────

def test_the_index_names_the_files_whose_content_it_can_only_partly_see(tmp_path):
    """A 60,000-character legacy file is two-thirds invisible to search, and nothing said so.

    The same module already reports whole files it skipped, because the agent's quality gate
    requires "any skipped files recorded as assumptions" — but a file read and then CUT was
    reported as nothing at all. That is the worse lie of the two: the agent searches, finds
    nothing, and concludes the codebase does not do the thing.
    """
    from integrations.codeintel.builtin import _SEARCH_TEXT_PER_FILE, BuiltinCodeIntel

    (tmp_path / "small.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "huge.py").write_text("# x\n" * (_SEARCH_TEXT_PER_FILE // 2), encoding="utf-8")

    engine = BuiltinCodeIntel()
    engine.index(workspace=tmp_path, repo="acme/app")
    report = engine.index_report(repo="acme/app")

    assert "huge.py" in report["partially_indexed_files"]
    assert "small.py" not in report["partially_indexed_files"]
    # And the summary boolean agrees with the detail, rather than claiming a clean read.
    assert report["content_search_complete"] is False
