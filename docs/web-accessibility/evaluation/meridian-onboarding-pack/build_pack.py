"""Build the Meridian Library client document pack.

Regenerates all nine documents in this directory from the content held below, so the pack is
reproducible and can be corrected in one place. The documents are written in the voice of
Meridian County Library Service (the client), before onboarding.

Run with any Python that has python-docx, openpyxl and pymupdf available:

    python build_pack.py

Files 06 and 07 are parsed by the platform's journey parser, so their structure is fixed:
real Word Heading styles for the section titles, and literal "1. " / "2. " numbering typed
into plain paragraphs (never Word's automatic list numbering, which does not survive
extraction).
"""
from __future__ import annotations

import os

import pymupdf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))


def out(name: str) -> str:
    return os.path.join(HERE, name)


# ─────────────────────────────────────────────────────────────────────────────
# PDF helper — pymupdf Story, so long documents paginate themselves
# ─────────────────────────────────────────────────────────────────────────────

PDF_CSS = """
body { font-family: sans-serif; font-size: 10.5px; color: #1a1a1a; }
h1 { font-size: 20px; margin-top: 0; margin-bottom: 4px; }
h2 { font-size: 13px; margin-top: 14px; margin-bottom: 4px; }
h3 { font-size: 11px; margin-top: 10px; margin-bottom: 3px; }
p  { margin-top: 0; margin-bottom: 7px; line-height: 1.35; }
li { margin-bottom: 4px; line-height: 1.35; }
.meta { color: #555555; font-size: 9px; margin-bottom: 12px; }
td { padding: 3px; font-size: 9.5px; }
th { padding: 3px; font-size: 9.5px; text-align: left; }
"""


def write_pdf(path: str, html: str) -> None:
    story = pymupdf.Story(html=html, user_css=PDF_CSS)
    writer = pymupdf.DocumentWriter(path)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (58, 56, -58, -56)
    more = 1
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()


# ─────────────────────────────────────────────────────────────────────────────
# DOCX helpers
# ─────────────────────────────────────────────────────────────────────────────

def new_doc() -> Document:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    return doc


def meta(doc: Document, lines: list[str]) -> None:
    for line in lines:
        para = doc.add_paragraph(line)
        para.runs[0].italic = True
        para.runs[0].font.size = Pt(9)
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT


# ═════════════════════════════════════════════════════════════════════════════
# 01 — Product vision (PDF)
# ═════════════════════════════════════════════════════════════════════════════

VISION_HTML = """
<h1>Meridian Library Web Service - Product Vision</h1>
<p class="meta">Meridian County Library Service | Digital Services Group |
Document reference DSG/PV/014 | Version 1.4 | Owner: Head of Library Services |
Review due: annually</p>

<h2>1. Purpose of this document</h2>
<p>This paper sets out why Meridian County Library Service commissioned a public web
service, what it is for, who it serves and how we judge whether it is working. It is the
standing reference for anyone taking on the service, whether that is a new member of the
Digital Services Group or an external supplier.</p>

<h2>2. Background</h2>
<p>Meridian Library has served Fenner Road and the surrounding parishes since 1897 and is a
registered charity (1042117) operating under a service agreement with the county. Until 2019
the only public-facing catalogue was a terminal in the Fenner Road reading room and a printed
new-arrivals sheet posted to each branch every month. Members outside Fenner Road had no
practical way of knowing whether a title was on the shelf before they travelled to a branch,
and staff spent a substantial part of the working week answering the same questions by
telephone.</p>
<p>The service was procured in 2019 from an external development partner under the county's
minor works framework and went live in 2020. It has been extended twice since, most recently
in 2023 when the staff console and the reporting pages were added. The original supplier
relationship ended in 2024 and the service has been maintained in a caretaker capacity since
then, with changes limited to content and to correcting faults.</p>

<h2>3. What the service is</h2>
<p>A single web application covering two audiences from one codebase:</p>
<ul>
<li><b>The borrower catalogue.</b> Anyone may browse the catalogue, search it, see what is
held at which branch, reserve a copy, look at their loans and manage their membership
details. No sign-in is required to browse; membership matters only at the point of
borrowing.</li>
<li><b>The staff console.</b> Branch and central staff use the same application to add items
to the catalogue, run shelf audits, apply bulk actions to a selection of items, adjust branch
and display settings, and pull the monthly lending figures.</li>
</ul>
<p>The service covers all eight county branches - Fenner Road, Ashcombe, North Quay,
Willowbank, St Mellick, Harrow Lane, Cadgwith and Penvale - although North Quay and
Harrow Lane are presently closed to the public and appear in listings as closed.</p>

<h2>4. Who uses it</h2>
<h3>4.1 Borrowers</h3>
<p>Roughly eleven thousand active members. Membership is free to anyone living, working or
studying in the county and allows twelve items at a time across all branches. Use is heavily
weighted towards two groups: people over sixty, who make up a little under half of the
catalogue searches recorded, and parents of primary-school children using the summer reading
challenge and the events calendar. A meaningful minority of members reach the service from a
public terminal in a branch rather than from their own device.</p>
<h3>4.2 Library staff</h3>
<p>About forty staff across the eight branches, of whom perhaps a dozen use the staff console
daily. Staff are not technical and receive no formal training on the service beyond a
half-day induction; the console is expected to be self-explanatory. Cataloguing is done at
Fenner Road; the branches use the console mostly for shelf audits, bulk actions and printing
labels.</p>
<h3>4.3 The county</h3>
<p>The county's culture and communities committee receives the lending figures quarterly and
takes them from the reporting pages directly.</p>

<h2>5. Goals</h2>
<ul>
<li>A member should be able to find out whether a title is available, and where, without
telephoning a branch.</li>
<li>A member should be able to reserve a copy for collection at their home branch, and know
what will happen next.</li>
<li>Staff should be able to catalogue a new acquisition and place it on a shelf at a named
branch without leaving the console.</li>
<li>The monthly lending figures should come out of the service itself rather than being
assembled by hand from branch returns.</li>
<li>The service should work on an ordinary, elderly device on a slow connection, and should
remain usable when scripting is limited.</li>
</ul>

<h2>6. Success measures</h2>
<ul>
<li>Catalogue enquiries taken by telephone at Fenner Road: down by half against the 2019
baseline. (Achieved in 2022; holding.)</li>
<li>Reservations placed through the web service rather than at a desk: above sixty per cent
of all reservations.</li>
<li>Items catalogued through the staff console rather than the legacy MARC loader: above
eighty per cent for single acquisitions.</li>
<li>Quarterly lending figures produced without manual reconciliation.</li>
<li>No page of the public service taking longer than two seconds to render on the branch
terminals.</li>
</ul>

<h2>7. Principles we hold to</h2>
<ul>
<li><b>Public first.</b> Everything a borrower needs is reachable without an account.</li>
<li><b>Plain pages.</b> The service is a set of documents, not an application shell. It must
degrade gracefully.</li>
<li><b>Nothing served from elsewhere.</b> No fonts, scripts or images from third-party
origins. The county's information governance position does not permit it.</li>
<li><b>Stable addresses.</b> Branch signage, printed leaflets and the county website point at
specific pages. Routes are not to be renamed.</li>
</ul>

<h2>8. Accessibility</h2>
<p>Meridian Library conforms to WCAG 2.1 Level AA. Last audited March 2024. The published
accessibility statement is carried on the service and reviewed annually alongside this
document.</p>

<h2>9. What is out of scope</h2>
<p>The service is not a library management system. Circulation, fines, membership records of
record and inter-library loan all remain in the county's back-office system; the web service
holds a fixed catalogue extract and displays it. There is no payment capability and no
intention to add one. Digital lending (e-books and audio) is provided by a separate national
platform and is linked to, not reproduced here.</p>

<h2>10. Open questions</h2>
<ul>
<li>Whether the two closed branches should continue to be listed at all.</li>
<li>Whether the reporting pages should be moved behind the staff console rather than being
publicly reachable, as they are today.</li>
<li>Whether the service should be re-procured or brought into a supported arrangement. This
paper assumes the latter.</li>
</ul>
"""


