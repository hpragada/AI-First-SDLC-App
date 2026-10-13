# TS-08 · Clarifications

An agent that hits a gap in its context does not guess and does not fail — it pauses and asks. This
suite proves the whole loop: the run parks on a question, the question surfaces where a human will
see it, the human answers, and **the same session resumes** rather than starting the phase over.

**Run these in order.** TC-113 → TC-122 follow a single paused run from the moment it asks to the
moment it resumes. TC-113–TC-120 all depend on the same live clarification; once you answer it in
TC-116 it is gone, so read the whole block before you click `Submit answers`.

**Time budget and a warning about determinism.** Whether an agent asks anything is the agent's call,
not the platform's. Ideation, Requirements and PRD ask most often. Trigger a phase (TS-07 TC-100)
and watch the run console; if the badge reaches `Awaiting gate` without ever showing `Needs answer`,
that is **not** a defect — mark the affected cases Blocked with the reason `no clarification raised
on this run` and retry them on the next phase you run. Budget 20–30 minutes per attempt.

**Timeout policy.** Every case here that waits on a live run states an explicit **max wait**. If the
run has not reached the state the case expects by then, record the verdict **Blocked** with the
reason `exceeded the stated max wait` — never Failed. Failed means the app rendered something wrong,
not that it was slow. Capture the run id and the last console line in the notes.

**One run per work item.** The backend admits a trigger only if the work item has no live run of
*any* phase. While the run you are watching here is live you cannot start a second phase on the same
epic to "increase the odds" of a clarification — use a **different work item** if you want two runs
in flight (that is also how TC-801 is set up).

**Only the first pending clarification is rendered.** `/clarifications` shows one card at a time even
when several are outstanding, while the sidebar badge counts all of them. That is a known product
defect, covered by TC-801 — do not raise it from the other cases in this suite.

---

### TC-113 · A paused run shows `Needs answer` in the console

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | Functional |
| Priority | Critical |
| Screen | `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A phase has been triggered on the epic `Stripe Webhook Integration` and the companion is running.
- **Needs a live run: 20–30 minutes typical, max wait 45 minutes** from the trigger. Leave the run
  console open.

**Steps**
1. Open the run console for the triggered run.
2. Watch the status badge until the agent asks something.
3. Read the badge, the banner title, the banner body and the link.
4. Read the last console lines.

**Expected**
- The status badge changes to `Needs answer`.
- A banner titled `Paused — waiting for your answer` reads
  `The agent asked a question. Answer it to resume in the same session.` followed by a link
  `Answer now ↗`.
- Clicking `Answer now ↗` navigates to `/clarifications`.
- The run does **not** fail or complete while the question is outstanding.

**Pass / Fail**
- PASS if the badge reads `Needs answer`, the banner copy matches exactly and `Answer now ↗` links
  to `/clarifications`.
- FAIL if the run keeps showing `Running` with a question outstanding, if it fails instead of
  pausing, or if the banner has no link to the answer screen.
- **BLOCKED** (not Failed) if the run reaches `Awaiting gate`, `Completed` or `Parked for takeover`
  without ever showing `Needs answer` — the agent simply had nothing to ask. Reason:
  `no clarification raised on this run`.
- **BLOCKED** if 45 minutes pass from the trigger with the badge still on `Dispatched · waiting` or
  `Running`. Reason: `exceeded the 45-minute max wait`.

**Notes**
- The console is polled (~3 s), so the badge may take a few seconds to flip after the agent asks.
- Do not kill a run that looks stuck inside the 45-minute window — see TS-07 TC-103's note on the
  20-minute silence (`docs/TESTING_PHASE_BUGS_HANDOFF.md` Bug 3). The max wait is the tie-breaker
  between "still working" and "stuck"; use it rather than your own judgement.

---

### TC-114 · The sidebar Clarifications count increments

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | UX |
| Priority | Medium |
| Screen | any screen (app shell) |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-113's run is paused with an unanswered question.
- Note the sidebar `Clarifications` item before the pause — it should carry no count.

**Steps**
1. Look at the sidebar `Clarifications` nav item before the agent asks anything.
2. Once the run console shows `Needs answer`, look at the sidebar again (reload if needed).
3. Click `Clarifications` in the sidebar.

**Expected**
- Before the pause, the `Clarifications` nav item shows no count badge.
- With a question outstanding, the item shows a count badge of `1` (or the number of pending
  clarifications across your work items).
- Clicking it navigates to `/clarifications` and the question is there.

**Pass / Fail**
- PASS if the count appears when a question is outstanding and matches the number of pending
  questions.
- FAIL if the count never appears, shows `0`, or stays behind after the question is answered.

---

### TC-115 · The question renders on `/clarifications` under its tier

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | Functional |
| Priority | Critical |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-113's run is paused with an unanswered question.

**Steps**
1. Go to `http://localhost:5173/clarifications`.
2. Read the h1 and the sub-heading.
3. Read the card header row.
4. Read the tier heading above the question(s).

