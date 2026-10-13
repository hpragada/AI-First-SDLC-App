"""BuiltinCodeIntel — the default, no-license code-intelligence analyzer (D1).

Matches the algorithmic SOTA the legacy Repowise engine targets, from stdlib + git:

- **Git analytics / hotspots** — churn x complexity per Tornhill (*Software Design X-Rays*):
  the highest-signal layer, fully real and language-agnostic (from `git log`).
- **Dependency graph** — regex import extraction (Python/TS-JS/Go/Java) -> a directed graph
  with pure-Python **PageRank** + connected-component communities. (tree-sitter parsing +
  networkx centrality are the drop-in precision upgrades behind this same interface.)
- **Code health** — dead-code (no inbound edge, not an entry point) + a complexity proxy.
- **Decisions** — ADR-marker / commit-message archaeology (best-effort).

Runs in the companion worktree (D2); persists only the analysis, never the source (#1/#3).
The same 8-tool surface is served regardless of engine, so agents never change.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from integrations.types import IntelIndex

_SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
              "vendor", ".next", ".turbo", "target", "out", ".mypy_cache", ".pytest_cache"}
#: Files that participate in the ANALYSIS — dependency graph nodes, complexity, hotspots, dead
#: code, search. This one set gates `_collect_files`, and `file_meta` is the only node set every
#: later layer knows about, so an extension missing here is invisible to all of them at once
#: (B4). A C#/PHP/Swift/C++ repo indexed as ZERO files while git analytics — which reads `git
#: log` and is not filtered — still reported thousands of commits: the shape of a *healthy*
#: codebase, because hotspots require a churn entry for a file that was never collected.
_LANG_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rb", ".rs", ".kt",
             ".cs", ".php", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".mm",
             ".scala", ".vue", ".svelte", ".dart", ".ex", ".exs", ".sh", ".sql", ".lua", ".pl"}

#: Files collected for PRESENCE only — never graph nodes, never complexity or hotspot inputs.
#: The agent's artifact spec requires a "Technology Stack (confirmed from code analysis)" and a
#: "CI/CD presence" field, and neither was answerable: `package.json`, `requirements.txt`,
#: `.github/workflows/*.yml` and `docker-compose.yml` all carry non-code extensions, so the only
#: stack evidence in existence was *which code extensions appeared*. Kept deliberately separate
#: from `_LANG_EXT` so widening the evidence base cannot distort the dependency graph.
_CONTEXT_EXT = {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml", ".gradle",
                ".tf", ".tfvars", ".md", ".rst", ".env", ".lock", ".properties"}

#: Extensionless files that are pure signal. `path.suffix` is empty for these, so no
#: extension-based rule could ever have reached them.
_CONTEXT_NAMES = {"Dockerfile", "Makefile", "Jenkinsfile", "Procfile", "Vagrantfile",
                  "CODEOWNERS", "Gemfile", "Rakefile", "requirements.txt"}
_ENTRY_NAMES = {"main", "index", "__init__", "__main__", "app", "manage", "cmd", "setup",
                "conftest", "wsgi", "asgi", "server"}

#: Language family per extension — an import may only resolve WITHIN its own family (S4-23).
#: A Python `import` cannot name a TypeScript file, so a match across families is always wrong.
#: Extensions absent here can never be an import TARGET, which is correct: nothing `import`s a
#: .css, .sql or .md file. Kept separate from `_LANG_EXT` (which decides what is a graph NODE)
#: because the two questions differ: `.vue` is a node and a legal JS target; `.sql` is a node
#: and never a target.
_IMPORT_FAMILY = {
    ".py": "py", ".pyi": "py",
    ".ts": "js", ".tsx": "js", ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".vue": "js", ".svelte": "js",
    ".java": "jvm", ".kt": "jvm", ".scala": "jvm",
    ".go": "go",
}

#: Python's own standard library. `import logging` names the stdlib module, never this repo's
#: `middleware/logging.py` — but a bare-name match cannot tell the difference, so before this
#: guard 6 of the 7 inbound edges on that file were fabricated by exactly that confusion.
#: `sys.stdlib_module_names` is authoritative and version-accurate (3.10+), so the set can
#: never drift from the interpreter actually running the analysis.
_PY_STDLIB_ROOTS = frozenset(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
_COMPLEXITY = re.compile(r"\b(if|for|while|case|elif|when|catch|switch|except)\b|&&|\|\||\?")
_MAX_BYTES = 1_000_000

#: Per-file and whole-repo caps on the searchable text copy kept in memory (see `_analyze`).
_SEARCH_TEXT_PER_FILE = 20_000
_SEARCH_TEXT_BUDGET = 40_000_000

# import-extraction patterns per language family
_JS_IMPORT = re.compile(
    r"""(?:import\s+[^'"]*?from\s+|require\(\s*|import\s*\(\s*)['"]([^'"]+)['"]"""
)
_GO_IMPORT = re.compile(r'"([^"]+)"')
_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
_PY_IMPORT = re.compile(r"^\s*import\s+(.+)", re.M)
_PY_FROM = re.compile(r"^\s*from\s+([.\w]+)\s+import\s+(.+)", re.M)


