"""Companion CLI: enroll a runner, serve as a daemon, or run a single build task.

    python -m runner.companion enroll --api-url URL --tenant T --project P --label laptop
    python -m runner.companion serve  --api-url URL --tenant T --token TOK --worktrees ~/sdlc \
                                      [--repo-path ~/repos/api] [--headed]   # single-repo
    python -m runner.companion serve  --api-url URL --tenant T --token TOK --worktrees ~/sdlc \
        --repo acme/api=~/repos/api --repo acme/web=~/repos/web             # multi-repo
    python -m runner.companion run    --task task.json --repo-path ~/repos/api --worktrees ~/sdlc
    python -m runner.companion audit  --api-url URL --tenant T --token TOK --project P \
                                      [--base-url http://localhost:5173]

`enroll` returns the one-time token. `serve` is the headless background process: it claims
phases dispatched to this enrollment and runs them on the **local logged-in Claude Code**
(no API key), so the user does everything in the web app. `run` drives a single BuildTask
(kept for local/manual runs). `audit` runs a baseline accessibility pass over an app that is
already built and already running — no repository, no build, no engine (QA-17). The
ClaudeDriver is imported lazily.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request

from .runner import BuildTask, run_build


def _engine_launch_supported() -> tuple[bool, str]:
    """(ok, anyio_version): can this Python actually launch Claude Code? claude-agent-sdk starts
    the CLI via `anyio.open_process(..., user=...)`, and that `user` kwarg only exists in
    anyio >= 4.5. Returns whether the installed anyio has it, plus its version for the message."""
    import inspect

    try:
        import anyio
        from importlib.metadata import version

        return "user" in inspect.signature(anyio.open_process).parameters, version("anyio")
    except Exception as exc:  # anyio missing / unreadable — treat as unsupported
        return False, f"(unavailable: {exc})"


def _assert_engine_env() -> None:
    """Fail fast at startup — never mid-build — if the environment can't launch Claude Code
    (Bugs S.No 135). A shared/global Python can have anyio silently downgraded to 4.4.0 by another
    project's `pip install` (e.g. an app pinning anyio==4.4.0), which otherwise surfaces only when
    the first build tries to start the engine ('open_process() got an unexpected keyword argument
    user'). Catching it here turns a cryptic demo-time failure into a clear, actionable startup
    error. Run the companion from its dedicated venv so this can't happen."""
    ok, ver = _engine_launch_supported()
    if not ok:
        sys.stderr.write(
            "\n[companion] CANNOT START — this Python cannot launch Claude Code.\n"
            f"  anyio {ver} lacks open_process(user=...), which claude-agent-sdk needs (anyio>=4.5).\n"
            "  A shared/global Python often gets anyio downgraded by another project's install.\n"
            "  Fix: launch the companion from its dedicated virtualenv, e.g.\n"
            "    <sdlc-companion-venv>\\Scripts\\python.exe -m runner.companion serve ...\n"
            "  (or, in this env:  python -m pip install \"anyio>=4.5\")\n\n"
        )
        raise SystemExit(2)


def _enroll(args) -> int:
    url = args.api_url.rstrip("/") + "/api/runners/"
    body = json.dumps({"project_id": args.project, "label": args.label,
                       "repos": args.repos or [],
                       "developer_id": args.developer_id}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Tenant-ID": args.tenant},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    print(json.dumps(data, indent=2))
    print("\nStore the token securely - it is shown only once.")
    return 0


def _run(args) -> int:
    task = BuildTask(**json.loads(open(args.task, encoding="utf-8").read()))
    from .daemon import ensure_backend_importable

    ensure_backend_importable()
    from drivers.claude_driver import ClaudeDriver

    driver = ClaudeDriver(body_loader=lambda spec: task.agent_body)
    out = asyncio.run(run_build(
        task, driver=driver, repo_path=args.repo_path, worktrees_root=args.worktrees,
        keep_worktree=args.keep,
    ))
    print(json.dumps(out, indent=2))
    return 0


def _audit(args) -> int:
    """Run a baseline accessibility audit against an already-built app (QA-17).

    Needs no repository and no build: the app is already running somewhere this machine can
    reach, which is the whole difference between this and every other accessibility check the
    platform does. The routes come from the project's registered list unless named here.
    """
    from .daemon import ensure_backend_importable

    # The capture parser lives in `backend/` and is the platform's single definition of the
    # format — the same lazy import discipline `a11ycapture` follows.
    ensure_backend_importable()
    from .a11yaudit import run_baseline_audit
    from .state_client import RemoteStateClient

    client = RemoteStateClient(api_url=args.api_url, tenant_id=args.tenant, token=args.token)
    out = run_baseline_audit(
        client=client, project_id=args.project, base_url=args.base_url,
        workdir=args.workdir or os.getcwd(), routes=args.route or None, node=args.node,
    )
    print(json.dumps(out, indent=2))
    # A pass that captured nothing is a failure of the audit, not a clean application — exit
    # non-zero so a script that ran this cannot read silence as success.
    return 0 if out["posted"] else 1


def _parse_repo_map(pairs) -> dict:
    """Turn repeated `--repo owner/name=/abs/clone` values into an {name: path} map. On a
    multi-repo project each work item is assigned a repo (`task.repo`), so the companion needs
    one local clone per repo — a single `--repo-path` can only ever serve one of them."""
    repo_paths: dict[str, str] = {}
    for pair in pairs or []:
        name, sep, path = pair.partition("=")
        if not sep or not name.strip() or not path.strip():
            raise SystemExit(f"--repo expects NAME=PATH (e.g. owner/name=/path/to/clone), got: {pair!r}")
        repo_paths[name.strip()] = path.strip()
    return repo_paths


def _serve(args) -> int:
    # Imported here, not at module level, like CompanionDaemon already was: importing daemon
    # pulls the engine stack in, and `enroll` must keep working on a machine where that cannot
    # yet be imported.
    from .daemon import (
        CompanionDaemon,
        DaemonError,
        EngineAuthError,
        RunnerRejectedError,
    )

    # `--headed` is shorthand for exporting SDLC_COMPANION_HEADED=1 for this process, so it is
    # inherited by the children that matter: the Playwright MCP (drops --headless) and the agent's
    # `npx playwright test` run (its generated config keys headless off this var). Set in-process
    # so "watch this run" needs no separate shell export. An explicit env var still works too.
    if getattr(args, "headed", False):
        os.environ["SDLC_COMPANION_HEADED"] = "1"

    # Write the engine's own output to a file (Bugs S.No 146, second pass). Without this the only
    # record of an engine failure is the terminal, which is why eight of nine such builds could
    # never be diagnosed. Announce the path so the operator knows where to look — and so "check
    # the companion terminal" stops being the only answer we can give them.
    from .enginelog import setup_engine_log

    log_path = setup_engine_log(args.worktrees)
    if log_path:
        print(f"[companion] engine log: {log_path}", file=sys.stderr, flush=True)
    else:
        print("[companion] engine log could not be opened - engine output stays terminal-only",
              file=sys.stderr, flush=True)

    repo_paths = _parse_repo_map(args.repo)
    daemon = CompanionDaemon(
        api_url=args.api_url, tenant_id=args.tenant, token=args.token,
        repo_path=args.repo_path, repo_paths=repo_paths, worktrees_root=args.worktrees,
        poll_interval=args.poll_interval, heartbeat_interval=args.heartbeat_interval,
    )
    # A companion that stops must say WHY in a sentence, not with a Python traceback. Three
    # endings are possible and a stack trace was the only one anybody saw:
    #   * disconnected in the app   — normal; you asked for it. Say how to connect it back.
    #   * engine auth refused       — already written as prose; it was just buried in a trace.
    #   * anything else             — unexpected, so the detail IS the useful part; keep it,
    #                                 but on one line that reads as an ending.
    # Exit 2 throughout: this process did not keep running, and a wrapper script must be able
    # to tell that without parsing the words.
    try:
        daemon.serve()
    except RunnerRejectedError:
        print("[companion] This machine was disconnected in the SDLC app, so it can no "
              "longer pick up work.", file=sys.stderr, flush=True)
        print("[companion] To run phases on this machine again, open Connect Machine in the "
              "app and connect it.", file=sys.stderr, flush=True)
        print("[companion] Stopping.", file=sys.stderr, flush=True)
        return 2
    except EngineAuthError as exc:
        print(f"[companion] Phases cannot start on this machine: {exc}",
              file=sys.stderr, flush=True)
        print("[companion] Stopping.", file=sys.stderr, flush=True)
        return 2
    except DaemonError as exc:
        print(f"[companion] Stopping — the companion hit a problem it could not recover "
              f"from: {exc}", file=sys.stderr, flush=True)
        return 2
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="runner.companion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll")
    e.add_argument("--api-url", required=True)
    e.add_argument("--tenant", required=True)
    e.add_argument("--project", required=True)
    e.add_argument("--label", default="")
    e.add_argument("--repos", nargs="*", default=[])
    e.add_argument("--developer-id", default=None,
                   help="route this enrollment's phases to a specific platform user")
    e.set_defaults(func=_enroll)

    s = sub.add_parser("serve")
    s.add_argument("--api-url", required=True)
    s.add_argument("--tenant", required=True)
    s.add_argument("--token", required=True)
    s.add_argument("--repo-path", default=None,
                   help="single-repo shorthand: the one local clone builds run against")
    s.add_argument("--repo", action="append", default=[], metavar="NAME=PATH",
                   help="multi-repo: map a repo (owner/name) to its local clone; repeat once per "
                        "repo. The build routes each work item to the clone matching its repo.")
    s.add_argument("--worktrees", default=None)
    s.add_argument("--headed", action="store_true",
                   help="attended local run: show the browser during 09b test automation (the "
                        "exploration browser AND the generated test suite run headed). Equivalent "
                        "to setting SDLC_COMPANION_HEADED=1 for this process.")
    s.add_argument("--poll-interval", type=float, default=5.0)
    s.add_argument("--heartbeat-interval", type=float, default=30.0,
                   help="seconds between liveness pings that keep the companion 'online' while "
                        "a phase runs (0 disables)")
    s.set_defaults(func=_serve)

    r = sub.add_parser("run")
    r.add_argument("--task", required=True)
    r.add_argument("--repo-path", required=True)
    r.add_argument("--worktrees", required=True)
    r.add_argument("--keep", action="store_true")
    r.set_defaults(func=_run)

    a = sub.add_parser("audit", help="baseline-audit an already-built app for accessibility")
    a.add_argument("--api-url", required=True)
    a.add_argument("--tenant", required=True)
    a.add_argument("--token", required=True)
    a.add_argument("--project", required=True)
    a.add_argument("--base-url", default="",
                   help="where the running app is reachable FROM THIS MACHINE, e.g. "
                        "http://localhost:5173 — the platform never connects to it. Optional: "
                        "left out, the platform uses the address it already holds for this "
                        "project (the repository's Preview URL, or the port it builds with) "
                        "and refuses with a readable reason if it holds none")
    a.add_argument("--route", action="append", default=[], metavar="PATH",
                   help="audit these paths instead of the project's registered routes; "
                        "repeat once per path")
    a.add_argument("--workdir", default=None,
                   help="where the capture is written (default: the current directory)")
    a.add_argument("--node", default="node", help="the Node executable to run the audit with")
    a.set_defaults(func=_audit)

    args = parser.parse_args(argv)
    # `serve`/`run` launch the engine — verify the runtime can before doing anything (S.No 135).
    # `enroll` needs no engine, so it still works even in a broken env (e.g. first-time setup).
    # `audit` drives a browser and never starts the engine, so it is exempt like `enroll`.
    if args.cmd in ("serve", "run"):
        _assert_engine_env()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
