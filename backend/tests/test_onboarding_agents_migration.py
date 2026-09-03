"""P4 — migrated onboarding/intelligence agents (AGENT_MIGRATION_SPEC §2/3/6/8).

Verifies the 75/15/10 migration on the real bodies: reasoning preserved verbatim, every
reference rerouted to the platform (engine -> the codeintel.* capability; outputs ->
registered artifacts + the Knowledge Index; codebase -> the companion worktree; Human Gate
removed), the §8 sweep clean, gate roles correct, and the AgentSpec resolves.

Covers 00c Intelligent Context Extractor, 00 Onboarding, and 00b Context Bridge.
(00d Snapshot is retired — see the test below.)
"""
from pathlib import Path

import pytest

from apps.registry.catalog import get_by_key, seed_agent_specs
from apps.registry.models import AgentSpec
from apps.tenancy.models import Tenant

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _REPO_ROOT / "agents"
_KEYS = ["00c_intelligent_context_extractor", "00_onboarding", "00b_context_bridge"]

_FORBIDDEN = [
    ".md", "docs/", "claude.md", "tasks.md", "reply approved", "/sdlc:",
    "rule-behavior", "rule-execution", "session-snapshot",
]

_REASONING = {
    "00c_intelligent_context_extractor": [
        "Codebase Intelligence Architect", "Software Design X-Rays", "Chidamber & Kemerer",
        "Lehman", "hotspot", "measured", "Tier-3",
    ],
    "00_onboarding": [
        "Senior Technical Programme Manager", "BABOK v3", "IEEE 830",
        "Working Effectively with Legacy Code", "characterisation test",
        "Fidelity to Source",
    ],
    "00b_context_bridge": [
        "Principal Integration Architect", "OpenAPI Specification 3.1", "contract mismatch",
        "Data Transfer Object", "Semantic Versioning 2.0.0", "ground truth from code",
    ],
}