def _py_imports(text: str) -> list[str]:
    """`import a.b [as x], c` and `from M import a, b` -> candidate module paths
    (incl. the M.a / M.b submodules so `from pkg import b` finds pkg/b)."""
    toks: list[str] = []
    for raw in _PY_IMPORT.findall(text):
        if raw.lstrip().startswith(("import", "from")):  # guard against odd matches
            continue
        for part in raw.split("#", 1)[0].split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                toks.append(name)
    for mod, names in _PY_FROM.findall(text):
        toks.append(mod)
        for part in names.split("#", 1)[0].split(","):
            name = part.strip().split(" as ")[0].strip().strip("()")
            if name and name != "*":
                toks.append((mod if mod.endswith(".") else mod + ".") + name)
    return toks


def _git(workspace: Path, *args: str) -> str:
    """Run a read-only git command in `workspace` and return stdout ("" on any failure).

    `stdin=DEVNULL` is LOAD-BEARING — do not drop it. `capture_output` covers stdout/stderr only,
    so without this the child INHERITS the parent's stdin. That is harmless from a web process and
    fatal inside the companion's CodeIntel **MCP server**, whose stdin *is* the JSON-RPC channel to
    the engine: git receives a duplicate handle to the protocol pipe, blocks on it, and the server
    is left with no line to answer on. Observed live (run edefff0d): `git log … --name-only` alive
    369s at **0s CPU** with its parent gone, `codeintel.index` never returning, and the engine
    finally reporting *'MCP server "codeintel" tool "index" sent no response or progress for
    1800s'*. The same command run by hand finished instantly with 6,689 bytes. Any subprocess
    spawned under a stdio MCP server must own its stdin.
    """
    return _git_checked(workspace, *args)[0]


