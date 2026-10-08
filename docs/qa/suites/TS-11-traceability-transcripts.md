# TS-11 · Traceability & Transcripts

The two read-only provenance screens: the lineage graph at `/traceability` and the run-transcript
replay at `/transcripts`. Neither screen creates anything — they render what the lifecycle already
produced. **Owner: Tester B.**

**This suite has a hard cross-suite dependency.** Tester B triggers no runs, so every case here
needs artifacts and completed runs produced by **Tester C in TS-07 and TS-09** in the same
workspace. Per the plan, hold this suite until C's first lifecycle is through its gates (around
day 6). If C's runs are not through, mark the cases **Blocked**, not Failed.

**Run these in order.** TC-161 and TC-162 need a *different*, empty project, so they deliberately
sit after the populated-graph cases.

Neither screen has a role gate — run everything as **P1 Owner-Admin** unless noted.

**Read this before you start.** The map colours each node by its artifact's status, using the same
words as the Artifacts screen. An artifact reads `Draft` while its run works, `Waiting for approval`
(amber) once its gate opens, `Published` once the gate is approved, and `Superseded` if the gate was
rejected. Approving a phase gate publishes in the same transaction, so `Approved` is rarely seen on
the plan path. Since commits 4ac75f9 and b40c557 the legend lists five statuses and the map has
phase, type and work-item filters (TC-158, TC-163).

**ID note.** The plan reserves TC-157 – TC-166 for this suite and that range is fully used. Cases
added by the pack audit continue at **TC-251**, which collides with nothing.

---

### TC-157 · The lineage graph renders nodes and edges once artifacts exist

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | Functional |
| Priority | High |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Tester C has completed at least two phases on `Payment Gateway v2` (for example Requirements then
  PRD), so more than one artifact exists and one derives from another.
- `Payment Gateway v2` is selected in the top-bar project select.

**Steps**
1. Go to `/artifacts` and click **View traceability** in the page header.
2. Read the heading and sub-heading.
3. Count the node boxes drawn in the graph.
4. Look for connecting lines between the boxes.
5. Read the two lines of text inside one node box.

**Expected**
- The URL is `/traceability`, the heading is `Traceability` and the sub-heading reads
  `Artifact lineage — what derives from what, which tasks implement which requirement, which tests cover which task. Click a node to preview or deep-link.`
- One node box is drawn per artifact in the registry — the node count equals the row count on
  `/artifacts` for the same project.
- Each node's first line is the human artifact name, truncated to 22 characters with a trailing `…`
  if longer. Its second line reads `{Phase} · {Status}`, where `{Phase}` is the humanized phase name
  and `{Status}` is the status in words (`Draft`, `Waiting for approval`, `Published`,
  `Superseded`), also cut to 22 characters with a trailing `…`. Hovering a node shows the full
  `{name} — {Phase} · {Status}` line.
- Record how many connecting lines are drawn, including zero. This is an observation, not an
  assertion — see Notes.

**Pass / Fail**
- PASS if the node count matches the artifact count on `/artifacts` and every node's two label
  lines are formatted as above.
- FAIL if the graph is empty while artifacts exist, if the node count disagrees with `/artifacts`,
  or if a node's first line shows a raw key such as `03_prd` or `test_case`.
- **Do not fail this case on a missing edge.** Record the edge count in the result notes and, if it
  is zero, raise it against the phase agent as described below.

**Notes**
- **Why edges are not an oracle here.** Trace edges are *mostly* not derived by the platform; they
  exist only if the phase agent chose to record one while it ran. A graph with correct nodes and no edges
  is an agent-behaviour problem in the phase that should have recorded the link, not a defect in
  `/traceability` — and this screen gives you no way to tell the two apart. If you see zero edges
  after two chained phases, raise it as **Medium** against the *later* phase's agent (the one whose
  artifact should derive from the earlier one), reference this TC-ID, and still pass this case if
  the nodes are right.
- The graph contains **artifacts only** — work items are not nodes. Missing work-item boxes are
  expected, not a defect.
- Edge relationships in the data are `derives` / `implements` / `tests` / `deploys`; the rendered
  lines are unlabelled, so you can only verify that a connection exists, not which kind.
- **One edge type is now platform-derived: `tests`.** Importing test results registers the run's
  `test_report` artifact and records a `tests` edge from it to the latest code artifact,
  automatically (August 2026). So after TS-13 TC-214 or a 09b run you should see at least one edge
  that no agent had to choose to record. If the graph is empty *after a test import has happened*,
  that is a stronger signal than an empty graph after two planning phases — note which case
  produced the data when you record the edge count.
