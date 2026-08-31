# Scope gap — WCAG 1.3.1 *Info and Relationships*

**Status:** CLOSED — the team chose **Option B** and it is built (2026-08-24)
**Raised:** 2026-08-24, from the live audit of Meridian Library on 21 August
**Written for:** the whole team, including anyone who has not read the code

> **What was decided and what was built — §11.** The analysis below is kept as written, because
> it is the record of how the answer was reached and of what the platform claimed while the gap
> was open. Nothing in §1–§10 has been edited to match the outcome.

> **One sentence.** The check that carries WCAG 1.3.1 asks a narrower question than the
> criterion does, so a whole family of real accessibility failures — visual structure that
> exists on screen but not in the markup — is currently reported by nobody.

This is written up on its own because it is **not a bug and not a quick fix**. Two neighbouring
problems found in the same investigation *were* small, and were fixed on 24 August (see §8).
This one is a design decision, and it is the team's to make.

---

## 1. What WCAG 1.3.1 actually requires

The criterion is one sentence, and it is deliberately broad:

> Information, structure, and relationships conveyed through presentation can be
> programmatically determined or are available in text.

In plain terms: **anything a sighted person can work out by looking at the page must also be
written into the markup, so software can work it out too.**

Concretely, on ordinary business software, that means:

| What a sighted person sees | What must exist in the markup |
|---|---|
| A table whose top row is clearly the headings | those cells marked as header cells |
| A bulleted list of three things | an actual list, with actual list items |
| Three radio buttons that clearly belong together under "Delivery" | a group, with "Delivery" as its name |
| A caption sitting under a photo | a link between the two |
| A field labelled "Card number" | that label tied to that field |
| A bold line that is obviously a heading | an actual heading |

If any of those exists only visually, a screen-reader user gets a flat, meaningless stream:
seven cells with no idea which is a heading, three loose radio buttons with no idea what
question they answer.

**Why it matters commercially.** 1.3.1 is **Level A** — the floor, not the stretch goal. It is
also one of the most frequently cited criteria in real accessibility complaints, because tables
and forms are what business software is mostly made of.

---

## 2. What we built instead

The platform has an AI check called `semantics`. It is recorded as covering 1.3.1 and 4.1.2.
It is well written and well tested. It asks **one** question:

> *Is this thing behaving or looking like a control or a heading, without actually being one?*

That catches a genuine and important failure — a `<div>` wired up to act as a button, or a line
of bold text standing in for a heading. Those are real, and we do find them.

But the question it asks is **"is this a fake control?"**, not **"is the visible structure
real?"**. Those are different questions, and only the second one is what 1.3.1 asks.

So the check works correctly and reports honestly, and the criterion above it is only partly
covered — while the platform records the page as *checked for 1.3.1*.

---

## 3. How we know — the evidence

Two independent pieces.

**(a) The selection code, tested directly.** Twelve textbook WCAG failures were passed through
the platform's own element-selection function. These four are 1.3.1 failures, and none of them
is claimed by any check:

| Failure | Handed to a check? |
|---|---|
| `<td>` used where a header cell belongs | no |
| A table with no header cells at all | no |
| A list built out of plain `<div>`s | no |
| Radio buttons with no grouping markup | no |

**(b) The live audit of 21 August.** Across the 11 pages it visited, 1.3.1 was recorded as
satisfied on every one. The record shows what produced that verdict:

- our `semantics` check — 11 pages
- one rule-scanner rule, `aria-hidden-body` — 11 pages

`aria-hidden-body` checks a single thing: that the page body has not been hidden from assistive
technology altogether. It is a sanity check, not a structural one.

So on those pages, **the entire 1.3.1 verdict rested on a check that only looks for fake
controls and fake headings** — and the pages were reported as conforming.

---

## 4. Doesn't the rule scanner cover this?

Partly, and it is worth being precise, because "axe covers structure" is roughly true and
misleading.

**What the scanner does catch:** a list containing something that is not a list item; a header
cell pointing at a column that does not exist; an ARIA widget missing the children its role
requires; a field carrying two conflicting labels. These are all cases where the markup is
*present but internally contradictory* — and a rule engine is very good at that.

**What it cannot catch:** markup that is *absent*. A table with no header cells is not
self-contradictory; it is just a table. The scanner deliberately does not flag it, because it
cannot tell a data table from a table used purely for layout, and flagging every layout table
would make the tool unusable.

**And that absence is exactly the failure class.** Deciding whether a table *needed* headers
requires looking at it and understanding what it is for — which is precisely why 1.3.1 was
assigned to the AI in the first place. The routing is right. The check underneath it is
narrower than the routing assumes.

---

## 5. What we would miss on a client's site

Stated plainly, because this is the part that matters commercially:

- **A data table with no header cells** — extremely common in reporting screens and admin
  panels. A screen-reader user hears a wall of numbers with no idea what any column is.
- **A list of items built from styled `<div>`s** — common in card layouts and dashboards. The
  user is never told how many items there are or where the list starts and ends.
- **Radio buttons or checkboxes with no group** — common in filters and settings. The user
  hears the options but never the question.
- **A caption or hint that visually belongs to a field but is not linked to it** — common in
  forms. The user is told the field's name but not its constraint.

We would report each of these pages as **passing 1.3.1**.

That last sentence is the reason this document exists. A missed finding is a gap. A missed
finding **reported as a pass** is a claim, and a client would be entitled to rely on it.

---

## 6. Why this is not being called a bug

Everything in the selection code is deliberate, documented and individually tested. Its own
opening comment says a skip rule is *"a promise that nothing this checker looks for could ever
be wrong with that element"*, and it holds itself to that. Nothing was written carelessly.

What happened is narrower and more ordinary: the check was built to answer a specific, valuable
question, the routing table recorded it against a criterion much broader than that question,
and nothing in between ever compared the two. The same thing will happen again on a different
criterion unless something checks that pairing.

**That is the durable lesson, and it is bigger than 1.3.1:** we currently have no way of asking
*"does the check we built actually cover the criterion we say it covers?"* — and no report would
ever have told us. It took reading a live conformance statement to notice.

---

## 7. What fixing it would involve

Three options, in increasing order of cost. These are sketches for the team to choose between,
not a plan.

### Option A — Widen the existing check

Teach `semantics` to also ask "is the visible structure real?", and offer it the containers it
would need to answer (a table, a list, a group of fields).

- **For:** one check, one place, no new moving parts.
- **Against:** it becomes two quite different questions in one prompt, which usually makes an AI
  worse at both. The evidence a table needs (its whole shape) is also much larger than the
  evidence a fake button needs (one element).
- **Against:** every table and list becomes something to judge, which costs budget on every run.

### Option B — A separate structure check

A fifth checker whose only job is structure, with the containers as its unit of work rather
than individual elements.

- **For:** each check keeps one clear question, which is how the other four are built and why
  they work.
- **For:** can be turned on, measured and tuned independently.
- **Against:** a new checker is a real piece of work — selection rules, prompt, answer schema,
  tests, and an entry in the routing table.
- **Against:** needs a rule for how much of a table to send, or the cost per judgement climbs
  sharply.

### Option C — Narrow what we claim, and say so

Leave the check as it is, and change the routing table so 1.3.1 is recorded as **partly**
covered — with the conformance statement saying which part.

- **For:** costs almost nothing and makes the reporting honest immediately.
- **For:** can be done **in addition to** A or B, as a stopgap while either is built.
- **Against:** fixes the claim, not the coverage. We still would not find these problems.

**A note on sequencing.** Option C is the only one that closes the *reporting* exposure, and it
is cheap. Whatever the team decides about A or B, C is worth doing first and separately.

---

## 8. What was already fixed, and what was not

Found in the same investigation, and all three are separate things:

| | What | Status |
|---|---|---|
| 1 | Table rows, lists, forms and other containers were never captured at all | **fixed 24 Aug** |
| 2 | A submit button's visible label could never be read, so 2.5.3 never applied to one | **fixed 24 Aug** |
| 3 | This document | **open — needs a decision** |

Fix 1 matters here: the containers a structure check would need **are now being captured**. Most
are not claimed by any rule yet, and that is deliberate — an element that is offered and
declined is *counted*, and the platform can say which rule declined it. An element never offered
is a silence nothing can measure. So whichever option is chosen, the groundwork is in place.

> ⚠️ **Fix 1 was narrower than this paragraph read, and the shortfall lasted a week.** It offered
> `div[class]`, so a container styled by `id` or by an inline style — with no class of its own —
> stayed exactly as invisible as before. Three hand-labelled `structure` failures sat in that
> state through a whole live audit. **Closed 31 August**: the capture now offers any `<div>` with
> three or more children, which is the same bar the structure rule itself uses. Measured across
> 95 routes it adds three elements to 8,385. See gap-fix §9.25.3.

---

## 9. Deliberately not covered here

- **4.1.2 *Name, Role, Value*** shares the same check and is in much better shape, because the
  rule scanner genuinely does cover native controls with missing names. It is not part of this
  gap.
- **The three criteria that record nothing** — 1.3.4 Orientation, 1.4.10 Reflow and 1.4.11
  Non-text Contrast are listed as covered today and produced no result on any page. Orientation
  and Reflow have a confirmed cause: the audit never changes the browser window size, and both
  tests *are* that resize. 1.4.11 is unexplained. **Separate issue, not yet written up.**
