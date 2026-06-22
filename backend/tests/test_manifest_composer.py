"""P0-T7 — Manifest Composer (spec §4): section order, content, token budget."""
import pytest

from manifest import TokenBudget, compose_manifest, estimate_tokens

_SECTION_ORDER = [
    "# Project",
    "# Important Context",
    "# Current Work Item",
    "# Relevant Artifacts",
    "# Recent Events",
    "# Retrieved Knowledge",
    "# Rules",
]


def _context(**over):
    ctx = {
        "profile": {
            "name": "Platform", "track": "greenfield", "repo_topology": "single",
            "domain": "sdlc", "version": 2, "description": "the platform",
            "tech_stack": {"backend": "django"}, "coding_standards": {},
            "nfrs": {}, "constraints": {}, "glossary": {},
            "important_context": "ALWAYS prefer retrieval. This is verbatim steering.",
        },
        "relevant_artifacts": [
            {
                "id": "a1", "type": "requirements", "version": 1, "phase": "requirements",
                "status": "published", "sor": "internal", "s3_key": "s3://b/req.md",
                "external_ref": None,
            }
        ],
        "recent_events": [
            {"ts": "2026-06-22T10:00:00", "actor": "system", "action": "run.completed",
             "target_type": "run", "target_id": "r1"}
        ],
        "retrieved_knowledge": [],
    }
    ctx.update(over)
    return ctx


def _work_item(**over):
    wi = {
        "id": "wi-1", "type": "story", "state": "in_progress",
        "feature_stream": "auth", "parent_id": None, "depends_on": ["wi-0"],
        "repo_id": None, "takeover_flag": False,
    }
    wi.update(over)
    return wi


def test_fixed_section_order():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    positions = [md.find(h) for h in _SECTION_ORDER]
    assert all(p != -1 for p in positions), "a section header is missing"
    assert positions == sorted(positions), "sections are out of the locked order"


def test_important_context_is_verbatim():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "ALWAYS prefer retrieval. This is verbatim steering." in md


def test_work_item_and_phase_rendered():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "- phase: prd" in md
    assert "- state: in_progress" in md
    assert "- depends_on: wi-0" in md


def test_artifacts_show_pointers_and_mcp_fetch_hint():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "get_artifact(artifact_id)" in md  # how to fetch via MCP
    assert "s3://b/req.md" in md  # pointer, not body
    assert "[requirements v1] a1" in md


def test_empty_sections_have_placeholders():
    ctx = _context(relevant_artifacts=[], recent_events=[])
    md = compose_manifest(context=ctx, work_item=_work_item(), phase="ideation")
    assert "# Retrieved Knowledge\n\n_none (Knowledge Index is Phase 4)_" in md
    # artifacts/events render the generic empty placeholder
    assert md.count("_none_") >= 2


def test_rules_section_uses_provided_text():
    md = compose_manifest(
        context=_context(), work_item=_work_item(), phase="prd", rules="RULE 3: zero hallucination."
    )
    assert "# Rules" in md and "RULE 3: zero hallucination." in md


def test_token_budget_truncates_oversized_section():
    big = "x" * 100_000  # ~25k tokens of important_context
    ctx = _context()
    ctx["profile"]["important_context"] = big
    budget = TokenBudget(important_context=50)  # cap hard
    md = compose_manifest(context=ctx, work_item=_work_item(), phase="prd", budget=budget)
    assert "[truncated to fit token budget]" in md
    # The 100k-char blob must not survive intact.
    assert big not in md


def test_artifact_count_capped():
    many = [
        {"id": f"a{i}", "type": "doc", "version": 1, "phase": "p", "status": "draft",
         "sor": "internal", "s3_key": f"s3://b/{i}", "external_ref": None}
        for i in range(50)
    ]
    md = compose_manifest(
        context=_context(relevant_artifacts=many), work_item=_work_item(), phase="prd",
        budget=TokenBudget(max_artifacts=10, relevant_artifacts=100_000),
    )
    assert "40 more not shown (budget)." in md


def test_estimate_tokens_is_monotonic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 4001) > estimate_tokens("a" * 4000)


@pytest.mark.django_db
def test_composes_from_real_get_context():
    """End-to-end with the real Platform-State get_context output (T5 → T7)."""
    from mcp_platform_state import tools

    from apps.projects.models import Project, ProjectProfile
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.tenancy.models import Tenant
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(
        tenant=t, project=project, important_context="verbatim ctx", domain="sdlc"
    )
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    tools.register_artifact(
        t.id, project.id, run.id, "requirements", "requirements", "internal", "h1"
    )

    ctx = tools.get_context(t.id, project.id, phase="prd")
    md = compose_manifest(context=ctx, work_item=tools._work_item(wi), phase="prd")

    for header in _SECTION_ORDER:
        assert header in md
    assert "verbatim ctx" in md
    assert "[requirements v1]" in md
