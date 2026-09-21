# -*- coding: utf-8 -*-
"""Rows for the Screen Words Sweep (commit 014e4b7, groups 2-6, and the 2026-09-21 follow-up,
groups 7-9), truncation T9 + T13, and the team's own 2026-09-20 fixes (S.No 266-269) so the
combined QA pass covers them. Placed into passes by passes.py.

S.No 270 and 271 (Screen Words groups 1 and 1b) are ON HOLD with no code behind them, so they
have no procedure here - they are counted as open."""

ROWS = {

266: ("DURING A RUN",
 "When a code review failed to run - usually because the engine hit a usage limit part way "
 "through - the platform still recorded a review that said 'No findings were raised in this "
 "review cycle' and opened the merge gate. The approver was shown a clean review of code nobody "
 "had reviewed.",
 "A review that fails now stops the build and parks it with its own reason, instead of passing "
 "as a clean review. Resume re-runs only the review and keeps the build, branch and pull request. "
 "The review document says the review did not complete, and why.",
 "SET UP: a task whose build is about to reach code review. The simplest way to make the review "
 "fail is to stop the companion (Ctrl+C) after the review has started but before it finishes.\n"
 "1. Start the build and wait until the run console shows the code review running.\n"
 "2. Stop the companion.\n"
 "3. Restart the companion and wait for the run to settle.\n"
 "PASS: the run is parked with a reason saying the code review did not complete.\n"
 "PASS: no merge gate opens for this cycle.\n"
 "FAIL: a merge gate opens, or a review document says 'No findings were raised'.\n"
 "4. Click Resume.\n"
 "PASS: only the review runs again; the same pull request is used and no new branch appears."),

267: ("DURING A RUN",
 "When a code review failed, the companion sent the platform the reason, but the platform threw "
 "it away, and the companion printed nothing in its own window. Nobody could see why the review "
 "failed without digging through a log file on the developer's machine.",
 "The platform keeps the reason and shows it on the parked run. The companion also prints a "
 "'failed' line in its own window, like its other errors.",
 "SET UP: the same failed review as S.No 266 - the two are tested together.\n"
 "1. After the review fails, look at the companion's terminal window.\n"
 "PASS: a line starting '[companion]' says the review run failed and gives the reason.\n"
 "2. Open the parked run on the run console.\n"
 "PASS: the reason shown matches what the companion printed.\n"
 "FAIL: the companion's window shows nothing, or the run's reason is blank or generic."),

268: ("DIRECT",
 "A test case created by the Testing phase showed 'No description yet' on its detail page. The "
 "steps, preconditions and test data were never shown anywhere on the work item, even though they "
 "are what a person needs to read before running Test Automation.",
 "Test cases created by the Testing phase now show a 'Test case' panel with the case itself, read "
 "from its document, with a 'View artifact' link. Test cases added by hand keep their own "
 "description.",
 "SET UP: a project where the Testing phase has run and created test cases.\n"
 "1. On Work Items, open one of the test cases the Testing phase created.\n"
 "PASS: a 'Test case' panel shows the case's steps, preconditions and expected results.\n"
 "PASS: 'View artifact' opens the test case document.\n"
 "FAIL: 'No description yet', or an empty panel.\n"
 "2. Open a test case that was added by hand.\n"
 "PASS: it shows its own description, as before."),

269: ("DIRECT",
 "On a Work Items board with a very long column, the sideways scrollbar sat at the very bottom of "
 "the page. To reach the later columns you had to scroll down past every card first, and the "
 "column headings scrolled away.",
 "The board now fits the window. Each column scrolls its own cards, the headings stay in place, "
 "and the sideways scrollbar is always on screen.",
 "SET UP: a project with many work items in one column (SpendLog's Backlog has over 100).\n"
 "1. Open Work Items in board view.\n"
 "PASS: the sideways scrollbar is visible without scrolling the page down.\n"
 "2. Scroll inside the long column.\n"
 "PASS: only that column scrolls, and its heading stays visible.\n"
 "3. Switch to the list view.\n"
 "PASS: the list scrolls with the page, as before.\n"
 "FAIL: the scrollbar is below the window, or the whole page scrolls on the board view."),

272: ("SET UP FIRST",
 "When a document could not be published yet, the publish page printed its internal status - "
 "for example 'staged', a word the client never sees anywhere else - and 'Open gate' opened the "
 "whole Gates list instead of this document's own gate.",
 "The status now uses the same words as the Artifacts list, and the link says 'Open its gate' and "
 "opens this document's own gate. A document with no gate yet shows no link.",
 "SET UP: a document whose phase has run and is waiting at its gate (not yet approved).\n"
 "1. Open Artifacts & Traceability and open that document's publish page.\n"
 "PASS: the red 'Can't publish yet' banner names the status in plain words, the same word the "
 "Artifacts list uses for it.\n"
 "PASS: 'Open its gate ↗' opens the Gates screen with THIS document's gate selected.\n"
 "FAIL: a lower-case internal word such as 'staged', or a link that opens the unfiltered list.\n"
 "2. Try to publish anyway, if the button is offered.\n"
 "PASS: any refusal names the target in words ('the task tracker', 'the documentation store'), "
 "never 'tasktracker' or 'docstore'."),

273: ("DIRECT",
 "Gate panels, the attention card on a work item, and the Contracts & drift screen named roles by "
 "their stored keys - 'required role: product_owner', 'tech_lead', 'qa_lead'.",
 "Every role is named the same way everywhere, from one shared list: Product Owner, Tech Lead, "
 "QA Lead and so on.",
 "1. Open Gates and select a pending gate.\n"
 "PASS: the role line names the role in words, e.g. 'required role: Product Owner'.\n"
 "2. Open a work item that has a pending gate.\n"
 "PASS: the attention card says 'decided by a Product Owner' (or whichever role).\n"
 "3. Open Users & invites and look at the role column.\n"
 "PASS: the same role names as on the gates.\n"
 "FAIL: any underscore word - product_owner, tech_lead, qa_lead, security_engineer, "
 "release_manager - anywhere on these screens."),

274: ("DIRECT",
 "Many screens printed stored values as they are kept in the database: run statuses such as "
 "'awaiting_gate', document states such as 'extracted', repository roles such as 'backend', a "
 "36-character run id as a page title, and the Confluence icon on every artifact whatever system "
 "it lived in.",
 "Every stored value goes through one shared list of labels. Artifacts show the icon of the "
 "system they actually live in. The engine line on the run console is kept, written as the "
 "product and model name.",
 "1. Open Phases & Runs.\n"
 "PASS: run statuses read as words - 'Queued', 'Waiting for approval', 'Changes requested', "
 "'Paused - your machine stopped reporting' - with matching colours.\n"
 "2. Open a finished run's console, then its transcript.\n"
 "PASS: the transcript's title reads like 'PRD run · 5b4a1bab' - the phase and a short run "
 "reference - not a 36-character id.\n"
 "3. Open Artifacts & Traceability.\n"
 "PASS: each row's icon matches where it lives (Confluence, Jira, Git, inside the platform).\n"
 "4. Open Repositories and Source documents.\n"
 "PASS: roles read 'Backend', 'Frontend'; a processed document reads 'Ready to adopt'.\n"
 "FAIL: any lower-case or underscore value, a raw id as a title, or a Confluence icon on a "
 "document that is not in Confluence."),

275: ("SET UP FIRST",
 "About sixty messages the server sends when it refuses something were written for developers: "
 "they started lower-case, named internal keys and ids, or quoted raw values - for example 'No "
 "connector registered for docstore:notion.'",
 "Every refusal a person can trigger now says what went wrong and what to do, in plain words. "
 "Technical detail goes to the server log. An automated check now fails on any new message that "
 "breaks these rules.",
 "Trigger a few refusals and read each message.\n"
 "1. On Integrations, test a connection with a wrong token.\n"
 "PASS: the message says the credentials were rejected and what to check.\n"
 "2. Trigger a phase on a work item while its previous run is still going.\n"
 "PASS: the message starts 'This work item already has a run' and says what to do next.\n"
 "3. As a member without the right role, try to decide a gate.\n"
 "PASS: the message names the role needed in words.\n"
 "4. Try to publish a document before its gate is approved.\n"
 "PASS: the message names the target in words.\n"
 "FAIL (any step): a message that starts lower-case, contains an underscore word, a long id, or a "
 "value in quotes."),

276: ("SET UP FIRST",
 "Three failures happened in silence. (a) When the server refused a project profile save, the "
 "screen said nothing and the typed text looked saved until the page was reloaded. (b) Inviting "
 "someone who already had an account, or an invalid email, left the invite drawer sitting there "
 "with no message. (c) Logging in while the server was down said the password was wrong.",
 "Each now says what happened: the profile keeps what was typed and says why it was not saved; "
 "the invite drawer shows the reason; login says the app can't be reached and that the password "
 "was not checked.",
 "1. As a member who is NOT a Tech Lead or admin, edit the Project Profile and click Save.\n"
 "PASS: a message says why it was not saved, and everything typed is still on screen.\n"
 "2. As an admin, open Users & invites and invite an email that already has an account.\n"
 "PASS: the drawer says that person is already a member.\n"
 "3. Invite 'not-an-email'.\n"
 "PASS: the drawer says what is wrong with the email.\n"
 "4. Stop the backend (or ask a developer to), then try to log in with a correct password.\n"
 "PASS: 'Can't reach the SDLC app right now' - 'Your password wasn't checked. Try again in a "
 "moment.'\n"
 "FAIL: no message, a message saying the password is wrong, or typed text that disappears."),

277: ("DIRECT",
 "Two screens were built but nothing linked to them: Contracts & drift (API contracts between "
 "repositories) and Run transcripts. An old version of the app was also still in the code, "
 "though nothing loaded it.",
 "Repositories now links to 'API contracts & drift' on projects with more than one repository. A "
 "finished run's console links to its 'Full transcript'. The old app code was deleted.",
 "1. On a project with two or more repositories, open Repositories.\n"
 "PASS: 'API contracts & drift →' appears beside the topology chip and opens the Contracts & "
 "drift screen.\n"
 "2. On a project with one repository, open Repositories.\n"
 "PASS: no such link.\n"
 "3. Open the console of a run that has completed or been approved.\n"
 "PASS: 'Full transcript →' appears beside the status badge and opens that run's transcript.\n"
 "4. Open the console of a run that is still running, or failed.\n"
 "PASS: no transcript link.\n"
 "FAIL: a link missing where it should be, shown where it should not, or opening an empty page."),

278: ("DIRECT",
 "The accessibility product had the same problems: the conformance statement said 'required "
 "role: qa_lead' and 'Signed by ... · qa_lead', and messages from the pages list, audit, review "
 "and journeys started lower-case or showed raw values - for example \"route '/x' must start with "
 "`/`\" and 'this could not be read as a list of pages (Expecting value: line 1 column 1)'.",
 "The role reads 'QA Lead'. Every message a tester sees is a full sentence without internal words; "
 "parser and storage errors go to the server log instead of the screen.",
 "1. Open Accessibility → Conformance statement, before it is signed.\n"
 "PASS: the signing panel says 'required role: QA Lead'.\n"
 "2. Sign it (as the QA Lead) and look at the banner.\n"
 "PASS: 'Signed by <name> · QA Lead'.\n"
 "3. On the pages list, paste 'checkout' (no slash) and preview.\n"
 "PASS: 'checkout must start with a slash, such as /checkout ...'.\n"
 "4. Paste '[not json' and preview.\n"
 "PASS: 'This couldn't be read as a list of pages. Paste a list of paths ...' with no "
 "'Expecting value' text.\n"
 "5. As a member who is not the QA Lead, try to start a keyboard journey.\n"
 "PASS: 'Only the accessibility reviewer (QA Lead) on this project can start a keyboard journey.'\n"
 "FAIL: 'qa_lead', a message starting lower-case, or parser text on screen."),

279: ("DIRECT",
 "The design documents said a story belongs with delivery work (repository, branch, merge gate), "
 "but the app treated it as a planning item. The rail headings also said 'Plan tier' and "
 "'Build tier', which are internal words.",
 "The team decided a story is a planning item, as the app already had it, and the documents were "
 "corrected. The headings now read 'Lifecycle - Planning' and 'Lifecycle - Delivery'.",
 "1. Open a story work item.\n"
 "PASS: it opens the planning layout with its child items, headed 'Lifecycle - Planning'.\n"
 "2. Open a task work item.\n"
 "PASS: it opens the delivery layout with repository and branch, headed 'Lifecycle - Delivery'.\n"
 "3. Open an epic.\n"
 "PASS: headed 'Lifecycle - Planning'.\n"
 "FAIL: the word 'tier' in any heading, or a story showing a repository, branch or merge gate."),

281: ("SET UP FIRST",
 "When a build paused on an error, the run console showed the raw failure: a rejected GitHub "
 "token read 'pr/gate setup failed: CapabilityError: GitHub GET ... -> 401', run straight into "
 "the next sentence. A code review stopped by the AI engine's session limit was called a failed "
 "build and followed by ten lines of the engine's own output.",
 "The banner now says one plain sentence - what stopped, why, and what to do - and names the "
 "code review when it was the review that stopped. 'Nothing you've done is lost' is its own line. "
 "The raw text is kept under a closed 'Technical details'. The log lines read 'Build paused' and "
 "'Code review stopped'.",
 "SET UP A: a project whose GitHub connection uses a token you can revoke.\n"
 "1. Start a build; once it is running, revoke the token on GitHub.\n"
 "2. Let the build reach the step that opens the pull request, then open its run console.\n"
 "PASS: 'GitHub didn't accept the access token, so the pull request couldn't be opened. Ask your "
 "admin to reconnect GitHub in Integrations, then Resume.'\n"
 "PASS: 'Nothing you've done is lost - the build, branch and pull request are kept.' on its own "
 "line.\n"
 "PASS: 'Technical details' is closed; opening it shows the GitHub call and the 401.\n"
 "FAIL: 'pr/gate setup failed', 'CapabilityError' or '401' in the sentence itself.\n"
 "SET UP B: a build whose code review stops part way (stop the companion during the review, or "
 "let the AI engine reach its usage limit).\n"
 "3. Open the run console.\n"
 "PASS: the sentence starts 'The code review stopped because ...' and says 'The code has not "
 "been reviewed yet.' A usage limit also gives the time it resets.\n"
 "PASS: the log lines read 'Code review stopped - ...' and 'Build paused - code review "
 "stopped: ...', with no engine output in them.\n"
 "FAIL: 'The AI engine exited before finishing the build', 'review already completed', or "
 "lines of engine output in the banner or the log.\n"
 "4. Click Resume.\n"
 "PASS: only the review runs again.\n"
 "SET UP C: a planning phase (for example PRD) that stops part way - stop the companion during "
 "the run, or let the AI engine reach its usage limit.\n"
 "5. Open that run's console.\n"
 "PASS: the sentence names the phase, e.g. 'The PRD phase stopped because the AI engine ...', "
 "with 'Technical details' closed underneath, and the log line reads 'Run paused - ...' or "
 "'Run failed - ...'.\n"
 "FAIL: engine output or 'exit code' in the sentence."),

280: ("DEV CHECK",
 "When a phase ran again, the human's earlier answers to its questions were fed back to the agent "
 "- but the same set of answers could be fed back twice, and the list was oldest first while the "
 "space for it is cut from the end. So on a long list the newest decisions were the first thing "
 "the agent lost.",
 "Each set of questions is fed back once, with its newest answer, and the newest answers come "
 "first, so if anything is ever cut it is the oldest context.",
 "This is not visible in the app - a developer confirms it.\n"
 "1. Ask a developer to run the two tests named in the fix "
 "(test_the_same_questions_answered_twice_are_replayed_once_with_the_newest_answer and "
 "test_answered_clarifications_come_newest_first).\n"
 "PASS: both pass.\n"
 "FAIL: either fails."),

282: ("SET UP FIRST",
 "On Phases & Runs, hovering a work item whose title was too long for the dropdown made the full "
 "title flash on and off with every movement of the mouse, and a click could pick nothing. The "
 "run history filters had the same problem.",
 "The full title now sits still over the row while the mouse rests on it, and clicking it picks "
 "that row. Nothing else about how it looks has changed.",
 "SET UP: a project with at least one work item whose title is too long to fit in the picker.\n"
 "1. Open Phases & Runs and open the Work item picker.\n"
 "2. Rest the mouse on a row whose title ends in '...', then move it slowly across the row.\n"
 "PASS: the full title shows in one box over the row and stays steady.\n"
 "FAIL: the title flickers, jumps, or disappears while the mouse is still on the row.\n"
 "3. Click while the full title is showing.\n"
 "PASS: that work item is picked and the list closes.\n"
 "4. Move to the next long row.\n"
 "PASS: the box moves with you; on a short row no box opens.\n"
 "5. Pick a long title, close the list, then hover the closed field.\n"
 "PASS: the full title shows steadily over the field.\n"
 "6. Open a run's history and repeat step 2 in both searchable filter pickers.\n"
 "PASS: same steady behaviour.\n"
 "7. Pick a work item, then click anywhere on the field again (not only the arrow).\n"
 "PASS: the list opens straight away, so you can change to another work item.\n"
 "FAIL: nothing happens until you click somewhere else first or on the arrow."),
}
