"""The WCAG conformance statement: compile the evidence, draft it, sign it, export it (QA-24).

A client who has to prove accessibility — to a buyer, a regulator, a procurement team — needs a
document that walks all 55 Level A and AA criteria and says where the product stands. No
automated tool may produce that on its own. It carries professional judgement and a name.

So this module does the part the platform can honestly do: it reads what was actually observed
(`coverage.py`), what is actually open (`findings.py`), and what a person actually ruled
(`review.py`), and lays all 55 criteria out with the evidence beside each one. Then it stops.

**Every one of the 55 is listed, including the ones nothing looked at.** A criterion quietly
missing from a conformance table reads as a criterion that was fine. `NOT_EVALUATED` is printed
as itself and never folded into anything else — the same discipline as the six silences, at the
scale of a whole document.

**The platform suggests a level; it never asserts one.** `suggest` returns what the evidence
supports, and it returns `None` wherever the evidence cannot settle it. The reviewer's own
verdict always wins, and what they did not change is stated at signing rather than hidden.

**And it only suggests a POSITIVE level where the engine that can settle the criterion actually
looked** (#6, QA-25). That guard was missing until 27 August, and its absence had a name: axe's
`video-caption` rule proves a `<video>` has a caption *track*, that pass was recorded as coverage
for 1.2.2, and this module returned **"Supports"** — a statement telling a buyer the captions met
Level A when nobody had watched a second of the video. `does_not_support` and
`partially_supports` are deliberately NOT guarded: a proven failure is a fact about the product
whichever engine proved it. See `_can_claim_positive`.

**A criterion whose check is held back claims nothing either**, for the same reason and in the
same direction. 1.4.11 is measured for control edges and JUDGED for icons; with the judged
half paused, the measured half alone must not carry the criterion. See
`integrations.types.A11Y_HELD_BACK_CLAIMS`.

**"Risk reduction, not certification."** That sentence is in the drafted body and in
`DISCLAIMER`, and it is not decoration: automated and AI checks cover part of WCAG, this
document says what was checked and what was found, and the conformance claim belongs to the
person who signs it.
"""
from __future__ import annotations

import hashlib

from django.utils import timezone

from apps.labels import role_label
from apps.tenancy.context import tenant_context
from integrations.types import A11Y_HELD_BACK_CLAIMS

from . import coverage
from .policy import ACCESSIBILITY_REVIEWER_ROLE

#: The artifact this renders to. Distinct from `a11y_report` (one run's findings) and
#: `a11y_baseline` (where the application stands): this is a signed external-facing claim, and
#: collapsing it into either would give it their run-shaped or audit-shaped identity.
CONFORMANCE_TYPE = "conformance"
CONFORMANCE_FILENAME = "a11y-conformance.md"
CONFORMANCE_TITLE = "Accessibility conformance statement"

#: The VPAT vocabulary. Deliberately the standard's own words rather than ours — a client's
#: procurement team is reading this against other vendors' documents.
SUPPORTS = "supports"
PARTIALLY = "partially_supports"
DOES_NOT = "does_not_support"
NOT_APPLICABLE = "not_applicable"
NOT_EVALUATED = "not_evaluated"
LEVELS = (SUPPORTS, PARTIALLY, DOES_NOT, NOT_APPLICABLE, NOT_EVALUATED)

LEVEL_WORDS = {
    SUPPORTS: "Supports",
    PARTIALLY: "Partially supports",
    DOES_NOT: "Does not support",
    NOT_APPLICABLE: "Not applicable",
    NOT_EVALUATED: "Not evaluated",
}

DISCLAIMER = (
    "This is risk reduction, not certification. Automated and AI-assisted checks cover part of "
    "WCAG 2.2. This statement says what was checked, by what, and what was found. It does not "
    "certify conformance, and no part of it was claimed by the platform on its own."
)


class ConformanceError(Exception):
    """A conformance action could not be taken. Carries what was wrong, for a human."""


class ConformanceRoleError(ConformanceError):
    """The user does not hold the accessibility reviewer role on this project."""


# ---------------------------------------------------------------------------------------
# Compiling the 55
# ---------------------------------------------------------------------------------------

def _criteria(version: str = "2.2") -> list:
    """Every Level A and AA criterion in the standard, in numeric order — all 55 of them."""
    from .models import WcagCriterion

    rows = list(
        WcagCriterion.objects.filter(version=version, level__in=["A", "AA"])
        .values("number", "handle", "level")
    )
    return sorted(rows, key=lambda r: [int(p) for p in r["number"].split(".")])


def _ownership_by_criterion(version: str = "2.2") -> dict[str, tuple[str, bool]]:
    """{criterion: (owner, must_a_person_always_settle_it)} from the routing registry.

    Platform-wide and tenant-independent — the registry is a committed file loaded under the
    `0006_wcag_platform_wide` carve-out, so this needs no tenant context and returns the same
    answer for every client.

    **An empty map is a safe map.** A criterion with no row here gets no owner, and
    `_can_claim_positive` refuses every positive claim for an owner it does not recognise. So a
    database where the registry was never loaded produces a statement full of rows waiting for a
    person — visible, countable and obviously wrong to whoever opens it — rather than a statement
    full of claims made without knowing who was entitled to make them.
    """
    from .models import CriterionOwnership, Tier

    return {
        row["number"]: (str(row["owner"]), row["tier"] == Tier.HUMAN)
        for row in CriterionOwnership.objects.filter(version=version).values("number", "owner",
                                                                            "tier")
    }