# ═════════════════════════════════════════════════════════════════════════════
# 02 — Functional requirements (DOCX)
# ═════════════════════════════════════════════════════════════════════════════

FRS = [
    ("Catalogue and search", [
        ("FR-001", "The service shall present a catalogue landing page at /catalogue listing the "
                   "current featured titles with author, subject and shelfmark."),
        ("FR-002", "The service shall provide a keyword search at /catalogue/search accepting a "
                   "title, an author name or a subject in a single field, covering the holdings "
                   "of every branch including branches closed to the public."),
        ("FR-003", "The service shall present search results at /catalogue/results and shall "
                   "state the number of matching items above the result list."),
        ("FR-004", "Where a search returns no matches the service shall say so in words and "
                   "shall not present an empty list without explanation."),
        ("FR-005", "The service shall provide an advanced search at /catalogue/advanced-search "
                   "allowing title, author, subject and branch to be given separately."),
        ("FR-006", "The service shall provide a subject index at /catalogue/genres listing every "
                   "subject held with the number of items in it."),
        ("FR-007", "The service shall allow results to be narrowed to a single subject at "
                   "/catalogue/filter using a subject chooser."),
        ("FR-008", "The subjects offered shall be those held in the catalogue extract: Literary "
                   "fiction, Crime, Historical fiction, Reference, Nature writing, Travel writing "
                   "and Poetry."),
        ("FR-009", "The service shall list every copy of every title at every branch at "
                   "/catalogue/all-titles, showing the branch and the shelfmark of each copy, and "
                   "shall present the same holding grouped by subject at /catalogue/by-subject. "
                   "Both listings shall carry headings at intervals so that a reader some way "
                   "down the list can still tell what they are looking at."),
        ("FR-010", "The service shall present new acquisitions of the last four weeks at "
                   "/catalogue/new-arrivals, a staff-selected list at /catalogue/staff-picks, a "
                   "monthly recommendation at /catalogue/recommended and prize winners at "
                   "/catalogue/award-winners."),
    ]),
    ("Reservations and holds", [
        ("FR-011", "The service shall allow a borrower to reserve a copy of a title from "
                   "/catalogue/reserve-copy."),
        ("FR-012", "The reservation control shall ask which branch the copy is to be collected "
                   "from before the reservation is placed."),
        ("FR-013", "The service shall confirm a placed reservation on the page, and the "
                   "confirmation shall be dismissible without leaving the page."),
        ("FR-014", "The service shall state that a reserved copy is held at the collecting "
                   "branch for seven days."),
        ("FR-015", "The service shall allow a hold to be placed on a title that is entirely on "
                   "loan at /catalogue/place-hold."),
        ("FR-016", "A borrower shall be able to reserve a meeting room at /events/book-a-room "
                   "and a study seat at /events/book-a-seat, choosing a date in each case."),
    ]),
    ("Loans", [
        ("FR-017", "The service shall list the borrower's current loans at /loans/current with "
                   "the due date and status of each item."),
        ("FR-018", "Loan status shall be shown as On loan, Due soon or Overdue, and shall be "
                   "distinguishable other than by colour alone."),
        ("FR-019", "The service shall list past loans at /loans/history with the date borrowed "
                   "and the date returned, and renewable items at /loans/renewals, saying why an "
                   "item cannot be renewed where that is the case."),
        ("FR-020", "A borrower shall be limited to twelve items on loan at any one time across "
                   "all branches."),
    ]),
    ("Membership and account", [
        ("FR-021", "The service shall allow a new member to apply for a card at /account/join, "
                   "capturing name, date of birth, address, contact details and home branch."),
        ("FR-022", "The service shall present the member's full profile at "
                   "/account/full-profile using the fifteen profile fields held for a "
                   "membership."),
        ("FR-023", "The service shall allow the member to change their contact details, "
                   "including their contact email address, at /account/settings and "
                   "/account/update-details."),
        ("FR-024", "The service shall allow the member to choose how they are contacted at "
                   "/account/preferences and what they are contacted about at "
                   "/account/notifications."),
        ("FR-025", "The service shall present a borrowing statement at /account/statements and "
                   "card services (replacement, suspension, cancellation) at "
                   "/account/card-services."),
    ]),
    ("Staff console", [
        ("FR-026", "The service shall allow a member of staff to add a single item to the "
                   "catalogue at /staff/catalogue-entry, capturing at least title, author and "
                   "shelfmark, and to save it from that page."),
        ("FR-027", "Bulk imports shall remain the responsibility of the MARC loader and shall "
                   "not be performed through the console."),
        ("FR-028", "The service shall allow staff to record which shelf sections have been "
                   "checked in the current month's audit at /staff/shelf-audit, with each "
                   "section switchable between checked and unchecked. Sections left unchecked "
                   "shall roll over to the following month's audit list."),
        ("FR-029", "The service shall offer the twenty defined bulk actions at "
                   "/staff/bulk-actions against a selection of catalogue items."),
        ("FR-030", "The service shall allow a branch to be chosen for a newly catalogued copy "
                   "at /about/find-a-branch and /about/choose-a-branch."),
        ("FR-031", "The service shall allow branch-level settings and display options to be "
                   "adjusted at /staff/branch-settings and /staff/display-options, and shall "
                   "provide catalogue and membership exports at /staff/exports."),
        ("FR-032", "The service shall allow an existing record to be corrected at "
                   "/staff/quick-edit without going through the full entry form."),
    ]),
    ("Reporting", [
        ("FR-033", "The service shall present a lending summary at /reports/lending-summary and "
                   "longer-run movement at /reports/borrowing-trends."),
        ("FR-034", "The service shall present monthly issue counts for the current year at "
                   "/reports/annual-review and /reports/monthly-issues."),
        ("FR-035", "The service shall compare branches over the same period at "
                   "/reports/branch-comparison, distinguishing branches other than by colour "
                   "alone."),
        ("FR-036", "Reporting figures shall be drawn from the catalogue extract and shall not "
                   "vary between two requests for the same page."),
    ]),
    ("Help, contact and general", [
        ("FR-037", "The service shall answer the questions most often asked at the desk at "
                   "/help/faq, each linking to the page that answers it, and shall explain "
                   "borrowing at /help/borrowing-guide including how many items may be borrowed "
                   "at once."),
        ("FR-038", "The service shall allow a problem with the service to be reported at "
                   "/help/report-a-problem and a problem with an item at /help/problem-report."),
        ("FR-039", "Every page shall carry the shared header and footer, and the header shall "
                   "include a means of skipping directly to the page content."),
        ("FR-040", "The service shall return a page explaining the situation, rather than a "
                   "server error, for any address it does not recognise, and shall expose a "
                   "health address at /health returning a simple machine-readable status for "
                   "monitoring."),
    ]),
]