def _git_checked(workspace: Path, *args: str, timeout: int = 60) -> tuple[str, str]:
    """`(stdout, error)` — the same call as `_git`, but it says WHY it produced nothing.

    `_git` collapses every outcome into `""`: a timeout, a missing git binary, a corrupt index
    and a repository with genuinely no commits are indistinguishable. That is not hypothetical
    — **S4-8 was exactly this**. git was missing from the server's PATH, `_git` returned `""`,
    and the platform reported `commits: 0`, which reads as "this repo has no history" rather
    than "I could not read the history". Because the empty string flows into `_git_analytics`,
    every counter stays at zero, and `_hotspots` skips any file with `churn <= 0` — so the
    churn x complexity ranking, the single highest-value output of this whole phase, comes back
    EMPTY and reports as "no hotspots found". The agent's Step 1 check ("verify the IntelIndex
    is non-empty") passes regardless, because `file_count` comes from the filesystem walk.

    Callers that need to tell those cases apart use this; `_decisions` stays on the tolerant
    `_git` because decision archaeology is best-effort by design (B5)."""
    try:
        out = subprocess.run(["git", "-C", str(workspace), *args],
                             stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0:
            return "", (out.stderr or "").strip()[:200] or f"git exited {out.returncode}"
        return out.stdout, ""
    except subprocess.TimeoutExpired:
        return "", f"timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"{type(exc).__name__}: {exc}"[:200]


class BuiltinCodeIntel:
    """Per-tenant connector; caches one analysis per repo (set by `index()`)."""

    def __init__(self):
        self._analyses: dict[str, dict] = {}

    # ── indexing ────────────────────────────────────────────────────
    def index(self, *, workspace, repo: str, scope: dict | None = None) -> IntelIndex:
        ws = Path(workspace)
        analysis = _analyze(ws, repo)
        self._analyses[repo] = analysis
        return IntelIndex(
            repo=repo, indexed_at=analysis["indexed_at"], file_count=analysis["file_count"],
            languages=analysis["languages"], commits=analysis["git"]["commits"],
            hotspots=len(analysis["hotspots"]),
        )

    def index_report(self, *, repo: str) -> dict:
        """Health of the INDEX ITSELF, separate from the codebase it describes.

        `IntelIndex` reports what was found; this reports what could not be. An agent that only
        checks "is the index non-empty" cannot distinguish a clean read from a degraded one —
        `file_count` comes from the filesystem walk and stays healthy even when git failed
        completely. Read this before interpreting any result (B4/B5)."""
        a = self._a(repo)
        g = a["git"]
        return {
            "git": {"ok": g.get("ok", True), "partial": g.get("partial", False),
                    "error": g.get("error", ""), "commits": g["commits"]},
            "skipped_files": a.get("skipped", {}),
            "analysed_files": a["file_count"],
            "config_files_seen": len(a.get("config_files", [])),
            "content_search_complete": a.get("search_text_complete", True),
            # Named, not counted. "Content search is incomplete" tells an agent to distrust every
            # search result it has; these two tell it exactly which files to distrust, which is
            # the difference between a usable assumption and a useless one.
            "partially_indexed_files": a.get("partially_indexed_files", []),
            "unsearchable_files": a.get("unsearchable_files", []),
        }

    def _a(self, repo: str) -> dict:
        if repo not in self._analyses:
            raise KeyError(f"repo not indexed: {repo!r} (call index() first)")
        return self._analyses[repo]

    # ── 8-tool surface ──────────────────────────────────────────────
    def get_overview(self, *, repo: str) -> dict:
        a = self._a(repo)
        top = sorted(a["graph"]["pagerank"].items(), key=lambda kv: -kv[1])[:10]
        return {
            "repo": repo, "file_count": a["file_count"], "languages": a["languages"],
            "commits": a["git"]["commits"], "authors": len(a["git"]["authors"]),
            "top_modules": [f for f, _ in top], "entry_points": a["entry_points"],
            "communities": len(a["graph"]["communities"]), "hotspots": a["hotspots"][:5],
            # Evidence-backed presence checks + index health, so the agent never has to infer
            # "is there CI/CD?" from code file names, and can see a degraded read (B4/B5).
            "signals": a.get("signals", {}),
            "git_ok": a["git"].get("ok", True),
            "git_error": a["git"].get("error", ""),
            "skipped_files": a.get("skipped", {}),
            "partially_indexed_files": a.get("partially_indexed_files", []),
            "unsearchable_files": a.get("unsearchable_files", []),
        }

    def get_context(self, *, repo: str, targets: list[str]) -> dict:
        a = self._a(repo)
        out = {}
        for t in targets:
            f = a["files"].get(t)
            if f is None:
                # A path that was never indexed used to answer with a full row of ZEROS —
                # 0 lines, 0 complexity, no owner, bus_factor_risk false. Indistinguishable
                # from a small, clean, well-shared file, so the agent wrote "not indexed" into
                # artifacts as "healthy". Say so instead (B4).
                out[t] = {"indexed": False,
                          "reason": "not analysed — unsupported file type, excluded directory, "
                                    "too large, or the path does not exist in this repo"}
                continue
            owners = a["git"]["file_owners"].get(t, {})
            top_owner = max(owners, key=owners.get) if owners else None
            out[t] = {
                "indexed": True,
                "lines": f.get("lines", 0), "complexity": f.get("complexity", 0),
                "lang": f.get("lang", ""), "churn": a["git"]["file_churn"].get(t, 0),
                "owner": top_owner, "bus_factor_risk": bool(owners) and len(owners) == 1,
            }
        return out

    def get_risk(self, *, repo: str, targets: list[str]) -> dict:
        a = self._a(repo)
        score = {h["file"]: h["score"] for h in a["hotspots"]}
        out = {}
        for t in targets:
            if t not in a["files"]:
                out[t] = {"indexed": False,                     # same trap as get_context (B4)
                          "reason": "not analysed — this file is not in the index, so its risk "
                                    "is UNKNOWN, not zero"}
                continue
            dependents = sorted(a["graph"]["in_edges"].get(t, []))
            co = a["git"]["co_change"].get(t, {})
            out[t] = {
                "hotspot_score": score.get(t, 0),
                "dependents": dependents,
                "co_change": sorted(co, key=co.get, reverse=True)[:5],
                "blast_radius": _reachable(a["graph"]["in_edges"], t),
            }
        return out

    def get_why(self, *, repo: str, query: str = "") -> list[dict]:
        decisions = self._a(repo)["decisions"]
        if not query:
            return decisions
        q = query.lower()
        return [d for d in decisions if q in (d.get("title", "") + d.get("ref", "")).lower()]

    def search_codebase(self, *, repo: str, query: str) -> list[dict]:
        """Whole-word keyword search over file paths AND file contents.

        It previously counted raw SUBSTRINGS in the path alone, and looked at nothing else.
        Two ways that lied, both observed live in run 98ab9a8c:

        - `'authentication JWT token'` returned NOTHING in a repo that authenticates, because
          no file was *named* that.
        - `'CI CD pipeline docker compose'` returned `dependencies.py` — "ci" appears inside
          "dependen**ci**es". A meaningless match, ranked first, presented as evidence.

        It never errored either time; it answered confidently and wrongly, which is the worst
        failure mode for a tool an agent uses to decide what exists. Now: word boundaries only,
        content matched as well as path, path weighted higher (a file named `auth.py` beats one
        that merely mentions auth), and single-character terms dropped (B3).
        """
        a = self._a(repo)
        terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1]
        if not terms:
            return []
        patterns = [re.compile(rf"\b{re.escape(t)}\b") for t in terms]
        hits = []
        for path, meta in a["files"].items():
            low = path.lower()
            body = (meta.get("text") or "").lower()
            path_hits = sum(1 for p in patterns if p.search(low))
            body_hits = sum(len(p.findall(body)) for p in patterns) if body else 0
            matched = sum(1 for p in patterns
                          if p.search(low) or (body and p.search(body)))
            if not matched:
                continue
            hits.append({
                "file": path,
                # Path match is the strong signal; body occurrences break ties. `matched`
                # (how many DISTINCT query terms appear) dominates both, so a file covering
                # the whole query outranks one repeating a single word.
                "score": matched * 100 + path_hits * 10 + min(body_hits, 9),
                "terms_matched": matched, "of_terms": len(terms),
                "where": ("path" if path_hits else "content"),
            })
        return sorted(hits, key=lambda h: (-h["score"], h["file"]))[:20]

    def get_dependency_path(self, *, repo: str, frm: str, to: str) -> list[str]:
        return _bfs_path(self._a(repo)["graph"]["out_edges"], frm, to)

    def get_dead_code(self, *, repo: str) -> list[dict]:
        return self._a(repo)["dead_code"]

    def get_architecture_diagram(self, *, repo: str, module: str | None = None) -> str:
        a = self._a(repo)
        lines = ["graph TD"]
        for frm, to in a["graph"]["edges"]:
            if module and not (frm.startswith(module) or to.startswith(module)):
                continue
            lines.append(f'  "{frm}" --> "{to}"')
        return "\n".join(lines[:200])


