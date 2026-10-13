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
    checker = models.CharField(max_length=16)        # one of `checkers.rules.CHECKERS`
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

    # Which of the AI checks apply to this element, in `rules.CHECKERS` order.
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


class A11yScreenScan(TenantScopedModel):
    """What the rule scanner said about one whole screen (QA-12).

    The other half of the merged report. `A11yCandidateBundle.axe` carries the scanner's verdict
    on an element the AI is going to be asked about, which is what makes the two comparable —
    but a row only exists for an element one of the AI checks applies to. A scanner failure on
    anything else has no bundle, so without this table the merged report's rule half would
    quietly cover a subset of the scan and read as the whole of it.

    Stored whole rather than one row per violation. The scan is a document the scanner produced
    about a page at a moment; splitting it into rows would invent an identity for each violation
    that the scanner never gave it, and the thing that *does* need a stable identity — a finding
    a reviewer tracks across runs — is QA-12a's ledger, keyed on a fingerprint, not on this.

    Keyed like `A11yCandidateBundle` (tenant, project, run_key, route) and for the same reasons:
    re-posting a screen updates its scan, and `run_key` is a string because a CI post has no run
    and a NULL compares unequal to itself in a Postgres unique index.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_screen_scans"
    )
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    run_key = models.CharField(max_length=128, blank=True, db_index=True)

    route = models.CharField(max_length=512)
    url = models.URLField(blank=True)
    screen_hash = models.CharField(max_length=64, blank=True, db_index=True)

    # [{rule, impact, criteria[], help, nodes[]}] exactly as `capture._violation` normalises it.
    violations = models.JSONField(default=list, blank=True)
    # Why the rule scanner did not run on this screen, in the capture's own words — blank when
    # it did (QA-16). Until QA-16 a capture only existed for a dedicated accessibility test
    # case, so "did a scan run?" was answered by whether that case executed. Now every screen
    # the suite visits is captured, including on a stack with no scanner wired, and an empty
    # `violations` list would otherwise be indistinguishable from a clean page — the exact
    # "incomplete check reading as a clean one" D-A11Y-3 exists to prevent. Mirrors
    # `screenshot_error`: an absence with a stated reason beats an absence.
    scan_error = models.TextField(blank=True, default="")
    # Why the page never opened — an auth wall, a 404, a timeout (QA-17). Blank when it did.
    #
    # A THIRD state, not a variant of the two above. `violations=[]` with both blank is a
    # clean page; `scan_error` set is a page that was seen but not measured; this is a page
    # that was never seen at all. A baseline audit of an app that never went through our
    # design phase hits this on real routes, and the row exists so the route is still part of
    # the run's coverage with a stated reason rather than being absent from it.
    #
    # Load-bearing beyond the report: `scanner.rule_findings_for` leaves these routes OUT of
    # `RuleScan.routes`, because that list is what `findings.record_run_findings` reads as
    # "where we looked". A route counted as looked-at would resolve every open finding on it
    # by absence — closing a screen's accessibility defects because nobody could reach it.
    load_error = models.TextField(blank=True, default="")

    #: The other three channels axe returns, kept from QA-24 onward (`passes` and
    #: `inapplicable` node-less, `incomplete` with its nodes).
    #:
    #: **This is what makes a conformance statement possible at all.** Until QA-24 only
    #: `violations` was stored, so a criterion with nothing against it could equally be one the
    #: scanner checked and found clean, one the scanner has no rule for, or one where nothing on
    #: the page was applicable. Three different facts, one silence — and a VPAT is made almost
    #: entirely of the positive ones.
    #:
    #: `incomplete` is axe saying *I looked and cannot decide, a human must*. Discarding it was
    #: the same silence this build refuses everywhere else, sitting inside our own scanner.
    #:
    #: An empty list on an old capture means **no positive evidence**, never "nothing passed" —
    #: see `capture._rule_list`.
    axe_passes = models.JSONField(default=list, blank=True)
    axe_inapplicable = models.JSONField(default=list, blank=True)
    axe_incomplete = models.JSONField(default=list, blank=True)

    #: Which scanner produced all of the above, e.g. "axe-core 4.13.0" (QA-24, D-A11Y-96).
    #: axe is imported from the CLIENT'S own project, so this differs per tenant and per run.
    #: Recorded on the export and never shown to the tenant — without it a signed statement
    #: can never be traced back to what produced it.
    scanner_version = models.CharField(max_length=64, blank=True, default="")

    #: The page-level measurements the rule scanner has no rule for (QA-25):
    #: `{"reflow": {...}, "non_text_contrast": {...}}` as `capture._page_measurements`
    #: normalises them.
    #:
    #: **Raw readings, never verdicts.** How wide the content was at a 320px window, and what
    #: colour every control's edge is drawn in — with nothing blended, nothing compared and no
    #: threshold applied. `page_rules` is the only place those become a ruling, which is what
    #: lets a defect raised months ago be re-checked against the numbers that raised it: a
    #: stored verdict could only ever be re-read, while a stored measurement can be re-argued.
    #:
    #: **`{}` means not measured, and it must never be read as measured-and-clean.** Every
    #: capture taken before this field existed carries `{}`, as does one from a companion too
    #: old to run the passes — and `page_rules` produces nothing at all from it, so those
    #: screens report 1.4.10 and 1.4.11 as *not evaluated* rather than as pages that were fine.
    page_measurements = models.JSONField(default=dict, blank=True)

    #: Object-store key of the WHOLE page as it looked, never the image (#1/#3).
    #:
    #: The picture was always taken and always stored — what was missing until QA-23 is
    #: that its key was computed inline as an argument and then dropped on the floor, so
    #: the platform held every element's rectangle and had thrown away the thing those
    #: rectangles are coordinates *into*. The reviewer console needs both halves: an
    #: element crop shows a button with no page around it, and most of what this reviewer
    #: decides ("is this image decorative, given what sits next to it?") is a question
    #: about the surroundings.
    #:
    #: Blank is a real answer and is kept apart from "not stored yet": a page whose
    #: screenshot could not be taken or could not be written has no key, and the console
    #: says so rather than showing an empty frame.
    page_image_ref = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project", "run_key", "route"],
                name="uniq_tenant_project_a11y_screen_scan",
            )
        ]
        ordering = ["route"]

    def __str__(self) -> str:
        return f"a11y-scan {self.route} ({len(self.violations or [])} violation(s))"


class A11yCriterionCoverage(TenantScopedModel):
    """Was this criterion looked at on this page, by what, and what came back? (QA-24.)

    **This is not the findings ledger, and the two must never be merged.** `A11yFinding` answers
    *"what is wrong with this element?"* — one row per problem, keyed on a fingerprint, worked
    through by a person and closed. This answers a different question at a different grain:
    *"was 1.4.3 evaluated on /checkout, by which engine, and what was the result?"* One is the
    fix list; this is the coverage map a conformance statement is compiled from.

    **It exists because the platform recorded only what was WRONG.** All three engines threw
    their positive result away, in three separate places: the scanner returned `violations` and
    dropped axe's `passes`, `inapplicable` and `incomplete`; the ledger's `RECORDED_OUTCOMES`
    dropped every AI verdict of "this is fine"; and the journey path returned early on anything
    that was not a failure or a review. So a criterion with nothing against it was
    indistinguishable from one nothing had ever looked at — and a VPAT is made almost entirely
    of positive claims. Fixing only the scanner would have covered 14 of the 55 criteria and
    left the other two engines just as silent.

    **Per route, deliberately.** "Supports" is never a fact about a product, it is a fact about
    the pages that were checked. A criterion clean on nine routes and failing on the tenth is
    "partially supports", and a table that averaged that away would be worse than no table.

    **`NOT_APPLICABLE` is a real answer and is not a pass.** It means the rule ran and there was
    nothing on the page for it to apply to — no images, so nothing to have bad alt text. Rolling
    that into "supports" would claim conformance for content that does not exist.
    """

    class Engine(models.TextChoices):
        RULE = "rule", "Rule scanner"
        AI = "AI", "AI judge"
        AGENTIC = "agentic", "Agentic testing"
        HUMAN = "human", "Human"

    class Outcome(models.TextChoices):
        FAILED = "failed", "Failed"
        PASSED = "passed", "Checked, nothing wrong"
        NOT_APPLICABLE = "not_applicable", "Rule ran; nothing on the page it applies to"
        NEEDS_HUMAN = "needs_human", "Looked at it and cannot decide"
        #: Selected for a check that never ran — the pass stopped at its cap before reaching
        #: this element, or ended without reporting on it. **Not a judgement at all**, and
        #: deliberately not folded into `NEEDS_HUMAN`: that one says a check looked and could
        #: not decide, which is a real result belonging to a person. This one says the platform
        #: has not finished, and the thing to do about it is finish — see `coverage._RANK`.
        NOT_CHECKED = "not_checked", "Selected for a check that has not run yet"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_coverage"
    )
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The capture partition, exactly as `A11yScreenScan` uses it — a baseline audit has a key
    #: and no run (QA-17), so this is the field every reader groups by.
    run_key = models.CharField(max_length=128, blank=True, db_index=True)

    route = models.CharField(max_length=512)
    criterion = models.CharField(max_length=16)
    engine = models.CharField(max_length=8, choices=Engine.choices)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)

    #: What produced this, in the engine's own words — an axe rule id, a checker name. Kept so
    #: a reader can see WHY a criterion is claimed covered rather than taking the row on trust.
    detail = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project", "run_key", "route", "criterion", "engine"],
                name="uniq_tenant_project_a11y_coverage",
            )
        ]
        ordering = ["criterion", "route", "engine"]
        indexes = [models.Index(fields=["tenant", "project", "criterion"])]

    def __str__(self) -> str:
        return f"a11y-coverage {self.criterion} {self.route} {self.engine}={self.outcome}"


class A11yFinding(TenantScopedModel):
    """One accessibility problem, with an identity that outlives the run that found it (QA-12a).

    Until this table, a finding was a line in a document the platform re-rendered from scratch
    every time it was asked to — a snapshot, not a record. Nothing could say "this is the same
    broken button we saw last week", so nothing could open a bug that closes itself, avoid
    raising the same bug twice, or hand a person a queue to work through.

    **The `fingerprint` is the whole point.** It hashes *(route + normalised selector + primary
    criterion + checker)*, and it is what turns three otherwise-unimplementable requirements
    into one-liners: the same problem on two runs is one row with a new `last_seen_run`; a
    problem that disappears and returns reuses the original row; two different elements failing
    one criterion stay two findings.

    **It is NOT `A11yJudgmentCache.content_hash`, and the two must never be merged.** That key
    identifies identical *input* — the markup, the picture, the surrounding text — so that a
    model is not asked the same question twice. This one identifies the same *problem*, so a
    person is not shown it twice. An element whose markup is edited gets a new content hash and
    keeps this fingerprint, which is exactly right: it is still the same button on the same
    screen breaching the same criterion.

    **Severity comes from the standard, not from prose.** `WcagCriterion.level` is loaded from
    W3C, so a Level A breach is Critical and a Level AA breach is High without anything having
    to restate the mapping. The scanner's own `impact` is kept beside it and never conflated —
    they measure different things, and only severity decides whether a defect opens (QA-14).

    **`status` is resolved by absence, but only where we actually looked.** A run reports on the
    screens it captured; a finding on a screen this run never visited is untouched. The same
    discipline `import_test_results` applies when it closes defects only for tests that were
    *reported passing*, never for tests that simply did not run.

    **This is state, not content** (#1/#3): a pointer, a provenance record and a verdict. The
    screenshot body stays in the object store.
    """

    class Source(models.TextChoices):
        RULE = "rule", "Rule scanner"
        AI = "AI", "AI judge"
        HUMAN = "human", "Human"
        AGENTIC = "agentic", "Agentic testing"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    class Adjudication(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed by a reviewer"
        REJECTED = "rejected", "Rejected by a reviewer"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_findings"
    )
    fingerprint = models.CharField(max_length=64, db_index=True)

    route = models.CharField(max_length=512)
    selector = models.CharField(max_length=512)
    # False when the selector is the platform's own positional fallback, so this row's identity
    # is "where it sat on the page" and a reorder will record the problem again. Flagged rather
    # than dropped: a finding with a weak handle beats no finding, and a reviewer seeing an
    # apparent duplicate can tell why.
    stable = models.BooleanField(default=True)

    criterion = models.CharField(max_length=16)                       # the primary one
    criteria = ArrayField(models.CharField(max_length=16), default=list)
    wcag_level = models.CharField(max_length=4, blank=True)           # "A" | "AA", "" if unknown
    checker = models.CharField(max_length=16, blank=True)             # "" for a scanner finding

    source = models.CharField(max_length=8, choices=Source.choices)
    # What the AI said (`pass`/`fail`/`uncertain`) and what the platform decided about it
    # (`failure`/`needs_review`) — deliberately two fields. A `pass` verdict on an element the
    # scanner failed comes out of triage as a failure, and a report that stored only one of
    # these could not show a reviewer why.
    verdict = models.CharField(max_length=16, blank=True)
    outcome = models.CharField(max_length=16)
    confidence = models.FloatField(null=True, blank=True)             # None for a measurement
    severity = models.CharField(max_length=16)                        # critical|high|medium|low
    impact = models.CharField(max_length=16, blank=True)              # the scanner's own word

    evidence = models.TextField(blank=True)
    suggested_fix = models.TextField(blank=True)
    screenshot_ref = models.CharField(max_length=512, blank=True)     # pointer, never an image
    rule_id = models.CharField(max_length=128, blank=True)

    engine = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=64, blank=True)
    prompt_version = models.CharField(max_length=64, blank=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    adjudication = models.CharField(
        max_length=16, choices=Adjudication.choices, default=Adjudication.PENDING
    )
    adjudicated_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    adjudication_note = models.TextField(blank=True)
    adjudicated_at = models.DateTimeField(null=True, blank=True)

    #: The hash of what the judge actually looked at — the markup, the surrounding text
    #: and the pointer to the picture (`dispatch.content_hash`). Stored on the finding so
    #: a later run can ask one question: **is this still the same element?**
    content_hash = models.CharField(max_length=64, blank=True, default="")
    #: What `content_hash` was at the moment a person ruled on this. The two together are
    #: how a human decision survives the next run (QA-23, team decision B1).
    #:
    #: Without this, the console silently undoes itself: `record_run_findings` rewrites
    #: `outcome`/`verdict`/`confidence` from every fresh report, so a reviewer confirms a
    #: real problem, a defect opens, the next run re-judges, the AI is still unsure, the
    #: outcome falls back to `needs_review`, and the defect loop closes the very ticket the
    #: reviewer raised. Equal hashes mean nothing the judge can see has changed, so the
    #: answer is still good and the human's ruling stands. A different hash means it is a
    #: different element now — the ruling is cleared and it returns to the queue, which is
    #: the honest outcome rather than a stale "this is fine" sitting over edited markup.
    adjudicated_content_hash = models.CharField(max_length=64, blank=True, default="")

    #: Who is reviewing this right now, and since when (QA-23, team decision C1).
    #:
    #: Two QA Leads opening one item is not hypothetical, and without a lock the second
    #: decision silently overwrites the first — leaving a defect open for a finding the
    #: record says was rejected, with neither reviewer aware. The claim is held for
    #: `review.LOCK_MINUTES` and renewed while the reviewer is on the item; it releases
    #: itself when they stop, so nobody has to remember to hand an item back. An expired
    #: lock is not cleared by a background job — it is simply not honoured, so there is no
    #: sweeper to fail silently.
    review_locked_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    review_locked_at = models.DateTimeField(null=True, blank=True)

    first_seen_run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_seen_run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project", "fingerprint"],
                name="uniq_tenant_project_a11y_finding",
            )
        ]
        ordering = ["route", "criterion", "selector"]

    def __str__(self) -> str:
        return f"a11y-finding {self.criterion} {self.route} {self.selector[:40]} ({self.status})"


class A11yConformanceStatement(TenantScopedModel):
    """A WCAG conformance statement (a VPAT) and the signature that makes it mean anything.

    **The platform never claims compliance.** It compiles the evidence, drafts the wording, and
    stops. A conformance statement carries someone's professional judgement, and the platform
    has none to give — so this row exists to record *whose* judgement it is, exactly what they
    put their name to, and what the evidence looked like at that moment.

    **State here, content in the object store** (#1/#3). The wording lives in the `conformance`
    artifact's body like every other document; this row holds the pointer, the reviewer's
    per-criterion levels, and the signature.

    **The signature IS the gate (team decision B1, 2026-08-18).** The ordinary `Approval` model
    cannot carry this: it requires a `Run` (non-nullable) and `gates.services.decide` signals
    that run's Temporal workflow — and a statement compiled from the ledger across many runs has
    neither. Rather than manufacture a run nobody executed or make a core control-plane table
    nullable for one document, the signature does the job a gate does: a role-checked person,
    named, timestamped, bound to the exact wording, and audit-logged. It flips the artifact to
    `approved`, which is the state the existing publish endpoint already demands — so nothing
    reaches a system of record without a named human approval (#5), which is what that rule is
    actually for.

    **A signature is bound to wording AND to evidence, and the two expire differently
    (team decision C1).** Editing the wording clears the signature outright: a signature on text
    nobody signed is worse than no signature. New evidence does not clear it — the reviewer did
    sign those words — but it marks the statement **stale** and refuses export until it is
    re-signed. A signed statement quietly describing last month's findings is the worst thing
    this document can become, and it is the failure mode nobody would notice.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_conformance"
    )
    #: The `conformance` artifact holding the wording. The document is an artifact like any
    #: other so it inherits versioning, the preview read-through and the publish flow.
    artifact = models.ForeignKey(
        "registry.Artifact", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )

    #: What the statement covers, in the reviewer's words — "Payment Gateway v2, checkout and
    #: expense journeys". Never inferred: a scope the platform guessed is a scope nobody agreed.
    scope = models.TextField(blank=True)
    #: The statement's prose. Drafted by the platform, edited freely by the reviewer.
    body = models.TextField(blank=True)

    #: The reviewer's own conformance level per criterion, where they set one:
    #: `{"1.4.3": {"level": "partially_supports", "note": "..."}}`. Absent means they accepted
    #: what the evidence suggests — which is recorded as such at signing rather than hidden.
    verdicts = models.JSONField(default=dict, blank=True)

    signed_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The name as it appears on the statement. Stored rather than read from the user row,
    #: because the document must keep saying what it said even if an account is renamed.
    signed_name = models.CharField(max_length=255, blank=True)
    signed_role = models.CharField(max_length=32, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    #: sha256 of the exact wording signed, and of the evidence behind it. The pair is what makes
    #: "this signature no longer describes the document" a fact rather than an opinion.
    signed_body_hash = models.CharField(max_length=64, blank=True, default="")
    signed_evidence_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project"],
                name="uniq_tenant_project_a11y_conformance",
            )
        ]

    def __str__(self) -> str:
        state = "signed" if self.signed_at else "unsigned"
        return f"a11y-conformance {self.project_id} ({state})"


class A11yRoute(TenantScopedModel):
    """One page of an app that a baseline audit should look at (QA-17).

    Every accessibility check so far has been a *side effect of building something*: a story
    ran, its test suite drove some screens, and whatever it happened to visit got captured.
    An app that was imported rather than built here has no story and no suite, so nothing
    anywhere says which pages exist. This table is that list.

    **Why a table and not a key on the project profile.** The profile's `a11y` block is gate
    *policy*, validated against a deliberately strict allow-list so a misspelled setting is
    refused rather than silently ignored (`policy.validate_policy`). A route list is audit
    *input* — it grows, gets disabled a route at a time, and will be written by onboarding
    (OP-06) rather than by a person editing settings. Mixing the two would loosen the
    validator that exists to catch typos in the thing that decides what blocks a release.

    `source` records who put a route here, so a list onboarding discovered stays
    distinguishable from one a person typed. `enabled` is how a route leaves the audit
    without leaving the record — a page behind a login the audit cannot pass is a fact worth
    keeping, and deleting the row would invite someone to add it again next month.
    """

    class Source(models.TextChoices):
        MANUAL = "manual", "Entered by a person"
        ONBOARDING = "onboarding", "Discovered during onboarding"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_routes"
    )
    # The path only — "/checkout". NOT a full URL: where the app is running is a property of
    # the machine auditing it (a localhost port today, a staging host tomorrow) and changes
    # between runs, while the route is the app's own and does not.
    path = models.CharField(max_length=512)
    label = models.CharField(max_length=200, blank=True)      # "Checkout — payment step"
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    enabled = models.BooleanField(default=True)
    notes = models.TextField(blank=True)                      # "needs a signed-in session"
    # A concrete address for a route that is a PATTERN — `/events/:id` is how a developer writes
    # "any event", and no browser can open it. Without this the page is asked for on every audit
    # and reported as never opened on every audit, forever: honest, and permanently useless.
    # With it the audit visits `/events/482` and the finding is still recorded against the
    # pattern, so one row keeps meaning one page of the application rather than one visit to it.
    example_path = models.CharField(max_length=512, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "project", "path"], name="uniq_tenant_project_a11y_route",
            )
        ]
        ordering = ["path"]

    @property
    def visit_path(self) -> str:
        """What a browser is actually pointed at — the example where there is one."""
        return (self.example_path or "").strip() or self.path

    def __str__(self) -> str:
        return f"a11y-route {self.path}{'' if self.enabled else ' (disabled)'}"