def build_functional_requirements() -> None:
    doc = new_doc()
    doc.add_heading("Meridian Library Web Service", level=1)
    doc.add_heading("Functional Requirements Specification", level=2)
    meta(doc, [
        "Meridian County Library Service - Digital Services Group",
        "Document reference DSG/FRS/006. Version 3.2.",
        "Supersedes version 3.1 (June 2023). Prepared by S. Ardley, Systems Librarian.",
        "Status: baselined. Changes require the agreement of the Head of Library Services.",
    ])

    doc.add_heading("Scope of this specification", level=2)
    doc.add_paragraph(
        "This document records what the Meridian Library web service does today. It is a "
        "statement of the service as built and as operated, not a wish list. Where a "
        "requirement below is met only in part that is noted against the requirement. "
        "Requirements are numbered FR-001 onwards and the numbers are not reused; a "
        "requirement that is withdrawn keeps its number and is marked withdrawn."
    )
    doc.add_paragraph(
        "The service comprises seventy-eight addressable pages across the borrower catalogue, "
        "the membership area, the events pages, the reporting pages, the staff console and the "
        "help pages. Each is served at a fixed address; the addresses are quoted in the "
        "requirements because printed material and branch signage refer to them."
    )

    doc.add_heading("Conventions", level=2)
    doc.add_paragraph(
        "\"Shall\" indicates a requirement. \"Should\" indicates a preference that is met where "
        "practical. \"Borrower\" and \"member\" are used interchangeably. \"Staff\" means any "
        "member of library staff with access to the console; the service does not distinguish "
        "roles within staff."
    )

    for section, items in FRS:
        doc.add_heading(section, level=2)
        for ref, text in items:
            para = doc.add_paragraph()
            run = para.add_run(ref + "  ")
            run.bold = True
            para.add_run(text)

    doc.add_heading("Known gaps against this specification", level=2)
    for line in [
        "FR-004 is met on /catalogue/results but not on /catalogue/quick-find, which shows an "
        "empty list with no wording.",
        "FR-018 is met on /loans/current. On /loans/history the status column was dropped in "
        "version 1.1 and has not been reinstated.",
        "FR-027 is a policy statement rather than an enforced control; nothing in the console "
        "prevents repeated single entries being used as a bulk import.",
        "FR-036 holds for all reporting pages. It does not hold for the events calendar, which "
        "carries a fixed month and has to be edited by hand each September.",
    ]:
        doc.add_paragraph("- " + line)

    doc.save(out("02-functional-requirements.docx"))


# ═════════════════════════════════════════════════════════════════════════════
# 03 — Product requirements (DOCX)
# ═════════════════════════════════════════════════════════════════════════════

def build_prd() -> None:
    doc = new_doc()
    doc.add_heading("Meridian Library Web Service", level=1)
    doc.add_heading("Product Requirements Document", level=2)
    meta(doc, [
        "Meridian County Library Service - Digital Services Group",
        "Document reference DSG/PRD/009. Version 2.1, revised February 2025.",
        "Author: H. Brannock, Digital Services Manager. Contributions from branch managers.",
    ])

    doc.add_heading("1. Why this document exists", level=2)
    doc.add_paragraph(
        "The Functional Requirements Specification (DSG/FRS/006) says what the service does. "
        "This document says who it is for and why each part of it exists, so that anyone "
        "proposing a change can tell whether the change serves somebody. It covers both "
        "audiences the service has: the borrower and the member of staff."
    )

    doc.add_heading("2. Personas", level=2)

    doc.add_heading("2.1 Ayesha - the regular borrower", level=3)
    doc.add_paragraph(
        "Fifty-two, works at the hospital, lives two streets from the Penvale branch. Reads "
        "steadily, mostly literary fiction and poetry, and has four or five items out at any "
        "time. Uses the service on a five-year-old Android phone during her break. She knows "
        "what she wants and wants to know whether it is on a shelf near her; she has no "
        "interest in browsing. Reserves rather than travels."
    )
    doc.add_paragraph(
        "What she needs: search that accepts a half-remembered title, a clear count of what "
        "came back, a way to narrow to a subject, and a reservation she can place in under a "
        "minute and be confident actually happened."
    )

    doc.add_heading("2.2 Ron - the occasional borrower", level=3)
    doc.add_paragraph(
        "Seventy-eight, uses the public terminal at Fenner Road because he does not have a "
        "computer at home. Comes in most Thursdays. Uses the service to check the events "
        "calendar and to see whether the large-print titles have changed. Enlarges the page. "
        "Does not use a mouse comfortably and works down a page with the keyboard."
    )
    doc.add_paragraph(
        "What he needs: pages that hold together when enlarged, plain wording, and a route "
        "back to where he was. He will abandon anything that needs more than three steps."
    )

    doc.add_heading("2.3 Gordon - branch staff", level=3)
    doc.add_paragraph(
        "Branch supervisor at Ashcombe, eleven years in the service. Catalogues perhaps five "
        "single acquisitions a week - donations and local-interest items that never go through "
        "the MARC loader - and runs the shelf audit at the end of every month. Works on a "
        "shared desk machine with a small screen. Learned the console by watching somebody "
        "else use it."
    )
    doc.add_paragraph(
        "What he needs: an entry form he can complete without looking anything up, a save that "
        "tells him it saved, an audit page where he can see at a glance which sections are "
        "still outstanding, and a way to say which branch a new copy belongs to."
    )

    doc.add_heading("2.4 Marion - central services", level=3)
    doc.add_paragraph(
        "Assembles the quarterly return for the county's culture and communities committee. "
        "Uses only the reporting pages and the exports. Needs the figures to be the same "
        "figures every time she looks."
    )

    doc.add_heading("3. Borrower experience", level=2)
    doc.add_heading("3.1 User stories", level=3)
    for story in [
        "As a borrower I want to search the catalogue by title, author or subject so that I can "
        "find an item without knowing how it is catalogued.",
        "As a borrower I want to see how many items matched my search so that I know whether to "
        "narrow it.",
        "As a borrower I want to narrow a search to a single subject so that a common word does "
        "not bury what I am looking for.",
        "As a borrower I want to see every copy of a title and the branch that holds it so that "
        "I can choose the branch I can actually get to.",
        "As a borrower I want to reserve a copy for collection at a branch of my choosing so "
        "that I do not travel for nothing.",
        "As a borrower I want to be told plainly that my reservation was placed, and to be able "
        "to carry on afterwards.",
        "As a borrower I want to see what I have out and when it is due so that I do not incur "
        "charges.",
        "As a borrower I want to change the email address you write to so that notices reach me.",
        "As a borrower I want to book a meeting room for my reading group on a date that suits "
        "us.",
        "As a borrower I want the questions I would ask at the desk answered on the site, each "
        "leading to the page that answers it in full.",
    ]:
        doc.add_paragraph("- " + story)

    doc.add_heading("3.2 In scope", level=3)
    doc.add_paragraph(
        "Browsing and searching the catalogue; subject listings; the county-wide holding by "
        "title and by subject; new arrivals, staff picks, recommendations and award winners; "
        "reservations and holds; room and seat booking; the events calendar and the summer "
        "reading challenge; loans, renewals and history; membership application and "
        "maintenance; contact preferences and notifications; borrowing statements; card "
        "services; the help and contact pages."
    )

    doc.add_heading("3.3 Out of scope", level=3)
    doc.add_paragraph(
        "Payment of any kind, including fines and replacement charges - these are taken at a "
        "desk. Digital lending, which is provided by the national platform and linked to. "
        "Inter-library loan requests, which go through the back-office system. Personal reading "
        "lists and recommendations based on borrowing history: the service agreement does not "
        "permit borrowing history to be profiled. Ratings, reviews and any other member-supplied "
        "public content."
    )

    doc.add_heading("4. Staff experience", level=2)
    doc.add_heading("4.1 User stories", level=3)
    for story in [
        "As a member of staff I want to catalogue a single new acquisition with its title, "
        "author and shelfmark and save it in one place.",
        "As a member of staff I want to record which shelf sections I have checked this month "
        "so that the outstanding ones are obvious.",
        "As a member of staff I want to say which branch a new copy will be held at.",
        "As a member of staff I want to apply the same action to a number of items at once "
        "rather than opening each one.",
        "As a member of staff I want to correct a catalogue record quickly without going "
        "through the full entry form.",
        "As a member of staff I want the branch's display settings to be mine to set.",
        "As central services I want the monthly issue figures and a branch comparison for the "
        "same period without assembling them by hand.",
    ]:
        doc.add_paragraph("- " + story)

    doc.add_heading("4.2 In scope", level=3)
    doc.add_paragraph(
        "Single-item catalogue entry and quick edit; the shelf audit and shelf settings; the "
        "twenty bulk actions; branch settings and display options; the staff overview; staff "
        "reports and exports; branch selection for a copy."
    )

    doc.add_heading("4.3 Out of scope", level=3)
    doc.add_paragraph(
        "Circulation itself - issue, return, renewal at the desk and fines - which remains in "
        "the back-office system. Bulk import, which is the MARC loader's job. Staff accounts, "
        "roles and permissions: the console is reached from the branch network and the service "
        "does not distinguish one member of staff from another. Rota and staffing. Acquisitions "
        "ordering and supplier management."
    )

    doc.add_heading("5. Constraints", level=2)
    for line in [
        "The service holds no borrower data of record. Anything shown about a membership is a "
        "view of the back-office system's extract.",
        "Nothing may be served from a third-party origin.",
        "Existing addresses may not be renamed. Printed leaflets, branch signage and the county "
        "website point at them.",
        "The service must remain usable on the branch terminals, which are old and are not "
        "going to be replaced this cycle.",
        "A borrower may hold ten items at once. (Note: the FRS gives twelve at FR-025. Twelve is "
        "correct; this paragraph has been wrong since version 1.0 and is left as it is because "
        "the branch handbooks quote it.)",
    ]:
        doc.add_paragraph("- " + line)

    doc.add_heading("6. Measures", level=2)
    doc.add_paragraph(
        "Reservations placed on the service as a proportion of all reservations; single "
        "acquisitions catalogued through the console rather than the loader; shelf audits "
        "completed within the month; catalogue enquiries taken by telephone at Fenner Road; the "
        "quarterly return produced without manual reconciliation."
    )

    doc.add_heading("7. Open items", level=2)
    for line in [
        "The reporting pages are publicly reachable. Nobody has decided whether that is "
        "intended.",
        "Two branches are closed and still listed. The listings say so, but the branch chooser "
        "on the membership form does not offer them at all, which is inconsistent.",
        "The events calendar carries a fixed month and is edited by hand each September.",
    ]:
        doc.add_paragraph("- " + line)

    doc.save(out("03-product-requirements.docx"))