# ── analysis engine ─────────────────────────────────────────────────
def _analyze(ws: Path, repo: str) -> dict:
    files, config_files, skipped = _scan(ws)
    languages: dict[str, int] = defaultdict(int)
    file_meta: dict[str, dict] = {}
    budget = _SEARCH_TEXT_BUDGET
    # Which files content-search can only PARTLY see, and which it cannot see at all (T7). A
    # whole file we skipped has always been reported, because the agent's own quality gate
    # requires "any skipped files recorded as assumptions" - but a file that was read and then
    # cut was reported as nothing at all. A 60,000-character legacy file was two-thirds invisible
    # to search while the index looked perfectly healthy, which is a worse lie than a skip: the
    # agent searches, finds nothing, and concludes the code does not do the thing.
    partially_indexed: list[str] = []
    not_searchable: list[str] = []
    for rel, ext, text in files:
        languages[ext] += 1
        file_meta[rel] = {"lang": ext, "lines": text.count("\n") + 1,
                          "complexity": len(_COMPLEXITY.findall(text))}
        # Keep a bounded, lower-cased copy so `search_codebase` can match CONTENT and not just
        # file names (B3). Bounded twice — per file and across the repo — because the whole
        # analysis is held in memory inside the companion's MCP server, and an unbounded copy of
        # a monorepo would put the developer's machine under pressure to answer a search query.
        # Past the budget, search degrades to path-only for the remaining files rather than
        # growing without limit; `search_text_complete` records whether that happened.
        if budget > 0:
            snippet = text[:_SEARCH_TEXT_PER_FILE].lower()
            file_meta[rel]["text"] = snippet
            budget -= len(snippet)
            if len(text) > _SEARCH_TEXT_PER_FILE:
                partially_indexed.append(rel)
        else:
            # Past the whole-repo budget the remaining files carry no searchable text at all.
            # This was recorded only as one repo-wide boolean, so an agent could learn that
            # SOMETHING was unsearchable but never which files - which is not enough to write
            # down as an assumption, and so not enough to act on.
            not_searchable.append(rel)

    git = _git_analytics(ws)
    edges, out_edges, in_edges = _dependency_graph(files)
    pagerank = _pagerank(out_edges, list(file_meta))
    communities = _components(out_edges, in_edges, list(file_meta))
    hotspots = _hotspots(file_meta, git["file_churn"], git["file_owners"])
    entry_points = [p for p in file_meta if Path(p).stem in _ENTRY_NAMES
                    or "/test" in p or p.startswith("test")]
    dead_code = _dead_code(file_meta, in_edges, set(entry_points))
    decisions = _decisions(ws, files)

    return {
        "repo": repo, "indexed_at": datetime.now(UTC).isoformat(),
        "file_count": len(file_meta), "languages": dict(languages), "files": file_meta,
        "git": git,
        "graph": {"edges": edges, "out_edges": out_edges, "in_edges": in_edges,
                  "pagerank": pagerank, "communities": communities},
        "hotspots": hotspots, "dead_code": dead_code, "decisions": decisions,
        "entry_points": entry_points,
        "config_files": config_files, "skipped": skipped,
        "signals": _signals(config_files),
        "search_text_complete": budget > 0 and not partially_indexed,
        "partially_indexed_files": partially_indexed,
        "unsearchable_files": not_searchable,
    }


