"""QA-08 — the project's accessibility policy, reviewer role and WCAG target.

Against the task's acceptance criteria:

  AC1  an admin can set which severities block and the confidence bar, and save it
  AC2  the accessibility reviewer role exists and can be assigned (mapped to QA Lead, D7)
  AC3  a project with no policy reads back the documented default
  AC4  ≥ 90% coverage on the new code

**What these tests are really guarding.** The policy is read in two places that must never
fail — while a gate is opening, and while defects are reconciled — so the interesting cases are
all about being wrong: a typo in the JSON, a severity word that no finding can carry, a project
that switches on a design question that does not exist. Every one of those is either refused at
the API (where a person is reading the error) or falls back to the *documented default* with the
reason attached (where a workflow is running). The tests assert both halves of that split.

**The severity vocabulary is asserted on purpose.** The backlog said "block on Critical/Serious";
`serious` is axe's word and no finding in the ledger can hold it, so a policy naming it is
rejected with a message that says where that word does belong. That test is the correction.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.a11y.defects import record_a11y_findings
from apps.a11y.findings import SEVERITY_BY_LEVEL, record_run_findings
from apps.a11y.models import A11yFinding, WcagCriterion
from apps.a11y.policy import (
    ACCESSIBILITY_REVIEWER_ROLE,
    DEFAULT_TARGET,
    SEVERITIES,
    TARGET_LEVELS,
    A11yPolicyError,
    blocks,
    default_policy,
    describe_policy,
    extra_design_criteria,
    policy_for,
    policy_or_default,
    severities_for_target,
    stored_policy,
    validate_policy,
)
from apps.a11y.report import SOURCE_AI, SOURCE_RULE, MergedReport, ReportRow
from apps.a11y.triage import TRIAGE_FAILURE
from apps.base import Role
from apps.gates.conditions import conditions_for_phase
from apps.gates.wcag import (
    DESIGN_CHECKS,
    NOT_ASKED,
    OPTIONAL_DESIGN_CHECKS,
    ChecklistGap,
    describe_checklist,
    explain,
    verify_complete,
    wcag_aa_checklist,
)
from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import gate_role_for, gate_roles
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_FAIL


@pytest.fixture
def client():
    return APIClient()


def _hdr(tenant_id):
    return {"HTTP_X_TENANT_ID": str(tenant_id)}


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    # S.No 214: editing the project profile — which is what the accessibility policy lives in —
    # takes tech_lead/admin on the project. It steers every agent that runs there, so the two
    # policy tests below now sign in as the admin their names always claimed they were.
    admin = User.objects.create_user(email="admin@acme.test", name="Admin", tenant=tenant,
                                     password="pw")
    Membership.objects.create(tenant=tenant, user=admin, project=project, role="admin")
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "admin": admin}


def _profile(world, a11y):
    return ProjectProfile.objects.create(
        tenant=world["tenant"], project=world["project"], a11y=a11y)


# ══ AC3 — the documented default ══════════════════════════════════════════════════

def test_the_default_is_aa_blocking_critical_and_high():
    policy = default_policy()
    assert policy["target"] == DEFAULT_TARGET == "wcag_2.2_aa"
    assert policy["gate"]["block_severities"] == ["critical", "high"]
    assert policy["gate"]["min_confidence"] == 0.0
    assert policy["gate"]["block_on_incomplete_run"] is True
    assert policy["gate"]["design_checks"] == {"extra_criteria": []}


def test_the_default_severities_are_derived_from_the_standard_not_typed_twice():
    """AA covers Level A and AA, and those levels' severities come from one mapping."""
    assert severities_for_target("wcag_2.2_aa") == (
        SEVERITY_BY_LEVEL["A"], SEVERITY_BY_LEVEL["AA"])


@pytest.mark.parametrize("target,expected", [
    ("wcag_2.2_a", ["critical"]),
    ("wcag_2.2_aa", ["critical", "high"]),
    ("wcag_2.2_aaa", ["critical", "high", "medium"]),
])
def test_the_target_decides_what_blocks(target, expected):
    assert validate_policy({"target": target})["gate"]["block_severities"] == expected


