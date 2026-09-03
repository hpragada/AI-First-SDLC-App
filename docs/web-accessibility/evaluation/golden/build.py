"""Emit the golden set's JSON files from the authored labels below (QA-09).

INTERNAL — Edvensoft accessibility evaluation data.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

    python build.py

**Why a generator and not 99 hand-written JSON objects.** The manifest's per-criterion counts
are a hard stop in `scorer/labels.py` — a file and a count that disagree refuse to score rather
than scoring a sample nobody chose. Deriving both from one table makes that class of mistake
impossible instead of merely unlikely. The *labels* are still hand-authored: every `truth`,
`expected_verdict` and `rationale` below is written per element, not computed.

**Where the selectors come from.** `scorer/platformdata.py` joins a label to a verdict on
`(route, selector, checker)` as an exact string match with no normalisation, so a selector that
is merely equivalent still misses and the record scores as never-looked-at. Every selector here
was produced by running the companion's own `cssPath()` against the fixture at v1.3.0 rather
than written by hand — see `../harness/dump-selectors.js`.

**What is deliberately NOT done here.** Nothing in this file reads the platform's output. The
labels must be independent of the system under test; a label agreed with after seeing the
verdict is not ground truth, it is the model marking its own work.
"""
from __future__ import annotations

import json
from pathlib import Path

APP_VERSION = "1.3.0"
DATASET_VERSION = "0.1.0"
GENERATED_ON = "2026-08-26"

#: Honest provenance. QA-09 wants an expert-adjudicated verdict per record; these are a first
#: pass drafted from the fixture source for that expert to review, and the field says so rather
#: than implying a sign-off that has not happened.
LABELLED_BY = "draft-unadjudicated"

HERE = Path(__file__).parent

FILES = {
    "1.1.1": "1.1.1-non-text-content.json",
    "1.3.1": "1.3.1-info-and-relationships.json",
    "4.1.2": "4.1.2-name-role-value.json",
    "1.4.1": "1.4.1-use-of-colour.json",
    "2.5.3": "2.5.3-label-in-name.json",
}

records: list[dict] = []


def rec(criterion, route, selector, checker, truth, expected, difficulty,
        rationale, fix=None, anchor="none — judgment call, see rationale"):
    records.append({
        "criterion": criterion, "route": route, "selector": selector, "checker": checker,
        "truth": truth, "expected_verdict": expected, "difficulty": difficulty,
        "rationale": " ".join(rationale.split()),
        "expected_fix_mentions": fix or [],
        "anchor": anchor,
    })


# ══════════════════════════════════════════════════════════════════════════════════
# 1.1.1 Non-text Content — checker `alt`
# ══════════════════════════════════════════════════════════════════════════════════

# Six covers, all carrying alt="cover". The failure is not that the alt is empty — it is that
# every cover on the page announces the same word, so the list is unusable by ear.
COVERS = [
    ("#cover-tidewater", "Tidewater", "Ursula Vane"),
    ("#cover-salt-path", "The Salt Path Home", "Idris Okonkwo"),
    ("#cover-nightjar", "Nightjar", "Marta Lindqvist"),
    ("#cover-cartographer", "The Cartographer's Apprentice", "Hana Sato"),
    ("#cover-bell-bone", "Bell and Bone", "Cormac Deasy"),
    ("#cover-quiet-inventory", "A Quiet Inventory", "Priya Raghunathan"),
]
for sel, title, author in COVERS:
    rec("1.1.1", "/catalogue/new-arrivals", sel, "alt", "fail", "fail", "clear",
        f"""alt="cover" says the image is a cover and nothing about which book. This is one of
        six covers on the page and all six carry the identical string, so a screen-reader user
        hears "cover" six times and cannot tell {title} from the other five. The title is not
        adjacent in the DOM, so nothing nearby recovers it.""",
        fix=["title", "author"])
    rec("1.1.1", "/catalogue/staff-picks", sel, "alt", "pass", "pass", "clear",
        f"""The same cover, named "{title} by {author} — cover showing …". The accessible name
        identifies the specific book and describes what the artwork depicts, so the image is
        distinguishable from its five neighbours by ear alone.""")

rec("1.1.1", "/authors/featured", "#portrait-vane", "alt", "fail", "fail", "clear",
    """alt="IMG_2231.jpg" is a camera filename. It passes any rule that only checks an alt
    attribute is present and non-empty, and conveys nothing: a listener learns that a file
    exists, not that this is a photograph of the author being featured.""",
    fix=["Ursula Vane"])