**Expected**
- The h1 is `Clarifications` and the sub-heading reads
  `Questions your agents are waiting on. Answering resumes the run in the same session.`
- The card header shows the work item (its 8-character id and title), a badge reading
  `{Phase} · needs answer` (e.g. `Ideation · needs answer`), and the text
  `⏸ Paused — waiting for your answer`.
- Each question sits inside a tier section whose heading is one of `Tier 1 · Must answer`,
  `Tier 2 · Suggested` or `Tier 3 · Industry-standard inference`, with the matching hint:
  `Business decisions the agent can't make for you.` / `The agent's recommendation — confirm or
  adjust.` / `High-confidence defaults — accept or override.`
- Required questions are marked with `*` next to the question text.

**Pass / Fail**
- PASS if the card header, the phase badge and at least one correctly-labelled tier section render.
- FAIL if the question appears with no tier grouping, if the phase badge shows a raw key such as
  `01_ideation`, or if the screen shows the empty state while the run says `Needs answer`.

**Notes**
- Tier sections carry a `data-tier` attribute (`1`, `2` or `3`) — the one testable attribute in the
  app. Everything else must be located by visible text, label or role.
- A question with no tier is grouped under Tier 1 by design.

---

### TC-116 · Answering the question resumes the same run

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | E2E |
| Priority | Critical |
| Screen | `/clarifications` · `/runs/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-115 passed; the question is on screen and its run is paused.
- Note the run's short reference from `/runs` first — you will come back to that same run.
- TC-117 and TC-118 should be read (and ideally executed) **before** you submit here, because
  answering clears the question.

**Steps**
1. On `/clarifications`, answer every required question — type a sensible value into a text input,
   pick an option in a choice question, tick `Yes` on a confirm question.
2. Click `Submit answers` (or `Submit answer` if there is only one question).
3. Go to `/runs/{the same run id}`.
4. Watch the status badge.

**Expected**
- The submit succeeds — no red error text appears under the buttons.
- `/clarifications` no longer shows the question.
- The **same** run (same run id, same console) leaves `Needs answer` and returns to `Running`, then
  continues on to `Awaiting gate` or `Completed`. No new run row is created on `/runs`.

**Test data**
- Free-text answers: use something plausible for the project, e.g. `Stripe` for a payment-provider
  question, `PAY` for a Confluence space.

**Pass / Fail**
- PASS if the answer submits, the question clears, and the original run resumes without a new run
  being created.
- FAIL if a second run appears, if any red error text appears under the buttons on submit, or if the
  question is still on screen after a submit that reported no error.
- **BLOCKED** (not Failed) if the submit succeeds and the question clears, but the run has not left
  `Needs answer` after a **max wait of 10 minutes**. Reason: `run did not resume within 10 minutes`.
  Record the run id.

**Notes**
- The button label is singular `Submit answer` when the clarification has exactly one question and
  plural `Submit answers` when it has more. Both are correct.
- **Do not look for the exact string `Couldn't submit the answer.`** It is only a fallback for a
  non-`Error` throw, and a real backend rejection (403, 400, 5xx) surfaces the **server's own
  message** in that same red line instead. Assert on *any* red text under the buttons, and record
  the exact wording you saw in the notes.