def _open_by_criterion(tenant_id, project_id) -> dict[str, list]:
    from .models import A11yFinding

    out: dict[str, list] = {}
    with tenant_context(tenant_id):
        for finding in A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id,
            status=A11yFinding.Status.OPEN, outcome="failure",
        ):
            out.setdefault(finding.criterion, []).append(finding)
    return out


def _adjudicated_by_criterion(tenant_id, project_id) -> dict[str, int]:
    """How many findings a person has personally ruled on, per criterion (QA-23).

    This is the `human` provenance column AC1 asks for. It is a count of decisions, never a
    conformance verdict — a reviewer confirming three failures has not said the criterion is
    supported, and the two must not be confused.
    """
    from .models import A11yFinding

    out: dict[str, int] = {}
    with tenant_context(tenant_id):
        for row in A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id,
        ).exclude(adjudication=A11yFinding.Adjudication.PENDING).values("criterion"):
            out[row["criterion"]] = out.get(row["criterion"], 0) + 1
    return out


#: Which coverage engine is capable of SETTLING a criterion the ownership registry gives to this
#: owner. Read only when a positive claim is about to be made — see `_can_claim_positive`.
#:
#: `human` maps to the agentic pass rather than to nothing, because fifteen of the thirty
#: human-owned criteria are the ones Phase 2's keyboard walk reaches (2.1.1 Keyboard, 2.4.3 Focus
#: Order, 3.3.1 Error Identification …). The other fifteen are `tier=human` and never reach a
#: positive suggestion at all, whatever looked at them.
OWNER_ENGINES: dict[str, frozenset[str]] = {
    "rule": frozenset({"rule"}),
    "ai": frozenset({"AI"}),
    "human": frozenset({"agentic"}),
}


def _can_claim_positive(owner: str | None, always_human: bool, engines) -> bool:
    """May the evidence in hand support a positive claim about this criterion at all?

    **The check this module was missing, and the bug it caused was not theoretical** (#6, QA-25).
    axe ships `video-caption`, which proves a `<video>` has a caption *track*. That pass was
    recorded as coverage for 1.2.2 Captions, no failure existed, and `suggest` returned
    **"Supports"** — a conformance statement telling a buyer that a product's captions meet
    Level A when nobody had watched a second of the video. The same shape applied to 1.2.1, and
    to 2.2.1 Timing Adjustable on the strength of a `meta refresh` rule, and to 2.4.4 Link
    Purpose on the strength of a link having *any* accessible name.
    `ownership.partially_flaggable`'s own docstring had promised for months that a partial flag
    "never licenses reporting a pass" — and nothing in the platform read it. It and
    `needs_human_always` were imported by the test suite and by nothing else.

    Two questions, in this order:

      * **Is this a criterion a person must always settle?** The fifteen `tier=human` criteria
        turn on things no machine observes — whether captions are *accurate*, whether a flash is
        under the seizure threshold, whether an irreversible action is properly confirmed. For
        those the platform makes no positive suggestion at all, and the reviewer's own verdict is
        the only thing that can fill the row.
      * **Did the engine that can decide this actually look?** A criterion whose decider never
        ran has been touched, not checked. axe firing one narrow rule on a criterion the AI owns
        is a contribution, and `criteria_touched_by` exists precisely to name contributions as
        contributions. It is not grounds for a claim.

    **Only the POSITIVE direction is guarded, and that asymmetry is deliberate.** A proven
    failure is a fact about the product no matter which engine proved it, so `does_not_support`
    and `partially_supports` are unaffected — a rule scanner that catches a missing caption track
    has found a real Level A defect, and nothing here may soften it. This is the same one-way
    rule `journey_rules` and `page_rules` follow: a measurement can prove something wrong and can
    never, on its own, prove something right.
    """
    if always_human:
        return False
    allowed = OWNER_ENGINES.get(str(owner or ""))
    if allowed is None:
        # An owner we do not recognise — a registry that has grown a value this code has not
        # heard of. Claim nothing rather than guess; the row goes to the reviewer, which is the
        # safe direction and is visible in `awaiting_a_person`.
        return False
    return bool(allowed & set(engines or ()))


