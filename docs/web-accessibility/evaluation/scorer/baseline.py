"""The last numbers we accepted, and whether the new ones may ship (QA-10a, QA-10).

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

**What this gate blocks is our own release** — shipping a changed prompt or a changed model —
and never a client's work. That distinction is the whole of D-A11Y-82: an earlier version of
the plan had these numbers deciding whether a check could stop a client's merge, and the team
rejected it. What decides whether anything blocks a client is the client's own accessibility
policy, which they set themselves. Nothing in the platform reads this file.

Three rules keep the gate usable rather than ignored:

  * **No stored numbers means record, not fail.** A first run has nothing to regress against.
  * **A tolerance band.** On fifty records a two-point move is sampling noise, not a
    regression. A gate with no tolerance fires constantly and gets switched off, which is worse
    than no gate. The band lives in this file so it reads as a decision somebody made.
  * **Too small a sample never gates, in either direction.** Below the minimum a checker is
    reported as *not yet measurable* — never as passing, and never as having regressed.

And one rule about honesty rather than usability: **a checker we previously considered proven,
which has since fallen below the bar, says so plainly.** The old number is not kept. Without
that, "proven once" quietly becomes "trusted forever", and a prompt change degrades a checker
with nobody noticing — the exact failure this whole epic exists to prevent (D-A11Y-65).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from accuracy import DEFAULT_MIN_SAMPLE, UNMEASURED, Score

#: How far a figure may fall before it counts as a regression rather than as noise.
DEFAULT_TOLERANCE = 0.02

RECORDED = "recorded as the first baseline"
IMPROVED = "improved"
STEADY = "unchanged within tolerance"
REGRESSED = "REGRESSED"
TOO_SMALL = "not yet measurable — sample too small to gate on"


@dataclass(frozen=True)
class Comparison:
    """One checker's new figure set against the stored one."""

    checker: str
    source: str
    metric: str
    previous: float | None
    current: float | None
    state: str

    @property
    def blocks_release(self) -> bool:
        return self.state == REGRESSED

    def line(self) -> str:
        def show(value):
            return "  —  " if value is None else f"{value:5.3f}"
        return (f"  {self.checker:10s} {self.source:7s} {self.metric:10s} "
                f"{show(self.previous)} -> {show(self.current)}   {self.state}")


def load(path: Path) -> dict:
    """The stored baseline, or an empty one. A missing file is a first run, not an error."""
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def settings(stored: dict) -> tuple[int, float]:
    """The minimum sample and the tolerance band actually in force.

    Read from the file rather than from the constants, so that changing either is an edit
    somebody makes to a decision record and not a code change nobody sees.
    """
    return (int(stored.get("min_sample", DEFAULT_MIN_SAMPLE)),
            float(stored.get("tolerance", DEFAULT_TOLERANCE)))


def _figures(score: Score) -> dict[str, float | None]:
    """The numbers worth comparing across runs. `UNMEASURED` never becomes a figure."""
    out: dict[str, float | None] = {}
    for name, value in (("precision", score.precision()),
                        ("recall", score.recall()),
                        ("f1", score.f1())):
        out[name] = None if isinstance(value, str) else value
    return out


def compare(scores: list[Score], stored: dict) -> list[Comparison]:
    """Every new figure against its stored predecessor, one row each."""
    min_sample, tolerance = settings(stored)
    previous_all = stored.get("checkers") or {}
    rows: list[Comparison] = []

    for score in scores:
        previous = (previous_all.get(score.checker) or {}).get(score.source) or {}
        for metric, current in _figures(score).items():
            was = previous.get(metric)
            was = None if was is None else float(was)

            if score.sample < min_sample:
                state = TOO_SMALL
            elif current is None or was is None:
                state = RECORDED if was is None else TOO_SMALL
            elif current < was - tolerance:
                state = REGRESSED
            elif current > was + tolerance:
                state = IMPROVED
            else:
                state = STEADY

            rows.append(Comparison(checker=score.checker, source=score.source, metric=metric,
                                   previous=was, current=current, state=state))
    return rows


def blockers(rows: list[Comparison]) -> list[Comparison]:
    """The comparisons that stop us shipping the change. Our release, never a client's work."""
    return [row for row in rows if row.blocks_release]


def updated(scores: list[Score], stored: dict, *, generated_on: str) -> dict:
    """The baseline as it should be stored after an accepted run.

    A checker whose sample is still too small is **left out entirely** rather than written with
    a placeholder, so that a later run with enough records records a real first baseline
    instead of comparing itself against a number that never meant anything.

    A checker that has fallen below its stored figure has the **new, worse number** written
    here. That is the point: keeping the flattering old one is how "proven once" becomes
    "trusted forever".
    """
    min_sample, tolerance = settings(stored)
    checkers: dict[str, dict] = {}
    for score in scores:
        if score.sample < min_sample:
            continue
        figures = {k: v for k, v in _figures(score).items() if v is not None}
        if figures:
            figures["sample"] = score.sample
            checkers.setdefault(score.checker, {})[score.source] = figures

    kept = dict(stored.get("checkers") or {})
    for checker, by_source in checkers.items():
        kept.setdefault(checker, {}).update(by_source)

    return {
        "min_sample": min_sample,
        "tolerance": tolerance,
        "generated_on": generated_on,
        "note": ("Edvensoft-internal. Nothing in the platform reads this file. The gate it "
                 "feeds blocks OUR release of a changed prompt or model, never a client's "
                 "work — see TASK_BACKLOG_QA.md D-A11Y-82."),
        "checkers": kept,
    }


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def unmeasured_note(scores: list[Score]) -> str:
    """One line naming what could not be measured at all, so it is never read as a zero."""
    live = sorted({s.checker for s in scores if isinstance(s.recall(), str)})
    if not live:
        return ""
    return (f"recall is {UNMEASURED} for {', '.join(live)} — scored from live review verdicts, "
            f"whose universe is the findings we already reported, so they cannot say what we "
            f"stayed silent about. Only the golden set can answer that.")
