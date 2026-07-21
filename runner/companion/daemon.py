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
import threading
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


class EngineAuthError(DaemonError):
    """Subscription-only auth could not be guaranteed (fail-closed). Subclasses DaemonError so
    existing callers/tests still catch it, but the serve loop re-raises it rather than treating
    it as a per-task failure — an auth problem must always halt the daemon, never be skipped."""


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
        repo_path: str | None = None, repo_paths: dict | None = None,
        worktrees_root: str | None = None,
        poll_interval: float = 5.0, heartbeat_interval: float = 30.0,
        transport: Callable[..., tuple[int, object]] | None = None,
        driver_factory: Callable[[str], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = api_url.rstrip("/")
        self._tenant = tenant_id
        self._token = token
        self._repo_path = repo_path
        # {repo "owner/name": local clone path} for multi-repo routing. The single --repo-path
        # shorthand is kept as an unnamed fallback (used only when exactly one clone is known and
        # the task's repo isn't explicitly mapped — see _resolve_repo_path).
        self._repo_paths = dict(repo_paths or {})
        self._worktrees_root = worktrees_root
        self._poll_interval = poll_interval
        self._heartbeat_interval = heartbeat_interval
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

    # Transient-outage policy (Bugs S.No 105): a backend/worker restart drops the HTTP
    # connection mid-poll; that surfaces as an OSError (URLError / ConnectionError / timeout),
    # NOT as an HTTP status. Those must be retried with backoff, never treated as fatal —
    # otherwise the companion silently stops heartbeating/polling and every later dispatch
    # sits unclaimed until a human restarts it.
    _RETRY_MAX_DELAY = 60.0   # cap between reconnect attempts (claim keeps trying forever)
    _REPORT_RETRIES = 7       # ~2 min of backoff before a report is given up as failed

    def _report(self, path: str, report: dict) -> None:
        """POST a task result. A finished phase/build is too expensive to lose to a backend
        restart, so transient connection errors are retried (~2 min of backoff) before the
        failure is surfaced; HTTP 4xx/5xx answers still fail immediately (the platform saw us)."""
        delay = min(self._poll_interval, self._RETRY_MAX_DELAY) or 1.0
        for attempt in range(self._REPORT_RETRIES + 1):
            try:
                status, data = self._transport(
                    "POST", f"{self._base}{path}", self._headers(), report)
            except OSError as exc:
                if attempt >= self._REPORT_RETRIES:
                    raise DaemonError(
                        f"report {path} failed after {attempt + 1} attempts "
                        f"(backend unreachable): {exc}") from exc
                print(f"[companion] backend unreachable reporting {path} ({exc}); "
                      f"retrying in {delay:.0f}s", file=sys.stderr, flush=True)
                self._sleep(delay)
                delay = min(delay * 2, self._RETRY_MAX_DELAY)
                continue
            if status >= 400:
                raise DaemonError(f"report {path} -> {status}: {data}")
            return

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
        run_kwargs = dict(
            manifest=payload.get("manifest", ""), agent_spec=spec, mcp_servers=mcp,
            allowed_tools=PLAN_ALLOWED_TOOLS, work_item=work_item,
        )
        # Repo-scoped planning (catalog `reads_code`, e.g. 10_security): provision a READ-ONLY
        # git worktree of the target repo so the agent can scan real source. `kind` stays "plan"
        # (this is NOT the build path) — the discriminator is `repo` + `reads_code` in the
        # payload. If we can't provision one (no --worktrees / no clone / git error), degrade to
        # the normal no-worktree planning run so the phase still produces a document.
        scan_worktree = None
        if not review and payload.get("repo") and payload.get("reads_code"):
            scan_worktree = self._provision_scan_worktree(payload["repo"], run_id, payload)
            if scan_worktree is not None:
                run_kwargs["repo_workspace"] = scan_worktree
        try:
            result = asyncio.run(runner(**run_kwargs))
            outputs = getattr(result, "outputs", {}) or {}
            body = outputs.get("result") or outputs.get("text") or ""
            cost = getattr(result, "cost_usd", 0.0)
            # `cost` is the engine's computed Claude-subscription-equivalent cost, reported
            # for the team's reference and surfaced in the web UI. It is NOT an API-billing
            # signal — current Claude Code reports a non-zero computed cost even on a
            # subscription, so subscription-only auth is enforced by ensure_local_engine_auth
            # (below/at startup), never inferred from this number.
            report = {"status": "ok", "body": body, "cost_usd": cost}
            # Don't swallow abnormal engine endings: the work that WAS done (MCP-registered
            # artifacts) is still reported, but the platform gets an honest message instead
            # of a silently empty phase draft (incident: run 7f67d88a previewed as blank).
            subtype = outputs.get("result_subtype") or ""
            if subtype and subtype != "success":
                report["message"] = f"engine ended abnormally ({subtype})"
            elif not body:
                report["message"] = ("engine returned no final text; the staged phase "
                                     "draft is empty")
            self._report(report_path, report)
        except Exception as exc:  # noqa: BLE001 — report the failure so the run never hangs
            self._report(report_path, {"status": "failed", "message": str(exc)})
            return
        finally:
            # Read-only scan worktree is throwaway — remove it (best-effort) whether the run
            # succeeded or failed. Its local `sdlc-scan/<run_id>` branch was never pushed.
            if scan_worktree is not None:
                from runner.companion.worktree import teardown_worktree
                try:
                    teardown_worktree(
                        repo_path=self._resolve_repo_path(payload["repo"]),
                        worktree_path=scan_worktree)
                except Exception:  # noqa: BLE001 — teardown must never mask the run result
                    pass

    def _provision_scan_worktree(self, repo: str, run_id: str, payload: dict):
        """Provision a READ-ONLY git worktree of `repo` for a repo-scoped planning scan
        (10_security). Returns the worktree Path, or None to DEGRADE gracefully (no --worktrees,
        no clone, or a git error) so the phase still runs manifest-only rather than failing.

        The branch/path namespace (`sdlc-scan/<run_id>`) is disjoint from a build's
        `feature/<work_item_key>`, so a scan can never touch or reuse a build worktree; and the
        branch is never pushed, so provision always bases it on `base` — read-only by construction."""
        from pathlib import Path

        from runner.companion.worktree import WorktreeError, provision_worktree

        if not self._worktrees_root or not (self._repo_path or self._repo_paths):
            print(f"[companion] security scan for run {run_id} has no worktree "
                  "(--worktrees / --repo(-path) not configured); scanning manifest only",
                  file=sys.stderr, flush=True)
            return None
        try:
            repo_path = self._resolve_repo_path(repo)
            return provision_worktree(
                repo_path=repo_path,
                branch=f"sdlc-scan/{run_id}",
                base=payload.get("base", "main"),
                worktree_path=Path(self._worktrees_root) / f"scan-{run_id}",
            )
        except (WorktreeError, DaemonError, OSError) as exc:
            print(f"[companion] could not provision scan worktree for run {run_id} "
                  f"({exc}); scanning manifest only", file=sys.stderr, flush=True)
            return None

    def _resolve_repo_path(self, repo: str) -> str:
        """Pick the local clone this work item's repo (`task.repo`) must build against. On a
        multi-repo project the wrong clone silently pushes code to the wrong GitHub repo, so we
        never guess: an explicit --repo mapping wins; otherwise the single --repo-path shorthand
        is used ONLY when no map was given (single-repo mode). A repo we can't resolve is a hard,
        loud failure — never a fall-back to some other repo's clone."""
        if repo in self._repo_paths:
            return self._repo_paths[repo]
        # single-repo shorthand: one clone, no explicit map → serve it.
        if self._repo_path and not self._repo_paths:
            return self._repo_path
        raise DaemonError(
            f"no local clone configured for repo {repo!r}; pass --repo {repo}=<path> "
            f"(known: {sorted(self._repo_paths) or 'none'})")

    def _run_build(self, task: dict) -> None:
        if not self._worktrees_root:
            raise DaemonError("build dispatched but --worktrees not configured")
        if not (self._repo_path or self._repo_paths):
            raise DaemonError(
                "build dispatched but no repo clone configured (pass --repo-path for single-repo "
                "or one or more --repo NAME=PATH for multi-repo)")
        from runner.companion.runner import to_build_report
        from runner.companion.worktree import WorktreeError

        payload = dict(task["payload"])
        payload.setdefault("runner_token", self._token)
        build_task = BuildTask(**{k: payload[k] for k in payload
                                  if k in BuildTask.__dataclass_fields__})
        repo_path = self._resolve_repo_path(build_task.repo)
        driver = self._driver_factory(build_task.agent_body)
        report_path = f"/api/runner/builds/{task['run_id']}/report/"
        try:
            result = asyncio.run(run_build(
                build_task, driver=driver, repo_path=repo_path,
                worktrees_root=self._worktrees_root))
        except WorktreeError as exc:
            # e.g. the clone's origin doesn't match the routed repo (mis-mapped --repo). Fail
            # THIS build loudly on the platform, but keep the daemon serving other work items.
            self._report(report_path, {"status": "failed", "message": str(exc)})
            return
        except EngineAuthError:
            # Fail-closed: a subscription/API-key problem surfaced mid-run must ALWAYS halt the
            # daemon, never be downgraded to a per-build failed report (mirrors the serve loop).
            raise
        except Exception as exc:  # noqa: BLE001
            # Bugs S.No 133: a build-agent error must fail THIS build and be reported back, not
            # crash the whole long-lived companion (which stopped polling and left the run
            # dangling). Mirror the phase path (_run_engine_phase) — report failed, keep serving.
            self._report(report_path, {"status": "failed", "message": str(exc)})
            return
        self._report(report_path, to_build_report(result))

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

    # ── liveness heartbeat (RC-2) ──────────────────────────────────
    def _heartbeat_once(self) -> None:
        """Touch last_seen so the platform keeps this companion 'online' even while the serve
        loop is blocked running a phase (it isn't polling /work/ then). Best-effort: a failed
        ping must never crash the daemon — the next tick retries."""
        try:
            self._transport("POST", f"{self._base}/api/runner/heartbeat/", self._headers(), {})
        except Exception:  # noqa: BLE001 — liveness is best-effort, never fatal
            pass

    def _run_heartbeat_loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            self._heartbeat_once()
            stop.wait(self._heartbeat_interval)

    # ── the loop ───────────────────────────────────────────────────
    def serve(self, *, max_iterations: int | None = None) -> int:
        """Claim → run → report, sleeping when idle. Runs forever unless `max_iterations`
        is set (tests). Returns the number of tasks processed. A background heartbeat thread
        keeps the companion 'online' throughout a long phase, when the loop is busy in
        run_task and not polling (RC-2)."""
        ensure_local_engine_auth()
        stop = threading.Event()
        if self._heartbeat_interval and self._heartbeat_interval > 0:
            threading.Thread(
                target=self._run_heartbeat_loop, args=(stop,), daemon=True).start()
        try:
            processed = 0
            iterations = 0
            reconnect_delay = 0.0  # 0 ⇒ connected; grows while the backend is unreachable
            while max_iterations is None or iterations < max_iterations:
                iterations += 1
                try:
                    task = self.claim()
                except OSError as exc:
                    # Backend restarting/unreachable (S.No 105): keep polling with capped
                    # backoff until it returns — NEVER exit the loop on a connection error.
                    # (The heartbeat thread already swallows its own failures and resumes.)
                    reconnect_delay = (min(reconnect_delay * 2, self._RETRY_MAX_DELAY)
                                       if reconnect_delay else
                                       min(self._poll_interval, self._RETRY_MAX_DELAY) or 1.0)
                    print(f"[companion] backend unreachable ({exc}); "
                          f"reconnecting in {reconnect_delay:.0f}s",
                          file=sys.stderr, flush=True)
                    self._sleep(reconnect_delay)
                    continue
                if reconnect_delay:
                    print("[companion] backend reconnected; resuming",
                          file=sys.stderr, flush=True)
                    reconnect_delay = 0.0
                if task is None:
                    self._sleep(self._poll_interval)
                    continue
                try:
                    self.run_task(task)
                    processed += 1
                except EngineAuthError:
                    raise   # fail-closed: an auth problem must always halt the daemon
                except DaemonError as exc:
                    # A failed run/report for ONE task must not take down the whole companion
                    # — otherwise the user sees it drop offline and every later phase stalls.
                    # The platform already owns the run's state; log and keep serving.
                    print(f"[companion] task {task.get('run_id')} failed, continuing: {exc}",
                          file=sys.stderr, flush=True)
            return processed
        finally:
            stop.set()


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
        raise EngineAuthError(
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
            raise EngineAuthError(
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
        raise EngineAuthError(
            "no Claude subscription login found (~/.claude/.credentials.json has no OAuth "
            "token). Refusing to run rather than fall back to an API key — log in with "
            "your subscription first: claude /login  (or set CLAUDE_CODE_OAUTH_TOKEN from "
            "`claude setup-token`)"
        )


# NOTE: subscription-only auth is enforced solely by ensure_local_engine_auth() (env,
# ~/.claude.json, and OAuth credential checks, fail-closed before every task). The daemon no
# longer halts on a non-zero engine cost: current Claude Code reports a computed
# subscription-equivalent cost even when correctly billing the subscription (a real
# subscription is not metered per-token), so cost is NOT a usable API-key signal. That
# computed figure is reported to the platform and shown in the web UI for the team's
# reference only.