rec("1.1.1", "/authors/spotlight", "#portrait-vane", "alt", "pass", "pass", "clear",
    """The same portrait, named "Ursula Vane, photographed at the 2019 festival" — it identifies
    the person and the occasion, which is what the image is on the page to convey.""")

rec("1.1.1", "/reports/borrowing-trends", "#chart-borrowing", "alt", "fail", "fail", "clear",
    """alt="chart" names the format and withholds the content. The chart is the only place the
    monthly borrowing figures appear, so a listener gets none of the data the page exists to
    present. Naming the genre of an image is not an alternative to it.""",
    fix=["loans", "month"])
rec("1.1.1", "/reports/annual-review", "#chart-borrowing", "alt", "pass", "pass", "clear",
    """The same chart, with the trend and its figures in the alt ("a rise from January to a May
    peak of 1,240, then a decline to 780 in August") and a link to the full table beneath it.
    The information in the image is available without the image.""")

rec("1.1.1", "/events/summer-reading", "#divider-summer", "alt", "fail", "fail", "clear",
    """alt="decorative divider line" describes the image instead of removing it. The rule is
    that a decorative image takes alt="" so assistive technology skips it; giving it text makes
    a screen reader announce a horizontal rule as content. The word "decorative" in an
    accessible name is itself the evidence the author knew it carried no meaning.""",
    fix=["empty", "alt"])
rec("1.1.1", "/events/book-club", "#divider-summer", "alt", "pass", "pass", "clear",
    """The same divider with alt="" and role="presentation" — correctly removed from the
    accessibility tree, so it is never announced.""")

rec("1.1.1", "/reports/lending-summary", "#chart-lending", "alt", "fail", "fail", "clear",
    """An informative chart marked decorative with alt="". This is the inverse of the usual
    error and the reason a rule engine cannot settle 1.1.1: axe is satisfied, because an empty
    alt is valid markup. The surrounding prose makes claims about loans rising and falling for
    which this chart is the only evidence, so hiding it removes information rather than noise.
    Deciding this needs somebody to look at the image and read the text around it.""",
    fix=["loans", "describe"])
rec("1.1.1", "/about/team", "#divider-team", "alt", "pass", "pass", "clear",
    """A genuinely decorative rule with alt="" and role="presentation". The twin of the
    lending-summary case: identical markup, opposite correct answer, because this image carries
    nothing the page depends on. The pair is here so a checker cannot score by preferring one
    answer for empty alt.""")

rec("1.1.1", "/catalogue/award-winners", "#cover-cartographer", "alt", "fail", "uncertain",
    "ambiguous",
    """The cover's alt repeats the figcaption immediately below it, so the title is announced
    twice in succession. Redundant text is a real harm — it doubles the length of the list
    without adding anything — but the alternative reading is that a named cover is better than
    an unnamed one, and an author could defend either. A confident verdict in either direction
    over-claims; the correct behaviour is to route this to a person. Scored as over-confidence
    if a checker answers pass or fail here.""",
    anchor="Understanding SC 1.1.1: Non-text Content — text alternatives that duplicate "
           "adjacent text")
rec("1.1.1", "/about/visit-us", "#photo-interior", "alt", "fail", "uncertain", "ambiguous",
    """alt="library" on a photograph inside a "Visit us" panel. Whether this image is
    informative (showing what the reading room looks like before you travel) or decorative
    (a mood photograph beside the address) depends on authorial intent, which is not
    recoverable from the page. One vague word is a poor alternative either way, but the right
    answer is that a person should decide.""",
    anchor="Understanding SC 1.1.1: Non-text Content — decorative vs informative images")


# ══════════════════════════════════════════════════════════════════════════════════
# 1.3.1 Info and Relationships — checkers `semantics` (one element) and `structure` (containers)
# ══════════════════════════════════════════════════════════════════════════════════

