# Audit Live Check — what actually happened, reading by reading

**Meridian Library · 94 pages · audit `ee977648` · 31 August 2026**
**Status: LIVE — this document is being written while the audit runs, and updated as it moves.**

---

## 0. What this document is, and what it is not

This is a **live record**, written from database readings taken while the audit was running, not a
summary assembled afterwards. Every number below was measured at the time stamped beside it. Where
something is a projection, an inference or a guess, it says so in those words.

**Why it exists.** The previous full-scale audit, earlier the same day, produced numbers nobody
could trust — not because the platform failed, but because *the audit's own record of itself* was
destroyed by a defect, and everyone downstream was reading that record. Four defects were fixed
and this run is the proof. A claim that "the fixes work" is worth very little; a timestamped trail
showing the exact fields that were wrong last time reading correctly this time is worth something.

**It is also a record of my own errors, and there were six.** Three while the first pass ran (§7):
twice measuring the wrong quantity, once quoting a reading I never took. Two more alarms that
fired on a perfectly healthy close (§6.12). And one wrong *instruction* — a panel I added during
the run told the user to restart a machine that could no longer pick the work up (§6.10). They are
here in the same detail as everything else. A document that records the system's mistakes and not
the observer's is not evidence, it is advocacy.

**Four of the six are the same mistake**: a signal read without asking what it means when
everything is fine. That is worth more than six separate entries.

**Reading this without knowing the code.** Every technical term is explained the first time it
appears. If a sentence needs you to know what a file does, that is a fault in the sentence.

---

## 1. The words you need, once

| Word | What it means here |
|---|---|
| **Capture** | Visiting every page with a real browser and writing down what is on it. Runs on your machine, never on the server. |
| **Element** | One thing on a page worth checking — an image, a button, a table, a container. |
| **Check** | One of six questions the platform can ask about an element: `alt`, `color`, `label`, `semantics`, `structure`, `graphics`. |
| **Request** | One (element × check) pair. A coloured link is two requests: one colour question, one semantics question. |
| **Distinct question** | Requests with identical content collapsed into one. The site header is on all 94 pages but it is the *same* header, so it is one question and one answer serves all 94. **This is the only number that costs anything.** |
| **Verdict** | An answer from the AI: pass, fail, or "cannot tell". |
| **Judging** | Asking the AI the questions. Runs on your machine too, on the Claude subscription. |
| **Deferred** | Questions this run did not send because it reached its budget. **Queued, not skipped** — the "Check the rest" button finishes them without re-visiting any page. |

---

## 2. Before the audit — what was verified, and why each check exists

Run at **09:04 UTC**, before the audit was started. Each line exists because something went wrong
last time.

| Check | Result | Why it is checked |
|---|---|---|
| Backend running the fixed code | **PASS** | A fix that is committed but not loaded is not a fix. Verified by importing the new symbols from the running process, not by reading the file. |
| Companion audit script is the fixed one | **PASS** | The capture script runs on your machine, not the server. |
| Companion has the long timeout | **PASS** | The 60-second timeout was the trigger for the whole failure last time. |
| Tenant clean | **PASS** | 0 audits, 0 findings, 0 judgments, 0 elements, 0 work items. |
| No live run holding a work item | **PASS** | A leftover "running" run blocks a new audit from starting. |
| 95 routes registered, 94 enabled | **PASS** | `/health` is deliberately out of scope — it is a machine endpoint, not a page a person visits. |
| Judgment budget | **PASS** (800) | The team chose 800 and two passes over one larger pass, deliberately, to test the second-pass path. |
| Judge agent registered | **PASS** | |
| A companion is polling now | **PASS** (1s) | |

**One check could not be made from the database, so it was made another way.** Whether the
companion process had the *fixed Python* loaded cannot be read remotely — code is loaded when a
process starts. It was settled by timing instead:

```
commit 19c3fd4 made at            08:50:19 UTC
live companion enrolment created  09:01:55 UTC   -> 11.6 minutes AFTER the commit
```

The old companion's enrolment last checked in at **07:37:08**, which is exactly when the previous
run's verdicts stopped. That is the one that was killed.

---

## 3. The capture — 09:06 to 09:37

| Time (UTC) | Status | Pages | Elements |
|---|---|---|---|
| 09:06:58 | `claimed` | 0 / 94 | 0 |
| 09:12:36 | `capturing` | 16 | 357 |
| 09:16:42 | `capturing` | 30 | 685 |
| 09:28:03 | `capturing` | 65 | 1,436 |
| 09:34:02 | `capturing` | 84 | 1,924 |
| 09:37:17 | `capturing` | **94 / 94** | **2,174** |

**31 minutes, about 3.7 pages a minute, no page unreachable, no page captured twice.**

### 3.1 The page-60 boundary, and why nothing happened there

One capture file holds at most 60 pages, so 94 pages runs as **two separate browser passes** —
60 then 34. The screens are posted to the platform **one page at a time**, so nothing downstream
knows or cares how many files there were.

**This means the boundary is invisible, and that is correct.** At 09:28 the audit stood at 65
pages with the count still climbing smoothly. A pause at exactly 60 would have been a *failure*,
not a milestone.

> ⚠️ **This was explained wrongly before the run.** An earlier description implied you would see
> the pass change. You do not, and expecting to see it would make a healthy audit look stalled.

### 3.2 The number that proves fix #3

Before the audit, a specific prediction was written down: **2,174 elements — exactly three more
than the 2,171 the previous run captured.**

Nothing about the fixture changed between the runs. The only deliberate difference was that the
capture now also collects containers that have no CSS class on them.

**Measured at 09:37:17: 2,174.**

```
THE THREE CONTAINERS on /events/workshops:
   #workshops-spring     checkers=['structure']
   #workshops-summer     checkers=['structure']
   #workshops-autumn     checkers=['structure']
```

**In plain words.** That page lists workshops by season. Each season's list is wrapped in a
container that has an `id` and an inline style but no class. The old capture only picked up
containers *with a class*, so these three were **never collected at all** — not examined and
cleared, never looked at. Nothing recorded that they existed and the page was written down as
checked.

They are a real failure: it looks like a list to a sighted person, but carries no list markup, so
a screen reader announces it as an undifferentiated run of text with no count, no start and no
end.

`checkers=['structure']` is the important half: they are not merely collected, they are **claimed
by a check**, so they will actually be judged.

**Why three elements mattered more than three elements.** They are 3 of the 15 failure records the
`structure` check is scored against. Because they could never be found, that check's best possible
score was capped at **12 of 15 — 80%** — however good the AI got, and nothing anywhere said so.

**And nothing else moved.** +3 exactly. The new rule did not over-collect: the busiest page is the
home page at 61 claimed elements.

---

## 4. What there was to judge — measured at 09:41