- The status on the node's second line is in words since commit 4ac75f9. A lower-case token such as
  `draft` or `staged` on a node is now a defect.

---

### TC-158 · The five-entry legend matches the node colours, and an artifact at an open gate is amber

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | UX |
| Priority | Medium |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-157 passed, and the project has artifacts in at least these two statuses: one from a gate that
  has been approved (reads `Published` on `/artifacts`) and one from a phase whose gate is still
  open (reads `Waiting for approval`).
- Optional: an artifact from a rejected run (reads `Superseded`).

**Steps**
1. Go to `/artifacts` and note the name and status badge of one `Published` artifact, one
   `Waiting for approval` artifact, and a `Superseded` one if you have it.
2. Go to `/traceability`.
3. Read the legend on the right of the row above the graph, left to right.
4. Find the node for the `Published` artifact from step 1 and compare its dot with the legend's
   `Published` swatch.
5. Find the node for the `Waiting for approval` artifact and compare its dot with that swatch.
6. If you noted a `Superseded` artifact, compare its node with the `Superseded` swatch.

**Expected**
- The legend shows exactly five entries, in order: `Published`, `Approved`,
  `Waiting for approval`, `Draft`, `Superseded`, each with a coloured dot. No raw status token appears
  in the legend.
- The `Published` artifact's node dot and outline match the `Published` swatch (green).
- The `Waiting for approval` artifact's node matches the `Waiting for approval` swatch (amber).
  Its second line, `{Phase} · Waiting for approval`, is cut at 22 characters, so where the `…` falls
  depends on the phase name. Hovering the node shows the full line ending `· Waiting for approval`.
- A `Superseded` artifact's node matches the grey `Superseded` swatch.
- Each node's colour agrees with the badge the same artifact shows on `/artifacts`.

**Pass / Fail**
- PASS if the legend renders the five labels in that order, and every node you checked matches the
  swatch for the status `/artifacts` shows for it.
- FAIL if a legend label is missing, renamed or out of order, if an artifact at an open gate draws
  blue (`Draft`) instead of amber, or if a node's colour disagrees with its `/artifacts` badge.

**Notes**
- **Changed in commit 4ac75f9.** The legend used to read `Published` / `Pending gate` / `Draft`, and
  its amber entry could never match a node. It now comes from the same status list the Artifacts
  screen uses, and opening a gate marks the run's drafts as waiting, so amber nodes are expected.
- `Approved` is in the legend because it is a real status, but approving a phase gate publishes in
  the same transaction, so on the plan path you will rarely see an `Approved` node. Its absence is
  not a defect.
- The screen has no zoom, so on a large graph use the browser's own zoom to compare swatch colours.

---