---

### TC-117 · Each question kind renders the right input

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | UX |
| Priority | High |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A clarification is on screen. Over the cycle you will see all three kinds; record whichever kinds
  this clarification contains and re-run the case on later clarifications until all three are seen.

**Steps**
1. For a **confirm** question, look at the control under the question text.
2. For a **choice** question, read the closed dropdown, then click it and read the list.
3. With the list open, find the longest option and check how it is laid out.
4. Close the list, press Tab until the dropdown has focus, and press ↓. Move with ↓ / ↑, press Home
   and End, then press Escape. Open it again and press Enter on an option.
5. In a choice question that offers an "Other"-style option, pick it and look below the dropdown.
6. For a plain **text** question, read the input's placeholder.

**Expected**
- A confirm question renders a checkbox labelled `Yes`.
- A choice question renders a dropdown that reads `Choose one…` (in faint text) until something is
  picked. Opening it shows only the agent's options — `Choose one…` is not itself an option in the
  list.
- The list is as wide as the dropdown and stays inside the card: a long option wraps onto several
  lines rather than running off the card on one line. A long chosen answer wraps in the closed
  dropdown too.
- Keyboard: Tab reaches the dropdown; ↓ or ↑ opens it; ↓ / ↑ move the highlight; Home and End jump to
  the first and last option; Enter (or Space) picks the highlighted option and closes the list;
  Escape closes it without changing the answer.
- Selecting an "Other"-style option (e.g. `Other`, `Other (please specify)`, `d) Other`) reveals a
  free-text input below the dropdown with the placeholder `Please specify…` and the accessible name
  `Please specify`.
- A text question renders a single-line input with the placeholder `Type your answer…`.
- When a clarification has more than one question, each label is numbered `1 · `, `2 · `, … .

**Pass / Fail**
- PASS if each kind you encounter renders exactly the control described, long options wrap inside
  the card, and the keyboard steps work.
- FAIL if a choice question renders as free text, if the closed dropdown shows an option instead of
  `Choose one…` before anything is picked, if a long option runs off the card, if the dropdown cannot
  be operated from the keyboard, or if picking `Other` gives no way to type the actual answer.

**Notes**
- The "Other" match tolerates a leading enumerator (`a) `, `3. `, `- `). If a clearly
  Other-flavoured option does **not** reveal the free-text box, that is a real defect — capture the
  exact option text in the report.
- Tier 2/3 questions arrive pre-filled with the agent's suggestion. That is by design, not a
  stale-form bug.

---

### TC-118 · A blank required question blocks submission

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | Negative |
| Priority | High |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A clarification is on screen with at least one question marked required (`*`).

**Steps**
1. Leave the required question empty (clear the field, or leave the select on `Choose one…`).
2. Click `Submit answers`.
3. Read the error under the required field.
4. Check `/runs/{id}` for the paused run.
5. Fill the required question in and submit again.

**Expected**
- Submission is blocked — the card stays on screen with the question still unanswered.
- The message `This answer is required before the run can resume.` appears against the required
  field.
- The field is marked invalid (it renders in the error state).
- The run is still on `Needs answer` — nothing was sent.
- After filling the field, submitting succeeds and the error clears.

**Pass / Fail**
- PASS if the blank submit is blocked with the exact message and the run is untouched.
- FAIL if the form submits with a required answer missing, if the error text differs, or if the
  error appears against the wrong question.

**Notes**
- A choice question whose selected option is an "Other"-style one and whose free-text box is empty
  counts as **unanswered** — the same required error applies. Worth checking if you have such a
  question.

---

### TC-119 · `Accept all suggestions & inferences` fills the Tier 2/3 answers

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | Functional |
| Priority | Medium |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A clarification that contains at least one Tier 2 or Tier 3 question (a
  `Tier 2 · Suggested` or `Tier 3 · Industry-standard inference` section is visible). PRD and
  Requirements produce these most often.