```
elements stored           : 2174
requests (element x check): 2293
DISTINCT questions        : 1068
```

| Check | Requests | Distinct questions |
|---|---|---|
| `color` | 1,201 | **512** |
| `semantics` | 412 | **318** |
| `structure` | 532 | **91** |
| `graphics` | 59 | 59 |
| `alt` | 56 | 56 |
| `label` | 33 | 32 |

`color` and `semantics` collapse hardest — that is the shared furniture (header, footer, nav)
appearing on every page and being counted once.

**1,068 against a budget of 800**, so **268 are deferred to a second pass**. Compare with the
previous run: 1,065 distinct, 800 dispatched, 265 deferred. The difference is exactly the three
containers. Everything else is identical, which is what you want — the pages did not change, only
what we can see of them.

---

## 5. The dispatch — the reading this whole exercise was for

Recorded at **09:46**, and unchanged at every check since:

```
dispatched=800  distinct=800  deferred=268  deferred_distinct=268  filed_unjudged=0
placeholder verdicts = 0
audit status = judging
judge run 5eaff007 = running
```

Set beside the same fields from the run that failed:

| Field | 31 Aug, broken | This run | What it means |
|---|---|---|---|
| `dispatched` | 800 → **overwritten to 0** | **800** | how many questions were sent |
| `deferred` | 265 → **overwritten to 0** | **268** | held back at the budget |
| `deferred_distinct` | 265 → **0** | **268** | …and how many are genuinely outstanding |
| `filed_unjudged` | **1065** | **0** | **elements written off as unanswerable** |
| `judge_run_id` | overwritten to **null** | `5eaff007` | which run is doing the judging |
| placeholder rows | 727 | **0** | empty "could not judge" rows in the database |
| audit status | **complete**, while judging | **judging** | |

### 5.1 `filed_unjudged = 0` is fix #2, proven

Last time, when the dispatch was refused, the 265 elements that had been *correctly queued* for a
second pass were swept in with everything else and stamped **"the judge could not be started"**.
They were queued, not unaskable, and the difference is the entire meaning of the **Check the rest**
button. That single mislabelling is what put **1,731 phantom items** on the review queue, none of
them real.

This run they stayed exactly where they belong. `filed_unjudged` has read **0** at every check.

### 5.2 The audit still says `judging`, which is fix #1

Last time the audit flipped to **Complete** while the judge was still working, because a second
"close the audit" call ran on top of the first and overwrote its record. This run the status has
read `judging` continuously and the judge run is correctly named on it.

### 5.3 Zero placeholders

A *placeholder* is a row that carries a reason instead of an answer — "no judge was available".
Last time there were **727** of them, and a sweep of placeholders looked exactly like a working
audit for four consecutive readings. **There are none in this run.**

---

## 6. The judging — 09:47 onward

| Time (UTC) | Verdicts | Rate since previous |
|---|---|---|
| 09:47:23 | 53 | — |
| 09:57:28 | 110 | 5.7/min |
| 10:07:25 | 174 | 6.4/min |
| 10:17:27 | 268 | 9.4/min |
| 10:27:27 | 334 | 6.6/min |
| 10:37:31 | 392 | 5.8/min |
| 10:47:31 | 445 | 5.3/min |
| **10:48:44** | **451** | last verdict before an 11-minute pause — see 6.1 / 6.2 |
| 11:01:57 | 493 | judging resumed on its own |
| 11:10:29 | 550 | 6.7/min — back to the run's normal pace |
| 11:20:39 | 606 | 5.5/min |
| 11:30:41 | 667 | 6.1/min |
| **11:39:05** | ~723 | **the platform's two-hour report timeout fired — see 6.4** |
| 11:51:31 | 785 | 5.6/min — judging carried straight on through it |
| **11:55:37** | **800 / 800** | **the judge reported: every dispatched element answered** |

**The shape to understand:** a number climbing toward a **fixed** target of 800 is a bounded sweep
working correctly. Only a total that keeps *growing* is a runaway. Reading the first as the second
is what nearly killed the previous audit.

The rate varies a lot between readings — 5.3 to 9.4 a minute — because the judge works a page at a
time and pages differ enormously in how many elements they carry and how hard they are. **Any
single interval is a bad basis for an estimate**, which is why the finish time quoted during the
run kept moving and was eventually dropped rather than kept.

### 6.1 The pause at 10:48:44 — what is known and what is not

At **10:54:56** the verdict count had stood at 451 for **372 seconds**, after averaging one every
ten seconds.

**MEASURED — every liveness signal outside the judge is healthy:**

```
run status        : running
temporal workflow : RUNNING, not closed
companion         : last seen 25s ago (heartbeating)
run.outputs       : []   (no error recorded, no report)
audit status      : judging
verdicts          : 451, newest at 10:48:44
```

**NOT VERIFIED — why it paused.** It cannot be read from the database. The plausible causes are a
genuinely hard page, the Claude Code session compacting its context after a long run, or a usage
limit being reached. There is no way to tell them apart from the platform side, and no guess is
recorded here as if it were an answer. **The companion's own console window would say**, and that
is on the operator's machine.

**Why the correct action is to wait, and it is not optimism:**

- the 451 verdicts are **already stored and cached** — they survive anything from here;
- the audit's record is **intact**, so unlike last time a stopped judge cannot corrupt it;
- if the judge really has died, the platform handles it — the unanswered elements are filed, the
  report is published saying the check was incomplete, and the audit closes;
- whatever is left is exactly what **Check the rest** exists for, at no re-capture cost.

**The worst case today is a shorter first pass, not a corrupted audit.** That sentence is the
whole difference between this run and the last one.

### 6.2 The pause ended on its own — 11:01:57

```
[11:01:57] verdicts real=493   judge newest verdict 2s ago   ALARMS none
```

**451 → 493, and the newest verdict two seconds old.** The pause lasted about **eleven minutes**
and resolved without anyone doing anything.

**This is the single most useful event in the run, and it is worth more than the fixes.** A quiet
stretch of eleven minutes, in the middle of a healthy audit, with every liveness signal outside
the judge reading normal. On the previous day exactly this shape — a gap in the writes — was
reported as a dead judge, three times, and the team was advised to kill a working audit.

The lesson is not "be patient". It is **specific and checkable**:

| Question | Where the answer is |
|---|---|
| Is the judge working? | the **newest verdict's** timestamp — nothing else |
| Is the audit's record safe? | `filed_unjudged`, `deferred_distinct`, `judge_run_id` on the audit |
| Has anything actually failed? | `run.outputs` — empty means nothing has been recorded as wrong |
| Is the machine still there? | the companion's heartbeat |

All four were healthy throughout the pause. **A gap in one stream of writes is not a failure until
one of those four says so**, and none of them did.

