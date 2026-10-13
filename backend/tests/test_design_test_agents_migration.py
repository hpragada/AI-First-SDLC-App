"""P3 — migrated design/test/security agents (AGENT_MIGRATION_SPEC §2/3/8).

Verifies the 75/15/10 migration on the real bodies: reasoning preserved verbatim, every
data reference rerouted to the platform (inputs -> get_context/get_artifact/designsource;
outputs -> register_artifact + trace edges; Human Gate removed), the §8 sweep clean, the
gate roles correct, and a run that reads its inputs from the platform (not a file).

Starts with 05 UX Design; 09 / 09b / 10 are appended as their migration tasks land.
"""
import asyncio
from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import get_by_key, seed_agent_specs
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from drivers import ClaudeDriver
from orchestration import activities
from orchestration.types import AgentRunInput

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _REPO_ROOT / "agents"
_KEYS = ["05_ux_design", "09_testing", "09b_test_automation", "10_security"]


def _read_system_prompt(options) -> str:
    """The system prompt the driver actually handed the engine.

    It is delivered as `--system-prompt-file <path>`, never on `options.system_prompt`, so read
    the file. Asserting on `options.system_prompt` silently reads `None` and every `in` check
    becomes a TypeError instead of a failed assertion about the body.
    """
    from drivers.claude_driver import _SYSTEM_PROMPT_FLAG

    path = (getattr(options, "extra_args", None) or {}).get(_SYSTEM_PROMPT_FLAG)
    assert path, "the driver passed no --system-prompt-file"
    return Path(path).read_text(encoding="utf-8")

# §8 forbidden tokens — any hit is a failed migration (same gate as every other agent).
_FORBIDDEN = [
    ".md", "docs/", "claude.md", "tasks.md", "reply approved",
    "/sdlc:", "rule-behavior", "rule-execution", "assumption-log",
]

# Reasoning that MUST survive verbatim (the 75% reuse), per agent.
_REASONING = {
    "05_ux_design": [
        "Senior UX/UI Designer and Design Systems Architect", "Double Diamond",
        "Atomic Design", "Cognitive Walkthrough", "WCAG", "Nielsen Norman",
        "a wireframe without states is not a wireframe", "Loading State Classification",
    ],
    # 09 reads "WCAG 2.2 AA" since QA-11. The *version* of a standard is a data reference (the
    # 15%), not reasoning (the 75%) — pinning it here as verbatim reasoning was the reason a
    # version uplift looked like a broken migration. What must survive is that the agent is
    # grounded in WCAG at all; which edition is data, and it now matches the loaded standard.
    "09_testing": [
        "Lead QA Engineer and Test Automation Architect", "test to break, not to pass",
        "Test Pyramid", "IEEE 829", "Requirements Traceability Coverage Map",
        "warm-up ramp", "axe-core", "WCAG 2.2 AA", "OWASP",
    ],
    "09b_test_automation": [
        "Senior Test Automation Engineer", "never guess a locator", "Page Object Model",
        "Playwright MCP", "DismissCookieBanner", "getByRole", "BasePage",
    ],
    "10_security": [
        "Senior Application Security Engineer", "think like an attacker first",
        "OWASP Top 10", "STRIDE", "CVSS 3.1", "SLSA", "Data Flow Diagram",
        "CWE", "least privilege",
    ],
}