# ═════════════════════════════════════════════════════════════════════════════
# 04 — System architecture (DOCX)
# ═════════════════════════════════════════════════════════════════════════════

def build_architecture() -> None:
    doc = new_doc()
    doc.add_heading("Meridian Library Web Service", level=1)
    doc.add_heading("System Architecture Note", level=2)
    meta(doc, [
        "Meridian County Library Service - Digital Services Group",
        "Document reference DSG/ARCH/003. Version 1.6, revised November 2025.",
        "Compiled by D. Iremonger, Infrastructure, after reading the code. Not written by the "
        "original supplier.",
    ])

    doc.add_heading("1. Purpose and honesty note", level=2)
    doc.add_paragraph(
        "This note describes the service as it actually is. The supplier's original design "
        "pack described a three-tier application with a database and a caching layer; none of "
        "that was built, and the pack is misleading enough that it has been withdrawn. What "
        "follows was compiled by reading the source and the running configuration. Where "
        "something looks unusual it is described as it is rather than tidied up."
    )

    doc.add_heading("2. Shape of the system", level=2)
    doc.add_paragraph(
        "One Node.js process running an Express application, serving HTML rendered on the "
        "server from EJS templates. There is no client-side framework, no bundler and no build "
        "step: the templates under views/ are what the browser receives, and the stylesheet and "
        "the handful of scripts under public/ are served as written. The process listens on "
        "port 4180 by default and is put behind the county's reverse proxy in the deployed "
        "environments."
    )
    doc.add_paragraph(
        "There is no database. The catalogue, the branch list, the loan rows, the profile "
        "fields, the bulk-action list and the reporting figures are all held in a single JSON "
        "file, data/seed.json, which is read once at start-up. Anything derived from it - the "
        "county-wide holding of ninety-six copies, for instance, being twelve titles at each of "
        "eight branches - is computed once at start-up rather than per request."
    )
    doc.add_paragraph(
        "A deliberate consequence, recorded in the data file itself, is that the same address "
        "returns byte-identical HTML on every request. Nothing reads the clock, nothing is "
        "randomised, nothing is counted per visit. This is why the events calendar has to be "
        "edited by hand each year and why the reporting figures never move."
    )

    doc.add_heading("3. Runtime dependencies", level=2)
    doc.add_paragraph(
        "Two, both from the public registry: express (4.x) and ejs (3.x). There are no others "
        "and no transitive additions have been accepted since 2023. The application is "
        "CommonJS. It is presently at version 1.2.0."
    )

    doc.add_heading("4. Request handling", level=2)
    doc.add_paragraph(
        "server.js sets the view engine, mounts public/ as static, parses form bodies, and "
        "installs one piece of middleware of local invention: a res.page helper. Express has no "
        "layout support and the supplier chose not to add a dependency for it, so res.page "
        "renders the page template to a string and then renders a layout template around that "
        "string. A page may opt into an alternative layout; exactly one does."
    )
    doc.add_paragraph(
        "Routing is declarative. routes/index.js holds a single table of every address in the "
        "service - path, template, page title, optional layout and any extra data the template "
        "needs - and registers a GET handler for each. There are seventy-eight entries. A small "
        "tool regenerates routes.json from that table so that the published address list cannot "
        "drift from what the server serves; the regeneration is a manual step and the committed "
        "routes.json is currently behind the table."
    )
    doc.add_paragraph(
        "Anything not matching a table entry falls through to a handler that responds 404 with "
        "a page explaining the situation. There is a /health address returning a small JSON "
        "status object, which is what the proxy and the monitoring check."
    )

    doc.add_heading("5. Templates", level=2)
    doc.add_paragraph(
        "views/ contains the shared layout, the alternative layout, the not-found page and the "
        "page templates, grouped in folders that mirror the address structure: about, account, "
        "authors, catalogue, events, help, loans, reports and staff, plus a few loose pages. "
        "The shared layout carries the skip link, the site header with the main navigation, the "
        "page heading, the rendered page body and a four-column footer. Because it is shared, "
        "anything placed in it appears on all seventy-eight pages."
    )
    doc.add_paragraph(
        "The long listing pages are generated from the arrays in the seed data rather than "
        "written out by hand, so their counts cannot fall out of step with the data behind "
        "them."
    )

    doc.add_heading("6. Client-side scripts", level=2)
    doc.add_paragraph(
        "Eight small scripts under public/js, each loaded by the one or two pages that need it: "
        "a branch jump, two date pickers, a hold dialog, a reserve dialog, a panels helper, a "
        "results renderer and a set of staff controls. They are hand-written, they share no "
        "framework and they are not tested. Two of them - the reserve dialog and one of the "
        "date pickers - implement their own pop-up behaviour rather than using a browser "
        "control."
    )
    doc.add_paragraph(
        "The results page is the only page whose content is produced in the browser rather than "
        "on the server; everything else is complete in the HTML."
    )

    doc.add_heading("7. Static assets", level=2)
    doc.add_paragraph(
        "public/ holds one stylesheet, the scripts, and assets grouped as charts, covers, "
        "decor, icons and photos. Everything is served from the application itself; there are "
        "no external origins, no CDN fonts and no hosted scripts. This is an information "
        "governance requirement rather than a preference."
    )

    doc.add_heading("8. State, sessions and security", level=2)
    doc.add_paragraph(
        "There is no session, no cookie and no sign-in. The staff console is not authenticated "
        "in the application; it is reached from the branch network and protected by the proxy "
        "restricting the /staff/ prefix to county address ranges. The reporting pages carry no "
        "such restriction and are reachable from the public internet. Forms that post do so "
        "without a token; since nothing is persisted, a post has no lasting effect, but this "
        "would need attention the moment anything is stored."
    )

    doc.add_heading("9. Deployment shape", level=2)
    doc.add_paragraph(
        "Three environments - development on a developer's own machine, staging, and "
        "production - each a single small virtual machine in the county's data centre. The "
        "application is deployed as a checkout of the repository plus an npm install of the two "
        "dependencies, run under a process supervisor and fronted by nginx, which terminates TLS "
        "and serves the static directory directly. There is no container image and no "
        "orchestration. There is no horizontal scaling; one process serves the whole county, "
        "which given the load is comfortable."
    )
    doc.add_paragraph(
        "Because there is no database, a release is a code change and nothing else, and a "
        "rollback is a checkout of the previous tag. The runbook covers this."
    )

    doc.add_heading("10. Observability", level=2)
    doc.add_paragraph(
        "Process output goes to the supervisor's log and is rotated weekly. nginx access logs "
        "are kept for thirty days. The monitoring polls /health every minute and alerts the "
        "duty officer after three consecutive failures. There is no application-level metrics "
        "collection and no error tracking service."
    )

    doc.add_heading("11. Known architectural weaknesses", level=2)
    for line in [
        "The catalogue is a fixed file. Adding a title is a code change and a release.",
        "The staff console has no authentication of its own and relies entirely on the proxy "
        "restriction being correct.",
        "The reporting pages are public.",
        "routes.json is regenerated by hand and is currently behind routes/index.js.",
        "The eight client-side scripts are untested and undocumented, and two of them "
        "reimplement browser behaviour.",
        "There is no automated test suite of any kind in the repository.",
    ]:
        doc.add_paragraph("- " + line)

    doc.save(out("04-system-architecture.docx"))