- **Whether the conformance statement should be shown to a client before this is settled.** A
  judgement call, and the team's.

---

## 10. The decision needed

1. **Option A, B or C** — and whether C is done first regardless.
2. **Whether the conformance statement goes in front of a client** while 1.3.1 is recorded as
   fully covered.
3. **Whether the pairing problem in §6 gets its own guard** — something that fails when a check
   is registered against a criterion it does not cover. This is the one that stops it happening
   again.

---

## 11. What the team decided, and what was built — 2026-08-24

**Decision: Option B**, with C skipped. The team's instruction was that time did not matter and
the fix should be accurate, so the interim disclaimer was passed over in favour of closing the
coverage itself. **Consequence, accepted knowingly:** the conformance statement kept claiming
full 1.3.1 coverage in the window between the decision and the build.

### The fifth check

A checker called **`structure`**, owning 1.3.1 on its own. `semantics` keeps 1.3.1 and 4.1.2.

**Two checkers now own 1.3.1, and that is the design rather than a duplication.** They ask
different questions about it — one about an element, one about a container — and they stay
apart because the accuracy harness scores **per checker**. Folded into one, a good score on
fake buttons would average away a poor one on tables, which is the same hiding that let this go
unnoticed in the first place. Coverage takes the worst outcome reported for a criterion, so
neither answer can mask the other.

### What it is handed

Its unit of work is the **container**, which is the whole point — whether a table has headers
is a fact about the table, not about any cell in it.

| Selected | Not selected |
|---|---|
| every rendered `<table>`, `<ul>`, `<ol>`, `<dl>`, `<fieldset>` | a container that never rendered |
| a `<form>` holding radio buttons or checkboxes **with no grouping around them** | a form whose fields are already grouped, natively or by ARIA |
| a container repeating the same child class **three or more times** | two repeated children — a pair is a layout, not a list |

**Containers that look correct are still selected.** Whether a table's headers are the *right*
cells, whether a list's items are really items, whether a legend actually names its group —
none of that is decidable from the tag, and the rule scanner already covers the cases where the
markup contradicts itself. What is left is exactly the judgment this check exists for.

**`role="presentation"` is not a skip**, for the same reason it is not one for an image: it is
an author's *claim* that there is no structure here, and whether that claim is true is the
question 1.3.1 asks. A layout table announced as one is a `pass`, and saying so costs one
judgment.

### One thing found while building it, and the fix that followed

A container's markup travels to the judge bounded at **8,000 characters** — about forty rows of
a five-column table. For a button that is never close; for a long table it is, and the judge
would have answered about a table it saw only part of, silently.

The first answer was to say so: the capture reports when it had to cut, and the judge answers
`uncertain` naming the truncation. **The team rejected that as a fix, correctly** — it stops us
being wrong without making us useful, because an uncertain verdict routes to a person, and on a
real reporting screen every large table would land in the review queue.

**The permanent fix (§9.19 of `GAP_FIX_BUILD_PLAN.md`): send the shape, not the markup.** How
many rows and columns, which cells are headers and what they are scoped to, what the top row and
left column say. A few hundred characters for a table of any size, because it is bounded by how
*wide* a container is rather than how *long*. Measured on a 401-row table: 31,985 characters of
markup against 906 of outline, with nothing about the shape lost. The truncation flag stays,
demoted to a backstop.

### Question 3 — also built, later the same day

The guard is `backend/tests/test_a11y_selection_corpus.py`: a corpus of real accessibility
failures, each with the same shape done correctly beside it. A criterion the checks claim must
own at least one failing shape **and** at least one shape that must be left alone — the second
half being what stops a rule that claimed everything from satisfying the first.

**Proven against this very gap.** With `structure` removed in memory, so the platform stands
exactly as it did on 21 August, **five of the recorded 1.3.1 failures reach no check** and the
guard names each. That same state previously produced a clean test run and a conformance
statement claiming eleven pages satisfied 1.3.1.

It proves a criterion has *some* path to a check, not that its coverage is complete — an
unbounded silence turned into a list somebody can argue with, which is the most a test can do
about this. §9.18 of `GAP_FIX_BUILD_PLAN.md` has the detail.

---

## Cross-references

- `GAP_FIX_BUILD_PLAN.md` — the live-run findings, including fixes 1 and 2
- `TASK_BACKLOG_QA.md` — QA-03 (the checkers, and the note recording the fifth), QA-05 (the routing table)
- `evaluation/GOLDEN_DATASET_SPEC.md` §8 — the completeness check, which is what would have
  surfaced this without anyone reading a conformance statement
- `backend/apps/a11y/checkers/rules.py` — the selection rules, and `describe_rules()` for a
  plain-English print of what each check covers and skips
