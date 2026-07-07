"""Companion daemon — the headless background process that makes the platform web-only (req #1).

`serve` long-polls the platform for work dispatched to this enrollment, runs each phase
**locally on the user's own Claude Code** (their logged-in subscription — never an API key),
and reports the result back so the Temporal workflow resumes. The user never opens a
terminal: they trigger phases and answer clarifications in the web app; this process is the
bridge to the `claude` on their machine.

Three kinds of work share one seam:
  - plan / review -> run_planning_task / run_review_task -> POST /api/runner/phases/<run>/report/
  - build         -> run_build (worktree)               -> POST /api/runner/builds/<run>/report/

The HTTP transport and the engine driver are injectable so the loop is unit-testable without
a network or a real engine. Pure stdlib otherwise, so the companion stays lightweight.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .runner import BUILD_STATE_TOOLS, BuildTask, _SpecShim, _WorkItemShim, run_build

# Planning/review expose the platform-state tools (incl. ask_human) over the remote MCP; no
# filesystem/Bash (those phases reason over registered context, not a working tree).
PLAN_ALLOWED_TOOLS = [f"mcp__platform-state__{name}" for name in BUILD_STATE_TOOLS]


class DaemonError(Exception):
    """The companion daemon could not start or run a task."""


def _urllib_transport(method: str, url: str, headers: dict, body: dict | None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:  # type: ignore[attr-defined]
        raw = exc.read()
        try:
            return exc.code, (json.loads(raw) if raw else None)
        except ValueError:
            return exc.code, raw.decode("utf-8", "replace")


def state_mcp_servers(*, api_url: str, tenant_id: str, token: str, run_id: str,
                      phase: str, project_id: str = "", repo_root: str | None = None) -> dict:
    """MCP config a planning/review agent uses: the companion-side platform-state server,
    proxying to the platform over HTTP and carrying the run/phase so `ask_human` can open a
    clarification against this run. The project this launch is bound to travels too, so
    artifact registration fills project_id from here rather than asking the user for a UUID
    they can't know (Bugs.xlsx rows 25 + 53 — the planning/review seam the earlier fix missed)."""
    root = repo_root or str(Path(__file__).resolve().parents[2])
    return {
        "platform-state": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "runner.companion.state_mcp"],
            "env": {
                "RUNNER_API_URL": api_url,
                "RUNNER_TOKEN": token,
                "RUNNER_TENANT_ID": tenant_id,
                "RUNNER_RUN_ID": run_id,
                "RUNNER_PHASE": phase,
                "RUNNER_PROJECT_ID": project_id,
                "PYTHONPATH": root,
            },
        }
    }


def ensure_backend_importable() -> None:
    """Put the repo's `backend/` on sys.path so `drivers.*` resolves. The companion runs as
    `python -m runner.companion` from the repo root, which only puts the root on the path —
    the engine driver lives under `backend/`, so without this the lazy import below fails
    with ModuleNotFoundError: No module named 'drivers'."""
    backend = Path(__file__).resolve().parents[2] / "backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def _default_driver_factory(agent_body: str):
    """Build the real ClaudeDriver (imported lazily so the daemon only needs the engine SDK
    when it actually runs a phase). The body travels in the task (no DB on the dev machine)."""
    ensure_backend_importable()
    from drivers.claude_driver import ClaudeDriver

    return ClaudeDriver(body_loader=lambda spec: agent_body)