@pytest.mark.parametrize("empty", [None, "", {}])
def test_an_empty_policy_reads_back_as_the_default(empty):
    assert validate_policy(empty) == default_policy()


def test_a_project_with_no_profile_reads_the_default(world):
    assert stored_policy(world["t"], world["p"]) == {}
    assert policy_for(world["t"], world["p"]) == default_policy()


def test_a_profile_with_no_a11y_block_reads_the_default(world):
    _profile(world, {})
    assert policy_for(world["t"], world["p"]) == default_policy()


# ══ AC1 — the settings, and how they overlay ══════════════════════════════════════

def test_setting_only_the_target_moves_the_severities_with_it():
    policy = validate_policy({"target": "wcag_2.2_aaa"})
    assert policy["gate"]["block_severities"] == ["critical", "high", "medium"]


def test_setting_only_the_confidence_bar_keeps_the_derived_severities():
    policy = validate_policy({"gate": {"min_confidence": 0.8}})
    assert policy["gate"]["min_confidence"] == 0.8
    assert policy["gate"]["block_severities"] == ["critical", "high"]
    assert policy["gate"]["block_on_incomplete_run"] is True


def test_naming_the_severities_overrides_the_target_deliberately():
    policy = validate_policy(
        {"target": "wcag_2.2_aaa", "gate": {"block_severities": ["critical"]}})
    assert policy["target"] == "wcag_2.2_aaa"
    assert policy["gate"]["block_severities"] == ["critical"]


def test_severities_are_normalised_and_kept_in_severity_order():
    policy = validate_policy({"gate": {"block_severities": ["HIGH", "high", " critical "]}})
    assert policy["gate"]["block_severities"] == ["critical", "high"]


def test_blocking_nothing_is_a_real_choice_not_an_accident():
    """Report-only. A typo can never land here — an unknown word is refused by name below."""
    assert validate_policy({"gate": {"block_severities": []}})["gate"]["block_severities"] == []


def test_a_target_is_read_case_and_space_insensitively():
    assert validate_policy({"target": "  WCAG_2.2_AA "})["target"] == "wcag_2.2_aa"


def test_the_policy_can_be_read_back_from_the_project(world):
    _profile(world, {"target": "wcag_2.2_a", "gate": {"min_confidence": 0.9}})
    policy = policy_for(world["t"], world["p"])
    assert policy["target"] == "wcag_2.2_a"
    assert policy["gate"]["block_severities"] == ["critical"]
    assert policy["gate"]["min_confidence"] == 0.9


def test_one_project_never_reads_another_projects_policy(world):
    other = Project.objects.create(tenant=world["tenant"], name="Other")
    _profile(world, {"target": "wcag_2.2_aaa"})
    assert policy_for(world["t"], str(other.id)) == default_policy()


def test_one_tenant_never_reads_another_tenants_policy(world):
    _profile(world, {"target": "wcag_2.2_aaa"})
    stranger = Tenant.objects.create(name="Rival")
    assert stored_policy(str(stranger.id), world["p"]) == {}


# ══ Validation — every way a policy can be wrong ══════════════════════════════════

def test_the_scanners_own_word_is_refused_with_an_explanation():
    """The backlog said 'Critical/Serious'. `serious` is axe's `impact`, not a finding's
    severity, and a policy naming it would block on nothing the AI pass produces."""
    with pytest.raises(A11yPolicyError) as exc:
        validate_policy({"gate": {"block_severities": ["critical", "serious"]}})
    assert "serious" in str(exc.value)
    assert "impact" in str(exc.value), "the message has to say where that word does belong"


def test_an_unknown_target_is_refused():
    with pytest.raises(A11yPolicyError, match="conformance target"):
        validate_policy({"target": "wcag_2.1_aa"})


