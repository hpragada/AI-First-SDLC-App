"""P0-T6 — ExecutionDriver / ClaudeDriver (engine seam, spec §3).

Pure unit tests: an injected fake `query_fn` yields real SDK message objects, so the
message->RunResult mapping, options construction and AGENTS.md writing are verified
without the network or a DB.
"""
from pathlib import Path
from types import SimpleNamespace

import claude_agent_sdk
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from drivers import ArtifactDraft, ClaudeDriver, ExecutionDriver, RunResult


def _messages():
    return [
        AssistantMessage(
            content=[
                TextBlock(text="Drafting the PRD..."),
                ToolUseBlock(
                    id="t1",
                    name="mcp__platform-state__register_artifact",
                    input={
                        "project_id": "p1", "run_id": "r1", "phase": "prd", "type": "prd",
                        "sor": "internal", "content_hash": "h1", "s3_key": "s3://b/prd.md",
                    },
                ),
            ],
            model="claude-opus-4-8",
            parent_tool_use_id=None,
        ),
        ResultMessage(
            subtype="success", duration_ms=10, duration_api_ms=8, is_error=False,
            num_turns=2, session_id="sess-1", total_cost_usd=0.0123, usage={},
            result="PRD complete",
        ),
    ]


def _fake_query_factory(messages, captured):
    async def fake_query(*, prompt, options, transport=None):
        captured["prompt"] = prompt
        captured["options"] = options
        captured["transport"] = transport
        for m in messages:
            yield m

    return fake_query


def _spec(**over):
    base = dict(
        body_ref="agents/03_prd/agent.md",
        recommended_model="claude-opus-4-8",
        phase_label="prd",
        key="03_prd",
    )
    base.update(over)
    return SimpleNamespace(**base)


async def test_run_planning_task_maps_stream_and_writes_manifest(tmp_path):
    captured: dict = {}
    driver = ClaudeDriver(
        query_fn=_fake_query_factory(_messages(), captured),
        body_loader=lambda spec: "AGENT BODY",
        workdir_base=tmp_path,
    )
    work_item = SimpleNamespace(id="wi-123")
    result = await driver.run_planning_task(
        manifest="# Project\nmanifest body",
        agent_spec=_spec(),
        mcp_servers={"platform-state": {"command": "python"}},
        allowed_tools=["mcp__platform-state__get_context"],
        work_item=work_item,
    )

    assert isinstance(result, RunResult)
    assert result.cost_usd == 0.0123
    assert result.outputs["result"] == "PRD complete"
    assert result.outputs["text"] == "Drafting the PRD..."
    assert len(result.raw_messages) == 2

    # Artifact captured from the register_artifact tool-use.
    assert len(result.artifacts) == 1
    art = result.artifacts[0]
    assert isinstance(art, ArtifactDraft)
    assert art.phase == "prd" and art.type == "prd"
    assert art.content_hash == "h1" and art.s3_key == "s3://b/prd.md"

    # AGENTS.md written to the run workdir.
    agents_md = tmp_path / "wi-wi-123" / "AGENTS.md"
    assert agents_md.read_text() == "# Project\nmanifest body"

    # Options built correctly from the agent spec + caller args.
    opts = captured["options"]
    assert opts.system_prompt == "AGENT BODY"
    assert opts.allowed_tools == ["mcp__platform-state__get_context"]
    assert opts.mcp_servers == {"platform-state": {"command": "python"}}
    assert opts.model == "claude-opus-4-8"
    assert opts.permission_mode == "default"
    assert "wi-123" in captured["prompt"]


async def test_run_build_task_runs_in_worktree_and_writes_manifest(tmp_path):
    captured: dict = {}
    driver = ClaudeDriver(
        query_fn=_fake_query_factory(_messages(), captured),
        body_loader=lambda spec: "BUILD BODY",
    )
    workspace = tmp_path / "wt-ST-1"
    workspace.mkdir()
    result = await driver.run_build_task(
        manifest="# Build manifest",
        agent_spec=_spec(phase_label="implementation", key="07_impl"),
        repo_workspace=workspace,
        mcp_servers={"platform-state": {"command": "python"}},
        allowed_tools=["Read", "Write", "Bash", "mcp__platform-state__register_artifact"],
        work_item=SimpleNamespace(id="wi-9", feature_stream="ST-1"),
    )

    assert isinstance(result, RunResult) and result.cost_usd == 0.0123
    # Manifest goes to .sdlc/ (excluded from the diff), never the worktree root.
    assert (workspace / ".sdlc" / "AGENTS.md").read_text() == "# Build manifest"
    assert not (workspace / "AGENTS.md").exists()

    opts = captured["options"]
    assert opts.cwd == str(workspace)          # the agent runs in the worktree
    assert opts.system_prompt == "BUILD BODY"
    assert "Bash" in opts.allowed_tools
    # The build prompt forbids git/PR — the platform does that (D2).
    assert ".sdlc/AGENTS.md" in captured["prompt"] and "Do NOT run git" in captured["prompt"]


def test_claude_driver_satisfies_protocol():
    driver = ClaudeDriver(query_fn=_fake_query_factory([], {}), body_loader=lambda s: "b")
    assert isinstance(driver, ExecutionDriver)


def test_default_query_fn_is_the_sdk():
    # Business logic must reach the engine only through the driver, using the real SDK.
    assert ClaudeDriver()._query is claude_agent_sdk.query


