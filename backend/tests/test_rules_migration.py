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
        "reviewer direction",               # Rule 12 — "Request changes"
    ]:
        assert needle in rules, f"missing distilled rule content: {needle!r}"


def test_reviewer_direction_is_authoritative_and_may_not_be_dropped_silently():
    """A reviewer's written direction is the one input a human typed against the agent's actual
    output. Two failure modes have to be closed in the prompt, because neither is detectable
    afterwards: quietly ignoring a point, and quietly overriding an earlier answer."""
    rules = get_prompt_rules().lower()
    assert "reviewer direction" in rules
    assert "authoritative" in rules
    # It must beat a stale clarification answer — and say when it does.
    assert "outranks" in rules or "supersede" in rules
    # An infeasible point must be reported, not dropped.
    assert "infeasible" in rules
    # It must not undo an earlier round's request.
    assert "do not undo" in rules


def test_gap_scan_is_a_question_never_an_artifact():
    """Regression: a planning agent (01_ideation on the Test09 tenant) wrote its Context Gap
    Scan into an `ideation` artifact instead of calling ask_human. The distilled rules must now
    forbid that unambiguously for every phase (the rule is rendered into every manifest)."""
    rules = get_prompt_rules().lower()
    for needle in [
        "never a deliverable",              # the gap scan is a question, not an artifact
        "wait for the answers before",      # block before producing/registering
        "only channel for a gap is the",    # ask_human is the sole channel
        "failed run",                       # dumping the scan / unanswered Tier-1 = failure
    ]:
        assert needle in rules, f"missing gap-scan enforcement: {needle!r}"


def test_rules_forbid_two_ask_human_calls_in_one_turn():
    """Regression: run 75adb0ec (01_ideation) emitted TWO ask_human calls in a single turn. The
    second queued behind the first and fired one second after the human answered, re-asking the
    same ten questions 37 minutes later. The existing "a SINGLE call" wording was read as "don't
    dribble questions out over time"; it never forbade two calls in one message. It does now."""
    rules = get_prompt_rules().lower()
    for needle in [
        "one `ask_human` tool call per message",   # the rule itself
        "never two in the same turn",              # the specific failure, named
        "queues behind the first",                 # why it is harmful, not just disallowed
    ]:
        assert needle in rules, f"missing single-call enforcement: {needle!r}"


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


# ── the failure message must follow EVIDENCE, not a remembered cause ──
# The original text asserted "the agent's write tools being absent from its context" because
# that was the cause of the run it was written for (2026-07-30 §4b). Run fad927a2 had its write
# tools working fine and `ask_human` broken, so the message pointed at the wrong subsystem.
def _register_platform_copy(run_input, body=b"# status\nDB unavailable"):
    """Reproduce the only-artifact-is-the-platform's-copy shape."""
    from mcp_platform_state import tools

    from orchestration.activities import PHASE_REPORT_SOURCE
    from storage import content_hash

    tools.register_artifact(
        run_input.tenant_id, run_input.project_id, run_input.run_id,
        "prd", "prd", "internal", content_hash(body), s3_key="drafts/t/p/r/prd.md",
        external_ref={"source": PHASE_REPORT_SOURCE},
    )


def test_no_agent_artifact_blames_tooling_when_nothing_was_asked(run_input):
    _register_platform_copy(run_input)
    with pytest.raises(WriteCompletenessError, match="write tools being absent"):
        verify_write_completeness_core(run_input, ["prd"])


def test_no_agent_artifact_names_the_unanswered_clarification_instead(run_input):
    """Run fad927a2: the agent reached its tools, asked, and the answer never came back — so
    Rule 1 correctly stopped it writing. Blaming the write tools here is simply wrong, and it
    buries the recovery (answer it, then re-run — the answers replay)."""
    from apps.clarifications.models import Clarification
    from apps.tenancy.context import tenant_context

    _register_platform_copy(run_input)
    with tenant_context(run_input.tenant_id):
        Clarification.objects.create(
            tenant_id=run_input.tenant_id, run_id=run_input.run_id,
            work_item_id=run_input.work_item_id, phase="prd",
            status=Clarification.Status.PENDING,
            questions=[{"id": "q1", "text": "Which currency?", "kind": "text"}],
        )
    with pytest.raises(WriteCompletenessError) as exc:
        verify_write_completeness_core(run_input, ["prd"])
    message = str(exc.value)
    assert "still unanswered" in message
    assert "NOT a tooling failure" in message
    assert "re-run the phase" in message
    assert "write tools being absent" not in message


def test_an_answered_clarification_does_not_change_the_diagnosis(run_input):
    """Only a PENDING one is evidence the agent is still waiting; an answered clarification
    means it got what it asked for and stopped for some other reason."""
    from apps.clarifications.models import Clarification
    from apps.tenancy.context import tenant_context

    _register_platform_copy(run_input)
    with tenant_context(run_input.tenant_id):
        Clarification.objects.create(
            tenant_id=run_input.tenant_id, run_id=run_input.run_id,
            work_item_id=run_input.work_item_id, phase="prd",
            status=Clarification.Status.ANSWERED,
            questions=[{"id": "q1", "text": "Which currency?", "kind": "text"}],
            answers={"q1": "USD"},
        )
    with pytest.raises(WriteCompletenessError, match="write tools being absent"):
        verify_write_completeness_core(run_input, ["prd"])
