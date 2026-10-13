# Meridian onboarding pack

Nine client-authored documents for **Meridian Library** — the county public-library web
application (borrower catalogue + staff console) used as the accessibility fixture.

> *Corrected 2026-09-17.* This line used to give the app's location as
> `C:\Users\Msi\projects\Web-Accessibility\meridian-library-web-accessibility` — one developer's
> machine, which nobody else has. The fixture app is its own repository and is **not** in this tree;
> ask the team for the current clone path or remote. Note also that its git history was deliberately
> rewritten so nothing reveals that its defects are planted — never write that back in.

They are test data for the **brownfield onboarding flow**: upload them, extract them, review
them, adopt each as a lifecycle artifact. They are written in the voice of Meridian County
Library Service before onboarding — ordinary corporate documents, a little dry, a little
dated, and occasionally inconsistent with one another (the loan limit is twelve in the FRS and
ten in the PRD; the PRD says so and leaves it). Nothing in them refers to the SDLC platform.

Everything they describe is real: the seventy-eight routes in `routes/index.js`, the twelve
titles and eight branches in `data/seed.json`, the subject counts, the eight client-side
scripts, the `/health` endpoint and the port. Where the documents make a claim the client
believes — the Product Vision repeating the app's own "conforms to WCAG 2.1 Level AA, last
audited March 2024" — that claim is copied from the application's `README.md`.

## The files

| # | File | Format | What it is | Adopt as |
|---|------|--------|------------|----------|
| 1 | `01-product-vision.pdf` | PDF, 3pp | Why the library service commissioned the app, what it is for, who uses it, goals, success measures, what is out of scope. Carries the WCAG 2.1 AA claim. | `ideation` |
| 2 | `02-functional-requirements.docx` | Word | FRS version 3.2 — 40 numbered requirements (FR-001…FR-040) across catalogue and search, reservations, loans, membership and account, staff console, reporting, and help. Ends with known gaps against itself. | `requirements` |
| 3 | `03-product-requirements.docx` | Word | PRD for the borrower and staff experiences: four personas, user stories, in scope / out of scope for each audience, constraints, measures, open items. | `prd` |
| 4 | `04-system-architecture.docx` | Word | Architecture note written by the client's own infrastructure team after reading the code. Node/Express, server-rendered EJS, no client framework, no build step, no database, `data/seed.json`, deployment shape, and an honest list of weaknesses. | `architecture` |
| 5 | `05-user-journeys.docx` | Word | Three narrative journeys — a regular borrower, a branch supervisor, and an older borrower on a public terminal — written from desk observation. Prose, not test cases. | `user_journey` |
| 6 | `06-tc-014-borrower-visit.docx` | Word | **One** test case: *TC-014 — E2E: A borrower's visit*. Eight steps, each naming a route. | `test_case` |
| 7 | `07-tc-015-staff-catalogue.docx` | Word | **One** test case: *TC-015 — E2E: Staff catalogue a new acquisition*. Five steps, each naming a route. | `test_case` |
| 8 | `08-regression-test-cases.xlsx` | Excel | 26 regression cases, one per row (TC ID, Title, Type, Priority, Preconditions, Steps, Expected Result), plus a Notes sheet. Types are Functional / Integration / Performance / Security only — **no row is E2E**, so nothing here is picked up as a journey. Numbering skips 014–015, which are held separately as files 6 and 7. | `test_case` |
| 9 | `09-deployment-runbook.pdf` | PDF, 3pp | How the app is built, released and rolled back; the three environments; configuration; monitoring; on-call; routine tasks; operational risks. | `deployment` |
| 10 | `10-a11y-pages.json` | JSON | Not a document and not uploaded — this is the page list pasted into **Pages & audit** at onboarding step 6. Converted from the app's own `routes.json`: the platform's key is `enabled`, not `in_scope`, and `/health` is registered out of scope so the audit does not report a JSON endpoint as a page. | — |

## Files 6 and 7 are structurally load-bearing

The platform parses them. Their section titles use **real Word Heading styles** (so
`integrations.extract` promotes them to markdown headings) and their step numbers are typed
literally into plain paragraphs as `1. `, `2. ` … (Word's automatic list numbering does not
survive extraction). Each document contains exactly one test case in this order:

```
Heading 1   TC-0nn — E2E: <title>
paragraph   Type: E2E
paragraph   Priority: High
Heading 2   Preconditions
paragraphs  - one precondition per line
Heading 2   Test Steps
paragraphs  1. …  2. …  (literal numbering)
Heading 2   Expected Result
paragraph   …
```

Verified against the platform's own code: `apps.workitems.test_cases.declared_type` returns
`"e2e"`, `apps.a11y.journeys.is_journey` returns `True`, and `parse_steps` returns 8 ordered
steps for TC-014 and 5 for TC-015, each with its `route` populated. `declared_type` on the
extracted body of file 8 returns `""`.

## Regenerating

`build_pack.py` holds all nine documents' content and rewrites them in place:

```
python build_pack.py
```

It needs `python-docx`, `openpyxl` and `pymupdf` — all already backend dependencies
(`backend/requirements.txt`). Correct the content there, not in the generated files, so the
pack stays reproducible.
