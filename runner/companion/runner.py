"""Companion build orchestration (Phase-2 §3).

`run_build` ties the pieces together: provision a worktree → inject the run environment
(secrets as env, never written to the repo) → run the build agent via `run_build_task`
scoped to the worktree → collect the changed files → tear the worktree down. The driver is
injected (so this is testable without a live engine); the build agent gets the FS/Bash tools
+ the remote Platform-State tools, and **no CodeHost / no arbitrary network** (PG12) — the
platform performs the git side-effects (D2).
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .guardrails import (
    EgressPolicy,
    assert_phase_allowlist,
    check_command_egress,
    playwright_tools_for,
    scan_worktree,
)
from .a11ycapture import collect_a11y_candidates, post_a11y_candidates
from .a11ycapture import summarize as summarize_capture
from .testresults import collect_test_results, summarize
from .worktree import (
    assert_remote_matches,
    changed_files,
    commit_all,
    commits_ahead_of_base,
    head_sha,
    provision_worktree,
    push_branch,
    teardown_worktree,
)

# The build-phase platform-state tools the companion exposes to the engine. `ask_human` is
# the interactive-clarification channel (req #2) — served by dedicated runner endpoints, not
# the generic state route, but still an mcp__platform-state__ tool the engine must be allowed.
BUILD_STATE_TOOLS = [
    "get_context", "get_artifact", "get_artifact_body", "list_artifacts",
    "register_artifact", "stage_artifact_body",
    "update_artifact", "add_trace_edge", "log_event", "list_work_items",
    "create_work_item", "transition_work_item", "ask_human",
    # Agent-driven onboarding: 00_onboarding submits its gap report through the shape-safe writer.
    "submit_gap_report",
    # Document vision (Part B): 00e reads a document's stored page images as image blocks, and
    # its already-extracted text — which for a document whose artifact this run is creating has
    # no artifact to come from, so get_artifact_body cannot serve it.
    "get_page_images",
    "get_source_extraction",
    # Accessibility judging (QA-02a): 09c reads its dispatched elements and the exact WCAG
    # wording, and reports one validated verdict per element. Without these three granted the
    # judge can see no work, has no rulebook, and has no way to answer.
    "get_a11y_batch",
    "get_wcag_grounding",
    "record_a11y_finding",
    # QA-11b: the judge's eyes. `color` is a question about what a thing looks like, and
    # `alt` is often one too — without this the judge holds a pointer to a picture it has no
    # way to open, and correctly records `uncertain` on every element that needed seeing.
    "get_a11y_screenshots",
    # Accessibility journeys (QA-20): 09d reads the frozen step list, records what became of
    # each step, and reports up to eight verdicts per step. These ARE granted to the engine —
    # unlike the capture tools below — because a journey result is a judgement about what
    # happened while operating the application, which is the agent's to make and nobody
    # else's. The step list it reports against is the platform's, frozen before it started,
    # so an agent cannot widen or narrow its own contract.
    "get_a11y_journey",
    "record_a11y_journey_step",
    "record_a11y_journey_finding",
    "finish_a11y_journey",
]
#: Granted to the CODE REVIEW agent and to nothing else. Every other list here is shared by every
#: phase, which is why this one is separate: 08 is the only agent with any business reading a
#: repository's files, and the whole point of splitting the list is that a tool added for one
#: agent does not quietly become a capability for all of them. A planning agent that could read
#: arbitrary repository files would be a wider sandbox than PG12 describes.
REVIEW_ONLY_STATE_TOOLS = ["get_pr_file"]

# NOT in the list above, deliberately: `ingest_a11y_candidates`, and QA-17's `start_a11y_audit`
# / `ingest_a11y_audit_screen` / `finish_a11y_audit`. The COMPANION posts the capture (see
# `run_build` and `a11yaudit`), not the agent — the file is machine truth from a real visit to
# the application, and an agent able to write candidate bundles could describe a page instead of
# one having been captured. They are allowed on the platform's build-state route, which is what
# the companion calls; they are never granted to the engine.
# Filesystem + shell for editing/testing the worktree; platform-state over MCP.
# Deliberately NO CodeHost and no networked tools — the platform owns Git side-effects (D2).
BUILD_ALLOWED_TOOLS = (
    # `ToolSearch` loads tools the CLI deferred out of the initial context — without it, granting
    # a tool is no guarantee the agent can see it (see `daemon.PLAN_ALLOWED_TOOLS`). It fetches
    # SCHEMAS only, for tools already granted below, so PG12's bound is unchanged.
    ["Read", "Write", "Edit", "Bash", "Glob", "Grep", "ToolSearch"]
    + [f"mcp__platform-state__{name}" for name in BUILD_STATE_TOOLS]
)


def allowed_tools_for(phase: str) -> list[str]:
    """The tools handed to the driver for a build of `phase`: the canonical build set, plus the
    curated Playwright browser tools for the test-automation phase (09b Live Application
    Exploration, spec §4). Keyed off the same `playwright_tools_for` the allowlist assertion uses,
    so what 09b is GIVEN and what PG12 PERMITS can never drift."""
    return [*BUILD_ALLOWED_TOOLS, *sorted(playwright_tools_for(phase))]


@dataclass
class BuildTask:
    """Everything the platform sends the companion for one build run. Self-contained — the
    dev machine has no Django/DB, so the agent body + composed manifest travel in the task."""

    run_id: str
    tenant_id: str
    project_id: str
    work_item_id: str
    work_item_key: str          # used for the branch name + run prompt
    repo: str                   # "owner/name"
    base: str                   # base branch the worktree forks from
    manifest: str               # composed run manifest (delivered in the system prompt)
    agent_body: str             # the migrated agent's role body (07 Implementation)
    model: str = ""
    phase: str = "implementation"
    work_item_title: str = ""   # for the derived Conventional-Commit subject
    work_item_type: str = ""    # epic/story/task/defect — maps to the commit type
    api_url: str = ""           # platform base url for remote Platform-State
    runner_token: str = ""
    secrets: dict = field(default_factory=dict)   # injected as env, never written to repo
    provisioning_commands: list = field(default_factory=list)  # toolchain/test-db setup hooks
    extra_allowed_hosts: list = field(default_factory=list)  # declared registries (egress §6)
    # Preview-start config for a test-automation build (D7 / P3-09bR): how to bring the app up
    # from the worktree so Live App Exploration has a live target. Resolved platform-side
    # (repo-first → profile) and shipped here; only carried for the test_automation phase.
    # {command, port, health_path, ready_timeout_s, ready_log}. Empty for a 09b build ⇒ fail loud.
    preview_start: dict = field(default_factory=dict)
    # Manual preview URL — an already-running app to explore (a local dev server or staging the
    # user keeps up). When set it WINS over preview_start: the companion uses this URL directly and
    # starts nothing. Blank ⇒ fall back to auto-start (preview_start). One URL per repo (P3-09bR).
    preview_url: str = ""


@dataclass
class _SpecShim:
    """A duck-typed AgentSpec for the driver (no Django on the dev machine)."""

    recommended_model: str
    phase_label: str
    key: str
    body_ref: str = ""


@dataclass
class _WorkItemShim:
    id: str
    feature_stream: str


def _headed_enabled() -> bool:
    """True when the operator asked for an attended, visible-browser local run
    (SDLC_COMPANION_HEADED=1). Drives both the exploration browser (Playwright MCP `--headless`)
    and the generated test config, so the whole 09b flow is watchable end to end. Default off —
    a dispatched run is normally unattended."""
    return os.environ.get("SDLC_COMPANION_HEADED", "").strip().lower() in {"1", "true", "yes", "on"}


def build_mcp_servers(task: BuildTask, *, repo_root: str | None = None,
                      preview_url: str = "") -> dict:
    """MCP config the agent uses: a local stdio server that proxies platform-state calls to
    the platform over HTTP (carrying the runner token; tenant resolved server-side).

    For the **test-automation phase** (09b) a second stdio server — Playwright MCP — is added so
    Live Application Exploration can navigate the live app and discover real locators (spec §4).
    It is phase-scoped (07/11 builds never launch a browser) and headless. When a `preview_url` is
    known (bring-up resolved the port), the browser is **origin-scoped to that preview host** via
    `--allowed-origins` — the tightest posture consistent with D2 (the browser can reach the app
    under test, nothing else). The 09b body hard-halts Step 4 when these tools are absent."""
    root = repo_root or str(Path(__file__).resolve().parents[2])
    # Inherit the machine's environment, then overlay ours — same reasoning as the planning path
    # in `daemon.state_mcp_servers`: a bare seven-variable environment is not enough for Python to
    # start on Windows (no SYSTEMROOT → WinError 10106 during `import asyncio`), and the process
    # that dies is the one that would have reported it. The build path launches the identical
    # server, so it carries the identical risk.
    env = dict(os.environ)
    env.update({
        "RUNNER_API_URL": task.api_url,
        "RUNNER_TOKEN": task.runner_token,
        "RUNNER_TENANT_ID": task.tenant_id,
        # Identify the run/phase/project this launch is bound to (the agent never
        # passes them — e.g. artifact registration fills project_id/run_id from here
        # instead of asking the user, Bugs.xlsx row 25).
        "RUNNER_RUN_ID": task.run_id,
        "RUNNER_PHASE": task.phase,
        "RUNNER_PROJECT_ID": task.project_id,
        "PYTHONPATH": root,
    })
    servers = {
        "platform-state": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "runner.companion.state_mcp"],
            "env": env,
        }
    }
    if playwright_tools_for(task.phase):
        # `npx @playwright/mcp` is a stdio MCP server. By default `--headless` runs without a
        # visible window — a dispatched run is normally unattended, even on a dev laptop. Set
        # SDLC_COMPANION_HEADED=1 to drop `--headless` and watch the agent drive the browser live
        # (Live Application Exploration) during an attended local run. The package + browser
        # binaries are an enrollment prerequisite (P3-09bR-6 docs); absent → Step 4's hard-halt.
        args = ["-y", "@playwright/mcp@latest"]
        if not _headed_enabled():
            args.append("--headless")
        if preview_url:
            # Scope the browser to the preview host only (semicolon-separated origin list).
            args += ["--allowed-origins", preview_url]
        servers["playwright"] = {"type": "stdio", "command": "npx", "args": args}
    return servers


# Placeholders the 09b body uses for the app under test (its Playwright examples). The composed
# manifest is the run-specific seam the companion controls post-bring-up, so the resolved preview
# URL is injected there (the body + manifest form one system prompt) — the platform supplies the
# value at run time rather than the agent guessing it (spec §4).
_BASE_URL_TOKENS = ("[base_url]", "[app_url]")


def manifest_with_preview(manifest: str, preview_url: str) -> str:
    """The composed manifest with the resolved preview URL made available to the agent: a leading
    `# Preview Environment` section plus literal substitution of the body's base-URL placeholders.
    A no-op when there is no preview URL (07/11, or a build that brought no app up)."""
    if not preview_url:
        return manifest
    for token in _BASE_URL_TOKENS:
        manifest = manifest.replace(token, preview_url)
    header = (
        "# Preview Environment\n"
        f"- Base URL: {preview_url}\n"
        "- This is the live app under test for this run. Use it wherever the role instructions "
        "reference the application base URL (e.g. Playwright navigation).\n\n"
    )
    if _headed_enabled():
        # Attended local run: the operator is watching. Make the generated Playwright config run
        # the suite with a visible browser too (the MCP exploration browser is already headed via
        # its own flag). Keyed off the env var so the SAME config still runs headless when this
        # run is later executed unattended (e.g. in CI). The env var is present in the agent's
        # Bash and in `process.env` at test time because the companion process exports it.
        header += (
            "# Run visibly (headed)\n"
            "- This run is being watched live. In the Playwright config you generate "
            "(`playwright.config.ts`), set the browser to headed so the test execution is "
            "visible — use `use: { headless: !process.env.SDLC_COMPANION_HEADED }` so the SAME "
            "config still runs headless when executed unattended. Do NOT hard-code `headless: "
            "true`, and do not add `--headless` when you invoke `playwright test`.\n\n"
        )
    return header + manifest


@contextmanager
def inject_environment(task: BuildTask):
    """Inject the run's secrets as process env for the duration of the build (so the agent's
    Bash inherits them), then restore. Secrets are **never written into the repo/worktree**."""
    saved = {k: os.environ.get(k) for k in task.secrets}
    os.environ.update({k: str(v) for k, v in task.secrets.items()})
    try:
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def run_provisioning(worktree: Path, task: BuildTask, policy: EgressPolicy) -> None:
    """Run optional toolchain/test-DB setup commands inside the worktree (a documented hook;
    actual installs are environment-specific). Each command's explicit URLs are checked against
    the egress allowlist first — a denied host blocks the build before anything runs (§6)."""
    import subprocess

    for cmd in task.provisioning_commands:
        check_command_egress(cmd, policy)
        # stdin=DEVNULL: a provisioning command that pauses for input (a package manager
        # confirmation, a credential prompt) would otherwise inherit the companion's stdin and
        # block forever with no timeout. Empty input makes it fail fast and report.
        subprocess.run(cmd, cwd=str(worktree), shell=isinstance(cmd, str), check=True,
                       stdin=subprocess.DEVNULL)


class PreviewError(Exception):
    """The preview app could not be brought up for a test-automation build (D7 / P3-09bR). Raised
    to fail the build loud — a 09b run without a live target would only produce guessed locators."""


@dataclass
class PreviewHandle:
    """A running companion-local preview app: its loopback URL (the E2E target) + the process to
    tear down. `log_tail` is the captured server output, for teardown diagnostics."""

    url: str
    proc: object                       # subprocess.Popen — kept for teardown
    port: int
    log_tail: object = None            # collections.deque — drained server output


def _readiness(config: dict, port) -> tuple[str, str]:
    """The readiness signals from a preview-start config: (health_path, ready_log). Defaults to
    polling `/` when neither is declared (but a port is), so a plain dev server is detectable."""
    health_path = str(config.get("health_path") or "")
    ready_log = str(config.get("ready_log") or "")
    if not health_path and not ready_log and port:
        health_path = "/"
    return health_path, ready_log


def _http_ok(url: str) -> bool:
    """True if `url` answers with a non-5xx status. Loopback-only (the companion probing its own
    preview) — not subject to the egress allowlist, which governs the *build's* outbound calls."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=2) as resp:      # noqa: S310 — loopback only
            return resp.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500        # a 4xx means the server is up and routing
    except Exception:  # noqa: BLE001 — not up yet / connection refused
        return False


