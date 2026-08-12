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
