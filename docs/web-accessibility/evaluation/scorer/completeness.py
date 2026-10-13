"""Did anything get dropped without saying so? (QA-10, GOLDEN_DATASET_SPEC §8)

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

This is counting, not judging. It needs **no answer key at all**, runs in seconds, and does not
move when the model or the prompt changes — which is why the dataset spec says to build it
first, and why it is the half of this harness that can be trusted from day one.

It exists because silent under-reporting is the worst failure a compliance feature has. A wrong
answer gets argued with. A confident silence gets believed, and then signed.

**Two transitions, and they fail for completely different reasons.**

    expected  ──►  captured  ──►  judged
       │              │              │
       │              │              └─ dropped here: the run reached a ceiling, or the
       │              │                 judging pass stopped early. A coverage problem.
       │              └─ dropped here: nothing on the page was ever offered to a check. This
       │                 is the one that produced "checked" on a page whose only failure was
       │                 never looked at, and no report anywhere mentioned it.
       └─ how many candidates the page is known to hold, from the dataset manifest — never
          from the page itself, because a page must not advertise how many problems it has.

The first transition can only be checked where an expected count exists. The second is always
checkable, on any run, with nothing but the platform's own records. Both are reported; neither
is inferred from the other.

**Counting is not enough, and for a long time counting was all this did.**

The manifest gives a number per page, so the first transition was checked by comparing two
integers: 11 expected, 29 captured, 29 is more than 11, fine. That is a packing list checked by
weighing the bag. A page can capture twenty-nine of the wrong things, miss every one of the
eleven the answer key names, and pass — and on 1 September that is exactly what it printed:
`/help/membership-actions ... ok`, on the same run where the accuracy half reported eleven
records on that page as never looked at. Two halves of one tool, opposite readings of one page,
and nothing anywhere noticing they disagreed.

The answer key names every record it holds — page and selector both. So the names are now
carried through and ticked off one by one, and a page reports **which** expected elements are
missing rather than whether two totals happen to match. The counts stay, because they cover
pages the manifest gives a number for without naming anything.
"""
from __future__ import annotations

from dataclasses import dataclass

OK = "ok"
DROPPED_BEFORE_CAPTURE = "never offered to any check"
DROPPED_BEFORE_JUDGING = "captured but never judged"
UNEXPECTED_SURPLUS = "more captured than the manifest expects"
NAMED_AND_MISSING = "named in the answer key and never offered to its check"

#: How many missing elements to name on the summary line before it stops being readable. The
#: rest are counted there and listed in full in `as_dict`, which is what the results file keeps.
MAX_NAMED = 3


@dataclass(frozen=True)
class RouteCount:
    """What one page was expected to hold, what was picked up, and what got an answer."""

    route: str
    captured: int
    judged: int
    expected: int | None = None      # None when the manifest says nothing about this page
    #: The elements the answer key names for this page that the run never offered to the check
    #: they belong to — `"#card-renew [label]"`, sorted. Empty when the key names nothing here,
    #: which is most pages: the key covers 173 records, the run covers 2,293.
    #:
    #: **This is the check the counts could not make.** `expected` is a total and says nothing
    #: about identity, so a page that captured the wrong twenty-nine things passed.
    missing: tuple[str, ...] = ()

    @property
    def problems(self) -> list[str]:
        found: list[str] = []
        # Named first, because it is the specific finding and the counts below are the coarse
        # approximation of it. A page that reports both should read as one problem, described
        # precisely and then loosely.
        if self.missing:
            found.append(NAMED_AND_MISSING)
        if self.expected is not None:
            if self.captured < self.expected:
                found.append(DROPPED_BEFORE_CAPTURE)
            elif self.captured > self.expected:
                # Not a failure on its own. The page may have grown, or a selection rule may
                # have widened — both are things somebody should know about rather than
                # discover when a label stops resolving.
                found.append(UNEXPECTED_SURPLUS)
        if self.judged < self.captured:
            found.append(DROPPED_BEFORE_JUDGING)
        return found

    @property
    def ok(self) -> bool:
        return not [p for p in self.problems if p != UNEXPECTED_SURPLUS]

    def line(self) -> str:
        expected = "  ?" if self.expected is None else f"{self.expected:3d}"
        state = OK if self.ok else "; ".join(self.problems)
        line = (f"  {self.route:38s} expected {expected}  captured {self.captured:3d}  "
                f"judged {self.judged:3d}   {state}")
        if self.missing:
            shown = ", ".join(self.missing[:MAX_NAMED])
            more = len(self.missing) - MAX_NAMED
            line += f"\n{' ' * 6}missing: {shown}" + (f", and {more} more" if more > 0 else "")
        return line


