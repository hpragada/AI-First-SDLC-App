"""BuildWorkflow payloads (Phase-2 §4). Django-free so the workflow sandbox can import
them without the ORM (same rule as `types.py`)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuildInput:
    """One build run = one BuildWorkflow. The companion runs the agent locally and reports
    back; the platform opens the PR and (on the merge gate) merges."""

    run_id: str
    tenant_id: str
    project_id: str
    work_item_id: str
    agent_spec_id: str
    work_item_key: str          # branch name + run prompt
    repo: str                   # "owner/name"
    base: str                   # base branch the worktree forks from
    phase: str = "implementation"
    gate_type: str = "merge_gate"
    required_role: str = "reviewer"      # D6: the merge gate is a reviewer's call
    # If the companion (a laptop) never reports within this window, park for takeover.
    report_timeout_seconds: int = 7200


@dataclass
class BuildReport:
    """What the companion posts back after running the build locally (signal payload)."""

    status: str = "ok"          # "ok" | "failed"
    branch: str = ""
    head_sha: str = ""
    changed_files: list = field(default_factory=list)
    message: str = ""