#: Presence checks the agent's artifact spec explicitly asks for, each answerable from the
#: config inventory alone. Substrings are matched against the repo-relative path, lowercased.
_SIGNAL_MARKERS = {
    "ci_cd": (".github/workflows/", ".gitlab-ci", "jenkinsfile", "azure-pipelines",
              ".circleci/", "bitbucket-pipelines", ".travis.yml"),
    "containerized": ("dockerfile", "docker-compose", ".dockerignore"),
    "iac": (".tf", "terraform/", "cloudformation", "helm/", "k8s/", "kubernetes/"),
    "dependency_manifest": ("package.json", "requirements.txt", "pyproject.toml", "go.mod",
                            "pom.xml", "build.gradle", "gemfile", "cargo.toml", "composer.json",
                            "*.csproj", "pubspec.yaml"),
    "documentation": ("readme", "docs/", "contributing"),
}


def _signals(config_files: list[str]) -> dict:
    """Evidence-backed yes/no answers with the file that proves each one.

    The health dashboard asks "CI/CD presence"; before this the only way to answer was to guess
    from code file names, which is how `dependencies.py` came back as CI/CD evidence. Every
    answer here names the file it rests on, so the agent reports a measured fact rather than an
    inference — the distinction its own Role section is built around (B4)."""
    low = [(p, p.lower()) for p in config_files]
    out = {}
    for name, markers in _SIGNAL_MARKERS.items():
        hits = [p for p, lp in low if any(m.strip("*") in lp for m in markers)]
        out[name] = {"present": bool(hits), "evidence": hits[:5]}
    return out


