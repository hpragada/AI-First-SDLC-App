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
from dataclasses import dataclass, field
from pathlib import Path

from .worktree import changed_files, provision_worktree, teardown_worktree

# The build-phase platform-state tools (must match the server-side allowlist).
BUILD_STATE_TOOLS = [
    "get_context", "get_artifact", "list_artifacts", "register_artifact",
    "update_artifact", "add_trace_edge", "log_event", "list_work_items",
    "create_work_item", "transition_work_item",
]
# Filesystem + shell for editing/testing the worktree; platform-state over MCP.
# Deliberately NO CodeHost and no networked tools — the platform owns Git side-effects (D2).
BUILD_ALLOWED_TOOLS = (
    ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
    + [f"mcp__platform-state__{name}" for name in BUILD_STATE_TOOLS]
)


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
    manifest: str               # composed AGENTS.md
    agent_body: str             # the migrated agent's system prompt (07 Implementation)
    model: str = ""
    phase: str = "implementation"
    api_url: str = ""           # platform base url for remote Platform-State
    runner_token: str = ""
    secrets: dict = field(default_factory=dict)   # injected as env, never written to repo
    provisioning_commands: list = field(default_factory=list)  # toolchain/test-db setup hooks


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


def build_mcp_servers(task: BuildTask, *, repo_root: str | None = None) -> dict:
    """MCP config the agent uses: a local stdio server that proxies platform-state calls to
    the platform over HTTP (carrying the runner token; tenant resolved server-side)."""
    root = repo_root or str(Path(__file__).resolve().parents[2])
    return {
        "platform-state": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "runner.companion.state_mcp"],
            "env": {
                "RUNNER_API_URL": task.api_url,
                "RUNNER_TOKEN": task.runner_token,
                "RUNNER_TENANT_ID": task.tenant_id,
                "PYTHONPATH": root,
            },
        }
    }


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


def run_provisioning(worktree: Path, task: BuildTask) -> None:
    """Run optional toolchain/test-DB setup commands inside the worktree (a documented hook;
    actual installs are environment-specific)."""
    import subprocess

    for cmd in task.provisioning_commands:
        subprocess.run(cmd, cwd=str(worktree), shell=isinstance(cmd, str), check=True)


async def run_build(task: BuildTask, *, driver, repo_path, worktrees_root,
                    keep_worktree: bool = False) -> dict:
    """Provision → environment → run the build agent in the worktree → collect → teardown."""
    branch = f"feature/{task.work_item_key}"
    worktree = provision_worktree(
        repo_path=repo_path, branch=branch, base=task.base,
        worktree_path=Path(worktrees_root) / task.work_item_key,
    )
    try:
        run_provisioning(worktree, task)
        with inject_environment(task):
            result = await driver.run_build_task(
                manifest=task.manifest,
                agent_spec=_SpecShim(task.model, task.phase, task.work_item_key),
                repo_workspace=worktree,
                mcp_servers=build_mcp_servers(task),
                allowed_tools=BUILD_ALLOWED_TOOLS,
                work_item=_WorkItemShim(task.work_item_id, task.work_item_key),
            )
        return {
            "run_id": task.run_id, "branch": branch, "worktree": str(worktree),
            "changed_files": changed_files(worktree),
            "cost_usd": getattr(result, "cost_usd", 0.0),
            "outputs": getattr(result, "outputs", {}),
        }
    finally:
        if not keep_worktree:
            teardown_worktree(repo_path=repo_path, worktree_path=worktree)