def _url_port(url: str) -> int:
    """The explicit port in a URL, or 0 if none (for the handle's diagnostics only)."""
    import urllib.parse

    try:
        return urllib.parse.urlsplit(url).port or 0
    except (ValueError, TypeError):
        return 0


def provision_preview_app(
    worktree: Path, task: BuildTask, policy: EgressPolicy) -> PreviewHandle | None:
    """Bring the project-declared app up from the worktree so 09b's Live App Exploration has a live
    target (D7). Returns a `PreviewHandle`, or `None` for any phase that needs no preview (07/11).

    Fail-loud for a test-automation build with no preview-start config — better a clear failure than
    a run that guesses locators against nothing. Waits for readiness (health endpoint OR a ready-log
    line) up to `ready_timeout_s`; a timeout or an early exit tears the process down and raises with
    the captured log tail. Never hangs."""
    import collections
    import subprocess
    import threading
    import time

    if task.phase != "test_automation":
        return None                    # no browser phase → no app to serve

    # Manual "point at a running app" URL wins: the user keeps a dev server / staging up, so use it
    # directly and start nothing. We probe it once so a stopped app fails loud (a clear message)
    # rather than the agent flailing against a dead target. A borrowed handle (proc=None) tears
    # down to a no-op.
    if task.preview_url:
        url = task.preview_url.rstrip("/")
        if not _http_ok(url):
            raise PreviewError(
                f"the configured preview URL {url} is not reachable — start the app there before "
                "running test automation (with a preview URL set, nothing is auto-started)")
        return PreviewHandle(url=url, proc=None, port=_url_port(url), log_tail=None)

    config = task.preview_start or {}
    command = config.get("command")
    if not command:
        raise PreviewError(
            "no preview target for this repo — set the repo's Preview URL (point at a running app) "
            "or a preview-start command before running test automation")
    # A start command that fetches from a denied host is blocked before anything runs (§6).
    check_command_egress(command, policy)

    port = config.get("port")
    timeout_s = float(config.get("ready_timeout_s") or 120)
    health_path, ready_log = _readiness(config, port)
    url = f"http://127.0.0.1:{port}" if port else "http://127.0.0.1"

    # A new session/process-group so teardown kills the whole server tree (dev servers spawn
    # children). POSIX: start_new_session; Windows: a new process group.
    # stdin=DEVNULL — the build command must never inherit the companion's stdin (see
    # `codeintel/builtin.py::_git`): a prompt would block it indefinitely, and under an MCP
    # server an inherited stdin is the JSON-RPC channel itself.
    popen_kwargs = {"cwd": str(worktree), "shell": isinstance(command, str),
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(command, **popen_kwargs)  # noqa: S603

    log_tail: collections.deque = collections.deque(maxlen=200)

    def _drain() -> None:
        for line in iter(proc.stdout.readline, ""):
            log_tail.append(line.rstrip("\n"))
    threading.Thread(target=_drain, daemon=True).start()

    handle = PreviewHandle(url=url, proc=proc, port=int(port) if port else 0, log_tail=log_tail)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            teardown_preview_app(handle)
            raise PreviewError(
                f"preview app exited before becoming ready (code {proc.returncode}). "
                f"Last output:\n{_preview_log(log_tail)}")
        if ready_log and any(ready_log in line for line in log_tail):
            return handle
        if health_path and _http_ok(url + health_path):
            return handle
        time.sleep(0.5)
    teardown_preview_app(handle)
    checked = ", ".join(
        part for part in (f"log={ready_log}" if ready_log else "",
                          f"GET {url + health_path}" if health_path else "") if part)
    raise PreviewError(
        f"preview app did not become ready within {timeout_s:.0f}s (checked {checked}). "
        f"Last output:\n{_preview_log(log_tail)}")


def _preview_log(log_tail) -> str:
    """The captured preview-server output tail, for a failure message (bounded by the deque)."""
    return "\n".join(log_tail) if log_tail else "(no output)"


def teardown_preview_app(handle: PreviewHandle | None) -> None:
    """Stop a preview app and free its port. Best-effort and idempotent — safe to call in a
    `finally` whether the app is running, already gone, or was never started."""
    import signal

    if handle is None or handle.proc is None:
        return
    proc = handle.proc
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001 — didn't stop in time → force kill
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass        # already gone / not ours — nothing to tear down


def _commit_message(task: BuildTask) -> str:
    """The Conventional-Commit message the platform derives from the WorkItem (07 agent §Commit
    convention). `<type>(<scope>): <subject>` — a defect maps to `fix`, everything else to `feat`;
    scope is the WorkItem key, subject is its title (falling back to the key)."""
    subject = (task.work_item_title or "").strip() or task.work_item_key
    ctype = "fix" if task.work_item_type == "defect" else "feat"
    return f"{ctype}({task.work_item_key}): {subject}"


def _state_client(task: BuildTask):
    """The platform-state client the companion itself uses (not the agent's MCP proxy).

    Same endpoint, same enrollment token, tenant resolved server-side — this is the companion
    speaking for itself, to post what the suite left behind.
    """
    from runner.companion.state_client import RemoteStateClient

    return RemoteStateClient(api_url=task.api_url, tenant_id=task.tenant_id,
                             token=task.runner_token)


async def run_build(task: BuildTask, *, driver, repo_path, worktrees_root,
                    keep_worktree: bool = False, state_client=None) -> dict:
    """Provision → environment → run the build agent in the worktree → **scan for secrets** →
    collect → teardown. Guardrails v1 (§6): the per-phase allowlist is asserted (PG12), the
    egress allowlist gates provisioning, and the changed files are secret-scanned before the
    branch is reported pushable — a hit returns `status="secret_blocked"` and nothing is pushed."""
    # PG12: the tools we hand the driver must be within the phase's policy. For 09b that policy
    # includes the curated Playwright browser tools; every other phase stays FS/Bash + state only.
    allowed_tools = allowed_tools_for(task.phase)
    assert_phase_allowlist(allowed_tools, allowed=BUILD_ALLOWED_TOOLS, phase=task.phase)
    policy = EgressPolicy.for_task(task)
    branch = f"feature/{task.work_item_key}"
    worktree = provision_worktree(
        repo_path=repo_path, branch=branch, base=task.base,
        worktree_path=Path(worktrees_root) / task.work_item_key,
    )
    preview: PreviewHandle | None = None
    mcp_config = ""
    try:
        run_provisioning(worktree, task, policy)
        with inject_environment(task):
            # D7: for a test-automation build, bring the app up from the worktree FIRST so Live App
            # Exploration has a live target; the server inherits the injected secrets (started here,
            # so it keeps them even after the env context restores). None for 07/11 (no browser).
            preview = provision_preview_app(worktree, task, policy)
            preview_url = preview.url if preview else ""
            from runner.companion.daemon import write_mcp_config
            mcp_config = write_mcp_config(
                build_mcp_servers(task, preview_url=preview_url), run_id=task.run_id)
            result = await driver.run_build_task(
                # Inject the resolved preview URL into the run's prompt (R-4): the agent explores
                # THIS live app instead of a placeholder, and Playwright is origin-scoped to it.
                manifest=manifest_with_preview(task.manifest, preview_url),
                agent_spec=_SpecShim(task.model, task.phase, task.work_item_key),
                repo_workspace=worktree,
                # Config via FILE, not inline command-line JSON: an inherited environment would
                # otherwise spend ~6KB of the ~32,767-char command-line ceiling (the one that
                # produced the misleading "Claude Code not found" in Bugs row 64) and publish the
                # runner token to any process listing. See `daemon.write_mcp_config`.
                mcp_servers=mcp_config,
                allowed_tools=allowed_tools,
                work_item=_WorkItemShim(task.work_item_id, task.work_item_key),
            )
        files = changed_files(worktree)
        secret_findings = scan_worktree(worktree)
        # D4: the worktree executed the suite — collect its JUnit report BEFORE teardown below
        # (the worktree, and the report in it, are gone once the `finally` runs).
        test_results = collect_test_results(worktree)
        # QA-11b: same window, same reason — the rendered page, its screenshots and everything
        # the AI pass will ever look at exist only until the `finally` below removes the
        # worktree and stops the app. Posted straight to the platform rather than carried on
        # the build report: a screen carries a full-page PNG, and the report rides a Temporal
        # signal that is no place for megabytes of image.
        a11y_screens = collect_a11y_candidates(worktree)
        a11y_post = {"posted": 0, "failed": []}
        if a11y_screens:
            a11y_post = post_a11y_candidates(
                a11y_screens, client=state_client or _state_client(task),
                project_id=task.project_id, run_id=task.run_id,
            )
        out = {
            "run_id": task.run_id, "branch": branch, "worktree": str(worktree),
            "changed_files": files,
            "test_results": test_results,
            "test_summary": summarize(test_results),
            "a11y_summary": summarize_capture(a11y_screens),
            "a11y_posted": a11y_post["posted"],
            "a11y_failed": a11y_post["failed"],
            "preview_url": preview.url if preview else "",
            "cost_usd": getattr(result, "cost_usd", 0.0),
            "outputs": getattr(result, "outputs", {}),
            "egress_allowed_hosts": sorted(policy.allowed_hosts),
        }
        if secret_findings:
            # PG14: block the push/PR. Report the redacted findings; the branch is never pushed.
            out["status"] = "secret_blocked"
            out["secret_findings"] = [asdict(f) for f in secret_findings]
            # Surface the (already-redacted) findings on the companion terminal — otherwise a
            # secret block is invisible locally and the platform only sees a bare count.
            print(f"[companion] SECRET SCAN BLOCKED push ({len(secret_findings)} finding(s)) - "
                  f"branch NOT pushed:", file=sys.stderr)
            for line in _format_secret_findings(out["secret_findings"]):
                print(f"   {line}", file=sys.stderr)
        else:
            out["status"] = "ok"
            # G2 / D2: the platform owns Git side-effects — the companion commits the agent's
            # work to the feature branch and pushes it so the platform can open the PR against a
            # real ref. Nothing is committed/pushed when the scan blocks or the agent produced
            # no change (head_sha stays empty → the saga reports an empty build).
            if files and commit_all(worktree, _commit_message(task)) is not None:
                # Multi-repo safety: never push a work item's branch to the wrong repo's remote.
                assert_remote_matches(worktree, task.repo)
                push_branch(worktree, branch)
                out["head_sha"] = head_sha(worktree)
            elif commits_ahead_of_base(worktree, task.base) > 0:
                # No NEW change this run, but the feature branch already carries committed work a
                # prior attempt pushed (a Retry / re-dispatch onto an already-built branch). Report
                # the branch tip as head_sha so the saga opens the PR against that existing work
                # instead of failing it as an empty build. Nothing new to push — the tip is already
                # on the remote (that is why provisioning found it).
                out["head_sha"] = head_sha(worktree)
        return out
    finally:
        # The MCP config file carries the runner token — remove it on every exit path.
        from runner.companion.daemon import _cleanup_mcp_config
        _cleanup_mcp_config(mcp_config)
        teardown_preview_app(preview)      # stop the app before the worktree it runs from is gone
        if not keep_worktree:
            teardown_worktree(repo_path=repo_path, worktree_path=worktree)


_MAX_REPORTED_FINDINGS = 8
#: How many redacted findings travel to the platform as structured data. Higher than the prose cap
#: because this is what makes a block diagnosable (D6), but still bounded — the report rides a
#: Temporal signal payload. The `message` always carries the TRUE count either way.
_MAX_CARRIED_FINDINGS = 50


def _format_secret_findings(findings: list[dict], limit: int = _MAX_REPORTED_FINDINGS) -> list[str]:
    """Render redacted secret findings as `[kind] path:line — preview` lines. Uses only the
    already-redacted `preview` (never the raw value), and caps the count so the report/message
    stays bounded no matter how many the scan returns."""
    lines = []
    for f in findings[:limit]:
        loc = f"{f.get('path') or '?'}:{f.get('line') or 0}"
        preview = f.get("preview")
        lines.append(f"[{f.get('kind') or 'secret'}] {loc}" + (f" - {preview}" if preview else ""))
    extra = len(findings) - limit
    if extra > 0:
        lines.append(f"(+{extra} more)")
    return lines


def to_build_report(result: dict) -> dict:
    """Map a `run_build` result to the BuildReport payload the platform's report API consumes.
    A secret-scan block becomes a **failed** build (the saga dead-letters it → Event logged,
    WorkItem returned to in_progress, triage opened) — secrets never reach the PR. The redacted
    findings (kind + path:line + redacted preview) travel in `message` so they surface in the
    `build.failed` event reason / run console (never the raw secret value)."""
    if result.get("status") == "secret_blocked":
        findings = result.get("secret_findings", [])
        detail = "; ".join(_format_secret_findings(findings))
        # No test_results on a blocked build: nothing was pushed, so the run's suite describes
        # code that will never land. Opening defects off it would litter the board with
        # findings about a discarded branch.
        return {"status": "failed", "branch": result.get("branch", ""),
                "message": f"secret scan blocked the push: {len(findings)} finding(s): {detail}",
                # D6: the redacted findings now travel as structured data too, not just prose, so
                # the platform can persist them and seed the retry with what actually tripped.
                "secret_findings": findings[:_MAX_CARRIED_FINDINGS]}
    # How the engine ENDED, not just what it produced. The plan/review path has always checked
    # this (daemon: "engine ended abnormally (<subtype>)"); the build path dropped `outputs`
    # wholesale, so an abnormal-but-exit-0 ending (e.g. `error_max_turns`) looked like a clean
    # build. "" means no ResultMessage arrived at all — itself worth knowing.
    subtype = (result.get("outputs") or {}).get("result_subtype", "")
    return {"status": "ok", "branch": result.get("branch", ""),
            "result_subtype": subtype,
            "head_sha": result.get("head_sha", ""),
            "changed_files": result.get("changed_files", []),
            "test_results": result.get("test_results", []),
            "test_summary": result.get("test_summary", ""),
            # The capture itself was already posted straight to the platform (QA-11b); what
            # travels here is the one line saying what was taken, so the run console can show
            # that an accessibility capture happened — or that none did.
            "a11y_summary": result.get("a11y_summary", ""),
            "preview_url": result.get("preview_url", "")}