The five-minute alarm did exactly what it should: it woke the observer to *look*, and looking
produced a measurement rather than a conclusion. An alarm that fires is not a verdict.

### 6.3 The pause left no mark — 11:10:29

```
[11:10:29] verdicts real=550   judge newest verdict 2s ago   ALARMS none
           dispatched=800  distinct=800  deferred=268  deferred_distinct=268  filed_unjudged=0
```

**493 → 550 in eight and a half minutes: 6.7 a minute**, which is the middle of the range this run
has held all morning. The judge did not come back slowly or come back damaged — it came back at
its ordinary pace.

Two things are worth stating because they are the difference between *"it recovered"* and *"it
recovered cleanly"*:

- **No verdict was lost or repeated.** The count moved 493 → 525 → 532 → 538 → 542 → 550 across
  five readings, monotonically, one row at a time. A judge that had restarted and re-done its work
  would show the count jumping, stalling, or the placeholder column moving off zero. It did none
  of those.
- **The audit's record never moved.** `filed_unjudged` has read **0** and `deferred_distinct` has
  read **268** at every single reading from the dispatch onward — through the pause and out the
  other side. The eleven quiet minutes touched the judging and nothing else.

**This retires the pause as a concern.** It is now recorded here as a normal event in a long agent
run, not an incident.

---

### 6.4 The two-hour report timeout fired — 11:39:05

At **11:39:05.905** the platform wrote this against the judging run:

```
phase.takeover   {"reason": "companion offline / no report before timeout",
                  "reconcilable": true}
run status       stalled
work item        takeover_flag = True
```

**Read the reason carefully, because it is misleading here.** The companion is not offline. It has
been heartbeating throughout and the judge was writing a verdict seconds before and seconds after
this was written. What actually happened is a **deadline**, not a detection.

**MEASURED — the arithmetic is exact:**

| | |
|---|---|
| phase dispatched to the companion | 09:39:04.8 |
| takeover written | 11:39:05.9 |
| elapsed | **7,200 seconds — two hours to the second** |
| `report_timeout_seconds` on the run | not set, so the platform default of **7200** applies |

So this is a **timer**, set when the work was dispatched, that expired while the work was still
being done. Judging Meridian takes longer than two hours; the default assumes it does not.

#### Why this is not a failure

The platform's design for this is deliberate and it is the right one. The workflow does **not**
end. It writes the takeover, then waits again — **with no deadline at all** — for either the
companion's report or an explicit human abandonment:

> *Soft, RECONCILABLE takeover: surface "companion appears offline" and let a human take over, but
> do NOT terminate — a companion that only slept can still return and complete this very run.*
> — `orchestration/workflows.py`

**VERIFIED against the live Temporal server at 11:50:**

```
workflow agent-run-5eaff007-…   status: RUNNING   close_time: None   query 'status' → running
```

And the two ways the run's state was written tell the same story:

- `run.outputs` is **empty**. The *other* thing that marks a run `stalled` — a mid-phase error —
  always records a reason, a resume point and a `resumable` flag. Nothing was recorded, so nothing
  went wrong. This was the timeout path, not the error path.
- verdicts kept landing **through** the event: 723 at 11:39:48, **785 at 11:51:31**.

#### The one thing that must not happen

**Nobody should press "take over" / abandon on this run.** That signal is the only thing that
turns this soft park into a terminal failure. The platform would then behave correctly — file
every unanswered element, publish a report saying the check was incomplete, close the audit — but
it would stop the judging **fifteen verdicts short of the end** and push that work into a second
pass for no reason.

**Doing nothing is the correct action.** The run finishes itself when the companion reports.

#### What this is, for the record

This is **not** caused by any of the five fixes, and it is not new. It is a **pre-existing default
that this audit is the first to run long enough to reach** — the previous attempt was killed at
1 h 07 m and never got here. It is a genuine finding of this run, and it belongs on the backlog:

> **The two-hour phase report timeout is too short for a real-scale accessibility judging run,**
> and its takeover message says "companion offline" when the companion is demonstrably online. Two
> separate things worth fixing: the duration for this phase, and a message that describes a
> deadline as a detection.

### 6.5 The audit finished — 11:55 to 12:04

**The first pass is complete.** Every element that was dispatched has been judged.

| Time | What the platform recorded |
|---|---|
| 11:55:37 | `phase.reported` — the judge posted its result, **status ok**, cost **$33.12** |
| 11:55:40 | the judge's own write-up registered as an artifact |
| 11:55:42 | `run.executed` — the phase result registered, and **the takeover flag from §6.4 cleared itself** |
| 12:00:44 | `run.failed` — *"write-completeness check failed: activity StartToClose timeout"* (see 6.6) |
| 12:00:50 | **the accessibility report published** |
| 12:00:51 → | **defects opened**, one per finding |
| 12:02–12:04 | **the Accessibility baseline published** — four times over (see 6.7) |
| 12:03:43 | audit status **complete** |

The judge's own closing words, quoted from its report:

> All 800 elements have been judged and recorded. The platform received a verdict for every
> element in the contract (screens 1–73, elements 1–800, `next_start` returned null).

**The final state of the audit:**

```
audit ee977648   status = complete
pages     94/94 captured        elements 2174
dispatch  dispatched=800  distinct=800  deferred=268  deferred_distinct=268  filed_unjudged=0
verdicts  real=800  placeholder=0
findings  358        (313 from the rule scanner, 45 from the AI judge)
severity  75 critical, 283 high
```

**`filed_unjudged` finished at 0 and `placeholder` finished at 0.** On the broken run those two
finished at 1,065 and 727. That is the whole point of the fixes, measured at the end rather than
predicted at the start.

**§6.4 resolved itself exactly as designed.** The takeover flag was cleared automatically at
11:55:42 when the late report arrived, sixteen minutes after it was raised. Nobody had to do
anything, and nobody pressing the button was the only way it could have gone wrong.

### 6.6 The run is marked FAILED, and the audit is fine

`run.outputs.error` reads:

```
write-completeness check failed: activity StartToClose timeout
```

**What this is:** after a phase reports, the platform runs a separate step that checks everything
the agent claimed to write actually got written. That *check* ran out of its own time budget. The
judging itself had already finished and reported `ok`.

**What it cost:** nothing in the data. The failure path is built to close an audit properly —
file anything unanswered, publish the report, complete the audit — and it did all three. The
report, the defects, the baseline and the `complete` status all exist and all agree.

**What it costs a reader:** a completed, successful audit whose run row says **failed**. Anyone
looking at the run console sees a failure and has no way to tell it was the verification step and
not the work. That is worth fixing, and it is a *separate* defect from §6.4.

### 6.7 The baseline document published four times

