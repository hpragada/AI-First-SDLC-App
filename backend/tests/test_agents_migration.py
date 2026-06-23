"""P0-T10c — migrated planning agents 01–04 (AGENT_MIGRATION_SPEC §2–3 + §8).

Verifies the 75/15/10 migration on the real bodies: reasoning preserved verbatim,
every reference rerouted to the platform, the §8 sweep clean, AgentSpecs resolve, and a
run reads its inputs from the platform (not a file).
"""
import asyncio
from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from drivers import ClaudeDriver
from orchestration import activities
from orchestration.types import AgentRunInput

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _REPO_ROOT / "agents"

# §8 forbidden tokens — any hit is a failed migration.
_FORBIDDEN = [
    ".md", "docs/", "claude.md", "tasks.md", "reply approved",
    "/sdlc:", "rule-behavior", "rule-execution", "assumption-log",
]

# Verbatim reasoning that MUST survive (75% reuse), per agent.
_REASONING = {
    "01_ideation": ["Chief Product Officer", "Problem Discovery", "TAM", "Beachhead"],
    "02_requirements": ["Senior Business Analyst", "INVEST", "ISO/IEC", "SHALL"],
    "03_prd": ["Senior Product Manager", "Working Backwards", "Four Risks", "Marty Cagan"],
    "04_architecture": [
        "Principal Solutions Architect", "C4 Model", "OWASP Top 10", "NFR-to-Architecture",
    ],
}
_KEYS = list(_REASONING)


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


@pytest.mark.parametrize("key", _KEYS)
def test_references_rerouted_to_platform(key):
    body = _body(key)
    # outputs -> register_artifact; inputs -> get_artifact + manifest sections
    assert "register_artifact" in body
    assert "get_artifact" in body
    assert "# Relevant Artifacts" in body
    assert "# Rules" in body


@pytest.mark.django_db
def test_seeded_agentspecs_resolve_to_migrated_bodies():
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    for key in _KEYS:
        spec = AgentSpec.objects.get(tenant=t, key=key)
        assert spec.body_ref == f"agents/{key}/agent.md"
        assert (_REPO_ROOT / spec.body_ref).is_file()


@pytest.mark.django_db
def test_prd_run_reads_inputs_from_platform():
    """A run composes a manifest from platform state and loads the migrated body as the
    system prompt — inputs come from the platform, not a local file."""
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(
        tenant=t, project=project, important_context="north-star steering"
    )
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key="03_prd")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)

    inp = AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
    )
    # Inputs come from the platform (get_context -> manifest), not a file.
    manifest = activities.compose_manifest_core(inp)
    assert "# Project" in manifest and "# Rules" in manifest
    assert "north-star steering" in manifest

    captured: dict = {}

    async def fake_query(*, prompt, options, transport=None):
        captured["system_prompt"] = options.system_prompt
        captured["cwd"] = options.cwd
        yield ResultMessage(
            subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
            num_turns=1, session_id="s", total_cost_usd=0.01, usage={}, result="# PRD\nbody",
        )

    # Default body_loader resolves spec.body_ref against the repo root -> the migrated body.
    driver = ClaudeDriver(query_fn=fake_query)
    result = asyncio.run(
        driver.run_planning_task(
            manifest=manifest, agent_spec=spec, mcp_servers={}, allowed_tools=[], work_item=wi
        )
    )

    # The migrated 03_prd body was loaded as the system prompt (reasoning + rerouting present).
    sysprompt = captured["system_prompt"]
    assert "PRD Agent — Phase 3" in sysprompt
    assert "Senior Product Manager" in sysprompt  # verbatim reasoning
    assert "register_artifact" in sysprompt  # rerouted output reference
    assert ".md" not in sysprompt  # §8 clean at runtime too
    assert result.outputs["result"] == "# PRD\nbody"
