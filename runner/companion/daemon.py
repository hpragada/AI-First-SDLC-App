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
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .guardrails import playwright_tools_for
from .runner import (
    BUILD_STATE_TOOLS,
    REVIEW_ONLY_STATE_TOOLS,
    BuildTask,
    _SpecShim,
    _WorkItemShim,
    run_build,
)

# Planning/review expose the platform-state tools (incl. ask_human) over the remote MCP; no
# filesystem/Bash (those phases reason over registered context, not a working tree).
#
# `ToolSearch` rides along because the CLI DEFERS tools out of the initial context and this is the
# only way to load them back. Granting the platform-state tools is not enough on its own: run
# 457f65e1 held all 13 in this list, yet the agent reported `ask_human` and `register_artifact`
# "not present in my available tool context" while `list_artifacts` worked in the same run. It is
# not a hole in the sandbox — ToolSearch only fetches SCHEMAS for tools already granted here.
PLAN_ALLOWED_TOOLS = [f"mcp__platform-state__{name}" for name in BUILD_STATE_TOOLS] + ["ToolSearch"]

#: What the CODE REVIEW agent gets: the same base, plus the tools only it may hold. Built
#: here rather than folded into BUILD_STATE_TOOLS so a build agent never inherits them.
REVIEW_ALLOWED_TOOLS = PLAN_ALLOWED_TOOLS + [
    f"mcp__platform-state__{name}" for name in REVIEW_ONLY_STATE_TOOLS
]


class DaemonError(Exception):
    """The companion daemon could not start or run a task."""


class TransientBackendError(DaemonError):
    """The backend answered, but with a server-side failure that is expected to pass (B8).

    A connection that never lands is an OSError and was already retried forever. A connection
    that lands on a backend whose own database blinked is an HTTP 5xx — and that was fatal.
    Observed live: the shared Postgres dropped one connection (`SSL SYSCALL error: EOF
    detected`), `/api/runner/work/` returned 500, `claim()` raised plain `DaemonError`, and the
    serve loop — which catches only OSError — let it escape and **the companion exited**. The
    developer's only symptom is a button that stops doing anything, with no obvious link to a
    momentary network blip minutes earlier. On a shared remote database that blip is normal.

    Subclasses DaemonError so existing handlers still catch it; the serve loop treats it like a
    connection failure and keeps polling with backoff."""


class RunnerRejectedError(DaemonError):
    """The app no longer accepts this machine's connection token (HTTP 401).

    The ordinary cause is deliberate: somebody pressed Disconnect on Connect Machine, which
    revokes the enrollment. That is a normal ending, not a failure — but it used to arrive as
    `DaemonError: claim work -> 401: {'detail': 'invalid or missing Runner token'}` escaping the
    serve loop and printing a Python traceback, which names an HTTP verb, a status code and a
    server field and never says the one useful thing: reconnect the machine.

    Kept apart from a plain `DaemonError` so the CLI can end on a readable sentence. The daemon
    still STOPS — retrying a revoked token forever would be worse, and reconnecting issues a new
    token this process could never pick up, so waiting would look alive while being useless."""


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
    # INHERIT the machine's environment, then overlay ours. Seven variables is not enough for a
    # Python process to start if this env ever REPLACES rather than extends the child's: on
    # Windows, without SYSTEMROOT, Winsock cannot initialise and the interpreter dies during
    # `import asyncio` with `OSError: [WinError 10106]` — before any of our code runs, and with
    # no log anywhere, because the process that would have logged it is the one that died.
    # Reproduced directly (7 vars → exit 1; + SYSTEMROOT → serves normally). Inheriting removes
    # the whole class of "the MCP server didn't come up and nobody knows why".
    # Safe to inherit freely ONLY because this config now travels in a FILE, not on the command
    # line — see `write_mcp_config`. Putting an inherited environment in `--mcp-config` JSON
    # would both bloat the command line and expose it in process listings.
    env = dict(os.environ)
    env.update({
        "RUNNER_API_URL": api_url,
        "RUNNER_TOKEN": token,
        "RUNNER_TENANT_ID": tenant_id,
        "RUNNER_RUN_ID": run_id,
        "RUNNER_PHASE": phase,
        "RUNNER_PROJECT_ID": project_id,
        "PYTHONPATH": root,
    })
    return {
        "platform-state": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "runner.companion.state_mcp"],
            "env": env,
        }
    }


