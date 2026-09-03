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
    # "b" is one character — dropped as a term (it would match anything). Search by a real
    # identifier instead, which is what the tool is now documented to want.
    hits = {h["file"] for h in ci.search_codebase(repo="acme/api", query="value")}
    assert "pkg/b.py" in hits                              # matched in CONTENT, not the path
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


# ── B3: search must match WORDS, in content as well as paths ────────
def test_search_matches_whole_words_not_substrings(repo):
    """The substring bug: 'ci' matched inside 'dependencies.py' and ranked it first.

    Live in run 98ab9a8c, `search_codebase('CI CD pipeline docker compose')` answered
    `dependencies.py` — because "ci" is inside "dependen**ci**es". It never errored; it just
    answered wrongly, which is the failure mode an agent cannot detect.
    """
    ws = repo
    (ws / "pkg" / "dependencies.py").write_text("def resolve():\n    return []\n")
    ci = BuiltinCodeIntel()
    ci.index(workspace=ws, repo="acme/api")
    hits = {h["file"] for h in ci.search_codebase(repo="acme/api", query="ci cd pipeline")}
    assert "pkg/dependencies.py" not in hits    # 'ci' is not a WORD in that path


def test_search_finds_content_not_just_filenames(repo):
    """The other half: a concept present in the code but absent from every file NAME.

    `search_codebase('authentication JWT token')` returned nothing on a repo that authenticates,
    because the search only ever looked at file paths."""
    (repo / "pkg" / "sec.py").write_text(
        'def authenticate(token):\n    """Check the JWT is valid."""\n    return True\n')
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    hits = ci.search_codebase(repo="acme/api", query="authenticate jwt")
    assert "pkg/sec.py" in {h["file"] for h in hits}
    top = hits[0]
    assert top["where"] == "content" and top["terms_matched"] == 2


# ── B4: the language/context filter ─────────────────────────────────
def test_previously_unsupported_languages_are_analysed(tmp_path):
    """A C#/PHP/Vue repo indexed as ZERO files while git still reported real commits — the
    shape of a healthy codebase, because hotspots need a file that was never collected."""
    ws = tmp_path / "poly"
    ws.mkdir()
    for name in ("Program.cs", "index.php", "App.vue", "main.swift", "util.cpp"):
        (ws / name).write_text("int x = 1;\n")
    idx = BuiltinCodeIntel().index(workspace=ws, repo="poly/x")
    assert idx.file_count == 5


