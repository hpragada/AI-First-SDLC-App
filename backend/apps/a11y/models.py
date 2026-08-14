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

from apps.base import TenantScopedModel, UUIDModel


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


class A11yCandidateBundle(TenantScopedModel):
    """One captured element from a real screen, and what the AI pass should ask about it (QA-11b).

    The app under test runs on the developer's own machine at a localhost address the server
    cannot reach, so a rendered page exists for a few minutes and then is gone. This table is
    what survives that window: the facts about one element, a pointer to a picture of it, and
    whatever the rule scanner already said about it.

    **Selection happened before this row existed.** The capture reports everything it saw; the
    platform runs `checkers.rules` on ingest and stores only elements at least one checker
    applies to, with `checkers` naming which. An element nothing applies to is counted and
    dropped — see `skipped` on the ingest result — so "why was this never judged?" stays an
    answerable question (`rules.explain`) rather than a silence.

    **`screenshot_ref` is a pointer, never an image.** The crop lives in the object store
    (#1/#3). Blank means no picture could be produced, and `uncapturable_reason` says why —
    that is a fact the judge is told, not a row that is quietly dropped, because an element
    with no image still needs a person to look at it.

    Keyed for re-ingest by (tenant, project, run_key, route, selector): posting the same screen
    twice updates its elements rather than doubling them. `run_key` is a string rather than the
    `run` FK because a CI post has no run — and a NULL in a unique constraint compares unequal
    to itself in Postgres, so two CI posts of the same page would both be stored.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_candidates"
    )
    # The run that captured this, when there was one. CI posts carry no run.
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    run_key = models.CharField(max_length=128, blank=True, db_index=True)

    route = models.CharField(max_length=512)          # "/checkout"
    url = models.URLField(blank=True)                 # the companion-local URL it was seen at
    # Where this element sat in the capture — page order. Stored because a primary key is a
    # UUID and tells you nothing about sequence, and the batch a judgment run is given has to
    # come out the same way twice: a run that cannot be reproduced cannot be compared against
    # the golden set (QA-09).
    position = models.PositiveIntegerField(default=0)
    # The whole screen's identity at capture time (QA-07, `capture.fingerprint`). A later run
    # whose capture of this route hashes the same is carried forward from these rows instead of
    # being cropped and stored again — the screen's coverage is kept, only the work is skipped.
    screen_hash = models.CharField(max_length=64, blank=True, db_index=True)
    # Bounded, not a TextField: it sits in a unique index, and Postgres refuses an index entry
    # over ~2.7 KB. Ingest truncates rather than failing the whole screen on one long selector.
    selector = models.CharField(max_length=512)       # unique within a route

    # Which of the four checks apply to this element, in `rules.CHECKERS` order.
    checkers = ArrayField(models.CharField(max_length=16), default=list)

    # The captured element exactly as `rules.CapturedElement.from_dict` reads it. Stored whole
    # rather than as columns: the capture format will grow (an accessibility-tree node, more
    # styles), and a growing format must not be a migration every time.
    element = models.JSONField(default=dict)

    # What the rule scanner already said about this element, if anything. Carried so a later
    # merge can put the rule finding and the AI finding side by side without re-running axe.
    axe = models.JSONField(default=dict, blank=True)

    screenshot_ref = models.CharField(max_length=512, blank=True)
    uncapturable_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project", "run_key", "route", "selector"],
                name="uniq_tenant_project_a11y_candidate",
            )
        ]
        ordering = ["route", "position", "selector"]

    def __str__(self) -> str:
        return f"a11y-candidate {self.route} {self.selector[:40]} ({','.join(self.checkers)})"


class WcagCriterion(UUIDModel):
    """One WCAG success criterion — **one copy for the whole platform** (QA-04).

    **Why this table has no `tenant_id`.** It is the only kind of table that may not: it
    holds published W3C text, identical for everyone, that no tenant may amend (team
    decision, 2026-08-13, superseding the earlier per-tenant plan). There is no tenant data
    in it to leak, so non-negotiable #6 has nothing to protect here — see the carve-out
    recorded in migration `0006_wcag_platform_wide`. Storing it per tenant meant 250
    duplicate rows each: 2.5 million rows and ~5.6 GB of identical public text at 10,000
    tenants, to support amendments the team has decided will never exist.

    The app database role has **SELECT only** on this table, so universality is enforced by
    the database rather than by everyone remembering the rule.

    `version` lets a new WCAG release load alongside the old one, so a reload never pulls the
    ground out from under a run in flight.
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
                fields=["version", "number"], name="uniq_wcag_criterion"
            )
        ]
        ordering = ["number"]

    def __str__(self) -> str:
        return f"WCAG {self.version} {self.number} {self.handle} ({self.level})"