# ═════════════════════════════════════════════════════════════════════════════
# 05 — User journeys (DOCX)
# ═════════════════════════════════════════════════════════════════════════════

def build_user_journeys() -> None:
    doc = new_doc()
    doc.add_heading("Meridian Library Web Service", level=1)
    doc.add_heading("User Journeys", level=2)
    meta(doc, [
        "Meridian County Library Service - Digital Services Group",
        "Document reference DSG/UJ/002. Version 1.3, revised April 2025.",
        "Written by H. Brannock from desk observation at Fenner Road and Ashcombe.",
    ])

    doc.add_heading("How to read this", level=2)
    doc.add_paragraph(
        "These are narratives, not test cases. They were written by sitting with members and "
        "with staff and describing what actually happened, including the parts that went "
        "badly. They exist so that a change can be judged against a real sequence of events "
        "rather than against a single page in isolation. Nothing here should be read as a "
        "specification; where a journey and the FRS disagree, the FRS is authoritative."
    )

    doc.add_heading("Journey one: Ayesha reserves a book of poetry", level=2)
    doc.add_paragraph(
        "Ayesha has ten minutes on her break. Somebody at work mentioned a novel called "
        "Tidewater and she wants to know whether the library has it and whether there is a copy "
        "anywhere she can reach. She opens the search page on her phone, types Tidewater into "
        "the single field and searches."
    )
    doc.add_paragraph(
        "The results page tells her how many items matched. This matters more than it sounds: "
        "when she searched for something looser last month the count told her immediately that "
        "she needed to narrow it, and she did. Today the count is small and she reads down the "
        "list."
    )
    doc.add_paragraph(
        "She is also after poetry, which she reads in short bursts and forgets the titles of, "
        "so she goes to the subject filter and picks Poetry from the chooser. The list "
        "reloads. Poetry is a small section - a few hundred items across the county - and she "
        "can see all of it. She notes A Quiet Inventory by Priya Raghunathan."
    )
    doc.add_paragraph(
        "Next she wants to know where the copies are. The all-titles listing shows every copy "
        "at every branch, which is ninety-six rows, and she works down it looking for anything "
        "at Penvale, which is the branch she can walk to. She finds one. The listing repeats "
        "its headings as she goes, which is the only reason she can still tell what column she "
        "is reading by the time she gets that far down."
    )
    doc.add_paragraph(
        "She opens the reserve page for the copy and presses the reserve control. A small panel "
        "appears asking which branch she will collect from. She chooses, confirms, and closes "
        "the panel. The page tells her the reservation is placed and that the copy will be held "
        "for seven days. This is the point at which the journey usually succeeds or fails: "
        "members who are not certain the reservation happened telephone the branch to check, "
        "which is exactly what the service was bought to avoid."
    )
    doc.add_paragraph(
        "With time left she does two more things. Her reading group meets monthly and she is "
        "hosting, so she opens the room booking page and picks a date for the book club. Then "
        "she remembers that library notices go to an email address she no longer uses, so she "
        "goes to her account settings and changes it. She stops there. She has been meaning to "
        "check how many items she is allowed out at once, and she looks it up in the common "
        "questions, which leads her to the borrowing guide."
    )
    doc.add_paragraph(
        "Observed friction, recorded rather than resolved: the count on the results page is "
        "easy to miss on a small screen; the subject chooser reloads the page as soon as it "
        "changes, which surprises people who expected to press something afterwards; and the "
        "confirmation panel on the reserve page is easy to leave open, after which the page "
        "underneath appears to have stopped responding."
    )

    doc.add_heading("Journey two: Gordon catalogues a donation and runs the audit", level=2)
    doc.add_paragraph(
        "It is the last Thursday of the month at Ashcombe. A local historian has donated a "
        "boxed set and Gordon has one item from it in front of him that is not in the "
        "catalogue and never will be through the loader, because nobody supplies records for "
        "local material."
    )
    doc.add_paragraph(
        "He opens the catalogue entry page in the staff console and types the title and the "
        "author from the title page of the book. He fills in the shelfmark from the sequence "
        "the branch uses for local history. Then he saves, using the save control on the same "
        "page. What he wants at that moment is to be told it saved; he has been caught out "
        "before by saving twice and creating a duplicate, which then has to be merged with a "
        "bulk action."
    )
    doc.add_paragraph(
        "The audit is the other job. He opens the shelf audit page, which lists the sections "
        "the branch is responsible for with a switch against each: fiction, reference, "
        "children's and local history. He has finished local history this afternoon, so he "
        "switches that section to checked. The sections he leaves alone roll over to next "
        "month, which is the whole point of the page: at the end of the month the manager looks "
        "at four switches and knows what is outstanding."
    )
    doc.add_paragraph(
        "Finally the new copy needs a home. Ashcombe is short of shelf space in local history "
        "and the county keeps a second local collection at St Mellick, so Gordon opens the "
        "branch finder, picks the branch that will hold the copy, and confirms the choice on "
        "the branch chooser page. That page is nearly identical to the finder except that it "
        "has a separate confirm control; nobody at the branches is quite sure why there are two "
        "pages, and both are in use."
    )
    doc.add_paragraph(
        "Once a quarter Gordon also pulls the branch comparison from the reporting pages for "
        "his manager's meeting, and once a year he uses the exports. Neither is part of the "
        "monthly rhythm."
    )
    doc.add_paragraph(
        "Observed friction: the save control on the entry form does not look like the other "
        "controls in the console and new staff frequently do not find it; the audit switches "
        "give no wording for their state, so a colleague reading over his shoulder cannot tell "
        "checked from unchecked without asking; and the two branch pages are a standing source "
        "of confusion."
    )

    doc.add_heading("Journey three: Ron on the branch terminal", level=2)
    doc.add_paragraph(
        "Ron comes to Fenner Road on a Thursday and uses the public terminal. He enlarges the "
        "page substantially and moves through it with the keyboard, because the terminal mice "
        "are worn and he does not get on with them. He wants two things: what is on this month, "
        "and whether the large-print shelf has anything new."
    )
    doc.add_paragraph(
        "He starts from the home page, uses the skip link, and works along the main navigation "
        "to the events calendar. He reads it and goes back. Then he goes to new arrivals. He "
        "gets that far reliably. Where he stops is anything that opens a panel over the page - "
        "he loses his place and starts again from the top - and anything that changes the page "
        "as soon as he touches a control, because he cannot tell whether he did it or the page "
        "did."
    )
    doc.add_paragraph(
        "Ron's journey is short and it is included because it is the one that most often ends "
        "with him asking a member of staff to finish it for him. Roughly one in six enquiries "
        "at the Fenner Road desk begins with somebody who was already on the right page."
    )

    doc.save(out("05-user-journeys.docx"))


