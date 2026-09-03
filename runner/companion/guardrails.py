"""Injection guardrails v1 (Phase-2 §6, decision D3) — runs on the companion (dev machine).

Three defenses for a **developer-trusted** runner (full gVisor/Firecracker sandboxing is P5):

1. **Secret scanning** — before the branch is pushed, scan the worktree's changed files for
   credentials (known key formats + Shannon entropy). A hit **blocks the push/PR** (PG14):
   secrets never reach GitHub. Values are redacted in findings — never logged in full.
   The entropy half only ever scores a **string literal**: quoted anywhere, or unquoted in a
   config file / a comment. An unquoted value in source code is an expression, not a credential
   (`_scans_bare_values`) — the distinction the four earlier false-positive fixes each guessed at.
2. **Egress allowlist** — build-step network targets are restricted to approved hosts (the
   tenant's GitHub, the platform, the Anthropic API, declared registries). A denial raises.
3. **Per-phase tool allowlist (PG12)** — the build phase gets only filesystem/Bash + the
   remote Platform-State tools; **no CodeHost, no arbitrary network**. A stray tool raises.

Stdlib only (the dev machine has no Django/DB); the platform records the Event when the
companion reports the block back.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .worktree import changed_files


class SecretLeakError(Exception):
    """A secret was found in the worktree — the push/PR is blocked (PG14)."""


class EgressDenied(Exception):
    """A build step targeted a host outside the egress allowlist (PG14)."""


class AllowlistViolation(Exception):
    """The build run was handed a tool outside the per-phase allowlist (PG12)."""


# ── secret scanning ─────────────────────────────────────────────────
@dataclass(frozen=True)
class SecretFinding:
    kind: str
    path: str
    line: int
    preview: str   # redacted — never the full secret value


# Known credential formats (prefix/shape based — high precision).
_PATTERNS = [
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[0-9A-Za-z_\-]{8,}\.eyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}")),
]
# Generic "<keyword> = <value>" where the value looks high-entropy (catches custom secrets).
#
# There are TWO of these because a credential and a piece of code look identical to a regex once
# the quotes are optional — which is what the single original pattern allowed, and what every
# false positive this scanner has ever produced came down to (see `_scans_bare_values`).
_KEYWORD = r"""(?:secret|token|password|passwd|pwd|api[_-]?key|access[_-]?key
                |client[_-]?secret|private[_-]?key|auth[_-]?token)"""
_VALUE = r"""([A-Za-z0-9/+_\-.]{16,})"""
#: `secret = "…"` / `secret: '…'` / `` secret: `…` `` — a string LITERAL. A hardcoded credential
#: is always one of these, in every language, so this pattern runs on every file.
_ASSIGNMENT_QUOTED = re.compile(
    r"(?i)" + _KEYWORD + r"""\s*[:=]\s*(?P<q>['"`])""" + _VALUE + r"(?P=q)", re.VERBOSE,
)
#: `SECRET=…` with no quotes — a literal only in a config file. See `_scans_bare_values`.
_ASSIGNMENT_BARE = re.compile(r"(?i)" + _KEYWORD + r"\s*[:=]\s*" + _VALUE, re.VERBOSE)
_ENTROPY_MIN = 3.5
_ENTROPY_LEN_MIN = 20
# Obvious non-secrets that trip the entropy heuristic — don't cry wolf on placeholders. The
# `change[-_ ]?me` / `replace[-_ ]?me` alternatives cover the very common hyphenated env-template
# convention (e.g. `change-me-minimum-32-characters-long`) that a bare `changeme` token missed.
_PLACEHOLDERS = re.compile(
    r"(?i)(?:x{8,}|0{8,}|your[_-]|example|placeholder|change[-_ ]?me|replace[-_ ]?me"
    r"|to[-_ ]?be[-_ ]?(?:changed|set|replaced|filled|generated)|secret[-_ ]?(?:here|goes)"
    r"|dummy|sample|redacted|<[^>]+>|\$\{?[A-Za-z_]+\}?"
    r"|os\.environ|getenv|process\.env)"
)
# An unquoted *dotted identifier* on the RHS is code, not a credential — an attribute/name
# reference like `self.refresh_token_expiry` or `settings.access_token_lifetime`. Because
# `_ASSIGNMENT` admits `.` in the value, a long snake_case attribute chain after a `token`/`secret`
# keyword otherwise trips the entropy heuristic (Bugs S.No 151: `self.…` on auth_service.py).
_DOTTED_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")


def _looks_encoded(seg: str) -> bool:
    """A base64/hex-ish blob rather than a word — digit-dense, or many intra-word case flips with
    digits present. Snake_case identifiers (`refresh_token_expiry`) are lowercase words with no
    digits, so they read as NOT encoded; a token segment (`eyJhbGciOiJIUzI1NiJ9`) reads as encoded."""
    if not seg:
        return False
    digits = sum(c.isdigit() for c in seg)
    if digits / len(seg) >= 0.2:
        return True
    case_flips = sum(
        1 for a, b in zip(seg, seg[1:])
        if a.isalpha() and b.isalpha() and a.islower() != b.islower()
    )
    return case_flips >= 3 and digits >= 1


#: A plain identifier — no dots. `isClosingBracketToken`, `refresh_token_expiry`.
_BARE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: camelCase / PascalCase / snake_case word boundaries, so an identifier can be read as the
#: words it is made of. `isClosingBracketToken` -> is · Closing · Bracket · Token.
_WORD_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|[0-9]+")
_MIN_WORDS = 2


def _reads_as_words(value: str) -> bool:
    """True when the value decomposes into two or more real words — how a programmer names a
    thing, and not how a credential looks.

    This is the distinction that matters: `isClosingBracketToken` is four words, while
    `abcdefghijklmnopqrst` is one long run of letters and stays flagged. A generated secret has
    no word structure, so requiring two words costs nothing in detection."""
    words = [part for part in _WORD_PARTS.findall(value) if part.isalpha() and len(part) >= 2]
    return len(words) >= _MIN_WORDS


def _is_code_reference(value: str) -> bool:
    """True when the RHS is a name in the source (code), not a credential literal.

    Two shapes count as code, and both must still read as words rather than as a base64/hex
    blob — so a real token is never let through by either:

    * **A dotted attribute chain** that is receiver-prefixed (`self.`/`cls.`/`this.`) or
      snake_case: `self.refresh_token_expiry` (S.No 151). A real token that merely contains a
      dot (a JWT-ish `eyJ….eyJ…`, a base64url blob) has encoded-looking segments and stays
      flagged — and JWTs are caught independently by the high-precision `_PATTERNS` anyway.
    * **A bare identifier** whose name happens to contain a keyword: `isClosingBracketToken`,
      where `_ASSIGNMENT` matched "Token" *inside* the name rather than as a field called
      "token". This is the same failure as S.No 151 with the dot removed, and it is what turned
      one `npm install` into 535 "high entropy secrets" — every one a variable name in a
      dependency. `supersecretpassword123` is NOT let through: digits make it read as encoded,
      and it is one word, not two.
    """
    if _DOTTED_IDENTIFIER.match(value):
        if not (value.startswith(("self.", "cls.", "this.")) or "_" in value):
            return False
        return not any(_looks_encoded(seg) for seg in value.split("."))
    if _BARE_IDENTIFIER.match(value):
        return not _looks_encoded(value) and _reads_as_words(value)
    return False

# Committed *template* files are meant to hold illustrative placeholders, so the generic entropy
# heuristic (which guesses at "custom" secrets) is skipped for them — a placeholder there is by
# design, not a leak. The high-precision `_PATTERNS` (AKIA…, ghp_…, PEM, JWT) STILL run, so a
# real key shape pasted into an example file is still caught.
_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".tpl")