def _collect_files(ws: Path) -> list[tuple[str, str, str]]:
    """Analysable source files only — kept as its own function because these, and only these,
    become dependency-graph nodes."""
    return _scan(ws)[0]


def _scan(ws: Path) -> tuple[list[tuple[str, str, str]], list[str], dict[str, int]]:
    """One walk, three results: `(code_files, context_files, skipped)`.

    `skipped` counts files that EXIST but were not analysed, by extension. The agent's own
    quality gate says "any skipped files recorded as assumptions" — and until now the agent had
    no way to know anything had been skipped, making that checkbox impossible to satisfy
    honestly. Now silence means silence and a number means a gap (B4)."""
    code: list[tuple[str, str, str]] = []
    context: list[str] = []
    skipped: dict[str, int] = defaultdict(int)
    for path in ws.rglob("*"):
        if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(ws).as_posix()
        if path.suffix in _CONTEXT_EXT or path.name in _CONTEXT_NAMES:
            context.append(rel)
            continue
        if path.suffix not in _LANG_EXT:
            # Only count things that plausibly ARE source. Images, fonts and binaries are not a
            # coverage gap and reporting them as one would bury the signal.
            if path.suffix and len(path.suffix) <= 6:
                skipped[path.suffix] += 1
            continue
        try:
            if path.stat().st_size > _MAX_BYTES:
                skipped[path.suffix] += 1        # too large to read is still a real gap
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            skipped[path.suffix] += 1
            continue
        code.append((rel, path.suffix, text))
    return code, sorted(context), dict(skipped)


def _git_analytics(ws: Path) -> dict:
    fmt = ("log", "--no-merges", "--format=__C__%H|%ae|%aI", "--name-only")
    log, err = _git_checked(ws, fmt[0], fmt[1], "-n", "500", *fmt[2:])
    partial = False
    if err and "timed out" in err:
        # Retry smaller before giving up. `--name-only` over 500 commits of a monorepo can be
        # tens of MB; partial history that we KNOW is partial beats none at all (B5).
        log, err2 = _git_checked(ws, fmt[0], fmt[1], "-n", "200", *fmt[2:], timeout=90)
        if not err2:
            err, partial = "", True
    commits = 0
    authors: dict[str, int] = defaultdict(int)
    file_churn: dict[str, int] = defaultdict(int)
    file_owners: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    co_change: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    first = last = None
    cur_email = None
    touched: list[str] = []

    def _flush():
        for i, f in enumerate(touched):
            for g in touched[i + 1:]:
                co_change[f][g] += 1
                co_change[g][f] += 1

    for line in log.splitlines():
        if line.startswith("__C__"):
            _flush()
            touched = []
            try:
                _sha, email, iso = line[len("__C__"):].split("|", 2)
            except ValueError:
                continue
            commits += 1
            cur_email = email
            authors[email] += 1
            last = last or iso
            first = iso
        elif line.strip():
            f = line.strip()
            file_churn[f] += 1
            if cur_email:
                file_owners[f][cur_email] += 1
            touched.append(f)
    _flush()
    return {
        # `ok` is the difference between "no history" and "could not read the history". Every
        # consumer — and the agent — must be able to tell those apart (B5).
        "ok": not err, "error": err, "partial": partial,
        "commits": commits, "authors": dict(authors), "first": first, "last": last,
        "file_churn": dict(file_churn),
        "file_owners": {f: dict(o) for f, o in file_owners.items()},
        "co_change": {f: dict(c) for f, c in co_change.items()},
    }


