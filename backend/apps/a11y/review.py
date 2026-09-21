"""The SME review console: what a person sees, and what happens when they rule (QA-23).

The platform refuses to guess. When a check cannot settle an element it marks the finding
`needs_review` and puts it aside, and until this module nothing in the product could open that
pile — `findings.review_queue` was a query nobody called. This is the other half: the evidence
a reviewer needs in front of them, and the consequences of the answer they give.

**A decision here is not an annotation, it is the platform's answer.** Confirming turns a
finding into a real failure, which is what makes the defect loop raise a ticket; rejecting
closes it. Both outrank the machine on later runs for as long as the element is unchanged
(`findings._ruling_still_applies`). A console whose decisions the next run quietly overwrote
would be worse than no console, because it would look like it worked.

**Nothing here decides what is in the queue.** That is `findings.review_queue`, and it is a
query rather than a table on purpose — being in the queue *is* what "needs review and nobody
has ruled" means, so there is no second state to keep in step.

**Pointer, never body (#1/#3).** `screenshot` is a read-through: it fetches the picture from
the object store on demand and hands the bytes straight out. It is never copied onto a row.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.tenancy.context import tenant_context

logger = logging.getLogger(__name__)

#: How long one reviewer holds an item before it returns to the queue by itself (team decision
#: C1, 2026-08-18). Renewed every time they load the item, so it only lapses when they have
#: genuinely stopped.
#:
#: The failure modes are not symmetrical, which is why this expires rather than being held
#: until released. A lock that lapses early costs a reviewer one re-open. A lock that never
#: lapses parks a finding under the name of whoever closed their laptop, and needs an admin
#: override — a thing to build, and a thing to remember exists.
#:
#: Nothing sweeps expired locks. An expired lock is simply not honoured, so there is no
#: background job here that can fail quietly and leave the queue wrong.
LOCK_MINUTES = 15

CONFIRM = "confirm"
REJECT = "reject"
DECISIONS = (CONFIRM, REJECT)


class ReviewError(Exception):
    """A review action could not be taken. Carries what was wrong, for a human."""


class ReviewRoleError(ReviewError):
    """The user does not hold the accessibility reviewer role on this project."""


class ReviewLockError(ReviewError):
    """Someone else is reviewing this item."""


# ---------------------------------------------------------------------------------------
# Who may review
# ---------------------------------------------------------------------------------------

def can_review(*, tenant_id, project_id, user_id) -> bool:
    """May this user rule on this project's accessibility findings?

    The role is `qa_lead` (`policy.ACCESSIBILITY_REVIEWER_ROLE`) and the admin carve-outs are
    the same two the gate uses (`gates.services.decide`): a project admin, or a tenant admin.
    Deliberately identical — a person who may approve the accessibility gate but may not answer
    the questions feeding it would be a strange place to draw a line.
    """
    from apps.base import Role
    from apps.tenancy.models import Membership, User

    from .policy import ACCESSIBILITY_REVIEWER_ROLE

    if not user_id:
        return False
    with tenant_context(tenant_id):
        if Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=project_id,
            role__in=[ACCESSIBILITY_REVIEWER_ROLE, Role.ADMIN],
        ).exists():
            return True
        return User.objects.filter(
            id=user_id, tenant_id=tenant_id, is_tenant_admin=True
        ).exists()


# ---------------------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------------------

def lock_holder(finding, *, now=None):
    """The user holding this item right now, or None — expiry honoured, never swept.

    Returns None for an unheld item AND for one whose claim has lapsed, so every caller gets
    the same answer to "may this be worked on" without anyone having to remember the timeout.
    """
    if not finding.review_locked_by_id or finding.review_locked_at is None:
        return None
    now = now or timezone.now()
    if now - finding.review_locked_at >= timedelta(minutes=LOCK_MINUTES):
        return None
    return finding.review_locked_by_id


def lock_state(finding, *, user_id=None, now=None) -> dict:
    """The lock as the screen needs to render it: who, until when, and is it me."""
    from apps.tenancy.models import User

    holder = lock_holder(finding, now=now)
    if holder is None:
        return {"held": False, "by_me": False, "held_by": None, "held_by_name": "",
                "expires_at": None}
    mine = str(holder) == str(user_id)
    name = ""
    if not mine:
        who = User.objects.filter(id=holder).values_list("name", "email").first() or ("", "")
        name = who[0] or who[1] or "another reviewer"
    return {
        "held": True,
        "by_me": mine,
        "held_by": str(holder),
        "held_by_name": name,
        "expires_at": finding.review_locked_at + timedelta(minutes=LOCK_MINUTES),
    }


def claim(finding, *, user_id, now=None) -> bool:
    """Take or renew the claim on this item. Returns True when it is a NEW claim.

    Raises `ReviewLockError` when someone else holds it. The return value exists so the caller
    can write one ledger event per real claim instead of one per page load — a renewal every
    few seconds is not an audit trail, it is noise that hides the entries that matter.
    """
    now = now or timezone.now()
    holder = lock_holder(finding, now=now)
    if holder is not None and str(holder) != str(user_id):
        state = lock_state(finding, user_id=user_id, now=now)
        raise ReviewLockError(
            f"{state['held_by_name']} is reviewing this one. It returns to the queue on its "
            f"own if they stop."
        )
    fresh = holder is None
    finding.review_locked_by_id = user_id
    finding.review_locked_at = now
    finding.save(update_fields=["review_locked_by", "review_locked_at", "updated_at"])
    return fresh


def release(finding) -> None:
    """Hand the item back. Called on a decision, and by a reviewer who steps away."""
    finding.review_locked_by_id = None
    finding.review_locked_at = None
    finding.save(update_fields=["review_locked_by", "review_locked_at", "updated_at"])


# ---------------------------------------------------------------------------------------
# The evidence
# ---------------------------------------------------------------------------------------

def _bundle_for(finding):
    """The captured element behind this finding — this run's if we have it, else the latest.

    A finding outlives the run that found it (that is the point of the ledger), so its
    evidence has to be looked up rather than carried. Preferring the run that last saw it keeps
    the picture and the verdict describing the same moment.
    """
    from .models import A11yCandidateBundle

    rows = A11yCandidateBundle.objects.filter(
        tenant_id=finding.tenant_id, project_id=finding.project_id,
        route=finding.route, selector=finding.selector,
    )
    if finding.last_seen_run_id:
        exact = rows.filter(run_key=str(finding.last_seen_run_id)).first()
        if exact is not None:
            return exact
    return rows.order_by("-created_at").first()


def _scan_for(finding):
    """The screen scan carrying the page picture for this finding's route.

    Falls back past scans that have no picture, because a route that failed to screenshot once
    should not hide the page image every other run of it captured.
    """
    from .models import A11yScreenScan

    rows = A11yScreenScan.objects.filter(
        tenant_id=finding.tenant_id, project_id=finding.project_id, route=finding.route,
    )
    if finding.last_seen_run_id:
        exact = rows.filter(run_key=str(finding.last_seen_run_id)).exclude(
            page_image_ref="").first()
        if exact is not None:
            return exact
    return rows.exclude(page_image_ref="").order_by("-created_at").first()


def evidence_for(finding) -> dict:
    """Everything the console needs to draw the picture, and to say why it cannot.

    `box` is the element's rectangle **in the page screenshot's own pixel space** — the capture
    records it as `getBoundingClientRect()` plus the scroll offset and the screenshot is
    full-page, so the two share one coordinate system and the marker needs no conversion.

    Every "missing" case answers itself. A blank `page_ref` with a stated `reason` is a screen
    whose picture could not be taken or could not be stored, and the screen says which — an
    empty frame with no explanation is the kind of silence this whole build exists against.
    """
    bundle = _bundle_for(finding)
    scan = _scan_for(finding)
    box = ((bundle.element or {}).get("box") or {}) if bundle is not None else {}
    return {
        # Which capture this picture came out of — the audit's own id on a brownfield pass, the
        # run's on a greenfield one. Returned from here rather than looked up again because the
        # row it comes off has already been fetched, and a second query for a field we are
        # holding is a second chance to disagree with it.
        "run_key": (bundle.run_key if bundle is not None else "") or (
            scan.run_key if scan is not None else "") or "",
        "page_ref": scan.page_image_ref if scan is not None else "",
        "element_ref": finding.screenshot_ref or (
            bundle.screenshot_ref if bundle is not None else ""),
        "box": {k: float(box[k]) for k in ("x", "y", "width", "height")} if box else None,
        "url": (bundle.url if bundle is not None else "") or "",
        "reason": (bundle.uncapturable_reason if bundle is not None else "") or "",
    }


# ---------------------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------------------

def _handles(criteria) -> dict[str, str]:
    """{number: handle} — "1.1.1" -> "Non-text Content", for the ones the standard holds."""
    from .models import WcagCriterion
    from .wcag import DEFAULT_VERSION

    numbers = sorted({str(c).strip() for c in criteria if str(c).strip()})
    if not numbers:
        return {}
    return dict(
        WcagCriterion.objects
        .filter(version=DEFAULT_VERSION, number__in=numbers)
        .values_list("number", "handle")
    )


def _provenance(finding) -> dict:
    """Where this finding came from — the run that saw it, and what that run was working on.

    **Null is the right answer on brownfield and must stay one.** A baseline audit partitions
    its captures by its own id and manufactures no `Run` (`findings.record_run_findings` resolves
    the key to `None` on purpose), so an audit finding has no run and no work item. There is
    genuinely nothing to link to, and the screen shows nothing rather than an empty link.

    On greenfield there is: findings are recorded against the **capture** run, not the judge's
    (`aipass.finish_ai_pass` publishes for `source_run`), and Test Automation runs one test case
    per run — so that run's work item is the test case that found this.

    `label` prefers the case's own `TC-031` over the platform's `WI-84`, because that is what a
    QA Lead recognises and what the test case document calls itself. It falls back to the work
    item key, since the source is not always a test case: a capture posted from CI is keyed to
    the project, and a finding can hang off a story.
    """
    run = finding.last_seen_run or finding.first_seen_run
    work_item = run.work_item if run is not None else None
    ref = (work_item.external_ref or {}) if work_item is not None else {}
    return {
        "source_run": str(run.id) if run is not None else None,
        "work_item_id": str(work_item.id) if work_item is not None else None,
        "work_item_label": (str(ref.get("tc_id") or "") or work_item.key
                            if work_item is not None else None),
        "work_item_title": work_item.title if work_item is not None else None,
    }


def _item(finding, *, handles, user_id, evidence=None, now=None) -> dict:
    """One finding as the console reads it — and, with `evidence`, the picture that goes with it.

    **The five evidence keys are present only when a caller asks for them**, and the only caller
    that does is `open_item` (G3b). The list does not draw a picture: the rail prints the rule,
    the page, the element, the level and the verdict, and the capture belongs to the detail
    panel, which fetches its one item separately.

    That split is the whole change. Working out the evidence costs two lookups per finding when
    the capture exists and four when it does not — the bundle and the scan each miss on the
    exact run and then fall back — so the queue was paying it for every row of every page load
    and throwing all of it away. Measured on local Postgres: **8 findings, 40 round trips**,
    where about 4 will do. The endpoint passes no limit either, so a project with two hundred
    findings waiting paid it two hundred times over.
    """
    row = _row(finding, handles=handles, user_id=user_id, now=now)
    if evidence is None:
        return row
    return row | {
        "page_image": bool(evidence["page_ref"]),
        "element_image": bool(evidence["element_ref"]),
        "box": evidence["box"],
        "url": evidence["url"],
        "capture_reason": evidence["reason"],
        "capture_key": evidence["run_key"],
    }


def _row(finding, *, handles, user_id, now=None) -> dict:
    """What is true of a finding without going and looking for its capture."""
    return {
        **_provenance(finding),
        "id": str(finding.id),
        "criterion": finding.criterion,
        "criterion_handle": handles.get(finding.criterion, ""),
        "wcag_level": finding.wcag_level,
        "route": finding.route,
        "selector": finding.selector,
        "stable_selector": finding.stable,
        "checker": finding.checker,
        # What the AI said, kept apart from how sure it was. `uncertain` means "I looked and
        # cannot tell" — it is an answer, and the screen prints it as "No verdict" rather than
        # as 0%, which would read as "the AI was 0% confident" (D-A11Y-95).
        "verdict": finding.verdict,
        "confidence": finding.confidence,
        "severity_if_confirmed": finding.severity,
        # What the platform decided, and whether it is still open. Constant across the review
        # queue — everything in it is `needs_review` and open — and the reason this shape can
        # also serve a finding opened to be read, where it is the first thing a reader needs.
        "outcome": finding.outcome,
        "status": finding.status,
        "evidence": finding.evidence,
        "suggested_fix": finding.suggested_fix,
        "lock": lock_state(finding, user_id=user_id, now=now),
    }


def queue(*, tenant_id, project_id, user_id=None, limit=None) -> list[dict]:
    """The review queue as the console renders it — worst first.

    No evidence: see `_item`. What a row costs is now flat in the number of findings, so the
    queue stays the same size of job whether a project has eight waiting or two hundred.
    """
    from .findings import review_queue

    rows = review_queue(tenant_id, project_id, limit=limit)
    if not rows:
        return []
    with tenant_context(tenant_id):
        handles = _handles([row.criterion for row in rows])
        return [_item(row, handles=handles, user_id=user_id) for row in rows]


def can_manage_pages(*, tenant_id, project_id, user_id) -> bool:
    """May this user change the audit scope — register, edit or remove pages, start an audit?

    `policy.PAGE_MANAGE_ROLES` says who, and why it is a wider list than the reviewer's. The
    tenant-admin carve-out is the same one `can_review` and `require_repo_manage_role` both
    apply: a workspace admin is not locked out of their own workspace by a missing membership.
    """
    from apps.tenancy.models import Membership, User

    from .policy import PAGE_MANAGE_ROLES

    if not user_id:
        return False
    with tenant_context(tenant_id):
        if Membership.objects.filter(
            tenant_id=tenant_id, user_id=user_id, project_id=project_id,
            role__in=list(PAGE_MANAGE_ROLES),
        ).exists():
            return True
        return User.objects.filter(
            id=user_id, tenant_id=tenant_id, is_tenant_admin=True).exists()


def ever_checked(*, tenant_id, project_id) -> bool:
    """Has anything on this project ever been checked for accessibility?

    **An empty queue means two completely different things and the screen could not tell them
    apart.** For a project that has run audits it means every check so far was sure enough to
    answer on its own — genuinely reassuring. For a project where nothing has ever run it means
    nobody has looked, and saying "every check so far was sure enough" to that reader is the
    reassurance this whole build exists to refuse.

    A screen scan OR a finding, because the two halves arrive by different roads: a captured
    page writes a scan whether or not it produced anything, and a keyboard journey writes
    findings without ever writing a scan. Either is evidence that something looked.
    """
    from .models import A11yFinding, A11yScreenScan

    with tenant_context(tenant_id):
        if A11yScreenScan.objects.filter(tenant_id=tenant_id, project_id=project_id).exists():
            return True
        return A11yFinding.objects.filter(tenant_id=tenant_id, project_id=project_id).exists()


def open_item(*, tenant_id, project_id, finding_id, user_id, take_lock=True) -> dict:
    """One item, claiming it for this reviewer (which is also how the claim is renewed).

    A reader without the reviewer role gets the item and no claim — the read-only state. They
    can see every piece of evidence; they simply cannot answer, and the screen says why rather
    than showing controls that fail on click.
    """
    from .models import A11yFinding

    with tenant_context(tenant_id):
        finding = A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=finding_id,
            # The item read renders the finding's provenance (G3); the other two fetches in this
            # module write a decision and never project it, so only this one needs the relations.
        ).select_related("last_seen_run__work_item", "first_seen_run__work_item").first()
        if finding is None:
            raise ReviewError("That finding wasn't found in this project.")

        may = can_review(tenant_id=tenant_id, project_id=project_id, user_id=user_id)
        locked_out = ""
        if take_lock and may:
            try:
                if claim(finding, user_id=user_id):
                    _event(tenant_id, "a11y.review.claimed", finding, user_id, {})
            except ReviewLockError as exc:
                locked_out = str(exc)

        handles = _handles([finding.criterion])
        # The one read that draws a picture, so the one read that pays for it (G3b).
        payload = _item(finding, handles=handles, user_id=user_id,
                        evidence=evidence_for(finding))
        payload |= {
            "can_review": may,
            "locked_out": locked_out,
            "adjudication": finding.adjudication,
            "note": finding.adjudication_note,
        }
        return payload


def _captured_by(tenant_id, project_id, capture_key: str) -> dict | None:
    """The baseline audit whose pass produced this evidence, when one did.

    A finding carries no audit of its own and must not: the ledger outlives every pass, and a
    finding first seen three audits ago is still the same problem. What identifies the pass is
    the **capture key** on the picture — `A11yCandidateBundle.run_key`, which a brownfield audit
    sets to its own id. So the audit is resolved from the evidence rather than stored beside it,
    and the answer is "the audit that took this picture", which is exactly the question a reader
    looking at the picture is asking.

    `None` on greenfield, where the key names a `Run` and there is no audit — the same shape as
    `_provenance`, and for the same reason: nothing to link to, so nothing shown.
    """
    from .models import A11yBaselineAudit

    if not capture_key:
        return None
    try:
        audit = A11yBaselineAudit.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=capture_key).first()
    except (ValidationError, ValueError):
        # A capture key that is not a uuid at all. It cannot be an audit, and a malformed
        # pointer is not worth failing a read for.
        return None
    if audit is None:
        return None
    summary = audit.summary or {}
    return {
        "id": str(audit.id),
        "label": f"audit {str(audit.id)[:8]}",
        "finished_at": audit.updated_at,
        "status": audit.status,
        "asked": int(summary.get("asked") or len(audit.routes or [])),
        "opened": int(summary.get("opened") or 0),
    }


def read_finding(*, tenant_id, project_id, finding_id, user_id=None) -> dict:
    """One finding, opened to be **read**. Nothing is claimed.

    **This is the whole of what S-39 needed that did not already exist.** The evidence, the
    picture, the element's rectangle and the provenance were all already assembled — by
    `open_item`, for the review console. What could not be reused was the side effect: opening
    an item is also what takes and renews the review claim, and a failure nobody is reviewing
    must not acquire a reviewer's name because somebody followed a link to look at it.

    So this is `open_item` with the claim off, plus the audit that took the picture. `can_review`
    is still answered honestly for this user, because the screen offers a way through to the
    console and should not offer it to someone who cannot answer.
    """
    payload = open_item(tenant_id=tenant_id, project_id=project_id, finding_id=finding_id,
                        user_id=user_id, take_lock=False)
    with tenant_context(tenant_id):
        payload["captured_by"] = _captured_by(tenant_id, project_id,
                                              payload.get("capture_key") or "")
    return payload


# ---------------------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------------------

def _event(tenant_id, action: str, finding, user_id, payload: dict) -> None:
    """Append one ledger entry. AC3 wants the two-reviewer outcome audit-logged, and this app
    had never written an Event — a decision nobody can reconstruct is not a decision."""
    from apps.ledger.models import Event

    Event.objects.create(
        tenant_id=tenant_id, actor=str(user_id or "system"), action=action,
        target_type="a11y_finding", target_id=finding.id,
        # Written straight to the column rather than resolved from the target (S.No 230): this
        # bypasses `tools.log_event`, and the finding is already loaded. A finding belongs to a
        # project, not to a work item — its run links are both nullable by design.
        project_id=finding.project_id,
        payload={"route": finding.route, "selector": finding.selector,
                 "criterion": finding.criterion, **payload},
    )


def adjudicate(*, tenant_id, project_id, finding_id, user_id, decision: str, note: str = ""):
    """Record a reviewer's answer, and make it the platform's answer.

    **Confirm flips the outcome to `failure`** (D-A11Y-98). Without that the defect loop —
    which only tickets findings whose outcome is `failure` — would raise nothing, and the
    screen's "a defect has been opened" would be untrue. A reviewer confirming *is* the finding
    becoming real.

    **Confirm also clears the confidence, and that is not tidying.** `policy.blocks` holds a
    finding back when its confidence is under the project's bar, and a confirmed finding still
    carries the AI's 41%. Left alone, a person says "yes, this is a real problem" and a
    numeric dial silently overrules them. A human judgement has no percentage; `None` is the
    same thing a rule measurement carries, and `blocks` already reads it as "no doubt to apply".

    **Reject resolves it.** Not deleted — the row and the reasoning stay in the ledger, and the
    conformance report can still show that a person looked. It simply stops being open work.

    A note is required to reject and optional to confirm, deliberately asymmetric: confirming
    agrees with evidence already written down, while rejecting overrules it and the reason is
    the only record of why.
    """
    from .models import A11yFinding

    decision = (decision or "").strip().lower()
    if decision not in DECISIONS:
        raise ReviewError("Choose whether to confirm or reject the finding.")
    note = (note or "").strip()
    if decision == REJECT and not note:
        raise ReviewError(
            "Say why this is fine. Rejecting overrules the evidence on the screen, and the note "
            "is the only record of the reason."
        )
    if not can_review(tenant_id=tenant_id, project_id=project_id, user_id=user_id):
        raise ReviewRoleError(
            "Only the accessibility reviewer (QA Lead) on this project can answer these."
        )

    with tenant_context(tenant_id):
        finding = A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=finding_id,
        ).first()
        if finding is None:
            raise ReviewError("That finding wasn't found in this project.")
        holder = lock_holder(finding)
        if holder is not None and str(holder) != str(user_id):
            state = lock_state(finding, user_id=user_id)
            raise ReviewLockError(
                f"{state['held_by_name']} is reviewing this one, so your answer was not saved. "
                f"Nothing was overwritten."
            )
        if finding.adjudication != A11yFinding.Adjudication.PENDING:
            raise ReviewError(
                f"This was already {finding.get_adjudication_display().lower()}, and a "
                f"decision is not a draft. "
                f"Nothing was changed."
            )

        confirmed = decision == CONFIRM
        finding.adjudication = (
            A11yFinding.Adjudication.CONFIRMED if confirmed
            else A11yFinding.Adjudication.REJECTED
        )
        finding.adjudicated_by_id = user_id
        finding.adjudication_note = note
        finding.adjudicated_at = timezone.now()
        # What they ruled ON, so a later run can tell "still the same element" from "different
        # element now" (B1). Blank when the finding predates the column — the ruling then
        # simply does not survive the next run, which is the conservative direction.
        finding.adjudicated_content_hash = finding.content_hash
        finding.source = A11yFinding.Source.HUMAN
        finding.confidence = None
        if confirmed:
            finding.outcome = "failure"
            finding.status = A11yFinding.Status.OPEN
        else:
            finding.outcome = "needs_review"
            finding.status = A11yFinding.Status.RESOLVED
        finding.review_locked_by_id = None
        finding.review_locked_at = None
        finding.save()

        _event(tenant_id, "a11y.finding.adjudicated", finding, user_id, {
            "decision": decision, "note": note, "outcome": finding.outcome,
            "severity": finding.severity, "was_verdict": finding.verdict,
            "content_hash": finding.adjudicated_content_hash,
        })
        return finding


# ---------------------------------------------------------------------------------------
# The picture
# ---------------------------------------------------------------------------------------

PAGE = "page"
ELEMENT = "element"


def _own_key(tenant_id, project_id, key: str) -> bool:
    """Is this object-store key one of THIS project's accessibility images?

    Checked rather than trusted. The key travels through the database and is handed to the
    object store, so this is the line between "serve a screenshot" and "serve any object whose
    key someone can get written into a row". `_image_key` builds exactly this prefix.
    """
    prefix = f"a11y/{tenant_id}/{project_id}/"
    return bool(key) and key.startswith(prefix) and ".." not in key


def screenshot(*, tenant_id, project_id, finding_id, kind: str = PAGE, object_store=None):
    """Read a finding's picture through to the caller: (bytes, content_type).

    Read-through and never persisted back onto a row (#1/#3), the same shape as the artifact
    preview. Raises `ReviewError` with a sentence a person can act on when there is no picture
    — which is a real and common state, not an error condition: a page that would not
    screenshot, an element with no rectangle, a capture over its size limit.
    """
    from .models import A11yFinding

    kind = (kind or PAGE).strip().lower()
    if kind not in (PAGE, ELEMENT):
        raise ReviewError("Choose a picture of the whole page or of one element.")

    with tenant_context(tenant_id):
        finding = A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=finding_id,
        ).first()
        if finding is None:
            raise ReviewError("That finding wasn't found in this project.")
        ev = evidence_for(finding)

    key = ev["page_ref"] if kind == PAGE else ev["element_ref"]
    if not key:
        raise ReviewError(
            ev["reason"] or (
                "no picture of this screen was kept" if kind == PAGE
                else "no picture of this element was cut"
            )
        )
    if not _own_key(tenant_id, project_id, key):
        raise ReviewError("That picture doesn't belong to this project.")

    store = object_store
    if store is None:
        from storage import s3_from_settings

        store = s3_from_settings()
    try:
        return store.get(key), "image/png"
    except Exception as exc:  # noqa: BLE001 — a missing object is a message, not a 500
        # Screen Words group 8: the storage error went to the screen; it goes to the log.
        logger.warning("Reading review picture %s failed: %s", key, exc)
        raise ReviewError("The picture couldn't be loaded. Try again; if it keeps "
                          "happening, tell your admin.") from exc
