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


def _read_system_prompt(options) -> str:
    """The system prompt the driver actually handed the engine.

    It is delivered as `--system-prompt-file <path>`, never on `options.system_prompt`, so read
    the file. Asserting on `options.system_prompt` silently reads `None` and every `in` check
    below becomes a TypeError instead of a failed assertion about the body.
    """
    from drivers.claude_driver import _SYSTEM_PROMPT_FLAG

    path = (getattr(options, "extra_args", None) or {}).get(_SYSTEM_PROMPT_FLAG)
    assert path, "the driver passed no --system-prompt-file"
    return Path(path).read_text(encoding="utf-8")

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
    "06_task_breakdown": [
        "Senior Tech Lead and Delivery Manager", "INVEST", "Critical Path Method",
        "Definition of Done",
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


@pytest.mark.parametrize("key", ["01_ideation", "02_requirements", "04_architecture"])
def test_gap_scan_routed_to_ask_human_gate(key):
    """Change B(i): the three agents that frame the gap scan as a produced step must point it at
    the `ask_human` clarifications gate and forbid writing the scan into an artifact. Regression:
    an 01_ideation run dumped its Context Gap Scan into an `ideation` artifact instead of asking."""
    body = _body(key)
    assert "ask_human" in body, f"{key}: gap scan not routed to ask_human"
    assert "Surface these through the gate" in body, f"{key}: missing gate reinforcement"


@pytest.mark.parametrize("key", _KEYS)
def test_references_rerouted_to_platform(key):
    body = _body(key)
    # outputs -> register_artifact; inputs -> get_artifact + manifest sections
    assert "register_artifact" in body
    assert "get_artifact" in body
    assert "# Relevant Artifacts" in body
    assert "# Rules" in body


def test_task_breakdown_proposes_work_items_to_platform():
    """06's output is rerouted to the platform backlog, not local files: it proposes the
    epic→story→task hierarchy via create_work_item and registers a `backlog` artifact —
    the reconciliation service later pushes the proposed items to the TaskTracker."""
    body = _body("06_task_breakdown")
    assert "create_work_item" in body
    assert 'type="epic"' in body and 'type="story"' in body and 'type="task"' in body
    assert "backlog" in body
    assert "proposed" in body  # items are proposals awaiting the gate, not published issues


def test_code_review_states_final_message_json_contract():
    """Bugs S.No 114: the platform parses 08's verdict from the LAST json block of its FINAL
    message. The body must make that contract explicit — final message ends with the json block,
    nothing after it, and the verdict is not delivered via a tool/event instead."""
    body = _body("08_code_review").lower()
    assert "final message" in body
    assert ("nothing after" in body or "last thing you output" in body
            or "last thing you emit" in body)
    assert "tool call or event" in body  # must not deliver the verdict only via an event


def test_code_review_hygiene_findings_are_non_blocking():
    """Bugs S.No 116: Step-1 hygiene checks (PR size, commit msg, branch, PR description, linear
    history) are platform-owned or non-code, so the 07 remediation loop can't fix them. They must
    be non-blocking Suggestions — NOT blocking Criticals that loop until the cycle cap exhausts."""
    body = _body("08_code_review").lower()
    assert "non-blocking suggestion" in body      # the reclassification
    assert "unwinnable remediation loop" in body  # the rationale is stated
    # the old "any check that fails -> CRITICAL finding" instruction must be gone
    assert "any check that fails" not in body


def test_task_breakdown_descriptions_and_ac_are_humanized():
    """Bugs S.No 118: 06 must require plain-language-with-technical-nuance, implement-by-reading
    descriptions + acceptance criteria — not just an engineer-only precision bar.

    The 2026-07-15 fix set the *instruction* but left technical exemplars, so Tasks stayed terse.
    This asserts the follow-up: a plain-language *intent-lead* requirement AND worked Story + Task
    exemplars the model can imitate (few-shot copies exemplars, not rules)."""
    body = _body("06_task_breakdown")
    assert "Writing standard" in body
    low = body.lower()
    assert "plain language" in low or "plain-language" in low
    assert "implement" in low and "acceptance criteria" in low

    # The intent-lead requirement: every Story/Task Description opens with a plain-language
    # statement of intent BEFORE the implementation detail.
    assert "statement of intent" in low
    assert "worked" in low and "example" in low  # worked exemplars are present

    # Worked exemplars the model imitates — a Story and a Task, both leading with intent and
    # carrying concrete given/when/then acceptance criteria.
    assert "US-021" in body  # worked User Story exemplar
    assert "Let a signed-in user change their email address" in body  # worked Task exemplar
    assert low.count("given ") >= 3 and "when " in low and "then " in low  # given/when/then AC


def test_per_item_agents_author_artifact_titles():
    """Bugs S.No 120: agents that register many artifacts of one type must pass a human-readable
    `title` so the UI can tell them apart (wireframe per screen, test_case per TC, etc.)."""
    assert "Wireframe — Login Page" in _body("05_ux_design")
    assert "title" in _body("09_testing").lower() and "TC-014" in _body("09_testing")
    assert "title" in _body("10_security").lower()
    assert "ADR-003" in _body("04_architecture")


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
        # The system prompt travels as a FILE, not as `options.system_prompt` — a large body
        # (the UX agent is ~36 KB) overflowed the Windows command line and surfaced as the
        # misleading "Claude Code not found" (Bugs row 64). Read it here, inside the call, while
        # the run's workdir still exists.
        captured["system_prompt"] = _read_system_prompt(options)
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


def test_10_must_say_whether_a_tool_actually_ran():
    """Bugs S.No 186. The live EPIC-004 report said Bandit was "blocked by sandbox restrictions →
    full manual pass performed" and the SBOM read "Manual CycloneDX Generation" — with every tool
    checkbox in the Quality Gate ticked. The findings were sound; the framing was not, and a human
    approved a gate believing scanners had run. Of the three causes behind S.No 185 this is the
    one that makes the phase dangerous rather than merely limited: it turns a known limitation
    into a misleading claim, so it ships ahead of the provisioning work."""
    body = _body("10_security")
    assert "Scan Provenance" in body, "the report must open with a provenance table"
    for label in ("TOOL-RUN", "MANUAL", "CI-GATE"):
        assert label in body, f"the provenance vocabulary must include `{label}`"
    lower = body.lower()
    assert "exit status" in lower, "a TOOL-RUN claim must carry the command's exit status"
    assert "never tick a tool checkbox in the quality gate for a `manual` step" in lower
    assert "never describe a `manual` step in tool language" in lower
    # The gate itself must offer the manual alternative, or the rule above has nowhere to land.
    assert "SAST reviewed by hand" in body and "SBOM hand-assembled" in body


# ── S.No 121-126: the artifacts humans approve must be readable by those humans ──
_HUMANIZED = {
    # agent key -> (what the standard is called, a phrase only the right register would contain)
    "02_requirements": ("Writing standard", "plain-language sentence of intent"),
    "09_testing": ("Clarity standard", "humanized-technical"),
    "00c_intelligent_context_extractor": ("Writing standard", "keep the technical nuance"),
    "04_architecture": ("Writing standard", "readable by a non-technical stakeholder"),
    "03_prd": ("Writing standard", "observable outcome someone could verify by hand"),
    "10_security": ("Writing standard", "two registers"),
}


@pytest.mark.parametrize("key", sorted(_HUMANIZED))
def test_the_artifacts_a_human_approves_carry_a_writing_standard(key):
    """Bugs S.No 121-126. The gate is the platform's central promise — a named human reviews
    before anything reaches a system of record. A reviewer who cannot read the artifact cannot
    review it: they approve on trust and the gate becomes ceremony. 06 had this defect and it was
    fixed (S.No 118); these six were written to an engineer-only bar while naming a Product Owner
    as their reviewer.

    Note the register is NOT uniform, and the difference is deliberate: 09 and 10's findings are
    humanized-TECHNICAL, because a QA or security reader must interpret precise detail correctly
    and flattening it into everyday words causes misreading."""
    heading, phrase = _HUMANIZED[key]
    body = _body(key)
    assert f"### {heading}" in body, f"{key} has no {heading} block"
    assert phrase.lower() in body.lower(), f"{key}'s standard is missing its defining phrase"
    # The 06 fix proved the instruction alone was not enough — the exemplars are what changed the
    # output. Every one of these must carry a worked example and a counter-example.
    assert "Worked example" in body or "Worked examples" in body, f"{key} has no worked example"
    assert "Failed" in body or "failed" in body


def test_09_and_10_are_explicitly_not_plain_language():
    """The asymmetry, pinned so a later tidy-up cannot flatten all six to one register."""
    assert "NOT plain language" in _body("09_testing")
    ten = _body("10_security")
    assert "humanized-technical" in ten.lower() and "plain language" in ten.lower()
