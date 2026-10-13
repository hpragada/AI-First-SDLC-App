"""The answer key, whichever form it comes in (QA-10, D-A11Y-63).

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

There are two sources of expert verdicts and they are **not interchangeable evidence**:

  1. **The golden set** — a fixed answer key (`../golden/*.json`). The only source that can
     measure *recall*, because it also lists what a checker should have found and did not.
  2. **Live adjudications** — a reviewer's `confirmed` / `rejected` on a finding the platform
     already raised. Accrues as a by-product of normal review work and needs no labelling
     session, but its universe is *findings we reported*, so it can never say what we missed.

Both are expert verdicts on one element of one screen — the same shape — so both become a
`Label`. Every `Label` carries the source it came from, and nothing downstream is allowed to
add the two together. A precision figure from live review and one from a fixed answer key are
different claims about the world.

This module reads the golden files only. Live adjudications live in the platform database and
are read by `platformdata.py`, which is the one module here that touches Django.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Where a verdict came from. Kept as strings rather than an enum because they are printed,
#: written into the results file, and used as dictionary keys in the baseline.
GOLDEN = "golden"
LIVE = "live"

#: The three things a well-calibrated checker may be expected to return. `uncertain` is not a
#: hedge — it is the correct answer on a record where a confident verdict would be over-claiming
#: (GOLDEN_DATASET_SPEC §4), and scoring it as though it were pass/fail rewards exactly the
#: behaviour that empties the human review queue.
PASS, FAIL, UNCERTAIN = "pass", "fail", "uncertain"
VERDICTS = frozenset({PASS, FAIL, UNCERTAIN})

#: The dataset spec and the platform call the same checks by different names, and nobody noticed
#: until a label was joined to a verdict for the first time. GOLDEN_DATASET_SPEC §2 says
#: `meaningful-alt` / `fake-semantics` / `colour-only` / `label`; the platform's own names are
#: `checkers.rules.CHECKERS`.
#:
#: Translated here rather than by correcting one side, because both are already written down —
#: the spec is what an expert labelling by hand reads, and the platform's names are in stored
#: data going back to the first run. Anything not in this table passes through unchanged, so a
#: dataset that already uses the platform's names simply works.
#:
#: Getting this wrong would not have been subtle: **no label would have joined to any verdict**,
#: every record would have scored as never-looked-at, and the report would have said the
#: checkers found nothing at all.
CHECKER_ALIASES: dict[str, str] = {
    "meaningful-alt": "alt",
    "fake-semantics": "semantics",
    "colour-only": "color",
    "color-only": "color",
    "label-in-name": "label",
    # `structure` (24 Aug) and `graphics` (27 Aug) arrived after the dataset spec was written,
    # so they have no spec name to translate FROM — these are the phrasings a person labelling
    # by hand actually reaches for. Harmless if unused: anything absent from this table passes
    # through unchanged, so a dataset already using the platform's own names still works.
    "fake-structure": "structure",
    "real-structure": "structure",
    "non-text-contrast": "graphics",
    "graphic-contrast": "graphics",
}

#: Difficulty bands, so a flat accuracy figure can be broken apart. A checker at 95% on clear
#: cases and 40% on borderline ones is a very different product from one at 78% flat.
DIFFICULTIES = ("clear", "borderline", "ambiguous")


class DatasetError(Exception):
    """The answer key cannot be trusted, so nothing is scored against it.

    Raised rather than warned about on purpose. Every failure mode this guards produces numbers
    that look fine and mean nothing: a record silently dropped inflates every score, and a
    dataset scored against a different version of the app is measuring something nobody
    labelled.
    """


@dataclass(frozen=True)
class Label:
    """One expert verdict on one element, from whichever source produced it."""

    source: str                 # GOLDEN | LIVE
    route: str
    selector: str
    checker: str
    criterion: str
    #: What a well-calibrated checker *should return* — pass, fail or uncertain. This is what
    #: gets scored, never `truth`. See the class docstring of `accuracy.Score`.
    expected: str
    #: What is actually correct per WCAG, pass or fail. Blank for a live adjudication, which
    #: records a reviewer's ruling on a reported finding rather than a standalone truth.
    truth: str = ""
    difficulty: str = ""
    record_id: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        """How a label finds the answer the platform gave: route, element, check."""
        return (self.route, self.selector, self.checker)


def _require(record: dict, field: str, where: str) -> str:
    value = str(record.get(field) or "").strip()
    if not value:
        raise DatasetError(f"{where}: record is missing `{field}`")
    return value


def load_golden(directory: Path) -> tuple[list[Label], dict]:
    """Every labelled record in the golden set, with its manifest.

    Returns `([], {})` when the directory does not exist — that is *not* an error. The set is
    hand-labelled expert work (QA-09) and may legitimately not exist yet; the caller reports
    "no label source" and exits rather than inventing a number. What *is* an error is a set
    that exists and does not add up, because that produces a plausible wrong answer.
    """
    if not directory.is_dir():
        return [], {}

    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise DatasetError(
            f"{directory} exists but has no manifest.json. The manifest carries the dataset "
            f"version, the app version it was labelled against and the per-criterion counts; "
            f"without it there is no way to tell a complete set from a half-written one."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    labels: list[Label] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "manifest.json":
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise DatasetError(f"{path.name}: expected a list of records, got {type(records)}")
        for index, record in enumerate(records):
            where = f"{path.name}[{index}]"
            expected = _require(record, "expected_verdict", where)
            if expected not in VERDICTS:
                raise DatasetError(
                    f"{where}: expected_verdict is {expected!r}, which is not one of "
                    f"{sorted(VERDICTS)}"
                )
            difficulty = str(record.get("difficulty") or "").strip()
            if difficulty and difficulty not in DIFFICULTIES:
                raise DatasetError(
                    f"{where}: difficulty is {difficulty!r}, not one of {list(DIFFICULTIES)}"
                )
            named = _require(record, "checker", where).lower()
            labels.append(Label(
                source=GOLDEN,
                route=_require(record, "route", where),
                selector=_require(record, "selector", where),
                checker=CHECKER_ALIASES.get(named, named),
                criterion=_require(record, "criterion", where),
                expected=expected,
                truth=str(record.get("truth") or "").strip(),
                difficulty=difficulty,
                record_id=str(record.get("id") or where),
            ))

    _check_counts(labels, manifest, directory)
    return labels, manifest


def _check_counts(labels: list[Label], manifest: dict, directory: Path) -> None:
    """The manifest's per-criterion counts must match what is actually in the files.

    A hard stop, because the failure it catches is invisible in the output: half a criterion's
    records left out of a file still scores, still prints a percentage, and the percentage is
    computed over a sample nobody chose.
    """
    declared = manifest.get("counts") or {}
    if not declared:
        return
    actual: dict[str, int] = {}
    for label in labels:
        actual[label.criterion] = actual.get(label.criterion, 0) + 1
    for criterion, count in sorted(declared.items()):
        if actual.get(criterion, 0) != int(count):
            raise DatasetError(
                f"{directory}/manifest.json says {count} record(s) for {criterion}; the files "
                f"hold {actual.get(criterion, 0)}. Every dropped record inflates every score, "
                f"so this refuses to run rather than scoring a sample nobody chose."
            )


def check_app_version(manifest: dict, running_version: str) -> None:
    """The dataset must be scored against the version of the app it was labelled against.

    A hard stop (GOLDEN_DATASET_SPEC §7 rule 1). A label describes one element on one version
    of one page; change the page and the label may no longer describe anything. Scoring across
    a mismatch produces numbers that look completely normal and mean nothing at all.

    **Skipped only when the ANSWER KEY states no version.** That was the original condition on
    both sides, and it was right while the fixture declared no version at all — failing then
    would have made the harness unbuildable. The fixture has declared one since v1.3.0, and it
    is published in `routes.json`, so the reason for the leniency has expired on the running
    side.

    Leaving it there was a hole with no floor under it. `run.py` reads the running version from
    a `--app-version` flag that **defaults to empty**, so the default behaviour of the one hard
    stop protecting every number this tool produces was to do nothing at all. Point a run at an
    older checkout of the app and you get a full report, normal-looking figures, and no warning
    of any kind. An unstated running version is now a refusal that tells you what to pass.
    """
    labelled = str(manifest.get("app_version") or "").strip()
    if not labelled:
        return
    if not running_version.strip():
        raise DatasetError(
            f"the golden set was labelled against app version {labelled}, and this run did not "
            f"say which version it audited. Pass --app-version (or set MERIDIAN_VERSION) — "
            f"scoring an answer key against an app it may not describe produces numbers that "
            f"look completely normal and mean nothing."
        )
    if labelled != running_version.strip():
        raise DatasetError(
            f"the golden set was labelled against app version {labelled}, but the app reports "
            f"{running_version.strip()}. Re-label the affected records and bump "
            f"dataset_version; a label that no longer describes the page it names is worse "
            f"than no label."
        )
