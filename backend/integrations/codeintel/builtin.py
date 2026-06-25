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
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from integrations.types import IntelIndex

_SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
              "vendor", ".next", ".turbo", "target", "out", ".mypy_cache", ".pytest_cache"}
_LANG_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rb", ".rs", ".kt"}
_ENTRY_NAMES = {"main", "index", "__init__", "__main__", "app", "manage", "cmd", "setup",
                "conftest", "wsgi", "asgi", "server"}
_COMPLEXITY = re.compile(r"\b(if|for|while|case|elif|when|catch|switch|except)\b|&&|\|\||\?")
_MAX_BYTES = 1_000_000

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
    try:
        out = subprocess.run(["git", "-C", str(workspace), *args],
                             capture_output=True, text=True, timeout=60)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


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
        }

    def get_context(self, *, repo: str, targets: list[str]) -> dict:
        a = self._a(repo)
        out = {}
        for t in targets:
            f = a["files"].get(t)
            owners = a["git"]["file_owners"].get(t, {})
            top_owner = max(owners, key=owners.get) if owners else None
            out[t] = {
                "lines": (f or {}).get("lines", 0), "complexity": (f or {}).get("complexity", 0),
                "lang": (f or {}).get("lang", ""), "churn": a["git"]["file_churn"].get(t, 0),
                "owner": top_owner, "bus_factor_risk": bool(owners) and len(owners) == 1,
            }
        return out

    def get_risk(self, *, repo: str, targets: list[str]) -> dict:
        a = self._a(repo)
        score = {h["file"]: h["score"] for h in a["hotspots"]}
        out = {}
        for t in targets:
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
        # Keyword baseline over file paths/symbols; the Knowledge Index backs the semantic
        # path once embeddings are wired (it delegates here when no provider is set).
        a = self._a(repo)
        terms = [t for t in re.split(r"\W+", query.lower()) if t]
        hits = []
        for path in a["files"]:
            low = path.lower()
            s = sum(low.count(t) for t in terms)
            if s:
                hits.append({"file": path, "score": s})
        return sorted(hits, key=lambda h: -h["score"])[:20]

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
    files = _collect_files(ws)
    languages: dict[str, int] = defaultdict(int)
    file_meta: dict[str, dict] = {}
    for rel, ext, text in files:
        languages[ext] += 1
        file_meta[rel] = {"lang": ext, "lines": text.count("\n") + 1,
                          "complexity": len(_COMPLEXITY.findall(text))}

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
    }


def _collect_files(ws: Path) -> list[tuple[str, str, str]]:
    out = []
    for path in ws.rglob("*"):
        if not path.is_file() or path.suffix not in _LANG_EXT:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out.append((path.relative_to(ws).as_posix(), path.suffix, text))
    return out


def _git_analytics(ws: Path) -> dict:
    log = _git(ws, "log", "--no-merges", "-n", "500", "--format=__C__%H|%ae|%aI", "--name-only")
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
        "commits": commits, "authors": dict(authors), "first": first, "last": last,
        "file_churn": dict(file_churn),
        "file_owners": {f: dict(o) for f, o in file_owners.items()},
        "co_change": {f: dict(c) for f, c in co_change.items()},
    }


def _dependency_graph(files):
    by_noext: dict[str, str] = {}
    by_base: dict[str, list] = defaultdict(list)
    for rel, _ext, _text in files:
        noext = rel.rsplit(".", 1)[0]
        by_noext[noext] = rel
        by_base[Path(rel).stem].append(rel)

    def resolve(token: str, importer: str) -> str | None:
        token = token.strip().strip("'\"")
        if not token:
            return None
        norm = token.lstrip(".").replace(".", "/")
        cand = norm.rsplit("/", 1)[0] if token.endswith((".ts", ".js")) else norm
        # 1) a file whose path-without-ext ends with the token path
        for noext, rel in by_noext.items():
            if noext == norm or noext.endswith("/" + norm) or noext == cand:
                return rel
        # 2) relative JS import resolved against the importer's directory
        if token.startswith("."):
            base = (Path(importer).parent / token.lstrip("./")).as_posix().rsplit(".", 1)[0]
            for noext, rel in by_noext.items():
                if noext == base or noext == base + "/index":
                    return rel
        # 3) fall back to a unique basename match
        last = norm.rsplit("/", 1)[-1]
        if len(by_base.get(last, [])) == 1:
            return by_base[last][0]
        return None

    out_edges: dict[str, set] = defaultdict(set)
    in_edges: dict[str, set] = defaultdict(set)
    for rel, ext, text in files:
        for tok in _extract_imports(ext, text):
            target = resolve(tok, rel)
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
