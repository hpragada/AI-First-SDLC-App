"""QA-19 — an application's inherited accessibility debt is reported until the team says stop.

Against the task's acceptance criteria:

  AC1  a project's first baseline run does not block the gate
  AC2  a later run, with enforcement enabled, blocks on real failures
  AC3  both states are covered, per project, independently

**Why AC1 needed building at all when it was already true.** An audit's problems belong to no
piece of work, and every one of the gate's three questions is scoped to the piece of work being
signed off — so they were never reachable from it. That is the right behaviour and it was true
*by accident of a filter*: nothing said so, and nothing tested it. The next widening of that
filter, for a perfectly good reason, would have turned a health check into a pipeline stop for
every brownfield client with no warning. `test_a_baseline_problem_does_not_stop_a_story_gate` is
the assertion that did not exist.

**The one thing that must not move.** A team building something new keeps being stopped by its
own accessibility failures — that is the whole of M1 and has nothing to do with inherited debt.
Every test here that turns enforcement on has a partner asserting a story's own failure still
behaves exactly as it did before.
"""
from __future__ import annotations

import pytest

from apps.a11y.backlog import BACKLOG_STREAM, BACKLOG_TITLE
from apps.a11y.baseline_report import baseline_body
from apps.a11y.defects import record_a11y_findings
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.policy import (
    A11yPolicyError,
    default_policy,
    describe_baseline_enforcement,
    describe_policy,
    enforces_baseline,
    policy_for,
    validate_policy,
)
from apps.gates.a11ygate import (
    A11Y_GATE_KEY,
    NOT_CHECKED_DETAIL,
    a11y_condition,
    baseline_debt,
    evaluate,
)
from apps.gates.conditions import ConditionContext
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    for number, handle, level in (("1.1.1", "Non-text Content", "A"),
                                  ("1.4.3", "Contrast (Minimum)", "AA")):
        WcagCriterion.objects.get_or_create(
            version="2.2", number=number,
            defaults={"handle": handle, "level": level, "slug": handle.lower(),
                      "text": f"{number} {handle}"})
    return {"t": str(tenant.id), "tenant": tenant}


def _project(world, name="Imported App"):
    project = Project.objects.create(tenant=world["tenant"], name=name)
    story = WorkItem.objects.create(tenant=world["tenant"], project=project, title="Checkout")
    return {"p": str(project.id), "project": project, "story": story}


@pytest.fixture
def app(world):
    return _project(world)


def _inherited(world, app, *, criterion="1.1.1", route="/admin", fingerprint="audit-1"):
    """A problem an audit found: no run behind it, exactly as QA-17 produces."""
    return A11yFinding.objects.create(
        tenant_id=world["t"], project_id=app["p"], fingerprint=fingerprint,
        route=route, selector="button.pay", criterion=criterion, criteria=[criterion],
        wcag_level="A", severity="critical", source=A11yFinding.Source.AI,
        outcome="failure", status=A11yFinding.Status.OPEN, evidence="no accessible name",
    )


def _from_a_story(world, app, *, fingerprint="story-1"):
    """A problem found while building: attached to the run, and so to the story."""
    spec = AgentSpec.objects.create(tenant_id=world["t"], key=f"09b-{fingerprint}",
                                    body_ref="x", semver="1.0.0")
    run = Run.objects.create(tenant_id=world["t"], work_item=app["story"], agent_spec=spec,
                             temporal_workflow_id=f"w-{fingerprint}")
    return A11yFinding.objects.create(
        tenant_id=world["t"], project_id=app["p"], fingerprint=fingerprint,
        route="/checkout", selector="img.hero", criterion="1.1.1", criteria=["1.1.1"],
        wcag_level="A", severity="critical", source=A11yFinding.Source.AI,
        outcome="failure", status=A11yFinding.Status.OPEN, evidence="filename as alt text",
        first_seen_run=run, last_seen_run=run,
    )