@pytest.mark.parametrize("raw", ["a string", 7, ["a", "list"]])
def test_a_policy_that_is_not_an_object_is_refused(raw):
    with pytest.raises(A11yPolicyError, match="must be an object"):
        validate_policy(raw)


def test_a_setting_that_does_not_exist_is_refused_rather_than_ignored():
    with pytest.raises(A11yPolicyError, match="do not exist"):
        validate_policy({"gate": {}, "targets": "wcag_2.2_aa"})


def test_a_gate_setting_that_does_not_exist_is_refused():
    with pytest.raises(A11yPolicyError, match="do not exist"):
        validate_policy({"gate": {"block_severity": ["critical"]}})


def test_a_gate_that_is_not_an_object_is_refused():
    with pytest.raises(A11yPolicyError, match="`gate` must be an object"):
        validate_policy({"gate": ["critical"]})


def test_severities_that_are_not_a_list_are_refused():
    with pytest.raises(A11yPolicyError, match="must be a list"):
        validate_policy({"gate": {"block_severities": "critical"}})


@pytest.mark.parametrize("value", [-0.1, 1.5, "nine", True, None])
def test_a_confidence_bar_that_is_not_a_fraction_is_refused(value):
    with pytest.raises(A11yPolicyError, match="min_confidence"):
        validate_policy({"gate": {"min_confidence": value}})


def test_a_confidence_bar_written_as_a_string_number_is_accepted():
    assert validate_policy({"gate": {"min_confidence": "0.75"}})["gate"]["min_confidence"] == 0.75


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_block_on_incomplete_run_must_be_true_or_false(value):
    with pytest.raises(A11yPolicyError, match="true or false"):
        validate_policy({"gate": {"block_on_incomplete_run": value}})


def test_the_incomplete_run_rule_can_be_switched_off():
    policy = validate_policy({"gate": {"block_on_incomplete_run": False}})
    assert policy["gate"]["block_on_incomplete_run"] is False


def test_design_checks_that_are_not_an_object_are_refused():
    with pytest.raises(A11yPolicyError, match="design_checks` must be an object"):
        validate_policy({"gate": {"design_checks": ["2.2.1"]}})


def test_a_design_checks_setting_that_does_not_exist_is_refused():
    with pytest.raises(A11yPolicyError, match="do not exist"):
        validate_policy({"gate": {"design_checks": {"extra": ["2.2.1"]}}})


def test_extra_criteria_that_are_not_a_list_are_refused():
    with pytest.raises(A11yPolicyError, match="must be a list"):
        validate_policy({"gate": {"design_checks": {"extra_criteria": "2.2.1"}}})


def test_switching_on_a_question_the_gate_does_not_have_is_refused():
    with pytest.raises(A11yPolicyError) as exc:
        validate_policy({"gate": {"design_checks": {"extra_criteria": ["1.1.1", "9.9.9"]}}})
    assert "9.9.9" in str(exc.value)
    assert "1.1.1" in str(exc.value), "already-asked criteria are not 'extra' either"
    assert "2.2.1" in str(exc.value), "the message lists the ones that can be switched on"


def test_extra_criteria_are_de_duplicated_and_ordered():
    policy = validate_policy(
        {"gate": {"design_checks": {"extra_criteria": ["3.3.4", "2.2.1", "2.2.1"]}}})
    assert extra_design_criteria(policy) == ("2.2.1", "3.3.4")


# ══ Falling back without failing — the two callers that must not raise ════════════

def test_a_bad_stored_policy_raises_for_a_person_reading_it(world):
    _profile(world, {"gate": {"block_severities": ["serious"]}})
    with pytest.raises(A11yPolicyError):
        policy_for(world["t"], world["p"])


def test_the_same_bad_policy_falls_back_to_the_default_with_the_reason(world):
    _profile(world, {"gate": {"block_severities": ["serious"]}})
    policy, error = policy_or_default(world["t"], world["p"])
    assert policy == default_policy(), "the fallback is the documented default, not a weaker one"
    assert "serious" in error