def test_claude_driver_honors_cli_path_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_PATH", "/usr/local/bin/claude")
    driver = ClaudeDriver(query_fn=_fake_query_factory([], {}), body_loader=lambda s: "b")
    assert driver._cli_path == Path("/usr/local/bin/claude")


def test_cli_path_defaults_to_claude_on_path_not_bundle(monkeypatch):
    """Regression (UX 'Claude Code not found'): with no explicit path or env var, the driver
    pins to the `claude` found on PATH — so the engine never falls back to the SDK's older
    bundled binary."""
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("drivers.claude_driver.shutil.which",
                        lambda name: "/usr/local/bin/claude" if name == "claude" else None)
    driver = ClaudeDriver(query_fn=_fake_query_factory([], {}), body_loader=lambda s: "b")
    assert driver._cli_path == Path("/usr/local/bin/claude")


async def test_cli_path_reaches_the_engine(tmp_path, monkeypatch):
    """The pinned CLI must reach the engine — via ClaudeAgentOptions.cli_path on SDKs that
    support it, else via an explicit transport — so the SDK never resolves its bundled binary."""
    import drivers.claude_driver as cd

    monkeypatch.setattr(cd.shutil, "which", lambda name: "/usr/local/bin/claude")
    captured: dict = {}
    driver = ClaudeDriver(query_fn=_fake_query_factory([], captured),
                          body_loader=lambda s: "b", workdir_base=tmp_path)
    await driver.run_planning_task(manifest="m", agent_spec=_spec(), mcp_servers={},
                                   allowed_tools=[], work_item=SimpleNamespace(id="w1"))
    if cd._OPTIONS_ACCEPTS_CLI_PATH:
        assert Path(captured["options"].cli_path) == Path("/usr/local/bin/claude")
    else:
        assert captured["transport"] is not None   # pinned via explicit transport (older SDK)


async def test_engine_launch_retries_transient_not_found(tmp_path, monkeypatch):
    """A transient 'Claude Code not found' while the CLI IS present on disk (a lost launch
    race) is retried, not surfaced as a phase failure."""
    import drivers.claude_driver as cd

    monkeypatch.setattr(cd, "_LAUNCH_BACKOFF", 0)              # no real waiting in tests
    cli = tmp_path / "claude.exe"
    cli.write_text("x")                                       # CLI exists on disk

    calls = {"n": 0}

    async def flaky(*, prompt, options, transport=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(f"Claude Code not found at: {cli}")
        for m in _messages():
            yield m

    driver = ClaudeDriver(query_fn=flaky, body_loader=lambda s: "b", workdir_base=tmp_path,
                          cli_path=str(cli))
    result = await driver.run_planning_task(manifest="m", agent_spec=_spec(), mcp_servers={},
                                            allowed_tools=[], work_item=SimpleNamespace(id="w1"))
    assert calls["n"] == 2 and result.outputs   # retried once, then succeeded


async def test_engine_launch_does_not_retry_when_cli_missing(tmp_path, monkeypatch):
    """A genuinely missing CLI must fail fast — no retry spin."""
    import pytest

    import drivers.claude_driver as cd

    monkeypatch.setattr(cd, "_LAUNCH_BACKOFF", 0)
    calls = {"n": 0}

    async def missing(*, prompt, options, transport=None):
        calls["n"] += 1
        raise RuntimeError("Claude Code not found at: /nope/claude")
        yield  # pragma: no cover — makes this an async generator

    driver = ClaudeDriver(query_fn=missing, body_loader=lambda s: "b", workdir_base=tmp_path,
                          cli_path="/nope/claude")            # path that does not exist
    with pytest.raises(RuntimeError, match="not found"):
        await driver.run_planning_task(manifest="m", agent_spec=_spec(), mcp_servers={},
                                       allowed_tools=[], work_item=SimpleNamespace(id="w2"))
    assert calls["n"] == 1   # failed fast, no retry


async def test_large_body_delivered_via_file_not_command_line(tmp_path):
    """Regression (UX 'Claude Code not found' = WinError 206, command line too long): an agent
    body larger than the command-line budget must be delivered via AGENTS.md, NOT as the system
    prompt on the command line. Small bodies (the other tests) still travel as the system prompt."""
    import drivers.claude_driver as cd

    captured: dict = {}
    big = "X" * (cd._MAX_INLINE_BODY_CHARS + 5000)
    driver = ClaudeDriver(query_fn=_fake_query_factory(_messages(), captured),
                          body_loader=lambda s: big, workdir_base=tmp_path)
    await driver.run_planning_task(manifest="# Project\nmanifest body", agent_spec=_spec(),
                                   mcp_servers={}, allowed_tools=[],
                                   work_item=SimpleNamespace(id="big1"))

    # The body is OFF the command line...
    assert captured["options"].system_prompt is None
    # ...and instead lives in AGENTS.md, together with the run context.
    agents_md = (tmp_path / "wi-big1" / "AGENTS.md").read_text(encoding="utf-8")
    assert big in agents_md and "# Project" in agents_md and "manifest body" in agents_md


def test_body_loader_reads_body_ref(tmp_path):
    body = tmp_path / "agent.md"
    body.write_text("ROLE: PRD agent\n", encoding="utf-8")
    driver = ClaudeDriver(query_fn=_fake_query_factory([], {}), repo_root=tmp_path)
    assert driver._read_body_file(_spec(body_ref="agent.md")) == "ROLE: PRD agent\n"
