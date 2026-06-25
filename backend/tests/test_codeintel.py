"""P4 — CodeIntel capability: the built-in SOTA analyzer (D1) on a real git repo.

Builds a tiny multi-file Python repo with real git history (a churned file, an import
graph, an entry point, a dead file), runs the built-in analyzer, and asserts every layer:
git analytics + Tornhill hotspots, the dependency graph + PageRank, dead-code, and the
8-tool surface. A registry test proves per-tenant selection (codeintel -> builtin).
"""
import subprocess

import pytest

from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant
from integrations.capabilities import CodeIntel
from integrations.codeintel.builtin import BuiltinCodeIntel
from integrations.registry import get_capability


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """pkg/b <- pkg/a <- main (entry); pkg/c is dead. b.py is churned 3x (hotspot)."""
    ws = tmp_path / "acme-api"
    (ws / "pkg").mkdir(parents=True)
    (ws / "main.py").write_text("import pkg.a\n\nprint('go')\n")
    (ws / "pkg" / "__init__.py").write_text("")
    (ws / "pkg" / "a.py").write_text("from pkg import b\n\ndef run():\n    return b.value()\n")
    (ws / "pkg" / "b.py").write_text("def value():\n    return 1\n")
    (ws / "pkg" / "c.py").write_text("def orphan():\n    return 0\n")

    _git(ws, "init", "-b", "main")
    _git(ws, "config", "user.email", "dev@acme.test")
    _git(ws, "config", "user.name", "Dev")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-m", "init")
    # churn b.py across separate commits so it dominates the hotspot ranking
    for i in range(3):
        (ws / "pkg" / "b.py").write_text(
            f"def value():\n    if {i}:\n        return {i}\n    return 1\n")
        _git(ws, "commit", "-am", f"tweak b {i}")
    return ws


def test_analyze_and_index(repo):
    ci = BuiltinCodeIntel()
    idx = ci.index(workspace=repo, repo="acme/api")
    assert idx.repo == "acme/api"
    assert idx.file_count == 5 and idx.languages == {".py": 5}
    assert idx.commits == 4                      # init + 3 churn commits
    assert idx.hotspots >= 1


def test_git_hotspots_rank_the_churned_file(repo):
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    over = ci.get_overview(repo="acme/api")
    assert over["commits"] == 4 and over["authors"] == 1
    assert over["hotspots"][0]["file"] == "pkg/b.py"      # churn x complexity -> top hotspot
    assert over["hotspots"][0]["risk"] == "high"


def test_dependency_graph_and_pagerank(repo):
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    over = ci.get_overview(repo="acme/api")
    # b.py is the most-imported module -> highest PageRank -> top module
    assert over["top_modules"][0] == "pkg/b.py"
    risk = ci.get_risk(repo="acme/api", targets=["pkg/b.py"])
    assert "pkg/a.py" in risk["pkg/b.py"]["dependents"]    # a imports b
    path = ci.get_dependency_path(repo="acme/api", frm="main.py", to="pkg/b.py")
    assert path == ["main.py", "pkg/a.py", "pkg/b.py"]     # main -> a -> b


def test_dead_code_flags_the_orphan(repo):
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    dead = {d["file"] for d in ci.get_dead_code(repo="acme/api")}
    assert "pkg/c.py" in dead                              # nothing imports c, not an entry
    assert "main.py" not in dead                           # entry point excluded


def test_context_and_search_and_diagram(repo):
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    ctx = ci.get_context(repo="acme/api", targets=["pkg/b.py"])
    assert ctx["pkg/b.py"]["churn"] == 4 and ctx["pkg/b.py"]["owner"] == "dev@acme.test"
    assert ctx["pkg/b.py"]["bus_factor_risk"] is True      # single owner
    hits = {h["file"] for h in ci.search_codebase(repo="acme/api", query="b")}
    assert "pkg/b.py" in hits
    assert "graph TD" in ci.get_architecture_diagram(repo="acme/api")


def test_unindexed_repo_raises(repo):
    ci = BuiltinCodeIntel()
    with pytest.raises(KeyError):
        ci.get_overview(repo="never/indexed")


def test_analyze_non_git_dir_degrades_gracefully(tmp_path):
    ws = tmp_path / "loose"
    ws.mkdir()
    (ws / "x.py").write_text("y = 1\n")
    idx = BuiltinCodeIntel().index(workspace=ws, repo="loose/x")
    assert idx.file_count == 1 and idx.commits == 0        # no git -> churn empty, still indexes


# ── per-tenant selection (the #9 seam) ──────────────────────────────
def test_get_capability_resolves_codeintel_to_builtin(db):
    tenant = Tenant.objects.create(name="Acme")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="codeintel", connector="builtin",
        scopes={}, token_ref="builtin",
    )
    ci = get_capability(tenant.id, "codeintel")
    assert isinstance(ci, CodeIntel)                       # behind the vendor-free Protocol
    assert isinstance(ci, BuiltinCodeIntel)


def test_repo_path_is_posix_relative(repo):
    """Paths are repo-relative POSIX (stable across OSes), never absolute host paths (#3)."""
    a = BuiltinCodeIntel()
    a.index(workspace=repo, repo="acme/api")
    over = a.get_overview(repo="acme/api")
    assert all("/" in m or m.endswith(".py") for m in over["top_modules"])
    assert not any(str(repo) in m for m in over["top_modules"])
