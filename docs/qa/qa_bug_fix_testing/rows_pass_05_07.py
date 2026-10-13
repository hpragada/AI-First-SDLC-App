# -*- coding: utf-8 -*-
"""Passes 5-7: integrations, repositories & multi-repo, work items."""

ROWS = {

37: ("DIRECT",
 "On the Integrations page each connector card's icon was invisible until you had connected that "
 "vendor - because the icon was derived from the vendor's name, and before you connect there is no "
 "vendor. So the cards you most needed to recognise were the blank ones.",
 "The card icon is now keyed to the CAPABILITY (document store, task tracker, design source and so "
 "on), so a distinct coloured icon is always visible. Once a real vendor is connected it still "
 "shows that vendor's initial and colour.",
 "1. Open Integrations on a project with NOTHING connected.\n"
 "2. Look at all six capability cards.\n"
 "PASS: every card shows a coloured icon. None is blank.\n"
 "3. Connect one capability, then come back.\n"
 "PASS: that card now shows the vendor's own initial and colour; the others still show their "
 "capability icons.\n"
 "FAIL: any card with no icon at all before a connection is made."),

38: ("DIRECT",
 "Two problems on the connect-a-capability form. Saving gave no confirmation at all - it just "
 "silently saved, leaving you unsure whether anything happened. And testing the connection failed "
 "with 'No connector registered for docstore:Confluence', because the form saved the vendor's "
 "display name where the platform expected its internal short name.",
 "The form now sends the correct identifier, taken from a list of vendors the platform genuinely "
 "supports, so that mismatch cannot happen. Save now shows an explicit success or error message, "
 "the grid shows 'Connected' once configured, and re-opening an already-connected capability "
 "pre-fills what you saved and updates it rather than creating a duplicate.",
 "1. Open Integrations, pick Document store, and enter credentials.\n"
 "2. Click Test connection.\n"
 "PASS: you get a clear result - 'Connection OK' or a readable failure. NOT 'No connector "
 "registered for ...'.\n"
 "3. Click Save.\n"
 "PASS: a visible confirmation appears, e.g. 'Confluence saved. Test the connection to verify it.'\n"
 "4. Go back to the Integrations grid.\n"
 "PASS: that card now shows 'Connected'.\n"
 "5. Open the same capability again.\n"
 "PASS: your saved vendor and settings are already filled in.\n"
 "6. Change one setting and Save.\n"
 "PASS: it updates - you do not end up with two connections for the same capability.\n"
 "FAIL: a silent save, a 'no connector registered' error, or a duplicate connection."),

39: ("DIRECT",
 "Every capability showed the SAME form - Confluence's fields (Space key, Base URL) and a "
 "Confluence-only vendor list - whether you were connecting a task tracker, a design source or a "
 "test-management tool. Each of those needs completely different credentials.",
 "The platform now serves a proper catalogue: each capability lists its own vendors, and each "
 "vendor its own fields. Task tracker shows Jira with Project key / Base URL / API token; Design "
 "source shows Figma with File key / Access token; Test management shows Xray with Client ID / "
 "Client secret; Code intelligence shows the built-in analyser with no credentials at all.",
 "Open Integrations and go into each of the six capabilities in turn. For each one:\n"
 "  a. Read the vendor dropdown.\n"
 "  b. Read the field labels.\n"
 "PASS: the vendors make sense for that capability (a task tracker must not offer Confluence), and "
 "the fields are the ones that vendor really needs.\n"
 "Specifically check:\n"
 "  Task tracker -> Jira -> Project key, Base URL, API token.\n"
 "  Design source -> Figma -> File key, Access token.\n"
 "  Test management -> Xray -> Client ID, Client secret.\n"
 "  Code intelligence -> built-in analyser -> NO credential fields.\n"
 "FAIL: the same Confluence form appears for more than one capability."),

48: ("DIRECT",
 "The Integrations cards used a fixed three-column grid, so on a narrower window the right-hand "
 "column was cut off, and on a very wide screen there was dead space.",
 "The cards now use a grid that wraps to fewer columns on narrow windows and fills wider ones.",
 "1. Open Integrations on a normal desktop window.\n"
 "2. Slowly narrow the browser window down to roughly half width, then to a phone-like width.\n"
 "PASS: the cards re-flow into fewer columns. No card is ever cut off at the right edge, and the "
 "page never scrolls sideways.\n"
 "3. Maximise the window on the widest screen you have.\n"
 "PASS: the cards spread out to use the space rather than huddling on the left.\n"
 "FAIL: a clipped card, or a horizontal scrollbar on the page."),

74: ("DURING A RUN",
 "The credentials a workspace entered when connecting Jira or Confluence were stored but never "
 "actually used. Every connector authenticated with a single account configured on the server, so "
 "a workspace that 'connected Jira' and passed the check was still using somebody else's account. "
 "Effectively single-tenant, and a credential-leak risk across workspaces. The connection also "
 "showed 'Healthy' without any real check.",
 "Figma, Xray and Atlassian (Confluence and Jira) now resolve credentials from the workspace's own "
 "stored connection, closing the same class of problem already fixed for GitHub. A per-field "
 "fallback to the server setting is kept so local development and automated tests are unchanged.",
 "SET UP: ideally two workspaces with DIFFERENT Atlassian accounts. If you only have one, do the "
 "single-workspace half.\n"
 "1. In workspace A, connect Confluence with account A's credentials. Test connection.\n"
 "PASS: it succeeds.\n"
 "2. Run a planning phase to completion and approve its gate so an artifact publishes to "
 "Confluence.\n"
 "PASS: the page appears in ACCOUNT A's Confluence space, and the link on the publish screen opens "
 "it.\n"
 "3. If you have a second workspace: connect Confluence there with account B, publish, and confirm "
 "the page lands in ACCOUNT B's space and NOT account A's.\n"
 "PASS: each workspace's content goes to its own account.\n"
 "4. Deliberately enter a WRONG token in a workspace and press Test connection.\n"
 "PASS: it fails with a readable message, rather than passing because the server's own account "
 "happens to work.\n"
 "FAIL: content lands in the wrong account, or a wrong token still reports healthy."),

103: ("DIRECT",
 "On a project with several repositories, the Code host connect form showed a single field labelled "
 "'Repository'. That reads as though you must pick one repo, and leaves you unsure whether the "
 "others are covered. In fact one connection covers every repository in the project, and each "
 "build targets its own.",
 "The field is now labelled 'Default repository', made OPTIONAL, and carries a hint: 'Each build "
 "targets its own repo; this is only a fallback default. The token must have access to ALL repos "
 "in this project.' Save no longer insists on it.",
 "SET UP: a project with two or more repositories registered.\n"
 "1. Open Integrations > Code host and read the repository field.\n"
 "PASS: it is labelled 'Default repository', not 'Repository'.\n"
 "PASS: a hint explains that each build targets its own repo and that the token must cover all of "
 "them.\n"
 "2. Leave that field EMPTY and click Save.\n"
 "PASS: the save is accepted - the field is optional.\n"
 "3. Go back to the Repositories page.\n"
 "PASS: all repositories show as connected, not just one.\n"
 "FAIL: the field is still called 'Repository', or Save refuses to proceed without it."),

113: ("DURING A RUN",
 "A follow-on from the credentials problem: after GitHub was fixed to use each workspace's own "
 "token, the remaining connectors - Atlassian Confluence and Jira, Figma and Xray - still "
 "authenticated from the server's own account. On a shared setup a publish to Confluence or Jira "
 "could use the wrong workspace's credentials, or simply fail.",
 "All of them now authenticate with the workspace's own stored credentials on any worker. Atlassian "
 "needed a new 'Atlassian account email' field on the Confluence and Jira connect form, because "
 "Atlassian signs in with email plus token; the site address is normalised to the bare site.",
 "1. Open Integrations > Document store > Confluence (and then Task tracker > Jira).\n"
 "PASS: there is now a field for the Atlassian ACCOUNT EMAIL, alongside the API token and site "
 "address.\n"
 "2. Fill in your own Atlassian email, token and site, and press Test connection.\n"
 "PASS: it succeeds.\n"
 "3. Deliberately put in the WRONG email with a correct token and test again.\n"
 "PASS: it fails with a readable message about the credentials being rejected.\n"
 "4. Put it right, then publish an artifact to Confluence and push a backlog to Jira.\n"
 "PASS: both land in YOUR Atlassian site, under your account.\n"
 "5. Try the site address with a trailing path or slash (e.g. https://yoursite.atlassian.net/wiki).\n"
 "PASS: it is accepted and still works - the address is tidied up for you.\n"
 "FAIL: no email field; or content lands somewhere other than your own site."),

156: ("DIRECT",
 "Two things the team asked for, plus a data-loss bug found while fixing them. (1) You could not "
 "edit a saved token - the field that would let you type a new one only appeared once a value was "
 "already in it, and the only thing that could put a value in it was that very field. A deadlock. "
 "(2) You were forced to SAVE credentials before you could test them, which is backwards. (3) "
 "Found while investigating: editing a configured connection WITHOUT retyping the token - say, "
 "changing only the project key - silently WIPED the stored credential.",
 "A Replace button beside the 'Configured' badge breaks the deadlock, with Cancel to keep what is "
 "stored. The data loss is fixed at both ends: the screen no longer sends an empty credential when "
 "you did not type one, and the server treats an empty one as 'no change' rather than 'erase'. "
 "Test connection now works BEFORE saving, against credentials that are never written to the "
 "database. And the test is now a REAL call - a cheap read-only 'who am I' against Jira, GitHub, "
 "Confluence or Figma - with vendor errors translated into plain messages. Xray keeps a "
 "wiring-only check and SAYS SO rather than implying it reached anything.",
 "1. Open Integrations and pick a capability you have NOT connected.\n"
 "2. Type credentials and press Test connection WITHOUT saving first.\n"
 "PASS: the test runs and gives a real result.\n"
 "3. Deliberately use a WRONG token and test.\n"
 "PASS: it FAILS, with a readable message such as 'credentials rejected'. (Note: this is a "
 "behaviour change - credentials that used to pass a shallow check will now correctly fail.)\n"
 "4. Fix the token, test, then Save.\n"
 "5. Re-open the capability. Look for the 'Configured' badge.\n"
 "PASS: there is a Replace button beside it.\n"
 "6. THE DATA-LOSS CHECK, the most important step here. Without touching the token, change only "
 "another field (e.g. the project key) and Save. Then re-open it.\n"
 "PASS: it still says Configured. Test connection still succeeds.\n"
 "FAIL: it now says not configured, or the connection stops working - that is the stored "
 "credential having been wiped.\n"
 "7. Click Replace, type a new token, then click Cancel.\n"
 "PASS: the old credential is kept and still works.\n"
 "8. Open Test management (Xray) and test.\n"
 "PASS: it says plainly that there is no live check for this vendor, rather than implying it "
 "reached Xray."),

90: ("DURING A RUN",
 "The umbrella item for multi-repository work. On a project with more than one repository, nothing "
 "could decide WHICH repository a task belongs in. The agent could not propose one, and a person "
 "could not set or change one - so a multi-repo project could not be built end to end at all.",
 "The agreed design, built and proven end to end: Task Breakdown suggests a repository for every "
 "work item with a reason and a confidence; the reviewer confirms or overrides at the Task "
 "Breakdown gate before the assignment is locked; implementation then opens each pull request in "
 "the assigned repository; and a person can redirect any task until its build starts. Single-repo "
 "projects skip the review entirely and all tasks go to the one repository.",
 "This is the end-to-end check for the whole multi-repo group (rows 91-102 and 106-109). Allow "
 "half a day.\n"
 "SET UP: a project with TWO repositories registered - say one frontend and one backend - each "
 "with its role set, and a Code host connection whose token covers both.\n"
 "1. Run the planning phases through to Task Breakdown.\n"
 "2. At the Task Breakdown gate, review the repo assignments (see S.No 97).\n"
 "PASS: every proposed task has a suggested repository, and the split looks sensible - backend "
 "work in the backend repo, frontend work in the frontend repo.\n"
 "3. Approve the gate.\n"
 "4. Trigger implementation on a BACKEND task.\n"
 "PASS: the pull request opens in the BACKEND repository on GitHub - not the other one.\n"
 "5. Repeat with a FRONTEND task.\n"
 "PASS: its pull request opens in the FRONTEND repository.\n"
 "6. Let one run through code review, the merge gate and the merge.\n"
 "PASS: it merges into the right repository and the work item reaches done.\n"
 "7. CONTROL CHECK: on a SINGLE-repo project, run Task Breakdown.\n"
 "PASS: no repo-assignment review appears, and everything builds into the one repository as before."),

91: ("DURING A RUN",
 "For a project-level planning run the platform never told the agent which repositories the project "
 "has. So the Task Breakdown agent had no list of frontend, backend and infrastructure repositories "
 "to sort work into - it literally could not see them.",
 "The project's repositories - name, role and which is the default - are now included in the "
 "context a project-level run receives, and mirrored on the companion side.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was in fact completed under "
 "S.No 90, whose note says all sub-tasks A1-E1 are complete and proven live. Test the behaviour.\n"
 "1. On a project with two or more repositories, run Task Breakdown.\n"
 "2. When the gate opens, look at the repo-assignment review.\n"
 "PASS: the repository dropdown offers EVERY repository on the project, by its real name, with its "
 "role shown.\n"
 "PASS: the agent's suggestions reference real repositories, not invented ones.\n"
 "FAIL: the dropdown is empty, lists only one repository, or shows names that do not match your "
 "Repositories page."),

92: ("DURING A RUN",
 "When the Task Breakdown agent proposed a work item it had no way to say which repository it "
 "belonged to, so every proposed item was created with no repository at all.",
 "The item-creation step now takes an optional repository, validated to one that really belongs to "
 "the same project. Left optional, so single-repo and repo-less projects are unchanged.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "1. On a multi-repo project, run Task Breakdown to completion.\n"
 "2. Before approving anything, open the Work Items board and look at the newly proposed items.\n"
 "PASS: they carry a repository - visible on the item or in the gate's review panel - rather than "
 "all showing blank.\n"
 "3. On a SINGLE-repo project, run Task Breakdown.\n"
 "PASS: it still works; items simply use the one repository.\n"
 "FAIL: every proposed item has no repository on a multi-repo project."),

93: ("DURING A RUN",
 "The briefing the agent receives described a single repository, which is right for a run aimed at "
 "one repo. On a project-level run for a multi-repo project it therefore said 'this project has "
 "many repositories' and then listed none of them.",
 "The briefing now renders a 'Repositories' section listing every repository with its role when a "
 "project-level run is multi-repo, and keeps the single-repository section for repo-scoped runs.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90. "
 "You cannot read the agent's briefing from the app, so judge it by the result.\n"
 "1. On a multi-repo project, run Task Breakdown.\n"
 "2. At the gate, read the agent's REASON on several items.\n"
 "PASS: the reasons name your real repositories by name and describe them correctly (e.g. 'this is "
 "an API endpoint, so the backend repo').\n"
 "FAIL: reasons that name no repository, invent one, or say the agent could not see the "
 "repositories."),

94: ("DURING A RUN",
 "The Task Breakdown agent had no instructions for sorting work by repository - no method for "
 "classifying an item, no requirement to give a reason, and no confidence rating.",
 "The agent was taught the assignment protocol: read the repositories from its context, classify "
 "each item (frontend / backend / infrastructure / shared) with a one-line reason and a confidence, "
 "and route everything to the single repository when the project has only one.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "1. On a multi-repo project, run Task Breakdown and open the gate's review panel.\n"
 "2. Read several items.\n"
 "PASS: each has a suggested repository, a ONE-LINE reason that makes sense, and a confidence.\n"
 "PASS: the reasons are specific to the item, not the same sentence repeated.\n"
 "3. Look at the overall split.\n"
 "PASS: it is sensible - database and API work in the backend repo, screens and components in the "
 "frontend repo.\n"
 "FAIL: no reasons, no confidence, or an obviously wrong split."),

95: ("DIRECT",
 "A decision about where to keep each item's assignment reason and confidence, so the review screen "
 "could show them. The recommendation was to keep them on the work item itself so they travel with "
 "it and survive being exported.",
 "Implemented as recommended - the reason and confidence live on the work item and reach the review "
 "screen.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "1. On a multi-repo project, reach the Task Breakdown gate.\n"
 "2. Confirm the reason and confidence are shown for each item (that is the visible half).\n"
 "3. Navigate AWAY from the gate and come back.\n"
 "PASS: the reasons and confidences are still there - they were stored, not held in the screen.\n"
 "4. Reload the browser entirely and return to the gate.\n"
 "PASS: still there.\n"
 "FAIL: the reasons vanish on reload."),

96: ("DIRECT",
 "There was no way to set or change a work item's repository through the app at all - the edit "
 "surface allowed only title, description and type. So neither the reviewer's override at the gate "
 "nor a later redirect could actually be saved.",
 "The repository can now be set on a work item, validated to one that belongs to the same project.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "1. On a multi-repo project, open a proposed task that has not started building.\n"
 "2. Change its repository using the selector.\n"
 "PASS: the change is accepted and a confirmation or the new value appears.\n"
 "3. Reload the page.\n"
 "PASS: the new repository is still set - it really saved.\n"
 "4. Trigger implementation on that task.\n"
 "PASS: the pull request opens in the repository you chose.\n"
 "FAIL: no way to change it, the change does not stick, or the build goes to the old repository."),

97: ("DIRECT",
 "There was no screen for reviewing where the agent proposed to put each task before approving the "
 "Task Breakdown gate.",
 "A repo-assignment review on the Task Breakdown gate: grouped by repository, showing the agent's "
 "suggestion, reason and confidence per item, with a dropdown to override, a running 'X of N "
 "confirmed' count, and the low-confidence items surfaced first.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90; "
 "the layout problems found afterwards are S.No 106.\n"
 "SET UP: a multi-repo project that has run Task Breakdown, with a gate pending.\n"
 "1. Open Gates and select the Task Breakdown gate.\n"
 "PASS: a repo-assignment review is shown.\n"
 "2. Check the layout.\n"
 "PASS: items are grouped by repository, with a summary of how many go to each.\n"
 "PASS: any LOW-CONFIDENCE items are at the TOP and expanded; confident groups are collapsed with "
 "a '+N more' you can click to open.\n"
 "3. Read one item's row.\n"
 "PASS: the title and the repository dropdown sit side by side and are readable - not one word per "
 "line.\n"
 "4. Override one item's repository using the dropdown.\n"
 "PASS: the change is marked visibly as an override, and the 'X of N confirmed' count moves.\n"
 "FAIL: no review at all, a cramped unreadable layout, or every item expanded with its full reason."),

98: ("DIRECT",
 "There was no control anywhere to redirect a task to a different repository once it had been "
 "assigned - the escape hatch the design promised.",
 "A repository selector on the work-item detail and the board, filled from the project's real "
 "repositories. Editable until the task's build starts, and read-only once its pull request is "
 "open.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "SET UP: a multi-repo project with assigned tasks.\n"
 "1. Open a task that has NOT started building.\n"
 "PASS: a repository selector is visible, showing the assigned repo and its role.\n"
 "2. Change it, reload, and confirm it stuck.\n"
 "3. Now trigger implementation on a task and wait until its pull request is open.\n"
 "4. Go back to that task and look at the selector.\n"
 "PASS: it is now disabled or read-only - you cannot move a task whose code is already being "
 "written.\n"
 "FAIL: no selector at all, or one that still lets you move a task mid-build."),

99: ("DIRECT",
 "A verification item: confirm the Add repository form really captures each repository's role "
 "(frontend, backend, infrastructure), because the automatic assignment depends on it.",
 "Verified working - no code change was needed. The form captures the role through a real "
 "selector, sends it, stores it, and shows it back as a chip.",
 "1. Open Repositories and click Add repository.\n"
 "PASS: there is a Role selector offering backend, frontend and infrastructure.\n"
 "2. Add a repository with role 'backend'.\n"
 "PASS: it appears in the list with a 'backend' chip.\n"
 "3. Reload the page.\n"
 "PASS: the chip is still there - the role was stored, not just displayed.\n"
 "4. Add a second repository with role 'frontend' and confirm the same.\n"
 "FAIL: no role selector, or the role is lost on reload."),

100: ("DIRECT",
 "Approving the Task Breakdown gate needed to be the moment the repository assignments are locked "
 "in - otherwise the review is advisory and the assignment could drift afterwards.",
 "Approving the gate now locks the assignments and the phase proceeds, so the assignment is "
 "committed exactly once, with a human sign-off.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "SET UP: a multi-repo project at the Task Breakdown gate.\n"
 "1. In the review, override at least one item's repository so you can recognise it later.\n"
 "2. Approve the gate.\n"
 "PASS: the approval is accepted and the phase moves on.\n"
 "3. Open the item you overrode.\n"
 "PASS: it holds the repository YOU chose, not the agent's original suggestion.\n"
 "4. Trigger implementation on it.\n"
 "PASS: the pull request opens in the repository you chose.\n"
 "FAIL: your override is lost on approval, or the build ignores it."),

101: ("DIRECT",
 "A policy question: should the gate BLOCK approval while low-confidence items are still "
 "unreviewed, or only warn? Recommendation was to warn and require an explicit 'confirm all', "
 "rather than hard-block, so a large backlog cannot dead-end.",
 "Decided and implemented as recommended - warn rather than hard-block.",
 "NOTE: this row's own fix note in Bugs.xlsx still reads 'Open'. It was completed under S.No 90.\n"
 "SET UP: a Task Breakdown gate whose review contains at least one LOW-CONFIDENCE item.\n"
 "1. Without confirming the low-confidence items, look at the Approve button.\n"
 "PASS: you are WARNED that some items still need review - the count or a message says so.\n"
 "PASS: you are not permanently blocked; there is a way to confirm them and proceed.\n"
 "2. Confirm the flagged items and approve.\n"
 "PASS: it goes through.\n"
 "FAIL: approval is hard-blocked with no way forward on a large backlog - that would be the "
 "behaviour the team explicitly chose against."),

102: ("DEV CHECK",
 "A one-off tool built for a specific multi-repo test: copy the earlier phases' artifacts and their "
 "stored files from one workspace into a new one, so a later phase could be run there natively "
 "without redoing everything. It reads the old workspace and writes only the new one.",
 "Built as a command-line tool for the team, with a dry-run mode and tests. It is not part of the "
 "product.",
 "NOT REACHABLE FROM THE APP - there is no screen for this and there should not be. It is a "
 "developer command that was used once to set up a test workspace.\n"
 "There is nothing here for a manual tester to do. Mark it 'Not applicable - developer tooling' "
 "unless the team specifically asks for it to be re-run, in which case a developer should run it "
 "with --dry-run first and confirm the old workspace is untouched afterwards.\n"
 "It is listed here only so the sheet accounts for every row rather than quietly skipping one."),

106: ("DIRECT",
 "The repo-assignment review was wired into the NARROW right-hand gate panel, so task titles, "
 "reasons and dropdowns wrapped to one word per line and overlapped each other. It also listed "
 "every one of 32 tasks with its full reasoning instead of surfacing the few that needed attention.",
 "The review now renders FULL WIDTH rather than in the narrow column; it shows a summary of the "
 "split, collapses the confident groups (click to expand), keeps the low-confidence items expanded "
 "at the top, and tightens each row so the title and repository dropdown sit side by side.",
 "SET UP: a multi-repo project with a Task Breakdown gate carrying MANY tasks - twenty or more is "
 "where the old layout broke.\n"
 "1. Open Gates and select the Task Breakdown gate.\n"
 "PASS: the review uses the FULL WIDTH of the page, not the narrow right-hand column.\n"
 "2. Read the task rows.\n"
 "PASS: titles read normally. No column so narrow that words wrap one per line, and nothing "
 "overlapping the dropdown.\n"
 "3. Look at the shape of the list.\n"
 "PASS: a summary line gives the split (e.g. '17 backend / 15 frontend'); low-confidence items are "
 "at the top and open; the confident groups are COLLAPSED with a '+N more'.\n"
 "4. Click a collapsed group.\n"
 "PASS: it expands.\n"
 "5. Narrow the browser window and check it again.\n"
 "PASS: still readable, no sideways scrolling.\n"
 "FAIL: a cramped column, overlapping controls, or all 30-odd tasks expanded with full reasoning."),

107: ("DURING A RUN",
 "The companion on your machine held ONE repository folder for its whole life and built every task "
 "from it, ignoring which repository the task actually belonged to. On a two-repository project it "
 "would either fail outright, or - worse - silently push code to the WRONG repository if a branch "
 "of the same name happened to exist there.",
 "The companion now takes a repository-to-folder mapping and picks the right folder for each task. "
 "If a task names a repository it has not been given a folder for, it FAILS LOUDLY and reports that "
 "build failed, rather than falling back to the wrong folder - and it keeps serving. As a second "
 "guard it refuses to push if the folder's remote does not match the repository the work was routed "
 "to.",
 "SET UP: a multi-repo project, and a companion started with a mapping for BOTH repositories - "
 "'serve --repo owner/name=/path' once per repository. (The single-repo shorthand still works and "
 "must keep working.)\n"
 "1. Trigger implementation on a task assigned to repository A.\n"
 "PASS: the code is committed and pushed to repository A on GitHub, and the pull request opens "
 "there.\n"
 "2. Trigger implementation on a task assigned to repository B.\n"
 "PASS: it lands in repository B.\n"
 "3. THE IMPORTANT NEGATIVE TEST: restart the companion with a mapping for ONLY repository A, then "
 "trigger a task assigned to repository B.\n"
 "PASS: that build FAILS with a clear message about the repository not being mapped, AND the "
 "companion KEEPS RUNNING and can still serve repository A.\n"
 "FAIL: code lands in the wrong repository - that is the serious one - or the companion exits."),

108: ("DIRECT",
 "On a multi-repository project, a work item with no repository assigned silently built into "
 "whichever repository happened to be the default - so backend code could open a pull request in "
 "the frontend repository. Because it was a mis-route rather than a failure, it would pass "
 "unnoticed.",
 "The trigger now counts the project's repositories. On a multi-repo project an unassigned work "
 "item raises a clear error telling you to assign its repository - it never silently defaults. "
 "Single-repo projects keep the default fallback unchanged.",
 "SET UP: a project with TWO or more repositories.\n"
 "1. Create a work item and deliberately leave its repository unset.\n"
 "2. Try to trigger implementation on it.\n"
 "PASS: it is REFUSED, with a message telling you to assign the repository - confirm it at the "
 "Task Breakdown gate, or set it on the work item.\n"
 "3. Assign a repository and trigger again.\n"
 "PASS: it builds, into that repository.\n"
 "4. CONTROL CHECK: on a SINGLE-repo project, create a work item without setting a repository and "
 "trigger implementation.\n"
 "PASS: it builds normally into the one repository. This fallback is correct and must not have "
 "been broken.\n"
 "FAIL: a multi-repo unassigned item builds anyway - especially into the wrong repository."),

109: ("DIRECT",
 "The repo-assignment review panel appeared on gates it has nothing to do with - the merge gate, "
 "and any later phase gate. Tasks keep their planner's repository suggestion long after Task "
 "Breakdown, so the panel kept reappearing and asking a reviewer to confirm assignments in the "
 "middle of approving something else entirely.",
 "The panel is now shown ONLY on the Task Breakdown gate. It is keyed on which phase opened the "
 "gate, not on the gate's type - because every planning gate shares one type, so the type alone "
 "would not have been safe.",
 "SET UP: a multi-repo project with tasks still in 'proposed' state and at least one NON-Task-"
 "Breakdown gate pending - a merge gate is ideal, or any later phase gate.\n"
 "1. Open Gates and select the MERGE gate.\n"
 "PASS: NO repo-assignment review panel. You see the normal merge decision panel only.\n"
 "2. Select a later PHASE gate (testing, security, deployment) if you have one.\n"
 "PASS: no repo-assignment panel there either.\n"
 "3. Select the TASK BREAKDOWN gate.\n"
 "PASS: the panel IS there - that is the one place it belongs.\n"
 "FAIL: the panel appears on any gate other than Task Breakdown."),

170: ("DIRECT",
 "On the Repositories page the optional Preview URL box did not line up with the other boxes in "
 "its row, because it alone carried a help line underneath that changed its height. The help line "
 "also said '09b', an internal phase code that means nothing to a user.",
 "The inline help was removed so all four inputs line up again, and the guidance moved to a single "
 "full-width line below the row, reworded with no code: 'Preview URL is optional - if your app is "
 "already running somewhere, paste its address so the testing phase can open it and write tests "
 "against the live app.'",
 "1. Open Repositories and look at the Add repository row.\n"
 "PASS: all four input boxes sit on the same line, bottom-aligned. The Preview URL box is not "
 "pushed out of line.\n"
 "2. Read any guidance text below the row.\n"
 "PASS: it explains the Preview URL in plain words and contains NO '09b' or other internal code.\n"
 "3. Narrow the window and check the alignment again.\n"
 "FAIL: the Preview URL box sits higher or lower than the others, or '09b' appears anywhere on "
 "screen."),

16: ("DIRECT",
 "Clicking 'Create work item' opened a form that looked broken: a grey block wedged into the page "
 "with the form squashed to the right, and the X and clicking outside did nothing. The same "
 "problem hit the Invite drawer and every Integrations connect form.",
 "The shared drawer and pop-up building blocks were rebuilt as real overlays - a proper dimmed "
 "backdrop over the whole page with the panel floating above it - and the X, a click on the dimmed "
 "area, and the Esc key all close it. Fixed once at the shared level, so all three screens were "
 "corrected together. The Integrations connect screen, which is a full page rather than a "
 "pop-over, now shows a clean centred card.",
 "Check all three places:\n"
 "1. Work Items > Create work item.\n"
 "2. Users & Invitations > Invite.\n"
 "3. Integrations > any capability > Connect.\n"
 "For each of 1 and 2:\n"
 "PASS: the rest of the page dims behind the panel, and the panel floats cleanly above it - no "
 "grey block wedged into the layout, nothing squashed to the right.\n"
 "PASS: the X closes it.\n"
 "PASS: clicking the dimmed area closes it.\n"
 "PASS: pressing Esc closes it.\n"
 "For 3: PASS: a clean centred card, not a grey right-floated block.\n"
 "FAIL: any of the three close actions does nothing, or the layout is wedged."),

17: ("DIRECT",
 "The Create work item form marked Title as optional, when it should be required. Separately, the "
 "Type field gave no explanation of what Epic, Story, Task and Defect actually mean.",
 "Title is now required - marked with an asterisk, and the Create button stays disabled until a "
 "title is entered. The Type field gained an explanation of each type.",
 "1. Open Create work item.\n"
 "PASS: the Title field is marked as required (an asterisk, or the word 'required').\n"
 "2. Fill in everything EXCEPT the title and look at the Create button.\n"
 "PASS: it is disabled.\n"
 "3. Type a title.\n"
 "PASS: the button becomes clickable.\n"
 "4. Look at the Type field for a hint or tooltip.\n"
 "PASS: an explanation of Epic / Story / Task / Defect is available, in plain words.\n"
 "FAIL: Title says 'optional', or a work item can be created with no title."),

21: ("DURING A RUN",
 "Five problems on the work item lifecycle screen, reported together. (i) The phase rail listed "
 "phases that do not belong on a normal work item - context bridge, context extraction, onboarding "
 "- and showed names with underscores. (ii) A Story still showed as 'Epic' because the word was "
 "typed into the screen. (iii) The Type field had no explanation. (iv) The run console showed "
 "nothing at all while a phase ran. (v) A failed phase gave no reason, and re-running it threw an "
 "error.",
 "Phase names are readable everywhere and the brownfield/onboarding phases are hidden from a work "
 "item's rail (a display filter only - the orchestration is unchanged, as agreed with the team). "
 "The type badge and headings show the item's real type. Run events now carry a colour and a "
 "readable message so the console shows progress. Re-run now sends the phase name rather than an "
 "internal id, and a failed run shows the actual reason.",
 "1. Create a work item of type STORY and open it.\n"
 "PASS: the heading and badge say Story, not Epic.\n"
 "2. Look at the lifecycle rail.\n"
 "PASS: no 'context bridge', 'context extraction' or 'onboarding' entries; every phase name is "
 "readable with no underscores or number prefixes.\n"
 "3. Trigger a phase and open the run console straight away.\n"
 "PASS: lines appear as the run progresses - e.g. 'Phase dispatched - Ideation'. The console is "
 "NOT blank.\n"
 "4. Click 'View full console'.\n"
 "PASS: same content, still not blank.\n"
 "5. If you can get a run to fail (stop your companion mid-run), read the failure.\n"
 "PASS: a real reason is shown, not a bare 'failed'.\n"
 "6. Click Retry on that failed run.\n"
 "PASS: it starts a new run cleanly - no error about an unregistered key.\n"
 "FAIL: a blank console, a Story labelled Epic, or a retry that errors."),

26: ("DIRECT",
 "Two problems on the Work Items board. It only ever showed FOUR phase columns - Ideation, "
 "Requirements, Architecture, UX Design - in the wrong order, with PRD missing, because the "
 "columns were a fixed list rather than the real lifecycle. And when a card was waiting for a gate "
 "or a clarification, the long status label overflowed and broke the card layout, with gate labels "
 "showing raw names like '04_architecture gate'.",
 "The board now builds its columns from the real phase list, so every phase from Ideation through "
 "Deployment appears in correct order and each column title is readable. Card headers wrap so a "
 "long label no longer breaks the layout, and gate labels are readable - 'Architecture gate'.",
 "1. Open the Work Items board.\n"
 "2. Read the column headers left to right.\n"
 "PASS: every lifecycle phase is there, in sensible SDLC order, including PRD. The board scrolls "
 "sideways to reach them all.\n"
 "PASS: every column title is readable - no underscores, no '04_' prefixes.\n"
 "3. Get a card into a waiting-for-gate state and look at it.\n"
 "PASS: the card layout holds together - the status label wraps rather than breaking the card.\n"
 "PASS: the gate label reads like 'Architecture gate', not '04_architecture gate'.\n"
 "FAIL: only four columns, PRD missing, a broken card, or a raw phase name."),

36: ("DIRECT",
 "The helper text under the Type dropdown on the Create work item form described the types in "
 "internal jargon - 'plan tier', 'build tier', 'remediation tier' - which means nothing to a user.",
 "Rewritten in plain language: Epic is a large feature that goes through all the planning phases "
 "from Ideation to Task Breakdown; Story is a smaller user-facing piece of an epic; Task is a "
 "concrete development job that gets implemented, code-reviewed and tested; Defect is a bug fix on "
 "the shorter fix-and-verify flow.",
 "1. Open Create work item and read the helper text under the Type dropdown.\n"
 "PASS: it explains all four types in ordinary words.\n"
 "PASS: the words 'plan tier', 'build tier' and 'remediation tier' do NOT appear.\n"
 "2. Ask yourself, as someone who has not built this app: could you now pick the right type?\n"
 "FAIL: any internal jargon, or an explanation that assumes you know how the platform works."),

40: ("DIRECT",
 "In the Work Items LIST, the type was printed exactly as stored - lower case 'story', 'epic'. "
 "Only the board cards capitalised it.",
 "One shared helper now formats the type, so the board and the list both show 'Story', 'Epic' and "
 "so on.",
 "1. Create work items of several types.\n"
 "2. Open the Work Items LIST view and read the Level / Type column.\n"
 "PASS: 'Story', 'Epic', 'Task', 'Defect' - properly capitalised.\n"
 "3. Switch to the BOARD view and read the same items.\n"
 "PASS: identical wording in both views.\n"
 "FAIL: lower-case raw values in the list, or the two views disagreeing."),

41: ("DIRECT",
 "Work items were shown everywhere by their long internal database id - a string like "
 "'1ba2b356-...' - with no friendly reference. The list, the board cards, the detail heading, the "
 "breadcrumb, the gate rows and the phase picker all showed it.",
 "Each work item now has a short per-project reference that displays as 'WI-42', including for "
 "items that already existed. Every screen shows that reference instead of the long id.",
 "1. Open the Work Items list.\n"
 "PASS: each row shows a short key like WI-1, WI-2 - not a long string of letters, numbers and "
 "dashes.\n"
 "2. Check the board cards, a work item's detail heading, and its breadcrumb.\n"
 "PASS: the same short key in all of them.\n"
 "3. Open Gates and look at the work item column.\n"
 "PASS: short key.\n"
 "4. Open Phases & Runs and open the work-item picker.\n"
 "PASS: short key.\n"
 "5. Check an OLD work item created before this fix.\n"
 "PASS: it has a key too - existing items were filled in.\n"
 "FAIL: a long internal id showing anywhere a person reads."),

42: ("DIRECT",
 "A work item with no title showed a blank cell in the list, or fell back to its long internal id "
 "in the detail heading - because the code treated an empty title as a real value.",
 "The fallback is now title, then the short key, then the id - so an untitled item shows its "
 "WI-key instead of a blank cell or a long id.",
 "NOTE: the Create form now requires a title (S.No 17), so you may need an item created before "
 "that, or one imported with an empty title.\n"
 "1. Find or create a work item with an empty title.\n"
 "2. Look at it in the list.\n"
 "PASS: the title cell shows its short key (e.g. WI-7), not a blank.\n"
 "3. Open its detail page.\n"
 "PASS: the heading shows the short key, not a long internal id.\n"
 "FAIL: a blank cell or a long id."),

43: ("DIRECT",
 "On the work-item lifecycle rail the phase names showed as 'Prd' and 'Ux Design' - the acronyms "
 "mangled by naive capitalisation - while the board showed them correctly. The two disagreed.",
 "The label helper now matches the shorter name too, so the rail shows 'PRD' and 'UX Design', "
 "matching the board.",
 "1. Open any work item's detail page and read the lifecycle rail.\n"
 "PASS: 'PRD' in capitals, and 'UX Design' with a capital UX.\n"
 "2. Open the Work Items board and read the same phase columns.\n"
 "PASS: identical spelling in both places.\n"
 "FAIL: 'Prd', 'Ux Design', or the rail and board disagreeing."),

49: ("DIRECT",
 "On the Work Items board the search box and the Phase, Role and Status dropdowns did nothing at "
 "all - only the Epics/Tasks/Defects chips filtered. The dropdowns also had no options to choose "
 "from.",
 "All four controls now work. Search matches the key, title, type and feature stream; the Phase and "
 "Status options are the values actually present on the board; and Role filters by the role "
 "responsible for the item's current phase.",
 "SET UP: a project with a good spread of work items - several types, several phases.\n"
 "1. Open the Work Items board and type part of a work item's title into the search box.\n"
 "PASS: the board narrows to matching cards as you type.\n"
 "2. Search for its short key instead (e.g. WI-3).\n"
 "PASS: it matches.\n"
 "3. Type something that matches nothing.\n"
 "PASS: the board empties, with a clear message rather than looking broken.\n"
 "4. Clear the search and open the Phase dropdown.\n"
 "PASS: it lists real phases that exist on this board - not an empty list.\n"
 "5. Pick one.\n"
 "PASS: only items in that phase remain.\n"
 "6. Repeat for Status and Role.\n"
 "7. Combine a search with a dropdown.\n"
 "PASS: both apply together.\n"
 "FAIL: an inert control, or an empty dropdown."),

50: ("DIRECT",
 "The 'Phase' column on the Work Items list did not show the phase at all - it showed the feature "
 "stream, because the platform never told the screen what phase an item was actually in. Board "
 "cards were placed by the same wrong value.",
 "The platform now works out each item's real current phase and sends it with the card, so the list "
 "shows the true phase (or 'Not started') and board cards land in their actual phase column. The "
 "feature stream is no longer used as a phase anywhere.",
 "SET UP: at least one work item that has RUN a phase (say PRD), and one that has never run "
 "anything.\n"
 "1. Open the Work Items LIST and read the Phase column.\n"
 "PASS: the item that ran PRD shows 'PRD'.\n"
 "PASS: the item that has never run anything shows 'Not started' - not a feature name.\n"
 "2. Switch to the BOARD.\n"
 "PASS: the PRD item sits in the PRD column.\n"
 "3. Compare the Phase column against the item's feature stream if it has one.\n"
 "PASS: they are DIFFERENT things and the Phase column shows the phase.\n"
 "FAIL: the Phase column repeats the feature stream, or a card sits in the wrong column."),

54: ("DIRECT",
 "When a phase was waiting for gate approval, the work item card read 'Phase Gate gate' - the word "
 "'gate' twice - because the platform built the label as '<type> gate' and the type is already "
 "'phase gate'.",
 "The platform now builds a clean readable gate label with the duplicate word and the underscore "
 "removed, so every card reads 'Phase gate'. Fixed for all phases, not just the one reported.",
 "1. Trigger a phase and let it reach its gate.\n"
 "2. Open the Work Items board and read the card.\n"
 "PASS: it reads 'Phase gate' - the word 'gate' appears once.\n"
 "3. Do the same for a DIFFERENT phase, and for a merge gate if you can reach one.\n"
 "PASS: all of them read cleanly.\n"
 "4. Check the Dashboard's 'Needs me' section too.\n"
 "PASS: same clean wording.\n"
 "FAIL: 'Phase Gate gate', 'phase_gate gate', or any doubled word."),

57: ("DIRECT",
 "On the work-item detail page two raw values leaked: the approve-gate box read 'phase_gate gate', "
 "and the latest run's status showed as 'awaiting_gate' with an underscore.",
 "Both now go through shared helpers - no duplicate 'gate', no underscores - and the fix was "
 "applied across the Epic, Task and Defect pages, the Task Breakdown screen and the phase console "
 "badge, so it holds for every phase, gate and status.",
 "1. Trigger a phase on a work item and let it reach its gate.\n"
 "2. Open that work item's detail page.\n"
 "3. Read the approve-gate box on the right.\n"
 "PASS: it reads 'Phase gate'.\n"
 "4. Read the latest run's Status.\n"
 "PASS: it reads 'Awaiting gate' - no underscore.\n"
 "5. Repeat on an Epic, a Task and a Defect if you have all three.\n"
 "PASS: consistent everywhere.\n"
 "FAIL: any underscore or doubled 'gate' on any of those pages."),

77: ("DIRECT",
 "Re-running Task Breakdown created a SECOND complete copy of the backlog - duplicate epics, "
 "stories and tasks, with duplicate numbers. Recovering meant deleting the partial batch by hand "
 "first.",
 "Three parts. Re-running Task Breakdown now REPLACES the matching proposed work items rather than "
 "duplicating them, and never touches items that have already been accepted, started or finished. "
 "A second trigger while a run is live is refused with a clear message. And both trigger points now "
 "show a confirmation dialog first: if the phase already completed it warns that re-running "
 "replaces this phase's artifacts with no duplicates; if a run is in progress it blocks with an "
 "explanation.",
 "SET UP: a project where Task Breakdown has already run and produced a backlog. Note how many "
 "work items exist.\n"
 "1. Trigger Task Breakdown again on the same work item.\n"
 "PASS: a confirmation dialog appears first, explaining that re-running replaces this phase's "
 "output and will not create duplicates.\n"
 "2. Confirm and let it finish.\n"
 "3. Count the work items again.\n"
 "PASS: roughly the same number as before - NOT double.\n"
 "4. Before re-running, move one item to 'in progress' or 'done'. Re-run again.\n"
 "PASS: that item is untouched - only proposed items were replaced.\n"
 "5. While a run is live, try to trigger the same phase again.\n"
 "PASS: it is BLOCKED, with a clear message saying a run is already in progress.\n"
 "FAIL: the backlog doubles, an in-progress item is reset, or a second run starts on top of a live "
 "one."),

118: ("DURING A RUN",
 "The epics, stories and tasks the Task Breakdown agent writes were too technical and pitched too "
 "high - a normal user could not understand them, and even a developer got only a summary. The "
 "descriptions and acceptance criteria need to be detailed enough that a developer could implement "
 "the task by reading them alone.",
 "The agent now has a writing standard: every description and acceptance criterion must lead with "
 "one plain-language sentence saying what it delivers and why, BEFORE the technical detail, and be "
 "self-contained enough to implement from - behaviour, inputs and outputs, states, edge cases - "
 "with concrete acceptance criteria and no leftover template placeholders. The worked examples in "
 "the agent's instructions were rewritten too, because the model copies examples more than rules: "
 "the first attempt set the rule and left the old technical examples in place, and tasks still came "
 "out too technical.",
 "1. Run Task Breakdown on a work item and let it complete.\n"
 "2. Open several generated TASKS and read their descriptions.\n"
 "PASS: each OPENS with a plain-language sentence saying what it delivers and why, before any "
 "technical detail.\n"
 "PASS: reading only that description, you could brief a developer without going back to anyone.\n"
 "3. Read the acceptance criteria.\n"
 "PASS: concrete and checkable by hand - not vague, and not template text like '<describe here>'.\n"
 "4. Do the same for STORIES and EPICS.\n"
 "PASS: all three levels read this way, not just epics.\n"
 "5. Compare against an older backlog if the project has one.\n"
 "PASS: noticeably more readable.\n"
 "FAIL: a task that opens with jargon; bare placeholders; or criteria you could not verify by "
 "hand."),

140: ("DIRECT",
 "There was no way to say 'this is not going to happen'. A duplicate, a defect nobody will fix, a "
 "task overtaken by a later decision - the only options were to mark it done, or leave it open for "
 "ever. Marking it done puts a lie into every report that counts finished work; leaving it open for "
 "ever is how a board stops being read.",
 "Work items gained a second final state, 'cancelled', which only a person can set. A tech lead or "
 "admin can cancel from the task page, the defect page, the run console beside Retry, and a row "
 "menu on the list. The dialog ASKS WHY, from a short list of standing reasons rather than an empty "
 "box a busy person leaves blank. Cancelled items come off the board by default, but the board SAYS "
 "how many it is hiding and one click brings them back. TEAM DECISION: cancelling a defect releases "
 "the gate it was blocking - and every gate still waiting on that story gains a checklist line "
 "naming the defect, who cancelled it and why, which the reviewer must tick before approving.",
 "SET UP: sign in as a tech lead or admin. Note: CANCELLING CANNOT BE UNDONE - use a throwaway "
 "item.\n"
 "1. Open a task and find the Cancel action.\n"
 "PASS: it is offered on the task page. Check the defect page ('Won't fix...'), the run console "
 "beside Retry, and the row menu on the Work Items list too - all four.\n"
 "2. Click Cancel.\n"
 "PASS: a dialog asks WHY, offering a short list of reasons rather than an empty box.\n"
 "3. Confirm.\n"
 "PASS: the item leaves the board, AND the board says how many items it is hiding.\n"
 "4. Click that to show them.\n"
 "PASS: the cancelled item reappears, clearly marked as cancelled.\n"
 "5. Check the Dashboard count.\n"
 "PASS: it excludes the cancelled item - the number and the board agree.\n"
 "6. THE GATE HALF: cancel a DEFECT that is blocking a story's gate.\n"
 "PASS: the dialog WARNS you about this BEFORE you decide, not after.\n"
 "7. Open that gate.\n"
 "PASS: it now carries a checklist line naming the cancelled defect, who cancelled it and why, and "
 "you CANNOT approve until you tick it.\n"
 "8. Sign in as a plain member and look for the Cancel action.\n"
 "PASS: not offered - it is tech lead or admin only.\n"
 "FAIL: no way to cancel, no reason asked, silent hiding, or a gate released with no disclosure."),

147: ("DURING A RUN",
 "When the review agent finds blocking problems it opens remediation work items to fix them. Those "
 "items were arriving on the board too technical and too thin. Worse, the platform was creating "
 "them with the finding's title and NO description at all - the reviewer's actual words about what "
 "was wrong and what to do were being thrown away before they reached the board.",
 "Both sides fixed, and the platform was the hard blocker. The finding now carries the problem, the "
 "fix and the category all the way through, and the work item gets a real readable brief: a "
 "plain-language severity lead, 'What's wrong', 'What to do', and a 'Where' line keeping the "
 "technical detail (file and line, review dimension, severity). A finding that genuinely has only a "
 "title now SAYS SO honestly instead of implying a fuller brief. The implementation agent gets the "
 "same detail. On the agent side, the review agent was given a writing standard and its example "
 "output was rewritten, because the model copies the example.",
 "SET UP: you need a build that produces BLOCKING code-review findings. Allow time - this is deep "
 "in the build flow.\n"
 "1. Trigger implementation on a task and let the code review run.\n"
 "2. When remediation items appear on the Work Items board, open one.\n"
 "PASS: it has a real DESCRIPTION, not just a title.\n"
 "3. Read that description.\n"
 "PASS: it leads with the severity in plain words, then says clearly WHAT IS WRONG and WHAT TO DO, "
 "and ends with WHERE - file and line.\n"
 "PASS: you could hand it to a developer as-is.\n"
 "4. Read the title.\n"
 "PASS: it reads like a board item's title, not a terse fragment such as 'unbounded result set'.\n"
 "FAIL: a remediation item with an empty description, or one you cannot act on without asking "
 "somebody."),

167: ("DIRECT",
 "The descriptions the Task Breakdown agent writes for epics, stories and tasks were shown as plain "
 "text, so formatting appeared as literal characters - asterisks around bold text, backticks "
 "around code, pipe characters where a table should be. The content was good; it was unreadable.",
 "Work-item descriptions now go through the same renderer already used for artifact previews, so "
 "bold, code, lists and tables display properly. The 'No description yet.' message is kept for "
 "items with none.",
 "SET UP: a work item whose description came from Task Breakdown - those contain formatting.\n"
 "1. Open a generated TASK and read the description.\n"
 "PASS: bold text is actually bold; code appears in a code style; bullet lists are real bullets; "
 "tables are laid out as tables.\n"
 "PASS: you can see NO stray ** characters, no backticks, and no rows of | pipes.\n"
 "2. Open a generated STORY or EPIC and check the same.\n"
 "3. Open a work item with NO description.\n"
 "PASS: it says 'No description yet.' rather than showing nothing or an error.\n"
 "4. Check the description sits neatly inside its panel.\n"
 "PASS: no card-inside-a-card, no overflowing.\n"
 "FAIL: raw markdown characters visible anywhere."),

168: ("DURING A RUN",
 "A work item could show as DONE while its run was still awaiting the merge gate or still in "
 "review. The AI agent that writes the code was marking its own task finished when it judged it "
 "complete - before code review and before the merge gate. Whether work is done is a decision for a "
 "person at a gate, not for the thing doing the work. A second path did the same: a merged pull "
 "request set the item done even while its merge gate was still pending.",
 "The agent's instructions no longer tell it to mark the item done - it only logs completion, and "
 "the platform marks the item done after the merge gate. The channel the agent uses now REFUSES a "
 "'done' transition outright. The merged-pull-request path defers while a merge gate is still "
 "pending, and when it does legitimately finish an out-of-band merge it records it properly.",
 "1. Trigger implementation on a task.\n"
 "2. Watch the work item's state THROUGHOUT - during coding, during code review, and while the "
 "merge gate is pending.\n"
 "PASS: it stays 'in progress' or 'in review'. It must NEVER read 'done' before you approve the "
 "merge gate.\n"
 "3. Approve the merge gate and let the merge complete.\n"
 "PASS: NOW it reads done.\n"
 "4. Check the item's history or event list.\n"
 "PASS: there is a proper transition record for it reaching done.\n"
 "5. SEPARATE CHECK: with a merge gate still pending, merge the pull request by hand on GitHub.\n"
 "PASS: the item does NOT jump to done on its own - the gate still wants a person (see S.No 88).\n"
 "FAIL: 'done' appears before you approved anything. That is the serious one."),

202: ("DIRECT",
 "The 'Test cases' screen - the per-story list of test cases with their automation status and a "
 "Generate script action - had no link anywhere in the app. It could only be reached by typing its "
 "address.",
 "A 'Test cases' button was added to the work-item detail header. (The fuller tabbed story and epic "
 "layout it was originally meant to live in remains a separate, deferred piece of work.)",
 "1. Open a Story or Epic work item.\n"
 "2. Look at the header area for a 'Test cases' button.\n"
 "PASS: it is there.\n"
 "3. Click it.\n"
 "PASS: the Test cases screen opens for that work item, listing its test cases with their "
 "automation status.\n"
 "4. Use the browser Back button.\n"
 "PASS: you return to the work item.\n"
 "FAIL: no button, or one that goes to the wrong place.\n"
 "KNOWN: a newly created test case may not appear until you reload the page - that is a separate "
 "OPEN row (S.No 215), not a failure of this one."),

}