def _is_template_file(path: str) -> bool:
    """True for committed placeholder templates (`.env.example`, `config.yaml.template`, …)."""
    name = (path or "").lower().replace("\\", "/").rsplit("/", 1)[-1]
    return (name.endswith(_TEMPLATE_SUFFIXES)
            or ".example." in name or ".sample." in name or ".template." in name)


# Test files legitimately hold mock credentials — fake JWTs, dummy tokens, sample keys used as
# fixtures. The generic entropy heuristic is skipped for them (Bugs S.No 144 class, extended to
# tests) while the high-precision `_PATTERNS` STILL run, so a REAL key shape hardcoded in a test
# (AKIA…, ghp_…, PEM, full JWT) is still blocked.
_TEST_FILE_MARKERS = (".test.", ".spec.", "_test.", "test_")
_TEST_DIR_SEGMENTS = ("/test/", "/tests/", "/__tests__/", "/__mocks__/", "/fixtures/")


def _is_test_file(path: str) -> bool:
    """True for test / fixture files (`foo.test.ts`, `test_foo.py`, anything under a tests dir,
    `conftest.py`, …), where mock credentials are expected, not leaks."""
    p = (path or "").lower().replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return (name == "conftest.py"
            or any(m in name for m in _TEST_FILE_MARKERS)
            or any(seg in ("/" + p) for seg in _TEST_DIR_SEGMENTS))