def _dependency_graph(files):
    by_noext: dict[str, str] = {}
    by_base: dict[str, list] = defaultdict(list)
    family_of: dict[str, str] = {}
    for rel, ext, _text in files:
        noext = rel.rsplit(".", 1)[0]
        by_noext[noext] = rel
        by_base[Path(rel).stem].append(rel)
        family_of[rel] = _IMPORT_FAMILY.get(ext, "")

    def resolve(token: str, importer: str, family: str) -> str | None:
        """Resolve one import token to a file IN THIS REPO, or None (S4-23).

        Every rule below is a heuristic, so each is fenced by what the language makes
        possible. Returning None is always safe — a missing edge understates coupling;
        a fabricated edge invents architecture, and PageRank, blast-radius, communities
        and the hotspot ranking are all computed from these edges.
        """
        token = token.strip().strip("'\"")
        if not token:
            return None
        norm = token.lstrip(".").replace(".", "/")
        # An absolute Python import rooted at the standard library is never a repo file.
        # Relative imports (`from .logging import x`) are always local, so they are exempt.
        if (family == "py" and not token.startswith(".")
                and norm.split("/", 1)[0] in _PY_STDLIB_ROOTS):
            return None
        # Same-family only: nothing can import across languages.
        def matches(rel: str) -> bool:
            return family_of.get(rel) == family

        cand = norm.rsplit("/", 1)[0] if token.endswith((".ts", ".js")) else norm
        # 1) a file whose path-without-ext ends with the token path
        for noext, rel in by_noext.items():
            if matches(rel) and (noext == norm or noext.endswith("/" + norm) or noext == cand):
                return rel
        # 2) relative JS import resolved against the importer's directory
        if token.startswith("."):
            base = (Path(importer).parent / token.lstrip("./")).as_posix().rsplit(".", 1)[0]
            for noext, rel in by_noext.items():
                if matches(rel) and (noext == base or noext == base + "/index"):
                    return rel
        # 3) fall back to a unique basename match. For a DOTTED Python module path the last
        # segment alone is a guess, not evidence — `starlette.types` is a third-party package,
        # not this repo's `types.py`. Such a token must have matched its FULL path at (1).
        if family == "py" and "/" in norm:
            return None
        last = norm.rsplit("/", 1)[-1]
        named = [rel for rel in by_base.get(last, []) if matches(rel)]
        if len(named) == 1:
            return named[0]
        return None

    out_edges: dict[str, set] = defaultdict(set)
    in_edges: dict[str, set] = defaultdict(set)
    for rel, ext, text in files:
        family = _IMPORT_FAMILY.get(ext, "")
        if not family:
            continue
        for tok in _extract_imports(ext, text):
            target = resolve(tok, rel, family)
            if target and target != rel:
                out_edges[rel].add(target)
                in_edges[target].add(rel)
    edges = sorted((f, t) for f, ts in out_edges.items() for t in ts)
    return (edges,
            {k: sorted(v) for k, v in out_edges.items()},
            {k: sorted(v) for k, v in in_edges.items()})