FAKE_HEADINGS = [
    ("#main > div:nth-of-type(2)", "Borrowing limits"),
    ("#sec-renewals", "Renewals"),
    ("#main > div:nth-of-type(4)", "Reservations"),
]
REAL_HEADINGS = [
    ("#main > h2:nth-of-type(1)", "Borrowing limits"),
    ("#sec-renewals", "Renewals"),
    ("#main > h2:nth-of-type(3)", "Reservations"),
]
for sel, text in FAKE_HEADINGS:
    rec("1.3.1", "/help/borrowing-guide", sel, "semantics", "fail", "fail", "clear",
        f""""{text}" is a <div class="h2"> styled to look like a heading. Sighted readers see a
        heading; the accessibility tree contains no heading at all, so the page has zero
        headings and cannot be navigated by heading — the primary way screen-reader users move
        through a long document. The visual hierarchy is real and the programmatic one is
        absent, which is exactly what 1.3.1 forbids.""",
        fix=["heading", "h2"])
for sel, text in REAL_HEADINGS:
    rec("1.3.1", "/help/getting-started", sel, "semantics", "pass", "pass", "clear",
        f""""{text}" is a real <h2>. The structure a sighted reader sees is written into the
        markup, so heading navigation works. Note this element is correctly NOT selected by the
        semantics rule — a native heading with no overriding role has real semantics and needs
        no judgment — so it is expected to score as never-looked-at rather than as a verdict.""")

rec("1.3.1", "/account/loan-history", "#history-table", "structure", "fail", "fail", "clear",
    """A table built out of <div class="grid-row">. It reads as a three-column table of loans to
    anyone who can see it, and to a screen reader it is an undifferentiated run of text with no
    column headers, no row boundaries and no count. A cell's value cannot be associated with the
    column it belongs to, so "14 March" is announced with no indication of whether it is the
    borrowed or the returned date.""",
    fix=["table", "th"])
rec("1.3.1", "/account/statements", "#history-table", "structure", "pass", "pass", "clear",
    """The same data as a real <table> with three <th scope="col"> header cells. Each value is
    programmatically associated with its column, so a screen reader announces "Returned, 14
    March" rather than a bare date.""")

rec("1.3.1", "/account/notifications", "#main > form", "structure", "fail", "fail", "clear",
    """Three radio buttons that each carry a correct individual <label>, inside a form with no
    fieldset and no legend. Every rule-level check passes: no input is unlabelled. What is
    missing is the relationship — nothing says these three options belong to one question, so a
    screen reader announces "Email, radio button, 1 of 3" with no statement of what is being
    chosen. The visible <h2> "Notify me by" supplies that to a sighted reader only.""",
    fix=["fieldset", "legend"])
rec("1.3.1", "/account/preferences", "#main > form > fieldset", "structure", "pass", "pass",
    "clear",
    """The same three radios inside a <fieldset> with a <legend>. The group has a programmatic
    name, so each option is announced in the context of the question it answers.""")

rec("1.3.1", "/catalogue/subject-index", "#subject-table", "structure", "fail", "fail", "clear",
    """A real <table> whose five header cells are <td>, styled to look like headers
    (uppercase, bold, tinted background) but carrying no <th> and no scope. The table has seven
    body rows and five columns, so a value in the fourth column is announced as a bare number
    with nothing to say it means "Available". This is the case that motivated the `structure`
    checker: the table is not pretending to be anything, so the `semantics` rule never reaches
    it, and every page of the 21 August audit was recorded as satisfying 1.3.1 with its tables
    unexamined.""",
    fix=["th", "scope"])
rec("1.3.1", "/catalogue/subject-list", "#subject-table", "structure", "pass", "pass", "clear",
    """The same table with five <th scope="col"> header cells and the same seven body rows.
    Identical to the eye, correct in the tree.""")

rec("1.3.1", "/catalogue/genres", "#genre-list", "structure", "fail", "uncertain", "ambiguous",
    """A <ul> whose items read "<b>Fiction</b> — 1,240 items". The <b> carries a
    name-versus-count distinction visually, and <b> has no semantics, so that distinction is
    absent from the tree. Whether this is a 1.3.1 failure turns on whether the boldface is
    conveying structure (a term and its definition, which would want <dl>/<dt>/<dd>) or is
    merely typographic emphasis on a list that already reads correctly in order. Both readings
    are defensible from the page alone, so the calibrated answer is uncertain.""",
    anchor="Understanding SC 1.3.1: Info and Relationships — presentation that conveys "
           "structure")


# ══════════════════════════════════════════════════════════════════════════════════
# 4.1.2 Name, Role, Value — checker `semantics`
# ══════════════════════════════════════════════════════════════════════════════════

