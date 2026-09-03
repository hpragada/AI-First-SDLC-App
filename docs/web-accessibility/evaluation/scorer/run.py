"""`make a11y-eval` — how accurate are our accessibility checks? (QA-10a, QA-10)

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

Run it:

    make a11y-eval                                   # the latest finished audit
    make a11y-eval ARGS="--run <audit-id>"           # a specific one
    make a11y-eval ARGS="--completeness-only"        # counting only, no answer key needed
    make a11y-eval ARGS="--dry-run"                  # score, print, write nothing

Exit codes, because they mean different things:

    0   nothing to report, or nothing measurable yet
    1   a checker regressed beyond the tolerance band — **our** release is blocked, never a
        client's work (D-A11Y-82)
    2   something was dropped between being on the page and getting an answer
    3   it was not told what to measure, and will not guess

There is no CI in this repository — no pipeline of any kind — so this runs locally through
`make`, which is decision D4 and the entire reason QA-10a exists as its own task.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

# The sibling modules are imported by name, so this directory has to be importable on its own.
# It is not a package under `backend/` and must never become one: nothing tenant-facing may
# import this code, and a search proving that is one of QA-10a's acceptance criteria.
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "backend"))

import accuracy                                                     # noqa: E402
import baseline as baseline_module                                  # noqa: E402
import completeness as completeness_module                          # noqa: E402
import labels as labels_module                                      # noqa: E402

DEFAULT_GOLDEN = HERE.parent / "golden"
DEFAULT_BASELINE = HERE / "baseline.json"
DEFAULT_RESULTS = HERE / "results"

RULE = "=" * 78


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="a11y-eval",
        description="Score the accessibility checks against whatever answer key exists.")
    parser.add_argument("--tenant", default=os.environ.get("A11Y_EVAL_TENANT"))
    parser.add_argument("--project", default=os.environ.get("A11Y_EVAL_PROJECT"))
    parser.add_argument("--run", default=None,
                        help="audit id to score; defaults to the latest finished one")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--app-version", default=os.environ.get("MERIDIAN_VERSION", ""),
                        help="version of the app under test, checked against the manifest")
    parser.add_argument("--completeness-only", action="store_true",
                        help="count what was dropped; skip scoring entirely")
    parser.add_argument("--dry-run", action="store_true",
                        help="print everything, write nothing")
    # A figure can be correct and still not settled — the first baseline locks `structure` at
    # 0.833 while the three records that put it there are disputed between our checker and the
    # answer key's author, unadjudicated. A number that outlives the reason for it is read three
    # months later as a settled fact, so whatever qualifies it travels IN the results file
    # rather than in somebody's memory of the day it was written.
    parser.add_argument("--note", default="", metavar="TEXT",
                        help="a caveat to record alongside this run's figures")
    return parser.parse_args(argv)


def _print_completeness(result) -> None:
    print(f"\n{RULE}\nCOMPLETENESS — was anything dropped without saying so?\n{RULE}")
    totals = result.totals
    print(f"  {totals['routes']} page(s); {totals['captured']} element-checks offered, "
          f"{totals['judged']} answered")
    if totals["routes_with_an_expected_count"] == 0:
        print("  No page has an expected count yet, so only the second transition is checked.")
        print("  Expected counts live in the golden set's manifest.json — never in the app,")
        print("  which must not advertise how many problems it holds.")
    print()
    for route in result.routes:
        print(route.line())
    if result.ok:
        # Say WHAT was checked, not just that it passed. "Nothing was dropped" used to mean
        # "the totals add up", which is a much weaker claim than it sounds and was true on a
        # page that had missed every element the answer key named.
        print("\n  Nothing was dropped silently — the counts reconcile on every page, and every"
              "\n  element the answer key names was offered to the check it belongs to.")
    else:
        print(f"\n  {len(result.failed)} page(s) lost something between being on the page and")
        print("  getting an answer. That is the failure this check exists to make loud.")
        if result.missing_named:
            print(f"\n  {result.missing_named} element(s) the answer key names were never "
                  f"offered to their check.")
            print("  Named above, per page. These are not scored against the checker: nothing")
            print("  asked it, so nothing it did or did not say is evidence either way.")


def _print_scores(scores, min_sample: int) -> None:
    print(f"\n{RULE}\nACCURACY — per check, per source\n{RULE}")
    if not scores:
        print("  Nothing scored.")
        return
    for score in scores:
        recall, f1 = score.recall(), score.f1()

        def show(value):
            if value is None:
                return "  —  "
            if isinstance(value, str):
                return value
            return f"{value:5.3f}"

        print(f"\n  {score.checker}  ({score.source})  — {score.verdict_line(min_sample)}")
        print(f"    precision {show(score.precision())}   recall {show(recall)}   "
              f"F1 {show(f1)}")
        print(f"    flagged and real {score.true_positive} · false alarms "
              f"{score.false_positive} · missed {score.false_negative}")
        if score.never_looked:
            # Called out on its own line because it is the one number here whose fix is
            # nowhere near the model: these elements were never offered to any check.
            was = "was" if score.never_looked == 1 else "were"
            print(f"    -> {score.never_looked} of those {was} NEVER LOOKED AT — not "
                  f"captured, so no check was ever asked")
        if score.over_confident or score.calibrated_uncertain:
            rate = score.over_confidence_rate()
            print(f"    over-confident on {score.over_confident} arguable record(s)"
                  + (f" ({rate:.0%})" if rate is not None else "")
                  + " — these skip the human review queue")
            # Said out loud, because the two have different remedies and the rule's version is
            # the easier one to miss: a rule answers silently, at no cost, on every run.
            if score.over_confident_by_rule:
                n = score.over_confident_by_rule
                print(f"       of those, {n} {'was' if n == 1 else 'were'} settled by RULE, "
                      f"not by the check — narrow the rule, do not re-prompt the model")
        if score.under_confident:
            print(f"    said 'not sure' on {score.under_confident} clear-cut record(s) "
                  f"— costs expert time, harms nothing")
        if score.deferred:
            print(f"    {score.deferred} record(s) captured but never judged — excluded from "
                  f"every figure above")
        if score.by_difficulty:
            bands = "  ".join(
                f"{band}: {counts['right']}/{counts['right'] + counts['wrong']}"
                for band, counts in sorted(score.by_difficulty.items()))
            print(f"    by difficulty  {bands}")


def _print_comparisons(rows, stored: dict) -> None:
    print(f"\n{RULE}\nAGAINST THE LAST ACCEPTED NUMBERS\n{RULE}")
    if not stored:
        print("  No baseline stored. This run's numbers become the baseline rather than")
        print("  failing — a first run has nothing to have regressed against.")
    interesting = [r for r in rows if r.state != baseline_module.TOO_SMALL]
    if not interesting:
        print("  Every checker is still below the minimum sample, so nothing is compared.")
        return
    for row in interesting:
        print(row.line())


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    _setup_django()
    import platformdata                                             # noqa: PLC0415

    try:
        tenant_id, project_id = platformdata.resolve_project(
            tenant_id=args.tenant, project_id=args.project)
    except platformdata.CannotTellWhatToMeasure as error:
        print(f"\n{error}", file=sys.stderr)
        return platformdata.CannotTellWhatToMeasure.exit_code
    run_id = args.run or platformdata.latest_complete_audit(
        tenant_id=tenant_id, project_id=project_id)
    if not run_id:
        print("This project has no finished audit, so there is nothing to score. Run one "
              "first.", file=sys.stderr)
        return 0

    run = platformdata.run_answers(
        tenant_id=tenant_id, project_id=project_id, run_id=run_id)

    print(f"{RULE}\na11y-eval — Edvensoft-internal. Nothing in the platform reads this.\n"
          f"{RULE}\n  project {project_id}\n  audit   {run_id}")

    # ── the half that needs no answer key ────────────────────────────────────────────
    try:
        golden_labels, manifest = labels_module.load_golden(args.golden)
    except labels_module.DatasetError as error:
        print(f"\nThe golden set cannot be trusted, so nothing was scored against it:\n  "
              f"{error}", file=sys.stderr)
        return 1

    expected = (manifest.get("expected_candidates") or {}) if manifest else {}
    # **The names, not just the totals.** The manifest gives a count per page and the labels
    # give the exact page + element + check for every record they hold, so the completeness
    # pass can tick the list off by name instead of weighing the bag. Built from `golden_labels`
    # only — a live adjudication is a reviewer's ruling on a finding that was already reported,
    # so it can never be "expected but never captured".
    expected_elements: dict[str, set[tuple[str, str]]] = {}
    for lab in golden_labels:
        expected_elements.setdefault(lab.route, set()).add((lab.selector, lab.checker))
    result = completeness_module.check(
        expected_elements=expected_elements,
        captured_elements=run["captured"],
        captured_by_route=run["captured_by_route"],
        judged_by_route=run["judged_by_route"],
        expected_by_route={str(k): int(v) for k, v in expected.items()},
    )
    _print_completeness(result)

    if args.completeness_only:
        return 0 if result.ok else 2

    # ── the half that does ───────────────────────────────────────────────────────────
    if manifest:
        try:
            labels_module.check_app_version(manifest, args.app_version)
        except labels_module.DatasetError as error:
            print(f"\n{error}", file=sys.stderr)
            return 1

    live_labels, live_answers = platformdata.live_labels(
        tenant_id=tenant_id, project_id=project_id)

    if not golden_labels and not live_labels:
        print(f"\n{RULE}\nNO ANSWER KEY\n{RULE}")
        print("  There is nothing to score against, so no number is printed. Silence is never")
        print("  reported as a score.")
        print(f"\n  The golden set would live at {args.golden} — it does not exist yet (QA-09).")
        print("  Live review verdicts would come from findings a reviewer has confirmed or")
        print("  rejected; every finding on this project is still awaiting review.")
        return 0

    answers = {**run["answers"], **live_answers}
    scores = accuracy.score_all(
        golden_labels + live_labels, answers, captured=run["captured"])

    stored = baseline_module.load(args.baseline)
    min_sample, tolerance = baseline_module.settings(stored)
    _print_scores(scores, min_sample)

    note = baseline_module.unmeasured_note(scores)
    if note:
        print(f"\n  NOTE: {note}")

    comparisons = baseline_module.compare(scores, stored)
    _print_comparisons(comparisons, stored)

    blockers = baseline_module.blockers(comparisons)
    generated_on = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = {
        "generated_on": generated_on,
        "project": project_id,
        "audit": str(run_id),
        "min_sample": min_sample,
        "tolerance": tolerance,
        "completeness": result.as_dict(),
        "scores": [
            {"checker": s.checker, "source": s.source, "sample": s.sample,
             "precision": s.precision(),
             "recall": s.recall() if isinstance(s.recall(), str) else s.recall(),
             "f1": s.f1() if isinstance(s.f1(), str) else s.f1(),
             "true_positive": s.true_positive, "false_positive": s.false_positive,
             "false_negative": s.false_negative, "true_negative": s.true_negative,
             "never_looked": s.never_looked, "deferred": s.deferred,
             "over_confident": s.over_confident, "under_confident": s.under_confident,
             "by_difficulty": s.by_difficulty}
            for s in scores
        ],
        "blocked": [f"{b.checker}/{b.source}/{b.metric}" for b in blockers],
        "note": args.note,
    }

    if not args.dry_run:
        args.results.mkdir(parents=True, exist_ok=True)
        stamp = generated_on.replace(":", "").replace("-", "")
        out = args.results / f"{stamp}.json"
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\n  results written to {out.relative_to(REPO)}")

    if blockers:
        print(f"\n{RULE}\nSHIPPING IS BLOCKED\n{RULE}")
        for blocker in blockers:
            print(f"  {blocker.checker} ({blocker.source}) {blocker.metric}: "
                  f"{blocker.previous:.3f} -> {blocker.current:.3f}")
        print("\n  What is blocked is OUR release of this prompt or model change. No client's")
        print("  work is affected by these numbers, and nothing in the platform reads them.")
        print("  The stored baseline is left alone so the comparison stays honest.")
        return 1

    if not args.dry_run:
        baseline_module.save(
            args.baseline,
            baseline_module.updated(scores, stored, generated_on=generated_on))
        print(f"  baseline updated at {args.baseline.relative_to(REPO)}")

    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