**Steps**
1. Confirm the button `Accept all suggestions & inferences` is present next to `Submit answers`.
2. Change or clear one of the Tier 2/3 fields so it no longer matches the agent's suggestion.
3. Click `Accept all suggestions & inferences`.
4. Read the Tier 2/3 fields, then read any Tier 1 field.

**Expected**
- The button is shown only when at least one Tier 2 or Tier 3 question exists.
- Clicking it restores every Tier 2/3 field to the agent's suggested value, including the one you
  changed.
- Tier 1 answers are **not** filled in — they remain the human's to answer.
- Clicking it does not submit anything; the card stays open until you press `Submit answers`.

**Pass / Fail**
- PASS if Tier 2/3 fields are restored to the suggestions and Tier 1 is left alone.
- FAIL if the button submits the form, if it also fills Tier 1, or if it is present on a
  clarification that has only Tier 1 questions.

---

### TC-120 · The answered confirmation names the work item and says the run resumed

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | UX |
| Priority | Medium |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- You are about to submit the only outstanding clarification (TC-116). Do not navigate away
  afterwards — the confirmation is shown in place.

**Steps**
1. Answer the question and click `Submit answers`.
2. Stay on `/clarifications` and read what replaces the card.

**Expected**
- The card is replaced by the empty state `No questions waiting`.
- Below it, a confirmation row shows a green `Answered` badge and the text
  `{work item id8} · {title} — run resumed.`
- The sidebar `Clarifications` count badge clears.

**Pass / Fail**
- PASS if the `Answered` badge and the `— run resumed.` line render naming the correct work item.
- FAIL if the screen goes blank, if the answered card stays in an editable state, or if the
  confirmation names the wrong work item.

**Notes**
- The confirmation is transient — it is shown while you stay on the screen. Navigating away and back
  showing only `No questions waiting` is expected.

---

### TC-121 · A user with no membership on the project cannot answer

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | Permission |
| Priority | High |
| Screen | `/clarifications` |
| Persona | Any (a non-member account) |
| Automation | No |

**Preconditions**
- A live clarification is outstanding on `Payment Gateway v2` (do not answer it yet).
- A second account exists in the workspace with **no membership on this project** — invite
  `qa+<x>.outsider@edvensoft.com` from `/admin/users` and grant it no role on
  `Payment Gateway v2`. Accept the invite and set the password `QaTest-2026!`.

**Steps**
1. Log out of P1 (account menu → sign out).
2. Log in as the non-member account.
3. Go to `/clarifications`.
4. Look at the sidebar `Clarifications` count.
5. Log out and log back in as P1 and confirm the question is still there, unanswered.

**Expected**
- The non-member sees no clarification card for `Payment Gateway v2` — the screen shows
  `No questions waiting` / `When an agent needs input, it pauses and the question appears here.`
- There is no form, no `Submit answers` button and therefore no way to answer.
- The sidebar shows no `Clarifications` count for this user.
- Back as P1, the question is still pending and the run is still on `Needs answer` — the non-member
  changed nothing.

**Pass / Fail**
- PASS if the non-member cannot see or answer the question and the question survives untouched.
- FAIL if the non-member sees the question card, or can submit an answer, or if the run resumes
  while they are logged in.

**Notes**
- Answering requires **any** membership on the project — not a specific role. P10 Engineer *is* a
  member and therefore *can* answer; that is intended, so do not test the boundary with P10.
- The backend refuses a non-member's answer with a 403. The UI never offers the form in the first
  place, so a raw 403 should never be visible; if one is, capture it as a Low UX defect.

---

### TC-122 · The Clarifications empty state

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | UX |
| Priority | Low |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | Yes |

**Preconditions**
- No run on the selected project is currently waiting on an answer (all clarifications answered, or
  no run in flight).

**Steps**
1. Go to `/clarifications`.
2. Read the panel body.

**Expected**
- The empty state title is `No questions waiting` and the text is
  `When an agent needs input, it pauses and the question appears here.`