rec("4.1.2", "/staff/catalogue-entry", "#save-entry", "semantics", "fail", "fail", "clear",
    """A <div> with an onclick handler acting as the Save button. It has no role, so it is
    announced as plain text rather than as a button; it is not in the tab order, so it cannot be
    reached by keyboard at all. The primary action of the form is unavailable to anyone not
    using a mouse.""",
    fix=["button", "role"])
rec("4.1.2", "/staff/quick-edit", "#save-entry", "semantics", "pass", "pass", "clear",
    """The same control as a real <button> with visible text. Role, name and keyboard operation
    all come free from the element. Correctly not selected by the semantics rule — a native
    control with no overriding role has real semantics — so expected to score as
    never-looked-at.""")

rec("4.1.2", "/staff/branch-settings", "#toggle-closed-branches", "semantics", "fail", "fail",
    "clear",
    """A <div> switch whose on/off state exists only as a knob position and an `is-on` class.
    No role, no accessible name, no aria-checked: the accessibility tree contains no control
    here and no state. A screen-reader user cannot discover that the setting exists, let alone
    which way it is set.""",
    fix=["role", "switch", "aria-checked"])
rec("4.1.2", "/staff/display-options", "#toggle-closed-branches", "semantics", "pass", "pass",
    "clear",
    """The same switch as a <button role="switch"> with aria-checked and an aria-labelledby
    pointing at its visible label. Role, name and value are all exposed.""")

rec("4.1.2", "/staff/reports", "#report-tabs", "semantics", "fail", "fail", "clear",
    """The tab strip container: a <div> holding three anchors, styled as a tab bar with one
    marked current. Nothing carries role="tablist", so the relationship between the strip and
    the three panels below it exists only visually. Note this element is expected to be
    never-captured for `semantics` — the div has no role, is not interactive and is not a
    heading, so the rule does not reach it. That is a coverage finding, not a model error.""",
    fix=["tablist", "role"])
TAB_LINKS = [("#report-tabs > a:nth-of-type(1)", "Loans"),
             ("#report-tabs > a:nth-of-type(2)", "Members"),
             ("#report-tabs > a:nth-of-type(3)", "Stock")]
for sel, text in TAB_LINKS:
    rec("4.1.2", "/staff/reports", sel, "semantics", "fail", "fail", "clear",
        f"""The "{text}" tab is an <a href="#panel-…"> presented as a tab. It is announced as a
        link, so its role contradicts what it looks like and how it behaves, and it exposes no
        aria-selected, so a screen-reader user cannot tell which of the three is showing.
        Expected to be never-captured: the semantics rule deliberately skips an <a> that has an
        href, because a real link with real semantics needs no judgment. Whether that skip is
        right when the link is dressed as a tab is a question for the expert.""",
        fix=["role", "tab", "aria-selected"])

rec("4.1.2", "/staff/overview", "#report-tabs", "semantics", "pass", "pass", "clear",
    """The same strip built as a real role="tablist" with an accessible name.""")
REAL_TABS = [("#tab-loans", "Loans"), ("#tab-members", "Members"), ("#tab-stock", "Stock")]
for sel, text in REAL_TABS:
    rec("4.1.2", "/staff/overview", sel, "semantics", "pass", "pass", "clear",
        f"""The "{text}" tab is a <button role="tab"> with aria-selected and aria-controls
        pointing at a real tabpanel. Role, name and state are all exposed and the relationship
        to its panel is programmatic.""")

SHELVES = [("#shelf-fiction", "Fiction"), ("#shelf-reference", "Reference"),
           ("#shelf-childrens", "Children's"), ("#shelf-local", "Local history")]
for sel, name in SHELVES:
    rec("4.1.2", "/staff/shelf-audit", sel, "semantics", "fail", "fail", "clear",
        f"""The "{name}" section switch is a <div> with an onclick handler and no role, no
        aria-checked, no aria-labelledby and no tabindex. Its visible label sits in a separate
        element that is never associated with it. Nothing about this control — that it exists,
        what it is called, whether it is on — reaches the accessibility tree, and it cannot be
        operated from the keyboard.""",
        fix=["role", "switch", "aria-checked"])
    rec("4.1.2", "/staff/shelf-settings", sel, "semantics", "pass", "pass", "clear",
        f"""The same "{name}" switch as a <button role="switch"> with aria-checked and an
        aria-labelledby resolving to its visible label.""")

