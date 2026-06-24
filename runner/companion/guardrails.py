"""Injection guardrails v1 (Phase-2 §6, decision D3) — runs on the companion (dev machine).

Three defenses for a **developer-trusted** runner (full gVisor/Firecracker sandboxing is P5):

1. **Secret scanning** — before the branch is pushed, scan the worktree's changed files for
   credentials (known key formats + Shannon entropy). A hit **blocks the push/PR** (PG14):
   secrets never reach GitHub. Values are redacted in findings — never logged in full.
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
_ASSIGNMENT = re.compile(
    r"""(?i)(?:secret|token|password|passwd|pwd|api[_-]?key|access[_-]?key
        |client[_-]?secret|private[_-]?key|auth[_-]?token)
        \s*[:=]\s*['"]?([A-Za-z0-9/+_\-.]{16,})['"]?""",
    re.VERBOSE,
)
_ENTROPY_MIN = 3.5
_ENTROPY_LEN_MIN = 20
# Obvious non-secrets that trip the entropy heuristic — don't cry wolf on placeholders.
_PLACEHOLDERS = re.compile(
    r"(?i)(?:x{8,}|0{8,}|your[_-]|example|placeholder|changeme|<[^>]+>|\$\{?[A-Za-z_]+\}?"
    r"|os\.environ|getenv|process\.env)"
)


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


def scan_text(text: str, *, path: str = "") -> list[SecretFinding]:
    """Scan one blob for credentials. Pattern hits are high-precision; the entropy heuristic
    catches custom tokens while skipping obvious placeholders / env-var references."""
    findings: list[SecretFinding] = []
    seen: set[tuple[int, str]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PATTERNS:
            match = pattern.search(line)
            if match and (lineno, kind) not in seen:
                seen.add((lineno, kind))
                findings.append(SecretFinding(kind, path, lineno, _redact(match.group(0))))
        assignment = _ASSIGNMENT.search(line)
        if assignment:
            value = assignment.group(1)
            if (
                len(value) >= _ENTROPY_LEN_MIN
                and shannon_entropy(value) >= _ENTROPY_MIN
                and not _PLACEHOLDERS.search(value)
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
# Always-allowed hosts: the tenant's GitHub, the Anthropic API. The platform host (from the
# task's api_url) and any declared registries are merged in `for_task`.
_DEFAULT_ALLOWED = ("api.github.com", "github.com", "codeload.github.com", "api.anthropic.com")


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


def assert_phase_allowlist(tools, *, allowed) -> None:
    """PG12: the build phase gets only FS/Bash + remote Platform-State. Any tool that matches
    a CodeHost/network hint, or that is not on the canonical allowlist, is a violation."""
    allowed_set = set(allowed)
    for tool in tools:
        low = tool.lower()
        if any(hint in low for hint in _FORBIDDEN_TOOL_HINTS):
            raise AllowlistViolation(f"tool {tool!r} is forbidden in the build phase (PG12)")
        if tool not in allowed_set:
            raise AllowlistViolation(f"tool {tool!r} is not on the build-phase allowlist (PG12)")