def _enforce(world, app, on=True):
    ProjectProfile.objects.update_or_create(
        tenant_id=world["t"], project_id=app["p"],
        defaults={"a11y": {"gate": {"block_on_baseline_debt": on}}})


def _gate(world, app):
    return evaluate(a11y_condition(), ConditionContext(
        tenant_id=world["t"], work_item_id=str(app["story"].id), project_id=app["p"]))


def _reconcile(world, app):
    return record_a11y_findings(tenant_id=world["t"], project_id=app["p"])


# ══ the setting ══════════════════════════════════════════════════════════════════════

def test_a_project_is_not_held_to_inherited_debt_unless_it_says_so():
    assert default_policy()["gate"]["block_on_baseline_debt"] is False
    assert enforces_baseline(default_policy()) is False


def test_a_project_can_choose_to_be_held_to_it():
    policy = validate_policy({"gate": {"block_on_baseline_debt": True}})
    assert enforces_baseline(policy) is True


def test_the_setting_must_be_yes_or_no():
    with pytest.raises(A11yPolicyError) as err:
        validate_policy({"gate": {"block_on_baseline_debt": "yes please"}})
    assert "true or false" in str(err.value)


def test_a_misspelled_setting_is_still_refused():
    """The allow-list that catches typos is the reason this lives in the policy at all — it
    must not have been widened into accepting anything."""
    with pytest.raises(A11yPolicyError) as err:
        validate_policy({"gate": {"block_on_baseline_dept": True}})
    assert "settings that do not exist" in str(err.value)


def test_turning_this_on_changes_nothing_else(world):
    """Every other setting keeps the value it had. A permissive default is only safe while it
    is the ONLY thing this touches."""
    plain = default_policy()
    enforcing = validate_policy({"gate": {"block_on_baseline_debt": True}})
    assert {k: v for k, v in enforcing["gate"].items() if k != "block_on_baseline_debt"} == \
        {k: v for k, v in plain["gate"].items() if k != "block_on_baseline_debt"}
    assert enforcing["target"] == plain["target"]


def test_the_policy_summary_says_which_mode_a_project_is_in():
    assert "reported only and do not stop work" in describe_policy(default_policy())
    assert "MUST be fixed" in describe_policy(
        validate_policy({"gate": {"block_on_baseline_debt": True}}))


def test_the_permissive_summary_still_says_new_work_is_held(world):
    """The sentence has to prevent the obvious misreading — that accessibility is switched off
    for this project."""
    assert "Problems introduced by new work still do." in \
        describe_baseline_enforcement(default_policy())


def test_the_setting_reaches_the_project_it_was_set_on(world, app):
    _enforce(world, app)
    assert enforces_baseline(policy_for(world["t"], app["p"])) is True


# ══ which defects count as inherited ═════════════════════════════════════════════════

def test_an_audits_problem_lands_in_the_projects_backlog(world, app):
    _inherited(world, app)
    _reconcile(world, app)
    [debt] = baseline_debt(tenant_id=world["t"], project_id=app["p"])
    assert debt["criterion"] == "1.1.1" and debt["route"] == "/admin"


def test_a_storys_own_problem_is_not_inherited_debt(world, app):
    _from_a_story(world, app)
    _reconcile(world, app)
    assert baseline_debt(tenant_id=world["t"], project_id=app["p"]) == []


def test_a_fixed_problem_stops_counting(world, app):
    finding = _inherited(world, app)
    _reconcile(world, app)
    A11yFinding.objects.filter(id=finding.id).update(status=A11yFinding.Status.RESOLVED)
    _reconcile(world, app)
    assert baseline_debt(tenant_id=world["t"], project_id=app["p"]) == []


