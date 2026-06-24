"""Companion CLI: enroll a runner, or run a build task.

    python -m runner.companion enroll --api-url URL --tenant T --project P --label laptop
    python -m runner.companion run --task task.json --repo-path ~/repos/api --worktrees ~/sdlc

`enroll` calls the platform's enrollment API and prints the one-time token. `run` loads a
BuildTask JSON and drives `run_build` with the real ClaudeDriver (imported lazily so the CLI
only needs the engine SDK when actually running a build).
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
                       "repos": args.repos or []}).encode()
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
    from drivers.claude_driver import ClaudeDriver

    driver = ClaudeDriver(body_loader=lambda spec: task.agent_body)
    out = asyncio.run(run_build(
        task, driver=driver, repo_path=args.repo_path, worktrees_root=args.worktrees,
        keep_worktree=args.keep,
    ))
    print(json.dumps(out, indent=2))
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
    e.set_defaults(func=_enroll)

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
