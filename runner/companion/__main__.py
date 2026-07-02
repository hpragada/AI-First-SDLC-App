"""Companion CLI: enroll a runner, serve as a daemon, or run a single build task.

    python -m runner.companion enroll --api-url URL --tenant T --project P --label laptop
    python -m runner.companion serve  --api-url URL --tenant T --token TOK \
                                      [--repo-path ~/repos/api --worktrees ~/sdlc]
    python -m runner.companion run    --task task.json --repo-path ~/repos/api --worktrees ~/sdlc

`enroll` returns the one-time token. `serve` is the headless background process: it claims
phases dispatched to this enrollment and runs them on the **local logged-in Claude Code**
(no API key), so the user does everything in the web app. `run` drives a single BuildTask
(kept for local/manual runs). The ClaudeDriver is imported lazily.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

from .runner import BuildTask, run_build


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
    print("\nStore the token securely — it is shown only once.")
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


def _serve(args) -> int:
    from .daemon import CompanionDaemon

    daemon = CompanionDaemon(
        api_url=args.api_url, tenant_id=args.tenant, token=args.token,
        repo_path=args.repo_path, worktrees_root=args.worktrees,
        poll_interval=args.poll_interval,
    )
    daemon.serve()
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
    s.add_argument("--repo-path", default=None)
    s.add_argument("--worktrees", default=None)
    s.add_argument("--poll-interval", type=float, default=5.0)
    s.set_defaults(func=_serve)

    r = sub.add_parser("run")
    r.add_argument("--task", required=True)
    r.add_argument("--repo-path", required=True)
    r.add_argument("--worktrees", required=True)
    r.add_argument("--keep", action="store_true")
    r.set_defaults(func=_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