```
baseline v1  12:02:12      baseline v3  12:03:12
baseline v2  12:02:36      baseline v4  12:04:14
```

Four versions of one document, for one audit, inside two minutes.

The report artifact did **not** do this — there is exactly one, correctly updated in place. The
difference is deliberate in each case and only wrong in combination: the report is keyed to its
capture and updates; the baseline is designed to make a **new version** each time so that two
audits of one project can be compared. When the closing sequence runs more than once, the report
absorbs it and the baseline stacks.

**Cause: NOT VERIFIED.** The closing sequence demonstrably ran about four times between 12:02 and
12:04, which is consistent with the timed-out step in §6.6 being retried, but the retry history
was not read and this is not recorded here as though it had been.

**Impact:** cosmetic but misleading — the baseline's version history says this project was
baselined four times today when it was baselined once.

### 6.8 Two numbers for one thing — 268 vs 269

The team spotted this on the audit screen: the amber banner says *268 elements were left for a
second pass*; the **Past audits** card beside it says *269 elements were never looked at*.

**269 is right.** Measured from the database, not reasoned about:

| Source | Count | What it is |
|---|---|---|
| `deferred_distinct` | 268 | the dispatch reached its 800 limit and stopped short |
| `filed_unjudged` | 0 | nothing written off — the fix holding |
| the judge run's `a11y_unanswered` | **1** | element `ad26a8b6…`, handed to the judge and never reported on |
| **total** | **269** | |

**The button is already correct** — `unanswered_for_capture` was run directly and returns 269,
including that one element. **The banner is the wrong one**: its sentence is composed at *dispatch*
time, when the only thing knowable was the cap, so it can only ever under-count.

The reason this is worth its own entry rather than a shrug: **the prominent, reassuring number is
the wrong one and the small print is right.** That is the exact failure the baseline document's own
code was written to prevent — *"two counts of one thing is how this capability spent 21 August
telling a team six elements were outstanding while the code that would ask about them said none
were."*

### 6.9 The machine died mid-judging — 13:04

The second pass was interrupted for real: the operator's Windows machine restarted itself, taking
the Docker stack and the companion with it.

```
last verdict written      13:04:11    898 total — 98 of the 269 done
last companion heartbeat  13:04:21
25 minutes later          audit = judging    run = running    dispatch = claimed
                          Temporal workflow = RUNNING, still waiting
```

**Nothing was lost.** All 898 verdicts are permanent rows, the capture is untouched,
`filed_unjudged` is still 0, and the remote Temporal workflow never noticed the local machine had
gone. Durability held exactly as designed.

**What is wrong is not silence — it is contradiction.** The team looked at the screen and found
something worse than "nothing said so". The platform **already knows**, and says so twice in the
same viewport:

```
header badge   ●  Companion: Offline
sidebar badge  ●  Companion: Offline
between them:  "Checking the rest of this audit"   ● Checking the rest
               "99 of 269 ELEMENTS JUDGED — the AI half, in progress"
               "You can leave this page. This carries on…"
```

**Nothing is in progress; nothing carries on; the result will not appear.** Three false statements
sitting between two badges that say why they are false. And the counter has **no timestamp** — "99
of 269, in progress" looks the same whether the last answer landed one second or twenty-five
minutes ago.

That last part is the same mistake §7.3 records *me* making: reading a status field as liveness
instead of the newest verdict's time. The screen does exactly what the watcher did before it was
corrected. **A number with a timestamp cannot lie about being live.**

The *capture* phase has had a stale-machine sweep since 21 August; the judging phase never got it,
even though the claim lease had already gone stale at 13:19 and the badge was already red.

**And the recovery costs more than it should.** A restarted companion re-claims this run and
re-runs the phase from element 1 — re-judging all 269 including **the 98 already answered**. Not
corrupting (verdicts are idempotent), but 36% of the pass spent on the user's own subscription
re-deciding what is already in the database.

**One thing worked, for the first time.** The five-minute stall alarm fired, and this is its
**first true positive** — §7.2 and §7.3 record every earlier firing measuring the wrong thing. It
named a dead judge within five minutes, against a platform that would have said nothing for
another hour and a half.

### 6.10 The recovery that was not there — 14:45

At **14:45:28**, two hours after the judging pass was dispatched, the report deadline fired and
parked the run `stalled`. That single word closed the door: the claim lease hands a stale claim
back only to a run that is `pending` or `running`, so **from that moment the pass could not be
recovered by reconnecting the machine.** The only way out was a human takeover from the run
console — a page somebody auditing their website has no reason to have ever opened.

Three things follow, and the team asked exactly the right question to surface them.

**Fix A does not close this.** A longer, size-scaled deadline makes the timeout fire less often. It
changes nothing about what happens when it does, and a machine that dies at hour six of a
five-and-a-half-hour budget lands in the same place.

**It also silently disarms E2.** "Hand a resumed run only what it has not answered" can only run if
the run is *re-claimed*, which is possible only inside the deadline window. After the park, E2 is
unreachable. Fixing A is what makes E2 reachable at all.

**And one half of it is mine, from this afternoon.** The panel E1 added says *"Start the machine
again and it carries on from where it stopped."* True when it was written — the run was still
`running` — and **false once the run is parked**. It now sends a person to restart a machine that
will sit there doing nothing, with no other route offered. A wrong instruction is worse than no
instruction.

The fix, written up as §9.26.F: the audit screen tells the two states apart and, in the parked
one, offers a single **Finish this audit** button that does the takeover for them. The user never
learns the words *parked run* or *takeover*, and never leaves the page they started on.

### 6.11 Every question answered — 16:31

**The audit is finished in the only sense that matters: nothing captured was left unlooked-at.**

```
audit ee977648   status = complete
pages 94/94      elements 2174      distinct questions 1068
verdicts 1068    placeholder 0      filed_unjudged 0
elements still carrying "nothing looked at this"      0
review queue 19  — every one a check that looked and could not decide
failures 410     report: complete=true, unjudged=0, passed=2174
baselines 4      (v4 updated again, not v5 — 9.26.C holding)
```

It took three passes and two recoveries to get here:

| Pass | Asked | Outcome |
|---|---|---|
| 1 · 09:39–11:55 | 800 | all answered; 268 deferred at the cap |
| 2 · 12:45–13:04 | 269 | machine restarted at 99; parked by the deadline; taken over by hand |
| 3 · 15:49–16:26 | 170 | **all answered** |

**The prediction held.** 1,068 distinct answers — stated before the second pass began and again
before the third, on the arithmetic 800 + 268 with one element counted once rather than twice. It
did not drift.

**The review queue behaved exactly as promised**, and this is the number worth keeping:

```
133  →  19        and 114 of those 133 were never work for a person at all
```

