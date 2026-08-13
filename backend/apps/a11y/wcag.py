"""WCAG 2.2 grounding — load the standard per tenant and hand a checker the exact rule (QA-04).

Two jobs, deliberately separated:

* **`load_wcag(tenant_id)`** copies the committed dataset into the tenant's own rows. Per
  tenant, not platform-wide, so one client's adjustments can never leak into another's and a
  tenant can carry an amended set (team decision, 2026-08-13). Idempotent — re-running
  updates in place and reports what changed, so a WCAG release is a reload, not a migration.
* **`criterion(...)` / `grounding(...)`** return the exact normative text for a criterion, to
  drop verbatim into a checker's prompt — together with the **glossary definitions** that
  criterion is written in. The AI must judge against the standard's words, not its own
  recollection of them, and a criterion whose defined terms are missing ("cognitive function
  test", "non-text content") grounds it in less than it appears to.

**Why a table and not the Knowledge Index.** The Knowledge Index cannot answer this question
at all: its BM25 tokenizer drops tokens shorter than two characters, so `retrieve("1.4.1")`
tokenizes to nothing and returns no rows — verified, not assumed. Criterion lookup is an
exact key lookup, so it is a keyed table. See the QA-04 note in TASK_BACKLOG_QA.md.

**Unknown criteria raise.** `UnknownCriterion` is an exception rather than an empty string or
a `None`, because a prompt builder can silently interpolate a falsy value and produce a
confident-looking judgment grounded in nothing. An exception cannot be interpolated.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from apps.tenancy.context import tenant_context

DATASET_PATH = Path(__file__).resolve().parent / "data" / "wcag22.json"

#: Rebuild with `python manage.py build_wcag_dataset` when W3C publishes a new version.
DEFAULT_VERSION = "2.2"


class UnknownCriterion(LookupError):
    """Asked for a criterion the loaded set does not contain."""


class WcagNotLoaded(RuntimeError):
    """The tenant has no WCAG set loaded — `load_wcag(tenant_id)` has never run for it."""


@lru_cache(maxsize=1)
def dataset() -> dict:
    """The committed dataset, read once per process. Never mutated."""
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def load_wcag(tenant_id, *, version: str = DEFAULT_VERSION, data: dict | None = None) -> dict:
    """Load (or refresh) the tenant's copy of the standard. Returns a per-table change count.

    Idempotent: rows are matched on (tenant, version, number) and updated in place, so a
    reload never duplicates and never orphans a criterion a checker might be mid-way through.
    """
    from .models import ActRule, WcagCriterion, WcagTerm

    data = data or dataset()
    if data.get("version") != version:
        raise ValueError(
            f"dataset holds WCAG {data.get('version')!r}, asked to load {version!r}")

    counts = {"criteria_created": 0, "criteria_updated": 0,
              "rules_created": 0, "rules_updated": 0,
              "terms_created": 0, "terms_updated": 0}
    with tenant_context(tenant_id):
        for crit in data["criteria"]:
            _, created = WcagCriterion.objects.update_or_create(
                tenant_id=tenant_id, version=version, number=crit["number"],
                defaults={
                    "handle": crit["handle"],
                    "level": crit["level"],
                    "slug": crit["slug"],
                    "text": crit["text"],
                    "guideline_number": crit["guideline"]["number"],
                    "guideline_handle": crit["guideline"]["handle"],
                    "principle_number": crit["principle"]["number"],
                    "principle_handle": crit["principle"]["handle"],
                    "added_in": crit["added_in"],
                    "url": crit["url"],
                    "understanding_url": crit["understanding_url"],
                    "intent": crit["intent"],
                    "techniques": crit["techniques"],
                    "terms": crit["terms"],
                    "act_rules": crit["act_rules"],
                    "no_act_rule": crit["no_act_rule"],
                },
            )
            counts["criteria_created" if created else "criteria_updated"] += 1

        for term_id, term in data["glossary"].items():
            _, created = WcagTerm.objects.update_or_create(
                tenant_id=tenant_id, version=version, term_id=term_id,
                defaults={"term": term["term"], "definition": term["definition"]},
            )
            counts["terms_created" if created else "terms_updated"] += 1

        for rule_id, rule in data["act_rules"].items():
            _, created = ActRule.objects.update_or_create(
                tenant_id=tenant_id, version=version, rule_id=rule_id,
                defaults={
                    "name": rule["name"],
                    "description": rule["description"],
                    "applicability": rule["applicability"],
                    "expectation": rule["expectation"],
                    "background": rule["background"],
                    "url": rule["url"],
                    "w3c_published": rule["w3c_published"],
                    "primary_criteria": rule["primary_criteria"],
                    "secondary_criteria": rule["secondary_criteria"],
                },
            )
            counts["rules_created" if created else "rules_updated"] += 1
    return counts


def criterion(tenant_id, number: str, *, version: str = DEFAULT_VERSION):
    """The tenant's `WcagCriterion` row for `number`. Raises rather than returning nothing."""
    from .models import WcagCriterion

    with tenant_context(tenant_id):
        row = WcagCriterion.objects.filter(
            tenant_id=tenant_id, version=version, number=number).first()
        if row is not None:
            return row
        loaded = WcagCriterion.objects.filter(tenant_id=tenant_id, version=version).exists()

    if not loaded:
        raise WcagNotLoaded(
            f"tenant {tenant_id} has no WCAG {version} set loaded; "
            f"call apps.a11y.wcag.load_wcag(tenant_id) for it"
        )
    raise UnknownCriterion(
        f"{number!r} is not a Level A/AA success criterion in WCAG {version}"
    )


