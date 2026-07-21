"""P3-09b B3 — materialize test-case WorkItems from a Testing run's `test_case` artifacts."""
import pytest

from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from apps.workitems.test_cases import automation_status_for, materialize_test_cases


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    story = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY,
                                    title="Checkout", feature_stream="checkout")
    spec = AgentSpec.objects.create(tenant=t, key="09_testing", body_ref="x")
    return {"t": t, "p": p, "story": story, "spec": spec}


def _run(world):
    return Run.objects.create(tenant=world["t"], work_item=world["story"],
                              agent_spec=world["spec"])


def _tc_artifact(world, run, *, tc_id=None, title=""):
    return Artifact.objects.create(
        tenant=world["t"], project=world["p"], run=run, phase="testing", type="test_case",
        title=title, external_ref=({"tc_id": tc_id} if tc_id else None),
    )


def _children(world):
    return WorkItem.objects.filter(parent_id=world["story"].id, type=WorkItem.Type.TEST_CASE)


def test_creates_one_test_case_wi_per_artifact(world):
    run = _run(world)
    _tc_artifact(world, run, tc_id="TC-014", title="TC-014 — Expired card")
    _tc_artifact(world, run, tc_id="TC-015", title="TC-015 — Valid card")

    out = materialize_test_cases(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 run_id=str(run.id), story_id=str(world["story"].id))
    assert out == {"created": 2, "updated": 0, "skipped": 0}

    kids = {w.external_ref["tc_id"]: w for w in _children(world)}
    assert set(kids) == {"TC-014", "TC-015"}
    tc14 = kids["TC-014"]
    # The WI inherits the story's stream + carries a pointer to its own test_case artifact.
    assert tc14.feature_stream == "checkout"
    assert tc14.external_ref["test_case_artifact_id"]
    assert tc14.title == "TC-014 — Expired card"


def test_tc_id_recovered_from_title_when_ref_absent(world):
    run = _run(world)
    _tc_artifact(world, run, title="TC009 Checkout guest")   # no external_ref
    materialize_test_cases(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                           run_id=str(run.id), story_id=str(world["story"].id))
    # Digits preserved (TC009 → TC-009), never re-padded to TC-9.
    assert _children(world).get().external_ref["tc_id"] == "TC-009"


def test_rerun_updates_pointer_not_duplicates(world):
    run1 = _run(world)
    _tc_artifact(world, run1, tc_id="TC-014", title="TC-014 — Expired card")
    materialize_test_cases(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                           run_id=str(run1.id), story_id=str(world["story"].id))

    # A second Testing run re-registers the same TC as a NEW artifact.
    run2 = _run(world)
    new_art = _tc_artifact(world, run2, tc_id="TC-014", title="TC-014 — Expired card (v2)")
    out = materialize_test_cases(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 run_id=str(run2.id), story_id=str(world["story"].id))
    assert out == {"created": 0, "updated": 1, "skipped": 0}
    assert _children(world).count() == 1        # never duplicated
    wi = _children(world).get()
    assert wi.title == "TC-014 — Expired card (v2)"
    assert wi.external_ref["test_case_artifact_id"] == str(new_art.id)   # repointed


def test_untitled_untagged_case_is_skipped_not_orphaned(world):
    run = _run(world)
    _tc_artifact(world, run, title="")      # no tc_id, no title → unmatchable
    out = materialize_test_cases(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                                 run_id=str(run.id), story_id=str(world["story"].id))
    assert out["skipped"] == 1 and _children(world).count() == 0


# ── B6: automation status from the test case's 09b run ───────────────
def _tc_wi(world):
    return WorkItem.objects.create(tenant=world["t"], project=world["p"], parent=world["story"],
                                   type=WorkItem.Type.TEST_CASE, title="TC-014")


def _tc_run(world, tc, status):
    spec, _ = AgentSpec.objects.get_or_create(
        tenant=world["t"], key="09b_test_automation", defaults={"body_ref": "x"})
    return Run.objects.create(tenant=world["t"], work_item=tc, agent_spec=spec, status=status)


def test_automation_status_none_generating_ready(world):
    tc = _tc_wi(world)
    assert automation_status_for(tc) == "not_automated"     # no 09b run yet

    _tc_run(world, tc, Run.Status.RUNNING)
    assert automation_status_for(tc) == "generating"

    _tc_run(world, tc, Run.Status.AWAITING_GATE)            # newer run, executed
    assert automation_status_for(tc) == "ready"


def test_automation_status_ignores_non_09b_runs(world):
    tc = _tc_wi(world)
    other = AgentSpec.objects.create(tenant=world["t"], key="07_implementation", body_ref="x")
    Run.objects.create(tenant=world["t"], work_item=tc, agent_spec=other,
                       status=Run.Status.COMPLETED)
    assert automation_status_for(tc) == "not_automated"     # a non-09b run doesn't count