class CompanionDaemon:
    def __init__(
        self, *, api_url: str, tenant_id: str, token: str,
        repo_path: str | None = None, worktrees_root: str | None = None,
        poll_interval: float = 5.0,
        transport: Callable[..., tuple[int, object]] | None = None,
        driver_factory: Callable[[str], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = api_url.rstrip("/")
        self._tenant = tenant_id
        self._token = token
        self._repo_path = repo_path
        self._worktrees_root = worktrees_root
        self._poll_interval = poll_interval
        self._transport = transport or _urllib_transport
        self._driver_factory = driver_factory or _default_driver_factory
        self._sleep = sleep

    # ── HTTP helpers ───────────────────────────────────────────────
    def _headers(self) -> dict:
        return {
            "Authorization": f"Runner {self._token}",
            "X-Tenant-ID": self._tenant,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def claim(self) -> dict | None:
        """Claim the next dispatched task for this enrollment, or None when idle (204)."""
        status, data = self._transport(
            "GET", f"{self._base}/api/runner/work/", self._headers(), None)
        if status == 204 or not data:
            return None
        if status >= 400:
            raise DaemonError(f"claim work -> {status}: {data}")
        return data

    def _report(self, path: str, report: dict) -> None:
        status, data = self._transport("POST", f"{self._base}{path}", self._headers(), report)
        if status >= 400:
            raise DaemonError(f"report {path} -> {status}: {data}")

    # ── per-kind execution ─────────────────────────────────────────
    def _run_engine_phase(self, task: dict, *, review: bool) -> None:
        payload = task["payload"]
        run_id = task["run_id"]
        phase = payload.get("phase", "review" if review else "plan")
        spec = _SpecShim(payload.get("model", ""), phase, phase)
        work_item = _WorkItemShim(payload["work_item_id"], "")
        driver = self._driver_factory(payload.get("agent_body", ""))
        mcp = state_mcp_servers(api_url=self._base, tenant_id=self._tenant, token=self._token,
                                run_id=run_id, phase=phase,
                                project_id=payload.get("project_id", ""))
        # Review posts its verdict to the review endpoint (findings); planning posts its draft
        # body to the phase endpoint (becomes the artifact).
        report_path = (f"/api/runner/reviews/{run_id}/report/" if review
                       else f"/api/runner/phases/{run_id}/report/")
        runner = driver.run_review_task if review else driver.run_planning_task
        try:
            result = asyncio.run(runner(
                manifest=payload.get("manifest", ""), agent_spec=spec, mcp_servers=mcp,
                allowed_tools=PLAN_ALLOWED_TOOLS, work_item=work_item,
            ))
            outputs = getattr(result, "outputs", {}) or {}
            body = outputs.get("result") or outputs.get("text") or ""
            cost = getattr(result, "cost_usd", 0.0)
            self._report(report_path, {"status": "ok", "body": body, "cost_usd": cost})
        except Exception as exc:  # noqa: BLE001 — report the failure so the run never hangs
            self._report(report_path, {"status": "failed", "message": str(exc)})
            return
        # After reporting (the work isn't wasted): halt if the run billed the API.
        assert_subscription_billing(cost)

    def _run_build(self, task: dict) -> None:
        if not (self._repo_path and self._worktrees_root):
            raise DaemonError("build dispatched but --repo-path/--worktrees not configured")
        from runner.companion.runner import to_build_report

        payload = dict(task["payload"])
        payload.setdefault("runner_token", self._token)
        build_task = BuildTask(**{k: payload[k] for k in payload
                                  if k in BuildTask.__dataclass_fields__})
        driver = self._driver_factory(build_task.agent_body)
        result = asyncio.run(run_build(
            build_task, driver=driver, repo_path=self._repo_path,
            worktrees_root=self._worktrees_root))
        self._report(f"/api/runner/builds/{task['run_id']}/report/", to_build_report(result))
        # After reporting: halt if the build billed the API (subscription reports $0.00).
        assert_subscription_billing((result or {}).get("cost_usd"))

    def run_task(self, task: dict) -> None:
        # Re-assert subscription-only auth before EVERY run, not just at startup — a
        # long-lived daemon must notice a key configured after it started (fail-closed).
        ensure_local_engine_auth()
        kind = task.get("kind", "plan")
        if kind == "build":
            self._run_build(task)
        elif kind == "review":
            self._run_engine_phase(task, review=True)
        else:
            self._run_engine_phase(task, review=False)

    # ── the loop ───────────────────────────────────────────────────
    def serve(self, *, max_iterations: int | None = None) -> int:
        """Claim → run → report, sleeping when idle. Runs forever unless `max_iterations`
        is set (tests). Returns the number of tasks processed."""
        ensure_local_engine_auth()
        processed = 0
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            iterations += 1
            task = self.claim()
            if task is None:
                self._sleep(self._poll_interval)
                continue
            self.run_task(task)
            processed += 1
        return processed


def ensure_local_engine_auth(home: Path | None = None) -> None:
    """FAIL-CLOSED guarantee that the engine bills the user's **Claude Code subscription**,
    never an API key (req #1). An API key can reach the engine through THREE channels; all
    are checked and the daemon refuses to run rather than ever bill the API (incident
    2026-07-07: an expired subscription login + a key persisted in ~/.claude.json silently
    billed the API for every phase — the env scrub alone could not catch it):

      1. Process env → ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN are dropped so the engine
         subprocess can't inherit them.
      2. The CLI's own config (~/.claude.json `primaryApiKey`, or an approved
         customApiKeyResponses entry) → refuse with removal instructions; env scrubbing
         cannot override a key stored in the CLI config.
      3. No valid subscription credential at all (no OAuth token in
         ~/.claude/.credentials.json and no CLAUDE_CODE_OAUTH_TOKEN from
         `claude setup-token`) → refuse with login instructions, instead of letting the
         CLI fall back to whatever key source it can find.
    """
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    if shutil.which("claude") is None:
        raise DaemonError(
            "the 'claude' CLI is not on PATH — install Claude Code and log in "
            "(claude / claude setup-token) so phases run on your local subscription"
        )

    home = home or Path.home()
    cli_config = home / ".claude.json"
    if cli_config.is_file():
        try:
            cfg = json.loads(cli_config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cfg = {}
        if cfg.get("primaryApiKey") or (cfg.get("customApiKeyResponses") or {}).get("approved"):
            raise DaemonError(
                "Claude Code has an API key stored in ~/.claude.json (primaryApiKey / an "
                "approved API-key prompt). Phases would bill the Anthropic API instead of "
                "your subscription — refusing to run. Remove it (delete the 'primaryApiKey' "
                "and 'customApiKeyResponses' entries) and log in with your subscription: "
                "claude /login"
            )

    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return  # long-lived subscription token from `claude setup-token`
    creds = home / ".claude" / ".credentials.json"
    oauth = {}
    if creds.is_file():
        try:
            oauth = (json.loads(creds.read_text(encoding="utf-8"))
                     .get("claudeAiOauth") or {})
        except (OSError, ValueError):
            oauth = {}
    if not oauth.get("accessToken"):
        raise DaemonError(
            "no Claude subscription login found (~/.claude/.credentials.json has no OAuth "
            "token). Refusing to run rather than fall back to an API key — log in with "
            "your subscription first: claude /login  (or set CLAUDE_CODE_OAUTH_TOKEN from "
            "`claude setup-token`)"
        )


# Subscription usage reports $0.00 — a non-zero engine cost means an API key slipped
# through some channel we don't know about yet. Last line of defense: halt the daemon so
# at most ONE run can ever bill the API, and say so loudly.
def assert_subscription_billing(cost_usd: float | None) -> None:
    if cost_usd and float(cost_usd) > 0:
        raise DaemonError(
            f"the engine reported a non-zero API cost (${float(cost_usd):.4f}) — phases "
            "must bill the Claude subscription (which reports $0.00), so an API key is "
            "reaching the engine. Companion halted to stop further API spend. Check "
            "~/.claude.json (primaryApiKey), the ANTHROPIC_API_KEY env var, and log in "
            "with: claude /login"
        )
