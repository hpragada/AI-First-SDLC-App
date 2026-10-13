"""QA-06 — the confidence gate and the "a measurement beats an opinion" safety valve.

What these prove, against the task's acceptance criteria:

  AC1  a judgment below its checker's threshold is marked "needs human review", not "fail"
  AC2  where the rule scanner proved a failure and the AI disagreed, the scanner failure stands
  AC3  a failure with no evidence is never reported as a hard failure
  AC4  the threshold split, the scanner rule and the evidence rule are all covered, ≥90%

Beyond the ACs, and deliberately:

  * **the scanner rule runs one way only** — a scanner that found nothing never silences an
    AI finding, or the AI layer would be pointless
  * **matching is exact** — a scanner failure on another element, screen or criterion does
    not settle this one
  * **nothing is ever dropped** (team decision, 2026-08-13): the lowest-confidence judgment
    still reaches a person, because dropping is the only outcome that can silently miss a
    real defect
  * **an item awaiting review never blocks a team**, which is the whole reason this exists
  * a misconfigured threshold is loud, and cannot silently invert the valve
"""
import pytest

from apps.a11y.triage import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    TRIAGE_FAILURE,
    TRIAGE_PASS,
    TRIAGE_REVIEW,
    TriagedFinding,
    threshold_for,
    thresholds_for,
    triage,
)
from integrations.types import (
    A11Y_FAIL,
    A11Y_PASS,
    A11yCandidate,
    A11yJudgment,
    A11yRuleFailure,
    uncertain,
)

ELEMENT = A11yCandidate(
    selector="main > button.cta", html="<div class='cta'>Buy</div>",
    context="checkout page primary action", route="/checkout",
)


def judged(verdict=A11Y_FAIL, *, confidence=0.95, checker="label",
           criteria=("2.5.3",), evidence="visible label 'Buy now', accessible name 'Buy'"):
    return A11yJudgment(criteria=criteria, verdict=verdict, confidence=confidence,
                        evidence=evidence, suggested_fix="", checker=checker)


def scanner_failed(criterion="2.5.3", *, selector=ELEMENT.selector, route=ELEMENT.route):
    return A11yRuleFailure(criterion=criterion, selector=selector, route=route,
                           rule_id="label-content-name-mismatch",
                           evidence="accessible name does not contain the visible label")


# ── AC1: the confidence gate ─────────────────────────────────────────
def test_a_confident_failure_is_reported_as_one():
    result = triage(judged(confidence=0.95), ELEMENT)
    assert result.outcome == TRIAGE_FAILURE
    assert result.blocks is True
    assert "95%" in result.reason and "80%" in result.reason


def test_an_unsure_failure_goes_to_a_person_not_the_build():
    result = triage(judged(confidence=0.4), ELEMENT)
    assert result.outcome == TRIAGE_REVIEW
    assert result.needs_human is True
    # The point of the whole task: an unsure AI must never block a team.
    assert result.blocks is False
    assert "40%" in result.reason


def test_exactly_at_the_threshold_rounds_toward_review():
    """Specified edge case: when the rule is a coin-flip, ask a person."""
    assert triage(judged(confidence=0.80), ELEMENT).outcome == TRIAGE_REVIEW
    assert triage(judged(confidence=0.801), ELEMENT).outcome == TRIAGE_FAILURE


def test_the_gate_applies_to_a_pass_as_well_as_a_failure():
    """A shrug is not a clean bill of health — the platform never auto-certifies."""
    assert triage(judged(A11Y_PASS, confidence=0.4), ELEMENT).outcome == TRIAGE_REVIEW
    assert triage(judged(A11Y_PASS, confidence=0.99), ELEMENT).outcome == TRIAGE_PASS


def test_nothing_is_ever_dropped():
    """Team decision: even the least confident judgment reaches a person.

    Report 1 §4 proposed discarding these; the User Journeys document routes them to the
    SME, and dropping is the only outcome that can silently miss a real defect.
    """
    for confidence in (0.0, 0.01, 0.2, 0.5):
        assert triage(judged(confidence=confidence), ELEMENT).outcome == TRIAGE_REVIEW


