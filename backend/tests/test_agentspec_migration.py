"""P0-T10b — AgentSpec + command/settings migration (AGENT_MIGRATION_SPEC §5)."""
import re
from pathlib import Path

import pytest

from apps.projects.models import Project
from apps.registry.catalog import (
    ACTIVE_AGENT_CATALOG,
    AGENT_CATALOG,
    get_by_command,
    seed_agent_specs,
)
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from orchestration.trigger import TriggerError, TriggerResult, trigger_phase

_KEY_RE = re.compile(r"^\d{2}[a-z]?_[a-z0-9_]+$")
_LEGACY_AGENTS = Path(__file__).resolve().parents[2] / "legacy_suite" / "agents"


def test_keys_normalized_to_nn_name():
    for d in AGENT_CATALOG:
        assert _KEY_RE.match(d.key), f"key not NN_name: {d.key}"
        assert not d.key.endswith("_agent")  # dropped the v6 _agent suffix
        assert "-" not in d.key  # no hyphens


def test_v6_inconsistencies_fixed():
    by_key = {d.key: d for d in AGENT_CATALOG}
    # 10 security: hyphenated file, underscore key.
    assert by_key["10_security"].legacy_body_file == "10-security-agent.md"
    # 09b: dropped the _agent suffix.
    assert "09b_test_automation" in by_key
    # cicd: legacy settings pointed it at an agent file; now a normal phase trigger.
    assert get_by_command("cicd").key == "11_cicd"
    # prd: legacy ref used a hyphen; key is underscore.
    assert get_by_command("prd").key == "03_prd"


def test_legacy_body_files_exist():
    """Every MIGRATED catalog entry maps to a real legacy file (validates the fixes). Native
    agents (00e Document Vision) have no v6 source — they're excluded by construction."""
    for d in AGENT_CATALOG:
        if d.native:
            assert d.legacy_body_file == "", f"native agent {d.key} should have no legacy file"
            continue
        assert (_LEGACY_AGENTS / d.legacy_body_file).exists(), f"missing {d.legacy_body_file}"


def test_body_ref_points_at_migrated_location():
    assert get_by_command("prd").body_ref == "agents/03_prd/agent.md"


@pytest.mark.django_db
def test_seed_agent_specs_is_idempotent():
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    seed_agent_specs(t)  # upsert, no duplicates
    # Only active agents are seeded; retired ones (00d, D8) are excluded.
    assert AgentSpec.objects.filter(tenant=t).count() == len(ACTIVE_AGENT_CATALOG)
    assert not AgentSpec.objects.filter(tenant=t, key="00d_context_snapshot").exists()
    prd = AgentSpec.objects.get(tenant=t, key="03_prd")
    assert prd.body_ref == "agents/03_prd/agent.md"
    assert prd.recommended_engine == "claude"
    assert prd.recommended_model == "claude-sonnet-4-6"
    assert prd.phase_label == "prd"


@pytest.mark.django_db
def test_trigger_phase_creates_run_and_starts_workflow():
    t = Tenant.objects.create(name="Acme")
    seed_agent_specs(t)
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)

    calls = []
    result = trigger_phase(
        tenant_id=str(t.id), project_id=str(project.id), work_item_id=str(wi.id),
        agent_key="04_architecture", workflow_starter=lambda wf, inp: calls.append((wf, inp)),
    )
    assert isinstance(result, TriggerResult)
    run = Run.objects.get(id=result.run_id)
    assert run.status == Run.Status.PENDING
    assert run.temporal_workflow_id == result.workflow_id == f"agent-run-{run.id}"

    assert len(calls) == 1
    _wf, inp = calls[0]
    assert inp.phase == "architecture"
    assert inp.required_role == "architect"  # gate role from spec §7


@pytest.mark.django_db
def test_trigger_phase_unknown_agent_raises():
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="P")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    with pytest.raises(TriggerError):
        trigger_phase(
            tenant_id=str(t.id), project_id=str(project.id), work_item_id=str(wi.id),
            agent_key="99_nope", workflow_starter=lambda *a: None,
        )
