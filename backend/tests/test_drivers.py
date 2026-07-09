"""P0-T6 — ExecutionDriver / ClaudeDriver (engine seam, spec §3).

Pure unit tests: an injected fake `query_fn` yields real SDK message objects, so the
message->RunResult mapping, options construction and system-prompt-file delivery are
verified without the network or a DB.

Delivery contract (Bugs row 65): the agent body + manifest are handed to the engine as its
SYSTEM PROMPT via `--system-prompt-file <path>`, never on the command line — so any body size
is safe on Windows and the instructions genuinely reach the model (unlike the earlier AGENTS.md
attempt, which Claude Code never auto-loaded). The tests render the REAL CLI args and read the
referenced file, rather than trusting that a file was merely written.
"""
from pathlib import Path
from types import SimpleNamespace

import claude_agent_sdk
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from drivers import ArtifactDraft, ClaudeDriver, ExecutionDriver, RunResult


def _cli_args(options) -> list[str]:
    """Render the actual argv the SDK would exec — the true delivery contract, not just the
    options object. `extra_args` (our SDK's channel for `--system-prompt-file`) lands here."""
    return SubprocessCLITransport(prompt="x", options=options, cli_path="claude")._build_command()


def _system_prompt_file(options) -> Path:
    from drivers.claude_driver import _SYSTEM_PROMPT_FLAG

    return Path(options.extra_args[_SYSTEM_PROMPT_FLAG])


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

    # System prompt (body + manifest) delivered via --system-prompt-file, never inline.
    opts = captured["options"]
    args = _cli_args(opts)
    assert "--system-prompt-file" in args and "--system-prompt" not in args
    assert opts.system_prompt is None
    sp = _system_prompt_file(opts)
    assert sp == (tmp_path / "wi-wi-123" / "SYSTEM_PROMPT.md")
    content = sp.read_text(encoding="utf-8")
    assert "AGENT BODY" in content and "# Project" in content and "manifest body" in content
    assert content.index("AGENT BODY") < content.index("# Project")   # body leads
    # Neither the body nor the manifest is an argv entry (they live in the file).
    assert not any("AGENT BODY" in str(a) or "manifest body" in str(a) for a in args)

    # Options built correctly from the agent spec + caller args.
    assert opts.allowed_tools == ["mcp__platform-state__get_context"]
    assert opts.mcp_servers == {"platform-state": {"command": "python"}}
    assert opts.model == "claude-opus-4-8"
    assert opts.permission_mode == "default"
    assert "wi-123" in captured["prompt"]

    # Sandbox (Bugs S.No 63): planning is locked to platform-state MCP tools — the built-in
    # filesystem/shell/subagent tools are denied, and only project (not user) settings load.
    for blocked in ("Agent", "Bash", "Read", "Write", "Edit", "Grep", "Glob", "ToolSearch"):
        assert blocked in opts.disallowed_tools
    assert opts.setting_sources == ["project"]
    assert "--disallowedTools" in args
    assert args[args.index("--setting-sources") + 1] == "project"


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
    opts = captured["options"]
    args = _cli_args(opts)
    # System prompt goes to .sdlc/ (excluded from the diff), never the worktree root; and via
    # --system-prompt-file so a large build-agent body can never overflow the command line.
    sp = _system_prompt_file(opts)
    assert sp == (workspace / ".sdlc" / "SYSTEM_PROMPT.md")
    assert not (workspace / "SYSTEM_PROMPT.md").exists()   # collision guard: clean worktree root
    assert not (workspace / "AGENTS.md").exists()
    content = sp.read_text(encoding="utf-8")
    assert "BUILD BODY" in content and "# Build manifest" in content
    assert "--system-prompt-file" in args and "--system-prompt" not in args
    # We deliberately do NOT force project setting-sources on the client repo (no client
    # CLAUDE.md / .claude hook loading). The SDK still emits an empty --setting-sources; assert
    # we never turn it on to "project".
    assert "project" not in args
    assert opts.cwd == str(workspace)          # the agent runs in the worktree
    assert opts.system_prompt is None
    assert "Bash" in opts.allowed_tools
    # Implementation is NOT sandboxed — it must edit code in the real worktree, so the
    # filesystem/shell tools are kept and never denied (Bugs S.No 63 sandbox is planning/review
    # only). No planning denylist, and no forced project-only setting sources.
    assert not opts.disallowed_tools
    for fs_tool in ("Read", "Write", "Edit", "Bash", "Grep", "Glob"):
        assert fs_tool not in (opts.disallowed_tools or [])
    assert opts.setting_sources is None
    # The build prompt forbids git/PR — the platform does that (D2).
    assert "system prompt" in captured["prompt"] and "Do NOT run git" in captured["prompt"]


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


import pytest


