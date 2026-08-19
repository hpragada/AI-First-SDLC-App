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

from datetime import timedelta

from django.utils import timezone

from apps.tenancy.context import tenant_context

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
    """One queue row. `evidence` is passed in for the list (one query pass) or computed here."""
    ev = evidence if evidence is not None else evidence_for(finding)
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
        "evidence": finding.evidence,
        "suggested_fix": finding.suggested_fix,
        "page_image": bool(ev["page_ref"]),
        "element_image": bool(ev["element_ref"]),
        "box": ev["box"],
        "url": ev["url"],
        "capture_reason": ev["reason"],
        "lock": lock_state(finding, user_id=user_id, now=now),
    }


def queue(*, tenant_id, project_id, user_id=None, limit=None) -> list[dict]:
    """The review queue as the console renders it — worst first, evidence attached."""
    from .findings import review_queue

    rows = review_queue(tenant_id, project_id, limit=limit)
    if not rows:
        return []
    with tenant_context(tenant_id):
        handles = _handles([row.criterion for row in rows])
        return [_item(row, handles=handles, user_id=user_id) for row in rows]


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
            raise ReviewError("no such finding on this project")

        may = can_review(tenant_id=tenant_id, project_id=project_id, user_id=user_id)
        locked_out = ""
        if take_lock and may:
            try:
                if claim(finding, user_id=user_id):
                    _event(tenant_id, "a11y.review.claimed", finding, user_id, {})
            except ReviewLockError as exc:
                locked_out = str(exc)

        handles = _handles([finding.criterion])
        payload = _item(finding, handles=handles, user_id=user_id)
        payload |= {
            "can_review": may,
            "locked_out": locked_out,
            "adjudication": finding.adjudication,
            "note": finding.adjudication_note,
        }
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
        raise ReviewError(f"decision must be one of {DECISIONS}, not {decision!r}")
    note = (note or "").strip()
    if decision == REJECT and not note:
        raise ReviewError(
            "say why this is fine. Rejecting overrules the evidence on the screen, and the note "
            "is the only record of the reason."
        )
    if not can_review(tenant_id=tenant_id, project_id=project_id, user_id=user_id):
        raise ReviewRoleError(
            "only the accessibility reviewer (QA Lead) on this project can answer these."
        )

    with tenant_context(tenant_id):
        finding = A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=finding_id,
        ).first()
        if finding is None:
            raise ReviewError("no such finding on this project")
        holder = lock_holder(finding)
        if holder is not None and str(holder) != str(user_id):
            state = lock_state(finding, user_id=user_id)
            raise ReviewLockError(
                f"{state['held_by_name']} is reviewing this one, so your answer was not saved. "
                f"Nothing was overwritten."
            )
        if finding.adjudication != A11yFinding.Adjudication.PENDING:
            raise ReviewError(
                f"this was already {finding.adjudication} and a decision is not a draft. "
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
        raise ReviewError(f"kind must be {PAGE!r} or {ELEMENT!r}, not {kind!r}")

    with tenant_context(tenant_id):
        finding = A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id, id=finding_id,
        ).first()
        if finding is None:
            raise ReviewError("no such finding on this project")
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
        raise ReviewError("that image does not belong to this project")

    store = object_store
    if store is None:
        from storage import s3_from_settings

        store = s3_from_settings()
    try:
        return store.get(key), "image/png"
    except Exception as exc:  # noqa: BLE001 — a missing object is a message, not a 500
        raise ReviewError(f"the picture could not be read from storage ({exc})") from exc