### TC-159 · Clicking a node opens the artifact preview, or the external URL

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | Functional |
| Priority | High |
| Screen | `/traceability` → `/artifacts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-157 passed. Note one node's name before you start.

**Steps**
1. Go to `/traceability`.
2. Hover a node box and note the cursor.
3. Click a node for an artifact that has **not** been exported to Confluence.
4. Go back to `/traceability` and click a node for an artifact that **has** been published to
   Confluence (TS-10 TC-153 produces one), if you have one.

**Expected**
- The cursor changes to a pointer over a node box.
- Step 3 navigates in the same tab to `/artifacts/{id}`, showing the preview for the artifact whose
  name was on the node — breadcrumb `Artifacts / Preview` and the read-through banner.
- Step 4 opens the artifact's system-of-record page in a **new tab** instead of navigating, leaving
  `/traceability` on screen.

**Pass / Fail**
- PASS if a node click reaches the matching artifact (in-app or in the SoR, per the artifact).
- FAIL if a click does nothing, or lands on a different artifact than the node's label.

**Notes**
- If no artifact in your project has an external URL yet, run step 3 only and record step 4 as not
  applicable.

---

### TC-160 · A graph node can be reached and activated from the keyboard

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | UX |
| Priority | Medium |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-157 passed. Use the mouse only to click into the page once, then keyboard only.

**Steps**
1. Go to `/traceability`.
2. Press `Tab` repeatedly until focus lands inside the graph and a node shows a visible focus ring.
3. Press `Enter`.
4. Navigate back, `Tab` to a node again, and press `Space`.

**Expected**
- Nodes are reachable by `Tab` — focus stops on each node box, not just on the surrounding page
  chrome.
- The focused node shows a visible focus indicator.
- `Enter` activates the focused node exactly as a mouse click does (navigates to the artifact
  preview, or opens the SoR URL in a new tab).
- `Space` does the same.

**Pass / Fail**
- PASS if a node can be focused with `Tab` and activated with both `Enter` and `Space`.
- FAIL if the graph is entirely skipped by `Tab`, if there is no visible focus indicator, or if the
  keys do nothing while a node is focused. Any of these is a real accessibility defect —
  severity **Medium**.

**Notes**
- The nodes are marked up as buttons, so a screen reader should announce them as such. Focus-ring
  visibility on an SVG shape is the part most likely to be wrong — check it carefully rather than
  assuming.

---

### TC-161 · The graph shows the empty state on a project with no artifacts

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | UX |
| Priority | Medium |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A second project with no completed runs exists (`QA Empty Project` from TS-10 TC-145, or create
  one from `/projects/new`).

**Steps**
1. Switch the top-bar project select to the empty project.
2. Go to `/traceability`.
3. Read the panel.

**Expected**
- An empty state titled `No lineage yet` with the text
  `Once phases produce artifacts and tasks, their relationships render here as a graph.`
- The heading `Traceability` and the five-entry legend are still rendered above it.
- The `Filter by phase`, `Filter by type` and `Highlight work item` selects are present but offer only
  their defaults (`Phase: All`, `Type: All`, `Highlight: none`), because there are no nodes to take
  options from.
- No empty SVG canvas or zero-node graph frame is drawn.

**Pass / Fail**
- PASS if that exact empty copy appears.
- FAIL if a blank graph area renders with no message, or the screen errors.

**Notes**
- Switch back to `Payment Gateway v2` afterwards.

---

### TC-162 · The graph shows a loading state before the lineage arrives

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | UX |
| Priority | Low |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- A populated project (`Payment Gateway v2`).

**Steps**
1. Go to `/traceability`.
2. Do a hard reload of the page and watch the area below the legend immediately after the reload.

**Expected**
- Before the graph paints, a panel shows a spinner next to the text
  `Loading traceability graph…`.
- The loading panel is replaced by the graph — it does not persist after the nodes render.
- No flash of the `No lineage yet` empty state occurs while data is still loading.

**Pass / Fail**
- PASS if the loading text appears (however briefly) and is replaced by the graph.
- FAIL if the empty state flashes before the graph appears — a "no lineage" message on a project
  that has lineage is misleading even for a moment. Severity **Low**.

**Notes**
- On a fast local stack the loading state can be too brief to read. If you genuinely cannot observe
  it, record the case as **Pass** on the "no empty-state flash" oracle and note that the spinner was
  not observable.

---

### TC-163 · Phase and type filters narrow the map, and a work-item highlight dims everything else

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | Functional |
| Priority | Medium |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-157 passed — the graph is populated with artifacts from at least two phases, of at least two
  types, produced for at least two different work items.

**Steps**
1. Go to `/traceability` and count the nodes.
2. Read the row above the graph, left to right, and open each of the three selects in turn, reading
   every option.
3. In `Filter by phase`, choose one phase. Read the text beside the selects and count the nodes.
4. Set it back to `Phase: All`, then choose one type in `Filter by type`, and count the nodes again.
5. Set type back to `Type: All`. In `Highlight work item`, choose one work item.
6. Compare the nodes that belong to that work item with the rest.
7. With the highlight still on, choose a phase and a type that no node has together, so nothing
   matches. Read the panel.
8. Set phase and type back to `All` and the highlight back to `Highlight: none`.
9. Check the top-right corner of the graph canvas.

**Expected**
- Step 2: three selects sit on the left of the row, in this order, with these defaults:
  `Phase: All` (labelled `Filter by phase` for screen readers), `Type: All` (`Filter by type`) and
  `Highlight: none` (`Highlight work item`). The five-entry legend sits at the right.
- The phase and type options are only the values present on the map, in human wording — never a
  phase or type that no node has.
- The work-item options name each work item as `{key} {title}` (for example `WI-12 Stripe Webhook
  Integration`) and are sorted alphabetically. `Not tied to a work item` is offered at the end
  **only** if the map has a node that belongs to no work item.
- Step 3: only nodes of that phase remain, and the text `{shown} of {total} shown` appears beside the
  selects, where `{total}` is the step 1 count.
- Step 4: only nodes of that type remain, and the count text updates.
- Step 6: every node is still drawn, but nodes that do **not** belong to the chosen work item are
  faded; that work item's nodes stay at full strength. Faded nodes can still be clicked. The count
  text does **not** appear for a highlight on its own.
- Step 7: the graph is replaced by an empty state titled `Nothing matches these filters` with the
  text `Clear the phase or type filter to see the whole map.` — **not** `No lineage yet`.
- Step 8 restores the full map with no count text.
- Step 9: there are **no** `−`, `+` or `Fit` zoom buttons on the live canvas.

**Pass / Fail**
- PASS if both filters narrow the map to matching nodes with a correct count, the highlight fades
  (not hides) the other nodes, and the no-match state reads `Nothing matches these filters`.
- FAIL if any select is inert, offers an option that matches no node, hides nodes when highlighting,
  or if a filtered-to-nothing map says `No lineage yet`.
- FAIL — **High** — if any select offers the demo work item `WI-492`, which exists in no project.

**Notes**
- **Rewritten for commit b40c557.** This case used to assert that the live screen had **no** filters.
  The filters now exist; the gallery's unwired dropdowns (one offering an invented `WI-492`) were
  deleted.
- `Not tied to a work item` gathers documents that no run produced — in a greenfield project you
  will normally not see this option. Its absence on a greenfield map is correct.
- The map still has no zoom. If the graph is too large to read without it, that is a **Low** usability
  observation, not a functional defect.

---

### TC-164 · `/transcripts` lists only completed and approved runs, with the right columns

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | Functional |
| Priority | High |
| Screen | `/transcripts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- Tester C has at least one run in `Completed` or `Approved` state, and ideally one run still
  `Running` or `Awaiting gate`, on `Payment Gateway v2`.