- No question card and no form controls are rendered.
- The sidebar `Clarifications` item shows no count.

**Pass / Fail**
- PASS if the empty state renders with the exact copy and nothing else.
- FAIL if a previously answered question is still listed as pending, or if the sidebar still carries
  a count while the panel shows the empty state.

**Notes**
- Earlier versions of this case also failed on demo questions (`WI-510`, `Should the analytics
  dashboard support CSV export in v1?`). Those exist only behind the design-gallery route and cannot
  render on `/clarifications`, so the criterion could never fire and has been dropped.
- A transient `Answered` confirmation card below the empty state is **expected** if you have just
  submitted an answer without navigating away (TC-120) — it is not a leftover pending question.

---

### TC-801 · With two questions outstanding, only the first is on screen

| Field | Value |
|---|---|
| Suite | TS-08 Clarifications |
| Type | Functional |
| Priority | High |
| Screen | `/clarifications` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- **Two different work items** in `Payment Gateway v2` each have a run paused on `Needs answer` at
  the same time. Because only one run may be live per work item, you must use two items: trigger a
  phase on the epic `Stripe Webhook Integration` and a phase on a second work item (create a task
  `QA — second clarification` on `/work-items` if needed), then wait for both to ask something.
- **Max wait: 45 minutes per run.** Whether an agent asks at all is the agent's call. If you cannot
  get two runs into `Needs answer` at the same time, record this case **Blocked** with the reason
  `could not obtain two concurrent clarifications`. Do not record it Failed.
- Do not answer either question before running this case.

**Steps**
1. Confirm on `/runs/{id}` that **both** runs show the badge `Needs answer`.
2. Look at the sidebar `Clarifications` nav item and read its count badge.
3. Go to `/clarifications` and count the question cards on screen.
4. Read the work item named in the card header (`{8-char id} · {title}`).
5. Scroll to the bottom of the page and confirm there is nothing below the card.
6. Answer the question on screen and click `Submit answer` / `Submit answers`.
7. Stay on `/clarifications` and read what is now displayed.

**Expected**
- The sidebar count badge reads `2`.
- **Exactly one** question card is rendered, for one of the two work items. The second work item's
  question is nowhere on the screen — there is no second card, no list, no pager and no tab.
- After answering the first, the second work item's card replaces it on the same screen, and the
  sidebar count drops to `1`.

**Pass / Fail**
- PASS if the sidebar reads `2` while exactly one card is rendered, and answering the first reveals
  the second.
- FAIL if answering the first clarification leaves the screen on `No questions waiting` while the
  sidebar still counts a pending question — that would strand the second run with no route to it at
  all.

**Notes**
- **This case asserts a known product defect, deliberately. Do not raise a duplicate.** The screen
  renders only the first pending clarification, so the sidebar badge and the screen disagree
  whenever more than one question is outstanding. A user with two paused runs has no way to see the
  second, and no indication one exists beyond the count. It is logged as a product defect; this case
  pins the behaviour so a fix is noticed.
- The step-6 answer is required: without it you cannot tell "the second card is hidden" from "the
  second clarification was never created".

---

### TC-233 · The "already answered" notice stops once it has done its job

**Why this case exists.** Bugs S.No 319, found 2026-10-05. The notice shown when you follow a link
to a question that has since been answered also rendered on the answered-history tab, where its
button — which only switches to that tab — did nothing at all when pressed.

**Setup**
- A clarification that has been answered, and the link that was sent for it (the notification link,
  or the address bar while the question was open).

**Steps**
1. Answer a clarification, then open the link to it again.
2. Read the notice on **Needs answer** and press **Look in the answered history**.
3. Read the **History** tab.

**Expected**
- Step 2: the notice appears and explains why there is no form — it stops you hunting for one.
- Step 3: **no notice**, because you have arrived where it was sending you.

**Pass / Fail**
- PASS if the notice appears exactly where it still has something to say.
- FAIL if it shows on History, where its button leads to the page you are already on.