@pytest.mark.parametrize("body_size", [5_000, 40_000])   # small AND ux_design-sized (>32767)
async def test_body_and_manifest_delivered_via_system_prompt_file(tmp_path, body_size):
    """Regression (Bugs row 65 — the row-64 AGENTS.md fix silently dropped the role body): for
    EVERY body size, the body + manifest travel via --system-prompt-file (never the command
    line, so no WinError 206), and both actually reach the file the model reads. The old test
    asserted only that a file was written — i.e. that the body was on NO delivered channel."""
    captured: dict = {}
    body = "ROLE-BODY " + ("X" * body_size)
    driver = ClaudeDriver(query_fn=_fake_query_factory(_messages(), captured),
                          body_loader=lambda s: body, workdir_base=tmp_path)
    await driver.run_planning_task(
        manifest="# Project\nmanifest body\n# Rules\nRULE-1 always register",
        agent_spec=_spec(), mcp_servers={}, allowed_tools=[],
        work_item=SimpleNamespace(id="big1"))

    opts = captured["options"]
    args = _cli_args(opts)
    # Delivered as a file-based system prompt; the raw text is never an argv entry.
    assert "--system-prompt-file" in args and "--system-prompt" not in args
    assert opts.system_prompt is None
    assert not any("ROLE-BODY" in str(a) or "RULE-1" in str(a) for a in args)
    # The file the CLI reads contains the whole body AND the whole manifest (incl. # Rules,
    # which reaches the model through no other channel).
    content = _system_prompt_file(opts).read_text(encoding="utf-8")
    assert body in content
    assert "# Project" in content and "manifest body" in content
    assert "# Rules" in content and "RULE-1 always register" in content


async def test_system_prompt_file_path_with_spaces(monkeypatch):
    """Windows run dirs can contain spaces; the SDK passes argv as a list (no shell), so an
    absolute path with a space must survive intact as a single --system-prompt-file argument."""
    import tempfile

    base = Path(tempfile.mkdtemp(prefix="sdlc run ")) / "with space"
    base.mkdir(parents=True)
    captured: dict = {}
    driver = ClaudeDriver(query_fn=_fake_query_factory(_messages(), captured),
                          body_loader=lambda s: "BODY", workdir_base=base)
    await driver.run_planning_task(manifest="# Project\nm", agent_spec=_spec(), mcp_servers={},
                                   allowed_tools=[], work_item=SimpleNamespace(id="w1"))
    sp = _system_prompt_file(captured["options"])
    assert " " in str(sp) and sp.exists()
    args = _cli_args(captured["options"])
    # The path is one argv entry immediately after the flag (not split on the space).
    assert args[args.index("--system-prompt-file") + 1] == str(sp)


async def test_review_task_is_sandboxed_to_platform_tools(tmp_path):
    """Review reasons over the PR diff the platform inlines into the manifest (read through the
    CodeHost capability), running in an empty temp workdir — so it, too, is locked to the
    platform-state MCP tools; the built-in filesystem/shell/subagent tools are denied."""
    captured: dict = {}
    driver = ClaudeDriver(query_fn=_fake_query_factory(_messages(), captured),
                          body_loader=lambda s: "REVIEW BODY", workdir_base=tmp_path)
    await driver.run_review_task(
        manifest="# Project\nx\n# Pull Request Under Review\n+ added line",
        agent_spec=_spec(phase_label="code_review", key="08_code_review"),
        mcp_servers={}, allowed_tools=["mcp__platform-state__get_artifact"],
        work_item=SimpleNamespace(id="rv1"))
    opts = captured["options"]
    for blocked in ("Agent", "Bash", "Read", "Grep", "ToolSearch"):
        assert blocked in opts.disallowed_tools
    assert opts.setting_sources == ["project"]
    # The inlined diff still reaches the model via the system-prompt file.
    assert "# Pull Request Under Review" in _system_prompt_file(opts).read_text(encoding="utf-8")


def test_resilient_parser_tolerates_unknown_message_types():
    """CLI/SDK version skew (Bugs: 'Unknown message type: rate_limit_event' aborted a run): an
    engine message type the pinned SDK doesn't know must NOT crash the phase — it becomes a
    benign SystemMessage — while a genuinely malformed message still raises."""
    from claude_agent_sdk import SystemMessage
    from claude_agent_sdk._errors import MessageParseError
    from claude_agent_sdk._internal import client as _client

    out = _client.parse_message({"type": "rate_limit_event", "rate_limit": {"status": "allowed"}})
    assert isinstance(out, SystemMessage) and out.subtype == "rate_limit_event"
    # forward-robust: any future unknown notification type is tolerated too
    assert isinstance(_client.parse_message({"type": "some_future_event"}), SystemMessage)
    # but real errors are NOT hidden
    import pytest
    with pytest.raises(MessageParseError):
        _client.parse_message({"no_type": True})


async def test_consume_ignores_system_message_in_stream(tmp_path):
    """A rate_limit_event (parsed to SystemMessage) interleaved in the stream is ignored; the
    run still maps the Assistant + Result messages to a valid RunResult."""
    from claude_agent_sdk import SystemMessage

    msgs = [_messages()[0], SystemMessage(subtype="rate_limit_event", data={}), _messages()[1]]
    captured: dict = {}
    driver = ClaudeDriver(query_fn=_fake_query_factory(msgs, captured),
                          body_loader=lambda s: "b", workdir_base=tmp_path)
    result = await driver.run_planning_task(manifest="m", agent_spec=_spec(), mcp_servers={},
                                            allowed_tools=[], work_item=SimpleNamespace(id="w1"))
    assert result.cost_usd == 0.0123 and result.outputs["result"] == "PRD complete"
    assert len(result.artifacts) == 1   # the SystemMessage didn't disrupt artifact capture


def test_body_loader_reads_body_ref(tmp_path):
    body = tmp_path / "agent.md"
    body.write_text("ROLE: PRD agent\n", encoding="utf-8")
    driver = ClaudeDriver(query_fn=_fake_query_factory([], {}), repo_root=tmp_path)
    assert driver._read_body_file(_spec(body_ref="agent.md")) == "ROLE: PRD agent\n"