**Steps**
1. Go to `/runs` and note the id and status of every run listed.
2. Navigate to `/transcripts` in the address bar.
3. Read the breadcrumb, heading and sub-heading.
4. Read the column headers.
5. Compare the listed runs against your note from step 1.

**Expected**
- The breadcrumb reads `Phases & Runs / Transcripts`, the heading `Run transcripts`, and the
  sub-heading
  `Read-only replay of each run — agent turns, tool calls, and the Q&A. Stored for provenance; never editable.`
- The table headers read `Run`, `Phase`, `Work item`, `Status`, plus one blank header above the
  action column.
- Only runs whose status is completed or approved are listed. A run that is running, awaiting its
  gate, failed or stalled does **not** appear.
- Each row's action column shows **Open transcript**.

**Pass / Fail**
- PASS if the column headers match exactly and only completed/approved runs are listed.
- FAIL if an in-flight or failed run appears in the list, or if a completed run is missing.

**Notes**
- `/transcripts` has no sidebar entry — reach it from the address bar or by following a link. The
  sidebar highlights **Phases & Runs** while you are on it; that is intended (see TS-12 TC-167).

---

### TC-165 · Opening a transcript shows the read-only replay with the provenance banner

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | Functional |
| Priority | High |
| Screen | `/transcripts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-164 passed and at least one row is listed.

**Steps**
1. Go to `/transcripts` and click **Open transcript** on the top row.
2. Read the panel title and the controls in its top-right corner.
3. Read the body of the transcript.
4. Read the banner at the bottom of the panel.
5. Try to click into a turn and edit its text.

**Expected**
- The panel is titled `{run id} · {Phase}` using the humanized phase name.
- Its top-right shows `Engine` followed by the engine name in bold, and a cost badge (a dollar
  amount, or `—` when no cost was recorded).
- The conversation replays as a sequence of turns — agent turns, tool calls and any human answers to
  clarifications from TS-08.
- A banner at the bottom reads
  `Read-only replay — transcripts are stored for provenance and cannot be edited.`
- Nothing on the screen is editable: no text cursor lands in a turn, and there is no Save, Edit,
  Delete or Retry control.

**Pass / Fail**
- PASS if the replay renders with the footer banner and nothing is editable.
- FAIL if any turn can be edited or removed (that is **High** — provenance must be immutable), or
  if the banner is missing.

---

### TC-166 · A run with no captured turns, and an unknown run id, both degrade gracefully

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | Negative |
| Priority | Medium |
| Screen | `/transcripts/:id` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-165 passed, so you have a working transcript URL whose id you can edit.
- A run in the project that has **not** completed — one that is still running, or that failed or
  stalled. Tester C's in-flight and failed runs are all listed on `/runs`; any of them will do, and
  you do not need to trigger anything. Such a run has recorded no transcript yet, which is exactly
  the state under test.

**Steps**
1. Go to `/runs`, select the work item Tester C is running, and open a run that is **not**
   completed — the run console at `/runs/{id}` shows its status. Copy the run id out of the address
   bar.
2. In the address bar, replace the id in your working transcript URL with that run id, so you are
   on `/transcripts/{that id}`, and press Enter.
3. Read the panel title, the panel body and the banner below it.
4. Now replace the id with `00000000-0000-0000-0000-000000000000` and press Enter.
5. Read the panel.

**Expected**
- Step 3: the panel renders its `{run id} · {Phase}` title with the `Engine` and cost controls in
  its top-right, and in the body an empty state titled `No transcript recorded` with the text
  `This run has no captured conversation yet.` The banner
  `Read-only replay — transcripts are stored for provenance and cannot be edited.` is still shown
  below it.
- Step 5: a danger banner titled `Transcript not found` with the text
  `This run doesn't exist or you don't have access to it.`, under the breadcrumb
  `Phases & Runs / Transcripts`, inside the normal app shell.

**Pass / Fail**
- PASS if the not-yet-completed run shows `No transcript recorded` **inside a panel titled with its
  own run id**, and the unknown id shows `Transcript not found`.
- FAIL if either state blanks the screen or leaks a raw 404/500 body.
- FAIL if the two are swapped — a real run reported as `Transcript not found` is misleading, and an
  unknown id reported as `No transcript recorded` invents a run that does not exist.

**Test data**
- Unknown run id: `00000000-0000-0000-0000-000000000000`

**Notes**
- Reaching `/transcripts/{id}` for a non-completed run is legitimate: the transcript route accepts
  any run id, even though the `/transcripts` **list** deliberately shows only completed and
  approved runs (TC-164). You are deep-linking through the address bar, not bypassing anything.
- If the run you picked in step 1 completes between steps 1 and 2 you will see real turns instead
  of the empty state. That is not a failure — pick another non-completed run and repeat.

---

### TC-251 · A failed lineage request shows an error panel with `Try again`, not `No lineage yet`

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | UX |
| Priority | High |
| Screen | `/traceability` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-157 passed, so `Payment Gateway v2` has a populated graph.
- P1 is a member of a second project as well.
- You can stop and restart the backend process. It will be down for about a minute.
- **Do not reload the browser tab during this case.** A reload re-requests your session, which
  fails with the backend down and bounces you to `/login`, and you observe nothing. Every step is
  an in-app navigation.

**Steps**
1. Go to `/traceability` with `Payment Gateway v2` selected and confirm nodes are drawn. Note the
   node count.
2. Stop the backend.
3. **Without reloading**, switch the top-bar project select to the second project. This forces a
   fresh lineage request the browser has never made.
4. Wait about 15 seconds — the app retries a failed request a few times before giving up — then
   read the whole screen. Note the heading, the filter selects, the legend, and the title and text
   of whatever replaces the graph.
5. **Cleanup — mandatory.** Restart the backend, wait for it to come up, click **Try again**, then
   switch back to `Payment Gateway v2`. Confirm the graph from step 1 returns.

**Expected**
- The `Traceability` heading, its sub-heading, the three filter selects (showing only `Phase: All`,
  `Type: All`, `Highlight: none`) and the five-entry legend still render.
- In place of the graph, a danger banner titled `Can't reach the SDLC app right now` reads
  `Your browser couldn't connect.`, followed by a **Try again** button and the line
  `This screen is empty because it didn't load — not because there is nothing here.`
