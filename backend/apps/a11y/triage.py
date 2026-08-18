"""The safety valve between what the AI says and what anyone acts on (QA-06).

An AI can be confidently wrong, and in a compliance product that is as damaging as a miss:
a false failure that blocks a merge teaches a team to switch the whole thing off, and a
false pass tells a client they conform when they do not. Nothing the judge returns reaches
a report, a gate or a developer without passing through here first.

Three rules, and they are the whole module:

1. **Not sure enough is not a failure.** A judgment at or below its checker's confidence
   threshold becomes *needs human review*, never *fail*. A model 40% sure a button is
   mislabelled has not found a defect; it has found something worth a person's two minutes.
2. **A measurement beats an opinion.** Where a deterministic rule scanner proved a failure
   on the same element and criterion, that failure stands whatever the AI said.
3. **No evidence, no failure.** A judgment that cannot say what it was based on is never
   reported as a hard failure. Nobody can act on "trust me", and nobody can defend it to an
   auditor.

**Rule 2 runs one way only, and this matters.** If the scanner passes something and the AI
fails it, *the AI finding stands*. The AI exists to catch what a scanner is blind to — is
the alt text *meaningful*, is this `div` really a button. It adds what the scanner cannot
see; it does not overrule what the scanner proved. Reading rule 2 as "the scanner always
wins" would delete the entire value of the AI layer.

**Nothing is ever dropped** (team decision, 2026-08-13). Report 1 §4 proposed discarding
findings below a low floor to keep reviewer noise down; the User Journeys document routes
them to the SME instead, and the team chose that. Dropping is the only option here that can
make the platform silently miss a real accessibility defect, and it would be the first place
in this build that throws something away rather than routing it. If the review queue proves
noisy once QA-09/QA-10 measure it, a floor can be added then — with evidence.

**Verdict is not outcome.** `A11yJudgment.verdict` is what the AI said. The outcome here is
what the platform *does about it*, which is a different question with a different answer:
a `pass` verdict on an element the scanner failed comes out of here as a failure.

**Pure and database-free.** `triage()` takes everything it needs as arguments, so the rules
can be tested exhaustively without a tenant, a run or a model. Reading a tenant's configured
thresholds is `thresholds_for()`, kept separate for exactly that reason.

**What this task honestly delivers** (correction R1): the rule is built and unit-tested, but
structured scanner output does not reach the platform until QA-11b, so rule 2 is only proven
end-to-end at QA-12. Say that at review rather than presenting a fixture-only test as a
working guarantee. Nothing calls `triage()` yet — QA-12 wires it into the run.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from integrations.types import (
    A11Y_ALL_CHECKER_CRITERIA,
    A11Y_FAIL,
    A11Y_PASS,
    A11Y_UNCERTAIN,
    A11yCandidate,
    A11yJudgment,
    A11yRuleFailure,
)

#: What the platform does with a judgment. Deliberately a different vocabulary from
#: `A11Y_PASS` / `A11Y_FAIL` / `A11Y_UNCERTAIN`, which are what the AI *said*.
TRIAGE_FAILURE = "failure"            # report it as a real finding; it may block a gate
TRIAGE_REVIEW = "needs_review"        # a person decides; never blocks on its own
TRIAGE_PASS = "pass"                  # nothing to report
TRIAGE_OUTCOMES = frozenset({TRIAGE_FAILURE, TRIAGE_REVIEW, TRIAGE_PASS})

#: How sure the judge must be before a verdict is treated as definite. Provisional by
#: design: **no research document specifies a threshold**, and the only number that looks
#: like one — "≥85% precision on high-confidence findings" — is an accuracy target for the
#: golden set (QA-09/QA-10), not a confidence cutoff. The real values come from measuring
#: against that golden set, which is why this is per-tenant config: tuning is a settings
#: change, never a code change. 0.80 chosen as a conservative round number (team, 2026-08-13).
DEFAULT_CONFIDENCE_THRESHOLD = 0.80

#: Reasons an item ended up where it did — sentences for the person who has to act on it,
#: not status codes.
REASON_RULE_OVERRODE = (
    "The rule scanner proved this fails {criterion}, so that stands — the AI judged it a "
    "pass, and a measurement is not overturned by an opinion."
)
REASON_RULE_CONFIRMED = (
    "The rule scanner proved this fails {criterion}; the AI agreed."
)
REASON_UNCERTAIN = (
    "The check could not reach a verdict, so a person needs to look: {evidence}"
)
REASON_NO_EVIDENCE = (
    "The AI reported a failure but recorded no evidence for it, so it cannot stand as one. "
    "Sent for human review instead."
)
REASON_BELOW_THRESHOLD = (
    "The AI was {confidence:.0%} sure and this check needs more than {threshold:.0%}, so a "
    "person decides rather than the build."
)
REASON_CONFIDENT_FAILURE = (
    "The AI was {confidence:.0%} sure this fails {criteria}, above the {threshold:.0%} this "
    "check requires."
)
REASON_CONFIDENT_PASS = (
    "The AI was {confidence:.0%} sure this is fine, above the {threshold:.0%} this check "
    "requires, and no rule scanner disagreed."
)


@dataclass(frozen=True)
class TriagedFinding:
    """One judgment, and what the platform decided to do with it.

    Carries the judgment and the candidate rather than copying fields out of them, so a
    reviewer, the conformance report and the defect loopback all read the same object and
    cannot drift into disagreeing about what was found.
    """

    outcome: str
    judgment: A11yJudgment
    candidate: A11yCandidate
    reason: str
    threshold: float
    #: The scanner failure that decided this, when one did. Present on agreement as well as
    #: on override, so the report can cite the scanner's own rule id rather than the AI.
    rule_failure: A11yRuleFailure | None = None

    def __post_init__(self) -> None:
        if self.outcome not in TRIAGE_OUTCOMES:
            raise ValueError(
                f"invalid triage outcome {self.outcome!r} — expected one of "
                f"{sorted(TRIAGE_OUTCOMES)}")

    @property
    def blocks(self) -> bool:
        """Whether this may fail a gate. Only a proven or confidently-judged failure does;
        an item awaiting human review must never block a team (the whole point of QA-06)."""
        return self.outcome == TRIAGE_FAILURE

    @property
    def needs_human(self) -> bool:
        return self.outcome == TRIAGE_REVIEW

    @property
    def rule_overrode_ai(self) -> bool:
        """The scanner and the AI genuinely disagreed, and the scanner won."""
        return self.rule_failure is not None and self.judgment.verdict == A11Y_PASS

    @property
    def criteria(self) -> tuple[str, ...]:
        return self.judgment.criteria


def threshold_for(checker: str, thresholds: dict[str, float] | None = None) -> float:
    """The confidence a checker must exceed. Unknown checkers get the default, not an error:
    a new checker must never be *more* permissive than an existing one by accident."""
    if not thresholds:
        return DEFAULT_CONFIDENCE_THRESHOLD
    value = thresholds.get(checker)
    # `is None`, not `or`: a configured 0.0 means "report everything the AI is sure enough
    # to state", which is a deliberate setting, and `or` would silently restore the default.
    return DEFAULT_CONFIDENCE_THRESHOLD if value is None else float(value)


def _matching_failure(judgment: A11yJudgment, candidate: A11yCandidate,
                      failures: Sequence[A11yRuleFailure]) -> A11yRuleFailure | None:
    """The scanner failure, if any, about this element and one of these criteria.

    Matched on all three of route, selector and criterion. A judgment about a *different*
    element, screen or criterion is a different question, and letting a scanner failure
    anywhere on the page silence it would hide real defects.

    A judgment can cover more than one criterion — `semantics` judges 1.3.1 and 4.1.2 at once
    (decision D-A11Y-2) — and a proven failure of *either* is a proven failure of the element.
    """
    index = {failure.key: failure for failure in failures}
    for criterion in judgment.criteria:
        found = index.get((candidate.route, candidate.selector, criterion))
        if found is not None:
            return found
    return None


def triage(judgment: A11yJudgment, candidate: A11yCandidate, *,
           rule_failures: Sequence[A11yRuleFailure] = (),
           thresholds: dict[str, float] | None = None) -> TriagedFinding:
    """Apply the three rules to one judgment. Never raises on a well-formed judgment.

    Order matters, and it is: the scanner first, then uncertainty, then evidence, then
    confidence. The scanner leads because a proven failure settles the question no matter
    how sure or unsure the AI was — including the case where the AI said it was fine.

    `rule_failures` must be a re-readable sequence, and a one-shot iterator is refused
    rather than accepted. Triaging a run means calling this once per judgment against the
    same failures; a generator would be drained by the first call and every judgment after
    it would silently see *no* scanner failures at all — turning the rule that protects
    against a wrong pass into one that quietly stops running. That is precisely the kind of
    silent degradation this module exists to prevent, so it is a loud error instead.
    """
    if not isinstance(rule_failures, Sequence):
        raise TypeError(
            "rule_failures must be a re-readable sequence (list/tuple), not a one-shot "
            f"{type(rule_failures).__name__} — an iterator would be exhausted by the first "
            "judgment and silently disable the scanner rule for the rest of the run"
        )
    threshold = threshold_for(judgment.checker, thresholds)

    def result(outcome: str, reason: str, failure: A11yRuleFailure | None = None):
        return TriagedFinding(outcome=outcome, judgment=judgment, candidate=candidate,
                              reason=reason, threshold=threshold, rule_failure=failure)

    # 1. A measurement beats an opinion — in the one direction only.
    failure = _matching_failure(judgment, candidate, rule_failures)
    if failure is not None:
        template = (REASON_RULE_OVERRODE if judgment.verdict == A11Y_PASS
                    else REASON_RULE_CONFIRMED)
        return result(TRIAGE_FAILURE, template.format(criterion=failure.criterion), failure)

    # 2. A check that could not answer is a routing decision, not a result. Its confidence
    #    is 0.0 by construction, but this is stated rather than left to the gate below so an
    #    "uncertain" judgment can never be reported as a pass by a threshold set to zero.
    if judgment.verdict == A11Y_UNCERTAIN:
        return result(TRIAGE_REVIEW,
                      REASON_UNCERTAIN.format(evidence=judgment.evidence or "no reason given"))

    # 3. No evidence, no failure. Applies to failures only: that is the claim that has to be
    #    defensible to a developer being asked to change code, and to an auditor later.
    if judgment.verdict == A11Y_FAIL and not judgment.evidence.strip():
        return result(TRIAGE_REVIEW, REASON_NO_EVIDENCE)

    # 4. The confidence gate. `<=` because exactly at the threshold rounds toward review:
    #    when the rule is a coin-flip, the conservative answer is to ask a person.
    if judgment.confidence <= threshold:
        return result(TRIAGE_REVIEW, REASON_BELOW_THRESHOLD.format(
            confidence=judgment.confidence, threshold=threshold))

    if judgment.verdict == A11Y_FAIL:
        return result(TRIAGE_FAILURE, REASON_CONFIDENT_FAILURE.format(
            confidence=judgment.confidence, threshold=threshold,
            criteria=", ".join(judgment.criteria)))
    return result(TRIAGE_PASS, REASON_CONFIDENT_PASS.format(
        confidence=judgment.confidence, threshold=threshold))


def thresholds_for(tenant_id) -> dict[str, float]:
    """Per-checker thresholds for a tenant, from the `a11yai` connection's scopes.

    Mirrors `dispatch.caps_for` deliberately — one place a tenant tunes accessibility
    checking, one shape, no second configuration surface to discover:

        {"confidence_thresholds": {"alt": 0.85, "color": 0.75}}

    Checkers left out get the default, so a tenant tunes the one that is noisy without
    restating the other three.

    A misconfiguration **raises** rather than quietly falling back, in all three of its
    forms: a threshold outside 0–1, a value that is not a number, and a checker name that
    does not exist. A negative threshold would make every judgment a hard failure — silently
    turning the safety valve into the opposite of itself — and a misspelled checker would
    leave someone believing they had tuned a check they had not touched. Read once per
    dispatch, this is cheap to get loudly right.
    """
    from integrations.registry import get_connection

    conn = get_connection(tenant_id, "a11yai")
    configured = ((conn.scopes or {}).get("confidence_thresholds") or {}) if conn else {}

    # The union of element and journey checks (QA-20). A journey check has a confidence and a
    # threshold like any other, so it must be tunable here — the alternative is a tenant being
    # told `trap` "does not exist" for a check the platform is actively running against them.
    if unknown := sorted(set(configured) - set(A11Y_ALL_CHECKER_CRITERIA)):
        raise ValueError(
            f"`confidence_thresholds` names accessibility checks that do not exist: "
            f"{', '.join(unknown)} — the checks are "
            f"{', '.join(sorted(A11Y_ALL_CHECKER_CRITERIA))}"
        )

    resolved = {}
    for checker in A11Y_ALL_CHECKER_CRITERIA:
        raw = configured.get(checker)
        if raw is None:
            resolved[checker] = DEFAULT_CONFIDENCE_THRESHOLD
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"confidence threshold for the {checker!r} accessibility check is {raw!r}, "
                f"which is not a number — fix `confidence_thresholds` in this workspace's "
                f"a11yai settings"
            ) from exc
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"confidence threshold for the {checker!r} accessibility check is {value}, "
                f"which is not between 0 and 1 — fix `confidence_thresholds` in this "
                f"workspace's a11yai settings"
            )
        resolved[checker] = value
    return resolved
