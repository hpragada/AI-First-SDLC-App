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

#: The fixture these labels were written against. v1.4.0 added sixteen pages and changed
#: none, so every v0.1.0 record still names the element it named at v1.3.0 — provable with
#: `git diff --stat`, which shows no existing view modified.
APP_VERSION = "1.4.0"
DATASET_VERSION = "0.2.0"

#: When these files were last written. Not the same thing as when a record was labelled.
GENERATED_ON = "2026-08-28"

#: The two authoring passes. Kept apart because `labelled_on` is provenance: rewriting the
#: first pass's date to today would quietly claim 99 records were reviewed on a day nobody
#: looked at them, and provenance that moves when a file is regenerated is not provenance.
FIRST_PASS_ON = "2026-08-26"        # the 99 records of v0.1.0
SECOND_PASS_ON = "2026-08-28"       # the 74 added for v0.2.0

#: Which pass the records below belong to. Flipped once, immediately before the v0.2.0 block.
#:
#: `LABELLED_AGAINST` is the app version a record was actually authored against, and it is NOT
#: the manifest's `app_version`. Only the manifest's is read — `labels.check_app_version` gates
#: on it — so the per-record field is free to stay truthful. The 99 records of v0.1.0 were
#: written against v1.3.0 and re-verified against v1.4.0; they did not become v1.4.0 records
#: because a later pass regenerated the file.
LABELLED_ON = FIRST_PASS_ON
LABELLED_AGAINST = "1.3.0"

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

#: How many candidates each completeness page is known to hold, counted by hand from the page
#: source (PROVING_GROUND_APP_SPEC §9). `scorer/run.py` reads this to check the FIRST of the two
#: transitions a run makes — expected -> captured -> judged. Without it only the second half is
#: checked, and the report says so.
#:
#: **It lives here and not in the app**, for the same reason no route names its own defect: a
#: page that advertises how many problems it holds tells the judge the answer. It is also not
#: derived from the DOM by the same selector list the companion uses — a count produced by the
#: capturing code could never disagree with it, so the check would always pass and prove
#: nothing. A person counts them; that is the whole point.
#:
#: `harness/count-candidates.js` asserts the same five numbers against the running app. The two
#: agreeing is itself a check, so keep them in step.
EXPECTED_CANDIDATES = {
    "/catalogue/browse-all": 12,     # images
    "/staff/bulk-actions": 20,       # interactive controls
    "/account/full-profile": 15,     # labelled form controls
    "/branches": 8,                  # colour-coded indicators
    "/about/terms": 0,               # text only — a clean no-op, not an error

    # The sixteen pages added for v0.2.0, counted by hand from what was placed on each one.
    #
    # **These are lower bounds, and the check they feed is coarser than it looks.**
    # `completeness.py` compares this number against how many (element, checker) claims the run
    # produced for the route — which counts everything on the page, not only what was planted.
    # So a page holding five photographs will report a surplus, that surplus is documented as
    # not a failure, and the number only ever fires when capture on the route collapses.
    # The sharp per-element version of this check is `harness/verify-selectable.js`, which
    # asserts that each individual labelled element is still claimed by its own checker.
    #
    # These sixteen are deliberately NOT added to `harness/count-candidates.js` the way the five
    # above are. Those five are instrumentation pages with no twin, so a total counted from the
    # rendered DOM is the only fixture-side check they can have. These sixteen are twin pairs,
    # and `verify-plants.js` already asserts their exact contents element by element — which is
    # strictly stronger than a total. A second copy of the totals would be one more thing to keep
    # in step and would check nothing new.
    "/about/reading-rooms": 5,          # photographs
    "/about/our-buildings": 5,
    "/account/charges": 6,              # colour-coded amounts
    "/account/statement-of-fees": 6,
    "/account/membership-tools": 11,    # controls with an accessible name
    "/help/membership-actions": 11,
    "/catalogue/saved-searches": 3,     # controls built from spans
    "/catalogue/my-searches": 3,
    "/reports/stock-levels": 3,         # containers
    "/reports/holdings-by-branch": 3,
    "/reports/issue-figures": 3,
    "/reports/loan-figures": 3,
    "/staff/rota": 3,
    "/staff/staffing-plan": 3,
    "/events/workshops": 3,
    "/events/classes": 3,
}