def codeintel_mcp_servers(*, workspace: str, repo: str, repo_root: str | None = None) -> dict:
    """MCP config for the companion CodeIntel server, bound to a `reads_code` run's throwaway
    worktree + repo. Launches `runner.companion.codeintel_mcp` (stdio); that module adds
    `backend/` to its own path and wraps one `BuiltinCodeIntel` over the worktree, so the agent
    calls `codeintel.*` (index + the 8 read tools) without handling a path or repo it can't know."""
    root = repo_root or str(Path(__file__).resolve().parents[2])
    # INHERIT the environment, exactly like `state_mcp_servers` above — this server was shipped
    # with a hand-built 3-variable env and it silently corrupted the analysis. The engine shells
    # out to `git` for history, and with no PATH there is no `git` to find: measured on the live
    # test repo, the same index returned **commits=0** under the 3-var env and **commits=22**
    # under an inherited one. No error, no warning — just a repository that looks like it has no
    # history, feeding a gap report that then reasons from it. Whatever else a minimal env breaks
    # (SYSTEMROOT/Winsock, TEMP), it is never worth re-deriving by hand.
    env = dict(os.environ)
    env.update({
        "RUNNER_WORKSPACE": workspace,
        "RUNNER_REPO": repo,
        "PYTHONPATH": root,
    })
    return {
        "codeintel": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "runner.companion.codeintel_mcp"],
            "env": env,
        }
    }
class NoAddressError(DaemonError):
    """A phase that needs a browser was dispatched without an address to bound it to (G6a)."""


def playwright_servers(*, phase: str, base_url: str) -> dict:
    """MCP config for a browser on the PLANNING path, scoped to one origin — or `{}`.

    The keyboard journey (09d) is the one planning phase that operates a live application: eight
    WCAG criteria cannot be answered by reading a page standing still, and the only way to answer
    them is to tab through the thing. This is where it gets the browser to do that, wired exactly
    the way `codeintel_mcp_servers` wires the code-intelligence server in below it.

    **`--allowed-origins` is the whole of the bound, so a missing address raises rather than
    launching.** The build path has the same launch and writes it as `if preview_url:` — which
    means an unresolved preview URL there quietly starts a browser that may open anything. That
    is not repeated here. A journey with no address is refused twice over: `start_journey_check`
    will not dispatch one, and if a payload somehow arrives without it the run fails with a
    sentence a person can act on instead of silently getting an unbounded browser.
    """
    from .runner import _headed_enabled

    if not playwright_tools_for(phase):
        return {}
    base_url = str(base_url or "").strip().rstrip("/")
    if not base_url:
        raise NoAddressError(
            f"the {phase} phase needs a browser and was dispatched without an address for the "
            "application, so there is nothing to scope the browser to and nowhere to go. "
            "Nothing was run."
        )
    # `--headless` unless the operator asked to watch (SDLC_COMPANION_HEADED=1) — the same switch
    # the build path uses, so a journey can be watched live on an attended local run.
    args = ["-y", "@playwright/mcp@latest"]
    if not _headed_enabled():
        args.append("--headless")
    args += ["--allowed-origins", base_url]
    return {"playwright": {"type": "stdio", "command": "npx", "args": args}}


