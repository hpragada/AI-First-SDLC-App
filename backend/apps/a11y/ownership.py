"""Who checks which criterion — the routing registry behind every accessibility run (QA-05).

For each of the 55 WCAG 2.2 Level A/AA success criteria this answers two questions:

* **owner** — who makes the decisive call: the rule engine (`rule`), our AI (`ai`), or a
  person (`human`). This is what routes a check to an engine.
* **tier** — `in_poc` (an automated or AI check ships in the POC), `phase_2` (reachable once
  Phase-2 interaction testing exists), or `human` (human-led with human sign-off, always).

Two facts sit alongside them, because almost no criterion belongs to one engine outright:

* **`secondary_checks`** — what another engine contributes where it is not the decider. 3.3.2
  is rule-owned, yet the AI "judges adequacy of instructions"; 1.2.2 is human-owned, yet a
  rule "can flag a missing caption track". Ask `criteria_touched_by("ai")` rather than only
  `criteria_for(owner="ai")`, or every hybrid contribution is invisible to routing.
* **`partial_auto_flag`** — the 6 of 15 human-led criteria a machine can partially flag. It
  never licenses an automatic verdict; it means a reviewer starts from a hint.

**Why both, when owner looks like enough.** The 30 human-owned criteria split exactly
15 / 15: fifteen are reached by Phase 2 (2.1.1 Keyboard, 2.4.3 Focus Order, 3.3.1 Error
Identification …) and fifteen never will be (caption accuracy, flash thresholds, legal
error prevention). `owner` cannot tell those apart, so a coverage report built on `owner`
alone would tell a client **30** criteria need a person when the honest answer is **15**.

Once the QA backlog is complete, 19 + 21 = **40** criteria carry an automated or AI check and
**15** genuinely remain human. Both numbers come from `tier`, and neither from `owner`.

**This is our judgment, not the standard.** QA-04's tables hold published W3C text; this one
holds Edvensoft's engineering assessment from Report 1 — Addendum A. It is platform-wide for
the same reason and under the same named carve-out (migration `0006_wcag_platform_wide`):
it contains no tenant data, is derived wholly from a committed file, and is never
tenant-writable. A tenant cannot decide that a criterion needs less checking than it does.

**Nothing is ever silently unowned.** A load refuses unless all 55 criteria are present with
exactly one owner and one tier each, and `verify_complete()` re-checks that against the
criteria actually loaded — because a criterion with no row is a criterion no run ever routes.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from django.db import transaction

from .wcag import DEFAULT_VERSION, UnknownCriterion, UnpublishedRows

DATASET_PATH = Path(__file__).resolve().parent / "data" / "ownership.json"

__all__ = [
    "DATASET_PATH", "ENGINEERING_OVERRIDES", "IncompleteOwnership", "OwnershipNotLoaded",
    "UnknownCriterion", "UnpublishedRows", "applied_overrides", "criteria_for",
    "criteria_touched_by", "dataset", "is_in_poc", "load_ownership", "needs_human_always",
    "ownership", "partially_flaggable", "verify_complete",
]


class OwnershipNotLoaded(RuntimeError):
    """The registry has never been loaded — `load_ownership()` has not run here."""


class IncompleteOwnership(RuntimeError):
    """A loaded criterion has no owner, so nothing would ever route a check for it."""


ENGINEERING_OVERRIDES: dict[str, dict] = {
    # R14, agreed 2026-08-27: "the rationale is correct and the owner is not."
    #
    # Addendum A gives 1.4.11 to `rule` on the strength of "contrast >= 3:1 is computable",
    # and its own rationale in the same cell immediately qualifies that -- "but 'which
    # graphics matter' needs some review." 1.4.11 is a criterion in two halves: whether you
    # can see where the CONTROLS are is arithmetic, and `page_rules` decides it; whether the
    # meaningful parts of the ICONS, CHARTS AND DIAGRAMS can be made out requires knowing
    # which parts of a picture carry meaning, and nothing deterministic knows that.
    #
    # Recording it as rule-only is how the judged half went unbuilt for four tasks while the
    # criterion was reported as covered -- and, on 1 September, how holding that half back
    # would have handed the whole criterion to the arithmetic. The decisive half decides, so
    # the owner is `ai` and the rule is recorded where a contributing engine belongs.
    #
    # The correction was agreed and written down on 27 August and the check was built the
    # same day. **The registry was never changed to match**, so the map of what the AI owns
    # and the registry disagreed, and five separate guards said so every day for five days.
    # This is that last step.
    "1.4.11": {
        "owner": "ai",
        "secondary_checks": [
            {"engine": "rule",
             "note": "page_rules measures every control's edge against 3:1"},
        ],
    },
}


@lru_cache(maxsize=1)
def dataset() -> dict:
    """The committed dataset, read once per process. Never mutated."""
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def applied_overrides(data: dict) -> dict:
    """The committed dataset with the team's recorded corrections applied, for ROUTING only.

    **Why this exists as a layer rather than an edit to the file.** `data/ownership.json` is not
    a decision record — it is a *derivation*, rebuilt from the committed research PDF by
    `ownership_build` and proved against eight independent cross-checks including the report's
    own headline counts (RULE 14 / AI 11 / HUMAN 30) and its enumeration of the fourteen
    rule-primary criteria. Editing a row there would make the file disagree with its own source
    and `build_ownership_dataset --check` would fail, correctly. The report says what the report
    says, and it stays saying it.

    So a place the platform can disagree *by name* has to exist, and this is it. The same shape
    the build already uses for corrections R7, R8 and decision D5: state the departure, state
    why, and let a test hold it — never reconcile a difference quietly.

    Applied at LOAD, so `dataset()` stays a faithful read of the file (and the tests that hold it
    to the report keep passing), while `CriterionOwnership` -- the table every routing and
    conformance decision actually reads -- carries the corrected view.

    Every entry must be recorded in `docs/web-accessibility/RESEARCH_CORRECTIONS.md`. A change
    here without one is how the last five days happened.
    """
    numbers = {row["number"] for row in data.get("criteria") or ()}
    if unknown := sorted(set(ENGINEERING_OVERRIDES) - numbers):
        raise UnknownCriterion(
            f"an ownership override names criteria the committed registry does not have: "
            f"{', '.join(unknown)}"
        )
    if not ENGINEERING_OVERRIDES:
        return data
    return {**data, "criteria": [
        {**row, **ENGINEERING_OVERRIDES.get(row["number"], {})}
        for row in data["criteria"]
    ]}


def load_ownership(*, version: str = DEFAULT_VERSION, data: dict | None = None) -> dict:
    """Load (or refresh) the registry. Returns created/updated counts.

    Idempotent: rows are matched on (version, number) and updated in place.

    Refuses, before writing anything, if the table holds a row the committed dataset does
    not — see `UnpublishedRows` on `wcag.py`. Nothing in the platform writes this table, so
    a stray row means something reached the database out of band and the routing silently
    differs from the report.

    Writes require the migration/owner role; the app role has SELECT only.
    """
    from .models import CriterionOwnership

    data = applied_overrides(data or dataset())
    if data.get("version") != version:
        raise ValueError(
            f"dataset holds WCAG {data.get('version')!r}, asked to load {version!r}")

    published = {row["number"] for row in data["criteria"]}
    have = set(CriterionOwnership.objects.filter(version=version)
               .values_list("number", flat=True))
    if strays := sorted(have - published):
        raise UnpublishedRows(
            f"the criterion ownership table holds rows that are not in the committed "
            f"registry — {', '.join(strays)}. Nothing in the platform writes this table. "
            f"Remove them deliberately, then reload."
        )

    counts = {"created": 0, "updated": 0}
    with transaction.atomic():
        for row in data["criteria"]:
            _, created = CriterionOwnership.objects.update_or_create(
                version=version, number=row["number"],
                defaults={"owner": row["owner"], "tier": row["tier"],
                          "rationale": row["rationale"],
                          "secondary_checks": row["secondary_checks"],
                          "partial_auto_flag": row["partial_auto_flag"]},
            )
            counts["created" if created else "updated"] += 1
    return counts


def ownership(number: str, *, version: str = DEFAULT_VERSION):
    """The `CriterionOwnership` row for `number`. Raises rather than returning nothing.

    A caller that gets `None` here would route no check at all and report a pass; an
    exception cannot be mistaken for "nothing to do".
    """
    from .models import CriterionOwnership

    row = CriterionOwnership.objects.filter(version=version, number=number).first()
    if row is not None:
        return row

    if not CriterionOwnership.objects.filter(version=version).exists():
        raise OwnershipNotLoaded(
            f"no WCAG {version} ownership registry is loaded on this database; "
            f"run `python manage.py load_ownership` (as the migration role)"
        )
    raise UnknownCriterion(
        f"{number!r} is not a Level A/AA success criterion in WCAG {version}"
    )


def criteria_for(*, owner: str | None = None, tier: str | None = None,
                 version: str = DEFAULT_VERSION) -> list[str]:
    """The criterion numbers matching an owner and/or a tier, in numeric order.

    This is how a run asks "which criteria does the AI decide?" without any caller having to
    know the stored strings.

    Sorted numerically rather than by the column, because sorting text puts 1.4.10 before
    1.4.2 — harmless in a query, confusing in a report a person reads.
    """
    from .models import CriterionOwnership

    rows = CriterionOwnership.objects.filter(version=version)
    if owner is not None:
        rows = rows.filter(owner=owner)
    if tier is not None:
        rows = rows.filter(tier=tier)
    return sorted((row.number for row in rows),
                  key=lambda n: [int(part) for part in n.split(".")])


def criteria_touched_by(engine: str, *, version: str = DEFAULT_VERSION) -> list[str]:
    """Criteria an engine contributes to **without owning** — in numeric order.

    The routing question `criteria_for` cannot answer: the label checker's own criterion is
    2.5.3, but the report also has it speaking to 3.3.2, which the rule engine owns. Asking
    only "what does the AI own?" would miss every hybrid.

    A finding raised here is a contribution, never a verdict on the criterion — the owner
    still decides, and an AI contribution never overrides a deterministic rule failure.
    """
    from .models import CriterionOwnership

    return sorted(
        (row.number for row in CriterionOwnership.objects.filter(version=version)
         if any(check["engine"] == engine for check in row.secondary_checks)),
        key=lambda n: [int(part) for part in n.split(".")],
    )


def partially_flaggable(*, version: str = DEFAULT_VERSION) -> list[str]:
    """The human-led criteria a machine can still hand a reviewer a head start on.

    Six of the fifteen: a missing caption track can be detected, a flash rate measured. What
    conformance turns on — whether the captions are *accurate* — stays human, so this never
    licenses reporting a pass.
    """
    from .models import CriterionOwnership

    return sorted(
        CriterionOwnership.objects.filter(version=version, partial_auto_flag=True)
        .values_list("number", flat=True),
        key=lambda n: [int(part) for part in n.split(".")],
    )


def is_in_poc(number: str, *, version: str = DEFAULT_VERSION) -> bool:
    """True when an automated or AI check for this criterion ships in the POC.

    Deliberately not called something like "in scope now": scope changes as the backlog is
    built, and a name that means different things at different times is a bug waiting to be
    written. This asks one fixed question about the plan the report records.
    """
    from .models import Tier

    return ownership(number, version=version).tier == Tier.IN_POC


def needs_human_always(number: str, *, version: str = DEFAULT_VERSION) -> bool:
    """True when this criterion needs a person's sign-off no matter how far the AI goes.

    The one question a conformance report must not get wrong: 15 criteria answer True, not
    the 30 that are merely human-*owned* today.
    """
    from .models import Tier

    return ownership(number, version=version).tier == Tier.HUMAN


def verify_complete(*, version: str = DEFAULT_VERSION) -> int:
    """Every loaded criterion has exactly one owner. Returns how many were checked.

    Loading validates the committed file; this validates the *database*, which is what a
    run actually reads. A criterion present in the standard but absent here is a criterion
    no run would route and no report would mention — the silent gap this task exists to
    prevent.
    """
    from .models import CriterionOwnership, WcagCriterion

    criteria = set(WcagCriterion.objects.filter(version=version)
                   .values_list("number", flat=True))
    owned = set(CriterionOwnership.objects.filter(version=version)
                .values_list("number", flat=True))
    if not criteria:
        raise OwnershipNotLoaded(
            f"no WCAG {version} criteria are loaded, so ownership cannot be verified; "
            f"run `python manage.py load_wcag` first")
    if unowned := sorted(criteria - owned):
        raise IncompleteOwnership(
            f"{len(unowned)} WCAG {version} criteria have no owner and would never be "
            f"checked: {', '.join(unowned)}")
    if orphaned := sorted(owned - criteria):
        raise IncompleteOwnership(
            f"ownership rows for criteria that are not loaded: {', '.join(orphaned)}")
    return len(owned)