def test_the_debt_comes_back_in_the_order_it_should_be_fixed_in(world, app):
    _inherited(world, app, criterion="1.4.3", route="/z", fingerprint="lesser")
    A11yFinding.objects.filter(fingerprint="lesser").update(severity="high")
    _inherited(world, app, criterion="1.1.1", route="/a", fingerprint="worst")
    _reconcile(world, app)
    assert [d["criterion"] for d in
            baseline_debt(tenant_id=world["t"], project_id=app["p"])] == ["1.1.1", "1.4.3"]


def test_another_projects_debt_is_not_this_projects(world, app):
    other = _project(world, "Another App")
    _inherited(world, other)
    _reconcile(world, other)
    assert baseline_debt(tenant_id=world["t"], project_id=app["p"]) == []
    assert baseline_debt(tenant_id=world["t"], project_id=other["p"])


# ══ AC1 — the first baseline stops nothing ═══════════════════════════════════════════

def test_a_baseline_problem_does_not_stop_a_story_gate(world, app):
    """**The assertion that did not exist.** True today by accident of scoping; true from now
    on by decision, and this is what would fail if somebody widened that scope."""
    _inherited(world, app)
    assert len(_reconcile(world, app)["opened"]) == 1, "it did open a tracked defect"

    result = _gate(world, app)
    assert result["key"] == A11Y_GATE_KEY
    assert result["satisfied"] is True


def test_the_gate_says_the_debt_is_there_rather_than_passing_quietly(world, app):
    """A green gate on an application with known problems must not look identical to a green
    gate on one with none (D-A11Y-3, one level up)."""
    _inherited(world, app)
    _reconcile(world, app)
    detail = _gate(world, app)["detail"]
    assert "1 open accessibility problem(s) inherited from its baseline audit" in detail
    assert "do not block" in detail
    assert "baseline enforcement is off" in detail


def test_a_project_with_no_debt_says_nothing_about_it(world, app):
    assert "inherited" not in _gate(world, app).get("detail", "")


def test_both_reasons_are_given_when_both_are_true(world, app):
    """A story with no UI, in a project carrying inherited debt. Dropping either note would
    leave a reviewer approving over something unsaid."""
    _inherited(world, app)
    _reconcile(world, app)
    detail = _gate(world, app)["detail"]
    assert "inherited from its baseline audit" in detail
    assert NOT_CHECKED_DETAIL in detail


# ══ AC2 — enforcement turns the same list into a rule ════════════════════════════════

def test_turning_enforcement_on_blocks_on_the_inherited_problems(world, app):
    _inherited(world, app)
    _reconcile(world, app)
    assert _gate(world, app)["satisfied"] is True, "off by default"

    _enforce(world, app)
    result = _gate(world, app)
    assert result["satisfied"] is False
    assert "1 accessibility problem(s) from this application's baseline" in result["detail"]


def test_the_blocking_message_names_the_way_out(world, app):
    """Enforcement is project-wide and blunt on purpose. A reviewer who cannot ship needs to
    know both routes forward, not just that the answer is no."""
    _inherited(world, app)
    _reconcile(world, app)
    _enforce(world, app)
    detail = _gate(world, app)["detail"]
    assert "Fix them, or turn baseline enforcement off" in detail
    assert "1.1.1 on /admin" in detail, "and what to fix"


def test_enforcement_with_nothing_inherited_blocks_nothing(world, app):
    _enforce(world, app)
    assert _gate(world, app)["satisfied"] is True


def test_fixing_the_debt_opens_the_gate_again(world, app):
    finding = _inherited(world, app)
    _reconcile(world, app)
    _enforce(world, app)
    assert _gate(world, app)["satisfied"] is False

    A11yFinding.objects.filter(id=finding.id).update(status=A11yFinding.Status.RESOLVED)
    _reconcile(world, app)
    assert _gate(world, app)["satisfied"] is True


def test_turning_enforcement_back_off_reports_instead_of_blocking(world, app):
    _inherited(world, app)
    _reconcile(world, app)
    _enforce(world, app)
    assert _gate(world, app)["satisfied"] is False

    _enforce(world, app, on=False)
    result = _gate(world, app)
    assert result["satisfied"] is True and "do not block" in result["detail"]