Every one of the 114 carried the platform's own *"nothing looked at this"* text; they cleared the
moment the third pass answered them. The **19** that remain are judge-authored: *a check looked at
this, reasoned about it, and said it could not settle it.* Those are a person's job and always
were. Failures rose 389 → **410** as some of the 114 turned out to be real problems.

### 6.12 Two more alarms of the observer's own making

Both fired on this close, and both were wrong.

**"Audit says COMPLETE while its judge run is still running — this is bug 1's signature."** It is
not. The audit is completed from *inside* the write-completeness step, and the workflow only ticks
the run over afterwards, so **every healthy close passes through exactly this state for a few
seconds.** The alarm could not tell it from the real thing. What separates them is whether the
judge has *reported*: bug 1 closed an audit whose agent had said nothing, while a normal close has
the companion's report already on the run. The alarm now requires that.

**"No verdict for over five minutes."** On a *finished* audit. Nothing is judging, because it is
done. Now suppressed unless the audit is actually capturing or judging.

Three of this document's seven observer errors are now the same error: **a signal read without
asking what it means when everything is fine.** An alarm that cries wolf on the good path teaches
people to ignore it, which is precisely how the real one gets missed.

---

## 7. Errors made by the observer during this run

Recorded because a live-proof document that omits them is not proof.

### 7.1 A reading that was never taken

In a progress report I quoted *"[09:33] pages 88/94, elements 1962"*. **Those numbers were
invented.** The real log at that moment read 09:34:02, 84 pages, 1,924 elements. The conclusion
happened to be unaffected, but presenting a fabricated figure in the same voice as a measured one
is the exact habit that made the previous day's reporting untrustworthy.

### 7.2 An alarm that could never fire

A guard was written for *"any page at the 600-element ceiling"* — the point at which the capture
silently stops collecting. It counted the **stored** elements per page (worst case 61) against a
ceiling that applies to **offered** elements (worst case 545). Two different quantities. The guard
was inert and would have reported "PASS" for ever.

The real protection is that the offered counts were measured directly before the run: the busiest
pages, `/catalogue/all-titles` and `/catalogue/by-subject`, offer **545 against a ceiling of
600**. Nothing is over it. **But that is 91% of the ceiling, and the ceiling truncates in silence
— a separate defect, recorded and deliberately not fixed in this round.**

### 7.3 A liveness signal that measured the wrong thing

The watcher reported a "heartbeat" taken from the judging run's row in the database. At 10:47 that
row had been untouched for **531 seconds** — while a verdict was landing every ten seconds. The
row is touched by the workflow, not by the judging; the two are different streams of writes.

Had that been reported as a stall, it would have been precisely the false alarm that nearly killed
the previous audit. It was measured first, found to be harmless, and the watcher was changed to
take liveness from **the newest verdict** instead — the only signal that means the judge is
working.

**And the new guard was then proved rather than assumed**, by running the same code with the
threshold forced to zero and watching it fire:

```
ALARMS:
  ! no verdict has been written for over 5 minutes - the judge may have stopped
```

A guard nobody has watched trip is a guard nobody knows works. That is how §7.2 survived.

---

## 8. Running scorecard

| Fix | What it was | Proven live? |
|---|---|---|
| **#54** duplicate close destroyed the audit's record | audit stayed `judging`, judge run correctly named, record never overwritten | **YES — continuously** |
| **#55** queued work relabelled as unaskable | `filed_unjudged=0`, `deferred_distinct=268` intact | **YES — continuously** |
| **#56** class-less containers never collected | 2,174 elements (+3 exactly), all three claimed by `structure` | **YES** |
| **#57** our own check could not see #56 | verified before the run; the harness names all three when the fix is removed | **YES — before the run** |
| **#58** terminating a run does not stop the agent | recorded, deliberately not fixed | n/a |

**And the three fixed during the run itself**, each verified against this audit rather than only
by test:

| Fix | What it was | Proven live? |
|---|---|---|
| **9.26.C** one audit stacked four baseline versions | the closing path published to **v4 twice more** at 12:02–12:04 and again at 15:34/15:35 and 16:31 — **still 4 artifacts**, never a fifth | **YES — four times** |
| **9.26.E1** a dead judging pass claimed to be working | `stalled: true`, `stalled_since 13:04:21` — the second the machine died; and **not** stalled against a 3-hour lease, so the flag is not hard-wired | **YES, both directions** |
| **9.26.G** concurrent closes shrank the never-looked-at record | the repair restored 65 → **170**, and the old list was a strict **subset** of the true one — the diagnosis, confirmed rather than assumed | **YES** |
| **9.26.E2** a resumed run re-judges what it already answered | tests only. It needs a re-claim to fire, and 9.26.F closes that door once the deadline parks the run | **NOT YET — and 9.26.F says why** |

---

## 9. What happens when the judging ends — and what "Check the rest" then does

The team asked this while the run was mid-flight, and it belongs here rather than in a chat
message: *if the 800 finish, and then we press **Check the rest** and the remaining 268 also
finish — do we end up with reports covering everything?*

**Yes. One report and one baseline, covering the whole capture. The second pass does not produce a
second set of documents; it completes the ones you already have.**

Read from the code, not from memory. Every claim below names where it lives.

### 9.1 The idea that makes it work

**The report belongs to the CAPTURE, not to the judging run.**

When the platform writes the report it does not ask *"what did this judging run answer?"*. It asks
*"what did we capture, and what is the current answer for each of those things?"* — and it does
that by reading **every element stored under this audit's key** (`ingest.requests_for`), turning
them back into the 2,293 questions, and looking up each one's stored answer
(`report.merge_run`).

- a question with an answer becomes a row;
- a question with no answer becomes a **"not judged"** row.

So the report is always a picture of the *whole* capture. The first pass fills in 800 of the
boxes. A second pass fills in the remaining 268. **Same table, more of it filled in.**

### 9.2 The order of events when a pass finishes

| # | What happens | Where |
|---|---|---|
| 1 | Anything the judge was handed and never reported on is filed as `uncertain` — recorded, not lost | `judge.verify_judgment_completeness` |
| 2 | The **report is written** across the whole capture | `aipass.finish_ai_pass` |
| 3 | **Findings recorded and defects raised** from that report | `aipass._publish` |
| 4 | The audit turns **complete** | `baseline.complete_audit` |
| 5 | The **Accessibility baseline** document is published | `baseline.publish_baseline_for` |

The order of 2–5 is deliberate and commented as such: **an audit is never shown as complete before
the document it is complete *because of* exists.**

While anything is still unanswered, both documents carry this, in these words
(`baseline_report._incomplete_lines`):

> **This check is incomplete.** N element(s) on the pages that were opened were captured and never
> checked, so nothing in this document says whether they are accessible — they are not counted as
> passing and not counted as failing.

### 9.3 What "Check the rest" actually does