# ═════════════════════════════════════════════════════════════════════════════
# 06 / 07 — the two single-test-case documents (STRICT FORMAT)
# ═════════════════════════════════════════════════════════════════════════════

def build_test_case(*, filename: str, title: str, priority: str,
                    preconditions: list[str], steps: list[str], expected: str) -> None:
    """One test case per document, in the exact layout the platform parses.

    Section titles are real Word Heading styles (the extractor only promotes heading-styled
    paragraphs to markdown headings). Step numbers are typed into the paragraph text, not
    produced by Word's automatic numbering, so they survive extraction.
    """
    doc = new_doc()
    doc.add_heading(title, level=1)
    doc.add_paragraph("Type: E2E")
    doc.add_paragraph(f"Priority: {priority}")

    doc.add_heading("Preconditions", level=2)
    for line in preconditions:
        doc.add_paragraph(f"- {line}")

    doc.add_heading("Test Steps", level=2)
    for i, step in enumerate(steps, start=1):
        doc.add_paragraph(f"{i}. {step}")

    doc.add_heading("Expected Result", level=2)
    doc.add_paragraph(expected)

    doc.save(out(filename))


TC_014 = dict(
    filename="06-tc-014-borrower-visit.docx",
    title="TC-014 — E2E: A borrower's visit",
    priority="High",
    preconditions=[
        "The service is running and reachable at the environment under test.",
        "The catalogue extract is the standard one, holding twelve titles across eight branches.",
        "The signed-in membership is the Ayesha test membership, with no reservations "
        "outstanding.",
        "A copy of the title being reserved is held at Penvale.",
        "The browser is at its default zoom with no stored preferences.",
    ],
    steps=[
        'Open /catalogue/search and search for the title "Tidewater".',
        "On /catalogue/results, read the number of matches reported above the list.",
        "Go to /catalogue/filter and narrow the results to Poetry using the subject chooser.",
        "Open /catalogue/all-titles and move down the list to the copy held at Penvale.",
        "Open /catalogue/reserve-copy, place a reservation with the Reserve button, and close "
        "the confirmation that appears.",
        "Go to /events/book-a-room and choose a date for the book club meeting.",
        "Open /account/settings and change the contact email address.",
        "Open /help/faq and follow the link to the question about borrowing limits.",
    ],
    expected=(
        "The borrower completes the visit without assistance: the search reports its match "
        "count, the subject filter narrows the list to Poetry, the Penvale copy is reachable in "
        "the county listing, the reservation is placed and confirmed and the confirmation can "
        "be dismissed, the room date is chosen, the new contact email address is saved, and the "
        "borrowing-limit question leads to the borrowing guide."
    ),
)

TC_015 = dict(
    filename="07-tc-015-staff-catalogue.docx",
    title="TC-015 — E2E: Staff catalogue a new acquisition",
    priority="High",
    preconditions=[
        "The service is running and reachable at the environment under test.",
        "The session is on the branch network, so the staff console is reachable.",
        "The acquisition being catalogued is not already in the catalogue extract.",
        "The current month's shelf audit is open with the Local history section unchecked.",
        "The branch that will hold the new copy is open to the public.",
    ],
    steps=[
        "Open /staff/catalogue-entry and enter the title and author of a new acquisition.",
        "Save the record using the Save control on /staff/catalogue-entry.",
        "Open /staff/shelf-audit and switch the Local history section to checked.",
        "Open /about/find-a-branch and pick the branch that will hold the new copy.",
        "Confirm the choice on /about/choose-a-branch.",
    ],
    expected=(
        "The acquisition is entered and saved from the catalogue entry page with visible "
        "confirmation, the Local history section reads as checked in the shelf audit, and the "
        "holding branch is chosen and confirmed."
    ),
)


