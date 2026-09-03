# Audit Live Check — what actually happened, reading by reading

**Meridian Library · 94 pages · Edvensoft SDLC Platform, web-accessibility capability**

Two full-scale audits are recorded here.

| | Audit | Date | Where |
|---|---|---|---|
| **Part I** | `ee977648` | 31 August 2026, with 1 September follow-up | Condensed retrospective |
| **Part II** | `f60c8f1a` | **2 September 2026** | The full live account |

---

## 0. What this document is, and what it is not

This is a **live record**, written from database readings taken while each audit ran, not a summary
assembled afterwards. Every number is measured at the time stamped beside it. Where something is a
projection, an inference or a guess, it says so in those words.

**Why it exists.** An audit that cannot describe itself accurately is worth very little. A claim
that "the platform works" is worth almost nothing on its own; a timestamped trail showing the exact
fields that were wrong last time reading correctly this time is worth something. That is the whole
purpose of the exercise, and it is why the observer's own errors are recorded here alongside the
platform's.

**Part I has been condensed.** The 31 August run was originally written up reading-by-reading at the
same level of detail as Part II. That account did its job — it proved four fixes and produced eleven
more — and the full text is preserved in git history at commit `41458ae`. What is kept below is the
shape of the run, the numbers, and the lessons that still bind.

---
---

# PART I — 31 August and 1 September, condensed

## 1. The 31 August run

**Audit `ee977648` · 94 pages · 2,174 elements · 2,293 requests · 1,068 distinct questions.**

### What it was for

The full-scale audit earlier that same day produced numbers nobody could trust — not because the
platform failed, but because *the audit's own record of itself* was destroyed by a defect, and
everyone downstream was reading that record. Four defects were fixed and this run was the proof.

### The shape of it

| Pass | Window | Elements | Outcome |
|---|---|---|---|
| 1 | 09:39–11:55 | 800 | All answered; 268 deferred at the run's cap |
| 2 | 12:45–13:04 | 269 | Machine restarted at element 99; parked; taken over by hand |
| 3 | 15:49–16:26 | 170 | All answered |

Capture ran 09:06 to 09:37 for all 94 screens. Pass 1 cost **$33.12**.

**Three passes, and the arithmetic held.** 1,068 distinct answers, predicted before the second pass
began and again before the third on the arithmetic 800 + 268, and it did not drift.

### What it proved

- `filed_unjudged = 0` — nothing was filed as unjudgeable that could have been asked.
- The audit correctly reported `judging` rather than closing early.
- Zero placeholder verdicts were written where a real answer was possible.
- The report is always a picture of the **whole** capture, with a later pass filling in more of the
  same table rather than producing a rival document.

### What it cost in lessons

Eleven further defects were found and fixed during and after the run. Four recur as patterns and are
worth carrying forward:

1. **A field captured is not a field delivered.** Something can be measured, stored, and still never
   reach the component that needs it. Three separate guards now exist for exactly this.
2. **A count scoped to what was recently touched is not a count.** Measuring eleven of thirty-three
   test files and reporting the total was the same error applied to a test run.
3. **A test whose purpose is to notice a change, red because of the change it was meant to notice,
   gets passed over.** This happened three times.
4. **An accepted background of red absorbs every guard you have.** Four independent drift guards
   reported one true fact for five days and nobody heard them.

## 2. What 1 September added

**The accuracy score.** The first baseline accuracy figure was produced, along with the rule that
makes it meaningful: the person who labels the answer key must not be the person who built the
checker being scored.

**The review queue, read properly.** Nineteen items were examined one by one rather than counted.

**The sixth check's paperwork.** A genuine contradiction surfaced: the code claimed WCAG **1.4.11
Non-text Contrast** for the AI judge, while the ownership register — derived from the research
evidence — assigned it to the rule engine. The team had already decided in favour of the AI on
27 August (correction **R14**) and that decision had never been carried into the register. Five drift
guards had been reporting this daily for five days and were read as background red.

It was resolved by adding an explicit `ENGINEERING_OVERRIDES` layer applied at load time, so the
derived dataset stays faithful to the research evidence while the live register carries the team's
decision. Seven selection-corpus rows and the missing capability method were added at the same time.
**All six element checks became live and exposed simultaneously for the first time.**

