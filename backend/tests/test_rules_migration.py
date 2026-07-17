"""P0-T10a — rules migration (AGENT_MIGRATION_SPEC §4).

Prompt-enforced rules distilled into the manifest `# Rules` section (reasoning preserved,
references rerouted), and platform-enforced Rule 11 (write-completeness) as a workflow hook.
"""
import pytest

from manifest.rules import get_prompt_rules
from orchestration import activities
from orchestration.activities import WriteCompletenessError, verify_write_completeness_core
from orchestration.types import AgentRunInput


# ── prompt-enforced rules (manifest # Rules) ────────────────────────
def test_distilled_rules_preserve_reasoning():
    rules = get_prompt_rules().lower()
    for needle in [
        "tier 1", "tier 2", "tier 3",      # three-tier gap scan (Rule 1)
        "must ask", "suggest", "infer",
        "zero hallucination",               # Rule 3
        "source hierarchy",                 # Rule 7
        "context gap check",                # Rule 2 question format
        "what not to ask",                  # Rule 9
        "mid-phase",                        # Rule 6
        "assumption",                       # Rule 5 (agent side)
    ]:
        assert needle in rules, f"missing distilled rule content: {needle!r}"


def test_distilled_rules_have_no_local_file_references():
    """The §8 sweep applies to rules too: references must be rerouted to the platform."""
    rules = get_prompt_rules().lower()
    for forbidden in ["docs/", "claude.md", "tasks.md", "requirements.md", "reply approved"]:
        assert forbidden not in rules, f"un-rerouted reference survived: {forbidden!r}"
    # References should point at the platform instead.
    assert "get_artifact" in rules and "register_artifact" in rules
    assert "# relevant artifacts" in rules


@pytest.mark.django_db
def test_composer_renders_distilled_rules_in_rules_section():
    from apps.projects.models import Project, ProjectProfile
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.tenancy.models import Tenant
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(tenant=t, project=project, important_context="ctx")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    inp = AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
    )
    md = activities.compose_manifest_core(inp)
    rules_section = md.split("# Rules", 1)[1]
    assert "Zero hallucination" in rules_section
    assert "Tier 1" in rules_section


# ── platform-enforced Rule 11 (write-completeness) ──────────────────
@pytest.fixture
def run_input(db):
    from apps.projects.models import Project
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.tenancy.models import Tenant
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    return AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
    )


def test_write_completeness_passes_when_expected_artifact_present(run_input):
    from mcp_platform_state import tools

    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "prd", "internal", "h1",
    )
    result = verify_write_completeness_core(run_input, ["prd"])
    assert result["present"] == ["prd"]


def test_write_completeness_raises_when_artifact_missing(run_input):
    with pytest.raises(WriteCompletenessError):
        verify_write_completeness_core(run_input, ["prd"])


# ── an EMPTY expected artifact is not a write (Testing-phase bug 4) ──
def test_write_completeness_rejects_an_empty_phase_document(run_input):
    """Run b0e6557b staged a phase document from an engine that returned no final text, and
    the platform opened the gate on it — asking a human to approve a blank page. Presence is
    not the bar; there must be something to review."""
    from mcp_platform_state import tools

    from storage import content_hash

    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "prd", "internal", content_hash(b""), s3_key="drafts/t/p/r/prd.md",
    )
    with pytest.raises(WriteCompletenessError, match="EMPTY"):
        verify_write_completeness_core(run_input, ["prd"])


def test_write_completeness_passes_a_phase_document_with_a_body(run_input):
    from mcp_platform_state import tools

    from storage import content_hash

    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "prd", "internal", content_hash(b"# PRD\nreal content"),
        s3_key="drafts/t/p/r/prd.md",
    )
    assert verify_write_completeness_core(run_input, ["prd"])["present"] == ["prd"]


def test_a_pointer_only_artifact_is_not_judged_empty(run_input):
    """Only what we can know: an artifact registered with a foreign hash makes no claim about
    its body, so it is not accused of being empty (that would break every agent-registered
    pointer)."""
    from mcp_platform_state import tools

    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "prd", "internal", "sha256:someagenthash",
    )
    assert verify_write_completeness_core(run_input, ["prd"])["present"] == ["prd"]


def test_an_empty_non_expected_artifact_does_not_block(run_input):
    """A run may legitimately register an empty side artifact; only the phase's own expected
    document gates the review."""
    from mcp_platform_state import tools

    from storage import content_hash

    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "prd", "internal", content_hash(b"# PRD\nreal"), s3_key="k1")
    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "assumption", "internal", content_hash(b""), s3_key="k2")
    assert verify_write_completeness_core(run_input, ["prd"])["present"] == ["assumption", "prd"]
