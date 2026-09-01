"""Scoring one checker against one label source (QA-10).

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

Pure arithmetic over data handed in: nothing here reads a file, a database or the clock, so
every rule below is testable without a platform behind it.

**Three things this module refuses to do**, each because doing it produces a number that looks
right and is not:

  * **Score against `truth` instead of `expected_verdict`.** On a genuinely arguable element,
    the correct behaviour is to say `uncertain` and route to a person. A checker that answers
    `pass` confidently there got the right answer for the wrong reason and skipped the review
    queue. Scoring against truth rewards it (GOLDEN_DATASET_SPEC §4).
  * **Compute recall from live adjudications.** Their universe is *findings we reported*, so a
    recall-shaped number built from them has "things we found" as its denominator — that is
    precision wearing recall's name (D-A11Y-63).
  * **Treat a silence as a pass.** An element nobody looked at has no verdict. Reading that as
    "the checker said it was fine" turns every gap in coverage into a free correct answer.

**And the two silences are different**, which is the distinction that makes this worth
building. `NOT_JUDGED` means the element was captured and the run never got to it — a coverage
fact, excluded from accuracy. `NOT_CAPTURED` means it was never offered to any check at all:
the real problem was on the page and the platform said nothing. That is a **miss**, it counts
against recall, and it is reported on its own line because its fix is nowhere near the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from labels import FAIL, LIVE, UNCERTAIN, Label

#: The element was captured and offered, and this run never produced an answer for it — the
#: dispatch cap was reached, or the judging pass stopped early. A coverage fact, not a verdict.
NOT_JUDGED = "not judged"

#: The element was never captured, so no check was ever asked about it. Not a verdict either,
#: but unlike `NOT_JUDGED` this one is a failure to look.
NOT_CAPTURED = "not captured"

SILENCES = frozenset({NOT_JUDGED, NOT_CAPTURED})

#: What a sample size below this means. Not a constant: it is written into the baseline file so
#: it reads as a decision somebody made and can revisit (D-A11Y-65). Three correct calls out of
#: three is not evidence, and a percentage computed over a handful is noise with a decimal point.
DEFAULT_MIN_SAMPLE = 30

NOT_MEASURABLE = "not yet measurable"
UNMEASURED = "unmeasured"


@dataclass(frozen=True)
class Answer:
    """What the platform said about one element — or which way it stayed silent."""

    route: str
    selector: str
    checker: str
    verdict: str                     # pass | fail | uncertain | NOT_JUDGED | NOT_CAPTURED
    confidence: float | None = None
    #: True when the platform reached this verdict from the SELECTION RULES alone, without
    #: asking the AI — the criterion's own wording made the answer a matter of fact (a button
    #: whose accessible name provably contains its visible text meets 2.5.3, and that is a
    #: string comparison, not an opinion).
    #:
    #: **Scored exactly like any other answer**, and that is the point: the rule is compared
    #: against the label, so a rule that ever clears something the answer key calls a failure is
    #: recorded as a miss like any other. It is counted separately only so the printed line can
    #: say how the sample was reached, and nobody mistakes a rule's work for the model's.
    by_rule: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.route, self.selector, self.checker)

    @property
    def is_silence(self) -> bool:
        return self.verdict in SILENCES


@dataclass
class Score:
    """One checker, scored against one source. Every field is a claim we can defend."""

    checker: str
    source: str

    true_positive: int = 0           # said fail, should have failed
    false_positive: int = 0          # said fail, should not have
    false_negative: int = 0          # should have failed, did not say so
    true_negative: int = 0           # said pass, should have passed

    #: Labels whose element was never captured at all. **A silence only ever counts against
    #: us, never for us.** Where the label says the element really did fail, that is a genuine
    #: miss and it is also counted as a false negative, because recall asks how many real
    #: problems we caught and we caught none of this one. Where the label says pass, or says
    #: the case was arguable, the element is counted here and **excluded from every other
    #: figure** — we got no credit for a right answer we never gave. Tracked apart from the
    #: rest because "we looked and got it wrong" and "we never looked" have completely
    #: different fixes, and only one of them is about the model.
    never_looked: int = 0

    #: Records where a confident verdict was itself the error, either way round.
    over_confident: int = 0          # should have been uncertain; answered pass/fail
    under_confident: int = 0         # answer was clear-cut; said uncertain
    calibrated_uncertain: int = 0    # should have been uncertain, and said so

    #: Captured, never judged. Excluded from every figure above and reported separately, so a
    #: run that hit its ceiling reads as incomplete rather than as inaccurate.
    deferred: int = 0

    #: Of the scored records, how many the platform answered from its selection rules alone.
    #: Included in every figure — they are decisions, and they are compared against the answer
    #: key like any other — and counted here so the printed line can say how the sample was
    #: reached. A number that mixes two kinds of work should say that it does.
    settled_by_rule: int = 0

    #: Of `over_confident`, how many were the RULE answering a record the key says an expert
    #: should weigh. Separate from the model's over-confidence because the remedy is different:
    #: a model can be re-prompted; a rule has to be narrowed, or the criterion re-read.
    over_confident_by_rule: int = 0

    #: Labels naming an element this run never had at all — neither captured nor judged, and
    #: not even present as a candidate. Usually a stale label pointing at a page that changed.
    unresolved: list[str] = field(default_factory=list)

    by_difficulty: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def sample(self) -> int:
        """How many records actually produced a scored comparison."""
        return (self.true_positive + self.false_positive
                + self.false_negative + self.true_negative)

    @property
    def measurable(self) -> bool:
        return self.sample > 0

    def precision(self) -> float | None:
        """Of what we flagged, how much was real. Low precision means alert fatigue."""
        flagged = self.true_positive + self.false_positive
        return None if flagged == 0 else self.true_positive / flagged

    def recall(self) -> float | None | str:
        """Of the real problems, how many we caught.

        Returns `UNMEASURED` for a live-adjudication source rather than a number. The
        denominator there would be "findings we reported", which cannot answer the question
        recall asks — and a wrong number here is worse than an honest gap, because low recall
        on a compliance feature means shipping an inaccessible product believing otherwise.
        """
        if self.source == LIVE:
            return UNMEASURED
        real = self.true_positive + self.false_negative
        return None if real == 0 else self.true_positive / real

    def f1(self) -> float | None | str:
        precision, recall = self.precision(), self.recall()
        if isinstance(recall, str):
            return UNMEASURED
        if precision is None or recall is None or (precision + recall) == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    def over_confidence_rate(self) -> float | None:
        """The most dangerous number in the report (GOLDEN_DATASET_SPEC §8).

        These are the records where the honest answer was "I am not sure", the checker gave a
        confident one instead, and the element therefore bypassed the human review queue and
        reached the gate on its own.
        """
        arguable = self.over_confident + self.calibrated_uncertain
        return None if arguable == 0 else self.over_confident / arguable

    def verdict_line(self, min_sample: int) -> str:
        """One sentence about whether these numbers are allowed to mean anything yet.

        **The split is printed whenever there is one**, because a sample reached partly by the
        model and partly by a rule is two kinds of work behind one number, and a reader deciding
        whether to trust it needs to know the mix. Silent on a sample that is all one kind —
        a caption that never varies is one nobody reads.
        """
        if not self.measurable:
            return "nothing to score"
        split = ""
        if self.settled_by_rule:
            asked = self.sample - self.settled_by_rule
            split = f" — {asked} answered by the check, {self.settled_by_rule} settled by rule"
        if self.sample < min_sample:
            return f"{NOT_MEASURABLE} — {self.sample} of {min_sample} records needed{split}"
        return f"scored on {self.sample} records{split}"


def _record(score: Score, label: Label, answer: Answer) -> None:
    """Fold one (label, answer) pair into a score. Every branch here is a decision."""
    band = score.by_difficulty.setdefault(
        label.difficulty or "unstated", {"right": 0, "wrong": 0})

    # An element the run never had an answer for, because it never got that far. Not evidence
    # about the checker in either direction.
    if answer.verdict == NOT_JUDGED:
        score.deferred += 1
        return

    never_looked = answer.verdict == NOT_CAPTURED

    # Nothing was ever asked about this element. It earns no credit anywhere: an element we
    # never looked at is not evidence that the checker is good at anything. Where a real
    # failure was sitting there, the branches below still record the miss.
    if never_looked:
        score.never_looked += 1
        band["wrong"] += 1
        if label.expected == FAIL:
            score.false_negative += 1
        return

    # The arguable records. Scored on calibration alone: whether the checker knew it did not
    # know. Deliberately kept out of precision and recall, which are claims about finding
    # failures, not about knowing when to ask a person.
    if label.expected == UNCERTAIN:
        if answer.verdict != UNCERTAIN:
            score.over_confident += 1
            # …and WHOSE over-confidence it was. A rule that answers a record the answer key
            # says an expert should weigh is a different problem from a model doing it: a model
            # can be re-prompted, a rule has to be narrowed or the criterion re-read. Both skip
            # the human review queue, which is what makes this the report's most dangerous
            # number either way.
            if answer.by_rule:
                score.over_confident_by_rule += 1
            band["wrong"] += 1
        else:
            score.calibrated_uncertain += 1
            band["right"] += 1
        return

    # A clear-cut record the checker declined to call. Harmless to correctness, expensive in
    # expert time, and worth watching as a trend rather than treating as an error.
    if answer.verdict == UNCERTAIN:
        score.under_confident += 1
        band["wrong"] += 1
        if label.expected == FAIL:
            score.false_negative += 1
        else:
            score.true_negative += 1
        return

    # Counted HERE and not at the top, because only what reaches this point enters `sample` —
    # a rule-settled record that was deferred, never captured, or over-confident is tallied by
    # the branch that caught it. Counting it at the top made the printed split describe a
    # different set of records from the one it was splitting, which is the exact class of
    # mistake this whole change exists to remove.
    if answer.by_rule:
        score.settled_by_rule += 1

    said_fail = answer.verdict == FAIL          # a silence is never a `fail`
    should_fail = label.expected == FAIL

    if should_fail and said_fail:
        score.true_positive += 1
        band["right"] += 1
    elif should_fail:
        score.false_negative += 1
        band["wrong"] += 1
    elif said_fail:
        score.false_positive += 1
        band["wrong"] += 1
    else:
        score.true_negative += 1
        band["right"] += 1


def score_all(labels: list[Label], answers: dict[tuple[str, str, str], Answer],
              *, captured: set[tuple[str, str, str]] | None = None) -> list[Score]:
    """Score every checker in `labels` against the answers this run produced.

    `answers` is keyed by (route, selector, checker). `captured` is every (route, selector,
    checker) the run captured, whether or not it was judged — supplying it is what lets a label
    with no answer be told apart into *deferred* and *never captured*. Without it every missing
    answer is treated as never captured, which is the safe direction to be wrong in: it counts
    against us rather than quietly for us.
    """
    captured = captured if captured is not None else set()
    scores: dict[tuple[str, str], Score] = {}

    for label in labels:
        key = (label.checker, label.source)
        score = scores.setdefault(key, Score(checker=label.checker, source=label.source))
        answer = answers.get(label.key)
        if answer is None:
            verdict = NOT_JUDGED if label.key in captured else NOT_CAPTURED
            answer = Answer(*label.key, verdict=verdict)
        _record(score, label, answer)

    return sorted(scores.values(), key=lambda s: (s.source, s.checker))