def test_a_good_policy_falls_back_to_nothing(world):
    _profile(world, {"target": "wcag_2.2_a"})
    policy, error = policy_or_default(world["t"], world["p"])
    assert error == ""
    assert policy["gate"]["block_severities"] == ["critical"]


def test_an_unreadable_project_still_yields_a_policy(world):
    """Any failure at all — not just an invalid policy — leaves the caller with the default."""
    policy, error = policy_or_default(world["t"], "not-a-uuid")
    assert policy == default_policy()
    assert error


# ══ blocks() — would this finding stop the pipeline? ══════════════════════════════

def test_a_severity_outside_the_policy_never_blocks():
    assert blocks(default_policy(), severity="medium", confidence=1.0) is False


def test_a_severity_inside_the_policy_blocks():
    assert blocks(default_policy(), severity="high", confidence=0.6) is True


def test_the_confidence_bar_holds_back_an_unsure_ai_finding():
    policy = validate_policy({"gate": {"min_confidence": 0.9}})
    assert blocks(policy, severity="critical", confidence=0.89, source=SOURCE_AI) is False
    assert blocks(policy, severity="critical", confidence=0.91, source=SOURCE_AI) is True


def test_a_finding_sitting_exactly_on_the_bar_blocks():
    """The opposite of `triage`'s `<=`, and deliberately so: there a coin-flip means ask a
    person; here it means surface it rather than let it through."""
    policy = validate_policy({"gate": {"min_confidence": 0.9}})
    assert blocks(policy, severity="critical", confidence=0.9, source=SOURCE_AI) is True


def test_the_confidence_bar_never_silences_the_rule_scanner():
    """A measurement has no confidence to doubt — QA-06's rule, which a dial must not undo."""
    policy = validate_policy({"gate": {"min_confidence": 0.99}})
    assert blocks(policy, severity="critical", confidence=0.1, source=SOURCE_RULE) is True


def test_a_finding_with_no_confidence_at_all_blocks():
    policy = validate_policy({"gate": {"min_confidence": 0.9}})
    assert blocks(policy, severity="critical", confidence=None) is True


def test_an_empty_severity_never_blocks():
    assert blocks(default_policy(), severity="", confidence=1.0) is False


# ══ describe_policy — the plain-words version ═════════════════════════════════════

def test_the_policy_reads_as_english():
    text = describe_policy(default_policy())
    assert "WCAG 2.2 AA" in text
    assert "critical, high" in text
    assert "Level A" in text and "Level AA" in text
    assert ACCESSIBILITY_REVIEWER_ROLE in text


def test_a_tuned_policy_says_what_it_changed():
    policy = validate_policy({
        "gate": {"min_confidence": 0.85, "block_on_incomplete_run": False,
                 "design_checks": {"extra_criteria": ["2.3.1"]}}})
    text = describe_policy(policy)
    assert "85%" in text
    assert "does NOT block" in text
    assert "2.3.1" in text


def test_a_report_only_policy_says_so():
    assert "reported only" in describe_policy(validate_policy({"gate": {"block_severities": []}}))


# ══ The design gate — optional questions, off by default ══════════════════════════

def test_the_default_checklist_is_exactly_what_it_was_before_this_task(db):
    """The one regression that matters: an empty policy must not change a single question."""
    items = wcag_aa_checklist()
    assert [i["key"] for i in items] == [c.number for c in DESIGN_CHECKS]
    assert not {c.number for c in OPTIONAL_DESIGN_CHECKS} & {i["key"] for i in items}


def test_switching_a_question_on_adds_it_in_the_order_of_the_standard(db):
    keys = [i["key"] for i in wcag_aa_checklist(extra=["2.3.1"])]
    assert len(keys) == len(DESIGN_CHECKS) + 1
    assert keys.index("2.3.1") == keys.index("2.2.2") + 1, "2.3.1 sits between 2.2.2 and 2.4.3"
    assert keys == sorted(keys, key=lambda n: tuple(int(p) for p in n.split(".")))