def rec(criterion, route, selector, checker, truth, expected, difficulty,
        rationale, fix=None, anchor="none — judgment call, see rationale"):
    records.append({
        "criterion": criterion, "route": route, "selector": selector, "checker": checker,
        "truth": truth, "expected_verdict": expected, "difficulty": difficulty,
        "rationale": " ".join(rationale.split()),
        "expected_fix_mentions": fix or [],
        "anchor": anchor,
        "labelled_on": LABELLED_ON,
        "labelled_against": LABELLED_AGAINST,
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


LABELLED_ON = SECOND_PASS_ON
LABELLED_AGAINST = "1.4.0"

# ══════════════════════════════════════════════════════════════════════════════════
# v0.2.0 — 74 records added 2026-08-28, so that every checker reaches a scored sample
# ══════════════════════════════════════════════════════════════════════════════════
#
# **Why these exist.** At v0.1.0 not one checker could produce a number. `accuracy.py` refuses
# to call a checker measured below 30 scored records, and the ceilings were: alt 20, color 19,
# label 9, semantics 25, structure 6. More audits would not have moved any of them — the answer
# key simply did not hold enough records.
#
# **The ceiling is not the record count, and that is the trap.** A record only reaches
# `Score.sample` if `accuracy._record` puts it there, and the rules are asymmetric:
#
#     expected `fail`       always counts — as a true positive if found, a false negative if not
#     expected `pass`       counts ONLY if the checker actually SELECTS the element
#     expected `uncertain`  never counts; it is scored on calibration instead
#
# So a `pass` twin the selection rules skip is a record that can never score. That is why
# `label` sat at 9 rather than 19: all ten of its pass twins name a control whose accessible
# name already contains its visible text, and `_applies_label` skips exactly those, correctly —
# the criterion is met as a matter of fact and there is nothing left to judge. A balanced answer
# key was producing a completely unbalanced scored sample and nothing said so.
#
# **Every one of the 74 elements below was checked against the platform's real selection rules
# before its label was written** — captured from the running fixture in the companion's own
# shape, then run through `rules.checkers_for()`. All 74 are claimed by the checker named here,
# including all 37 pass records. `harness/verify-selectable.js` re-runs that check.
#
# **What is deliberately not here.** No `uncertain` records and no `ambiguous` tier: those are
# where a single labeller's judgment is worth least, and the spec says to author them with the
# expert present. Nothing for `graphics` / 1.4.11 — see "Not covered, and how to add it" in
# README.md; the short version is that whoever wrote that checker must not write its answer key.
#
# **Citations.** Every defect below names a published WCAG technique, checked against the live
# W3C document on 2026-08-28 rather than recalled. Where no failure technique covers the case —
# there is none for "built a table out of divs" — the record cites the sufficient technique it
# fails to meet and says so in as many words. The 99 records above mostly carry the default
# anchor; that is the dev's convention and the README's item 3 asks the expert to strengthen
# them, so the newer records simply start where that request points.

F30 = ("F30: Failure of Success Criterion 1.1.1 and 1.2.1 due to using text alternatives that "
       "are not alternatives (e.g., filenames or placeholder text)")
F59 = ("F59: Failure of Success Criterion 4.1.2 due to using script to make div or span a user "
       "interface control in HTML without providing a role for the control")
F91 = "F91: Failure of Success Criterion 1.3.1 for not correctly marking up table headers"
F92 = ("F92: Failure of Success Criterion 1.3.1 due to the use of role presentation on content "
       "which conveys semantic information")
F96 = "F96: Failure due to the accessible name not containing the visible label text"
G14 = ("G14: Ensuring that information conveyed by color differences is also available in text "
       "(sufficient technique for SC 1.4.1)")
H48 = ("H48: Using ol, ul and dl for lists or groups of links (sufficient technique for "
       "SC 1.3.1)")
H51 = ("H51: Using table markup to present tabular information (sufficient technique for "
       "SC 1.3.1)")
ACT_LABEL = ("ACT rule 2ee8b8 'Visible label is part of accessible name' — its label-in-name "
             "algorithm normalises case and whitespace and treats punctuation as a separator")


# ── 1.1.1 Non-text Content · checker `alt` · +10 ──────────────────────────────────
#
# Five photographs of rooms, each given a word that names the format instead of describing the
# picture. The page's prose gives the floor and the staffed hours and never says what any room
# looks like, so the image is the only place that information exists — which is what makes the
# placeholder a clear failure rather than a thin-but-survivable name.

ROOMS = [
    ("#room-local-history", "local history room", "photo",
     "wide oak map cabinets along two walls, a framed county map above them and a globe on a "
     "wooden stand"),
    ("#room-childrens", "children's corner", "image",
     "a round patterned rug with floor cushions on it, shelves at child height on either side "
     "and paper bunting across the ceiling"),
    ("#room-carrels", "study carrels", "picture",
     "four desks divided by shoulder-height partitions, each with its own reading lamp"),
    ("#room-newspapers", "newspaper lounge", "graphic",
     "two armchairs facing a low table, with a tall rack of newspapers on poles beside them"),
    ("#room-terrace", "garden terrace", "photograph",
     "a paved terrace with two wooden benches, planters at either end and a low brick wall "
     "behind"),
]
for sel, room, placeholder, shows in ROOMS:
    rec("1.1.1", "/about/reading-rooms", sel, "alt", "fail", "fail", "clear",
        f"""The photograph of the {room} is named "{placeholder}". That names the format and
        withholds everything else: a listener learns an image is present and nothing about what
        is in it. The picture shows {shows}, and none of that appears anywhere else — the
        surrounding text gives the floor and the staffed hours only. All five photographs on
        this page follow the same pattern, so the page is a list of five rooms that cannot be
        told apart by ear. An alt attribute is present and non-empty, so nothing that only
        checks for presence has anything to report.""",
        fix=[room, "describe"], anchor=F30)
    rec("1.1.1", "/about/our-buildings", sel, "alt", "pass", "pass", "clear",
        f"""The same photograph of the {room}, named by what it shows: {shows}. A listener
        learns what the room is like without seeing it, which is what the image is on the page
        to convey.""")


# ── 1.4.1 Use of Color · checker `color` · +12 ─────────────────────────────────────
#
# Whether a charge is still owed or already settled is carried by the colour of the amount and
# by nothing else. Measured on the rendered page: the red is 5.44:1 on white and the green
# 5.13:1, so both are comfortably legible and 1.4.3 is not in play — but their relative
# luminances are 0.143 and 0.155, near enough identical, so a reader who cannot separate red
# from green sees six amounts in the same grey.
#
# No failure technique fits. F81 covers required and error fields; F73 covers links. Neither is
# an amount in a statement, so the citation is the sufficient technique this fails to meet.

FEES = [("#fee-1", "4.20", "still owed", "red"), ("#fee-2", "3.00", "settled", "green"),
        ("#fee-3", "1.80", "still owed", "red"), ("#fee-4", "2.50", "settled", "green"),
        ("#fee-5", "0.90", "still owed", "red"), ("#fee-6", "1.20", "settled", "green")]
for sel, amount, state, colour in FEES:
    rec("1.4.1", "/account/charges", sel, "color", "fail", "fail", "clear",
        f"""This charge of GBP {amount} is {state}, and the only thing on the page that says so
        is that the amount is printed in {colour}. The line carries the date, the title and the
        reason; it does not carry the state. A key beneath the list explains that red means
        owed and green means settled, which helps only a reader who can already tell the two
        apart — a colour key is still colour. Measured as rendered: the two colours differ in
        hue and are all but identical in lightness, so they do not separate in greyscale
        either.""",
        fix=["text", "owed", "settled"], anchor=G14 + " — not met")
    rec("1.4.1", "/account/statement-of-fees", sel, "color", "pass", "pass", "clear",
        f"""The same GBP {amount} in the same {colour}, with the word "{state.split()[-1]}"
        written beside it. The colour still distinguishes the lines and is no longer the only
        thing that does, which is all 1.4.1 asks.""",
        anchor=G14 + " — met")


# ── 2.5.3 Label in Name · checker `label` · +22 ────────────────────────────────────
#
# Eleven controls whose visible text is identical on both pages; only the accessible name
# differs. On the defect page each name is a well-meant rewrite that drops the words printed on
# the control, so a speech-input user reading the button aloud activates nothing.
#
# **The pass side needed care, and the first attempt was wrong.** For a pass record to score at
# all, `_applies_label` has to select the element — and it only selects when the visible text is
# NOT already contained in the name. So a pass twin has to be a case where the two strings
# genuinely differ and the criterion is still met. The first design used a parenthetical
# ("Pay (3 charges)" named "Pay"): the ACT rule's algorithm strips parenthesised text and passes
# it, and axe-core 4.13.0 does not strip it and flags it. Two authoritative implementations
# disagreeing is the definition of an unclear case, so it was replaced.
#
# What is here instead is the family both agree on: the visible label carries a typographic
# mark — a trailing ellipsis, or a spaced em dash — and the name is the same words without it.
# Verified in both directions: axe reports all eleven controls on the defect page and none on
# the twin, and the ACT algorithm agrees on all twenty-two.
#
# **These eleven pass records no longer score, and that is the correct outcome.** Building them
# exposed why: `_applies_label` was comparing the two strings letter by letter, so a trailing
# ellipsis was enough to make it think the strings differed and ask the judge. Compared the way
# the criterion is actually written — whole words, punctuation as a separator — these controls
# are provably fine and there is nothing to judge, so the rule now skips them.
#
# The same comparison was also hiding real failures: a button reading "Search" named "Research
# tools" was treated as satisfying the criterion, because the letters of *search* sit inside
# *research*. Fixed on 2026-08-28 (RESEARCH_CORRECTIONS R21), which cost `label` ten of the
# thirty records it needs and bought back every failure of that shape.
#
# **The records are kept rather than deleted.** They are honest pass labels on elements the
# platform correctly declines, `accuracy.py` excludes them from every figure, and they document
# why 2.5.3 cannot have a balanced sample. If someone ever reverts the comparison to letters,
# `verify-selectable.js` will show `label` climbing back to 31 and these eleven leaving the
# inert list — which is the signal that something went backwards.

ACTIONS = [
    ("#act-pay", "Pay charges...", "Settle outstanding balance", "Pay charges"),
    ("#act-renew", "Renew - all items", "Extend the loan period", "Renew all items"),
    ("#act-collect", "Collect holds...", "Pick up reservations", "Collect holds"),
    ("#act-return", "Return an item...", "Bring something back", "Return an item"),
    ("#act-transfer", "Transfer - to another branch", "Move titles between sites",
     "Transfer to another branch"),
    ("#act-cancel", "Cancel - outstanding requests", "Withdraw what is queued",
     "Cancel outstanding requests"),
    ("#act-receipt", "Print receipt...", "Send a copy of the statement", "Print receipt"),
    ("#act-update", "Update details...", "Change your contact information", "Update details"),
    ("#act-remind", "Set reminders...", "Configure notification settings", "Set reminders"),
    ("#act-replace", "Order a replacement card...", "Request a new membership card",
     "Order a replacement card"),
    ("#act-holds", "Manage holds...", "Review your reservations", "Manage holds"),
]
for sel, visible, bad_name, good_name in ACTIONS:
    rec("2.5.3", "/account/membership-tools", sel, "label", "fail", "fail", "clear",
        f"""The control reads "{visible}" and its accessible name is "{bad_name}", which
        contains none of the words printed on it. Somebody saying "click {visible.rstrip('.')}"
        — reading the control aloud, which is the whole way speech input is used — matches
        nothing, because the name the software compares against never contains what is on
        screen. All eleven controls on this page are rewritten the same way, so no control on
        the page can be operated by voice. The rewrites are more descriptive than the labels,
        which is what makes this worth testing: nothing about the page looks like a mistake.""",
        fix=[good_name.split()[0]], anchor=F96)
    rec("2.5.3", "/help/membership-actions", sel, "label", "pass", "pass", "clear",
        f"""The same control reading "{visible}", named "{good_name}" — the same words without
        the typographic mark. The two strings are not equal, which is why this element is still
        offered for judgment, but the criterion is met: the label-in-name comparison treats
        punctuation as a separator, so the visible text is present in the name as whole words
        and speaking the label activates the control. Confirmed against axe-core 4.13.0, which
        reports nothing on this page and all eleven on its twin.""",
        anchor=ACT_LABEL)


# ── 4.1.2 Name, Role, Value · checker `semantics` · +6 ─────────────────────────────

SEARCHES = [("#drop-search-1", "crime fiction"), ("#drop-search-2", "local history"),
            ("#drop-search-3", "picture books")]
for sel, which in SEARCHES:
    rec("4.1.2", "/catalogue/saved-searches", sel, "semantics", "fail", "fail", "clear",
        f"""The control that removes the saved {which} search is a <span> with a click handler
        and nothing else. It has no role, so it is announced as ordinary text rather than as a
        control; it has no tabindex, so it is not in the tab order and cannot be reached from
        the keyboard at all. Three of them sit on this page, one per saved search, and as far
        as the accessibility tree is concerned not one of them exists. The only way to delete a
        saved search is with a mouse.""",
        fix=["role", "button", "tabindex"], anchor=F59)
    rec("4.1.2", "/catalogue/my-searches", sel, "semantics", "pass", "pass", "clear",
        f"""The same control for the {which} search, built as a <span role="button"
        tabindex="0"> with a key handler for Enter and Space. The role is announced, its visible
        text supplies the name, and it can be operated without a mouse. Note the role is what
        keeps this element in scope: a native <button> here would have real semantics, the rule
        would correctly decline to judge it, and the record could never score.""")


# ── 1.3.1 Info and Relationships · checker `structure` · +24 ───────────────────────
#
# `structure` was the thinnest checker in the set — six records against twenty-plus for the
# others — because it shares 1.3.1 with `semantics` and got what was left. It judges containers,
# so its records come from tables and lists rather than from single controls. Four kinds of
# container failure, three instances of each.

STOCK = [("#stock-fiction", "literary fiction"), ("#stock-reference", "reference"),
         ("#stock-childrens", "children's")]
for sel, subject in STOCK:
    rec("1.3.1", "/reports/stock-levels", sel, "structure", "fail", "fail", "clear",
        f"""The {subject} stock figures are a three-column table built out of <div> elements. A
        sighted reader sees a heading row and five branch rows; a screen reader gets an
        undifferentiated run of text with no column headers, no row boundaries and no count of
        rows. "412" is announced as a bare number with nothing to say whether it is copies held
        or copies on loan, and the reader has no way to know how far down the table they are.
        Nothing in the markup contradicts itself, so no rule engine has anything to report —
        the structure is simply absent.""",
        fix=["table", "th", "scope"], anchor=H51 + " — not met")
    rec("1.3.1", "/reports/holdings-by-branch", sel, "structure", "pass", "pass", "clear",
        f"""The same {subject} figures as a real <table> with three <th scope="col"> header
        cells and the same five body rows. Every value is programmatically associated with its
        column, so a cell is announced as "On loan, 96" rather than as "96".""",
        anchor=H51 + " — met")

QUARTERS = [("#issues-q1", "January to March"), ("#issues-q2", "April to June"),
            ("#issues-q3", "July to September")]
for sel, quarter in QUARTERS:
    rec("1.3.1", "/reports/issue-figures", sel, "structure", "fail", "fail", "clear",
        f"""The {quarter} table is a real four-column <table> whose heading cells are <td>
        styled to look like headings — uppercase, bold, tinted background. It has three body
        rows and four columns, so a figure in the third column is announced as a bare number
        with nothing to say it means "Renewals". This is the shape of failure the `structure`
        checker was added for: the table is not pretending to be anything else, so `semantics`
        never reaches it, and the page would otherwise be recorded as satisfying 1.3.1 with its
        tables unexamined.""",
        fix=["th", "scope"], anchor=F91)
    rec("1.3.1", "/reports/loan-figures", sel, "structure", "pass", "pass", "clear",
        f"""The same {quarter} table with four <th scope="col"> header cells and the same three
        body rows. Identical to the eye, correct in the tree.""",
        anchor=H51 + " — met")

ROTA = [("#rota-week-1", "3 August"), ("#rota-week-2", "10 August"),
        ("#rota-week-3", "17 August")]
for sel, week in ROTA:
    rec("1.3.1", "/staff/rota", sel, "structure", "fail", "fail", "clear",
        f"""The rota for the week beginning {week} is marked up correctly — a <table> with four
        <th scope="col"> header cells — and then carries role="presentation", which throws all
        of it away. The role propagates to the rows and cells, so a screen reader announces a
        run of names with no shifts, no branches and no table at all. This is the case where
        the author did the work and cancelled it in one attribute, and it is deliberately not
        skipped: role="presentation" is a claim that the content carries no structure, and
        whether that claim is true is the whole question 1.3.1 asks.""",
        fix=["presentation", "role", "remove"], anchor=F92)
    rec("1.3.1", "/staff/staffing-plan", sel, "structure", "pass", "pass", "clear",
        f"""The same rota for the week beginning {week}, without the role. The header cells it
        already carried are exposed, and each name is announced with its shift and its
        branch.""")

TERMS = [("#workshops-spring", "spring"), ("#workshops-summer", "summer"),
         ("#workshops-autumn", "autumn")]
for sel, term in TERMS:
    rec("1.3.1", "/events/workshops", sel, "structure", "fail", "fail", "clear",
        f"""The {term} workshops are a list built out of <div> elements, each line beginning
        with a bullet character. The bullet is text, not list markup, so a screen reader
        announces five separate runs of text with no count, no start and no end. "List, five
        items" is what is missing, and it is what a listener uses to decide whether to skip the
        section or read it — a decision a sighted reader makes in a glance from the shape of
        the page.""",
        fix=["ul", "li", "list"], anchor=H48 + " — not met")
    rec("1.3.1", "/events/classes", sel, "structure", "pass", "pass", "clear",
        f"""The same five {term} workshops as a real <ul> with five <li>. The count and the
        boundaries come free from the markup.""",
        anchor=H48 + " — met")


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
            "app_version": record["labelled_against"],
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
            "labelled_on": record["labelled_on"],
            "relabel_verdict": None,
            "relabel_on": None,
            "adjudication": None,
            "anchor": record["anchor"],
        })

    for criterion, filename in FILES.items():
        path = HERE / filename
        # newline="\n" so a run on Windows does not rewrite all five files with CRLF and
        # show every record as changed when not one label moved.
        path.write_text(
            json.dumps(by_criterion[criterion], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")
        print(f"  {filename:38} {len(by_criterion[criterion]):3} records")

    manifest = {
        "dataset_version": DATASET_VERSION,
        "app_version": APP_VERSION,
        "generated_on": GENERATED_ON,
        "counts": counts,
        "expected_candidates": EXPECTED_CANDIDATES,
        "relabel_agreement": None,
        "notes": (
            "INTERNAL — Edvensoft accessibility evaluation data. Not a tenant feature. Must "
            "never be read by tenant-facing code or written to tenant tables. "
            "v0.2 is still for proving the harness — DO NOT PUBLISH THESE NUMBERS and do not "
            "gate on them (GOLDEN_DATASET_SPEC §5). Every verdict is an unadjudicated draft "
            "awaiting expert review; `labelled_by` says so on every record. No blind re-label "
            "round has been run, so `relabel_agreement` is null. Single-labeller dataset — see "
            "GOLDEN_DATASET_SPEC §6 for the limitation that inherits. "
            "Five of the platform's six AI checkers are covered; `graphics` (1.4.11 Non-text "
            "Contrast) has no records, deliberately and not by oversight — see 'Not covered, "
            "and how to add it' in README.md, which names what a future author needs and the "
            "one constraint on who may write them."
        ),
    }
    (HERE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

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