def suggest(cover: dict | None, failures: int, *, owner: str | None = None,
            always_human: bool = False, held_back: bool = False) -> str | None:
    """What the evidence supports, or `None` when it cannot settle it.

    `None` is a first-class answer here and the most important one: it is the platform declining
    to put a word in a reviewer's mouth. It comes back whenever something looked and could not
    decide, which is exactly the case a person exists for.

    The rules, in the order they are applied:

      * anything failed on every route it was checked on → **does not support**;
      * anything failed somewhere but not everywhere → **partially supports**;
      * a page is still waiting to be checked → **no suggestion** (finish the pass first);
      * something could not be decided → **no suggestion** (a human must);
      * **the engine that can decide this criterion never looked → no suggestion** (QA-25);
      * **a check this criterion needs is held back → no suggestion** (`A11Y_HELD_BACK_CLAIMS`):
        one half of a two-half criterion answering on its own is the same unsafe claim as the
        wrong engine answering, and it fails in the same direction;
      * checked somewhere with nothing wrong → **supports**;
      * the rule ran everywhere and had nothing to apply to → **not applicable**;
      * nothing looked at all → **not evaluated**.

    **`not_checked` returns `None` for a different reason from `needs_human`, and the document
    says so** (24 Aug). Both stop a claim being made, but one is waiting on a person and the
    other is waiting on us. Neither may become "supports" on the strength of the pages that did
    get checked — a criterion is a claim about the pages in scope, not about the subset we
    happened to reach before a budget ran out.

    **`owner` and `always_human` come from the ownership registry and default to the safe
    values.** A caller that passes neither gets the old behaviour for failures and silence for
    positive claims, which is the direction an omission should fail in.

    Note `failures` outranks the coverage map. An open failure is a fact about the product that
    survives the run that found it, and coverage is a fact about one capture — a criterion with
    an open Level A defect must never read as "supports" because the latest run happened not to
    revisit that page.
    """
    routes = (cover or {}).get("routes") or {}
    if failures:
        failed_routes = sum(1 for outcome in routes.values() if outcome == "failed")
        # Everything we looked at is broken, or we have failures and no coverage map at all.
        if not routes or failed_routes >= len(routes):
            return DOES_NOT
        return PARTIALLY
    if not routes:
        return NOT_EVALUATED
    outcomes = set(routes.values())
    if "failed" in outcomes:
        return DOES_NOT if outcomes == {"failed"} else PARTIALLY
    if "not_checked" in outcomes or "needs_human" in outcomes:
        return None
    # Everything below this line is a POSITIVE claim — "supports" or "not applicable" — and both
    # are claims a client's procurement team will read as an assurance. Neither may be made on
    # evidence from an engine that cannot settle this criterion.
    if held_back:
        # A criterion one of whose checks is paused (`A11Y_HELD_BACK_CLAIMS`). The evidence in
        # hand may be perfectly good and still be only part of the question: 1.4.11 is
        # measured for control edges by `page_rules` and JUDGED for icons and charts by
        # `graphics`, and with `graphics` held, a page whose buttons all have visible edges
        # would otherwise read "Supports" with nothing having looked at a single icon. That
        # is QA-25 word for word.
        #
        # Sits with the other positive-only guards, so a proven failure is untouched: an edge
        # under 3:1 is still a Level AA defect and is still reported.
        return None
    if not _can_claim_positive(owner, always_human, (cover or {}).get("engines") or ()):
        return None
    if "passed" in outcomes:
        return SUPPORTS
    return NOT_APPLICABLE


#: Who looked, in the words the screen's badges already use.
_ENGINE_WORDS = {"rule": "the automatic rule", "AI": "the AI check",
                 "agentic": "the keyboard walk", "human": "a person"}


def _checks_words(engines) -> str:
    """"this rule" / "the AI check" / "these checks" — whoever actually looked (finding 7)."""
    looked = [e for e in (engines or ()) if e != "human"]
    if looked == ["rule"]:
        return "this rule"
    if len(looked) == 1:
        return _ENGINE_WORDS.get(looked[0], "this check")
    return "these checks"


def why_undecided(cover: dict | None, *, owner: str | None = None, always_human: bool = False,
                  held_back: bool = False) -> str:
    """Why the platform suggests no level for this row — one line a reviewer can act on.

    Recon 2026-10-10, finding 7: a row said "needs your decision" and never why. The reasons are
    `suggest`'s own guards, in its own order, so the sentence cannot disagree with the decision.

    Never "choose a level" (mockup B, 2026-10-12): on this page "level" is WCAG's Level A / AA,
    so the person's pick is named as a result, in the column where it is made.
    """
    routes = (cover or {}).get("routes") or {}
    outcomes = set(routes.values())
    engines = sorted(e for e in ((cover or {}).get("engines") or ()) if e != "human")
    if "not_checked" in outcomes:
        return ("A page is still waiting to be checked. Let the audit finish, or pick its result "
                "in the Conformance column.")
    if "needs_human" in outcomes:
        return ("A check looked at this and couldn't decide. "
                "Pick its result in the Conformance column.")
    if held_back:
        return ("Part of the checking for this criterion is paused, so no result is suggested. "
                "Pick its result in the Conformance column.")
    if always_human:
        return ("Only a person can judge this criterion — no check can observe it. "
                "Pick its result in the Conformance column.")
    who = " and ".join(_ENGINE_WORDS.get(e, e) for e in engines) or "a check"
    return (f"{who[:1].upper()}{who[1:]} looked, but can't settle this criterion on its own. "
            "Pick its result in the Conformance column.")


def _evidence_sentence(cover: dict | None, failures: int, adjudicated: int) -> str:
    """What actually happened, in words, with no verdict in it.

    This is the column the team asked for: *whatever the platform tests and captures, shown as
    it was*. It never says "supports" — it says what was checked, where, and what came back.
    """
    routes = (cover or {}).get("routes") or {}
    if not routes and not failures:
        return "Nothing checked this."
    counts: dict[str, int] = {}
    for outcome in routes.values():
        counts[outcome] = counts.get(outcome, 0) + 1
    parts = []
    if failures:
        parts.append(f"{failures} open failure{'s' if failures != 1 else ''}")
    if counts.get("failed"):
        parts.append(f"failed on {counts['failed']} of {len(routes)} pages checked")
    # Said before `needs_human`, matching the order `coverage._RANK` puts them in: an unfinished
    # pass is the first thing to do something about, and the something is cheap.
    if counts.get("not_checked"):
        parts.append(
            f"{counts['not_checked']} page{'s' if counts['not_checked'] != 1 else ''} still "
            f"waiting on a check that has not run"
        )
    if counts.get("needs_human"):
        parts.append(
            f"{counts['needs_human']} page{'s' if counts['needs_human'] != 1 else ''} a check "
            f"looked at and could not decide"
        )
    if counts.get("passed"):
        parts.append(f"checked on {counts['passed']} pages with nothing wrong")
    if counts.get("not_applicable"):
        parts.append(
            f"{counts['not_applicable']} pages had nothing for "
            f"{_checks_words((cover or {}).get('engines'))} to apply to"
        )
    if adjudicated:
        parts.append(f"{adjudicated} reviewed by a person")
    if not parts:
        return "Nothing checked this."
    text = "; ".join(parts)
    # Only the first character. `str.capitalize()` lower-cases everything after it, which
    # would quietly mangle a rule id or a route name the moment one appears here.
    return text[:1].upper() + text[1:] + "."