def test_a_check_that_could_not_answer_always_goes_to_a_person():
    result = triage(uncertain(("2.5.3",), checker="label", reason="no screenshot"),
                    ELEMENT)
    assert result.outcome == TRIAGE_REVIEW
    assert "no screenshot" in result.reason


def test_an_uncertain_judgment_survives_a_zero_threshold():
    """A threshold of 0 means "report what the AI is sure of" — not "report its shrugs"."""
    result = triage(uncertain(("1.1.1",), checker="alt", reason="image not rendered"),
                    ELEMENT, thresholds={"alt": 0.0})
    assert result.outcome == TRIAGE_REVIEW


# ── AC2: a measurement beats an opinion ──────────────────────────────
def test_the_scanner_wins_when_the_ai_says_it_is_fine():
    """The AC's case: the scanner proved a failure, the AI disagreed, the scanner stands."""
    result = triage(judged(A11Y_PASS, confidence=0.99), ELEMENT,
                    rule_failures=[scanner_failed()])
    assert result.outcome == TRIAGE_FAILURE
    assert result.rule_overrode_ai is True
    assert result.rule_failure.rule_id == "label-content-name-mismatch"
    assert "measurement is not overturned by an opinion" in result.reason


def test_the_scanner_wins_however_unsure_the_ai_was():
    """A proven failure settles it — the confidence gate never reaches this case."""
    result = triage(judged(A11Y_PASS, confidence=0.01), ELEMENT,
                    rule_failures=[scanner_failed()])
    assert result.outcome == TRIAGE_FAILURE


def test_agreement_is_still_the_scanners_finding():
    """Both say it fails: the outcome cites the scanner, which can prove it."""
    result = triage(judged(A11Y_FAIL, confidence=0.3), ELEMENT,
                    rule_failures=[scanner_failed()])
    assert result.outcome == TRIAGE_FAILURE
    assert result.rule_overrode_ai is False       # they agreed; nothing was overridden
    assert "the AI agreed" in result.reason


def test_the_rule_runs_one_way_only():
    """A silent scanner never silences the AI.

    The AI is here to catch what a scanner is blind to — whether alt text is *meaningful*,
    whether a div is really a button. Reading "the scanner wins" as "the scanner always
    wins" would delete the entire value of the AI layer.
    """
    result = triage(judged(A11Y_FAIL, confidence=0.95), ELEMENT, rule_failures=[])
    assert result.outcome == TRIAGE_FAILURE
    assert result.rule_failure is None


def test_a_scanner_failure_elsewhere_does_not_settle_this_element():
    for elsewhere in (
        scanner_failed(selector="footer a"),          # another element
        scanner_failed(route="/basket"),              # another screen
        scanner_failed(criterion="1.4.3"),            # another criterion
    ):
        result = triage(judged(A11Y_PASS, confidence=0.99), ELEMENT,
                        rule_failures=[elsewhere])
        assert result.outcome == TRIAGE_PASS, elsewhere
        assert result.rule_failure is None


def test_a_failure_of_any_criterion_the_judgment_covers_counts():
    """`semantics` judges 1.3.1 and 4.1.2 together (D-A11Y-2); either being proven is proof."""
    judgment = judged(A11Y_PASS, confidence=0.99, checker="semantics",
                      criteria=("1.3.1", "4.1.2"))
    result = triage(judgment, ELEMENT, rule_failures=[scanner_failed("4.1.2")])
    assert result.outcome == TRIAGE_FAILURE
    assert result.rule_failure.criterion == "4.1.2"


# ── AC3: no evidence, no failure ─────────────────────────────────────
def test_a_failure_with_no_evidence_never_stands():
    """Nobody can act on "trust me", and nobody can defend it to an auditor."""
    result = triage(judged(A11Y_FAIL, confidence=1.0, evidence=""), ELEMENT)
    assert result.outcome == TRIAGE_REVIEW
    assert result.blocks is False
    assert "recorded no evidence" in result.reason