def test_a_switched_on_question_carries_its_wording_from_the_loaded_standard(db):
    item = next(i for i in wcag_aa_checklist(extra=["2.2.1"]) if i["key"] == "2.2.1")
    assert "2.2.1" in item["label"] and "Level A" in item["label"]
    assert "time limit" in item["label"]
    assert item["required"] is True and item["satisfied"] is False


def test_all_five_can_be_switched_on_at_once(db):
    keys = {i["key"] for i in wcag_aa_checklist(extra=[c.number for c in OPTIONAL_DESIGN_CHECKS])}
    assert {c.number for c in OPTIONAL_DESIGN_CHECKS} <= keys


def test_a_question_that_does_not_exist_is_refused_not_skipped(db):
    """Silently dropping it would leave a project believing it asks about flashing."""
    with pytest.raises(ChecklistGap, match="9.9.9"):
        wcag_aa_checklist(extra=["9.9.9"])


def test_the_optional_questions_are_still_recorded_as_not_asked_by_default():
    assert {c.number for c in OPTIONAL_DESIGN_CHECKS} == set(
        NOT_ASKED["answerable_at_design_but_not_asked"])


def test_every_criterion_is_still_accounted_for(db):
    assert verify_complete() == 55


def test_explain_now_says_an_optional_question_can_be_switched_on():
    text = explain("2.3.1")
    assert "switch it on" in text
    assert "flashes" in text


def test_the_printed_checklist_shows_what_can_be_switched_on():
    text = describe_checklist()
    for check in OPTIONAL_DESIGN_CHECKS:
        assert check.question in text


# ══ The gate composition reads the project's policy ═══════════════════════════════

def test_a_gate_opened_without_a_project_gets_the_default_checklist(db):
    keys = {c["key"] for c in conditions_for_phase("ux_design")}
    assert keys == {c.number for c in DESIGN_CHECKS}


def test_a_gate_opened_for_a_project_honours_its_policy(world):
    _profile(world, {"gate": {"design_checks": {"extra_criteria": ["2.5.4"]}}})
    keys = {c["key"] for c in conditions_for_phase(
        "ux_design", tenant_id=world["t"], project_id=world["p"])}
    assert "2.5.4" in keys


def test_a_project_with_no_policy_opens_the_same_gate_as_before(world):
    keys = {c["key"] for c in conditions_for_phase(
        "ux_design", tenant_id=world["t"], project_id=world["p"])}
    assert keys == {c.number for c in DESIGN_CHECKS}


def test_an_unreadable_policy_still_opens_the_gate(world):
    """A bad key in a JSON field must not stop every design review in the project."""
    _profile(world, {"gate": {"block_severities": ["serious"]}})
    keys = {c["key"] for c in conditions_for_phase(
        "ux_design", tenant_id=world["t"], project_id=world["p"])}
    assert keys == {c.number for c in DESIGN_CHECKS}


def test_no_other_phase_grew_a_checklist(world):
    _profile(world, {"gate": {"design_checks": {"extra_criteria": ["2.5.4"]}}})
    assert conditions_for_phase("prd", tenant_id=world["t"], project_id=world["p"]) == []


# ══ AC2 — the accessibility reviewer role ════════════════════════════════════════

def test_the_accessibility_reviewer_is_a_real_role():
    assert ACCESSIBILITY_REVIEWER_ROLE in Role.values


def test_the_accessibility_reviewer_can_be_assigned(world):
    user = User.objects.create_user(email="sme@acme.test", name="SME",
                                    tenant=world["tenant"], password="p")
    membership = Membership.objects.create(
        tenant=world["tenant"], user=user, project=world["project"],
        role=ACCESSIBILITY_REVIEWER_ROLE)
    assert membership.role == ACCESSIBILITY_REVIEWER_ROLE