def _body(key: str) -> str:
    return (_AGENTS / key / "agent.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("key", _KEYS)
def test_migrated_body_exists(key):
    assert (_AGENTS / key / "agent.md").is_file()


@pytest.mark.parametrize("key", _KEYS)
def test_reference_sweep_is_clean(key):
    """§8 hard gate: no local-file references survive."""
    body = _body(key).lower()
    hits = [tok for tok in _FORBIDDEN if tok in body]
    assert not hits, f"{key}: forbidden references survived: {hits}"


@pytest.mark.parametrize("key", _KEYS)
def test_reasoning_preserved_verbatim(key):
    body = _body(key)
    for needle in _REASONING[key]:
        assert needle in body, f"{key}: lost reasoning {needle!r} (75% reuse broken)"


def test_05_reroutes_to_designsource_and_artifacts():
    body = _body("05_ux_design")
    # inputs rerouted to the manifest + platform reads
    assert "get_artifact" in body
    assert "# Relevant Artifacts" in body and "# Rules" in body
    # the current design is read-as-SoR via the capability, not a local file (G3)
    assert "designsource" in body
    assert "get_design_context" in body and "get_variable_defs" in body
    # outputs rerouted to platform artifacts (no "Write These Files")
    assert "register_artifact" in body and "add_trace_edge" in body
    for art in ["ux_design", "user_journey", "wireframe", "design_system", "accessibility"]:
        assert art in body, f"05 missing rerouted artifact type {art!r}"
    # the legacy "Write These Files" output became "Register These Artifacts"
    assert "Register These Artifacts" in body
    # no human-gate glue survives (sweep catches "reply approved"; assert the next-command too)
    assert "/sdlc:task-breakdown" not in body
    assert "Reply APPROVED" not in body


def test_09_reroutes_to_testmgmt_and_platform():
    body = _body("09_testing")
    # inputs rerouted to the manifest + platform reads
    assert "get_artifact" in body
    assert "# Relevant Artifacts" in body and "# Rules" in body
    # outputs rerouted: test cases/results → platform artifacts + the TestMgmt SoR
    assert "register_artifact" in body and "add_trace_edge" in body
    assert "testmgmt.create_test" in body and "testmgmt.import_results" in body
    for art in ["test_plan", "test_case", "test_report"]:
        assert art in body, f"09 missing rerouted artifact type {art!r}"
    # the platform's flaky-quarantine + defect-loopback replace the local DEFECT-LOG
    assert "defect loopback" in body and "quarantine" in body.lower()
    # no human-gate / slash-command glue survives (sweep also catches "reply approved")
    assert "/sdlc:security" not in body and "Reply APPROVED" not in body


def test_09_is_planning_only_and_owns_no_working_copy():
    """Bugs S.No 85. 09's body told it to read the codebase, run the suite with coverage, and
    write E2E files into the working copy — while it is registered as a PLANNING phase, which
    has no worktree, no shell and no ability to run a command. Its first real run would have
    failed or produced nothing useful.

    That instruction set also duplicated 09b Test Automation, which already writes and runs
    tests and already has a worktree — two agents writing tests into the same repository.

    Team decision: 09 authors the specification, 09b executes it. This test used to assert
    `"worktree" in body`, which is what made the contradiction look intentional."""
    from apps.registry.catalog import reads_code, rides_build

    body = _body("09_testing")
    assert "worktree" not in body.lower(), "a planning-only agent has no working copy"
    assert not reads_code("09_testing") and not rides_build("09_testing")
    # the handover to 09b is stated, not implied
    assert "Test Automation agent" in body
    # …and 09b still owns the execution half
    assert reads_code("09b_test_automation") is False
    assert rides_build("09b_test_automation") is True


def test_09_never_registers_a_results_report():
    """Left behind by S.No 85: after the opening was rewritten to "does not run tests", four
    passages further down still told 09 to register a `test_report` of execution results, record
    scan violations in it, compare it against a baseline and capture defects in it. 09 runs
    nothing, so any report it wrote would be invented — and it would be filed under the same type
    as 09b's real one, which the defect loopback, the test gate and Deployment read as measured."""
    body = _body("09_testing")
    outputs = body.split("## Output — Register These Artifacts")[1].split("## Quality Gate")[0]
    table_rows = [line for line in outputs.splitlines() if line.startswith("| `")]
    assert [row.split("`")[1] for row in table_rows] == ["test_plan", "test_case"]
    assert "Never register a `test_report` from this phase" in outputs
    # none of the old instructions to write results survives anywhere in the body
    for stale in ("Record all violations in the `test_report`",
                  "Capture the following for each finding in the `test_report`",
                  "When you report execution results",
                  "your report has to show both",
                  "The run's `a11y_report` read where one exists"):
        assert stale not in body, stale


def test_09_requires_one_staged_body_per_test_case():
    """Testing-phase bug 1: a run registered 90 test cases against 4 batched bodies, which the
    TestMgmt export would have collapsed into 4 issues (create_test is idempotent by the summary
    it parses out of the body). The body must direct one `stage_artifact_body` per test case;
    the platform guard in `tools.register_artifact` enforces it, but intent lives here."""
    body = _body("09_testing")
    assert "stage_artifact_body" in body                   # the staging half is named at all
    assert "one test case = one staged body" in body.lower()
    assert "batch" in body.lower()                         # batching is called out as wrong


def test_09_requires_a_manual_executable_case_per_user_facing_criterion():
    """Testing-phase bug 2: run b0e6557b left US-002 (Log In) and US-012 (View Recent
    Transactions) covered ONLY by API-level Integration cases — a manual QA had no way to
    verify "I can log in". The agent already did the right thing for 11 of 13 stories, so the
    body must make that a rule rather than leave it to chance."""
    body = _body("09_testing")
    lowered = body.lower()
    assert "manual-executable coverage (mandatory)" in lowered
    assert "user-facing" in lowered
    # API depth is additional, never a substitute — the exact hole US-002 fell through.
    assert "never a substitute" in lowered


def test_09_keeps_automation_detail_out_of_the_testers_steps():
    """The same case serves the tester and the 09b script, because they read different FIELDS.
    Developer mechanics belong in Automation Notes (which 09b parses), not in the steps a
    human follows — so precision is relocated, never lost."""
    body = _body("09_testing")
    assert "Automation Notes" in body
    assert "One case, two readers" in body
    # A Functional/E2E oracle must be observable on screen, not a JWT/DB/DOM assertion.
    assert "observable on screen" in body.lower()


def test_09_does_not_claim_the_gate_auto_publishes_to_the_sor():
    """Doc/implementation drift: export is a reviewer-triggered action
    (`api/views.py::_publish_testmgmt`, "manual export, team flow decision 2026-07-07"), not a
    consequence of approval. The body must not promise the platform does it automatically."""
    body = _body("09_testing")
    assert "on gate approval the platform publishes" not in body.lower()


def test_09b_preserves_playwright_pom_and_reroutes():
    body = _body("09b_test_automation")
    # the locator-discovery IP is preserved verbatim
    assert "Playwright MCP" in body and "Page Object Model" in body
    assert "mcp__playwright__browser_navigate" in body
    assert "mcp__playwright__browser_snapshot" in body
    assert "never guess a locator" in body
    # inputs rerouted to the platform; scripts are code written into the worktree
    assert "get_artifact" in body and "testmgmt.get_test" in body
    assert "worktree" in body
    assert "register_artifact" in body
    # the engine never touches Git — the platform commits/pushes/opens the PR (D2)
    for forbidden in ["git push", "gh pr create", "git checkout"]:
        assert forbidden not in body, f"09b still drives git: {forbidden!r}"
    # the interactive TC-selection / human-gate glue is replaced by platform assignment
    assert "Reply APPROVED" not in body and "STOP HERE" not in body


def test_10_reroutes_to_worktree_and_security_artifacts():
    body = _body("10_security")
    # inputs rerouted to the manifest + the worktree (the code/deps under review)
    assert "get_artifact" in body
    assert "# Relevant Artifacts" in body and "# Rules" in body
    assert "worktree" in body
    # outputs rerouted to platform artifacts (no "Write These Files")
    assert "register_artifact" in body
    for art in ["security_review", "security_finding", "threat_model", "sbom"]:
        assert art in body, f"10 missing rerouted artifact type {art!r}"
    # the SOTA quality bar is preserved verbatim
    assert "STRIDE" in body and "OWASP Top 10" in body and "CVSS 3.1" in body
    # criticals/highs ride the platform defect loopback (D8); standalone — no merge-gate glue
    assert "defect loopback" in body
    # no human-gate / slash-command glue survives
    assert "/sdlc:cicd" not in body and "Reply APPROVED" not in body


def test_qa_designer_and_security_gate_roles():
    assert get_by_key("05_ux_design").gate_role == "designer"
    assert get_by_key("09_testing").gate_role == "qa_lead"
    assert get_by_key("09b_test_automation").gate_role == "qa_lead"
    assert get_by_key("10_security").gate_role == "security_engineer"


@pytest.mark.django_db
@pytest.mark.parametrize("key", _KEYS)
def test_seeded_agentspec_resolves_to_migrated_body(key):
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key=key)
    assert spec.body_ref == f"agents/{key}/agent.md"
    assert (_REPO_ROOT / spec.body_ref).is_file()


