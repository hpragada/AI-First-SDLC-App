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
"""
from __future__ import annotations

from dataclasses import dataclass

OK = "ok"
DROPPED_BEFORE_CAPTURE = "never offered to any check"
DROPPED_BEFORE_JUDGING = "captured but never judged"
UNEXPECTED_SURPLUS = "more captured than the manifest expects"


@dataclass(frozen=True)
class RouteCount:
    """What one page was expected to hold, what was picked up, and what got an answer."""

    route: str
    captured: int
    judged: int
    expected: int | None = None      # None when the manifest says nothing about this page

    @property
    def problems(self) -> list[str]:
        found: list[str] = []
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
        return (f"  {self.route:38s} expected {expected}  captured {self.captured:3d}  "
                f"judged {self.judged:3d}   {state}")


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
                 "judged": r.judged, "problems": r.problems}
                for r in self.routes
            ],
        }


def check(*, captured_by_route: dict[str, int], judged_by_route: dict[str, int],
          expected_by_route: dict[str, int] | None = None) -> Completeness:
    """Compare the three counts for every page either side knows about.

    A page that was captured but is absent from `judged_by_route` counts as zero judged rather
    than being skipped, and a page the manifest expects but the run never visited is reported
    with zero captured. Both are the honest reading: a page nobody has a number for is exactly
    the case this check exists to surface, and dropping it from the table would reproduce the
    silence being looked for.
    """
    expected_by_route = expected_by_route or {}
    routes = sorted(set(captured_by_route) | set(judged_by_route) | set(expected_by_route))
    return Completeness(routes=[
        RouteCount(
            route=route,
            captured=captured_by_route.get(route, 0),
            judged=judged_by_route.get(route, 0),
            expected=expected_by_route.get(route),
        )
        for route in routes
    ])