# Source files, where an unquoted right-hand side is an EXPRESSION and never a credential.
#
# This is the rule the four previous false-positive fixes were each approximating. `api_key =
# 8f3Kd9Lm2Qp7Rs4Tv6Wx1Zy0Ab5Cd` with no quotes is not valid Python, TypeScript, Java, Go or
# anything else — a hardcoded credential in code is ALWAYS a quoted string literal. So an
# unquoted value after a `secret`/`token` keyword in one of these files is a call, a variable or
# an attribute chain: `configService.getOrThrow` (the TASK-013 block), `isClosingBracketToken`
# (the 535-finding block), `self.refresh_token_expiry_seconds` (S.No 151). Scoring those for
# entropy is what produced every one of them.
#
# Config files are the mirror image — they hold no expressions, so an unquoted value there IS a
# literal and must keep being scanned (`JWT_SECRET=…` in `.env`, `ENV API_KEY=…` in a Dockerfile,
# `client_secret: …` in YAML). Anything not listed here — including extensionless files like
# `Dockerfile`, `Makefile`, `Procfile` — is treated as config, so an unknown file type fails
# TOWARD detection rather than away from it.
_CODE_SUFFIXES = frozenset({
    "py", "ts", "tsx", "js", "jsx", "mjs", "cjs", "java", "go", "rb", "cs", "php", "kt", "swift",
    "scala", "rs", "c", "cc", "cpp", "h", "hpp", "m", "dart", "vue", "svelte",
})
#: A comment line. The "unquoted means code" reasoning holds for *statements*, not for prose — a
#: real key pasted into a `# …` / `// …` note is unquoted and is still a leak, so comments in code
#: files keep the bare scan.
_COMMENT_LINE = re.compile(r"^\s*(?:#|//|/\*|\*|--|;)")


def _scans_bare_values(path: str, line: str) -> bool:
    """True when an UNQUOTED value on this line could be a credential literal — i.e. the file is
    config-shaped, or the line is a comment inside a code file."""
    suffix = (path or "").lower().replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)
    is_code = len(suffix) == 2 and suffix[1] in _CODE_SUFFIXES
    return not is_code or bool(_COMMENT_LINE.match(line))


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(
        (cnt / n) * math.log2(cnt / n)
        for cnt in (s.count(c) for c in set(s))
    )


def _redact(value: str) -> str:
    """A traceable, non-reversible preview — never the full secret."""
    if len(value) <= 8:
        return value[0] + "***"
    return f"{value[:4]}***{value[-2:]} ({len(value)} chars)"


def _candidate_value(line: str, path: str) -> str | None:
    """The one value on this line that could be a hardcoded credential, or None.

    A quoted literal always counts. An unquoted one counts only where an unquoted value can BE a
    literal — see `_scans_bare_values`. Quoted is tried first so a code file's quoted secret is
    still caught on a line that also contains an expression."""
    quoted = _ASSIGNMENT_QUOTED.search(line)
    if quoted:
        return quoted.group(2)
    if not _scans_bare_values(path, line):
        return None
    bare = _ASSIGNMENT_BARE.search(line)
    return bare.group(1) if bare else None