def criterion_rows(tenant_id, project_id, *, verdicts: dict | None = None) -> list[dict]:
    """All 55 Level A and AA criteria with their evidence, provenance and level.

    `established_by` is AC1's rule/AI/human provenance, read from what actually produced the
    evidence rather than from what we expect to produce it — a criterion the ownership table
    says the AI owns still reports `rule` if that is what looked at it.
    """
    verdicts = verdicts or {}
    with tenant_context(tenant_id):
        cover = coverage.summary(tenant_id, project_id)
    failures = _open_by_criterion(tenant_id, project_id)
    adjudged = _adjudicated_by_criterion(tenant_id, project_id)
    owners = _ownership_by_criterion()

    rows = []
    for crit in _criteria():
        number = crit["number"]
        cov = cover.get(number)
        open_count = len(failures.get(number, []))
        ruled = adjudged.get(number, 0)
        engines = sorted((cov or {}).get("engines") or set())
        if ruled:
            engines = [*engines, "human"]
        # Who the registry says decides this criterion, and whether a person must always be the
        # one to settle it (QA-25, #6). Unknown for a criterion with no registry row, which
        # `suggest` treats as grounds to claim nothing rather than as grounds to claim anything.
        owner, always_human = owners.get(number, (None, False))
        suggested = suggest(cov, open_count, owner=owner, always_human=always_human,
                            held_back=number in A11Y_HELD_BACK_CLAIMS)
        chosen = (verdicts.get(number) or {}).get("level")
        undecided = chosen not in LEVELS and suggested is None
        rows.append({
            "criterion": number,
            "handle": crit["handle"],
            "level": crit["level"],
            "evidence": _evidence_sentence(cov, open_count, ruled),
            "established_by": engines,
            "routes_checked": len((cov or {}).get("routes") or {}),
            "open_failures": open_count,
            "human_decisions": ruled,
            "suggested": suggested,
            "verdict": chosen if chosen in LEVELS else None,
            # What the statement will actually say. The reviewer's word if they gave one, the
            # evidence's word if it had one, and otherwise NOT EVALUATED — never a guess.
            "effective": (chosen if chosen in LEVELS else None) or suggested or NOT_EVALUATED,
            # True when the platform has no suggestion and the reviewer has not ruled: the row
            # is unfinished, and the signing step counts these out loud.
            "needs_a_person": undecided,
            # Why, when a person is needed (finding 7). Empty otherwise.
            "why": why_undecided(cov, owner=owner, always_human=always_human,
                                 held_back=number in A11Y_HELD_BACK_CLAIMS) if undecided else "",
        })
    return rows


def totals(rows: list[dict]) -> dict:
    """The headline counts S-37 shows, derived from the rows so they cannot disagree."""
    out = {level: 0 for level in LEVELS}
    for row in rows:
        out[row["effective"]] = out.get(row["effective"], 0) + 1
    out["total"] = len(rows)
    out["evaluated"] = len(rows) - out[NOT_EVALUATED]
    out["awaiting_a_person"] = sum(1 for row in rows if row["needs_a_person"])
    # Levels the EVIDENCE suggested and the reviewer kept. "Not evaluated" is not a suggestion
    # — nothing looked — and counting it told a signer that 50 levels came from evidence when
    # 36 of them came from nothing at all (recon 2026-10-10, finding 8).
    out["platform_suggested"] = sum(
        1 for row in rows if row["verdict"] is None
        and row["suggested"] not in (None, NOT_EVALUATED)
    )
    return out


# ---------------------------------------------------------------------------------------
# Provenance — recorded, never displayed (D-A11Y-96)
# ---------------------------------------------------------------------------------------

def provenance(tenant_id, project_id) -> dict:
    """Which engine, model, prompt version and scanner produced the evidence.

    **Recorded on the export and never shown to the tenant** (team decision, D-A11Y-96). It is
    our implementation detail, not a client's business — but without it a signed statement can
    never be traced back to what produced it, which is what AC2 requires.

    The scanner version is per-project and per-run because axe-core is imported from the
    client's own repository; a statement covering two runs on two axe versions says both.
    """
    from .models import A11yFinding, A11yScreenScan

    with tenant_context(tenant_id):
        engines = sorted({
            f"{row['engine']}/{row['model']}/{row['prompt_version']}"
            for row in A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .values("engine", "model", "prompt_version")
            if row["engine"] or row["model"]
        })
        scanners = sorted({
            row["scanner_version"] for row in A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .values("scanner_version") if row["scanner_version"]
        })
    return {"judges": engines, "scanners": scanners}