@pytest.mark.django_db
def test_ux_run_reads_inputs_from_platform():
    """A run composes a manifest from platform state and loads the migrated 05 body as the
    system prompt — inputs come from the platform, not a local file."""
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(
        tenant=t, project=project, important_context="web-first, desktop 1280px+"
    )
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="05_ux_design")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)

    inp = AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="ux_design",
    )
    manifest = activities.compose_manifest_core(inp)
    assert "# Project" in manifest and "# Rules" in manifest
    assert "desktop 1280px+" in manifest

    captured: dict = {}

    async def fake_query(*, prompt, options, transport=None):
        # Delivered as a file, not on `options.system_prompt` — see `_read_system_prompt`.
        captured["system_prompt"] = _read_system_prompt(options)
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="s", total_cost_usd=0.01, usage={},
            result="# UX\nregistered",
        )

    driver = ClaudeDriver(query_fn=fake_query)
    result = asyncio.run(
        driver.run_planning_task(
            manifest=manifest, agent_spec=spec, mcp_servers={}, allowed_tools=[], work_item=wi
        )
    )

    sysprompt = captured["system_prompt"]
    assert "UX Design Agent — Phase 5" in sysprompt
    assert "Senior UX/UI Designer and Design Systems Architect" in sysprompt  # verbatim
    assert "register_artifact" in sysprompt          # rerouted output reference
    assert "designsource" in sysprompt               # read-as-SoR reroute
    assert ".md" not in sysprompt                    # §8 clean at runtime too
    assert result.outputs["result"] == "# UX\nregistered"
