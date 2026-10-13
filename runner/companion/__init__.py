"""Local-companion runner (Phase-2 §3).

Runs on the *developer's* machine — not the platform. It enrolls with the platform,
provisions a managed git **worktree** off the dev's clone (a clean `feature/<key>` branch),
runs the build agent against that worktree via `run_build_task`, and reaches platform state
only over the authenticated **remote Platform-State** HTTP API (no DB on the dev machine;
tenant binding + RLS stay server-side). The developer runs/tests the worktree locally
before any PR.
"""