def test_config_files_answer_ci_cd_and_stack_without_polluting_the_graph(tmp_path):
    """`signals` exists because "is there CI/CD?" was unanswerable: workflow and manifest files
    carry non-code extensions, so the only evidence available was which code extensions
    appeared — which is how `dependencies.py` came back as CI/CD evidence."""
    ws = tmp_path / "app"
    (ws / ".github" / "workflows").mkdir(parents=True)
    (ws / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (ws / "Dockerfile").write_text("FROM python:3.12\n")
    (ws / "package.json").write_text('{"name":"app"}\n')
    (ws / "app.py").write_text("x = 1\n")
    ci = BuiltinCodeIntel()
    idx = ci.index(workspace=ws, repo="a/b")
    over = ci.get_overview(repo="a/b")
    assert over["signals"]["ci_cd"]["present"] is True
    assert ".github/workflows/ci.yml" in over["signals"]["ci_cd"]["evidence"]
    assert over["signals"]["containerized"]["present"] is True
    assert over["signals"]["dependency_manifest"]["present"] is True
    # Presence-only: config files must never become analysis nodes or inflate the file count.
    assert idx.file_count == 1
    dead = {d["file"] for d in ci.get_dead_code(repo="a/b")}
    assert not any(f.endswith((".json", ".yml")) or f == "Dockerfile" for f in dead)


def test_skipped_file_types_are_reported(tmp_path):
    """The agent's quality gate demands "any skipped files recorded as assumptions" — it had no
    way to know anything was skipped."""
    ws = tmp_path / "mixed"
    ws.mkdir()
    (ws / "a.py").write_text("x = 1\n")
    (ws / "legacy.cobol").write_text("IDENTIFICATION DIVISION.\n")
    ci = BuiltinCodeIntel()
    ci.index(workspace=ws, repo="m/x")
    assert ci.index_report(repo="m/x")["skipped_files"] == {".cobol": 1}


def test_unindexed_target_reports_unknown_not_zero(repo):
    """A row of zeros — 0 lines, 0 complexity, no owner, bus_factor false — is indistinguishable
    from a small, clean, well-shared file. The agent wrote "not indexed" into artifacts as
    "healthy"."""
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    ctx = ci.get_context(repo="acme/api", targets=["Program.cs"])["Program.cs"]
    assert ctx["indexed"] is False and "lines" not in ctx
    risk = ci.get_risk(repo="acme/api", targets=["Program.cs"])["Program.cs"]
    assert risk["indexed"] is False and "hotspot_score" not in risk


# ── B5: git failure must be distinguishable from "no history" ───────
def test_git_failure_is_reported_not_silently_zero(repo, monkeypatch):
    """S4-8 was exactly this: git missing from PATH -> `""` -> `commits: 0`, which reads as
    "this repo has no history" instead of "I could not read the history". Hotspots then come
    back EMPTY (every file has churn 0) and report as "no hotspots found"."""
    import integrations.codeintel.builtin as b

    monkeypatch.setattr(b, "_git_checked",
                        lambda ws, *a, **k: ("", "timed out after 60s"))
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    report = ci.index_report(repo="acme/api")
    assert report["git"]["ok"] is False
    assert "timed out" in report["git"]["error"]
    assert report["analysed_files"] > 0          # the file walk succeeded — the trap
    assert ci.get_overview(repo="acme/api")["git_ok"] is False


def test_healthy_git_reports_ok(repo):
    ci = BuiltinCodeIntel()
    ci.index(workspace=repo, repo="acme/api")
    report = ci.index_report(repo="acme/api")
    assert report["git"] == {"ok": True, "partial": False, "error": "", "commits": 4}


def test_git_checked_separates_timeout_from_empty_output(monkeypatch):
    import subprocess as sp

    from integrations.codeintel.builtin import _git_checked

    def boom(cmd, **kw):
        raise sp.TimeoutExpired(cmd, 60)

    monkeypatch.setattr(sp, "run", boom)
    out, err = _git_checked(__import__("pathlib").Path("/ws"), "log")
    assert out == "" and "timed out after 60s" in err


def test_git_helper_never_inherits_stdin(monkeypatch):
    """Every git subprocess must be handed its OWN stdin.

    `capture_output=True` redirects stdout/stderr only — stdin is still inherited. Harmless from
    a web process; fatal inside the companion's CodeIntel **MCP server**, whose stdin *is* the
    JSON-RPC channel to the engine. The child gets a duplicate handle to the protocol pipe and
    blocks on it, leaving the server no line to answer on.

    Observed live (run edefff0d): `git log … --name-only` alive 369s at 0s CPU with its parent
    gone, `codeintel.index` never returning, and the engine reporting 'MCP server "codeintel"
    tool "index" sent no response or progress for 1800s'. The identical command run by hand
    finished instantly. Three earlier runs were killed chasing this.
    """
    import subprocess as sp
    from pathlib import Path
    from types import SimpleNamespace

    from integrations.codeintel.builtin import _git

    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(cmd=cmd, kwargs=kwargs)
        return SimpleNamespace(returncode=0, stdout="out", stderr="")

    monkeypatch.setattr(sp, "run", fake_run)
    assert _git(Path("/ws"), "log", "--oneline") == "out"
    assert seen["kwargs"].get("stdin") is sp.DEVNULL, (
        "git would inherit the MCP server's stdin — the JSON-RPC channel"
    )
    # The other guards that keep a hung git from taking the run down with it.
    assert seen["kwargs"].get("timeout") == 60
    assert seen["kwargs"].get("capture_output") is True


# ── S4-23: the dependency graph must not invent edges ────────────────
@pytest.fixture
def polyglot_repo(tmp_path):
    """A repo shaped like the real defect: a Python package that (a) imports the STDLIB
    `logging` while also containing its own `middleware/logging.py`, (b) imports a
    third-party dotted module `starlette.types`, and (c) sits beside a frontend whose only
    `types.ts` is the sole file in the tree with that basename.

    Before the fix every one of those produced an edge: 6 files "importing" the local
    logging module they never named, and two Python files "importing" a TypeScript file.
    """
    ws = tmp_path / "poly"
    (ws / "backend" / "app" / "middleware").mkdir(parents=True)
    (ws / "frontend" / "src" / "api").mkdir(parents=True)
    (ws / "backend" / "app" / "middleware" / "logging.py").write_text(
        "import json\nimport logging\nfrom starlette.types import ASGIApp\n")
    # Names the stdlib module only — must NOT be wired to middleware/logging.py.
    (ws / "backend" / "app" / "service.py").write_text(
        "import logging\n\ndef go():\n    return 1\n")
    # Names the LOCAL module explicitly — this edge is real and must survive.
    (ws / "backend" / "app" / "main.py").write_text(
        "import logging\nfrom app.middleware.logging import Mw\n")
    (ws / "backend" / "app" / "__init__.py").write_text("")
    (ws / "frontend" / "src" / "api" / "types.ts").write_text(
        "export type Expense = { id: string }\n")
    (ws / "frontend" / "src" / "api" / "client.ts").write_text(
        "import { Expense } from './types'\nexport const c = 1\n")
    return ws


def _edges(ws):
    from integrations.codeintel.builtin import _analyze

    return {(f, t) for f, t in _analyze(ws, "acme/poly")["graph"]["edges"]}


def test_python_import_never_resolves_to_a_frontend_file(polyglot_repo):
    """A Python `import` cannot name a TypeScript file. Two such edges shipped live."""
    cross = {(f, t) for f, t in _edges(polyglot_repo)
             if f.endswith(".py") != t.endswith(".py")}
    assert cross == set(), f"fabricated cross-language edges: {cross}"


def test_stdlib_import_does_not_wire_to_a_same_named_repo_file(polyglot_repo):
    """`import logging` names the standard library, not this repo's middleware/logging.py.

    On the live repo 6 of that file's 7 inbound edges were exactly this confusion, inflating
    its PageRank and blast radius sevenfold."""
    edges = _edges(polyglot_repo)
    target = "backend/app/middleware/logging.py"
    assert ("backend/app/service.py", target) not in edges
    # And the same, through the surface the agent actually reads.
    ci = BuiltinCodeIntel()
    ci.index(workspace=polyglot_repo, repo="acme/poly")
    assert "backend/app/service.py" not in ci.get_risk(
        repo="acme/poly", targets=[target])[target]["dependents"]


def test_an_explicit_local_import_of_that_same_module_still_resolves(polyglot_repo):
    """The other half of the guard: narrowing must not delete REAL edges. `main.py` does
    name the local module, so that edge has to survive the stdlib filter."""
    assert ("backend/app/main.py", "backend/app/middleware/logging.py") in _edges(polyglot_repo)


def test_relative_js_import_still_resolves(polyglot_repo):
    """The family restriction must leave ordinary in-language resolution untouched."""
    assert ("frontend/src/api/client.ts", "frontend/src/api/types.ts") in _edges(polyglot_repo)
