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
    scan_worktree,
)
from .worktree import changed_files, provision_worktree, teardown_worktree

# The build-phase platform-state tools the companion exposes to the engine. `ask_human` is
# the interactive-clarification channel (req #2) — served by dedicated runner endpoints, not
# the generic state route, but still an mcp__platform-state__ tool the engine must be allowed.
BUILD_STATE_TOOLS = [
    "get_context", "get_artifact", "list_artifacts", "register_artifact",
    "update_artifact", "add_trace_edge", "log_event", "list_work_items",
    "create_work_item", "transition_work_item", "ask_human",
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
    extra_allowed_hosts: list = field(default_factory=list)  # declared registries (egress §6)


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
                # Identify the run/phase/project this launch is bound to (the agent never
                # passes them — e.g. artifact registration fills project_id/run_id from here
                # instead of asking the user, Bugs.xlsx row 25).
                "RUNNER_RUN_ID": task.run_id,
                "RUNNER_PHASE": task.phase,
                "RUNNER_PROJECT_ID": task.project_id,
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


def run_provisioning(worktree: Path, task: BuildTask, policy: EgressPolicy) -> None:
    """Run optional toolchain/test-DB setup commands inside the worktree (a documented hook;
    actual installs are environment-specific). Each command's explicit URLs are checked against
    the egress allowlist first — a denied host blocks the build before anything runs (§6)."""
    import subprocess

    for cmd in task.provisioning_commands:
        check_command_egress(cmd, policy)
        subprocess.run(cmd, cwd=str(worktree), shell=isinstance(cmd, str), check=True)


async def run_build(task: BuildTask, *, driver, repo_path, worktrees_root,
                    keep_worktree: bool = False) -> dict:
    """Provision → environment → run the build agent in the worktree → **scan for secrets** →
    collect → teardown. Guardrails v1 (§6): the per-phase allowlist is asserted (PG12), the
    egress allowlist gates provisioning, and the changed files are secret-scanned before the
    branch is reported pushable — a hit returns `status="secret_blocked"` and nothing is pushed."""
    assert_phase_allowlist(BUILD_ALLOWED_TOOLS, allowed=BUILD_ALLOWED_TOOLS)  # PG12
    policy = EgressPolicy.for_task(task)
    branch = f"feature/{task.work_item_key}"
    worktree = provision_worktree(
        repo_path=repo_path, branch=branch, base=task.base,
        worktree_path=Path(worktrees_root) / task.work_item_key,
    )
    try:
        run_provisioning(worktree, task, policy)
        with inject_environment(task):
            result = await driver.run_build_task(
                manifest=task.manifest,
                agent_spec=_SpecShim(task.model, task.phase, task.work_item_key),
                repo_workspace=worktree,
                mcp_servers=build_mcp_servers(task),
                allowed_tools=BUILD_ALLOWED_TOOLS,
                work_item=_WorkItemShim(task.work_item_id, task.work_item_key),
            )
        files = changed_files(worktree)
        secret_findings = scan_worktree(worktree)
        out = {
            "run_id": task.run_id, "branch": branch, "worktree": str(worktree),
            "changed_files": files,
            "cost_usd": getattr(result, "cost_usd", 0.0),
            "outputs": getattr(result, "outputs", {}),
            "egress_allowed_hosts": sorted(policy.allowed_hosts),
        }
        if secret_findings:
            # PG14: block the push/PR. Report the redacted findings; the branch is never pushed.
            out["status"] = "secret_blocked"
            out["secret_findings"] = [asdict(f) for f in secret_findings]
        else:
            out["status"] = "ok"
        return out
    finally:
        if not keep_worktree:
            teardown_worktree(repo_path=repo_path, worktree_path=worktree)


def to_build_report(result: dict) -> dict:
    """Map a `run_build` result to the BuildReport payload the platform's report API consumes.
    A secret-scan block becomes a **failed** build (the saga dead-letters it → Event logged,
    WorkItem returned to in_progress, triage opened) — secrets never reach the PR."""
    if result.get("status") == "secret_blocked":
        n = len(result.get("secret_findings", []))
        return {"status": "failed", "branch": result.get("branch", ""),
                "message": f"secret scan blocked the push: {n} finding(s) — see run events"}
    return {"status": "ok", "branch": result.get("branch", ""),
            "head_sha": result.get("head_sha", ""),
            "changed_files": result.get("changed_files", [])}