class WcagTerm(UUIDModel):
    """One WCAG glossary definition — **one copy for the whole platform** (QA-04).

    The criteria are written in defined terms — 3.3.8 turns on "cognitive function test",
    1.1.1 on "non-text content". Loading them means a checker can be handed the rule *and*
    W3C's definition of the words the rule hinges on.

    Platform-wide and SELECT-only to the app role, for the reasons on `WcagCriterion`.
    """

    version = models.CharField(max_length=8, default="2.2")
    term_id = models.CharField(max_length=128)            # "dfn-cognitive-function-test"
    term = models.CharField(max_length=256)               # "cognitive function test"
    definition = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "term_id"], name="uniq_wcag_term"
            )
        ]
        ordering = ["term"]

    def __str__(self) -> str:
        return f"WCAG {self.version} term: {self.term}"


class ActRule(UUIDModel):
    """One ACT rule and the criteria it maps to — **one copy for the whole platform** (QA-04).

    Platform-wide and SELECT-only to the app role, for the reasons on `WcagCriterion`.

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
                fields=["version", "rule_id"], name="uniq_act_rule"
            )
        ]
        ordering = ["rule_id"]

    def __str__(self) -> str:
        return f"ACT {self.rule_id} {self.name}"


class Owner(models.TextChoices):
    """Who makes the decisive determination for a criterion (Addendum A §2.2)."""

    RULE = "rule", "Rule engine"      # a deterministic engine decides the typical case
    AI = "ai", "AI"                   # the decisive check is semantic or visual
    HUMAN = "human", "Human"          # judgment, assistive tech, media or process knowledge


class Tier(models.TextChoices):
    """When — if ever — a criterion gets an automated or AI check (Addendum A §3).

    `HUMAN` is not the same statement as `Owner.HUMAN`: 30 criteria are human-*owned*, but
    only these 15 stay that way once Phase 2 is built.
    """

    IN_POC = "in_poc", "In POC"       # shipped in the Scope-A POC
    PHASE_2 = "phase_2", "Phase 2"    # AI-extendable later (incl. agentic)
    HUMAN = "human", "Human"          # human-led with human sign-off, always


class CriterionOwnership(UUIDModel):
    """Who checks one WCAG criterion, and when — **one copy for the whole platform** (QA-05).

    The routing table for an accessibility run: given a criterion, it says whether the rule
    engine, the AI or a person decides it, and whether a check for it exists in the POC, in
    Phase 2, or never.

    **Why this is separate from `WcagCriterion`.** That table is the standard — published
    W3C text, quoted verbatim, and true regardless of what we build. This one is Edvensoft's
    engineering judgment about our own coverage, and it changes when our capabilities change
    (2.1.1 Keyboard moves the day agentic interaction testing lands). Keeping our opinion out
    of the standard's table means a WCAG reload never touches our routing, and a change of
    plan never edits the standard.

    **Why no `tenant_id`.** The same narrow carve-out as `WcagCriterion`, recorded in
    migration `0006_wcag_platform_wide`: no tenant data, derived wholly from a committed
    file, never tenant-writable. The app role has SELECT only, so a tenant cannot decide a
    criterion needs less checking than it does.

    Keyed on (version, number) rather than a foreign key to `WcagCriterion`. A foreign key
    would only prevent an ownership row without a criterion; the dangerous direction is the
    other one — a criterion with no ownership row, which nothing would ever route — and no
    key can prevent that. `ownership.verify_complete()` checks both directions instead.
    """

    version = models.CharField(max_length=8, default="2.2")
    number = models.CharField(max_length=16)                    # "1.4.1"
    owner = models.CharField(max_length=8, choices=Owner.choices)
    tier = models.CharField(max_length=8, choices=Tier.choices)

    # The report's own one-line reason, kept so a coverage report can say *why* a criterion
    # needs a person rather than only that it does.
    rationale = models.TextField(blank=True)

    # What another engine contributes where it is not the decider: `[{"engine", "note"}]`.
    # Most criteria are hybrids — 3.3.2 is rule-owned but "AI judges adequacy of
    # instructions", and 1.2.2 is human-owned but a rule "can flag a missing caption track".
    # Without this, routing sees only the primary owner and those contributions exist purely
    # as English prose in `rationale`, where nothing can act on them.
    secondary_checks = models.JSONField(default=list, blank=True)

    # Addendum B §2.2: 6 of the 15 human-led criteria still get partial machine flagging
    # (a missing caption track, a flash rate). It never means the criterion can be decided
    # automatically — it means a reviewer starts from a hint rather than a blank page. False
    # for every criterion that is not human-led, where the question does not arise.
    partial_auto_flag = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["version", "number"], name="uniq_criterion_ownership"
            )
        ]
        ordering = ["number"]

    def __str__(self) -> str:
        return f"WCAG {self.version} {self.number}: {self.owner} / {self.tier}"