rec("4.1.2", "/staff/exports", "#open-exports", "semantics", "pass", "uncertain", "ambiguous",
    """An <a class="btn" href="/reports/lending-summary"> — a link styled as a button. It
    navigates, so link is arguably the honest role and adding role="button" would be a
    downgrade that breaks Enter-vs-Space expectations. The counter-reading is that a control
    which looks like a button sets an expectation about behaviour that its role contradicts.
    The visual/semantic mismatch is real; whether it rises to a 4.1.2 failure is a judgment
    call, so the calibrated answer is uncertain rather than a confident pass.""",
    anchor="Understanding SC 4.1.2: Name, Role, Value — role must match the way a component "
           "is presented and behaves")


# ══════════════════════════════════════════════════════════════════════════════════
# 1.4.1 Use of Color — checker `color`
# ══════════════════════════════════════════════════════════════════════════════════

LOAN_ROWS = [
    ("#loans-table > tbody > tr:nth-of-type(1)", "overdue", "row-overdue"),
    ("#loans-table > tbody > tr:nth-of-type(2)", "due soon", "row-due-soon"),
    ("#loans-table > tbody > tr:nth-of-type(3)", "on loan", "row-on-loan"),
]
for sel, status, cls in LOAN_ROWS:
    rec("1.4.1", "/loans/current", sel, "color", "fail", "fail", "clear",
        f"""This row's loan status — {status} — is carried entirely by its background tint
        (.{cls}), decoded by a colour key beneath the table. The words "{status}" appear nowhere
        in the row, and the table has only two columns (Title, Due), so a reader who cannot
        distinguish the tints has no way to learn that this item is {status}. The cells inside
        the row inherit the colour rather than owning it, so the row is the only element on the
        page where this can be judged.""",
        fix=["text", "status", "column"])
    rec("1.4.1", "/loans/history", sel, "color", "pass", "pass", "clear",
        f"""The same row with a third column carrying a text badge that states the status in
        words. Colour still distinguishes the rows, but it is no longer the only thing that
        does — which is all 1.4.1 asks.""")

REQUIRED = [("#main > form > div:nth-of-type(1) > label", "Name"),
            ("#main > form > div:nth-of-type(2) > label", "Email"),
            ("#main > form > div:nth-of-type(5) > label", "Postcode")]
for sel, field_name in REQUIRED:
    rec("1.4.1", "/account/join", sel, "color", "fail", "fail", "clear",
        f"""The "{field_name}" field is marked required by rendering its label in red and
        nothing else. There is no asterisk, no "(required)" in the text, and no `required` or
        `aria-required` on the control — so the obligation is invisible to anyone who cannot
        see the colour difference, and invisible to assistive technology as well. The user
        learns the field was required when the form rejects it.""",
        fix=["required", "text"])
    rec("1.4.1", "/account/update-details", sel, "color", "pass", "pass", "clear",
        f"""The same "{field_name}" label says "required" in words and the control carries
        aria-required="true". The colour is now reinforcement rather than the sole carrier.""")

SERIES = [("#main > svg > polyline:nth-of-type(1)", "Fenner Road"),
          ("#main > svg > polyline:nth-of-type(2)", "Ashcombe"),
          ("#main > svg > polyline:nth-of-type(3)", "North Quay")]
for sel, branch in SERIES:
    rec("1.4.1", "/reports/branch-comparison", sel, "color", "fail", "fail", "clear",
        f"""The {branch} series is told apart from the other two by stroke colour alone: no
        dash pattern, no direct label on the line, and the only key is a colour legend beside
        the chart. Two of the three colours are a red and a green of similar lightness. The
        chart is otherwise correct — it carries role="img" and a full aria-label — so colour
        encoding is the single defect here. **Expected to be never-captured:** `polyline` is
        not in the companion's OFFER list, so this element is never sent to any check. That is
        a coverage gap in the platform, not a model error, and it is the reason this record
        exists.""",
        fix=["dash", "label", "pattern"])
    rec("1.4.1", "/reports/monthly-issues", sel, "color", "pass", "pass", "clear",
        f"""The same {branch} series with its own dash pattern and its name written on the line
        itself. Colour is one cue among three.""")