def write_mcp_config(servers: dict, *, run_id: str = "") -> str:
    """Write an MCP server config to a temp FILE and return its path, for `mcp_servers`.

    The SDK serialises a config DICT into `--mcp-config <json>` on the command line; given a str
    or Path it passes it through as a file path instead. That difference matters twice over:

    1. **The command line has a hard ceiling.** Windows caps it at ~32,767 chars, and exceeding it
       surfaces as the misleading "Claude Code not found" (Bugs row 64, where a 36KB agent body
       overflowed it — fixed then by moving the system prompt to a file). An inherited environment
       is ~6KB of JSON, and a long PATH pushes it higher: 20% of the ceiling spent on plumbing.
    2. **Command lines are world-readable.** Any user can read them from a process listing, so an
       inlined config publishes the runner token and every inherited variable. A temp file is
       readable only by the account that created it.

    Same shape the team already chose for the agent body: payload in a file, path on the command
    line. Caller deletes the file when the run ends (`_cleanup_mcp_config`).
    """
    fd, path = tempfile.mkstemp(prefix=f"mcp-{run_id[:8] or 'run'}-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"mcpServers": servers}, fh)
    return path


def _cleanup_mcp_config(path: object) -> None:
    """Remove a config written by `write_mcp_config`. Best-effort: a leftover temp file must
    never fail a run that otherwise succeeded."""
    if not isinstance(path, str) or not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


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
        if status >= 500:
            raise TransientBackendError(f"claim work -> {status}: {data}")
        if status == 401:
            raise RunnerRejectedError("this machine is no longer connected")
        if status >= 400:
            raise DaemonError(f"claim work -> {status}: {data}")   # 4xx = a real rejection
        return data

    def claim_code_intel(self) -> dict | None:
        """Claim the next dispatched code-intel job (B4), or None when idle (204). A separate
        endpoint from /work/ so the proven plan/review/build claim path is untouched."""
        status, data = self._transport(
            "GET", f"{self._base}/api/runner/code-intel/", self._headers(), None)
        if status == 204 or not data:
            return None
        if status >= 500:
            raise TransientBackendError(f"claim code-intel -> {status}: {data}")
        if status == 401:
            raise RunnerRejectedError("this machine is no longer connected")
        if status >= 400:
            raise DaemonError(f"claim code-intel -> {status}: {data}")
        # Only a real job payload (carries job_id) is work; treat anything else as idle so a
        # permissive/unexpected 200 can never be mistaken for a job to run.
        if not isinstance(data, dict) or "job_id" not in data:
            return None
        return data

    def claim_a11y_audit(self) -> dict | None:
        """Claim the next accessibility audit waiting for a machine (task 8a), or None (204).

        Its own endpoint, like code intelligence: an audit needs no engine and no work item —
        it needs a browser and an address that only this machine can reach. The proven
        plan/review/build claim path is untouched.
        """
        status, data = self._transport(
            "GET", f"{self._base}/api/runner/a11y-audits/", self._headers(), None)
        if status == 204 or not data:
            return None
        if status >= 500:
            raise TransientBackendError(f"claim a11y audit -> {status}: {data}")
        if status == 401:
            raise RunnerRejectedError("this machine is no longer connected")
        if status >= 400:
            raise DaemonError(f"claim a11y audit -> {status}: {data}")
        if not isinstance(data, dict) or "audit_id" not in data:
            return None
        return data

    def _run_a11y_audit(self, claimed: dict) -> None:
        """Visit the claimed audit's pages from the project's own folder, and close it.

        **Every refusal closes the audit with its reason rather than dropping it.** An audit
        that is claimed and then quietly abandoned looks, from the screen, exactly like one no
        machine has got to yet — and the person waiting would keep waiting. Whatever goes wrong,
        the audit ends in a state that says what happened.
        """
        # `backend/` on the path BEFORE anything downstream reaches for it. `run_baseline_audit`
        # imports `apps.a11y.capture.MAX_SCREENS` lazily — one definition of the batch bound
        # rather than a second copy here — and on this path nothing had put it there. The other
        # three callers are the two `__main__` subcommands and the engine driver factory, and
        # a companion that only ever runs audits reaches none of them: it died on the import with
        # `No module named 'apps'`. Invisible until now, because `serve` could not claim an audit
        # at all until the audit it is handed started life as `pending`.
        #
        # This call is the FOURTH, and it counts: the Connect Machine redesign deletes
        # `ensure_backend_importable()` entirely, and the spec undercounted the call sites as three
        # because this comment said "the three existing callers" while itself sitting above a
        # fourth one. A leftover bootstrap still works on any machine that has a platform checkout,
        # so it fails only on a clean machine — the exact machine the redesign is for. See
        # docs/CONNECT_MACHINE_REDESIGN_SPEC.md §2.1 for the full inventory.
        ensure_backend_importable()

        from runner.companion.a11yaudit import run_baseline_audit
        from runner.companion.state_client import RemoteStateClient

        audit_id = claimed["audit_id"]
        client = RemoteStateClient(api_url=self._base, tenant_id=self._tenant,
                                   token=self._token)

        # PREFERRED, not required. The audit only ever visits URLs; the folder exists so the
        # browser and the scanner can be resolved out of the audited project's own
        # `node_modules` — which is worth having, because the version stamped on every scan is
        # then the version that application actually ships.
        #
        # But it used to be a REFUSAL, and that made a whole class of application unauditable:
        # a Django, Rails or .NET app has no `node_modules` for anything to be resolved from,
        # so the only way to audit one was to add npm dev-dependencies to the client's own
        # repository in order to look at it. Now a missing clone falls through to the
        # companion's own pinned toolchain (`runner/package.json`) running from a scratch
        # folder, and the capture records `axe-core X.Y.Z (companion)` so no report ever
        # implies the client's version when it used ours.
        workdir, where = "", ""
        repo = str(claimed.get("repo") or "")
        if not str(claimed.get("repo_reason") or "").strip() and repo:
            try:
                workdir, where = self._resolve_repo_path(repo), f"the {repo} clone"
            except DaemonError:
                workdir = ""
        if not workdir:
            workdir = self._a11y_scratch(str(claimed.get("project_id") or ""))
            where = "this companion's own toolchain"
            print(f"[companion] a11y audit {audit_id}: no local clone of "
                  f"{repo or 'any repository for this project'}, running from {workdir}",
                  flush=True)

        # Not pre-checked here: `run_baseline_audit` runs its own preflight and, when no browser
        # can be resolved from either place, closes the audit carrying that exact reason rather
        # than the generic "the application did not respond". One authority on that answer.
        out = run_baseline_audit(client=client, project_id=claimed["project_id"],
                                 workdir=workdir, audit_id=audit_id)
        print(f"[companion] a11y audit {audit_id}: {out['posted']} screen(s) posted "
              f"from {workdir} ({where})", flush=True)

    def _close_failed_a11y_audit(self, claimed: dict, exc: BaseException) -> None:
        """Close an audit whose run raised, so the screen says what happened to it.

        Without this the audit stays `claimed` until its 15-minute lease ages out, and for those
        fifteen minutes the screen is indistinguishable from an audit no machine has reached yet
        — the person waiting has no way to tell "still starting" from "this is never coming".

        **The reason is written for the person reading the screen, not for whoever fixes it.**
        The exception is already on this machine's log, in full, one line above the call to this.
        Putting `ModuleNotFoundError("No module named 'apps'")` on an accessibility report tells
        its reader nothing they can act on and nothing they can understand.

        Best-effort by design: if the platform cannot be reached either, the lease is the
        backstop and this must not be what takes the companion down.
        """
        from runner.companion.state_client import SLOW_TIMEOUT_S, RemoteStateClient

        reason = ("The machine running this audit stopped before it could visit any pages. "
                  "Nothing here tells you anything about your application. Start a new audit.")
        try:
            # The same long allowance the ordinary close uses (`SLOW_TIMEOUT_S`). This path
            # exists to recover an audit whose run raised — and one of the ways it raised was
            # the ordinary close timing out, so a recovery on the short default would time out
            # in the same place and report a healthy audit as unrecoverable as well as failed.
            RemoteStateClient(api_url=self._base, tenant_id=self._tenant, token=self._token).call(
                "finish_a11y_audit", _timeout=SLOW_TIMEOUT_S,
                audit_id=claimed["audit_id"], reason=reason)
        except Exception as close_exc:  # noqa: BLE001 — the lease is the backstop
            print(f"[companion] a11y audit {claimed.get('audit_id')} could not be closed "
                  f"({close_exc!r}); its claim will age out instead. Original: {exc!r}",
                  file=sys.stderr, flush=True)

    def _a11y_scratch(self, project_id: str) -> str:
        """A folder to run an audit from when this machine has no clone of the project.

        Under the companion's worktree root when it has one — the operator already chose that
        location and it is already on a disk they expect us to use — and beside the user's
        profile otherwise. Per project, because two audits of two applications must not fight
        over one `test-results/a11y-candidates.json`.
        """
        from pathlib import Path as _Path

        root = _Path(self._worktrees_root) if getattr(self, "_worktrees_root", "") else _Path.home() / ".sdlc"
        path = root / "a11y-audit" / (project_id or "unknown")
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    # Transient-outage policy (Bugs S.No 105): a backend/worker restart drops the HTTP
    # connection mid-poll; that surfaces as an OSError (URLError / ConnectionError / timeout),
    # NOT as an HTTP status. Those must be retried with backoff, never treated as fatal —
    # otherwise the companion silently stops heartbeating/polling and every later dispatch
    # sits unclaimed until a human restarts it.
    _RETRY_MAX_DELAY = 60.0   # cap between reconnect attempts (claim keeps trying forever)
    _REPORT_RETRIES = 7       # ~2 min of backoff before a report is given up as failed

    def _report(self, path: str, report: dict) -> None:
        """POST a task result. A finished phase/build is too expensive to lose to a backend
        restart, so transient failures are retried (~2 min of backoff) before the failure is
        surfaced. Retried: a connection that never lands (OSError) and a 5xx — the platform
        answered, but out of its own database blinking, so it did NOT record the report (B8).
        Not retried: 4xx, which is a real rejection that retrying cannot fix."""
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
            if status >= 500:
                if attempt >= self._REPORT_RETRIES:
                    raise DaemonError(
                        f"report {path} failed after {attempt + 1} attempts -> {status}: {data}")
                print(f"[companion] backend error reporting {path} ({status}); "
                      f"retrying in {delay:.0f}s", file=sys.stderr, flush=True)
                self._sleep(delay)
                delay = min(delay * 2, self._RETRY_MAX_DELAY)
                continue
            if status == 401:
                raise RunnerRejectedError("this machine is no longer connected")
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
        # Collected as a DICT first and written to a file at the end, once every server this run
        # needs is known — a repo-scoped phase adds a second one (codeintel) below.
        servers = state_mcp_servers(
            api_url=self._base, tenant_id=self._tenant, token=self._token,
            run_id=run_id, phase=phase, project_id=payload.get("project_id", ""))
        # Review posts its verdict to the review endpoint (findings); planning posts its draft
        # body to the phase endpoint (becomes the artifact).
        report_path = (f"/api/runner/reviews/{run_id}/report/" if review
                       else f"/api/runner/phases/{run_id}/report/")
        runner = driver.run_review_task if review else driver.run_planning_task
        run_kwargs = dict(
            manifest=payload.get("manifest", ""), agent_spec=spec,
            allowed_tools=REVIEW_ALLOWED_TOOLS if review else PLAN_ALLOWED_TOOLS,
            work_item=work_item,
        )
        # A browser, for the one planning phase that operates a live application (09d, G6a).
        # Scoped to the address the platform sent with the task and to nothing else; a task that
        # needs a browser and carries no address is reported failed rather than run, because the
        # origin list IS the bound (see `playwright_servers`). Every other planning phase gets an
        # empty dict here and is byte-identical to before.
        if not review:
            try:
                browser = playwright_servers(
                    phase=phase, base_url=payload.get("app_base_url", ""))
            except NoAddressError as exc:
                self._report(report_path, {"status": "failed", "message": str(exc)})
                return
            if browser:
                servers.update(browser)
                run_kwargs["allowed_tools"] = (
                    PLAN_ALLOWED_TOOLS + sorted(playwright_tools_for(phase)))
        # Repo-scoped planning (catalog `reads_code`, e.g. 10_security): provision a THROWAWAY
        # git worktree of the target repo so the agent can scan real source (and run scanners).
        # `kind` stays "plan" (this is NOT the build path) — the discriminator is `repo` +
        # `reads_code` in the payload. The worktree is never committed or pushed and is torn down
        # after. If we can't provision one (no --worktrees / no clone / git error), degrade to the
        # normal no-worktree planning run so the phase still produces a document.
        scan_worktree = None
        if not review and payload.get("repo") and payload.get("reads_code"):
            scan_worktree = self._provision_scan_worktree(payload["repo"], run_id, payload)
            if scan_worktree is not None:
                run_kwargs["repo_workspace"] = scan_worktree
                # Give the agent the CodeIntel tool surface over a second MCP server bound to the
                # worktree: a `reads_code` agent queries the codebase via `codeintel.*`, not raw
                # file tools (planning has no filesystem/Bash). Only wired when a worktree exists.
                # Today that is 00c and 10_security ONLY. It is NOT 00_onboarding — that agent
                # reads code facts from 00c's registered artifacts, so it never gets a worktree
                # and never gets these tools. This comment used to name it, which is exactly the
                # kind of stale note that sends the next reader hunting for a branch that cannot
                # fire (S5-2). The catalog's `reads_code` flag is the single source of truth.
                from .codeintel_mcp import CODEINTEL_TOOL_NAMES
                servers.update(codeintel_mcp_servers(
                    workspace=str(scan_worktree), repo=payload["repo"]))
                # Added to whatever this run already has, not set over it: no phase is both
                # repo-scoped and browser-scoped today, and a future one that was would
                # otherwise silently lose its browser here.
                run_kwargs["allowed_tools"] = list(run_kwargs["allowed_tools"]) + [
                    f"mcp__codeintel__{n}" for n in CODEINTEL_TOOL_NAMES]
        # Now that the server set is final, hand it over as a FILE path — never as inline
        # command-line JSON (see `write_mcp_config` for the size ceiling and the token exposure).
        mcp = write_mcp_config(servers, run_id=run_id)
        run_kwargs["mcp_servers"] = mcp
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
            # Say so locally too. This path used to print NOTHING: the operator watching the
            # companion saw an ordinary-looking run end, and the only record of the cause was
            # the rotating engine log nobody thinks to open.
            print(f"[companion] {phase} run {run_id} failed: {exc}",
                  file=sys.stderr, flush=True)
            self._report(report_path, {"status": "failed", "message": str(exc)})
            return
        finally:
            # The MCP config file carries the runner token — remove it as soon as the run ends,
            # on every path (success, failure, or the early return above).
            _cleanup_mcp_config(mcp)
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
        """Provision a THROWAWAY git worktree of `repo` for a repo-scoped planning scan
        (10_security). Returns the worktree Path, or None to DEGRADE gracefully (no --worktrees,
        no clone, or a git error) so the phase still runs manifest-only rather than failing.

        The branch/path namespace (`sdlc-scan/<run_id>`) is disjoint from a build's
        `feature/<work_item_key>`, so a scan can never touch or reuse a build worktree; and the
        branch is never pushed, so provision always bases it on `base` and the real repo is never
        mutated (the worktree is torn down after the run)."""
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

    def _run_code_intel(self, job: dict) -> None:
        """Run the built-in analyzer for a code-intel job (B4) in a THROWAWAY read-only worktree
        of the repo, and report the computed index back. The client's source never leaves the
        machine — only the index (file/commit/hotspot counts, languages) is posted. Mirrors the
        reads_code security-scan pattern; no engine/LLM is involved, so it needs no auth check.
        Failures are reported (never left hanging), and the worktree is always torn down."""
        from pathlib import Path

        from runner.companion.worktree import provision_worktree, teardown_worktree

        job_id = job["job_id"]
        repo = job["repo"]
        base = job.get("base", "main")
        report_path = f"/api/runner/code-intel/{job_id}/report/"
        if not self._worktrees_root:
            self._report(report_path,
                         {"status": "failed", "error": "no --worktrees configured for code-intel"})
            return
        try:
            repo_path = self._resolve_repo_path(repo)
        except DaemonError as exc:
            self._report(report_path, {"status": "failed", "error": str(exc)})
            return

        worktree = None
        try:
            worktree = provision_worktree(
                repo_path=repo_path, branch=f"sdlc-codeintel/{job_id}", base=base,
                worktree_path=Path(self._worktrees_root) / f"codeintel-{job_id}")
            # The built-in analyzer runs companion-side (D2) — pure analysis, persists nothing.
            from integrations.codeintel.builtin import BuiltinCodeIntel

            analyzer = BuiltinCodeIntel()
            idx = analyzer.index(workspace=str(worktree), repo=repo)
            # Report the analyzer's real depth, not just counts (B4 enrichment): the overview
            # (architecture communities, most-depended-on modules, top hotspots), dead code, and
            # decision archaeology — so the persisted artifact shows how deep the analysis went.
            overview = analyzer.get_overview(repo=repo)
            index = {
                "file_count": idx.file_count, "commits": idx.commits, "hotspots": idx.hotspots,
                "languages": idx.languages, "indexed_at": idx.indexed_at,
                "authors": overview.get("authors"),
                "communities": overview.get("communities"),
                "entry_points": (overview.get("entry_points") or [])[:20],
                "top_modules": overview.get("top_modules") or [],
                "hotspot_files": overview.get("hotspots") or [],
                "dead_code": analyzer.get_dead_code(repo=repo)[:50],
                "decisions": analyzer.get_why(repo=repo)[:20],
            }
            summary = (f"{repo}: {idx.file_count} files, {idx.commits} commits, "
                       f"{overview.get('communities', 0)} modules, {idx.hotspots} risk hotspots.")
            self._report(report_path, {"status": "ok", "index": index, "summary": summary})
        except DaemonError:
            raise   # a failed REPORT (backend problem) bubbles to serve(); it logs + keeps serving
        except Exception as exc:  # noqa: BLE001 — provision/analysis failure: report it, move on
            self._report(report_path, {"status": "failed", "error": str(exc)})
        finally:
            if worktree is not None:
                try:
                    teardown_worktree(repo_path=repo_path, worktree_path=worktree)
                except Exception:  # noqa: BLE001 — teardown must never mask the result
                    pass

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
                except (OSError, TransientBackendError) as exc:
                    # Backend restarting/unreachable (S.No 105) or answering 5xx because its own
                    # database blinked (B8): keep polling with capped backoff until it returns —
                    # NEVER exit the loop on a failure that is expected to pass.
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
                    # No agent-run work — check for a code-intel job (B4) before idling.
                    try:
                        job = self.claim_code_intel()
                    except (OSError, TransientBackendError):
                        job = None   # transient; the main-claim backoff handles reconnect
                    if job is not None:
                        try:
                            self._run_code_intel(job)
                            processed += 1
                        except DaemonError as exc:
                            print(f"[companion] code-intel job {job.get('job_id')} failed, "
                                  f"continuing: {exc}", file=sys.stderr, flush=True)
                        continue
                    # ...then for an accessibility audit (task 8a). Same place, same rules: a
                    # failed audit must never take the companion down, because every later
                    # dispatch would then sit unclaimed.
                    try:
                        audit = self.claim_a11y_audit()
                    except (OSError, TransientBackendError):
                        audit = None
                    if audit is not None:
                        try:
                            self._run_a11y_audit(audit)
                            processed += 1
                        # `Exception`, not `DaemonError`. The comment above has always said a
                        # failed audit must never take the companion down, but only the tidy
                        # failure was caught — and the one that actually happened was a
                        # ModuleNotFoundError, which walked straight past this and killed the
                        # process. The two costs are not comparable: an audit that dies is one
                        # audit, said on the screen with its reason; a companion that dies is
                        # every later dispatch sitting unclaimed, and from the app it looks
                        # identical to a machine nobody has got to yet.
                        except Exception as exc:  # noqa: BLE001 — see above
                            print(f"[companion] a11y audit {audit.get('audit_id')} failed, "
                                  f"continuing: {exc!r}", file=sys.stderr, flush=True)
                            self._close_failed_a11y_audit(audit, exc)
                        continue
                    self._sleep(self._poll_interval)
                    continue
                try:
                    self.run_task(task)
                    processed += 1
                except EngineAuthError:
                    raise   # fail-closed: an auth problem must always halt the daemon
                except RunnerRejectedError:
                    # Disconnected mid-task. "Keep serving" is right for a task that failed on
                    # its own, but here every later claim and report would fail the same way, so
                    # continuing would print the same rejection forever instead of stopping once
                    # and saying how to reconnect.
                    raise
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