@dataclass(frozen=True)
class Completeness:
    """Every page of one run, and whether anything went missing between the two transitions."""

    routes: list[RouteCount]

    @property
    def failed(self) -> list[RouteCount]:
        return [route for route in self.routes if not route.ok]

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def totals(self) -> dict[str, int]:
        return {
            "routes": len(self.routes),
            "captured": sum(r.captured for r in self.routes),
            "judged": sum(r.judged for r in self.routes),
            "expected": sum(r.expected for r in self.routes if r.expected is not None),
            "routes_with_an_expected_count": sum(
                1 for r in self.routes if r.expected is not None),
        }

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "totals": self.totals,
            "routes": [
                {"route": r.route, "expected": r.expected, "captured": r.captured,
                 "judged": r.judged, "problems": r.problems, "missing": list(r.missing)}
                for r in self.routes
            ],
        }

    @property
    def missing_named(self) -> int:
        """How many named-and-missing elements across the whole run. One number for the summary
        line, because "nothing was dropped silently" is only worth printing if something checked
        whether anything was."""
        return sum(len(r.missing) for r in self.routes)


def check(*, captured_by_route: dict[str, int], judged_by_route: dict[str, int],
          expected_by_route: dict[str, int] | None = None,
          expected_elements: dict[str, set[tuple[str, str]]] | None = None,
          captured_elements: set[tuple[str, str, str]] | None = None) -> Completeness:
    """Compare what every page was expected to hold against what it actually offered.

    A page that was captured but is absent from `judged_by_route` counts as zero judged rather
    than being skipped, and a page the manifest expects but the run never visited is reported
    with zero captured. Both are the honest reading: a page nobody has a number for is exactly
    the case this check exists to surface, and dropping it from the table would reproduce the
    silence being looked for.

    **Two comparisons, and the second is the one worth trusting.**

      * the counts (`expected_by_route`), which the manifest gives per page and which can only
        ever say whether two totals match;
      * the names (`expected_elements` against `captured_elements`), which say whether the
        specific things the answer key points at were actually offered to the check they belong
        to. `expected_elements` is `{route: {(selector, checker)}}` from the labels;
        `captured_elements` is the run's own `{(route, selector, checker)}`.

    Both are optional and independent. Passing neither reduces this to the second transition
    alone — captured against judged — which needs no answer key at all and is why this half of
    the harness works on any run, on any application, from day one.
    """
    expected_by_route = expected_by_route or {}
    expected_elements = expected_elements or {}
    captured_elements = captured_elements if captured_elements is not None else set()
    routes = sorted(set(captured_by_route) | set(judged_by_route)
                    | set(expected_by_route) | set(expected_elements))

    def absent(route: str) -> tuple[str, ...]:
        wanted = expected_elements.get(route) or set()
        return tuple(sorted(
            f"{selector} [{checker}]"
            for selector, checker in wanted
            if (route, selector, checker) not in captured_elements
        ))

    return Completeness(routes=[
        RouteCount(
            route=route,
            captured=captured_by_route.get(route, 0),
            judged=judged_by_route.get(route, 0),
            expected=expected_by_route.get(route),
            missing=absent(route),
        )
        for route in routes
    ])