class A11yBaselineAudit(TenantScopedModel):
    """One pass over a project's registered routes, start to finish (QA-17).

    **Why this is not a `Run`.** A `Run` in this platform is an agent run — a Temporal
    workflow with an `AgentSpec` behind it (#8). Visiting a list of URLs and writing down
    what is on each page needs no intelligence and no engine, so manufacturing a `Run` for it
    would put a row in the runs table that no agent ever executed, and every screen in the
    product that lists runs would show it. `CodeIntelJob` made the same call for the same
    reason. The judging that follows *is* a real run, dispatched the ordinary way.

    **Its id is the capture's `run_key`.** Candidates, screen scans and the merged report are
    all partitioned by that string, so an audit gets its own bucket: re-running it does not
    collide with the last one, and neither collides with the project-wide bucket a CI post
    lands in. Everything downstream reads the key as a string and does not care that no `Run`
    has that id — the two places that looked one up (`findings.record_run_findings`,
    `report.publish_report`) resolve it and carry on without one.

    **Two ways in, one set of states.** Opened from the app the audit is `pending` until a
    machine claims it; started from the companion's own command line it goes straight to
    `capturing`, because the machine that opened it is already standing there. Neither path
    knows the other exists: the status simply says what is true, and `capturing` is reached the
    moment a screen arrives whoever sent it (`ingest_audit_capture`). There is no mode flag,
    because a mode flag would be a second thing to keep in step with reality.

    **`routes` is frozen at the start.** The audit has to be able to say "this route was
    asked for and never came back", which cannot be answered from the captures alone — that
    is precisely the silence it would be reading. Re-reading the registry at the end would
    also mean a route added mid-audit looked like one that failed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"            # opened from the app; no machine has it yet
        CLAIMED = "claimed", "Claimed"            # a companion took it and is about to visit
        CAPTURING = "capturing", "Capturing"      # waiting for screens from the companion
        JUDGING = "judging", "Judging"            # captures in, AI pass dispatched
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_audits"
    )
    # Where the app was reachable FROM THE MACHINE THAT AUDITED IT. Recorded as provenance,
    # never as something the platform will connect to: the server cannot reach a developer's
    # localhost, and the whole capture design exists because of that (R2).
    base_url = models.CharField(max_length=512, blank=True)
    #: The paths this audit was asked to visit, frozen at start: ["/", "/login", …].
    routes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CAPTURING)
    started_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # The companion this audit was routed to. NULL is a broadcast any active companion for the
    # project may take, and it is bound to the machine that takes it — the same self-healing
    # `CodeIntelJob` has, so an audit opened before a companion is up still runs when one
    # appears. `claimed_at` is what makes a dead companion's claim recoverable rather than a
    # dead end: past the lease, the audit is claimable again.
    enrollment = models.ForeignKey(
        "runs.RunnerEnrollment", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    #: What happened, in numbers a person can check — see `baseline.finish_baseline_audit`.
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"a11y-audit {self.project_id} ({self.status})"


class A11yJourneyRun(TenantScopedModel):
    """One keyboard-and-interaction pass over one critical journey (QA-20).

    **Why a journey needs a row of its own at all.** Every other accessibility check is about a
    place — a screen, an element. This one is about a *path*, and a path has something no screen
    has: steps that may never be reached. If the agent gets three steps into a five-step journey
    and the login breaks, the two remaining steps were not clean and were not broken. They were
    never tested, and nothing in the element ledger can express that.

    **`steps` is frozen at the start**, the same rule and the same reason as `A11yBaselineAudit.
    routes`: the honest question at the end is "which steps never reported?", and that cannot be
    answered from what *did* report — that is the silence itself. Re-reading the test case
    afterwards would also mean a step edited mid-run looked like a step that failed.

    `run` is nullable and `run_key` carries the identity, mirroring the baseline audit: the pass
    is normally a real `Run`, but nothing downstream may *require* one.
    """

    class Status(models.TextChoices):
        WALKING = "walking", "Walking"      # dispatched; the agent is operating the app
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_journey_runs"
    )
    run = models.ForeignKey(
        "runs.Run", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The test case this journey came from — "TC-031". Provenance, not a foreign key: the
    #: journey is defined by a document, and that document's identity is its TC-ID.
    test_ref = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=512, blank=True)
    #: Pointer to the `test_case` artifact the steps were read from (#1/#3 — never the body).
    artifact_id = models.CharField(max_length=64, blank=True)
    #: Where the application answered for this walk — "http://127.0.0.1:5173" (G6a).
    #:
    #: Stored rather than resolved at read time for the same reason `steps` is frozen: a journey
    #: result is a claim about *the thing that was walked*, and the address a project resolves to
    #: moves (a repository's Preview URL is edited, a port changes). A result whose address was
    #: looked up afterwards would quietly re-attribute itself to whatever is running now.
    #:
    #: It is also what scopes the browser. The companion passes it to the browser as the only
    #: origin that may be opened, so a blank one is not a default — it is a run that must not
    #: start, and `start_journey_check` refuses before it gets this far.
    base_url = models.CharField(max_length=512, blank=True)
    #: The steps as parsed at start: [{"number": 1, "text": "...", "route": "/login"}, …].
    steps = models.JSONField(default=list, blank=True)
    preconditions = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.WALKING)
    started_by = models.ForeignKey(
        "tenancy.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: What happened, in numbers a person can check — asked / walked / blocked / never reported.
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "project", "test_ref"])]

    def __str__(self) -> str:
        return f"a11y-journey {self.test_ref or self.title} ({self.status})"


class A11yJourneyStepResult(TenantScopedModel):
    """What became of one step of one journey pass (QA-20) — the sixth silence, stored.

    Three outcomes, and the difference between them is the whole point of this table:

      * **walked** — the agent got here and operated it. Judgments for this step mean something.
      * **blocked** — the agent got here and could not go on, and said why. Everything after it
        is untested, and the report must say so rather than let the journey read as covered.
      * **not_reached** — the agent never mentioned this step at all. The platform's own
        reconciliation writes this by subtracting what was reported from the frozen list; it is
        never something the agent claims, because an agent that stopped early cannot be relied
        on to report that it stopped.

    A blocked or unreached step produces **no judgment**, deliberately. "I never got there" is
    not a verdict, and giving it one — pass *or* fail — is how an untested journey comes back
    looking either clean or broken when the truth is neither.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="a11y_journey_steps"
    )
    journey_run = models.ForeignKey(
        A11yJourneyRun, on_delete=models.CASCADE, related_name="step_results"
    )
    number = models.PositiveIntegerField()
    text = models.TextField(blank=True)
    route = models.CharField(max_length=512, blank=True)
    outcome = models.CharField(max_length=16)          # walked | blocked | not_reached
    #: Why the agent could not go on, in its own words. Required for `blocked` — a step that
    #: reports it was blocked without saying by what is not actionable by anyone.
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "journey_run", "number"),
                name="uniq_tenant_journey_step",
            )
        ]

    def __str__(self) -> str:
        return f"step {self.number}: {self.outcome}"


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
