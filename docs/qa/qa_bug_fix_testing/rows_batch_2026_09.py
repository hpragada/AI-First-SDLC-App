# -*- coding: utf-8 -*-
"""Rows for the 2026-09 bug batches (commits 4ac75f9 and b40c557), placed into passes by passes.py."""

ROWS = {

81: ("DEV CHECK",
 "Two automated checks that confirm the requirements and design agents read their inputs from the "
 "platform had been failing for a long time. They were written for the old way the agent's "
 "instructions were handed to the engine, and when that changed to handing them over as a file, "
 "the checks were never updated. The app itself was not affected - only the checks were stale, which "
 "meant a real fault in that area could have gone unnoticed.",
 "Both checks were rewritten to read the instructions from the file the engine is actually given. "
 "No change to the app.",
 "This is not visible in the app - a developer confirms it.\n"
 "1. Ask a developer to run the two agent-migration test files on the current code.\n"
 "PASS: both files pass, including the two checks that prove the requirements and design agents "
 "read their inputs from the platform.\n"
 "FAIL: either check errors or fails."),

85: ("DURING A RUN",
 "The Testing agent's instructions were written as if it could run the test suite, measure "
 "coverage and write end-to-end test files into the code - but the Testing phase is a planning "
 "phase with no access to do any of that. The same work was also already the job of the Test "
 "Automation agent. So the first real Testing run would either fail or hand back a results report "
 "for tests nobody ever ran.",
 "The Testing agent is now planning-only. It writes the test plan and one test case per case, and "
 "hands that specification to Test Automation, which builds and runs the tests. Its instructions "
 "now say plainly that it never produces a test results report - results only ever come from a real "
 "Test Automation run.",
 "SET UP: a work item that has been through the earlier planning phases, so the Testing phase has "
 "requirements and a design to work from.\n"
 "1. On Phases & Runs, pick that work item and click '▶ Testing'.\n"
 "2. Let the run finish and reach its gate.\n"
 "3. Open Artifacts & Traceability and look at what the Testing run produced (use 'Preview ↗' on "
 "its gate, which shows only that run's documents).\n"
 "PASS: there is a test plan and a set of test cases, each test case as its own document.\n"
 "PASS: there is NO test report among them.\n"
 "FAIL: a test report from the Testing phase, or a document that claims tests were run, coverage was "
 "measured or results were recorded.\n"
 "4. Open one or two test cases.\n"
 "PASS: they read as cases to be run (steps, expected results), not as results."),

104: ("DIRECT",
 "Create Project asked you to choose Single or Multi-repo, but the platform ignored that choice: the "
 "moment you added repositories it worked the topology out from how many there were. A user who "
 "chose Multi-repo and added two repositories ended up with something different from what they "
 "picked, and the form never offered the third option the platform actually uses.",
 "The topology choice was removed from Create Project. The platform now works it out from the "
 "repositories you register, in one place, and the Repositories screen shows that value.",
 "1. Open the create-project page (go to /projects/new in the address bar).\n"
 "2. Look at the whole form.\n"
 "PASS: the heading reads 'Create a project', the form asks for a name and a Track (greenfield or "
 "brownfield), and there is NO Single / Multi-repo choice anywhere on it.\n"
 "3. Create a greenfield project, then open Repositories and add two repositories.\n"
 "PASS: the chip above the table reads 'Topology: split'.\n"
 "4. Add a third repository.\n"
 "PASS: the chip now reads 'Topology: multi'.\n"
 "FAIL: a topology picker on Create Project, or a chip that disagrees with the number of "
 "repositories."),

117: ("DIRECT",
 "On the Work Items board, work items that nothing had run on yet were dropped into whichever column "
 "happened to be first - Ideation on the normal board, Implementation when filtered to Tasks. So "
 "brand-new work looked as if it were already under way, and an item jumped columns when you changed "
 "the filter. Code-review tasks also sat in Implementation instead of Review. And a card gave no "
 "sign of what its phase was doing, so a failed run looked the same as a running one.",
 "The board has a new Backlog column for work nothing has run on. Code-review tasks land in Review. "
 "Every card carries a status pill saying what its phase is doing: Not started, Running, Waiting "
 "for you, Done or Failed (and Cancelled for a cancelled item).",
 "SET UP: a project where Task Breakdown has created tasks that have not been run yet, plus at least "
 "one work item with a running or finished phase. A task that has been through Code Review helps "
 "for step 5.\n"
 "1. Open Work Items in Board view.\n"
 "PASS: the first column is 'Backlog', and the not-yet-run items are there.\n"
 "PASS: each of those cards carries a 'Not started' pill.\n"
 "FAIL: not-yet-run items sitting in Ideation.\n"
 "2. Look at an item whose phase is running.\n"
 "PASS: it is in that phase's column with a 'Running' pill.\n"
 "3. Look at an item whose phase has finished and been approved, and one whose run failed.\n"
 "PASS: 'Done' on the first, 'Failed' on the second.\n"
 "4. Click the 'Tasks' level filter.\n"
 "PASS: the columns are Backlog, Implementation and Review, and the not-yet-run tasks are in "
 "Backlog - NOT in Implementation.\n"
 "5. Find a task whose latest run is Code Review.\n"
 "PASS: it is in the Review column.\n"
 "FAIL: code-review tasks in Implementation.\n"
 "NOTE: which cards say 'Waiting for you' is tested separately under S.No 260."),

132: ("DURING A RUN",
 "When a build opened its pull request, the platform put a 'build' check on the commit in GitHub and "
 "set it to pending - and never moved it. It stayed pending forever. Harmless while nobody requires "
 "that check, but the moment anyone makes it required on GitHub, every merge would be blocked for "
 "good.",
 "Every way a build can end now finishes the check: success when the build is merged, failure when "
 "the build fails, when changes are rejected at the merge gate, or when the platform stops the build "
 "and hands it to a person. A build that never pushed anything has no commit, so nothing is posted.",
 "SET UP: a project connected to a GitHub repository you can open, and a task ready to build. You "
 "need to see the pull request on GitHub.\n"
 "1. Run a build and let it open its pull request.\n"
 "2. On GitHub, open the pull request's checks.\n"
 "PASS: there is a check named 'sdlc/build', pending, with the description 'Build in progress.'\n"
 "3. Approve the merge gate in the app and let it merge.\n"
 "4. Look at the same check on GitHub.\n"
 "PASS: 'sdlc/build' is now green (success) with the description 'Build merged.'\n"
 "FAIL: still pending after the merge.\n"
 "5. Run a second build and this time click 'Reject' at its merge gate.\n"
 "PASS: 'sdlc/build' on that pull request turns red (failure) with the description 'Changes were "
 "rejected at the merge gate.'\n"
 "6. If you see a build fail on its own, check that pull request too.\n"
 "PASS: 'sdlc/build' is red, and its description is the failure reason."),

166: ("DIRECT",
 "On Phases & Runs, the 'Search work items' dropdown was cut off by the panel it sits in. With a "
 "handful of work items - too few for the list to grow a scrollbar, enough to cross the panel's edge "
 "- the bottom items were simply unreachable. The '...' action menu on each row of the Work Items "
 "list had the same fault; it went unnoticed only because that menu is short.",
 "Every dropdown, menu and tooltip in the app is now drawn above the page, so no panel can cut it "
 "off. Near the bottom of the window a list opens upwards instead of downwards, and it follows its "
 "field when the page scrolls. Clicking an item in a list still picks it, and clicking elsewhere "
 "still closes it.",
 "SET UP: a project with about 5-10 work items.\n"
 "1. Open Phases & Runs and click into the 'Search work items…' box.\n"
 "PASS: every work item in the list can be seen or scrolled to. None is cut off at the panel edge.\n"
 "FAIL: the last items hidden behind the edge of the panel.\n"
 "2. Pick one with the mouse.\n"
 "PASS: it is chosen and the list closes.\n"
 "3. Make the browser window short, or scroll so the box is near the bottom of the window, and open "
 "the list again.\n"
 "PASS: the list opens UPWARDS, above the box, instead of running off the bottom of the window.\n"
 "4. With the list open, scroll the page a little.\n"
 "PASS: the list stays attached to its box.\n"
 "5. Click somewhere else on the page.\n"
 "PASS: the list closes.\n"
 "6. Open Work Items, switch to 'List', and click the '...' at the end of a row near the bottom of "
 "the table.\n"
 "PASS: the menu shows 'Open' (and 'Cancel…' on an item that can still be cancelled) in full, not "
 "clipped by the table.\n"
 "PASS: clicking 'Open' opens the item.\n"
 "7. Open the account menu (your initials, top right) and hover any 'i' help icon on a screen that "
 "has one.\n"
 "PASS: both still open and close normally."),

178: ("SET UP FIRST",
 "The security gate could be approved while Critical or High security findings were still open. The "
 "Security agent's own rules say that must never happen, but the platform had no such rule - the "
 "security gate was a plain approval, and the only thing standing between an open Critical and a "
 "passed gate was a careful reviewer.",
 "The security gate now carries a required checklist item that the platform checks itself: 'No "
 "unresolved Critical or High security finding — every one the security review raised has been "
 "fixed'. It is worked out from the open security defects on the work item, so it clears by itself "
 "once those findings are resolved. It also applies to security gates that were already waiting when "
 "this was released.",
 "SET UP: a Security run that raised at least one Critical or High finding, so defect work items for "
 "those findings are open under the work item (see S.No 177 for how to produce one). Sign in as a "
 "Security Engineer on that project, or an admin.\n"
 "1. Open Gates and select that work item's security gate.\n"
 "PASS: the panel shows a 'Required checklist' containing 'No unresolved Critical or High security "
 "finding — every one the security review raised has been fixed *', NOT ticked.\n"
 "PASS: the Approve button reads 'Approve (1 remaining)' and cannot be clicked.\n"
 "2. Click the checklist line to tick it yourself, then click Approve.\n"
 "PASS: the gate is NOT approved. A red box 'Couldn't record the decision' appears and names the "
 "open findings by severity and title.\n"
 "FAIL: the gate is approved while the findings are still open.\n"
 "NOTE: record the exact wording of that red box in your comment - it currently begins 'cannot "
 "approve: 1 required gate condition(s) unmet:' followed by an internal name for the rule, which a "
 "client should not see.\n"
 "3. Resolve the findings (let a later Security run report them fixed, or cancel the open defect "
 "work items), then reopen the gate.\n"
 "PASS: the checklist line is now ticked on its own, and Approve works.\n"
 "4. Open a gate for any OTHER phase.\n"
 "PASS: it does not carry this security checklist line."),

183: ("DURING A RUN",
 "When a phase was re-run, the platform decided whether a document was a new version of an earlier "
 "one by comparing the title the agent wrote. Titles are free text, so a re-run that worded a title "
 "even slightly differently registered a second copy at version 1 beside the first, instead of "
 "making version 2. Worst on the Security phase, which files one document per finding.",
 "Where a document carries a stable identifier of its own - a security finding's ID, a test case's "
 "ID - the platform now uses that to decide it is the same document, and only falls back to the title "
 "when there is none. A re-worded title on a re-run now becomes the next version, not a duplicate.",
 "SET UP: a work item whose Security phase has already run once and registered findings.\n"
 "1. Open Artifacts & Traceability and note the security findings and their version numbers "
 "(for example 'v1').\n"
 "2. Re-run the Security phase on the same work item and let it finish.\n"
 "3. Look at the Artifacts list again.\n"
 "PASS: each finding that came back again appears ONCE, now at the next version (for example 'v2'), "
 "even if its title is worded a little differently this time.\n"
 "FAIL: two copies of the same finding, both at 'v1'.\n"
 "4. Open one re-run finding's Preview.\n"
 "PASS: its version list shows both versions, the older one marked 'Superseded'.\n"
 "5. If the project uses test cases, re-run the Testing phase and check the same thing for test "
 "cases with the same case number."),

184: ("DURING A RUN",
 "On Clarifications, a question with a list of answer choices used the browser's own dropdown. When "
 "an agent wrote long, sentence-length choices, the list ran off the sides of the question card on "
 "one unbroken line and could push text off the screen.",
 "The answer dropdown is now drawn by the app. It is exactly as wide as its field, and long choices "
 "wrap onto more lines inside it. It still works fully from the keyboard, and choosing an 'Other' "
 "style option still reveals a box to type your own answer.",
 "SET UP: a run that has asked a question with a list of choices - ideally long ones.\n"
 "1. Open Clarifications and find the question. Click the box that reads 'Choose one…'.\n"
 "PASS: the list opens directly under the box, the same width as the box, and long choices WRAP onto "
 "several lines. Nothing spills outside the card or the window.\n"
 "FAIL: choices running off the card on one line.\n"
 "2. Click a choice.\n"
 "PASS: the box now shows that choice and the list closes.\n"
 "3. Keyboard: Tab to the box, press Enter (or Space) to open it, use the Up and Down arrows to move, "
 "and press Enter to pick.\n"
 "PASS: all of that works, and Escape closes the list without changing the answer.\n"
 "4. If the question offers an 'Other' or 'Something else - please specify' choice, pick it.\n"
 "PASS: a text box with 'Please specify…' appears under the dropdown.\n"
 "5. Type an answer there and submit.\n"
 "PASS: the answer recorded is what you typed."),

212: ("DIRECT",
 "On Repositories, 'Set default' did nothing - its click was never wired to anything, even though "
 "the platform could already do it. Most of the time the button was not even there, because the "
 "screen worked out the project's topology with its own rule, which disagreed with the platform's. "
 "Opening the add-repository form also switched the table to a layout with no Set default, and the "
 "form never closed again.",
 "Set default now works: the green 'default' marker moves to the row you chose, and that row's "
 "button disappears. The button is offered on every non-default row whenever the project has two or "
 "more repositories. The topology chip shows the platform's own value. The add form closes after a "
 "repository is added, and has a Cancel button. If you are not allowed to change the default, the "
 "screen says why in plain words.",
 "SET UP: a project with at least two repositories. You need a Tech Lead or admin on that project "
 "for steps 1-5, and a second user with neither role for step 6.\n"
 "1. Open Repositories.\n"
 "PASS: the chip reads 'Topology: split' for two repositories, 'Topology: multi' for three or more.\n"
 "PASS: one row has a green 'default' marker beside its base branch; every OTHER row has a 'Set "
 "default' button.\n"
 "2. Click 'Set default' on a row that is not the default.\n"
 "PASS: the 'default' marker moves to that row, its button disappears, and the old default row now "
 "has a 'Set default' button.\n"
 "3. Reload the page.\n"
 "PASS: the new default is still the default.\n"
 "4. Click '+ Add repository'.\n"
 "PASS: the form opens above the table, and the table below still shows every row with its buttons.\n"
 "5. Add a repository.\n"
 "PASS: the form closes by itself and the new repository is in the table. Open the form again and "
 "click 'Cancel' - it closes.\n"
 "6. Sign in as the user with neither role and click 'Set default'.\n"
 "PASS: a box 'Couldn't set the default repository' says 'Only a tech lead or an admin can change "
 "which repository is the default for this project.'\n"
 "FAIL: nothing happens, or the message names a role like 'tech_lead'."),

215: ("DIRECT",
 "Adding a test case to a story saved it, but the test-case table on screen did not refresh - the "
 "new case only appeared after reloading the page. It looked as if saving had failed, which invites "
 "creating the same case twice. The same happened after 'Generate script': the row kept showing "
 "'Generating…' until a reload.",
 "The table now refreshes as soon as a test case is added, and after 'Generate script' is clicked. "
 "While any row is generating, the table checks again every few seconds by itself, and stops once "
 "nothing is generating.",
 "1. Open a story work item and click 'Test cases'.\n"
 "2. Click '+ Add test case', fill in a title and steps, and click 'Add test case'.\n"
 "PASS: the new test case appears in the table straight away, without reloading.\n"
 "FAIL: the table only shows it after a reload.\n"
 "3. On a test case that has no script yet, click 'Generate script' (the companion needs to be "
 "running).\n"
 "PASS: the row changes to 'Generating…' without a reload.\n"
 "4. Leave the page open and wait for the script to finish.\n"
 "PASS: the row changes to 'Script ready' by itself, without a reload."),

218: ("DURING A RUN",
 "Three problems with how a document's status was shown. Opening a gate did not change its "
 "documents at all, so a document waiting on a reviewer still read 'Draft' - no different from a "
 "draft nobody had been asked to look at. The preview screen showed one message for two different "
 "situations: 'This artifact doesn't exist, has no body, or you don't have access to it' - three "
 "explanations at once, only one true. And a build rejected at its merge gate left its code sitting "
 "as waiting forever.",
 "When a gate opens, the documents it covers now show 'Waiting for approval' - on the Artifacts list, "
 "on the preview screen and on the traceability map, which all use the same words and colours. "
 "Approving publishes them; rejecting marks them 'Superseded'. The preview screen now says either "
 "that the document can't be found, or that its preview is unavailable, whichever is true. A "
 "rejected build now marks its code 'Superseded'.",
 "SET UP: trigger a planning phase (for example PRD) and let it reach its gate. Do not decide it yet.\n"
 "1. Open Artifacts & Traceability.\n"
 "PASS: the documents that run produced show a 'Waiting for approval' badge, NOT 'Draft' and NOT "
 "'Staged'.\n"
 "2. Open the 'Status: All' filter.\n"
 "PASS: it offers 'Waiting for approval' in the same words as the badge.\n"
 "3. Open one of those documents' Preview.\n"
 "PASS: its status reads 'Waiting for approval', and the version list shows statuses in words.\n"
 "4. Open Traceability.\n"
 "PASS: the legend lists Published, Approved, Waiting for approval, Draft and Superseded, and the "
 "waiting documents are drawn in the 'Waiting for approval' colour.\n"
 "5. Approve the gate, then look again.\n"
 "PASS: those documents no longer say 'Waiting for approval'.\n"
 "6. Run a second phase to its gate and click 'Reject'.\n"
 "PASS: its documents now read 'Superseded'.\n"
 "7. Change the address of a preview page so the document's code at the end is wrong.\n"
 "PASS: 'We couldn't find that document' with 'It may have been removed, or you may not have access "
 "to this project.'\n"
 "FAIL: the old three-explanation message.\n"
 "8. If you see a build rejected at its merge gate, check its code document in Artifacts.\n"
 "PASS: it reads 'Superseded', not 'Waiting for approval'.\n"
 "NOTE: 'Preview unavailable' only shows for a document whose stored copy is missing, which a tester "
 "cannot normally create. Record it if you meet it."),

222: ("SET UP FIRST",
 "The dashboard tiles read 'Gates need your approval' and 'Questions awaiting you', but they counted "
 "every pending gate and question on the project, whoever they were for - only 'My runs in flight' "
 "was really personal. The gates tile's subtitle named the role of whichever gate happened to be "
 "first, which could be a role you do not hold. Both counts also stopped at 20, so a busy project "
 "under-reported.",
 "The gates tile now counts only gates you may decide (the gate's role on this project, or any gate "
 "if you are an admin). The questions tile counts questions on projects you are a member of. The "
 "numbers are true totals, not capped, and the subtitle says '{N} waiting on you' or 'nothing "
 "waiting on you'. The 'Needs me' list underneath and the bell count follow the same rules.",
 "SET UP: two users on the same project. User A holds the role a pending gate needs (for example "
 "Product Owner for a PRD gate). User B is a project member who does NOT hold that role and is not "
 "an admin. Invite B on Users & invitations and set roles on Roles & memberships. Have at least one "
 "pending gate needing A's role, and one pending question.\n"
 "1. Sign in as A and open the Workspace Dashboard.\n"
 "PASS: 'Gates need your approval' counts that gate, and its subtitle reads '1 waiting on you' (or "
 "the right number).\n"
 "PASS: the gate is listed under 'Needs me' with a 'Review' button.\n"
 "2. Sign in as B and open the dashboard.\n"
 "PASS: 'Gates need your approval' does NOT count that gate; with nothing else for B it reads 0 and "
 "'nothing waiting on you'.\n"
 "PASS: the gate is NOT in B's 'Needs me' list.\n"
 "PASS: the pending question IS counted and listed for B, because B is a project member.\n"
 "FAIL: B is shown a gate only A's role can decide.\n"
 "3. Sign in as a workspace admin.\n"
 "PASS: the admin's gates tile counts every pending gate on the project.\n"
 "4. Compare the bell count in the top bar with the tiles for each user.\n"
 "PASS: the bell agrees with that user's own gates plus questions.\n"
 "5. If you have a project with more than 20 pending gates, check the tile.\n"
 "PASS: it shows the full number, not 20."),

224: ("SET UP FIRST",
 "The dashboard's 'Published this week' figure, and the recently-published list, counted documents "
 "by the date the agent drafted them, not the date they were published. Drafting and publishing are "
 "separated by a review, often by days, so a document drafted last week and published this morning "
 "was missed, and one drafted today but never published could be counted.",
 "The platform now records the moment each document is published and counts by that. Publishing "
 "the same document again later keeps its first publish date. Documents published before this change "
 "were given the best available date - the last time their status changed.",
 "SET UP: a document that was drafted more than a week ago and has not been published yet (a gate "
 "left waiting, or a draft from an older run).\n"
 "1. Open the Workspace Dashboard and note 'Published this week'.\n"
 "2. Approve or publish that older document today.\n"
 "3. Reload the dashboard.\n"
 "PASS: 'Published this week' has gone up by one, and the document appears in the recently "
 "published list.\n"
 "FAIL: no change, because the document was drafted more than a week ago.\n"
 "4. Let a phase draft a new document today but do NOT approve it.\n"
 "PASS: 'Published this week' does NOT go up for it."),

225: ("DIRECT",
 "Typing any unknown address under the admin section showed a developer placeholder page to the "
 "client's administrator - 'Foundation route mounted. Feature screens land in T2-T5', 'Ready for "
 "screen implementation', 'This route is auth-gated and rendered inside the Phase 4.8 app shell' - "
 "notes from one developer to another, with no way back.",
 "An unknown admin address now goes to Users & invitations, the way an unknown address elsewhere "
 "goes to the dashboard. The placeholder page was deleted.",
 "Sign in as a workspace admin.\n"
 "1. In the address bar, change the address to the admin section followed by a made-up page, for "
 "example /admin/anything.\n"
 "PASS: you land on 'Users & invitations'.\n"
 "FAIL: any page mentioning 'Foundation route mounted', 'T2-T5', 'Ready for screen implementation' "
 "or 'Phase 4.8'.\n"
 "2. Try a second made-up admin address, for example /admin/settings/xyz.\n"
 "PASS: same result.\n"
 "3. Click 'Workspace Admin' in the sidebar.\n"
 "PASS: Users & invitations opens as before, and Roles & memberships still opens normally."),

230: ("DEV CHECK",
 "The background briefing each agent receives before it starts included a list of recent events "
 "taken from the WHOLE workspace, not from its own project. A brand-new work item's agent was shown "
 "questions asked on other work items - from runs that had since been deleted - with no answers "
 "beside them. At best noise; at worst an agent treating another work item's questions as its own, "
 "or another project's work as relevant.",
 "Every event now records which project, and where there is one which work item, it belongs to. An "
 "agent's briefing now only lists events from its own project, and questions only from its own work "
 "item. Older events that carry no project are left out.",
 "This is not visible in the app - a developer confirms it.\n"
 "1. Ask a developer to start a phase on a brand-new work item in a project where other work items "
 "have had questions asked, and inspect the briefing the agent was given.\n"
 "PASS: the recent-events list holds only events from this project, and no question events from "
 "other work items.\n"
 "FAIL: events from another project, or questions from a different work item.\n"
 "2. Ask the developer to run the event-scope tests.\n"
 "PASS: they pass."),

254: ("DIRECT",
 "The Integrations page showed a Code intelligence card that always read 'Connected' and "
 "'Built-in', whatever the workspace really had. It was not something anyone could connect or "
 "change, and a real workspace could have no code-intelligence setup at all while the card said "
 "Connected.",
 "The Code intelligence card is removed. Code intelligence is now set up automatically for every "
 "workspace, new and existing, the same way accessibility checking already was. An old link or "
 "bookmark to the Code intelligence page - or any unknown capability address - now goes back to the "
 "Integrations page.",
 "1. Open Integrations.\n"
 "PASS: there are five cards - Document store, Task tracker, Design source, Code host and Test "
 "management. There is NO Code intelligence card.\n"
 "PASS: each card reads 'Connected' only if that capability really is connected; otherwise 'Not "
 "connected'.\n"
 "2. In the address bar, go to /integrations/codeintel.\n"
 "PASS: you are taken back to the Integrations page.\n"
 "FAIL: a page with a blank or 'undefined' title.\n"
 "3. Try a made-up one, for example /integrations/abcdef.\n"
 "PASS: same - back to Integrations.\n"
 "4. Click 'Connect' or 'Manage' on a real card.\n"
 "PASS: its connect page opens normally.\n"
 "5. If you can run brownfield onboarding, run the code-indexing step.\n"
 "PASS: it still works without any code-intelligence connection being set up."),

255: ("DIRECT",
 "The bell in the top bar showed a live count of what needed you, but clicking it did nothing. The one "
 "control saying 'something needs you' was the one that did not respond.",
 "Clicking the bell now opens the dashboard's 'Needs me' list, scrolled into view, with a link into "
 "every item. At zero it still opens, and the list says you are all caught up. It works from the "
 "keyboard too.",
 "1. On any screen other than the dashboard, note the number on the bell.\n"
 "2. Click the bell.\n"
 "PASS: the Workspace Dashboard opens with the 'Needs me' panel in view, and its items match the "
 "bell count.\n"
 "FAIL: nothing happens.\n"
 "3. Scroll to the top of the dashboard and click the bell again.\n"
 "PASS: the page brings the 'Needs me' panel back into view.\n"
 "4. Keyboard: Tab to the bell and press Enter.\n"
 "PASS: same result as a click.\n"
 "5. As a user with nothing waiting (no badge on the bell), click the bell.\n"
 "PASS: the dashboard opens at 'Needs me', which reads 'You're all caught up'."),

256: ("DIRECT",
 "Following a gate's 'Preview' link opens Artifacts narrowed to just that run's documents, with a "
 "'Showing part of the registry' notice and a 'Show the whole registry' button. That button did "
 "nothing: the address changed, but the list stayed narrowed.",
 "'Show the whole registry' now clears the narrowing, and the full list of the project's documents "
 "comes back. The narrowing is taken only from the link you followed, so it cannot linger once that "
 "link is gone.",
 "SET UP: at least one gate, pending or decided, on a project with documents from several runs.\n"
 "1. Open Gates and click 'Preview ↗' on a gate.\n"
 "PASS: Artifacts opens with the notice 'Showing part of the registry' - 'Everything one run "
 "produced, including superseded versions.' - and only that run's documents.\n"
 "2. Click 'Show the whole registry'.\n"
 "PASS: the notice disappears and the list now shows documents from every run in the project.\n"
 "FAIL: the list stays narrowed to the one run.\n"
 "3. Press the browser's Back button.\n"
 "PASS: the narrowed view and its notice come back.\n"
 "4. Also try 'Preview artifact under review ↗' in a selected gate's panel.\n"
 "PASS: the same behaviour."),

257: ("DIRECT",
 "In the work-item picker on Phases & Runs, each work item sits on one line as wide as the field, so "
 "a long title was cut off with '…' and the rest could not be read. Agents write long titles where "
 "the words that tell two items apart come at the end, so it was easy to pick the wrong one - and "
 "start a phase on the wrong work item.",
 "When a title is actually cut off, pointing at it - or moving to it with the arrow keys - opens it "
 "out over its own row so the whole title can be read. Short titles that fit behave exactly as "
 "before. The chosen item in the closed field does the same on hover. The work-item filter above the "
 "Gates and Clarifications history uses the same dropdown and gets the same behaviour.",
 "SET UP: at least two work items with long titles that start the same way, too long for the field.\n"
 "1. Open Phases & Runs and click into 'Search work items…'.\n"
 "2. Move the mouse over a row whose title ends in '…'.\n"
 "PASS: the full title opens out over that row, so the whole of it can be read.\n"
 "3. Move the mouse over a short title that fits.\n"
 "PASS: nothing opens out.\n"
 "4. Keyboard: with the list open, press the Down and Up arrow keys.\n"
 "PASS: when the highlight lands on a cut-off title, the full title opens out there; on a short one "
 "it does not.\n"
 "5. Pick a long-titled item, then hover the closed field.\n"
 "PASS: the full title shows over the field.\n"
 "6. On Gates, use the work-item filter above the decided-gates history ('All work items') and do "
 "steps 2-4 there. Repeat on Clarifications.\n"
 "PASS: the same behaviour on both."),

258: ("SET UP FIRST",
 "On Roles & memberships, the warning about gate roles nobody holds could never appear. It only "
 "showed when no admin could approve instead - but only an admin can open that page, so the reader "
 "was always that backup. An empty role was reported only as a red line at the bottom of the page, "
 "under a wide table.",
 "A one-line warning now shows at the top whenever any gate role has nobody on the project. It names "
 "the role when one is empty ('Nobody holds Architect on {project}.'), names both when two are "
 "empty ('Nobody holds Architect or Designer on {project}.'), and counts them beyond that ('{N} roles "
 "have nobody on {project}.'). It adds 'That gate falls to an admin meanwhile —' (or 'Those gates "
 "fall to an admin meanwhile —') and a 'see gate-role coverage' link that jumps to the coverage "
 "box. The page's intro now reads that a role nobody holds leaves its gate to an admin.",
 "Sign in as a workspace admin.\n"
 "SET UP: a project where you can grant and remove roles freely (a new test project is best).\n"
 "1. Open Workspace Admin, then Roles & memberships, on a project where every gate role has someone "
 "except ONE.\n"
 "PASS: a yellow warning line at the top reads 'Nobody holds {that role} on {project}. That gate "
 "falls to an admin meanwhile — see gate-role coverage.'\n"
 "2. Remove a second role holder so two roles are empty.\n"
 "PASS: 'Nobody holds {role 1} or {role 2} on {project}. Those gates fall to an admin meanwhile — "
 "see gate-role coverage.'\n"
 "3. Leave three or more roles empty (a brand-new project has most empty).\n"
 "PASS: still ONE line, reading '{N} roles have nobody on {project}.' - the roles are counted, not "
 "listed.\n"
 "4. Click 'see gate-role coverage'.\n"
 "PASS: the page scrolls to the 'Gate-role coverage' box, which lists each empty role as '— nobody'.\n"
 "5. Give every gate role a holder.\n"
 "PASS: the warning disappears.\n"
 "6. Read the line under the page title.\n"
 "PASS: it reads 'Per-project role grants. Each role gates specific decisions — a role nobody holds "
 "leaves its gate to an admin.'\n"
 "NOTE: the red, stronger wording ('…cannot be approved by anyone until someone holds the role') "
 "only appears when the workspace has no admin at all, which cannot happen while an admin is viewing "
 "the page. It cannot be tested from the app."),

259: ("DIRECT",
 "On Project profile, clicking Save with the Description empty simply did nothing - no red field, no "
 "message, nothing saved. The sentence explaining why had only ever been wired into the design "
 "preview. Every other field vanished from the form while the description was being asked for, so "
 "you could not tell whether what you had typed was kept. On a brand-new project that also meant "
 "setup never moved on.",
 "Description is now marked as required. Clicking Save with it empty shows 'A description is "
 "required — agents rely on it for every phase.' under the field and puts the cursor in it. Every "
 "other field stays on screen with what you typed. Typing a description clears the message. The "
 "platform applies the same rule, in the same words, to any save that sends an empty description.",
 "1. Open Project Profile on a project whose description is empty (or clear it).\n"
 "PASS: the 'Description' label carries a required marker (*).\n"
 "2. Fill in Domain and Tech stack, leave Description empty, and click 'Save'.\n"
 "PASS: under Description: 'A description is required — agents rely on it for every phase.', the "
 "field is outlined as invalid, and the cursor is in the Description box.\n"
 "PASS: Domain, Tech stack and all other fields are still on screen with what you typed.\n"
 "FAIL: nothing happens, or the other fields disappear.\n"
 "3. Type only spaces in Description and click Save.\n"
 "PASS: refused with the same message.\n"
 "4. Type a real description.\n"
 "PASS: the message disappears as you type.\n"
 "5. Click Save.\n"
 "PASS: it saves, with Domain and Tech stack kept.\n"
 "6. On a brand-new project that lands on the profile straight after Create Project, do steps 2-5.\n"
 "PASS: the same, and setup continues once a description is saved."),

260: ("SET UP FIRST",
 "The Work Items board put 'Waiting for you' on every card with a pending gate or question, whoever "
 "was looking. A Designer saw it on a build gate only a Tech Lead can decide - while their own "
 "dashboard said nothing was waiting for them.",
 "A card now says 'Waiting for you' only when the person looking may act on it: a gate whose role "
 "they hold on this project (or any gate if they are an admin), or a question on a project they are "
 "a member of - the same rules as the Approve and Answer buttons. Anyone else sees the waiting work "
 "in grey instead: 'Waiting for review' for a gate, 'Waiting for an answer' for a question.",
 "SET UP: two users on the same project, as in S.No 222. User A holds the role a pending gate needs; "
 "user B is a project member who does NOT hold that role and is not an admin. Have one work item "
 "waiting at that gate and one work item with an unanswered question.\n"
 "1. Sign in as A and open Work Items in Board view.\n"
 "PASS: the card waiting at the gate carries a 'Waiting for you' pill.\n"
 "PASS: the card with the question also says 'Waiting for you'.\n"
 "2. Sign in as B and open the same board.\n"
 "PASS: the gate card carries a GREY 'Waiting for review' pill - NOT 'Waiting for you'.\n"
 "PASS: the question card says 'Waiting for you' for B, because B is a member and may answer.\n"
 "FAIL: 'Waiting for you' on a gate B cannot decide.\n"
 "3. Still as B, open Gates and select that gate.\n"
 "PASS: B is not offered Approve - the board and the Gates screen agree.\n"
 "4. Sign in as a workspace admin.\n"
 "PASS: the gate card says 'Waiting for you'."),

261: ("DIRECT",
 "The filter boxes above the Work Items board and the Artifacts list had fixed widths, so longer "
 "choices were cut off in the closed box - the longer phase names, and a status such as 'Waiting for "
 "approval' - with no way to read them.",
 "Each filter box now sizes itself to fit the choice it shows, so nothing is cut.",
 "1. Open Work Items. Open the 'Phase: All' filter and pick the phase with the longest name.\n"
 "PASS: the closed box shows the whole phase name, not cut off.\n"
 "2. Do the same with the 'Role: All' and 'Status: All' filters.\n"
 "PASS: each shows its whole choice.\n"
 "3. Open Artifacts & Traceability. In the 'Phase: All', type and 'Status: All' filters, pick the "
 "longest choice in each - for status, 'Waiting for approval' if a gate is open.\n"
 "PASS: each closed box shows the whole choice.\n"
 "4. Make the browser window narrow.\n"
 "PASS: the boxes wrap onto a new line rather than running off the page."),

262: ("DIRECT",
 "Phases & Runs called the same work item three different things: the picker showed 'WI-159 · "
 "title', the line above the phase buttons showed eight characters of an internal code and the "
 "title, and the Runs panel showed only the bare title.",
 "All three places now read the same: the work item's number and title, for example 'WI-159 · "
 "title'. An item without a number shows its title - never an internal code.",
 "1. Open Phases & Runs and pick a work item in 'Search work items…'.\n"
 "2. Note how the picker shows it.\n"
 "PASS: 'WI-{number} · {title}'.\n"
 "3. Look at the label above the phase buttons.\n"
 "PASS: 'All phases — WI-{number} · {title}' - the same name.\n"
 "FAIL: a string of letters and digits in place of the WI number.\n"
 "4. Look at the right-hand side of the 'Runs' panel header.\n"
 "PASS: 'WI-{number} · {title}' - the same name again.\n"
 "5. Pick a different work item.\n"
 "PASS: all three update together to that item's name."),

263: ("DURING A RUN",
 "The 'Needs me' list on the dashboard named each item by eight characters of an internal code - "
 "for example 'Merge gate · 3f2a9c1b' - which matches nothing a client can search for or recognise, "
 "and run rows printed a code twice.",
 "Every row now names its work item by number and title. A gate row reads '{gate} · WI-{number} "
 "{title}', a question row 'Question · WI-{number} {title}', and a run row '{phase} run · WI-{number} "
 "{title}', with 'just started' or 'started {N}m ago' and the run's status underneath instead of a "
 "code.",
 "SET UP: sign in as a user who has at least one gate to decide, one question to answer and one run "
 "they started that is still running or waiting at a gate.\n"
 "1. Open the Workspace Dashboard and look at the 'Needs me' list.\n"
 "2. Look at a gate row.\n"
 "PASS: the title names the gate, then the work item's number and title. The line under it reads "
 "'required role: {role}'.\n"
 "3. Look at a question row.\n"
 "PASS: 'Question · WI-{number} {title}', with the question and how long it has waited underneath.\n"
 "4. Look at a run row.\n"
 "PASS: '{phase} run · WI-{number} {title}', and underneath 'just started · {status}' for a run "
 "under a minute old, or 'started {N}m ago · {status}'.\n"
 "FAIL: any row showing a string of letters and digits instead of a WI number.\n"
 "5. Click 'Review', 'Answer' or 'View' on the rows.\n"
 "PASS: each opens the right item."),

264: ("DIRECT",
 "The Traceability map had no filters on the real screen - the ones drawn for it only ever appeared "
 "in the design preview, wired to nothing, one offering a made-up 'WI-492'. On a project with "
 "hundreds of documents the map was a wall of boxes with no way to answer 'what came out of THIS "
 "work item?'.",
 "The map now has three filters. 'Phase' and 'Type' narrow the map to matching documents and show "
 "'{N} of {total} shown'. 'Highlight' picks one work item and dims everything else instead of "
 "hiding it, so its documents stand out while the rest stays in view. Documents adopted during "
 "onboarding, which belong to no work item, can be highlighted together as 'Not tied to a work "
 "item'. If a filter matches nothing, the map says 'Nothing matches these filters'.",
 "SET UP: a project with documents from several phases and several work items. A brownfield project "
 "with adopted documents helps for step 5.\n"
 "1. Open Traceability.\n"
 "PASS: three filters above the map: 'Phase: All', 'Type: All' and 'Highlight: none'.\n"
 "PASS: the filters offer only phases, types and work items that are on this map - no 'WI-492'.\n"
 "2. Pick a phase.\n"
 "PASS: only that phase's documents remain, and a note reads '{N} of {total} shown'.\n"
 "3. Also pick a type that phase does not have.\n"
 "PASS: 'Nothing matches these filters' with 'Clear the phase or type filter to see the whole map.'\n"
 "FAIL: 'No lineage yet' - the project does have lineage.\n"
 "4. Set Phase and Type back to All. Pick a work item under Highlight.\n"
 "PASS: that work item's documents stay bright; every other document is faded but still on the map "
 "and still clickable. No '{N} of {total} shown' note appears for a highlight.\n"
 "5. On a project with adopted documents, pick 'Not tied to a work item' under Highlight.\n"
 "PASS: the adopted documents stay bright and the rest fade.\n"
 "6. Set Highlight back to 'Highlight: none'.\n"
 "PASS: everything is at full strength again."),

265: ("DIRECT",
 "Beside the Roles & memberships page title sat a project dropdown with exactly one choice that did "
 "nothing - just under the real project switcher in the top bar. Two project pickers on one screen, "
 "only one of which worked.",
 "The dead dropdown is replaced by a plain line of text naming the project the roles belong to. "
 "Changing project is done, as everywhere else, with the switcher in the top bar.",
 "Sign in as a workspace admin.\n"
 "1. Open Workspace Admin, then Roles & memberships.\n"
 "PASS: beside the title is plain text reading 'Project {project name}', with the name in bold. It "
 "is NOT a dropdown.\n"
 "2. Switch project using the top bar's project switcher.\n"
 "PASS: the line changes to the newly selected project, and the table shows that project's roles."),

}
