"""Accessibility judgment cache (QA-02).

An AI judgment costs time and subscription usage, so the same element must never be judged
twice. This table is that memory: one row per *input*, holding the answer that input produced
and the audit trail of what produced it.

**Why the key is a content hash.** The row is keyed on a hash of what the judge actually
looked at — the checker plus the element's markup, its screenshot pointer and its surrounding
context. So a cache hit can never be stale: if the element changes in any way that could
change the answer, the hash changes and it is judged again. That is the whole safety argument
for caching a model's opinion, and it only holds while the hash covers every input.

Deliberately NOT part of the key: the CSS selector and the route. The same markup in the same
context gets the same answer wherever it sits, and selectors churn constantly in a live
codebase — including them would mean re-judging (and re-paying for) elements nobody changed.
This is a different question from QA-12a's finding *fingerprint* (route + selector + criterion
+ checker), which exists to recognise "the same problem, still open" for a reviewer. One
identifies identical INPUT; the other identifies the same PROBLEM. They are not interchangeable.

Tenant-scoped with RLS like every platform table (#6), and project-scoped besides: a cached
verdict belongs to the project whose screens it came from.
"""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.base import TenantScopedModel


class A11yJudgmentCache(TenantScopedModel):
    """One stored AI verdict, keyed by the hash of the input that produced it."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_judgments"
    )
    checker = models.CharField(max_length=16)        # alt | semantics | color | label
    content_hash = models.CharField(max_length=64, db_index=True)

    # The judgment itself — the same shape `integrations.types.A11yJudgment` carries.
    criteria = ArrayField(models.CharField(max_length=16), default=list)
    verdict = models.CharField(max_length=16)        # pass | fail | uncertain
    confidence = models.FloatField(default=0.0)
    evidence = models.TextField(blank=True)
    suggested_fix = models.TextField(blank=True)

    # Audit (QA-02 AC): which run, engine, model and prompt version produced this verdict.
    # Stored on the row rather than looked up through the run, because a verdict outlives the
    # question "what said this?" — and answering it must not depend on the run still existing.
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    engine = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=64, blank=True)
    prompt_version = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project", "checker", "content_hash"],
                name="uniq_tenant_project_a11y_judgment",
            )
        ]

    def __str__(self) -> str:
        return f"a11y:{self.checker}:{self.verdict} ({self.content_hash[:12]})"


class WcagCriterion(TenantScopedModel):
    """One WCAG success criterion, in this tenant's copy of the standard (QA-04).

    Tenant-scoped rather than platform-wide so a client can carry an amended set without it
    leaking to anyone else (team decision, 2026-08-13). `version` lets a new WCAG release
    load alongside the old one, so a reload never pulls the ground out from under a run.
    """

    version = models.CharField(max_length=8, default="2.2")
    number = models.CharField(max_length=16)              # "1.4.1"
    handle = models.CharField(max_length=128)             # "Use of Color"
    level = models.CharField(max_length=4)                # "A" | "AA"
    slug = models.CharField(max_length=128)               # w3.org anchor
    text = models.TextField()                             # the exact normative wording

    guideline_number = models.CharField(max_length=8, blank=True)
    guideline_handle = models.CharField(max_length=128, blank=True)
    principle_number = models.CharField(max_length=4, blank=True)
    principle_handle = models.CharField(max_length=64, blank=True)

    added_in = models.CharField(max_length=8, blank=True)  # "2.0" | "2.1" | "2.2"
    url = models.URLField(blank=True)
    understanding_url = models.URLField(blank=True)
    intent = models.TextField(blank=True)                 # informative grounding
    techniques = models.JSONField(default=dict)           # sufficient/advisory/failure ids

    # The glossary terms this criterion's own wording leans on ("cognitive function test").
    # A judge given the rule but not its defined terms is grounded in less than it looks.
    terms = ArrayField(models.CharField(max_length=128), default=list)

    act_rules = ArrayField(models.CharField(max_length=16), default=list)
    # 25 of the 55 have no ACT rule because they are not machine-testable. Recorded as a
    # fact so a later phase reads "none exists" instead of guessing from an empty list.
    no_act_rule = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "version", "number"], name="uniq_tenant_wcag_criterion"
            )
        ]
        ordering = ["number"]

    def __str__(self) -> str:
        return f"WCAG {self.version} {self.number} {self.handle} ({self.level})"


class WcagTerm(TenantScopedModel):
    """One WCAG glossary definition, in this tenant's copy of the standard (QA-04).

    The criteria are written in defined terms — 3.3.8 turns on "cognitive function test",
    1.1.1 on "non-text content". Loading them means a checker can be handed the rule *and*
    W3C's definition of the words the rule hinges on.
    """

    version = models.CharField(max_length=8, default="2.2")
    term_id = models.CharField(max_length=128)            # "dfn-cognitive-function-test"
    term = models.CharField(max_length=256)               # "cognitive function test"
    definition = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "version", "term_id"], name="uniq_tenant_wcag_term"
            )
        ]
        ordering = ["term"]

    def __str__(self) -> str:
        return f"WCAG {self.version} term: {self.term}"


class ActRule(TenantScopedModel):
    """One ACT rule and the criteria it maps to (QA-04).

    `w3c_published` separates the rules W3C publishes from the community group's drafts —
    only the published ones are mapped onto criteria, so a draft can never be cited as
    evidence of conformance.
    """

    version = models.CharField(max_length=8, default="2.2")
    rule_id = models.CharField(max_length=16)             # "674b10"
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    applicability = models.TextField(blank=True)
    expectation = models.TextField(blank=True)
    background = models.TextField(blank=True)
    url = models.URLField(blank=True)
    w3c_published = models.BooleanField(default=False)

    # A *primary* mapping means failing the rule fails the criterion. A *secondary* mapping
    # means the ACT authors state the rule is stricter or looser than the criterion, so it
    # must never stand in as a conformance test for it.
    primary_criteria = ArrayField(models.CharField(max_length=16), default=list)
    secondary_criteria = ArrayField(models.CharField(max_length=16), default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "version", "rule_id"], name="uniq_tenant_act_rule"
            )
        ]
        ordering = ["rule_id"]

    def __str__(self) -> str:
        return f"ACT {self.rule_id} {self.name}"