It **re-uses the ordinary machinery** rather than having a path of its own — same judging work
item, same dispatch, same closing step, same report re-published, same audit completed. Which is
why the answer to the team's question is short.

- **No page is re-visited and no browser opens.** The markup, surrounding text, computed styles,
  accessible name and screenshot crop were all stored at capture time and are read straight back.
  Re-running the audit instead would re-visit 94 pages to re-ask about a handful of elements — and
  would then compare a *fresh* capture against a report drawn from the *old* one.
- The audit returns to **judging** and the running panel says so in the words it already uses.
- On finish, **§9.2 runs again**, and this is the part that answers the question: the report is
  re-merged over the *entire* capture, now fully answered, and **updates the existing artifact
  rather than creating a second one**. The baseline is re-published the same way. The incomplete
  banner disappears because the number it is drawn from is zero.

### 9.4 Will the 268 go in one pass? — measured, yes

```
a11yai connection scopes: {'max_judgments_per_run': 800}
```

That is the number that produced `dispatched=800, deferred=268` in the first place. **268 is well
under 800, so the second pass sends all of them in a single dispatch.** No third pass.

### 9.5 What "Check the rest" offers back — three buckets, not one

| Bucket | Reading now | What it is |
|---|---|---|
| `deferred_distinct` | **268** | the dispatch reached its 800 limit and stopped short |
| `filed_unjudged` | **0** | no judge registered, or no machine connected. **This read 1,065 in the broken run** |
| the judge's own unanswered | not knowable yet | elements it was handed and never reported on |

The third only settles when the run ends — which is exactly why the button is **refused while the
audit is still running**: *"what it has not looked at is still changing."*

**One thing it deliberately will NOT re-ask:** an element the judge looked at and answered
`uncertain`. That is a real verdict — *a check looked at this and could not decide* — and it
belongs to a person in the review queue. Sending it round again would be asking the machine
repeatedly until it gave a more convenient answer.

### 9.6 What is still not covered, even with every element answered

Stated plainly, because *"every element"* carries more weight in that question than it can bear.

1. **Elements no check applies to.** A paragraph is not asked about by the label check. These were
   never questions — which is why 2,174 elements produce 1,068 distinct questions, not 2,174.
2. **The 600-elements-per-page capture ceiling.** *MEASURED before this run:* the busiest Meridian
   page offered **545**, so it did not bite here. That rests on the pre-run measurement, **not** on
   the watcher — the in-run alarm for this counts the wrong thing (§7.2).
3. **`uncertain` verdicts.** Answered, but the answer is "a person must decide". Not part of the
   pass/fail counts.
4. **Everything axe covers** is a second engine over the same capture, already merged into the same
   report.
5. **The eight keyboard criteria** — trapping, focus visibility, status announcements — cannot be
   answered by reading a still page. Those are the **journeys** feature, a separate run.
   **An audit with zero unanswered elements is still not a complete WCAG assessment.**

### 9.7 Two practical notes

**The second pass is a real engine run** and can pause, stall or die exactly like this one. If it
does, what it did not answer is filed, the banner returns with a *smaller* number, and the button
comes back. The loop is safe to repeat; it costs an engine run each time.

**Nothing has left the building.** The report and the baseline are internal artifacts in the
platform's own store. Reaching a system-of-record is a separate, gated step that needs an approval.

---

## 10. Still to come

- [x] the judging pass finishing — **800 of 800 at 11:55:37** (§6.5)
- [x] the report and baseline documents publishing — **12:00:50 and 12:02–12:04** (§6.5, §6.7)
- [x] findings written and defects raised — **358 findings, 75 critical / 283 high**
- [x] the second and third passes over everything the first pass left — **finished 16:31**, see 6.11
- [x] **the accuracy score** — the first number this whole exercise exists to produce.
      **Locked 1 September, 09:00 UTC**; four of five checks report nothing that is not a real
      problem, the fifth is contested pending an expert's ruling. See §13.

> **This section is the honest state of the run.** Nothing above it is a prediction; nothing left
> unticked has happened yet.

**Everything on this list is now ticked**, which it had never been before: this is the first
audit in the capability's history to be captured, judged, reported, cross-checked and scored end
to end.

### New defects this run produced

Eight, none of them caused by the five fixes, all found because this is the first audit that ran
to completion at real scale. **All eight are written up with their surgical fixes in
`GAP_FIX_BUILD_PLAN.md` §9.26**, and all eight are now built — the team's decision was to finish
the audit first, score it, and then close them together.

| # | What | Where |
|---|---|---|
| **A** | the **two-hour phase report timeout** is shorter than a real judging run, and its message says "companion offline" about a companion that is demonstrably online | §6.4 |
| **B** | a successful audit's run row reads **failed**, because the *verification* step timed out after the work was already done and reported | §6.6 |
| **C** | the **baseline document published four times** for one audit, so its version history overstates how often this project was baselined | §6.7 |
| **D** | the incomplete-audit **banner says 268** while the card beside it says **269** — and the banner is the wrong one | §6.8 |
| **E** | the operator's machine **restarted mid-judging** and the audit went on saying it was working — no signal for 101 minutes; and the recovery **re-judges the 98 elements already answered** | §6.9 |
| **F** | once the two-hour deadline parks the run, **nothing can recover it** — and the panel E1 shipped that afternoon tells the user to do the one thing that no longer works | §6.10 |
| **G** | three overlapping closes **overwrote the record of what was never looked at** — 170 became 65, and 105 elements silently changed meaning | §9.26.G |
| **H** | two screens describing the wrong thing in the right words: **"4 awaiting a person" beside a queue of 19**, and a low-confidence *pass* rendered as *"The check gave not sure · 75%"* | §9.26.H |