def test_whitespace_is_not_evidence():
    assert triage(judged(A11Y_FAIL, confidence=1.0, evidence="   \n "),
                  ELEMENT).outcome == TRIAGE_REVIEW


def test_the_evidence_rule_cannot_be_bypassed_by_a_zero_threshold():
    result = triage(judged(A11Y_FAIL, confidence=1.0, evidence=""), ELEMENT,
                    thresholds={"label": 0.0})
    assert result.outcome == TRIAGE_REVIEW


def test_a_proven_scanner_failure_does_not_need_the_ais_evidence():
    """The scanner's own evidence is what stands, so the AI having none is irrelevant."""
    result = triage(judged(A11Y_FAIL, confidence=0.1, evidence=""), ELEMENT,
                    rule_failures=[scanner_failed()])
    assert result.outcome == TRIAGE_FAILURE


# ── per-checker thresholds ───────────────────────────────────────────
def test_thresholds_are_per_checker():
    judgment = judged(A11Y_FAIL, confidence=0.7, checker="color", criteria=("1.4.1",))
    assert triage(judgment, ELEMENT).outcome == TRIAGE_REVIEW          # default 0.80
    assert triage(judgment, ELEMENT,
                  thresholds={"color": 0.5}).outcome == TRIAGE_FAILURE


def test_an_unconfigured_checker_keeps_the_default():
    """Tuning one noisy check must never loosen the other three."""
    assert threshold_for("alt", {"color": 0.5}) == DEFAULT_CONFIDENCE_THRESHOLD
    assert threshold_for("alt", None) == DEFAULT_CONFIDENCE_THRESHOLD
    assert threshold_for("alt", {}) == DEFAULT_CONFIDENCE_THRESHOLD


def test_an_unknown_checker_is_never_more_permissive():
    assert threshold_for("brand-new-check") == DEFAULT_CONFIDENCE_THRESHOLD


def test_a_configured_zero_is_honoured_not_treated_as_unset():
    assert threshold_for("alt", {"alt": 0.0}) == 0.0


def test_the_default_is_the_agreed_starting_point():
    """0.80 — provisional until QA-09/QA-10's golden set tunes it (team, 2026-08-13)."""
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.80


# ── the tenant's configuration ───────────────────────────────────────
@pytest.fixture
def tenant(db):
    from apps.tenancy.services import create_tenant

    return create_tenant(name="Triage Co")


def _scopes(tenant, scopes):
    """Set the tenant's a11yai settings, through RLS like any other write."""
    from apps.tenancy.context import tenant_context
    from integrations.registry import get_connection

    conn = get_connection(tenant.id, "a11yai")
    assert conn is not None, "a11yai should be auto-provisioned on tenant creation (D-A11Y-1)"
    conn.scopes = scopes
    with tenant_context(tenant.id):
        conn.save(update_fields=["scopes"])
    return conn


def test_a_tenant_with_no_settings_gets_the_defaults(tenant):
    """Every check the platform runs, element and journey alike (QA-20 widened this from the
    four element checks: a tenant must be able to tune `trap` for a check that will actually
    run against them, and before QA-20 configuring it was rejected as a check that "does not
    exist")."""
    from integrations.types import A11Y_ALL_CHECKER_CRITERIA

    resolved = thresholds_for(tenant.id)
    assert set(resolved) == set(A11Y_ALL_CHECKER_CRITERIA)
    assert set(resolved.values()) == {0.80}
    assert resolved["alt"] == resolved["trap"] == 0.80


def test_a_tenant_tunes_one_check_without_restating_the_others(tenant):
    _scopes(tenant, {"confidence_thresholds": {"color": 0.6}})
    resolved = thresholds_for(tenant.id)
    assert resolved["color"] == 0.6
    assert resolved["alt"] == resolved["semantics"] == resolved["label"] == 0.80


def test_thresholds_are_read_through_the_same_settings_as_the_caps(tenant):
    """One place a tenant tunes accessibility checking, not two to discover."""
    from apps.a11y.dispatch import caps_for

    _scopes(tenant, {"max_judgments_per_run": 25,
                     "confidence_thresholds": {"alt": 0.9}})
    assert caps_for(tenant.id)[0] == 25
    assert thresholds_for(tenant.id)["alt"] == 0.9