def scan_text(text: str, *, path: str = "") -> list[SecretFinding]:
    """Scan one blob for credentials. Pattern hits are high-precision; the entropy heuristic
    catches custom tokens while skipping obvious placeholders / env-var references."""
    findings: list[SecretFinding] = []
    seen: set[tuple[int, str]] = set()
    # In a template OR test file the entropy heuristic is skipped (placeholders / mock fixtures
    # are expected); the high-precision format patterns below still run so a real key shape is
    # never missed (Bugs S.No 144 + test-file extension).
    skip_entropy = _is_template_file(path) or _is_test_file(path)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PATTERNS:
            match = pattern.search(line)
            if match and (lineno, kind) not in seen:
                seen.add((lineno, kind))
                findings.append(SecretFinding(kind, path, lineno, _redact(match.group(0))))
        value = None if skip_entropy else _candidate_value(line, path)
        if value is not None:
            if (
                len(value) >= _ENTROPY_LEN_MIN
                and shannon_entropy(value) >= _ENTROPY_MIN
                and not _PLACEHOLDERS.search(value)
                and not _is_code_reference(value)   # attribute/name reference, not a literal (S.No 151)
                and (lineno, "high_entropy_secret") not in seen
            ):
                seen.add((lineno, "high_entropy_secret"))
                findings.append(SecretFinding("high_entropy_secret", path, lineno, _redact(value)))
    return findings


def scan_worktree(worktree_path) -> list[SecretFinding]:
    """Scan every changed file's content (new + modified) for secrets before the push (PG14).
    Reads working-tree content so secrets in brand-new untracked files are caught too."""
    worktree = Path(worktree_path)
    findings: list[SecretFinding] = []
    for rel in changed_files(worktree):
        target = worktree / rel
        if not target.is_file():
            continue
        try:
            text = target.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(scan_text(text, path=rel))
    return findings


# ── egress allowlist ────────────────────────────────────────────────
# Always-allowed hosts: the tenant's GitHub, the Anthropic API, the npm registry. The platform
# host (from the task's api_url) and any declared registries are merged in `for_task`.
#
# `registry.npmjs.org` is here because a JavaScript app under test cannot be **started** — let
# alone tested — without installing its dependencies, so registry access is already a
# precondition of every 09b build on such a project, not something accessibility introduced
# (QA-11a). Naming it means the day real network isolation lands, those builds keep working
# instead of failing for a reason nobody would connect to this list. yarn and pnpm default to
# the same host. Other ecosystems' registries (NuGet, Maven, PyPI) are deliberately NOT added:
# per-project declaration is what `extra_allowed_hosts` is for — and that path now EXISTS on the
# server (Bugs S.No 185). A project declares them as `ProjectProfile.scan.registries`, and
# `_phase_extras` merges them into the security phase's `extra_allowed_hosts` at dispatch. That
# is deliberately per-project and per-phase rather than a wider default: this list is the whole
# egress policy, and a scanner needing PyPI is not a reason for every phase of every project to
# be able to reach it.
_DEFAULT_ALLOWED = ("api.github.com", "github.com", "codeload.github.com", "api.anthropic.com",
                    "registry.npmjs.org")


def _host(url_or_host: str) -> str:
    if not url_or_host:
        return ""
    parsed = urlparse(url_or_host if "://" in url_or_host else "//" + url_or_host)
    return (parsed.hostname or "").lower()


@dataclass(frozen=True)
class EgressPolicy:
    allowed_hosts: frozenset

    @classmethod
    def for_task(cls, task) -> EgressPolicy:
        hosts = set(_DEFAULT_ALLOWED)
        platform_host = _host(getattr(task, "api_url", "") or "")
        if platform_host:
            hosts.add(platform_host)
        for extra in getattr(task, "extra_allowed_hosts", None) or []:
            host = _host(extra) or str(extra).lower()
            if host:
                hosts.add(host)
        return cls(frozenset(hosts))

    def allows(self, url_or_host: str) -> bool:
        host = _host(url_or_host)
        if not host:
            return False
        return any(host == allowed or host.endswith("." + allowed)
                   for allowed in self.allowed_hosts)

    def check(self, url: str) -> None:
        """Raise if `url` targets a host outside the allowlist (denials block the build)."""
        if not self.allows(url):
            raise EgressDenied(f"egress to {_host(url) or url!r} is not on the allowlist")


_URL_RE = re.compile(r"https?://[^\s'\"<>|]+")


def check_command_egress(command, policy: EgressPolicy) -> None:
    """Best-effort egress check on a provisioning command: any explicit URL it targets must be
    on the allowlist. (Full network isolation is the server-runner / Phase-5 story.)"""
    text = command if isinstance(command, str) else " ".join(map(str, command))
    for url in _URL_RE.findall(text):
        policy.check(url)