def _extract_imports(ext: str, text: str) -> list[str]:
    if ext == ".py":
        return _py_imports(text)
    if ext in (".ts", ".tsx", ".js", ".jsx"):
        return _JS_IMPORT.findall(text)
    if ext == ".java" or ext == ".kt":
        return _JAVA_IMPORT.findall(text)
    if ext == ".go":
        block = re.search(r"import\s*\((.*?)\)", text, re.S)
        return _GO_IMPORT.findall(block.group(1)) if block else _GO_IMPORT.findall(text)
    return []


def _pagerank(out_edges, nodes, *, damping=0.85, iters=30) -> dict:
    if not nodes:
        return {}
    n = len(nodes)
    rank = {x: 1.0 / n for x in nodes}
    for _ in range(iters):
        nxt = {x: (1 - damping) / n for x in nodes}
        for src in nodes:
            outs = out_edges.get(src, [])
            share = rank[src] / len(outs) if outs else rank[src] / n
            if outs:
                for dst in outs:
                    nxt[dst] = nxt.get(dst, 0) + damping * share
            else:  # dangling: spread evenly
                for x in nodes:
                    nxt[x] += damping * share
        rank = nxt
    return {k: round(v, 6) for k, v in rank.items()}


def _components(out_edges, in_edges, nodes) -> list[list[str]]:
    adj = defaultdict(set)
    for s, ts in out_edges.items():
        for t in ts:
            adj[s].add(t)
            adj[t].add(s)
    seen, comps = set(), []
    for start in nodes:
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in adj.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        if len(comp) > 1:
            comps.append(sorted(comp))
    return sorted(comps, key=len, reverse=True)


def _hotspots(file_meta, churn, owners) -> list[dict]:
    rows = []
    for f, meta in file_meta.items():
        c = churn.get(f, 0)
        if c <= 0:
            continue
        # Tornhill hotspot = churn x complexity (complexity floored at 1 so churn dominates
        # for low-complexity files rather than a size proxy distorting the ranking).
        complexity = max(meta["complexity"], 1)
        score = c * complexity
        o = owners.get(f, {})
        rows.append({"file": f, "churn": c, "complexity": meta["complexity"],
                     "lines": meta["lines"], "score": score,
                     "top_owner": max(o, key=o.get) if o else None})
    rows.sort(key=lambda r: (-r["score"], -r["churn"], -r["lines"], r["file"]))
    cut = max(1, len(rows) // 5)
    for i, r in enumerate(rows):
        r["risk"] = "high" if i < cut else ("medium" if i < cut * 2 else "low")
    return rows


def _dead_code(file_meta, in_edges, entry_points) -> list[dict]:
    out = []
    for f in file_meta:
        if f in entry_points or in_edges.get(f):
            continue
        out.append({"file": f, "reason": "no inbound import edge; not an entry point",
                    "confidence": "low"})  # conservative — dynamic loading may apply
    return out


def _decisions(ws: Path, files) -> list[dict]:
    out = []
    for rel, _ext, _text in files:
        if "adr" in rel.lower() or "/decisions/" in ("/" + rel.lower()):
            out.append({"title": Path(rel).stem, "source": "file", "ref": rel})
    log = _git(ws, "log", "--no-merges", "-n", "300", "--format=%s")
    for subj in log.splitlines():
        if re.search(r"\bADR-\d+|\bdecision:|\bdecided\b", subj, re.I):
            out.append({"title": subj.strip(), "source": "commit", "ref": subj.strip()})
    return out[:100]


def _reachable(in_edges, start: str) -> int:
    seen, q = set(), deque([start])
    while q:
        x = q.popleft()
        for y in in_edges.get(x, []):
            if y not in seen:
                seen.add(y)
                q.append(y)
    return len(seen)


def _bfs_path(out_edges, frm: str, to: str) -> list[str]:
    if frm == to:
        return [frm]
    prev, q = {frm: None}, deque([frm])
    while q:
        x = q.popleft()
        for y in out_edges.get(x, []):
            if y not in prev:
                prev[y] = x
                if y == to:
                    path, n = [], y
                    while n is not None:
                        path.append(n)
                        n = prev[n]
                    return list(reversed(path))
                q.append(y)
    return []
