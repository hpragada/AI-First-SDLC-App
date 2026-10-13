"""Could each golden record ever reach the scored sample at all? (QA-09, QA-10)

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

    node ../harness/verify-selectable.js      # captures, then runs this

**The check `verify-golden.js` cannot make.** That one proves every label's `(route, selector)`
still resolves on the running app, which is necessary and is not enough. A record can resolve
perfectly and still be incapable of ever scoring, because resolving is about the page and
scoring is about the selection rules.

`accuracy._record` is not symmetric, and that asymmetry is the whole reason this file exists:

    expected `fail`       always counts — a true positive if found, a false negative if not
    expected `pass`       counts ONLY if the checker actually selects the element
    expected `uncertain`  never counts; it is scored on calibration instead

So a `pass` twin that the selection rules skip is a record that can never contribute to a
number, in either direction, no matter how many audits are run. It is not wrong — it is inert,
and it looks exactly like a healthy record in every other check.

**This was not hypothetical.** At v0.1.0 the `label` checker had 19 clear records and could
reach a sample of 9. All ten of its pass twins named a control whose accessible name already
contained its visible text, and `_applies_label` skips precisely those — correctly, because the
criterion is met as a matter of fact and there is nothing left to judge. A deliberately balanced
answer key was producing a completely one-sided scored sample, and every check in the harness
was green.

**The rules are imported, never restated.** `rules.py` says the platform owns the selection
table and nobody re-implements it; a copy of it in this file would drift and would then be
certifying the answer key against the wrong rules, which is worse than not checking. That is
also why the capture comes from `verify-selectable.js` in the companion's own shape rather than
from anything invented here.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "backend"))

import labels as labels_module                                      # noqa: E402
from apps.a11y.checkers.rules import CapturedElement, checkers_for  # noqa: E402

#: Below this a checker reads "not yet measurable" in the report. Mirrors
#: `accuracy.DEFAULT_MIN_SAMPLE`; imported rather than repeated would be better, and importing
#: `accuracy` here would pull in the whole scoring path for one integer.
MIN_SAMPLE = 30

#: Checkers that cannot reach `MIN_SAMPLE` for a reason we have looked into and accepted, with
#: the reason. A shortfall listed here is reported and does not fail the run; a shortfall that
#: is NOT listed does fail it, which is the whole point — this is a record of what we know,
#: never a way to turn the check off.
KNOWN_SHORTFALL = {
    "label": (
        "2.5.3 cannot have a balanced sample, and that is a property of the criterion rather "
        "than a gap in the data. A pass record only scores if the checker selects the element, "
        "and the rule correctly skips any control whose accessible name already contains its "
        "visible label as whole words - there is nothing left to judge there. So the only "
        "controls that reach the judge are ones where the words genuinely differ, and those "
        "are either real failures or genuinely arguable. A clearly-correct example is, by "
        "definition, one the check skips. Recall for this checker is meaningful; precision is "
        "not, because no correct examples remain that it could get wrong. See golden/README.md."
    ),
}


def ceilings(golden_dir: Path, captured_path: Path) -> tuple[dict, list, list]:
    """The best sample each checker could reach, what can never score, and what is never seen.

    **Two ways a record fails to reach a checker, and they are not the same problem.** Selection
    is two steps: the companion COLLECTS everything matching its `OFFER` list, and only then do
    the rules decide what to claim.

      * *collected, then declined* — a rule looked at it and said no. Usually correct, sometimes
        a property of the criterion (see `KNOWN_SHORTFALL`), and always visible: `explain()` can
        say which rule declined it and why. Returned as `inert`.
      * *never collected* — the capture never showed it to any rule. Nothing declined it, nothing
        counted it, nothing anywhere records that it existed. Always a gap in the capture, and
        for an expected-`fail` record it is a permanent miss no improvement to any judge can
        recover. Returned as `never_offered`, and it fails the run.

    Until 31 August this file could not tell them apart, because the capture it reads reached
    each element by `document.querySelector` and so collected everything. Three answer-key
    records had been in the second state for a whole audit while every check here was green.
    """
    label_rows, _ = labels_module.load_golden(golden_dir)
    captured = {
        (c["route"], c["selector"]): c
        for c in json.loads(captured_path.read_text(encoding="utf-8"))
    }

    ceiling: Counter = Counter()
    breakdown: dict[str, Counter] = {}
    inert: list[dict] = []
    never_offered: list[dict] = []

    for label in label_rows:
        raw = captured.get((label.route, label.selector))
        counts = breakdown.setdefault(label.checker, Counter())

        if raw is None or raw.get("missing"):
            # verify-golden.js owns this failure and says it far better. Counted so the totals
            # cannot silently drift, and not reported again here.
            counts["selector does not resolve"] += 1
            continue

        # Absent on a capture written before this flag existed. Defaulting to True keeps such a
        # capture reading exactly as it did rather than declaring every record unreachable — the
        # honest default, since an old capture genuinely cannot answer the question.
        offered = bool(raw.get("offered", True))
        claimed = checkers_for(CapturedElement.from_dict(raw))
        # An element no audit collects can never be selected, whatever the rules would have said
        # about it. The rules are still run, because WHICH rule would have claimed it is exactly
        # what tells whoever fixes the capture that the record is worth recovering.
        selected = offered and label.checker in claimed

        if not offered:
            never_offered.append({
                "id": label.record_id, "checker": label.checker, "route": label.route,
                "selector": label.selector, "expected": label.expected,
                "claimed": list(claimed),
            })

        if label.expected == "fail":
            ceiling[label.checker] += 1
            counts["fail — always counts"] += 1
            if not offered:
                counts["  of those, NEVER COLLECTED by the capture (permanent miss)"] += 1
            elif not selected:
                counts["  of those, collected but no rule claimed it (scores as a miss)"] += 1
        elif label.expected == "pass":
            if selected:
                ceiling[label.checker] += 1
                counts["pass — selected, so it counts"] += 1
            elif not offered:
                counts["pass — NEVER COLLECTED by the capture, so it can never count"] += 1
            else:
                counts["pass — collected and declined, so it can never count"] += 1
                inert.append({"id": label.record_id, "checker": label.checker, "route": label.route,
                              "selector": label.selector, "claimed": list(claimed)})
        else:
            counts["uncertain — scored on calibration, never in the sample"] += 1

    return {"ceiling": ceiling, "breakdown": breakdown}, inert, never_offered


def main() -> int:
    golden_dir = Path(sys.argv[1]).resolve()
    captured_path = Path(sys.argv[2]).resolve()
    result, inert, never_offered = ceilings(golden_dir, captured_path)
    ceiling, breakdown = result["ceiling"], result["breakdown"]

    print(f"\n  {'checker':12}{'best sample':>12}{'needs':>7}   verdict")
    short = 0
    known: list[str] = []
    for checker in sorted(breakdown):
        best = ceiling[checker]
        if best >= MIN_SAMPLE:
            verdict = "reachable"
        elif checker in KNOWN_SHORTFALL:
            verdict = f"short by {MIN_SAMPLE - best} - known, and the reason is recorded"
            known.append(checker)
        else:
            verdict = f"SHORT BY {MIN_SAMPLE - best}"
            short += 1
        print(f"  {checker:12}{best:12}{MIN_SAMPLE:7}   {verdict}")

    for checker in sorted(breakdown):
        print(f"\n  {checker}")
        for reason, n in sorted(breakdown[checker].items()):
            print(f"    {n:4}  {reason}")

    if inert:
        # Not automatically an error. A pass label on an element the platform correctly declines
        # is honest — `accuracy.py` gives no credit and no penalty for it. It is listed because
        # a checker that is short of a sample is usually short for exactly this reason, and
        # because a set with many of these is balanced on paper and lopsided in practice.
        print(f"\n  {len(inert)} pass record(s) are collected and then declined by a rule.")
        print("  These can never score. Not an error on its own — see the note in this file.")
        for row in inert:
            claimed = ", ".join(row["claimed"]) or "nothing"
            print(f"    {row['id']:14} {row['checker']:10} {row['route']}{row['selector']}"
                  f"   (claimed by: {claimed})")

    if never_offered:
        # **Always an error, and reported before the sample table's verdict is believed.** No
        # rule declined these; nothing collected them. The capture's OFFER list does not reach
        # them, so no audit of any application will ever put them in front of a checker, and an
        # expected-`fail` record here is a false negative that no better judge can recover.
        #
        # `would have been claimed by` is what makes it actionable: it says the record is real
        # and the rule wants it, so the fix is in the capture rather than in the answer key.
        print(f"\n  {len(never_offered)} record(s) name an element NO AUDIT EVER COLLECTS.")
        print("  The capture's OFFER list does not reach these, so no rule ever sees them and")
        print("  nothing records that they exist. Fix the OFFER list in")
        print("  runner/companion/assets/a11y_audit.mjs, or retire the record.")
        for row in never_offered:
            claimed = ", ".join(row["claimed"]) or "nothing"
            print(f"    {row['id']:14} {row['checker']:10} expected {row['expected']:9} "
                  f"{row['route']}{row['selector']}   (would have been claimed by: {claimed})")

    for checker in known:
        print(f"\n  {checker} is short on purpose:")
        for line in _wrap(KNOWN_SHORTFALL[checker]):
            print(f"    {line}")

    if never_offered:
        # Reported first when both are true: a checker short of a sample BECAUSE its records are
        # never collected has one problem, not two, and `KNOWN_SHORTFALL` is not the answer to it.
        print(f"\n{len(never_offered)} record(s) can never reach a checker because nothing "
              f"collects them. That is a gap in the capture, not a property of the criterion, "
              f"so it does not belong in KNOWN_SHORTFALL.")
        return 1
    if short:
        print(f"\n{short} checker(s) cannot reach {MIN_SAMPLE} scored records from this answer "
              f"key, so no audit will ever produce a number for them. If that is understood "
              f"and accepted, record the reason in KNOWN_SHORTFALL rather than deleting this "
              f"check.")
        return 1
    if known:
        print(f"\nevery checker can reach {MIN_SAMPLE} scored records, except the "
              f"{len(known)} recorded above")
        return 0
    print(f"\nevery checker can reach {MIN_SAMPLE} scored records")
    return 0


def _wrap(text: str, width: int = 92) -> list[str]:
    """Enough wrapping to keep a paragraph readable in a terminal, without a dependency."""
    line: list[str] = []
    out: list[str] = []
    for word in text.split():
        if sum(len(w) + 1 for w in line) + len(word) > width:
            out.append(" ".join(line))
            line = []
        line.append(word)
    if line:
        out.append(" ".join(line))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
