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
_KEYS = ["05_ux_design"]

# §8 forbidden tokens — any hit is a failed migration (same gate as every other agent).
_FORBIDDEN = [
    ".md", "docs/", "claude.md", "tasks.md", "reply approved",
    "/sdlc:", "rule-behavior", "rule-execution", "assumption-log",
]

# Reasoning that MUST survive verbatim (the 75% reuse), per agent.
_REASONING = {
    "05_ux_design": [
        "Senior UX/UI Designer and Design Systems Architect", "Double Diamond",
        "Atomic Design", "Cognitive Walkthrough", "WCAG 2.1 AA", "Nielsen Norman",
        "a wireframe without states is not a wireframe", "Loading State Classification",
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


def test_designer_gate_role():
    assert get_by_key("05_ux_design").gate_role == "designer"


@pytest.mark.django_db
def test_seeded_agentspec_resolves_to_migrated_body():
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="05_ux_design")
    assert spec.body_ref == "agents/05_ux_design/agent.md"
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
        captured["system_prompt"] = options.system_prompt
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