- `No lineage yet` does **not** appear, and no status code or raw error text is visible.
- Step 5: after **Try again** with the backend up, the second project's map (or its
  `No lineage yet` state) renders, and switching back restores the graph from step 1.

**Pass / Fail**
- PASS if the failed request shows the `Can't reach the SDLC app right now` panel with a working
  **Try again**, and never `No lineage yet`.
- FAIL if the failure renders as `No lineage yet`, if there is no **Try again**, or if the app
  blanks, crashes, shows a raw error body, or redirects to `/login`.

**Notes**
- **Rewritten for commit 6d85ec9.** This case used to record that a failed request showed
  `No lineage yet`, so TC-161 passed on a broken backend. The screen now checks for a failure first
  (`TraceabilityView.tsx:167-177`), so an empty map and a failed request look different.
- Stopping the backend is a lost connection, which gives the copy above. A server fault would
  instead read `Something went wrong on our side` /
  `The app couldn't load this. Nothing you did caused it.` Record the title you saw.

---

### TC-252 · A failed runs request renders `No transcripts yet`, not an error

| Field | Value |
|---|---|
| Suite | TS-11 Traceability & Transcripts |
| Type | UX |
| Priority | Medium |
| Screen | `/transcripts` |
| Persona | P1 Owner-Admin |
| Automation | No |

