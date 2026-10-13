"""Accessibility findings → tracked defects that close themselves (QA-14).

The platform already runs this loop twice: a failing test opens a `defect` child WorkItem and a
now-passing one closes it (`quality.services._reconcile_defects`), and a Critical/High security
finding does the same (`record_security_findings`). This is the third, and it is deliberately a
copy of the second — right down to the `external_ref` shape — because a reviewer who has read
one should not have to learn another.

**Where this lives, and why not next to its twin.** The task text says "copy
`record_security_findings`" in `apps/quality/services.py`. The pattern is copied; the file is
not, because that would make `quality` depend on `a11y` models, and every other piece of
accessibility logic (capture, ingest, scanner, triage, report, findings) already lives here.
Nothing about the loop changes by sitting in the app that owns the data it reads.

**One thing from security that must NOT be copied, and it is the whole risk of this task.**
Security closes a defect when its finding is *absent from the current list*. Copying that
literally would be a serious bug: a run covers the screens it captured, so a run that tested
`/checkout` and not `/cart` would close every accessibility defect on `/cart` as though it had
been fixed. That is the exact trap QA-12a exists to avoid. So this reconciles against the
**ledger's own status**, which already encodes "resolve by absence, but only where we looked" —
a defect closes when its finding was seen to be gone, never because a run did not visit it.

**The other difference the backlog names.** Security *drops* its non-blocking findings; only
Critical/High become work items and the rest are discarded. Accessibility cannot do that — the
uncertain ones have to stay for the SME queue. They already do, because QA-12a stores every
finding. All this module does is not open a defect for them:

    blocking      ⇒ defect + ledger row
    non-blocking  ⇒ ledger row only, and it stays in the review queue

**Its own `external_ref` key.** Test defects are keyed on `test_ref`, security on `finding`,
and these on `a11y_finding`. Three distinct keys means three reconciliations that cannot reach
into each other's rows — the test gate already scopes itself this way, and a shared key would
have let a security run quietly close every accessibility defect on the same story.

**One problem, one ticket — even when two checks found it (QA-21).** A finding's identity is
`(route, selector, criterion, checker)`, and the checker is in there for good reason: it is what
lets QA-10 grade a named check on its own record. But it also means the *same broken element*
seen by the page scanner and by the keyboard agent is two ledger rows, and left alone that is
two tickets for one fix. So this module tickets **groups**: findings are grouped on
`(route, selector, criterion)` — the identity minus the checker, which is exactly
`A11yRuleFailure.key` — and each group gets one defect. Both rows stay in the ledger, because
both are true observations and the agentic one carries the record QA-10 needs.

Where a group has a measurement in it, **the measurement owns the ticket**: the developer should
read what was proven, not what was judged, and QA-06 already says which of those wins. The other
members are listed in `external_ref.also_found_by`, and the ticket closes only when *every*
member has resolved — one check going quiet while the other still fails is not a fix.

**The honest limit of the grouping**, worth saying at review: two checks are recognised as
having found the same thing when they report the same selector. A scanner naming
`main > div.card button` and an agent naming `.card button` for one element are not grouped, and
that is the platform's identity model everywhere, not something new here.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

from .policy import blocks, default_policy, is_advisory, policy_or_default
from .selectors import normalise

#: The severities that open a defect **by default**. The same bar security uses. QA-12a derives
#: severity from the WCAG conformance level, so in practice every Level A breach (Critical) and
#: every Level AA breach (High) opens one — which is exactly the AA conformance target a project
#: commits to. Since QA-08 this is the *default*, not the rule: a project's own policy is read
#: below, and this set is what a project with no policy gets.
A11Y_BLOCKING = set(default_policy()["gate"]["block_severities"])

#: Marks these rows as ours in `external_ref`, alongside the key. Not load-bearing on its own —
#: `a11y_finding` is what scopes the query — but it is what a person reads on the work item.
DEFECT_KIND = "a11y"


#: A tag, in the word a person would use for it. Only the ones a page scanner actually offers
#: up — this is not an HTML dictionary, and anything missing falls through to the raw selector,
#: which is never wrong, only ugly.
#:
#: **Headings are named by level, and that is not decoration.** A screen reader announces
#: "heading level 2", so it is the vocabulary this product should already be speaking — and it
#: is what tells an `h1` apart from an `h2` in the same part of the page, which "heading" for
#: both did not.
_ELEMENT_WORDS = {
    "a": "link", "button": "button", "img": "image", "svg": "graphic",
    "input": "field", "select": "dropdown", "textarea": "text box", "label": "label",
    "form": "form", "fieldset": "group of fields", "legend": "group heading",
    "table": "table", "thead": "table head", "tbody": "table body", "tfoot": "table foot",
    "tr": "row", "td": "cell", "th": "heading cell", "caption": "table caption",
    "ul": "list", "ol": "numbered list", "li": "list item", "dl": "definition list",
    "h1": "level 1 heading", "h2": "level 2 heading", "h3": "level 3 heading",
    "h4": "level 4 heading", "h5": "level 5 heading", "h6": "level 6 heading",
    "nav": "navigation", "header": "page header", "footer": "page footer",
    "main": "main content", "aside": "sidebar", "section": "section", "article": "article",
    "p": "paragraph", "summary": "summary", "details": "expander", "iframe": "embedded frame",
    "video": "video", "audio": "audio", "canvas": "canvas", "dialog": "dialog",
}

#: A region of the page, in the words a person uses for it — reached either by its landmark tag
#: or by the id conventionally given to it.
#:
#: This is what tells "paragraph 1" in the main content apart from "paragraph 1" in the footer,
#: and that was most of what used to collide. Measured across 74 real findings in two tenants:
#: without regions, twelve of them shared a phrase with a sibling on the same page and rule.
_REGION_TAGS = {"main": "the main content", "footer": "the page footer",
                "header": "the page header", "nav": "the navigation",
                "aside": "the sidebar", "form": "the form", "dialog": "the dialog"}
_REGION_IDS = {"main": "the main content", "content": "the main content",
               "footer": "the page footer", "header": "the page header"}

#: Ids that are a wrapper or a landmark rather than a NAME. `#main` is where the page's content
#: goes; saying an element is "of the main" tells nobody anything, and it used to crowd out the
#: position that actually distinguished one element from its siblings. They are still used as
#: regions above — they just never win the "of the <name>" slot.
_GENERIC_IDS = set(_REGION_IDS) | {"root", "app", "wrapper", "container", "page", "body",
                                   "layout", "outer", "inner"}


def _id_of(part: str) -> str:
    """The `#id` in one segment of a selector, if it carries one."""
    if "#" not in part:
        return ""
    tail = part.split("#", 1)[1]
    for stop in (".", "[", ":", " "):
        tail = tail.split(stop, 1)[0]
    return tail.strip()


def _tag_of(part: str) -> str:
    """The tag name in one segment, without its classes, attributes or pseudo-classes."""
    return part.split(":", 1)[0].split(".", 1)[0].split("[", 1)[0].strip().lower()


def _position_of(part: str) -> str:
    """`tr:nth-of-type(2)` -> `"2"`. Empty when the segment carries no position."""
    if ":nth-of-type(" not in part:
        return ""
    n = part.split(":nth-of-type(", 1)[1].split(")", 1)[0].strip()
    return n if n.isdigit() else ""


def _readable(ident: str) -> str:
    """`loans-table` becomes `loans table` — the name a developer chose, read out loud."""
    return ident.replace("-", " ").replace("_", " ").strip()


def _element_words(selector: str) -> str:
    """The element, in words, for the one line a person reads on a board.

    **Why not just the selector.** `#loans-table > tbody > tr:nth-of-type(2)` is exactly right
    and completely unreadable, and it was the back half of every accessibility defect title in
    the platform — truncated on a board card, meaningless to anyone who does not write CSS, and
    sitting where a summary belongs.

    **The selector is not lost.** It is on the ticket under **Element**, verbatim, which is where
    somebody fixing it goes. This is the title.

    **It has to tell siblings apart, and the first version did not.** Three labels in three rows
    of one form all came out "label of the main" — three tickets on one board, one title. So the
    phrase is built from three things, in this order:

      * *what it is*, and its own position where it has one — `row 2`, `paragraph 1`;
      * *which repeat it is in*, when it has no position of its own but an ancestor does —
        `label (group 2)`. This is the part that was missing;
      * *where on the page*, preferring a thing with a real name over a region —
        `in the loans table` beats `in the main content`, which beats nothing.

    Worked through::

        #loans-table > tbody > tr:nth-of-type(2)   ->  row 2 in the loans table
        #main > form > div:nth-of-type(2) > label  ->  label (group 2) in the form
        #main > p:nth-of-type(1)                   ->  paragraph 1 in the main content
        html > body > footer > ... > p:nth-of-type(1)  ->  paragraph 1 in the page footer
        #main > h2                                 ->  level 2 heading in the main content
        #photo-interior                            ->  #photo-interior

    An element with an id of its own keeps it and stops there: `#photo-interior` is short,
    precise, and the name its own developer chose — describing it would be a downgrade.

    Falls back to the selector itself rather than to nothing: a tag this does not know is a gap
    in a list, not a failure, and a title saying less than the old one is not an improvement.

    **The honest limit.** Nothing here can *guarantee* two siblings never read the same, because
    this sees one selector and knows nothing of the others. What can be said is what was
    measured: across all 74 findings in both tenants, twelve collisions became zero.
    """
    parts = [part.strip() for part in (selector or "").split(">") if part.strip()]
    if not parts:
        return ""
    last = parts[-1]
    if ident := _id_of(last):
        # Said in words, never as `#id` (recon 2026-10-10, finding 4): a client reading a board
        # card does not read CSS. A landmark id is the region it names ("main content"); any
        # other id is quoted as the name its developer gave it. The selector itself stays on
        # the ticket under **Element**, verbatim, for whoever fixes it.
        region = _REGION_IDS.get(ident.lower())
        if region:
            return region.removeprefix("the ")
        return f'the "{ident}" element'

    noun = _ELEMENT_WORDS.get(_tag_of(last), "")
    if not noun:
        return selector

    if own := _position_of(last):
        phrase = f"{noun} {own}"
    else:
        # No position of its own — carry the nearest ancestor that has one. Without this, every
        # label in every row of a form reads the same and one board shows three of them.
        phrase = noun
        for part in reversed(parts[:-1]):
            if n := _position_of(part):
                phrase = f"{noun} ({_ELEMENT_WORDS.get(_tag_of(part), 'group')} {n})"
                break

    # A thing with a real name beats a region: "row 2 in the loans table" says more than
    # "row 2 in the main content", and only one of them is worth the words.
    for part in reversed(parts[:-1]):
        ident = _id_of(part)
        if ident and ident.lower() not in _GENERIC_IDS:
            return f"{phrase} in the {_readable(ident)}"
    for part in reversed(parts[:-1]):
        region = _REGION_IDS.get(_id_of(part).lower()) or _REGION_TAGS.get(_tag_of(part))
        if region:
            return f"{phrase} in {region}"
    return phrase


def _criterion_handles(criteria) -> dict[str, str]:
    """{number: name} for these criteria, or {} when the standard is not loaded here.

    Never raises. A ticket without the rule's name is a far smaller loss than no ticket, and an
    accessibility defect failing to open because a lookup table is missing would be absurd.
    """
    from .review import _handles

    try:
        return _handles(criteria)
    except Exception:  # noqa: BLE001 — a missing name must never cost somebody a defect
        return {}


def _page_names(tenant_id, project_id) -> dict[str, str]:
    """`{path: name}` for this project's listed pages — what a person calls each page.

    Never raises, for the same reason `_criterion_handles` does not: a missing name costs a
    title some polish, never a ticket.
    """
    from .models import A11yRoute

    try:
        with tenant_context(tenant_id):
            return {path: label for path, label in A11yRoute.objects.filter(
                tenant_id=tenant_id, project_id=project_id).exclude(label="")
                .values_list("path", "label")}
    except Exception:  # noqa: BLE001 — see docstring
        return {}


def _page_words(route: str, pages: dict[str, str] | None) -> str:
    """"the Catalogue entry page" when the page has a name; its address otherwise."""
    name = (pages or {}).get(route or "", "").strip()
    return f"the {name} page" if name else (route or "this page")


def _title(finding, handles: dict[str, str] | None = None,
           pages: dict[str, str] | None = None) -> str:
    """A defect title a person can act on without opening anything else.

    It used to read `Accessibility: 1.4.1 on /loans/current — #loans-table > tbody >
    tr:nth-of-type(2)`: the rule named by a number nobody has memorised, the element by a CSS
    path nobody can read. Both halves are now said in words, and both facts somebody navigates
    by — the criterion number and the page's address — are still in it.

    `handles` is `{number: name}`, passed in so the caller looks the standard up **once** for
    every defect it is about to open rather than once per defect. Absent, or missing this
    criterion, the title simply goes without the name: a project whose WCAG set has not been
    loaded still gets a ticket, and it still says which page and which element.
    """
    where = _element_words(finding.selector) or finding.route or "this page"
    name = (handles or {}).get(finding.criterion, "")
    rule = f"{name} ({finding.criterion})" if name else finding.criterion
    # The page by its NAME when it has one (recon 2026-10-10, finding 4) — "/staff/catalogue-entry"
    # is an address, not what anybody calls the page. The address stays on the ticket as Screen.
    return f"Accessibility: {rule} on {_page_words(finding.route, pages)} — {where}"[:512]


#: How a finding's source reads on the ticket. One phrase, used wherever the source is named, so
#: the line that opens the description and the line that lists the other finders cannot drift
#: into calling the same thing two different names.
SOURCE_WORDS = {
    "rule": "the rule scanner",
    "AI": "the AI accessibility check",
    "agentic": "the keyboard journey agent",
    "human": "a human reviewer",
}


def _source_words(source: str) -> str:
    return SOURCE_WORDS.get(source, "an accessibility check")


def _group_key(finding) -> tuple[str, str, str]:
    """What makes two findings *the same problem* for ticketing purposes.

    The finding fingerprint minus the checker — deliberately the same three parts as
    `A11yRuleFailure.key`, so "the same element failing the same criterion" means one thing
    across triage, the merge and here. Normalised on route and selector for the same reason
    `fingerprint()` normalises them: two spellings of one selector are one element.
    """
    return (normalise(finding.route), normalise(finding.selector), finding.criterion)


def _owner(members: list):
    """Which finding the ticket is written from.

    A measurement first, because QA-06 says a measurement beats an opinion and the developer
    opening the ticket should read the proof rather than the judgement. Past that, the lowest
    fingerprint — arbitrary but *stable*, so the same group produces the same ticket on every
    reconciliation instead of the description flip-flopping between two equally good rows.
    """
    measured = [m for m in members if m.source == "rule"]
    return sorted(measured or members, key=lambda f: f.fingerprint)[0]


def _first_seen(members: list):
    """The member that saw this problem first — it decides which story the defect hangs off.

    Taken across the whole group rather than from the owner, so a scanner that noticed an
    element the agent had already reported does not move the ticket to a later story. Same
    reasoning as `_parent_for`: a bug that keeps moving is a bug a developer loses.
    """
    return sorted(members, key=lambda f: (f.first_seen_run_id is None, f.created_at))[0]


def _description(finding, also: list | None = None) -> str:
    """What was found, what to change, and how sure we are — in that order.

    The suggested fix is included because a checker only produces one for a *failure* (QA-03's
    schema requires it), so on a defect it is always there and always the most useful line.

    `also` is the rest of the group (QA-21) — named on the ticket rather than left implicit,
    because "the scanner and the keyboard agent both found this" is the strongest thing that
    can be said about an accessibility defect and it would be a waste to keep it in a JSON
    field nobody reads.
    """
    level = f" (Level {finding.wcag_level})" if finding.wcag_level else ""
    # Named from the source rather than from a two-way conditional. The old form read every
    # non-scanner finding as "the AI accessibility check", which since QA-20 would have told a
    # developer a keyboard walk was a static page check.
    lines = [
        f"**WCAG 2.2 {finding.criterion}{level}** — found by {_source_words(finding.source)}.",
        "",
        f"- Screen: `{finding.route}`",
        f"- Element: `{finding.selector}`",
    ]
    if others := sorted({_source_words(m.source) for m in (also or [])}):
        lines.append(f"- Also found independently by: {', '.join(others)}")
    if finding.confidence is not None:
        lines.append(f"- Confidence: {finding.confidence:.0%}")
    if finding.rule_id:
        lines.append(f"- Scanner rule: `{finding.rule_id}`")
    if len(finding.criteria or []) > 1:
        lines.append(f"- Also breaches: {', '.join(finding.criteria[1:])}")
    if not finding.stable:
        lines.append(
            "- This element had no selector of its own, so it is identified by its position "
            "on the page. If the page is reordered this may be reported again."
        )
    lines.extend(["", "**What was found**", "", finding.evidence or "_No evidence recorded._"])
    for member in sorted(also or [], key=lambda f: f.fingerprint):
        if member.evidence and member.evidence != finding.evidence:
            lines.extend(["", f"**Also, from {_source_words(member.source)}**", "",
                          member.evidence])
    if fix := (finding.suggested_fix
               or next((m.suggested_fix for m in sorted(also or [],
                                                        key=lambda f: f.fingerprint)
                        if m.suggested_fix), "")):
        # A measurement owns the ticket but does not produce a suggested fix — only a checker
        # does. So the group's fix is borrowed from whichever member has one, rather than the
        # ticket losing the most actionable line it had by being upgraded to a proven failure.
        lines.extend(["", "**Suggested fix**", "", fix])
    return "\n".join(lines)


def _advisory_group(members: list) -> bool:
    """Whether this ticket is barred from failing a gate (QA-22).

    **Only when EVERY member is advisory**, and the "every" is the whole point. When the page
    scanner has also found this problem, the scanner's finding is a measurement of a still page
    and blocks on its own merits — the keyboard agent happening to agree cannot take that away.
    The one case that goes quiet is the one where the keyboard agent is the *only* thing that
    saw it, which is exactly the case we are not yet willing to stop a team's work over.
    """
    return all(is_advisory(member.checker) for member in members)


def _external_ref(finding, rank: dict | None = None, also: list | None = None) -> dict:
    rank = rank or {}
    return {
        "defect": f"DEF-A11Y-{finding.fingerprint[:12]}",
        # The key this reconciliation scopes on. Deliberately NOT `finding`, which is security's
        # — see the module docstring.
        "a11y_finding": finding.fingerprint,
        # The rest of the group (QA-21). A ticket is found again by ANY of these, so the same
        # defect is recognised even if a later run's owner changes — and it closes only when
        # every one of them has resolved.
        "also_found_by": sorted(m.fingerprint for m in (also or [])),
        "found_by_sources": sorted({finding.source} | {m.source for m in (also or [])}),
        # Tracked, but barred from failing a gate (QA-22). Written onto the ticket rather than
        # re-derived at the gate for the same reason `priority` is: a defect leaves the platform
        # for a client's tracker, where nothing of ours can work it out again. Recomputed on
        # every reconciliation, so a ticket the scanner later confirms stops being advisory.
        "advisory": _advisory_group([finding, *(also or [])]),
        "kind": DEFECT_KIND,
        "severity": finding.severity,
        "criterion": finding.criterion,
        "route": finding.route,
        "selector": finding.selector[:512],
        "ledger_id": str(finding.id),
        # Where this sits in the fix order, and why (QA-18). Written onto the ticket rather
        # than left as a query result because a defect leaves the platform — it reaches a task
        # tracker, where nothing of ours can re-derive it. Recomputed on every reconciliation,
        # so an item whose neighbours were fixed moves up rather than keeping a stale number.
        "priority": rank.get("priority"),
        "pages_affected": rank.get("pages_affected"),
    }


def _claimed(item) -> set[str]:
    """Every finding fingerprint a defect already speaks for — its owner and its group.

    Read from the ticket rather than recomputed, so a defect opened before grouping existed
    (owner only, no `also_found_by`) is still recognised as the ticket for its problem and is
    re-stamped rather than duplicated.
    """
    ref = item.external_ref or {}
    return {key for key in [ref.get("a11y_finding"), *(ref.get("also_found_by") or [])] if key}


def _parent_for(finding, container=None):
    """The work item a defect hangs off — where the problem was **first** seen.

    First rather than last on purpose. A finding that is still open when a second story's test
    run sees it again would otherwise migrate between stories run by run, and a developer would
    lose track of a bug that kept moving.

    With no run behind it — a baseline audit, a CI post, a direct ledger write — it hangs off
    the project's accessibility backlog instead (QA-18). Until that container existed these
    defects were parentless: still trackable, but scattered across the project with nothing
    naming them as one body of work, which is precisely what OP-08's campaign has to pick up.
    """
    run = finding.first_seen_run
    return run.work_item if run is not None else container


def record_a11y_findings(*, tenant_id, project_id, run_id=None) -> dict:
    """Open, close and reopen accessibility defects from the ledger. Never raises at the caller.

    Reconciles the **whole project's** ledger rather than one run's findings, and that is what
    makes the closing rule safe: a finding on a screen this run never visited is still `open` in
    the ledger, so its defect stays open. `run_id` is provenance for the event log only.

    Idempotent. Running it twice changes nothing the second time, and a finding that flips
    between runs reuses its own defect rather than spawning a duplicate — the fingerprint is the
    key, so "the same problem" means the same thing here as everywhere else.

    Which findings are "blocking" is the project's own policy since QA-08, and the effective
    policy is returned so a reader can see the bar this reconciliation actually applied. Raising
    the bar closes defects that no longer clear it — correct, and worth knowing: an admin
    narrowing the policy is choosing to stop tracking those, and the event log records each one.
    """
    from mcp_platform_state import tools

    from apps.workitems.models import WorkItem

    from .backlog import backlog_container, breadth_by_criterion, open_findings, ranks
    from .models import A11yFinding

    opened: list[str] = []
    closed: list[str] = []
    reopened: list[str] = []
    # The project's policy decides the bar (QA-08). `policy_or_default` never raises: a policy
    # nobody can read falls back to the documented default and hands back the reason, which is
    # returned to the caller below — a bad JSON key must not leave real failures untracked.
    policy, policy_error = policy_or_default(tenant_id, project_id)
    severities = policy["gate"]["block_severities"]
    with tenant_context(tenant_id):
        candidates = (
            A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN, outcome="failure",
                    severity__in=sorted(severities))
            .select_related("first_seen_run", "first_seen_run__work_item")
        )
        # The severity filter runs in the database because it is a plain column; the confidence
        # bar runs here because it also depends on the source — a rule-scanner measurement is
        # never held back by a confidence dial (see `policy.blocks`).
        blocking = {
            finding.fingerprint: finding
            for finding in candidates
            if blocks(policy, severity=finding.severity, confidence=finding.confidence,
                      source=finding.source)
        }
        # One ticket per problem, not per finding (QA-21). Both rows stay in the ledger; only
        # the ticketing collapses them.
        groups: dict[tuple[str, str, str], list] = {}
        for finding in blocking.values():
            groups.setdefault(_group_key(finding), []).append(finding)
        owners = {key: _owner(members) for key, members in groups.items()}
        # One lookup for every ticket this reconciliation might open, rather than one
        # per ticket. `review._handles` is the same query the review queue uses to put
        # a name beside a criterion number — reused rather than copied, so a ticket and
        # the queue can never end up calling 1.4.1 two different things.
        handles = _criterion_handles(owner.criterion for owner in owners.values())
        pages = _page_names(tenant_id, project_id)

        existing = [
            item for item in WorkItem.objects.filter(
                tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT)
            if _claimed(item)
        ]
        # Any member fingerprint finds the ticket. `setdefault` so the first item to claim a
        # fingerprint keeps it — two tickets claiming one finding would be a pre-existing
        # duplicate, and silently re-pointing it at the newer one would hide that.
        claims: dict = {}
        for item in existing:
            for key in sorted(_claimed(item)):
                claims.setdefault(key, item)

        # What to fix first (QA-18). Ranked over the **owners**, so priority numbers count
        # tickets rather than rows — a problem found twice must not take two places in the fix
        # order and push everything below it down. Breadth is still counted over every open
        # finding, which is the one definition of that number.
        rank = ranks(owners.values(),
                     breadth_by_criterion(open_findings(tenant_id, project_id)))
        # Created lazily, and only for a finding that has no run behind it — a project whose
        # accessibility work all comes from builds never grows an empty container.
        container = None

        # Close what is no longer blocking. "No longer blocking" is a statement about the
        # LEDGER — resolved, or downgraded to needs-review by a later run — or about the
        # POLICY, if an admin has since raised the bar past it. Never about this run's
        # coverage: a screen this run did not visit keeps every defect it had.
        # A grouped ticket closes only when EVERY member has stopped blocking. One of two
        # checks going quiet while the other still fails is not a fix, and closing on the
        # first one to fall silent would tell a team a live defect had been dealt with.
        for item in existing:
            mine = _claimed(item)
            # A cancelled ticket is excluded (S.No 140): "no longer blocking" would
            # otherwise close it as resolved, which is a different statement about the same
            # defect than the one the person who cancelled it made.
            if not (mine & set(blocking)) and item.state not in WorkItem.TERMINAL_STATES:
                item.state = WorkItem.State.DONE
                item.save(update_fields=["state", "updated_at"])
                tools.log_event(tenant_id, "a11y", "a11y.defect.resolved", "work_item",
                                str(item.id),
                                {"finding": (item.external_ref or {}).get("a11y_finding", ""),
                                 "findings": sorted(mine), "run": str(run_id or "")})
                closed.append(str(item.id))

        # Ordered by the owner's fingerprint, which is what `sorted(blocking)` gave before
        # grouping existed: same tickets, same order, whatever order the ledger came back in.
        taken: set = set()
        for group in sorted(groups, key=lambda g: owners[g].fingerprint):
            members = groups[group]
            finding = owners[group]
            fingerprint = finding.fingerprint
            others = [m for m in members if m.fingerprint != fingerprint]
            # Any member finds the ticket. `taken` guards the one pathological case: a defect
            # already claiming fingerprints from two different groups, which would otherwise
            # have both groups writing over each other on the same row.
            open_item = next(
                (found for member in sorted(members, key=lambda f: f.fingerprint)
                 if (found := claims.get(member.fingerprint)) is not None
                 and id(found) not in taken),
                None,
            )
            if open_item is not None:
                taken.add(id(open_item))
            if open_item is None:
                first = _first_seen(members)
                if first.first_seen_run is None and container is None:
                    container = backlog_container(tenant_id, project_id)
                created = WorkItem.objects.create(
                    tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT,
                    parent=_parent_for(first, container),
                    title=_title(finding, handles, pages),
                    description=_description(finding, others), state=WorkItem.State.IN_PROGRESS,
                    external_ref=_external_ref(finding, rank.get(fingerprint), others),
                )
                tools.log_event(tenant_id, "a11y", "a11y.defect.opened", "work_item",
                                str(created.id), {"finding": fingerprint,
                                                  "findings": sorted(m.fingerprint
                                                                     for m in members),
                                                  "severity": finding.severity,
                                                  "criterion": finding.criterion})
                opened.append(str(created.id))
            else:
                # The order changes as its neighbours are fixed, so an existing ticket is
                # restamped rather than left holding the number it was opened with — a
                # priority nobody maintains is worse than none at all. The group is restamped
                # too, so a ticket opened by one check picks up the second one that finds it.
                before = open_item.external_ref or {}
                open_item.external_ref = _external_ref(finding, rank.get(fingerprint), others)
                # The description is rewritten only when the group actually changed — a second
                # check finding the same problem, or the owner changing hands. Rewriting it on
                # every reconciliation would quietly overwrite whatever a developer had added
                # to the ticket, every time any run touched the project.
                if (before.get("a11y_finding") != fingerprint
                        or (before.get("also_found_by") or [])
                        != open_item.external_ref["also_found_by"]):
                    open_item.description = _description(finding, others)
                if open_item.state == WorkItem.State.DONE:
                    # The same problem came back. The SAME defect reopens — a second one would
                    # give a developer two tickets for one fix and lose the first's history.
                    # Its description is refreshed here whatever the group did, because the
                    # evidence is from a new sighting and the old one is now history.
                    open_item.state = WorkItem.State.IN_PROGRESS
                    open_item.description = _description(finding, others)
                    tools.log_event(tenant_id, "a11y", "a11y.defect.reopened", "work_item",
                                    str(open_item.id), {"finding": fingerprint})
                    reopened.append(str(open_item.id))
                open_item.save(update_fields=["state", "description", "external_ref",
                                              "updated_at"])

    out: dict = {"opened": opened, "closed": closed, "reopened": reopened,
                 "blocking": sorted(blocking), "policy": policy}
    if policy_error:
        out["policy_error"] = policy_error
    return out