def _body(key: str) -> str:
    return (_AGENTS / key / "agent.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("key", _KEYS)
def test_migrated_body_exists(key):
    assert (_AGENTS / key / "agent.md").is_file()


@pytest.mark.parametrize("key", _KEYS)
def test_reference_sweep_is_clean(key):
    body = _body(key).lower()
    hits = [tok for tok in _FORBIDDEN if tok in body]
    assert not hits, f"{key}: forbidden references survived: {hits}"


@pytest.mark.parametrize("key", _KEYS)
def test_reasoning_preserved_verbatim(key):
    body = _body(key)
    for needle in _REASONING[key]:
        assert needle in body, f"{key}: lost reasoning {needle!r} (75% reuse broken)"


def test_00c_reroutes_to_codeintel_knowledge_and_artifacts():
    body = _body("00c_intelligent_context_extractor")
    # inputs/engine rerouted to the capability + the worktree
    assert "codeintel" in body and "worktree" in body
    assert "get_overview" in body and "get_risk" in body          # the 8-tool surface
    assert "# Relevant Artifacts" in body and "# Rules" in body
    # outputs rerouted to platform artifacts + the Knowledge Index (no docs/intelligence/*.md)
    assert "register_artifact" in body and "add_trace_edge" in body
    assert "Knowledge Index" in body
    for art in ["codebase_intelligence", "dependency_graph", "git_analytics",
                "dead_code", "architecture_decisions"]:
        assert art in body, f"00c missing rerouted artifact type {art!r}"
    # no repowise install glue / human-gate glue survives
    assert "pip install" not in body and "repowise init" not in body
    assert "Reply APPROVED" not in body


def test_00c_body_matches_what_the_platform_actually_does():
    """B6 — the migrated body described three things that were not true, and an agent working
    from wrong instructions makes wrong decisions confidently:

    1. it told the agent to index artifacts into the Knowledge Index — no such tool exists, and
       measured after run 98ab9a8c the chunk count for its seven artifacts was 0;
    2. it called `search_codebase` "semantic" when it is keyword matching, so an empty result
       was read as "this codebase has no authentication";
    3. it promised a Tech Lead review gate, but onboarding runs headless and opens none.
    """
    body = _body("00c_intelligent_context_extractor")
    # 1 — the platform indexes on registration; the agent is told so, not asked to do it.
    assert "platform indexes each registered body" in body.lower()
    # 2 — the tool is described as what it is, with the trap named.
    assert "not semantic" in body.lower() or "This is not semantic search" in body
    assert "index_health" in body and "index_report" in body     # degraded reads are checkable
    assert "unavailable, not zero" in body                       # the S4-8 lesson, stated
    # 3 — no gate is promised in a headless phase.
    assert "headless" in body.lower()
    assert "Tech Lead" not in body
    # the four trace-edge values are named, so the agent never has to guess (B2)
    assert "`derives`" in body
    # signatures match the real tools: `frm` (not the reserved word `from`), and index() takes
    # no `workspace` — an agent following the old text literally fails the call outright.
    assert "get_dependency_path(frm, to)" in body
    assert "get_dependency_path(repo, from, to)" not in body
    assert "index(workspace=" not in body


def test_00c_resolves_anomalies_instead_of_forwarding_them():
    """S4-24 — run bf0f27c0 reported a backend module importing a frontend file and asked the
    READER to go and check it. The agent had `Read`/`Grep` over the worktree and could have
    settled it in one call; it also had `ask_human`, which the body never mentioned at all.

    An unresolved anomaly forwarded as a finding is the worst of both: the user does the work,
    and the artifact still carries the wrong data — downstream agents read the artifact, not
    the caveat. The body must name all three routes and rank them.
    """
    body = _body("00c_intelligent_context_extractor")
    # the clarification channel exists and is now reachable from the instructions
    assert "ask_human" in body, "00c never tells the agent the clarification channel exists"
    # self-verification comes FIRST — asking a human what the code can answer stalls a
    # headless run on a question the user would have to read the code to answer
    verify_at = body.find("answer it yourself")
    ask_at = body.find("ask_human")
    assert verify_at != -1 and verify_at < ask_at, "self-verification must precede ask_human"
    # and the fallback when neither settles it
    assert "assumption" in body.lower()
    # the gate keeps it honest at completion time
    assert "none passed to the reader unresolved" in body


def test_00c_gate_role_is_tech_lead():
    assert get_by_key("00c_intelligent_context_extractor").gate_role == "tech_lead"


def test_00_reroutes_to_registered_evidence_and_gap_report():
    body = _body("00_onboarding")
    # discovery reads what the PLATFORM registered — the manifest + the registry read tools.
    assert "get_artifact_body" in body and "list_artifacts" in body
    assert "list_work_items" in body
    assert "# Relevant Artifacts" in body and "# Rules" in body
    # register-don't-recreate reasoning preserved; the Knowledge Index is stated as the platform's
    # job, not asked of the agent (B6 wording, S5-12)
    assert "register-don't-recreate" in body and "Knowledge Index" in body
    assert "platform indexes each registered body" in body.lower()
    # the gap analysis is a gap_report artifact, with a resume phase
    assert "gap_report" in body and "resume phase" in body.lower()
    # no interactive-checklist / human-gate / next-command glue survives
    assert "STOP HERE" not in body and "Reply APPROVED" not in body
    assert "Next command" not in body and "Human Gate" not in body


def test_00_names_the_tool_that_actually_writes_the_report():
    """S5-1 — `submit_gap_report` is built, granted (runner.BUILD_STATE_TOOLS) and wired end to
    end, and the body never mentioned it once. Worse, it told the agent the OPPOSITE: that the
    platform computes the assessment and the agent's job is to 'verify and correct' it. Nothing
    pre-generates a report on the agent path, so the agent found nothing to verify, and `gap.ready`
    stayed false forever. The old test passed on the word "gap_report" appearing anywhere in prose,
    which is why this survived."""
    body = _body("00_onboarding")
    assert "submit_gap_report" in body, "00_onboarding never names the tool that writes its report"
    # called ONCE, at the end — not written into a document (the ideation-class adherence risk)
    assert "exactly once" in body.lower()
    # and the contract is inline, so the shape is never guessed
    for key in ["ideation", "task_breakdown", "code_review", "cicd", "deployment"]:
        assert key in body, f"phase key {key!r} missing from the submit contract"
    assert '"complete"' in body and '"partial"' in body and '"missing"' in body
    # the platform-computes-it-for-you instruction is gone
    assert "verify and correct" not in body.lower()


def test_00_does_not_promise_code_access_it_does_not_have():
    """S5-2 — `00_onboarding` runs with `reads_code=False`: no worktree, an empty temp cwd, no
    `codeintel.*` server, and Read/Grep/Glob/Bash hard-denied by `_PLANNING_DISALLOWED_TOOLS`. The
    body instructed worktree + `codeintel.*` work in four places, including the fallback used when
    00c never ran — the one case with no other source of code facts. Code evidence comes from 00c's
    registered artifacts, which are pinned into the manifest (S5-11)."""
    body = _body("00_onboarding")
    assert "codeintel" not in body, "00_onboarding cannot call codeintel.* — it has no such server"
    assert "search_codebase" not in body
    # `worktree` may only appear as a denial, never as an instruction
    for line in body.splitlines():
        if "worktree" in line:
            assert "no worktree" in line.lower(), f"body still directs worktree work: {line!r}"
    # the intelligence artifacts it reads INSTEAD are named
    for art in ["codebase_intelligence", "dependency_graph", "git_analytics",
                "dead_code", "architecture_decisions"]:
        assert art in body, f"00 missing code-evidence source {art!r}"
    # and 00c is a stated prerequisite, not an optional nicety
    assert "prerequisite" in body.lower()


def test_00_does_not_call_capabilities_no_agent_can_reach():
    """S5-10 — `docstore.*` / `tasktracker.*` / `designsource.*` / `testmgmt.*` are backend-only
    Python Protocols (integrations/capabilities.py). No MCP tool wraps any of them, and none appear
    in BUILD_STATE_TOOLS. The body told the agent to 'refresh detail through the capability' and
    named `designsource.get_design_context()` by name. The reachable route is the registry."""
    body = _body("00_onboarding")
    for cap in ["docstore.", "tasktracker.", "designsource.", "testmgmt."]:
        assert cap not in body, f"00 still instructs an uncallable capability {cap!r}"
    assert "registered artifacts, not as live connectors" in body


def test_00_assesses_only_and_registers_no_lifecycle_content():
    """Team decision 2026-08-03 (option c): 00_onboarding assesses and reports. It does NOT
    transform source material into requirements/PRD/architecture drafts.

    Why it matters: onboarding runs on a carrier work item, and `publish_artifacts` publishes every
    run-scoped artifact. Under the old body the drafts it was told would 'publish only on the gate'
    were published with no review, while the gap report — the one thing built for review — was
    never published at all. Transformation belongs to the phase agents, each already gated."""
    body = _body("00_onboarding")
    assert "register no lifecycle content" in body
    assert "assumption" in body.lower()
    # the transformation instructions are gone
    assert "Transformation Rules" not in body
    assert "Translate Jira tickets into User Story format" not in body
    assert "Translate architecture diagrams into ADR format" not in body
    # `register_artifact` survives for the assumption log ONLY, and says so
    assert "only** artifact type this agent registers" in body


def test_00_describes_a_gate_that_actually_opens():
    """S5-14 — the body promised a Product Owner gate while the run was headless. It is now
    genuinely gated (`_GATED_ONBOARDING_AGENTS`), and approval is what publishes the report."""
    body = _body("00_onboarding")
    assert "Product Owner" in body and "review gate" in body
    assert "headless" not in body.lower()


def test_00_resolves_anomalies_instead_of_forwarding_them():
    """S5-13 — the S4-24 rule, weighted for THIS agent. 00c was told to verify from the code first
    because it had Read/Grep. 00_onboarding has no file tools at all, so the first route is the
    registry and `ask_human` carries far more of the load."""
    body = _body("00_onboarding")
    assert "ask_human" in body, "00 never tells the agent the clarification channel exists"
    verify_at = body.find("answer it yourself")
    ask_at = body.find("ask_human")
    assert verify_at != -1 and verify_at < ask_at, "self-service from the registry must precede ask"
    assert "none passed to the reader unresolved" in body


def test_00_gate_role_is_product_owner():
    assert get_by_key("00_onboarding").gate_role == "product_owner"


def test_00b_reroutes_to_api_contract_artifact_and_read_through():
    body = _body("00b_context_bridge")
    # the copied bridge file is replaced by a versioned registry artifact (M2/D4)
    assert "api_contract" in body and "CONTEXT-BRIDGE" not in body
    assert "register_artifact" in body and "semver" in body.lower()
    # Import is replaced by read-through + a cross-repo implements edge
    assert "read-through" in body.lower() and "get_artifact" in body
    assert "add_trace_edge" in body and "implements" in body
    # extraction rerouted to the worktree + code-intel, inputs from the platform
    assert "worktree" in body and "codeintel" in body
    assert "# Relevant Artifacts" in body and "# Rules" in body
    assert "Knowledge Index" in body
    # version bump is the drift signal; no copied-file / human-gate glue survives
    assert "drift" in body.lower()
    assert "Reply APPROVED" not in body and "Human Gate" not in body
    assert "STOP." not in body and "Next command" not in body


def test_00b_gate_role_is_architect():
    assert get_by_key("00b_context_bridge").gate_role == "architect"


def test_00d_snapshot_is_retired():
    """00d Snapshot is retired (continuity = platform DB + Temporal resumable runs, D8):
    no agent body is authored, the catalog flags it retired, and it is never seeded."""
    from apps.registry.catalog import is_retired

    assert not (_AGENTS / "00d_context_snapshot" / "agent.md").exists()
    assert get_by_key("00d_context_snapshot").retired is True
    assert is_retired("00d_context_snapshot") is True
    # the live agents are not flagged retired
    assert all(not get_by_key(k).retired for k in _KEYS)


@pytest.mark.django_db
def test_retired_agent_is_not_seeded():
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    assert not AgentSpec.objects.filter(tenant=t, key="00d_context_snapshot").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("key", _KEYS)
def test_seeded_agentspec_resolves_to_migrated_body(key):
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key=key)
    assert spec.body_ref == f"agents/{key}/agent.md"
    assert (_REPO_ROOT / spec.body_ref).is_file()