def evidence_basis(tenant_id, project_id) -> dict:
    """Which accessibility checks this statement rests on, and when they ran.

    **Not the same thing as `provenance` above, and deliberately the opposite of it.** That
    records our engine, model and prompt version, is written to the signature's audit entry and
    is never shown to a tenant. This is the client's own half of the same question — *which
    audit produced this, and when did somebody run it* — and it belongs on the screen and,
    more importantly, inside the wording that gets signed.

    **Every completed audit is counted, not only the most recent one.** The findings ledger is
    project-scoped and cumulative, so a statement compiled today rests on everything recorded
    up to today. Naming only the latest audit would read as "this is what was checked", which
    would be untrue the moment a project has had two.

    A `failed` audit is left out on purpose. It published nothing — an audit whose machine went
    away has its partial capture kept and its baseline deliberately not written — so listing it
    as a basis would credit this statement with coverage it never had.
    """
    from .baseline import audit_label
    from .models import A11yBaselineAudit, A11yFinding

    complete = A11yBaselineAudit.Status.COMPLETE
    with tenant_context(tenant_id):
        audits = A11yBaselineAudit.objects.filter(
            tenant_id=tenant_id, project_id=project_id, status=complete)
        # A total order, not just a sort key. Two audits can carry the same `updated_at` — two
        # finishing inside one timestamp is unlikely in the field and routine in a test — and
        # a tie there would make "the most recent audit" a different answer on different reads
        # of the same data, on a document somebody signs.
        latest = audits.order_by("-updated_at", "-created_at", "-id").first()
        total = audits.count()
        # Greenfield: a finding recorded against a build's own run rather than an audit. Counted
        # rather than listed — a project with two hundred runs would drown the statement.
        runs = (
            A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN, last_seen_run__isnull=False)
            .values_list("last_seen_run_id", flat=True).distinct().count()
        )
    return {
        "latest": None if latest is None else {
            "id": str(latest.id),
            # A name, not an id (recon 2026-10-10, finding 5). `started_at` rides along so the
            # screen can add the time of day in the reader's own clock.
            "label": audit_label(latest),
            "started_at": latest.created_at,
            "finished_at": latest.updated_at,
            "asked": int((latest.summary or {}).get("asked") or len(latest.routes or [])),
            "opened": int((latest.summary or {}).get("opened") or 0),
        },
        "audits": total,
        "runs": runs,
    }


def _basis_lines(basis: dict | None) -> list[str]:
    """The "what this is based on" section, in the statement's own words.

    **Inside `draft_body` rather than beside it**, which is the whole point of the change: the
    section is part of what `signed_body_hash` covers, so the person signing is signing the
    claim about which audit this came from as well as the claim about conformance. A label
    printed next to the document would not be signed, and would go on looking right after the
    document had been edited to say something else.
    """
    basis = basis or {}
    lines = ["## What this is based on", ""]
    latest = basis.get("latest")
    if latest is None and not basis.get("runs"):
        lines += [
            "**No completed accessibility audit is recorded for this project.** Nothing below "
            "rests on a check this platform ran, so every criterion it would have established "
            "is listed as not evaluated.",
            "",
        ]
        return lines

    if latest is not None:
        when = latest["finished_at"]
        stamp = when.strftime("%d %B %Y at %H:%M UTC") if when else "an unrecorded time"
        started = latest.get("started_at")
        began = started.strftime("%d %B %Y at %H:%M UTC") if started else "an unrecorded time"
        # No id in the wording (recon 2026-10-10, finding 5): this document is read — and signed —
        # by people. The id is kept with the signature's provenance, which is never displayed.
        lines.append(
            f"The most recent accessibility audit of this application started on {began}, "
            f"asked for {latest['asked']} page(s), opened {latest['opened']}, and finished on "
            f"{stamp}."
        )
        others = int(basis.get("audits") or 0) - 1
        if others > 0:
            lines.append("")
            lines.append(
                f"It is not the only evidence here. {others} earlier completed audit(s) of this "
                f"project also contribute findings, because what is recorded about an "
                f"application accumulates rather than being replaced by the latest pass."
            )
    if basis.get("runs"):
        lines.append("")
        lines.append(
            f"{basis['runs']} development run(s) contributed findings that are still open."
        )
    lines.append("")
    return lines