rec("1.4.1", "/help/report-a-problem", "#problem-detail", "color", "fail", "fail", "clear",
    """The rejected field is marked by a red border and nothing else — no aria-invalid, no
    aria-describedby, no error note in the DOM, no live region, and no change of text. A reader
    who cannot see the border colour cannot tell which of the fields the form objected to, and
    assistive technology is told nothing at all.""",
    fix=["error", "message", "aria-invalid"])
rec("1.4.1", "/help/problem-report", "#problem-detail", "color", "pass", "pass", "clear",
    """The same field with aria-invalid="true" and an aria-describedby resolving to a note that
    states the reason in words. The border colour is reinforcement.""")

RENEWALS = [("#renew-tidewater", "cannot be renewed", "ring"),
            ("#renew-nightjar", "can be renewed", "dot"),
            ("#renew-bell-bone", "can be renewed", "dot")]
for sel, meaning, shape in RENEWALS:
    rec("1.4.1", "/loans/renewals", sel, "color", "fail", "uncertain", "ambiguous",
        f"""The Renew column shows this item as a coloured {shape} meaning it {meaning}. There
        IS a second cue — the shapes differ, a ring against a filled dot — so colour is not
        strictly the only channel, which is the letter of 1.4.1. But neither shape is explained
        anywhere on the page and the indicator carries no text, so a reader who sees the
        difference still cannot decode it. Whether an unexplained second cue satisfies the
        criterion is genuinely arguable; a confident verdict either way over-claims.""",
        anchor="Understanding SC 1.4.1: Use of Color — a second visual cue must itself be "
               "understandable")


# ══════════════════════════════════════════════════════════════════════════════════
# 2.5.3 Label in Name — checker `label`
# ══════════════════════════════════════════════════════════════════════════════════

rec("2.5.3", "/catalogue/search", "#search-submit", "label", "fail", "fail", "clear",
    """The button reads "Search" and its aria-label is "Find books", which does not contain the
    word "Search". A speech-input user who says "click Search" — reading the button aloud — does
    not activate it, because the name the software matches against never contains what is
    printed on the control.""",
    fix=["Search"])
rec("2.5.3", "/catalogue/advanced-search", "#search-submit", "label", "pass", "pass", "clear",
    """The same button reads "Search" with aria-label "Search books". The accessible name
    contains the visible text, so speaking the visible label activates it.""")

rec("2.5.3", "/account/apply", "#apply-submit", "label", "fail", "fail", "clear",
    """The button reads "Join" and its aria-label is "Submit membership application" — a longer,
    more descriptive name that drops the visible word entirely. The intent is helpful and the
    effect is that the control cannot be operated by voice using the word on it.""",
    fix=["Join"])
rec("2.5.3", "/account/register", "#apply-submit", "label", "pass", "pass", "clear",
    """The same button reads "Join" with aria-label "Join the library" — the name extends the
    visible text rather than replacing it, which is the pattern 2.5.3 asks for.""")

CARDS = [("#card-renew", "Renew", "Extend the loan period on every item"),
         ("#card-pay", "Pay", "Settle outstanding charges"),
         ("#card-report", "Report", "Tell us your card is lost"),
         ("#card-freeze", "Freeze", "Suspend borrowing temporarily"),
         ("#card-replace", "Replace", "Order a new membership card"),
         ("#card-upgrade", "Upgrade", "Move to a family membership"),
         ("#card-close", "Close", "End your membership")]
CARD_PASS = {"#card-renew": "Renew all loans", "#card-pay": "Pay outstanding charges",
             "#card-report": "Report a lost card", "#card-freeze": "Freeze borrowing temporarily",
             "#card-replace": "Replace your membership card",
             "#card-upgrade": "Upgrade to a family membership",
             "#card-close": "Close your membership"}
for sel, visible, name in CARDS:
    rec("2.5.3", "/account/card-services", sel, "label", "fail", "fail", "clear",
        f"""The button reads "{visible}" and its aria-label is "{name}", which does not contain
        "{visible}". Every one of the seven buttons on this page follows the same pattern — a
        plain verb on screen, a descriptive sentence in the tree — so a voice user cannot
        operate any control on the page by reading it aloud. The rewrite is well-intentioned,
        which is what makes it a good test: nothing about it looks like a bug.""",
        fix=[visible])
    rec("2.5.3", "/account/card-options", sel, "label", "pass", "pass", "clear",
        f"""The same button reads "{visible}" with aria-label "{CARD_PASS[sel]}" — the name
        keeps the visible word and adds context around it.""")