def test_the_accessibility_reviewer_is_the_role_that_gates_testing():
    """QA-15 hangs its gate on the testing phase, so the reviewer has to be that phase's role —
    otherwise the person who signs off accessibility is not the person who can."""
    assert gate_role_for("09_testing") == ACCESSIBILITY_REVIEWER_ROLE
    assert ACCESSIBILITY_REVIEWER_ROLE in gate_roles()


def test_no_new_role_was_invented_for_this(db):
    """D7: mapping onto QA Lead is the decision. A new enum value would drag in a migration,
    the RBAC coverage report and the UI — this fails if someone quietly adds one."""
    assert not [v for v in Role.values if "a11y" in v or "accessib" in v]


# ══ AC1 (the API) — an admin sets it and saves it ════════════════════════════════

def test_an_admin_saves_a_policy_and_reads_it_back(client, world):
    client.force_authenticate(world["admin"])
    url = f"/api/projects/{world['p']}/profile/"
    saved = client.put(url, {"a11y": {"target": "wcag_2.2_aaa",
                                      "gate": {"min_confidence": 0.8}}},
                       format="json", **_hdr(world["t"]))
    assert saved.status_code in (200, 201)
    assert saved.data["a11y"]["target"] == "wcag_2.2_aaa"
    assert client.get(url, **_hdr(world["t"])).data["a11y"]["gate"]["min_confidence"] == 0.8


def test_an_invalid_policy_is_refused_at_the_api_with_a_readable_reason(client, world):
    client.force_authenticate(world["admin"])
    resp = client.put(f"/api/projects/{world['p']}/profile/",
                      {"a11y": {"gate": {"block_severities": ["serious"]}}},
                      format="json", **_hdr(world["t"]))
    assert resp.status_code == 400
    assert "serious" in str(resp.data["a11y"])
    assert not ProjectProfile.objects.filter(project_id=world["p"]).exists()


def test_the_policy_endpoint_shows_defaults_overrides_and_the_effective_result(client, world):
    _profile(world, {"target": "wcag_2.2_a"})
    resp = client.get(f"/api/projects/{world['p']}/a11y-policy/", **_hdr(world["t"]))
    assert resp.status_code == 200
    assert resp.data["defaults"]["gate"]["block_severities"] == ["critical", "high"]
    assert resp.data["overrides"] == {"target": "wcag_2.2_a"}
    assert resp.data["effective"]["gate"]["block_severities"] == ["critical"]
    assert "WCAG 2.2 A" in resp.data["summary"]
    assert resp.data["error"] == ""


def test_the_policy_endpoint_answers_for_a_project_that_has_no_profile(client, world):
    resp = client.get(f"/api/projects/{world['p']}/a11y-policy/", **_hdr(world["t"]))
    assert resp.status_code == 200
    assert resp.data["overrides"] == {}
    assert resp.data["effective"] == default_policy()


def test_the_policy_endpoint_says_so_when_the_stored_policy_is_unusable(client, world):
    _profile(world, {"gate": {"block_severities": ["serious"]}})
    resp = client.get(f"/api/projects/{world['p']}/a11y-policy/", **_hdr(world["t"]))
    assert resp.status_code == 200
    assert "serious" in resp.data["error"]
    assert resp.data["effective"] == default_policy(), "never show a policy that is not in force"


def test_another_tenant_cannot_read_the_policy(client, world):
    _profile(world, {"target": "wcag_2.2_a"})
    stranger = Tenant.objects.create(name="Rival")
    resp = client.get(f"/api/projects/{world['p']}/a11y-policy/", **_hdr(stranger.id))
    assert resp.status_code == 404


# ══ The policy actually governs the defect loop ══════════════════════════════════