# ── per-phase tool allowlist (PG12) ─────────────────────────────────
# Substrings that must never appear in a build-phase tool name (CodeHost / arbitrary network).
_FORBIDDEN_TOOL_HINTS = ("codehost", "web", "fetch", "http", "curl", "network")

# The Playwright MCP browser tools 09b needs for Live Application Exploration (real-locator
# discovery, spec §4). Deliberately the locator-discovery surface only — navigation + snapshot +
# interaction, NOT network/console/evaluate inspection (not needed to find selectors, and keeps
# the exposed surface tight).
#
# Granted to two phases and no others (see `playwright_tools_for`): the test-automation BUILD,
# and the accessibility keyboard journey, which is a planning-shaped run. Every other build phase
# (07/11) and every other planning phase still gets FS/Bash + Platform-State only.
#
# **What actually bounds the browser is `--allowed-origins`, not the tool name and not
# EgressPolicy.** That is worth stating plainly because the note here used to credit EgressPolicy:
# that class gates SHELL COMMANDS on the build path (`check_command_egress`) and has no bearing
# on what a browser may open, and the planning path does not construct one at all. The origin
# list handed to the Playwright server is the whole of the bound — so a launch with no address is
# an UNBOUNDED browser, and both call sites refuse to start one (`runner.build_mcp_servers` has
# a preview URL by construction; `daemon._playwright_servers` refuses without one).
PLAYWRIGHT_MCP_TOOLS = frozenset(
    f"mcp__playwright__{name}" for name in (
        "browser_navigate", "browser_navigate_back", "browser_snapshot",
        "browser_click", "browser_hover", "browser_type", "browser_press_key",
        "browser_select_option", "browser_wait_for", "browser_take_screenshot",
        "browser_tabs", "browser_resize", "browser_close",
    )
)


#: The two phases that operate a live application, and therefore the only two that get a browser.
#:
#: `a11y_journey` (09d) is the reason this is a set rather than one string. Eight WCAG criteria
#: cannot be answered by reading a page standing still — whether tabbing ever traps you, whether
#: focus stays visible, whether a status message is announced — and the only way to answer them
#: is to operate the application. That agent runs on the planning path, so this grant is what
#: gives it the one tool its whole existence depends on.
#:
#: Repeated here rather than imported from `apps.a11y.journey.JOURNEY_PHASE`: the companion runs
#: on a developer's machine with no Django and no database, so it cannot import the backend.
#: `test_automation` is duplicated from the agent catalog the same way, and both are held honest
#: by a test that reads the catalog and asserts these are the phases it names.
BROWSER_PHASES = frozenset({"test_automation", "a11y_journey"})


def playwright_tools_for(phase: str) -> frozenset:
    """The Playwright MCP tools permitted for `phase`, empty for every phase that does not
    operate a live application. Single source of truth so the driver allowlist and the
    MCP-server wiring (`runner.build_mcp_servers`, `daemon._playwright_servers`) can never
    disagree on which phase gets a browser."""
    return PLAYWRIGHT_MCP_TOOLS if phase in BROWSER_PHASES else frozenset()


def assert_phase_allowlist(tools, *, allowed, phase: str = "") -> None:
    """PG12: the build phase gets only FS/Bash + remote Platform-State. Any tool that matches
    a CodeHost/network hint, or that is not on the canonical allowlist, is a violation.

    For the test-automation phase (09b) the curated Playwright browser tools are additionally
    permitted (`playwright_tools_for`) — the origin-bounded exception for Live Application
    Exploration. They bypass the network-hint check because they ARE the curated exception; what
    bounds them is the `--allowed-origins` list the browser is launched with, not the tool name
    and not EgressPolicy (which gates shell commands, and says nothing about a browser).
    """
    phase_extra = playwright_tools_for(phase)
    allowed_set = set(allowed) | phase_extra
    for tool in tools:
        if tool in phase_extra:
            continue        # curated phase-scoped browser tool — origin-bounded, not name-bounded
        low = tool.lower()
        if any(hint in low for hint in _FORBIDDEN_TOOL_HINTS):
            raise AllowlistViolation(f"tool {tool!r} is forbidden in the build phase (PG12)")
        if tool not in allowed_set:
            raise AllowlistViolation(f"tool {tool!r} is not on the build-phase allowlist (PG12)")