def criterion_text(tenant_id, number: str, *, version: str = DEFAULT_VERSION) -> str:
    """The exact normative text of one criterion (QA-04 AC1)."""
    return criterion(tenant_id, number, version=version).text


def terms_for(tenant_id, numbers, *, version: str = DEFAULT_VERSION) -> list:
    """The glossary definitions the given criteria lean on, in a stable order.

    A criterion is written in defined terms; without them a judge reads "cognitive function
    test" as ordinary English rather than as W3C defines it.
    """
    from .models import WcagTerm

    wanted: list[str] = []
    for number in numbers:
        for term_id in criterion(tenant_id, number, version=version).terms:
            if term_id not in wanted:
                wanted.append(term_id)
    if not wanted:
        return []
    with tenant_context(tenant_id):
        found = {t.term_id: t for t in WcagTerm.objects.filter(
            tenant_id=tenant_id, version=version, term_id__in=wanted)}
    return [found[term_id] for term_id in wanted if term_id in found]


def grounding(tenant_id, numbers, *, version: str = DEFAULT_VERSION,
              include_intent: bool = True, include_terms: bool = True) -> str:
    """The grounding block a checker drops into its prompt (QA-04 AC2).

    Every requested criterion must resolve; one unknown number fails the whole block rather
    than producing a prompt that is quietly missing the rule it claims to judge against.
    """
    numbers = list(numbers)
    if not numbers:
        raise ValueError("grounding() needs at least one criterion number")

    blocks = []
    for number in numbers:
        row = criterion(tenant_id, number, version=version)
        block = [f"WCAG {version} Success Criterion {row.number} {row.handle} "
                 f"(Level {row.level})", "", row.text]
        if include_intent and row.intent:
            block += ["", "Intent:", row.intent]
        blocks.append("\n".join(block))

    if include_terms:
        defined = terms_for(tenant_id, numbers, version=version)
        if defined:
            blocks.append("\n".join(
                ["Defined terms used above (WCAG glossary):", ""]
                + [f"{t.term}: {t.definition}" for t in defined]))
    return "\n\n---\n\n".join(blocks)