def test_a_threshold_outside_zero_to_one_is_refused(tenant):
    """A negative threshold would make every judgment a hard failure — the exact inverse."""
    _scopes(tenant, {"confidence_thresholds": {"alt": -1}})
    with pytest.raises(ValueError, match="not between 0 and 1"):
        thresholds_for(tenant.id)

    _scopes(tenant, {"confidence_thresholds": {"alt": 1.5}})
    with pytest.raises(ValueError, match="not between 0 and 1"):
        thresholds_for(tenant.id)


def test_a_threshold_that_is_not_a_number_is_refused(tenant):
    _scopes(tenant, {"confidence_thresholds": {"alt": "high"}})
    with pytest.raises(ValueError, match="not a number"):
        thresholds_for(tenant.id)


def test_a_misspelled_check_name_is_refused(tenant):
    """Otherwise someone believes they tuned a check they never touched."""
    _scopes(tenant, {"confidence_thresholds": {"labels": 0.9}})
    with pytest.raises(ValueError, match="do not exist: labels"):
        thresholds_for(tenant.id)


def test_an_unconfigured_tenant_still_gets_thresholds(db):
    """A missing connection is not a reason to run without a safety valve."""
    from apps.integrations.models import IntegrationConnection
    from apps.tenancy.context import tenant_context
    from apps.tenancy.services import create_tenant

    other = create_tenant(name="No Conn")
    with tenant_context(other.id):
        IntegrationConnection.objects.filter(
            tenant_id=other.id, capability="a11yai").delete()
    from integrations.types import A11Y_ALL_CHECKER_CRITERIA

    resolved = thresholds_for(other.id)
    assert set(resolved) == set(A11Y_ALL_CHECKER_CRITERIA)
    assert set(resolved.values()) == {0.80}


# ── the result object ────────────────────────────────────────────────
def test_a_triaged_finding_carries_what_it_was_judged_on():
    result = triage(judged(), ELEMENT)
    assert result.judgment.checker == "label"
    assert result.candidate.route == "/checkout"
    assert result.criteria == ("2.5.3",)
    assert result.threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_an_invalid_outcome_cannot_be_constructed():
    with pytest.raises(ValueError, match="invalid triage outcome"):
        TriagedFinding(outcome="maybe", judgment=judged(), candidate=ELEMENT,
                       reason="", threshold=0.8)


def test_a_rule_failure_must_name_its_criterion():
    with pytest.raises(ValueError, match="must name the WCAG criterion"):
        A11yRuleFailure(criterion="", selector="button")


def test_a_rule_failure_identifies_itself_the_same_way_a_finding_does():
    """(route, selector, criterion) — QA-12a's fingerprint minus the checker."""
    assert scanner_failed().key == ("/checkout", "main > button.cta", "2.5.3")


def test_a_one_shot_iterator_of_failures_is_refused():
    """A generator would be drained by the first judgment, silently disabling the rule.

    Triaging a run calls `triage()` once per judgment against the same scanner failures.
    Accepting a generator would mean judgment 1 is checked against them and judgments 2..n
    see none — the rule that protects against a wrong pass would stop running, quietly.
    """
    with pytest.raises(TypeError, match="silently disable the scanner rule"):
        triage(judged(A11Y_PASS), ELEMENT,
               rule_failures=(f for f in [scanner_failed()]))


def test_the_same_failures_settle_every_judgment_in_a_run():
    """The case the guard above protects: one sequence, reused, still matches each time."""
    failures = [scanner_failed()]
    for _ in range(3):
        assert triage(judged(A11Y_PASS, confidence=0.99), ELEMENT,
                      rule_failures=failures).outcome == TRIAGE_FAILURE


def test_the_type_is_not_named_after_a_vendor():
    """axe-core is what runs today; the platform must not bake it into a type (#9)."""
    assert "axe" not in A11yRuleFailure.__name__.lower()
    assert "axe" not in " ".join(A11yRuleFailure.__dataclass_fields__)