def evidence_fingerprint(tenant_id, project_id) -> str:
    """A hash of everything the statement rests on (team decision C1).

    Changes when a run finds something new, when a reviewer rules, or when a scanner reports
    differently. That is how "the words are unchanged but the facts underneath moved" becomes a
    fact the screen can state, rather than something nobody notices until a client does.

    Built from the compiled rows rather than from raw tables on purpose: two different sets of
    findings that produce an identical statement genuinely are the same statement, and re-asking
    for a signature there would train reviewers to click through re-signing.
    """
    rows = criterion_rows(tenant_id, project_id)
    payload = "\\n".join(
        f"{r['criterion']}|{r['effective']}|{r['open_failures']}|{r['routes_checked']}|"
        f"{','.join(r['established_by'])}"
        for r in rows
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------------------

def draft_body(*, scope: str, rows: list[dict], version: str = "2.2",
               basis: dict | None = None) -> str:
    """The platform's draft of the statement. The reviewer edits this freely.

    Written to be readable by the person it is *about* — a procurement reader, not us. Every
    number in it is derived from `rows`, so the prose and the table can never disagree.

    `basis` names the audit the evidence came from and when it ran (`evidence_basis`). It is
    rendered *into* the document rather than shown beside it so that the person signing signs
    it too — a statement that cannot say which pass produced it is a statement nobody can check
    a year later.
    """
    counts = totals(rows)
    lines = [
        f"# Accessibility conformance statement (WCAG {version} Level AA)",
        "",
        f"**Scope.** {scope.strip() or 'Not stated.'}",
        "",
        f"> {DISCLAIMER}",
        "",
        *_basis_lines(basis),
        "## Summary",
        "",
        f"Of the {counts['total']} Level A and AA success criteria, **{counts['evaluated']} "
        f"were evaluated** and **{counts[NOT_EVALUATED]} were not**. Criteria that were not "
        f"evaluated are listed as such and are not counted as supported.",
        "",
    ]
    if counts[DOES_NOT] or counts[PARTIALLY]:
        lines += [
            f"{counts[DOES_NOT]} criteria do not support and {counts[PARTIALLY]} partially "
            f"support. Every underlying problem is tracked as a defect.",
            "",
        ]
    if counts["awaiting_a_person"]:
        lines += [
            f"{counts['awaiting_a_person']} criteria were looked at by a check that could not "
            f"decide, and are awaiting a person's assessment.",
            "",
        ]
    lines += [
        "## Per criterion",
        "",
        "| Criterion | Level | Conformance | Established by | What was checked |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        established = ", ".join(row["established_by"]) or "—"
        lines.append(
            f"| {row['criterion']} {row['handle']} | {row['level']} | "
            f"{LEVEL_WORDS[row['effective']]} | {established} | {row['evidence']} |"
        )
    lines += [
        "",
        "## How to read this",
        "",
        "**Not evaluated** means nothing checked it. It is printed as itself and is never "
        "rolled into a supporting result — a criterion nobody looked at is the single easiest "
        "way for a document like this to become untrue.",
        "",
        "**Not applicable** means a check ran and there was nothing on the page for it to "
        "apply to. That is not the same as supporting it.",
        "",
    ]
    return "\n".join(lines)


def _statement(tenant_id, project_id, *, create=True):
    from apps.projects.models import Project

    from .models import A11yConformanceStatement

    with tenant_context(tenant_id):
        row = A11yConformanceStatement.objects.filter(
            tenant_id=tenant_id, project_id=project_id).first()
        if row is None and create:
            project = Project.objects.get(id=project_id, tenant_id=tenant_id)
            row = A11yConformanceStatement.objects.create(
                tenant_id=tenant_id, project=project,
                scope=project.name, verdicts={},
            )
        return row


def _body_hash(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def is_stale(row, *, evidence_hash: str) -> bool:
    """Signed, but the evidence has moved since (team decision C1)."""
    return bool(row.signed_at) and row.signed_evidence_hash != evidence_hash


def state(*, tenant_id, project_id) -> dict:
    """Everything S-37 renders: the rows, the counts, the draft, and the signature's standing."""
    row = _statement(tenant_id, project_id)
    rows = criterion_rows(tenant_id, project_id, verdicts=row.verdicts or {})
    basis = evidence_basis(tenant_id, project_id)
    body = row.body or draft_body(scope=row.scope, rows=rows, basis=basis)
    fingerprint = evidence_fingerprint(tenant_id, project_id)
    stale = is_stale(row, evidence_hash=fingerprint)
    return {
        "scope": row.scope,
        "body": body,
        "drafted": not row.body,
        # Also on the payload, not only inside the wording. The body is the reviewer's to edit
        # — they may cut the section — and the screen still has to be able to say which audit
        # the numbers on it were compiled from.
        "basis": basis,
        "rows": rows,
        "totals": totals(rows),
        # An audit is still running, so the numbers above are still coming in (finding 3).
        "audit_in_progress": audit_in_progress(tenant_id, project_id),
        # Nothing has looked at anything yet: the signing panel says "Run an audit first".
        "has_evidence": has_evidence(rows),
        "disclaimer": DISCLAIMER,
        "signed": bool(row.signed_at),
        "signed_name": row.signed_name,
        "signed_role": row.signed_role,
        "signed_at": row.signed_at,
        "stale": stale,
        "artifact_id": str(row.artifact_id) if row.artifact_id else None,
        "required_role": ACCESSIBILITY_REVIEWER_ROLE,
        "can_export": bool(row.signed_at) and not stale,
        # When the signed statement was last exported — the Export box says so after the click.
        "exported_at": _exported_at(row),
        "export_refused_because": _refusal(row, stale),
    }


def has_evidence(rows: list[dict]) -> bool:
    """Did anything look at anything? False when no check has run on a single page and nothing
    is open — the state in which there is nothing to sign (recon 2026-10-10, finding 8)."""
    # A reviewer's own level counts: a person who assessed a criterion themselves has evidence.
    return any(row["routes_checked"] or row["open_failures"] or row["verdict"] for row in rows)


def audit_in_progress(tenant_id, project_id) -> bool:
    """Is an audit on this project still running? Its pages are recorded as they arrive, so
    the statement's numbers are partial until it ends (recon 2026-10-10, finding 3)."""
    from .baseline import IN_FLIGHT_STATUSES
    from .models import A11yBaselineAudit

    with tenant_context(tenant_id):
        return A11yBaselineAudit.objects.filter(
            tenant_id=tenant_id, project_id=project_id, status__in=IN_FLIGHT_STATUSES,
        ).exists()


def _refusal(row, stale: bool) -> str:
    if not row.signed_at:
        return (
            "This cannot be exported unsigned. A conformance statement carries someone's "
            "professional judgement, and the platform has none to give."
        )
    if stale:
        return (
            "The evidence has changed since this was signed. The wording is still what "
            f"{row.signed_name or 'the reviewer'} signed, but it no longer describes what the "
            "platform holds — read it again and re-sign."
        )
    return ""


def save_draft(*, tenant_id, project_id, user_id, scope=None, body=None, verdicts=None) -> dict:
    """Edit the statement. **Any edit clears the signature.**

    Not a courtesy — a signature on wording nobody signed is worse than no signature at all, and
    it is the one way this document could carry a name against words that person never read.
    """
    if not can_sign(tenant_id=tenant_id, project_id=project_id, user_id=user_id):
        raise ConformanceRoleError(
            f"Only the accessibility reviewer ({role_label(ACCESSIBILITY_REVIEWER_ROLE)}) on "
            f"this project can edit the conformance statement."
        )
    row = _statement(tenant_id, project_id)
    changed = False
    with tenant_context(tenant_id):
        if scope is not None and scope != row.scope:
            row.scope, changed = scope, True
        if body is not None and body != row.body:
            row.body, changed = body, True
        if verdicts is not None:
            merged = dict(row.verdicts or {})
            for number, value in (verdicts or {}).items():
                level = (value or {}).get("level")
                if level is not None and level not in LEVELS:
                    raise ConformanceError(
                        f"That isn't a conformance level. Use one of: "
                        f"{', '.join(LEVEL_WORDS[k] for k in LEVELS)}."
                    )
                merged[str(number)] = {"level": level,
                                       "note": str((value or {}).get("note") or "")}
            if merged != (row.verdicts or {}):
                row.verdicts, changed = merged, True
        if changed and row.signed_at:
            row.signed_by_id = None
            row.signed_name = ""
            row.signed_role = ""
            row.signed_at = None
            row.signed_body_hash = ""
            row.signed_evidence_hash = ""
            _event(tenant_id, "a11y.conformance.signature_cleared", row, user_id,
                   {"why": "the statement was edited after it was signed"})
        row.save()
    return state(tenant_id=tenant_id, project_id=project_id)


def can_sign(*, tenant_id, project_id, user_id) -> bool:
    """The same role and the same two admin carve-outs the review console uses."""
    from .review import can_review

    return can_review(tenant_id=tenant_id, project_id=project_id, user_id=user_id)


def sign(*, tenant_id, project_id, user_id, name: str, acknowledged: bool = False) -> dict:
    """Put a person's name to the statement — which is also what unlocks export (B1).

    `acknowledged` is the reviewer confirming they understand what they are signing, and it is
    required rather than implied. Two things they must have seen: how many criteria were **not
    evaluated**, and how many levels the **platform suggested and they did not change**. Both
    are counted for them; neither is buried.
    """
    from apps.registry.models import Artifact

    if not can_sign(tenant_id=tenant_id, project_id=project_id, user_id=user_id):
        raise ConformanceRoleError(
            f"Only the accessibility reviewer ({role_label(ACCESSIBILITY_REVIEWER_ROLE)}) on "
            f"this project can sign a conformance statement."
        )
    if not (name or "").strip():
        raise ConformanceError("Sign with your name as it should appear on the statement.")
    if not acknowledged:
        raise ConformanceError(
            "Confirm you have read the statement and the evidence behind it, including how "
            "many criteria were not evaluated. Signing is the whole point of this document."
        )

    # Refused on the server, not only hidden on the screen (findings 3 and 8): a statement signed
    # over half an audit, or over no evidence at all, is the claim this document exists to stop.
    if audit_in_progress(tenant_id, project_id):
        raise ConformanceError(
            "An audit is still running, so these numbers are still coming in. Sign once it "
            "finishes."
        )
    row = _statement(tenant_id, project_id)
    rows = criterion_rows(tenant_id, project_id, verdicts=row.verdicts or {})
    counts = totals(rows)
    if not has_evidence(rows):
        raise ConformanceError(
            "Nothing has been checked yet, so there is nothing to sign. Run an audit first."
        )
    body = row.body or draft_body(
        scope=row.scope, rows=rows, basis=evidence_basis(tenant_id, project_id))

    with tenant_context(tenant_id):
        row.body = body
        row.signed_by_id = user_id
        row.signed_name = name.strip()[:255]
        row.signed_role = ACCESSIBILITY_REVIEWER_ROLE
        row.signed_at = timezone.now()
        row.signed_body_hash = _body_hash(body)
        row.signed_evidence_hash = evidence_fingerprint(tenant_id, project_id)
        row.save()

        artifact = _publish_artifact(tenant_id, project_id, row, body)
        row.artifact = artifact
        row.save(update_fields=["artifact", "updated_at"])
        # **The signature is the gate** (B1). This is the state the existing publish endpoint
        # already requires, so nothing reaches a system of record without a named human
        # approval — which is what non-negotiable #5 is actually for.
        artifact.status = Artifact.Status.APPROVED
        artifact.save(update_fields=["status", "updated_at"])
    published = publish_evidence(tenant_id, project_id)

    _event(tenant_id, "a11y.conformance.signed", row, user_id, {
        "name": row.signed_name,
        "role": row.signed_role,
        "body_hash": row.signed_body_hash,
        "evidence_hash": row.signed_evidence_hash,
        "not_evaluated": counts[NOT_EVALUATED],
        "platform_suggested_unchanged": counts["platform_suggested"],
        "evidence_published": published,
        # Which audit the wording rests on. The wording names it by when it ran (recon
        # 2026-10-10, finding 5); this is what still ties the signature to exactly that audit.
        "audit_id": ((evidence_basis(tenant_id, project_id).get("latest") or {}).get("id")),
        # Recorded here and NEVER displayed (D-A11Y-96) — without it a signed statement can
        # never be traced back to what produced it (AC2).
        "provenance": provenance(tenant_id, project_id),
    })
    return state(tenant_id=tenant_id, project_id=project_id)


def publish_evidence(tenant_id, project_id) -> list[str]:
    """Publish the audit documents a signature stands on. Returns the ids it published.

    Team decision 2026-10-10: the Accessibility report and baseline stay **Draft** until the
    conformance statement is signed, and signing publishes them — the signature is the named
    human approval they were waiting for (non-negotiable #5). Inside the platform only: the
    statement itself keeps its own path (Approved here, Published when exported).

    **Audit documents only** (`run` is null). A report filed against a development run belongs
    to that run's own gate, and a signature on a statement is not a decision about it.
    Drafts only, so nothing already published, approved or superseded moves.
    """
    from mcp_platform_state import tools

    from apps.registry.models import Artifact

    from .baseline_report import BASELINE_TYPE
    from .report import REPORT_TYPE

    with tenant_context(tenant_id):
        ids = [str(i) for i in Artifact.objects.filter(
            tenant_id=tenant_id, project_id=project_id, run__isnull=True,
            type__in=(REPORT_TYPE, BASELINE_TYPE), status=Artifact.Status.DRAFT,
        ).values_list("id", flat=True)]
        for artifact_id in ids:
            tools.update_artifact(tenant_id, artifact_id, status=Artifact.Status.PUBLISHED)
    return ids


def _publish_artifact(tenant_id, project_id, row, body: str):
    """Register (or refresh) the `conformance` artifact holding the signed wording."""
    from mcp_platform_state import tools

    from apps.registry.models import Artifact

    digest = _body_hash(body)
    staged = None
    try:
        staged = tools.stage_artifact_body(
            tenant_id, project_id, None, "testing", CONFORMANCE_FILENAME, body,
            content_type="text/markdown",
        )
    except Exception:  # noqa: BLE001 — a pointer beats no document; same trade as publish_report
        staged = None

    existing = Artifact.objects.filter(
        tenant_id=tenant_id, project_id=project_id, type=CONFORMANCE_TYPE).first()
    if existing is not None:
        tools.update_artifact(
            tenant_id, str(existing.id),
            content_hash=(staged or {}).get("content_hash") or digest,
        )
        existing.refresh_from_db()
        return existing
    created = tools.register_artifact(
        tenant_id, project_id, None, "testing", CONFORMANCE_TYPE, "internal",
        content_hash=(staged or {}).get("content_hash") or digest,
        s3_key=(staged or {}).get("s3_key"),
        title=CONFORMANCE_TITLE,
    )
    return Artifact.objects.get(id=created["id"], tenant_id=tenant_id)


def check_export(*, tenant_id, project_id) -> None:
    """Raise unless this statement may leave the building. AC3's no-auto-certify rule.

    Enforced here as well as by the publish endpoint's gate check, deliberately: the endpoint
    knows only that an artifact is approved, and the sentence a refused reviewer needs to read
    is about a signature, not a status.
    """
    row = _statement(tenant_id, project_id, create=False)
    if row is None or not row.signed_at:
        raise ConformanceError(
            "This cannot be exported unsigned. A conformance statement carries someone's "
            "professional judgement, and the platform has none to give — sign it as the "
            "accessibility reviewer, or ask someone who holds that role to."
        )
    if is_stale(row, evidence_hash=evidence_fingerprint(tenant_id, project_id)):
        raise ConformanceError(_refusal(row, True))


def _exported_at(row):
    """When THIS signature was last exported. Not `published_at`: that is the first publish,
    kept on purpose for reporting, so after an edit, re-sign and re-export the box showed the
    earlier export's time (live retest 2026-10-12)."""
    from apps.ledger.models import Event

    artifact = row.artifact if row.artifact_id else None
    if artifact is None or artifact.status != "published" or not row.signed_at:
        return None
    latest = (Event.objects.filter(tenant_id=row.tenant_id, action="a11y.conformance.exported",
                                   target_id=row.id, ts__gte=row.signed_at)
              .order_by("-ts").values_list("ts", flat=True).first())
    return latest or artifact.published_at


def export_statement(*, tenant_id, project_id, user_id) -> dict:
    """Export the signed statement: mark it Published inside the platform and record it.

    The person gets the file itself from the screen, which downloads exactly the signed wording.
    Deliberately NOT the generic publish-to-a-system-of-record path: the statement is filed
    under Testing, and Testing documents go to test management, which would turn a signed
    statement into test cases (recon 2026-10-10, item 3).
    """
    from apps.registry.models import Artifact

    check_export(tenant_id=tenant_id, project_id=project_id)
    row = _statement(tenant_id, project_id, create=False)
    with tenant_context(tenant_id):
        artifact = Artifact.objects.get(id=row.artifact_id, tenant_id=tenant_id)
        if artifact.published_at is None:
            artifact.published_at = timezone.now()
        artifact.status = Artifact.Status.PUBLISHED
        artifact.save(update_fields=["status", "published_at", "updated_at"])
    _event(tenant_id, "a11y.conformance.exported", row, user_id, {
        "artifact_id": str(artifact.id),
        "body_hash": row.signed_body_hash,
    })
    return state(tenant_id=tenant_id, project_id=project_id)


def _event(tenant_id, action: str, row, user_id, payload: dict) -> None:
    from apps.ledger.models import Event

    Event.objects.create(
        tenant_id=tenant_id, actor=str(user_id or "system"), action=action,
        target_type="a11y_conformance", target_id=row.id,
        project_id=row.project_id,      # S.No 230 — this path bypasses tools.log_event
        payload={"project_id": str(row.project_id), **payload},
    )