rec("2.5.3", "/newsletter", "#newsletter-email", "label", "pass", "pass", "ambiguous",
    """**Disputed — flagged for the expert.** The fixture files this under 2.5.3 as "a field
    whose only label is its placeholder", but on the criterion's own terms 2.5.3 is satisfied
    here: the visible text is the placeholder "Email" and the accessible name computed from
    that placeholder is "Email", so the name does contain the visible label. The real defects on
    this element are 3.3.2 (no persistent label — the text vanishes as soon as the user types)
    and arguably 4.1.2. It is also expected to be never-captured, because the label rule skips a
    control with no visible text and an <input type="email"> has none. Recorded as a pass under
    2.5.3 rather than deleted, so the disagreement is visible and can be adjudicated.""",
    anchor="Understanding SC 2.5.3: Label in Name — applies to components whose labels include "
           "text; see also SC 3.3.2")

rec("2.5.3", "/account/my-loans", "#renew-all", "label", "pass", "uncertain", "ambiguous",
    """The button reads "Renew" and its aria-label is "Renew all loans". The name contains the
    visible text, so the letter of 2.5.3 is met and a voice command matches. But the name widens
    the scope the visible text promised — "Renew" on its own does not tell a sighted user that
    pressing it renews every item — so the two audiences are told different things about what
    the control does. That is a real problem and it is not the one 2.5.3 measures. Uncertain is
    the calibrated answer.""",
    anchor="Understanding SC 2.5.3: Label in Name — the name must contain, and should begin "
           "with, the visible text")


# ══════════════════════════════════════════════════════════════════════════════════
# emit
# ══════════════════════════════════════════════════════════════════════════════════

def main() -> None:
    counts: dict[str, int] = {}
    by_criterion: dict[str, list[dict]] = {c: [] for c in FILES}

    for record in records:
        criterion = record["criterion"]
        counts[criterion] = counts.get(criterion, 0) + 1
        number = counts[criterion]
        flat = criterion.replace(".", "")
        by_criterion[criterion].append({
            "id": f"g-{flat}-{number:04d}",
            "app_version": APP_VERSION,
            "route": record["route"],
            "selector": record["selector"],
            "checker": record["checker"],
            "criterion": criterion,
            "truth": record["truth"],
            "expected_verdict": record["expected_verdict"],
            "difficulty": record["difficulty"],
            "rationale": record["rationale"],
            "expected_fix_mentions": record["expected_fix_mentions"],
            "labelled_by": LABELLED_BY,
            "labelled_on": GENERATED_ON,
            "relabel_verdict": None,
            "relabel_on": None,
            "adjudication": None,
            "anchor": record["anchor"],
        })

    for criterion, filename in FILES.items():
        path = HERE / filename
        path.write_text(
            json.dumps(by_criterion[criterion], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        print(f"  {filename:38} {len(by_criterion[criterion]):3} records")

    manifest = {
        "dataset_version": DATASET_VERSION,
        "app_version": APP_VERSION,
        "generated_on": GENERATED_ON,
        "counts": counts,
        "relabel_agreement": None,
        "notes": (
            "INTERNAL — Edvensoft accessibility evaluation data. Not a tenant feature. Must "
            "never be read by tenant-facing code or written to tenant tables. "
            "v0.1 is for proving the harness only — DO NOT PUBLISH THESE NUMBERS and do not "
            "gate on them (GOLDEN_DATASET_SPEC §5). Every verdict is an unadjudicated draft "
            "awaiting expert review; `labelled_by` says so on every record. No blind re-label "
            "round has been run, so `relabel_agreement` is null. Single-labeller dataset — see "
            "GOLDEN_DATASET_SPEC §6 for the limitation that inherits."
        ),
    }
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    total = sum(counts.values())
    print(f"  {'manifest.json':38} {total:3} records total")
    for criterion in FILES:
        rows = by_criterion[criterion]
        fails = sum(1 for r in rows if r["truth"] == "fail")
        passes = sum(1 for r in rows if r["truth"] == "pass")
        amb = sum(1 for r in rows if r["difficulty"] == "ambiguous")
        print(f"    {criterion}  {len(rows):3} = {fails:2} fail / {passes:2} pass "
              f"({amb} ambiguous)")


if __name__ == "__main__":
    main()