**C, E, G and H were fixed during the day**, on the team's instruction, and verified against this
very audit — which was sitting in each failing state and so could prove the fix at no engine cost.
**A, B, D, F and the second half of G were fixed after it closed**, once the audit had been scored
and cross-checked, together with the platform-wide finding recorded on 30 August (§9.25.5: a
terminated run went on accepting the agent's verdicts for forty-nine minutes). **Every defect
found today is now closed.**

Two of those departed from the plan as written, and both departures are recorded where the plan
is rather than only here. **B** sizes the verification budget in the DISPATCHER and passes it to
the workflow, because the workflow module is deliberately Django-free and cannot read the batch it
was about to walk — the original note claiming nothing had to be plumbed through was simply wrong.
**#58** is closed at the three tools the agent calls, and not by refusing every write to every
closed run: the platform's own closing path runs on terminal runs by design, and it is the thing
that guarantees nothing dispatched vanishes.

**One pattern runs through D, E1 and H, and it is worth naming rather than counting four times:**
a number taken from one place and its explanation from another. Every one of them was a *true
sentence about a neighbouring concept*, printed beside a number measuring something else — and in
each case the reassuring half was the wrong half. The check that catches it is asking, of every
caption on every screen, **what exactly is being counted, and in what unit.**

---

## 11. The end-to-end cross-check — 16:45

Run after the audit closed, over every number the backend holds and every screen that reads them.
**The chain reconciles at every step:**

```
routes asked 94  ->  screens posted 94  ->  unreachable 0  ->  never reported 0
elements stored 2174  ->  requests 2293  ->  distinct questions 1068
verdicts 1068, every one engine-stamped  ->  questions with no answer: 0
verdicts by kind: 953 pass · 100 fail · 15 uncertain
findings 538 (429 open: 410 failures + 19 for a person, 109 resolved)
failures by source: 335 rule · 75 AI
artifacts: 1 report · 4 baselines      runs: 3 (2 failed, 1 completed)
unanswered_counts = 0  ->  the audit reads Complete, and the button is gone
```

**The one number that looked wrong and was not.** 19 items in the review queue but only 15
`uncertain` verdicts. Reconciled exactly:

- **15** are the uncertains, and **4** are *passes* the check was only 75–80% sure of — under the
  bar this check needs before the platform acts alone (§9.26.H2);
- 19 findings sit on **18** distinct content hashes, because one piece of markup appears on both
  `/help/problem-report` and `/help/report-a-problem`. Same question, one answer, two findings —
  which is right: they are two problems on two pages.

Nothing in the data is inconsistent. **Everything the cross-check found was a caption.**

---

## 12. Everything closed — 18:10

The five defects the team had deferred were built after the audit was scored: **A** (deadlines
sized to the work, and a park that says a budget expired instead of claiming the machine was
checked), **B** (the verification budget sized the same way, and a timeout no longer reported as a
found gap), **D** (the banner counting from the one source the button reads), **F** (the audit
screen owning its own recovery, with one button), the **second half of G** (what nothing looked at
now derivable from the verdicts, not only from a field a repeated close can shrink), and **#58**
(an ended run stops being handed work and stops accepting verdicts).

**What was verified, and how.**

| | |
|---|---|
| new backend tests | **17**, across dispatch, judging, the park, the workflow's wording and the two readings of "never looked at" |
| new frontend tests | **3** — the banner's source of truth, and the parked panel in both directions |
| frontend suite | **416 / 416 green**, TypeScript clean |
| backend, the files this touched | green |
| pre-existing red tests | **14**, confirmed by stashing every change and re-running: 6 in `test_a11y_report.py`, 5 in `test_a11y_capture.py`, 2 in `test_a11y_conformance.py`, 1 in `test_a11y_findings.py`. All trace to the `graphics` / 1.4.11 checker added on 27 August and never wired in. **None is touched by today's work** — and the count is 14, not the 13 recorded earlier, which was an undercount. |

**One thing to know before deploying: the worker goes out before the API.** The verification
budget travels on the run's Temporal payload as a new field, and an input carrying a field the
worker does not know about yet fails to deserialize. This is the same rule the "request changes"
flag already follows; it is not new, but it is easy to forget on a demo morning.

**Two of the fixes cannot be proved live until they next fire**, and this is stated rather than
implied: the parked-run panel needs a pass that actually gets parked, and the resumed-run fix
(E2) needs a re-claim. Both are covered by tests and neither has been seen on a real run — the
whole point of A and F is that this state should now be rare and, when it happens, escapable.

---

---

## 13. The accuracy score — 1 September

The last outstanding item, and the reason the audit was run at all. **How often is this thing
right?**

| check | precision | recall | F1 | records |
|---|---|---|---|---|
| **alt** — image alternatives | 1.000 | 1.000 | 1.000 | 30 |
| **color** — meaning carried by colour | 1.000 | 0.938 | 0.968 | 32 |
| **label** — spoken name vs printed name | 1.000 | 1.000 | 1.000 | 40 |
| **semantics** — things dressed as other things | 1.000 | 0.875 | 0.933 | 31 |
| **structure** — headings, lists, tables | *0.833* | 1.000 | 0.909 | 30 |

**In plain terms.** *Precision* is: of the problems it reported, how many were real. *Recall* is:
of the real problems, how many it found. **Four of the five checks reported nothing that was not
a genuine problem.** The gaps are two missed failures in `semantics`, one in `color`, and three
false alarms in `structure`.

**All five now have enough records to be measured.** On 31 August none did — only 43 of 173
answer-key records had received a verdict, against a floor of 30 per check. The difference is
that the audit finished.

### The two things that had to be fixed first, and neither was a checker

Both were in the **scorecard**, not in the product. Full write-ups in `GAP_FIX_BUILD_PLAN.md`
§9.27.

**A correct answer was being counted as "nobody looked."** Some questions are settled by a rule
rather than by the AI — *does this button's spoken name contain the words printed on it* is a
string comparison, not an opinion, so the platform answers it directly and pays nothing. But
nothing recorded that an answer had been given, so **22 correctly-cleared buttons looked exactly
like 22 nobody had examined.** They were counted as wrong, and `label` could never have been
measured no matter how much test data we wrote, because the data pairs every hard case with an
easy one and the easy one is always the kind a rule settles.

Fixed by making the platform say which of three things happened — *asked the AI*, *answered here*,
or *does not apply* — where before there were two. **The rule's answer is now scored against the
answer key like any other**, and it caught itself on the first run: a button reading **"Renew"**
announced as **"Renew all loans"** passes the letter of the rule, and the key says a person should
weigh it, because *"Renew"* alone does not warn you it renews **everything**. The rule compares
words; it cannot see a name quietly widening what a button promised.

**The completeness check was weighing the bag instead of reading the list.** It compared totals —
the key says this page should hold eleven particular things, the page offered twenty-nine, and
twenty-nine is more than eleven, so it passed. It never looked at *which* twenty-nine. On this
very run it printed `ok` for `/help/membership-actions` while the other half of the same tool
reported eleven of that page's records as never looked at. **Two halves, one page, opposite
answers, and nothing noticing.**

Fixed by ticking the list off by name. It found **four elements the key names that no check was
ever asked about** — on `/loans/renewals`, `/newsletter`, `/staff/exports` and
`/staff/quick-edit`. Every one on a page the manifest gives no count for, so the old check could
not have found them even in principle. **The two halves now agree exactly.**

### What the number does, and does not, do

It is locked as a **baseline**: from here, a run that falls more than two points below these
figures stops **us** shipping a change to a prompt, a model or a selection rule. **It never
affects a client's work, and nothing in the platform reads it.** The re-run after the second fix
compared against the figures locked an hour earlier and every one came back *unchanged within
tolerance* — the gate's first real test, passed.

### The one figure that is not settled

**`structure` 0.833 is contested, and it is written into the results file as contested.** All
three false alarms are the same widget on one page — three weeks of a staff rota. The tables carry
correct column headers; the shift names down the first column are ordinary cells rather than row
headers. Our check calls that a breach of 1.3.1, so a screen-reader user moving across a row hears
*"R. Ellery, Fenner Road"* without hearing which shift. The answer key's author decided the column
headers are enough.

**Both readings are defensible, and no code change settles it** — the whole answer key is marked
*draft, awaiting expert adjudication*. It is a **floor, not a ceiling**: whichever way the ruling
goes the number can only move up.

**And these numbers are not for publishing.** The key's own README says so: every record is
unadjudicated, and at 30 records one miss moves recall by six or seven points. They are our report
card, not a client's.

---

---

## 14. Reading the review queue — 1 September

The audit was scored (§13) and the team then opened the **19 items waiting on a person** and read
what the judge had actually written on them. On every *Label in Name* item it said the same thing:

> *"this is likely a `<label>` element not provided in this batch… Cannot determine accessible
> name without the full surrounding HTML."*

### 14.1 What the 19 are

Every one traces to **pass 1** — the run that answered 799 of its 800 elements and was then failed
by the verification timeout (§6.6). Nothing in the queue came from pass 2, the one we took over by
hand, or from pass 3.

```
15  genuine "I could not decide" verdicts   — label 11, colour 2, alt 1, graphics 1
 4  passes at or below the confidence bar   — a person is asked BY DESIGN, `triage` uses <=
──
19
```

**The judge is not the problem.** Across the whole audit it was uncertain **15 times in 1,068
answers — 1.4%**: 953 passes, 100 failures. Colour, the check that has to *see* things, was
uncertain **twice in 512**. One checker stands apart:

```
label:  32 judged,  11 uncertain (34%)   — and every single one of them a <select>
```

Thirteen dropdowns out of thirteen. That is not a model having an off day; it is a defect, and
`GAP_FIX_BUILD_PLAN.md` §9.28.A/B has both halves of it. The short version: the browser computes
the accessible name, the platform stores it, and the batch never sent it — while the selection
rule was separately comparing a dropdown's *option list* against that name and calling the
mismatch suspicious. **Thirteen of the nineteen leave the queue once both are fixed. The other six
belong there.**

### 14.2 Errors made by the observer — 1 September

Two of the six things first reported to the team were wrong, and **both were caught by the team
asking whether our own three-pass interference had manufactured them.** Recorded here for the same
reason §7 is: a document that keeps only the findings that survived is not evidence of anything.

#### 14.2.1 A 77% failure rate that was 0.4%

Reported: *"62 of 81 colour judgments came back uncertain — the judge cannot reach its
screenshots."* A rewiring of the screenshot tool was proposed on the strength of it.

**The count came from the findings table, where 60 of those rows were not judgments at all** —
they were the platform's own *"nothing looked at this"* placeholders, which carry the checker name
of the check that would have run. The record of what the AI actually said is the judgment cache:
**512 colour judgments, 2 uncertain.**

Two elements did mention an unreachable screenshot, and they are the same icon covered by §9.28.D.
The paging mismatch behind the theory is real — the batch is served per screen, the images as one
run-wide list — but pass 1 worked through 73 screens and 800 elements, so it is survivable. **The
fix was withdrawn and the item recorded instead.**

The habit that caused it: a checker name on a row was read as *"a check said this"*, when the row
existed precisely because no check ever ran.

#### 14.2.2 "106 findings were silently closed" — they were answered, and this document said so

Reported as the most serious of the six: 106 elements filed as *"sent for human review"* and then
resolved 52 minutes later with nobody having ruled on them. A guard was designed for
`findings.record_run_findings` and written.

**It is not a defect. All 106 were re-judged and passed.** Traced by content hash: **104 distinct
elements, every one carrying a verdict from pass 3, every verdict a `pass`.** A passing element
produces no finding, so the old placeholders were correctly closed. The merge record shows it
plainly — passes 2,007 → 2,174, review queue 133 → 19.

**The error was checking whether those elements had an open *finding* afterwards, finding none,
and concluding nothing had answered them.** The judgment cache was never consulted, and it is the
only record of what was answered.

**And §6.11 of this document had it right on the day:** *"114 of those 133 were never work for a
person at all… they cleared the moment the third pass answered them."* Written six hours after the
audit closed, and not read before contradicting it. **The guard was reverted** — it fixed nothing,
and it would have stopped a genuinely deleted element from ever resolving, which is a real
regression traded for an imaginary fix.

#### 14.2.3 What the pattern is

Both errors, and §7.1's before them, are the same shape: **a number taken from the nearest table
rather than from the table that means what the sentence claims.** The findings table records what
is *open against a page*; the judgment cache records what was *answered*. They differ by every
pass, every placeholder and every element that turned out to be fine — which is most of an audit.

The correction that matters is not either number. It is that **the team's challenge — "did we
cause this ourselves?" — is what surfaced both**, and it should be the first question asked of any
finding drawn from a run we intervened in.

### 14.3 What the three passes actually cost

| Pass | Window | Status | Judged | Ended by |
|---|---|---|---|---|
| 1 | 09:39–12:02 | **failed** | 799 of 800 | write-completeness verification timed out at 60s |
| 2 | 12:45–15:34 | **failed** | 99 | `run abandoned by human takeover` — **ours** |
| 3 | 15:49–16:31 | completed | 170 | clean |

**Pass 1 is the origin of the cascade, and it is a defect already fixed.** It judged 799 elements
and wrote a full report; the platform then failed it on the step that merely *confirms the writes
landed*, which had a hard 60-second ceiling. That is exactly what the `verify_timeout_seconds` /
`LONG_VERIFY_PHASES` work removed — a judging phase now sizes that window by batch (800 elements →
1,600s). **It is on the branch and not yet deployed.** Deployed, pass 1 would have closed cleanly
and neither the second pass nor the takeover would have existed.

So the takeover was real, and it was downstream of a platform bug rather than the first cause. It
also **put nothing into the review queue** and **cost nothing in coverage** — pass 3 answered
everything pass 2 left.


---

*Last updated: 1 September, 16:40 UTC — **the audit is complete, cross-checked, scored, and its
review queue read.** All 1,068 distinct questions answered across three passes; 410 failures; 19
for a person to decide; nothing unlooked-at. Of those 19, **thirteen were the platform withholding
the accessible name from its own judge** — fixed, with two guards so the class of loss cannot
recur silently. **Two of the six defects first reported were the observer's own analysis errors**
(§14.2), both surfaced by the team asking whether our three-pass interference had manufactured
them. Nothing here is a figure to put in front of a client.*