# ═════════════════════════════════════════════════════════════════════════════
# 08 — Regression test cases (XLSX)
# ═════════════════════════════════════════════════════════════════════════════

REGRESSION_HEADERS = ["TC ID", "Title", "Type", "Priority", "Preconditions", "Steps",
                      "Expected Result"]

REGRESSION_ROWS = [
    ("TC-001", "Catalogue landing page lists featured titles", "Functional", "Medium",
     "The service is running.",
     "1. Open /catalogue.\n2. Read the featured list.",
     "Each featured title is listed with its author, subject and shelfmark."),
    ("TC-002", "Keyword search accepts a title", "Functional", "High",
     "The service is running.",
     "1. Open /catalogue/search.\n2. Enter \"Nightjar\" in the single search field.\n"
     "3. Submit the search.",
     "The search runs and Nightjar by Marta Lindqvist appears in the results."),
    ("TC-004", "Search results report a match count", "Functional", "High",
     "A search has been submitted.",
     "1. Open /catalogue/results.\n2. Run a search from the form.\n"
     "3. Read the line above the result list.",
     "The number of matching items is stated above the list."),
    ("TC-005", "Empty search result is explained", "Functional", "Medium",
     "The service is running.",
     "1. Open /catalogue/results.\n2. Search for a term that matches nothing.",
     "The page says in words that nothing matched. No bare empty list is shown."),
    ("TC-007", "Subject index lists every subject with its count", "Functional", "Medium",
     "The service is running.",
     "1. Open /catalogue/genres.\n2. Read the list.",
     "All seven subjects are listed with counts: Literary fiction 4120, Crime 3380, "
     "Historical fiction 1870, Reference 2240, Nature writing 940, Travel writing 760, "
     "Poetry 512."),
    ("TC-008", "Subject filter narrows the catalogue", "Functional", "High",
     "The service is running.",
     "1. Open /catalogue/filter.\n2. Choose Poetry in the subject chooser.",
     "The list is narrowed to Poetry titles."),
    ("TC-009", "County holding lists every copy at every branch", "Functional", "High",
     "The service is running.",
     "1. Open /catalogue/all-titles.\n2. Count the rows.",
     "Ninety-six rows are listed, twelve titles at each of the eight branches, each row "
     "showing branch and shelfmark."),
    ("TC-011", "Reservation asks for a collection branch", "Functional", "High",
     "The service is running.",
     "1. Open /catalogue/reserve-copy.\n2. Start a reservation.",
     "The collection branch is asked for before the reservation is placed."),
    ("TC-012", "Reservation confirmation can be dismissed", "Functional", "High",
     "A reservation has been placed on /catalogue/reserve-copy.",
     "1. Place the reservation.\n2. Close the confirmation.",
     "The confirmation closes and the page beneath is usable again."),
    ("TC-016", "Current loans show due date and status", "Functional", "High",
     "The test membership has three items out.",
     "1. Open /loans/current.\n2. Read the three rows.",
     "Tidewater shows as Overdue, Nightjar as Due soon and Bell and Bone as On loan, each "
     "with its due date."),
    ("TC-017", "Loan status is distinguishable without colour", "Functional", "Medium",
     "The test membership has three items out.",
     "1. Open /loans/current.\n2. Inspect how each status is conveyed.",
     "Each status carries wording, not colour alone."),
    ("TC-019", "Renewals page explains a refusal", "Functional", "Medium",
     "One item is reserved by another borrower.",
     "1. Open /loans/renewals.\n2. Attempt to renew the reserved item.",
     "The page says why the item cannot be renewed."),
    ("TC-020", "Membership application captures the required fields", "Functional", "High",
     "The service is running.",
     "1. Open /account/join.\n2. Complete every field.\n3. Submit.",
     "Name, date of birth, address, contact details and home branch are all captured."),
    ("TC-022", "Contact email address can be changed", "Functional", "High",
     "The test membership exists.",
     "1. Open /account/settings.\n2. Change the contact email address.\n3. Save.",
     "The new address is retained and shown on the settings page."),
    ("TC-023", "Catalogue entry saves a single acquisition", "Functional", "High",
     "The session is on the branch network.",
     "1. Open /staff/catalogue-entry.\n2. Enter title, author and shelfmark.\n"
     "3. Use the Save control.",
     "The record is saved and the member of staff is told so."),
    ("TC-024", "Shelf audit sections can be switched", "Functional", "High",
     "The current month's audit is open.",
     "1. Open /staff/shelf-audit.\n2. Switch Local history to checked.",
     "The section reads as checked and the remaining sections are unchanged."),
    ("TC-025", "All twenty bulk actions are offered", "Functional", "Medium",
     "The session is on the branch network.",
     "1. Open /staff/bulk-actions.\n2. Count the actions offered.",
     "Twenty actions are offered, from Mark received through to Clear selection."),
    ("TC-026", "Branch comparison distinguishes branches without colour alone", "Functional",
     "Medium", "The service is running.",
     "1. Open /reports/branch-comparison.\n2. Inspect the series labels.",
     "Fenner Road, Ashcombe and North Quay are each identifiable without relying on colour."),
    ("TC-027", "Monthly figures are stable between requests", "Integration", "High",
     "The service is running.",
     "1. Open /reports/monthly-issues and record the figures.\n2. Reload the page.\n"
     "3. Compare.",
     "The figures are identical: Jan 820 through to Aug 780."),
    ("TC-028", "Common questions link to the page that answers them", "Functional", "Medium",
     "The service is running.",
     "1. Open /help/faq.\n2. Follow each question link in turn.",
     "Each question leads to a page that answers it; no link is broken."),
    ("TC-029", "Unknown address returns an explained not-found page", "Functional", "Medium",
     "The service is running.",
     "1. Request an address that does not exist.",
     "A 404 status is returned with a page explaining the situation, not a server error."),
    ("TC-030", "Health address reports status for monitoring", "Integration", "High",
     "The service is running.",
     "1. Request /health.",
     "A JSON body reporting an ok status is returned."),
    ("TC-031", "County holding renders within the page budget", "Performance", "Medium",
     "The service is running on a branch terminal.",
     "1. Open /catalogue/all-titles from a cold start.\n2. Time to first render.",
     "The page renders in under two seconds on the branch terminal specification."),
    ("TC-033", "Staff console is not reachable from outside the branch network", "Security",
     "High", "A session outside the county address ranges.",
     "1. Request /staff/catalogue-entry from outside the branch network.",
     "The request is refused by the proxy before it reaches the application."),
    ("TC-034", "No asset is served from a third-party origin", "Security", "High",
     "The service is running.",
     "1. Load any page.\n2. List every request the page makes.",
     "Every request is to the service's own origin. No fonts, scripts or images come from "
     "elsewhere."),
    ("TC-035", "Form input is not reflected into the page unescaped", "Security", "High",
     "The service is running.",
     "1. Open /catalogue/search.\n2. Submit a term containing markup characters.",
     "The term is shown as text. No markup from the term is interpreted."),
]