---
---

# PART II — 2 September 2026, the run in full

**Audit `f60c8f1a` · tenant `Edvensoft-WCAG-2` · project `WCAG-Audit-2`**
**Fresh tenant, fresh project, nothing inherited.**

## 3. The words you need, once

| Term | What it means here |
|---|---|
| **Element** | One thing on one page — a button, an image, a table. |
| **Request** | One question about one element on one page. |
| **Distinct question** | The same markup asked once, not once per page it appears on. A footer on 94 pages is 94 requests and **one** question. |
| **Check** | One of six inspectors: `alt`, `semantics`, `structure`, `color`, `label`, `graphics`. |
| **Pass** | One attempt at judging. A pass stops at its cap, or when the engine stops. |
| **Verdict** | The judge's answer: `pass`, `fail`, or `uncertain`. |
| **Finding** | A row in the permanent ledger. Survives runs. This is what the screen reads. |

## 4. Before the audit — the pre-flight

Verified before the run was allowed to start, each because something once went wrong there:

- **Worker holding today's code** — asked the running process directly rather than reading a file.
  All six checks present; the 1.4.11 override live; `check_graphics` exposed on the connector.
- **Companion connected and beating** — heartbeat one second old.
- **94 of 95 routes in scope**, one deliberately excluded.
- **Clean slate** — zero cached verdicts, zero findings. Nothing inherited from any earlier tenant.
- **Shared server reachable** on both the database and the workflow engine.

### 4.1 The five-checker safety proof

The five original checks had to be shown unchanged by the previous day's work. Rather than assert
it, the selection rules **as they stood on 31 August** were loaded alongside the current ones and
every element in the selection corpus was walked past both.

```
BEFORE (31 Aug) : alt, semantics, structure, color, label, graphics
NOW             : alt, semantics, structure, color, label, graphics
elements compared: 50

RESULT: the five original checkers select IDENTICALLY on all 50 elements.
        No element gained a check. No element lost one.
```

Scope prose, skip rules and criteria were identical character for character for all five.

## 5. The capture — 01:53:01 to 02:22:31

**94 of 94 screens in 29.5 minutes. Zero scan errors. Zero load errors.**

| Reading | Screens | Elements |
|---|---|---|
| 01:53:46 | 2 | 61 |
| 01:54:48 | 6 | 137 |
| 02:02 | 20 | 482 |
| 02:14 | 41 | 930 |
| 02:22:31 | **94** | **2,177** |

**2,083 elements carried a screenshot.** The 92 that did not were all `semantics` candidates whose
rectangle falls outside the page — collapsed menus, skip links, off-canvas navigation. `semantics`
is answered from tags and roles, not pixels, so nothing was lost. This held flat at roughly 4.3%
throughout the capture rather than climbing.

### 5.1 The scanner was working, and it was checked

Early screens returned few automatic violations, which could equally mean "clean pages" or "broken
scanner". The two were distinguished by looking at the *passes*: `axe-core 4.13.0` returned **16 to
23 passes per screen** alongside its violations. A scanner returning zero passes would be broken; one
returning passes and few violations is working, on pages whose planted defects are mostly of the kind
no automatic rule can catch. That is precisely why the six AI checks exist.

## 6. What there was to judge — measured at 02:24

```
requests (every copy on every page) : 2,283
DISTINCT questions                  : 1,068
dedup ratio                         : 2.14x
```

| Check | Requests | Distinct |
|---|---|---|
| color | 1,204 | 523 |
| semantics | 412 | 319 |
| structure | 532 | 91 |
| **graphics** | **59** | **59** |
| alt | 56 | 56 |
| label | 20 | 20 |

### 6.1 The reading that mattered most

Set beside 31 August:

| | 31 Aug | 2 Sep | |
|---|---|---|---|
| Requests | 2,293 | **2,283** | −10 |
| **Distinct questions** | **1,068** | **1,068** | **identical** |
| Dedup ratio | 2.15× | 2.14× | identical |
| **Graphics elements** | **59** | **59** | **identical** |

**The audit selected the same work it selected before the changes.** Not approximately — the same
number, splitting the same way. If any of the previous day's work had widened or narrowed what the
five original checks look at, this is the number that would have moved.

