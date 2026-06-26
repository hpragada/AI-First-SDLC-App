"""P4 — migrated onboarding/intelligence agents (AGENT_MIGRATION_SPEC §2/3/6/8).

Verifies the 75/15/10 migration on the real bodies: reasoning preserved verbatim, every
reference rerouted to the platform (engine -> the codeintel.* capability; outputs ->
registered artifacts + the Knowledge Index; codebase -> the companion worktree; Human Gate
removed), the §8 sweep clean, gate roles correct, and the AgentSpec resolves.

Covers 00c Intelligent Context Extractor and 00 Onboarding; 00b Context Bridge is appended
as its migration task lands. (00d Snapshot is retired — see the test below.)
"""
from pathlib import Path

import pytest

from apps.registry.catalog import get_by_key, seed_agent_specs
from apps.registry.models import AgentSpec
from apps.tenancy.models import Tenant

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _REPO_ROOT / "agents"
_KEYS = ["00c_intelligent_context_extractor", "00_onboarding"]

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


def test_00c_gate_role_is_tech_lead():
    assert get_by_key("00c_intelligent_context_extractor").gate_role == "tech_lead"


def test_00_reroutes_to_sors_intel_and_gap_report():
    body = _body("00_onboarding")
    # discovery rerouted to the connected SoRs + code-intel + the worktree (no local files)
    assert "docstore" in body and "tasktracker" in body
    assert "codeintel" in body and "worktree" in body
    assert "get_artifact" in body and "# Relevant Artifacts" in body and "# Rules" in body
    # register-don't-recreate + reconcile reasoning preserved, rerouted to platform writes
    assert "register-don't-recreate" in body and "register_artifact" in body
    assert "add_trace_edge" in body and "Knowledge Index" in body
    # the gap analysis is now a gap_report artifact, with a resume phase
    assert "gap_report" in body and "resume phase" in body.lower()
    # no interactive-checklist / human-gate / next-command glue survives
    assert "STOP HERE" not in body and "Reply APPROVED" not in body
    assert "Next command" not in body and "Human Gate" not in body


def test_00_gate_role_is_product_owner():
    assert get_by_key("00_onboarding").gate_role == "product_owner"


def test_00d_snapshot_is_retired():
    """00d Snapshot is retired (continuity = platform DB + Temporal resumable runs, D8):
    no agent body is authored for it."""
    assert not (_AGENTS / "00d_context_snapshot" / "agent.md").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("key", _KEYS)
def test_seeded_agentspec_resolves_to_migrated_body(key):
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    spec = AgentSpec.objects.get(tenant=t, key=key)
    assert spec.body_ref == f"agents/{key}/agent.md"
    assert (_REPO_ROOT / spec.body_ref).is_file()