def build_regression_workbook() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Regression"

    ws.append(REGRESSION_HEADERS)
    for row in REGRESSION_ROWS:
        ws.append(list(row))

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="44546A")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    widths = [10, 46, 13, 10, 40, 52, 56]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(REGRESSION_HEADERS))}{ws.max_row}"

    notes = wb.create_sheet("Notes")
    for line in [
        ["Meridian Library Web Service - regression pack"],
        ["Meridian County Library Service, Digital Services Group. DSG/QA/011 version 4.0."],
        ["Maintained by S. Ardley. Run by hand before each release; there is no automated "
         "suite."],
        [""],
        ["TC-014 and TC-015 are held separately as full test cases and are not repeated here."],
        ["Numbers are never reused. A gap is a case withdrawn at some point since version "
         "1.0, or one held elsewhere."],
    ]:
        notes.append(line)
    notes.column_dimensions["A"].width = 100

    wb.save(out("08-regression-test-cases.xlsx"))


# ═════════════════════════════════════════════════════════════════════════════
# 09 — Deployment runbook (PDF)
# ═════════════════════════════════════════════════════════════════════════════

RUNBOOK_HTML = """
<h1>Meridian Library Web Service - Deployment and Operations Runbook</h1>
<p class="meta">Meridian County Library Service | Digital Services Group |
Document reference DSG/OPS/007 | Version 2.3, revised January 2026 |
Owner: D. Iremonger, Infrastructure</p>

<h2>1. Scope</h2>
<p>How the Meridian Library web service is built, released, rolled back and supported. It
assumes the reader has access to the county's deployment jump host and to the service
repository. It does not cover the back-office library management system, which is a supplier
arrangement with its own procedures.</p>

<h2>2. Environments</h2>
<ul>
<li><b>Development</b> - a developer's own machine, on localhost port 4180. npm install then
npm start; no configuration is needed.</li>
<li><b>Staging</b> - host lib-stage-01, reachable internally only. Identical to production and
refreshed from the main branch on demand.</li>
<li><b>Production</b> - host lib-prod-01, public and behind the county proxy. A single virtual
machine; there is no second instance.</li>
</ul>
<p>Each environment is one small virtual machine in the county data centre running the
supported long-term Node.js release. nginx fronts the application, terminates TLS, serves the
static directory directly and restricts the /staff/ prefix to county address ranges. The
application itself listens on port 4180 and is kept alive by the process supervisor.</p>

<h2>3. Build</h2>
<p>There is no build step. The service is a server-rendered Express application with no
bundler, no transpilation and no generated assets: what is in the repository is what is
served. "Building" a release means nothing more than checking out a tag and installing the two
runtime dependencies.</p>
<p>The only generated file in the repository is the published address list, which is
regenerated from the route table with the routes script. This is a manual step and must be run
and committed whenever an address is added or removed.</p>

<h2>4. Release procedure</h2>
<p>Releases go out on a Tuesday morning outside opening hours, or at any time for a fault
affecting the public service. The steps are the same either way.</p>
<ul>
<li>Confirm the change is merged to the main branch and that the version in the package
manifest has been raised. Any change to a rendered page must raise it.</li>
<li>Tag the release as <b>v<version></b> and push the tag.</li>
<li>On staging: fetch, check out the tag, install dependencies, restart under the supervisor.
Confirm the health address returns ok.</li>
<li>Walk the release check on staging - the home page, catalogue search, the county
holding, a reservation, the staff catalogue entry page and one reporting page.</li>
<li>Notify the duty officer and the Fenner Road desk that a release is going out.</li>
<li>On production: repeat the fetch, checkout, install and restart. The restart is under a
second and is not announced to members.</li>
<li>Confirm the health address, then repeat the release check against production.</li>
<li>Record the tag, the time and the person releasing in the change log.</li>
</ul>

<h2>5. Rollback</h2>
<p>Rollback is a checkout of the previous tag and a restart, and takes about two minutes.
There is no database and therefore no data migration to undo: a release is code and nothing
else, and the previous code will behave exactly as it did before.</p>
<ul>
<li>Check out the previous tag on the affected host.</li>
<li>Install dependencies (only necessary if the dependency versions changed, which is rare).
</li>
<li>Restart under the supervisor and confirm the health address.</li>
<li>Repeat the release check.</li>
<li>Record the rollback and the reason in the change log, and raise a fault so the cause is
looked at rather than forgotten.</li>
</ul>
<p>The decision to roll back rests with the duty officer and does not need to wait for the
Digital Services Manager. If in doubt, roll back.</p>

<h2>6. Configuration and secrets</h2>
<p>The application takes one setting, the listening port, from the environment and defaults it
when absent. It holds no credentials of any kind: there is no database, no third-party service
and no outbound integration. TLS certificates are held by nginx and renewed by the county's
central process. There is nothing in this service that belongs in a secret store.</p>

<h2>7. Monitoring and alerting</h2>
<p>The county monitoring polls the health address every minute. Three consecutive failures
raise an alert to the duty officer's pager. nginx access and error logs are kept for thirty
days; the application's own output goes to the supervisor journal and is rotated weekly. There
is no application metrics collection and no error tracking service, so a fault that does not
stop the process will not be noticed by monitoring - it will be reported by a member of
staff at a branch.</p>

<h2>8. On-call</h2>
<p>The service is in the county's shared out-of-hours rota. The duty officer covers all
Digital Services applications and is not expected to know this one in detail; the expectation
out of hours is restart, then roll back, then escalate. Escalation is to the Infrastructure
lead and then to the Digital Services Manager.</p>
<p>Because the library is closed outside opening hours, an out-of-hours outage is not treated
as urgent unless it falls within the hour before opening. In practice the service is restarted
in the morning and the cause looked at during the working day.</p>

<h2>9. Routine tasks</h2>
<ul>
<li><b>Node.js version</b> - moved to the next long-term release each spring, on staging
first, with a full walk of the release check.</li>
<li><b>Dependency updates</b> - the two dependencies are reviewed twice a year and
updated only for a security advisory.</li>
<li><b>Events calendar</b> - carries a fixed month and is edited by hand each September.
This is a release like any other.</li>
<li><b>Log review</b> - the nginx error log is skimmed monthly for repeated not-found
addresses, which usually indicate a printed leaflet pointing at an address that no longer
exists.</li>
</ul>

<h2>10. Known operational risks</h2>
<ul>
<li>One production host with no second instance. A host failure is an outage until the host is
recovered.</li>
<li>The staff console is protected only by the proxy restriction. A misapplied nginx
configuration exposes it, and nothing in the application would prevent use.</li>
<li>The reporting pages are publicly reachable by design of the proxy rules as they stand.</li>
<li>There is no automated test suite, so the release check is walked by hand and its coverage
depends on who walks it.</li>
</ul>
"""


def main() -> None:
    write_pdf(out("01-product-vision.pdf"), VISION_HTML)
    build_functional_requirements()
    build_prd()
    build_architecture()
    build_user_journeys()
    build_test_case(**TC_014)
    build_test_case(**TC_015)
    build_regression_workbook()
    write_pdf(out("09-deployment-runbook.pdf"), RUNBOOK_HTML)
    for name in sorted(os.listdir(HERE)):
        if name != os.path.basename(__file__):
            print(f"{name}  {os.path.getsize(out(name)):,} bytes")


if __name__ == "__main__":
    main()