**Preconditions**
- TC-164 passed, so `/transcripts` lists at least one completed run on `Payment Gateway v2`.
- P1 is a member of a second project.
- You can stop and restart the backend. It will be down for about a minute.
- **Do not reload the browser tab during this case** — see TC-251's precondition for why.

**Steps**
1. Go to `/transcripts` with `Payment Gateway v2` selected and confirm rows are listed.
2. Stop the backend.
3. **Without reloading**, switch the top-bar project select to the second project, then navigate to
   `/transcripts` by clicking `Phases & Runs` in the sidebar and editing the address bar to
   `/transcripts` — do not press reload.
4. Wait about 15 seconds, then read the exact title and text of whatever replaces the table.
5. **Cleanup — mandatory.** Restart the backend, switch back to `Payment Gateway v2`, and confirm
   the rows from step 1 return.

**Expected**
- The breadcrumb `Phases & Runs / Transcripts`, the heading `Run transcripts` and its sub-heading
  all render normally.
- In place of the table, an empty state titled `No transcripts yet` with the text
  `Once you run a phase, its full session is captured here for read-only replay.`
- No error banner, no retry control and no status code anywhere on the screen.

**Pass / Fail**
- PASS if the failed request renders the ordinary `No transcripts yet` empty state with no failure
  signal.
- FAIL if the app blanks, crashes, shows a raw error body, or redirects to `/login`.

**Notes**
- This is the "failed request looks empty" defect that commit 6d85ec9 fixed on the dashboard,
  artifacts and traceability screens (TC-261, TC-241, TC-251) but **not** here: the transcripts list
  has no failure branch (`RunTranscriptScreen.tsx:106-116`). It is tracked — **do not raise it
  again**. The value of this case is that
  it puts on record that the `/transcripts` empty state is also indistinguishable from a failure,
  so a tester who sees it must confirm the backend is up before concluding "Tester C has run
  nothing".

---

### TC-944 · Every name sits inside its box on the map

**Why this case exists.** Boxes were a fixed width and names were cut by counting 22 letters, which
at that font is wider than the box, so names ran past the border. Bugs S.No 352.

**Steps**
1. Open **Traceability** on a project with documents that have long names
   (e.g. "PeopleDesk — Market Sizing & Organizational Value").
2. Hover a box.

**Expected**
- Three boxes per row. Each name wraps onto a second line if it needs to, and ends in "…" only when
  it is longer than two lines.
- No text crosses a box's border.
- Hovering shows the full name and its phase and status.

**Pass / Fail**
- **FAIL on any text outside its border.**

---

### TC-945 · The legend explains only what is on the map

**Why this case exists.** All five statuses were always listed. A map of only published documents
carried four colours that explained nothing, and "Approved" — reached only by a signed accessibility
conformance report — read as stale. Bugs S.No 353.

**Steps**
1. Open **Traceability** on a project where every document is published.
2. Run a phase to its gate (documents waiting for approval) and reload.
3. Filter by a Phase that has only published documents.

**Expected**
- Step 1: the legend shows **Published** only.
- Step 2: **Published** and **Waiting for approval**.
- Step 3: the legend follows the filter.

**Pass / Fail**
- **FAIL on a legend colour no box on the map has.**

---

### TC-946 · The third filter says what it highlights

**Why this case exists.** It read "Highlight: none", which looked like "no results" and never said
what gets highlighted. Bugs S.No 354.

**Steps**
1. Open the third filter on **Traceability**.
2. Pick a work item. Then pick **Highlight: All work items**.

**Expected**
- Closed with nothing picked: **Highlight: All work items**.
- After picking: **Highlight: WI-1 People Desk - Ideation**; that item's documents stay bright and
  every other document fades (nothing disappears).
- Picking **All work items** again brings every box back to full strength.

**Pass / Fail**
- **FAIL if picking an item hides documents instead of fading them.**