### 6.2 A false alarm, and how it died

Mid-capture the observer flagged element density as "22 per page against a baseline of 8.5" and began
investigating a possible regression. Three things were done before anything was said to the team:

1. **Read the code history.** The dominant colour predicate dates from 14 August, unchanged since.
2. **Measured the only post-31-August change.** The 1 September `border-color` / `outline-color`
   additions were stripped from all 481 live captured elements and selection re-run:

```
colour candidates WITH border-color+outline-color : 270
colour candidates WITHOUT them (31 Aug logic)     : 270
difference attributable to the change             : 0
```

3. **Found the actual error — the observer's own.** The "8.5 per page" baseline came from dividing
   31 August's *capped first pass* (800 elements over 73 screens) by all 94 pages. The correct
   comparison is whole capture against whole capture, and those match to within 0.6%.

**No finding was ever reported to the team from this.** It is recorded because the discipline that
killed it — measure before naming a fault — is the point of the document.

## 7. The judging cap — a configuration gap caught before it bit

`caps_for()` reads `max_judgments_per_run` from the `a11yai` connection's scopes and falls back to
`DEFAULT_MAX_JUDGMENTS_PER_RUN = 200` when it is absent.

**The fresh tenant had `scopes = {}`.** The 31 August tenant had 800 configured; the new one had
nothing, so this audit would have judged 200 questions per pass and needed roughly five passes.

It was caught during capture, while there was still time to act. The team chose 800, matching
31 August. Exactly one row was updated, named by primary key, guarded by an assert that would roll
the transaction back if it touched anything other than a single row:

```
before: {}
after : {"max_judgments_per_run": 800}
caps_for(tenant) -> (800, None)
```

`get_connection` reads the database on every call, so no restart was needed.

> **Carry forward.** A new tenant starts with no judging cap and silently inherits 200. Worth making
> visible at project setup rather than discoverable mid-audit. Logged in `GAP_FIX_BUILD_PLAN.md`.

## 8. Pass 1 — 02:24:46 to 04:11:25

**Dispatched exactly 800** distinct questions across 74 screens.

| Check | Dispatched |
|---|---|
| color | 383 |
| semantics | 225 |
| structure | 68 |
| alt | 52 |
| **graphics** | **52** |
| label | 20 |

Three things in the dispatch were confirmations rather than expectations:

- **726 of 800 carried a screenshot** — the 74 without are the off-screen `semantics` items.
- **`parent` on 800 of 800; `accessible_name` on 524 of 800.** These are the two fields added on
  1 September, the ones that required a companion restart. Their presence proved the companion was
  running the current capture script — the single item the pre-flight could not confirm directly.
- **All six checks present**, `graphics` among them, in a live dispatch.

### 8.1 The first graphics verdict — 02:40:51

The sixth check's first answer on real content, at confidence 0.88:

> *"Screenshot shows a flat SVG illustration of a two-storey brick building. The dark reddish-brown
> building silhouette is clearly visible against the light grey background. The building outline (the
> part that conveys the subject's identity and two-storey structure) contrasts visibly against the
> background — the dark brown on light grey appears to exceed 3:1. The arched windows (light
> grey/white on dark brown) are also clearly delineated. This is a flat illustration, not a
> photograph, so the essential-appearance exemption does not apply. All meaningful parts of the
> graphic (building outline, windows, roofline) are sufficiently visible."*

Five things are demonstrated in one paragraph: it read actual pixels; it named the real colours; it
applied 1.4.11's 3:1 threshold; **it knew the photograph exemption and correctly declined to use
it**; and it identified which parts of the drawing carry meaning. The criterion is `1.4.11` — the
exact rule at the centre of the previous day's ownership contradiction.

### 8.2 The first failures — 02:49

Three `alt` failures at 0.99 confidence, each quoting `accessible_name` in its reasoning — the
1 September field being *used*, not merely delivered:

| alt text | What the picture actually shows |
|---|---|
| `alt="photo"` | Local history room — map cabinets, county map, globe |
| `alt="image"` | Children's corner — patterned rug, floor cushions, bunting |
| `alt="picture"` | Four study carrels — partitions, reading lamps, chairs |

Each carried a written replacement drawn from the pixels, for example *"A round patterned rug with
floor cushions on it, low shelves at child height on either side, and paper bunting strung across the
ceiling."*

### 8.3 The 19-of-19 label failures, verified rather than assumed

`label` failed every element it saw. A 100% failure rate is exactly the shape of an over-eager check,
so the findings were read individually before being accepted:

| Button reads | Screen reader announces |
|---|---|
| Join | "Submit membership application" |
| Renew | "Extend the loan period on every item" |
| Pay | "Settle outstanding charges" |
| Report | "Tell us your card is lost" |
| Freeze | "Suspend borrowing temporarily" |

WCAG 2.5.3 requires the visible label to appear in the accessible name. Someone operating by voice
says *"click Renew"*, the browser matches against the hidden name, and nothing happens. Meridian
carries one construction mistake repeated across the site. **The check is correct; the site is
consistently wrong.**

### 8.4 The stall that was not a stall

At 12 minutes with the verdict counter reading zero, the observer began investigating a suspected
stall. The verdicts were being written under the **judge run's** id; the counter was querying the
**audit's** id. Wrong drawer.

```
judge run started 02:25:19
FIRST VERDICT     02:26:45   ← 86 seconds later
rate              6.8 / min  (31 August ran 5.7 to 6.4)
```

Nothing had ever been stuck. Recorded because the instruction that prevented it reaching the team as
a finding — *wait, confirm, root-cause, then report* — is the operative lesson, and the root cause
was the observer.

### 8.5 How pass 1 ended

At 04:11:25, at element 626 of 800:

> `API Error: Can't reach the API server — check your internet or DNS (ENOTFOUND)`

A network failure on the machine running the companion. The same event made the observer's database
probes time out between 03:55 and 04:11 — one cause, two symptoms. **Not a platform fault.**

The platform's response was correct: 174 elements were filed as `uncertain` carrying the text *"the
accessibility judge finished without reporting on this element"* and routed to human review rather
than being silently treated as passing. The report and the baseline were both written.

## 9. Pass 2 — 04:39:39 to 05:38:32

**Dispatched 442, deferred 0** — the 268 never asked plus the 174 the network took. It fitted in one
pass under the 800 cap.

The repair was visible as two distinct movements: `uncertain` falling 174 → 2 as placeholders were
overwritten with real answers, and the cache total rising past 800 as never-asked elements were
judged for the first time.

It ended at element 398 of 442:

> `Screen 36 complete (398/442). Fetching screen 37.` **`You've hit your session limit · resets 12pm`**

A subscription session limit. **Again not a platform fault, and a different cause from pass 1** —
worth stating plainly, because two stoppages in one day invite the assumption of a single underlying
defect.

## 10. Pass 3 — 07:32:21 to 07:48:04

**Dispatched the final 44.** Completed in 15.7 minutes.

```
pass 968 | fail 100 | unanswered 0
```

**968 + 100 = 1,068.** Every question the audit asked has a real answer. This is the first fully
complete state across the three passes.

| | Unanswered |
|---|---|
| After pass 1 | 174 |
| After pass 2 | 44 |
| **After pass 3** | **0** |

## 11. The ledger — the one genuine engineering finding

**Symptom.** After pass 2 the screen showed 370 problems and 106 awaiting review. Those were pass 1's
numbers. The report document had regenerated at 05:39:38; the ledger had not.

**Proof.** All 476 ledger rows were created *and last touched* between 04:13 and 04:16. Pass 2
finished at 05:39. Not one row moved.

**Diagnosis.** `record_run_findings` was run as a dry run inside a rolled-back transaction — nothing
was written:

```
merge_run           :   8.3 s
record_run_findings : 427.3 s   ← and it SUCCEEDS
   would open      76
   would see again 377
   would resolve   99
```

The function is not broken. It is **slow**, and it sits in a best-effort wrapper whose captured error
travels on the activity's return value — **which a failed run never persists**. So when it does not
complete, nothing anywhere says so.

**Confirmed on pass 3.** The write ran and completed normally, moving the queue 106 → 98 → 2 and open
problems 370 → 395 → 410. The failure was therefore specific to the moment a failing run tore down,
not a permanent fault.

> **Carry forward.** A multi-minute ledger write, wrapped in a handler whose error is lost precisely
> when the run fails, left the screen wrong for 80 minutes with no signal anywhere. The write itself
> is correct. The **silence** is the defect. Logged in `GAP_FIX_BUILD_PLAN.md`.

### 11.1 What the ledger did when it ran

| Bucket | Count |
|---|---|
| opened | 76 |
| seen again | 377 |
| **needs_review resolved** | **96** |
| failure resolved | 3 |

**A finding is closed only where we actually looked and it was gone.** A page not visited is
untouched; an element captured but never judged is untouched — *"we did not get an answer"* is not
*"the problem is gone"*. That rule is why the 44 unanswered elements did not have their problems
silently marked as fixed after pass 2.

## 12. Final state — 07:47:59

**94 pages · 2,177 elements · 1,068 questions · 0 unanswered**

| Check | Pass | Fail |
|---|---|---|
| color | 507 | 16 |
| semantics | 299 | 20 |
| structure | 71 | 20 |
| **graphics** | **59** | **0** |
| alt | 32 | 24 |
| label | 0 | 20 |
| **Total** | **968** | **100** |

**410 open problems** — 105 critical, 305 high. **2 awaiting a person.**

| Source | Open failures |
|---|---|
| Automatic scanner | 310 |
| alt | 24 |
| label | 20 |
| structure | 20 |
| semantics | 20 |
| color | 16 |

**The 2 in the review queue are both `graphics` at 0.78 confidence** — the same study-carrel
illustration on `/about/our-buildings` and `/about/reading-rooms`. The judge decided it passes and
was not confident enough for that to be banked as a claim, so it went to a person. These were the
only two low-confidence passes in 1,068 judgments; average graphics confidence was 0.938. **This is
the platform declining to make a conformance claim on a shaky answer, which is correct behaviour.**

### 12.1 Time and cost

| | |
|---|---|
| Capture | 29.5 min |
| Judging, active | 181.2 min |
| **Active work total** | **210.7 min — 3 h 31 m** |
| Wall clock, start to finish | 357.3 min |
| Engine cost | **$37.18** |

The difference between active work and wall clock is the two stoppages and the waiting between
passes. The cost is engine-reported; runs execute on the Claude Code subscription with the API key
dropped at runtime, so this is a usage figure and not an invoice.

## 13. Errors made by the observer during this run

Three, all either caught before reaching the team or corrected shortly after.

**13.1 A wrong-key query read as a 12-minute judging stall (§8.4).** Verdicts were counted under the
audit id; they are stored under the judge run id.

**13.2 A density alarm built on a mismatched baseline (§6.2).** Today's whole capture compared
against 31 August's capped first pass. Never reported as a finding; killed by measurement.

**13.3 The ledger, twice.** First reported as empty when it was in fact mid-write — a timing artefact,
and wrong. Later, a "60-second rule" was invented to explain the gap between a run ending and the
document being written. **No such rule exists.** The 66 seconds was an observation; presenting it as
a mechanism was the same error as 13.2 — naming a cause before measuring one. Retracted in full. The
underlying finding in §11 stands on its own evidence.

**The pattern in all three:** an inference presented with the confidence of a measurement. The
instruction that governed this run — *wait, confirm, root-cause, then report* — caught the first two
before they became findings and forced the retraction of the third.

## 14. What remains open

| Item | Where it stands |
|---|---|
| **`graphics` has never reported a failure** | 59 pictures, 59 passes, two of them low-confidence. Same shape as 31 August. Without an expert answer key there is no way to distinguish "Meridian's illustrations are genuinely fine" from "the check is lenient". Recorded so the first failure it reports is read as news rather than noise. |
| **1.4.11 has no accuracy evidence** | Fully wired and fully guarded, but holds zero answer-key records against 31 to 42 for every other check. Ships **judged but not measured**, which the team accepted. Cannot be closed by code: the labeller must not be the checker's author. |
| **The whole answer key is unadjudicated** | Every record still reads `draft-unadjudicated`. Any accuracy figure drawn from it measures agreement with a careful draft, not correctness. Largest open item in the capability. |
| **New-tenant judging cap** | §7. A new tenant silently inherits 200. |
| **Silent ledger-write failure** | §11. The write is correct; the silence is not. |
| **Two review items** | §12. Genuine judgement calls awaiting a person. |