# ══ AC3 — per project, independently ═════════════════════════════════════════════════

def test_one_project_enforcing_does_not_hold_another_shut(world, app):
    """The edge case the task names: a second project's first baseline is informational on its
    own terms, whatever the first project decided."""
    other = _project(world, "Another App")
    _inherited(world, app, fingerprint="app-debt")
    _inherited(world, other, fingerprint="other-debt")
    _reconcile(world, app)
    _reconcile(world, other)
    _enforce(world, app)

    assert _gate(world, app)["satisfied"] is False, "the one that opted in"
    assert _gate(world, other)["satisfied"] is True, "the one that did not"


def test_an_unreadable_policy_falls_back_to_reporting_not_blocking(world, app):
    """`policy_or_default` never raises, and the default is permissive here — a project whose
    settings nobody can read must not have every gate held shut by inherited debt."""
    _inherited(world, app)
    _reconcile(world, app)
    ProjectProfile.objects.update_or_create(
        tenant_id=world["t"], project_id=app["p"],
        defaults={"a11y": {"gate": {"nonsense": True}}})
    assert _gate(world, app)["satisfied"] is True


# ══ the thing that must not have moved ═══════════════════════════════════════════════

def test_a_storys_own_failure_still_stops_its_gate(world, app):
    """M1's behaviour, unchanged. If this ever passes, the accessibility gate has stopped
    doing the job it was built for."""
    _from_a_story(world, app)
    _reconcile(world, app)
    result = _gate(world, app)
    assert result["satisfied"] is False
    assert "1 accessibility failure(s) still open" in result["detail"]


def test_a_storys_own_failure_stops_it_whether_or_not_baseline_debt_is_enforced(world, app):
    _from_a_story(world, app)
    _reconcile(world, app)
    for on in (False, True):
        _enforce(world, app, on=on)
        assert _gate(world, app)["satisfied"] is False, f"enforcement={on}"


def test_a_greenfield_project_never_touches_this_path(world, app):
    """Nothing inherited, nothing to ask about — the new question costs a project that has
    only ever built things nothing at all."""
    _from_a_story(world, app)
    _reconcile(world, app)
    assert baseline_debt(tenant_id=world["t"], project_id=app["p"]) == []
    assert not WorkItem.objects.filter(
        tenant_id=world["t"], feature_stream=BACKLOG_STREAM).exists()


def test_the_story_failure_is_reported_before_the_inherited_one(world, app):
    """When both are true the reviewer is told about their own work first — it is the thing
    they can act on now."""
    _inherited(world, app)
    _from_a_story(world, app)
    _reconcile(world, app)
    _enforce(world, app)
    detail = _gate(world, app)["detail"]
    assert detail.startswith("1 accessibility failure(s) still open")


# ══ the baseline document says which mode the project is in ══════════════════════════

def test_the_baseline_document_says_the_backlog_does_not_stop_work(world, app):
    _inherited(world, app)
    body = baseline_body(tenant_id=world["t"], project_id=app["p"])
    assert "**These do not currently stop any work.**" in body
    assert "turn baseline enforcement on" in body


def test_the_baseline_document_says_when_it_does(world, app):
    _inherited(world, app)
    _enforce(world, app)
    body = baseline_body(tenant_id=world["t"], project_id=app["p"])
    assert "**These currently stop work.**" in body


def test_the_backlog_container_is_still_the_visible_one(world, app):
    """The container is how "inherited" is recognised. If it ever became a hidden carrier the
    gate would silently stop seeing the debt it is meant to enforce."""
    from integrations.onboarding import carrier_q

    _inherited(world, app)
    _reconcile(world, app)
    visible = WorkItem.objects.filter(
        tenant_id=world["t"], feature_stream=BACKLOG_STREAM).exclude(carrier_q())
    assert [item.title for item in visible] == [BACKLOG_TITLE]