@pytest.fixture
def defect_world(world):
    story = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                    title="Checkout")
    spec = AgentSpec.objects.create(tenant=world["tenant"], key="09b_test_automation",
                                    body_ref="x", semver="1.0.0")
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.4.3",
        defaults={"handle": "Contrast (Minimum)", "level": "AA", "slug": "c", "text": "…"})
    run = Run.objects.create(tenant=world["tenant"], work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-a11y-policy")
    return {**world, "story": story, "run": run}


def _row(**over) -> ReportRow:
    base = {
        "source": SOURCE_AI, "outcome": TRIAGE_FAILURE, "criteria": ("1.4.3",),
        "route": "/checkout", "selector": "button.pay", "evidence": "contrast is 2.1:1",
        "confidence": 0.93, "suggested_fix": "darken the label", "checker": "color",
        "verdict": A11Y_FAIL,
    }
    base.update(over)
    return ReportRow(**base)


def _record(defect_world, rows):
    record_run_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                        run_id=str(defect_world["run"].id),
                        report=MergedReport(rows=list(rows), routes=["/checkout"], unjudged=[]))


def _a11y_defects(world):
    return [d for d in WorkItem.objects.filter(tenant_id=world["t"],
                                               type=WorkItem.Type.DEFECT)
            if (d.external_ref or {}).get("a11y_finding")]


def test_a_narrowed_policy_stops_a_high_finding_opening_a_defect(defect_world):
    _profile(defect_world, {"gate": {"block_severities": ["critical"]}})
    _record(defect_world, [_row()])                      # 1.4.3 is Level AA ⇒ high
    out = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                               run_id=str(defect_world["run"].id))
    assert out["opened"] == []
    assert out["policy"]["gate"]["block_severities"] == ["critical"]
    assert A11yFinding.objects.filter(project_id=defect_world["p"]).count() == 1, \
        "still recorded and still in the review queue — only the defect is withheld"


def test_the_default_policy_opens_that_same_defect(defect_world):
    _record(defect_world, [_row()])
    out = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                               run_id=str(defect_world["run"].id))
    assert len(out["opened"]) == 1
    assert _a11y_defects(defect_world)[0].external_ref["severity"] == "high"


def test_a_raised_confidence_bar_holds_back_an_unsure_finding(defect_world):
    _profile(defect_world, {"gate": {"min_confidence": 0.95}})
    _record(defect_world, [_row(confidence=0.93)])
    out = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                               run_id=str(defect_world["run"].id))
    assert out["opened"] == []


def test_a_raised_confidence_bar_never_holds_back_the_rule_scanner(defect_world):
    _profile(defect_world, {"gate": {"min_confidence": 0.95}})
    _record(defect_world, [_row(source=SOURCE_RULE, confidence=None, checker="axe")])
    out = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                               run_id=str(defect_world["run"].id))
    assert len(out["opened"]) == 1


def test_an_unreadable_policy_still_opens_defects_at_the_default_bar(defect_world):
    _profile(defect_world, {"gate": {"block_severities": ["serious"]}})
    _record(defect_world, [_row()])
    out = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                               run_id=str(defect_world["run"].id))
    assert len(out["opened"]) == 1, "a bad policy must not leave a real failure untracked"
    assert "serious" in out["policy_error"]


def test_raising_the_bar_closes_defects_that_no_longer_clear_it(defect_world):
    _record(defect_world, [_row()])
    opened = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                                  run_id=str(defect_world["run"].id))
    assert len(opened["opened"]) == 1

    _profile(defect_world, {"gate": {"block_severities": ["critical"]}})
    closed = record_a11y_findings(tenant_id=defect_world["t"], project_id=defect_world["p"],
                                  run_id=str(defect_world["run"].id))
    assert len(closed["closed"]) == 1
    assert _a11y_defects(defect_world)[0].state == WorkItem.State.DONE


def test_the_severity_words_the_policy_accepts_are_the_ones_findings_can_carry():
    """If `SEVERITY_BY_LEVEL` ever gains a level, this fails until the policy knows about it."""
    assert set(SEVERITY_BY_LEVEL.values()) <= set(SEVERITIES)
    assert set(TARGET_LEVELS["wcag_2.2_aaa"]) == set(SEVERITY_BY_LEVEL)
