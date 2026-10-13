# -*- coding: utf-8 -*-
"""Passes 1-4: shell, project setup, connect machine, people & permissions."""

ROWS = {

1: ("DIRECT",
 "The login page greeted everyone as though they worked at a company called Acme Corp - a demo "
 "name left in the code. There is no real company to name before anyone has even signed in.",
 "The greeting is now a plain 'Welcome back.' with no company name in it.",
 "1. Sign out completely, or open the app in a private window.\n"
 "2. Land on the login page.\n"
 "3. Read the greeting above the form.\n"
 "PASS: it reads 'Welcome back.' and nothing else.\n"
 "FAIL: any company name appears - especially 'Acme Corp'."),

2: ("DIRECT",
 "The email box on the login page arrived pre-filled with a sample address, sarah@acme.com. A "
 "returning user had to delete somebody else's email before typing their own.",
 "The email box now starts empty and shows a grey example hint, 'you@company.com', matching the "
 "signup form.",
 "1. Sign out, or open the app in a private window.\n"
 "2. Land on the login page and look at the email box WITHOUT clicking it.\n"
 "PASS: the box is empty; the words 'you@company.com' are grey placeholder text that disappears "
 "as soon as you type.\n"
 "FAIL: the box contains a real-looking address you have to clear first.\n"
 "TIP: if your browser has saved your own email, that is browser autofill, not this bug - check "
 "in a private window."),

4: ("DIRECT",
 "The signup form arrived pre-loaded with someone else's details - Sarah Chen, sarah@acme.com, "
 "Acme Corp. A new user had to delete every one of them before typing their own.",
 "All four fields (name, work email, password, workspace name) now start empty, with grey example "
 "hints instead of real-looking values.",
 "1. Open the app in a private window and go to the signup page.\n"
 "2. Look at all four fields before touching anything.\n"
 "PASS: every field is empty. Any text you see is grey and vanishes when you start typing.\n"
 "FAIL: any field holds a value you must delete - names, emails or a workspace name."),

5: ("DIRECT",
 "For a brand-new user with no project yet, the project menu in the top bar still showed a made-up "
 "project called 'Payment Gateway v2'.",
 "The project menu now reads 'No project yet' until the user actually creates a project.",
 "1. Sign up a completely new workspace and log in.\n"
 "2. Do NOT create a project.\n"
 "3. Look at the project menu in the top bar.\n"
 "PASS: it reads 'No project yet'.\n"
 "FAIL: it names any project, especially 'Payment Gateway v2'.\n"
 "NOTE: this needs a genuinely new workspace. On an existing account you will correctly see your "
 "own projects."),

6: ("DIRECT",
 "On first login the Get Started checklist showed a green tick against 'Create your first project' "
 "before any project existed - telling the user they had done something they had not.",
 "Step 1 now shows as the active, not-yet-done step (numbered 1) with a 'Create a project' action, "
 "until a project is actually created.",
 "1. Sign up a new workspace and log in.\n"
 "2. Look at the Get Started checklist on the Dashboard before creating anything.\n"
 "PASS: step 1 shows a number 1 and a 'Create a project' button - no tick.\n"
 "3. Now create a project and come back to the checklist.\n"
 "PASS: step 1 now shows a tick.\n"
 "FAIL: a tick appears at step 2 of this test, before the project exists."),

11: ("DIRECT",
 "The Get Started page listed four setup steps, but after creating a project the app dropped the "
 "user on the Project Profile screen with no way back. Steps 2 to 4 - connect your machine, invite "
 "your team, connect integrations - were unreachable unless you typed the address by hand. The "
 "flow dead-ended after step 1.",
 "The checklist is now the home base you always come back to. Saving the Project Profile returns "
 "you to the checklist with step 1 ticked, and each of the step 2-4 screens carries a 'Back to Get "
 "started' link until setup is finished. The ticks work themselves out automatically.",
 "1. From a new workspace, click 'Create your first project' on the checklist.\n"
 "2. Create the project. You land on Project Profile.\n"
 "3. Fill anything in and click Save.\n"
 "PASS: you are returned to the Get Started checklist, and step 1 is ticked.\n"
 "4. Click step 2 (Connect your machine). Look at the top of that screen.\n"
 "PASS: there is a 'Back to Get started' link, and it returns you to the checklist.\n"
 "5. Repeat step 4 for Invite your team and Connect integrations.\n"
 "FAIL: any of those three screens has no way back, or the checklist does not tick."),

12: ("DIRECT",
 "The app was calling an internal address (/api/runners/) over and over on every screen. The team "
 "asked what it was and whether it was wasteful. It is the check on whether your machine is still "
 "connected - but it ran at full speed everywhere, including screens where nobody is watching for "
 "it.",
 "The check now runs gently (about every 15 seconds) on ordinary screens and keeps its fast pace "
 "(about every 4 seconds) only on Connect Machine and Phases & Runs, where live connection status "
 "actually matters. Roughly a four-fold reduction in background traffic on ordinary screens.",
 "1. Open the browser's developer tools (F12) and go to the Network tab.\n"
 "2. In its filter box type: runners\n"
 "3. Sit on the Dashboard for one minute without clicking anything and count the requests.\n"
 "PASS: roughly 4 requests in a minute (about one every 15 seconds).\n"
 "4. Clear the list, go to Phases & Runs, and count again for one minute.\n"
 "PASS: roughly 15 requests in a minute (about one every 4 seconds).\n"
 "FAIL: the Dashboard is as busy as Phases & Runs.\n"
 "NOTE: this is the one test in this sheet that needs developer tools. It is a fair check to skip "
 "if you would rather not."),

18: ("DIRECT",
 "The navigation showed made-up numbers: the notification bell always said 4, the sidebar Gates "
 "and Clarifications tabs always showed the same counts, and the companion pill was always a green "
 "'Ready' even when no machine was connected.",
 "Those counts are now driven by what genuinely needs you, and they hide when nothing is pending. "
 "The companion pill shows the real Ready or Offline state.",
 "1. Log in to a workspace where nothing is waiting for you - no pending gates, no clarifications.\n"
 "2. Look at the bell in the top bar and the Gates and Clarifications entries in the sidebar.\n"
 "PASS: no number is shown against any of them.\n"
 "3. Make sure your companion machine is NOT running, and look at the companion pill.\n"
 "PASS: it says Offline, not Ready.\n"
 "4. Now trigger a phase so a gate or a clarification opens, and come back.\n"
 "PASS: the counts appear and match what is actually waiting.\n"
 "FAIL: a fixed 4, 3 or 1 appears, or the pill says Ready with nothing connected."),

28: ("DIRECT",
 "In the 'Needs me' section of the Workspace Dashboard, phase and role names were shown raw, with "
 "underscores - '04_architecture', 'product_owner' - and the sidebar counts were fixed numbers "
 "that never changed.",
 "The Needs-me tiles and list now show readable names ('Architecture', 'Product Owner'), and the "
 "sidebar Gates and Clarifications counts and the bell are driven by the real totals.",
 "1. Get at least one gate and one clarification pending (trigger a phase and let it reach its "
 "gate).\n"
 "2. Open the Workspace Dashboard and read the 'Needs me' section carefully.\n"
 "PASS: phase names read like 'Architecture', roles like 'Product Owner' - no underscores, no "
 "leading numbers such as '04_'.\n"
 "3. Compare the sidebar Gates count against the number of gates actually listed on the Gates "
 "page.\n"
 "PASS: they match.\n"
 "FAIL: any underscore or number prefix on screen, or a count that does not match reality."),

29: ("DIRECT",
 "A sweep the team asked for: anywhere in the app that machine-style names with underscores were "
 "shown to a user, and anywhere a value was hardcoded that should have reflected real data.",
 "A bounded sweep across the main in-app screens: remaining raw phase, role and status names were "
 "made readable on the Gate-role coverage list, Clarifications, the Phases & Runs gate tooltip, "
 "the Work Item panels, Traceability nodes and the Run transcript title; and the companion status "
 "pill now reflects the real machine status instead of a fixed 'Ready'.",
 "This is a LOOK-EVERYWHERE check rather than a single test. Walk these screens and read every "
 "label, badge, chip, tooltip and status:\n"
 "  Dashboard - Work Items board and list - a Work Item detail page - Phases & Runs - Run Console "
 "- Clarifications - Gates - Artifacts & Traceability - Traceability graph - Roles Matrix.\n"
 "PASS: you find NO text containing an underscore between words (task_breakdown, product_owner, "
 "awaiting_gate, phase_gate) and no leading number prefix (04_architecture).\n"
 "FAIL: note the exact screen and the exact text you saw, and which element it was in - that "
 "detail is what makes it fixable.\n"
 "NOTE: brownfield and code-intelligence screens were deliberately left out of this sweep by team "
 "agreement, so findings there are not failures of this row."),

31: ("DIRECT",
 "The 'Back to Get started' link kept appearing on the Connect Machine, Invite and Integrations "
 "screens even after setup was finished. It only went away once you had a project, a connected "
 "machine AND a teammate who had accepted an invite - so a solo developer, who never needs to "
 "invite anybody, saw it forever.",
 "By team decision the link now hides once you have a project and a connected machine. Inviting a "
 "team stays optional.",
 "1. Get to a state with a project created and your companion machine connected (the pill reads "
 "Ready). Do NOT invite anyone.\n"
 "2. Open Connect Machine, then Users & Invitations, then Integrations.\n"
 "PASS: none of the three shows a 'Back to Get started' link any more.\n"
 "FAIL: the link is still nagging on any of them.\n"
 "3. As a sanity check, on a fresh workspace with no companion connected, the link SHOULD still be "
 "there - that is correct behaviour, not a failure."),

34: ("DIRECT",
 "The companion status text was near-white on the white top bar - it had been styled for the dark "
 "sidebar and reused on the light header - so 'Companion: Offline' and 'Companion: Ready' were "
 "barely readable.",
 "The pill now has proper contrast in both places: solid white bold text in the dark sidebar, and "
 "colour-coded text on a bordered tint in the white top bar - red offline, green ready, amber "
 "connecting.",
 "1. With the companion NOT running, look at the status pill in the top bar.\n"
 "PASS: 'Companion: Offline' is clearly readable at a normal viewing distance, in red.\n"
 "2. Look at the same status in the dark sidebar.\n"
 "PASS: clearly readable there too.\n"
 "3. Start the companion and wait for it to connect. Look at both again.\n"
 "PASS: 'Ready' is clearly readable, in green.\n"
 "FAIL: you have to lean in or select the text to read it in any of those four places."),

171: ("DIRECT",
 "The companion connection status was shown in THREE places at once - the top bar pill, a "
 "'Connected --' box on the Workspace Dashboard, and a green 'Companion ready --' box on Phases & "
 "Runs - all saying the same thing. The team judged the two page boxes redundant.",
 "The Dashboard 'Companion' card and the Phases & Runs 'Companion ready' box were removed. The "
 "top-bar pill is now the single place companion status is shown.",
 "1. With the companion connected, open the Workspace Dashboard.\n"
 "PASS: there is NO separate box or card showing companion or 'Connected' status anywhere on the "
 "page. The top-bar pill still shows it.\n"
 "2. Open Phases & Runs.\n"
 "PASS: there is NO green 'Companion ready' box above or beside the Trigger a Phase card.\n"
 "3. Repeat both with the companion stopped.\n"
 "PASS: still no page-level box; the top-bar pill correctly reads Offline.\n"
 "FAIL: either box is still on screen."),

174: ("DIRECT",
 "The Clarifications page carried leftover testing-era wording about billing - '...and nothing is "
 "billed while it waits' in the header, '(billing $0)' in the empty state, and a 'Paused - no "
 "usage billed while waiting' chip. The team asked for all of it to go.",
 "The billing clause and the '(billing $0)' hint were removed and the message re-aligned; the "
 "pause chip now reads 'Paused - waiting for your answer' with no mention of cost.",
 "1. Open the Clarifications page with nothing pending, and read the header and the empty state.\n"
 "PASS: no mention of billing, cost, usage or dollars anywhere; the text is neatly aligned.\n"
 "2. Get a clarification pending (trigger Ideation on a new work item and wait for the questions), "
 "then open the page and read the chip on the card.\n"
 "PASS: it reads 'Paused - waiting for your answer'.\n"
 "FAIL: any '$', 'billed', 'billing' or 'usage' text on this screen."),

175: ("DIRECT",
 "A 'Cost (est.)' column and a 'no usage billed while waiting' note were added across many screens "
 "for testing and are no longer wanted. The team asked for them gone, and asked for a sweep to "
 "find every place they appeared - which turned out to be SEVEN screens, not one.",
 "The cost column and its note were removed everywhere: the Phases & Runs Runs card, the Run "
 "Console, the Work Item Task and Epic panels, the Phase Console table and the Run Transcript "
 "table; every 'no usage billed while waiting' pause banner was reworded to 'Paused - waiting for "
 "your answer'; and a '$0 while waiting' note was removed from the Dashboard.",
 "Check all seven, in this order - trigger a phase first so there is a run to look at:\n"
 "1. Phases & Runs, the Runs card.\n"
 "2. Run Console (click into the run).\n"
 "3. A Task work-item page.\n"
 "4. An Epic work-item page.\n"
 "5. The Phase Console table on a work item.\n"
 "6. The Run Transcript view.\n"
 "7. The Workspace Dashboard.\n"
 "PASS on each: no 'Cost', 'Cost (est.)', '$' figure or billing note anywhere.\n"
 "KNOWN AND DELIBERATE: the /dev/components design gallery still has a demo COST column. That is "
 "the raw component showcase, not an app screen, and is NOT a failure.\n"
 "FAIL: a cost column or billing note on any of the seven real screens."),

3: ("DIRECT",
 "Several form fields were left blank with nothing telling the user what to type - every Project "
 "Profile field except tech stack, the free-text clarification answer box, and the repository base "
 "branch.",
 "Every remaining field now shows a helpful grey example: all seven Project Profile fields, the "
 "clarification answer box ('Type your answer...') and the repository base branch ('main').",
 "1. Open Project Profile on a project with an empty profile. Look at every field.\n"
 "PASS: each empty field shows grey example text.\n"
 "2. Open Repositories and start adding a repository. Look at the base branch box.\n"
 "PASS: it shows 'main' as a grey hint.\n"
 "3. Get a clarification with a free-text answer and look at the answer box.\n"
 "PASS: it shows 'Type your answer...'.\n"
 "FAIL: any empty box with no guidance at all."),

7: ("DIRECT",
 "The project-name box on the Create Project screen was pre-filled with the sample name 'Payment "
 "Gateway v2'.",
 "The box now starts empty with a grey example ('e.g. Billing Service'), and the Create project "
 "button stays greyed out until a name is typed.",
 "1. Open Create Project.\n"
 "PASS: the name box is empty; 'e.g. Billing Service' is grey placeholder text.\n"
 "2. Without typing anything, look at the Create project button.\n"
 "PASS: it is greyed out and cannot be clicked.\n"
 "3. Type a name.\n"
 "PASS: the button becomes clickable.\n"
 "FAIL: any pre-filled name, or a live Create button with an empty name box."),

8: ("DIRECT",
 "The Create Project screen showed a long sentence under the track selector - 'Greenfield starts "
 "from a blank profile. Brownfield opens onboarding to assess what already exists.' The team asked "
 "for it to become a tooltip instead of permanent page text.",
 "The sentence was removed and the same explanation is now a hover tooltip: an info marker beside "
 "the Track label, plus tooltips on the Greenfield and Brownfield buttons themselves.",
 "1. Open Create Project and look at the Track selector.\n"
 "PASS: the long 'Greenfield starts from a blank profile...' sentence is NOT printed on the page.\n"
 "2. Hover over the small info marker next to the 'Track' label.\n"
 "PASS: the explanation appears as a tooltip.\n"
 "3. Hover over the Greenfield button, then the Brownfield button.\n"
 "PASS: each shows its own short explanation.\n"
 "FAIL: the sentence is still printed, or no tooltip appears anywhere."),

9: ("DIRECT",
 "Straight after creating a project, the Project Profile screen claimed the profile was already "
 "saved: a '✓ Saved · v1' badge at the top and 'Saving will create v2' at the bottom - even though "
 "nothing had ever been saved.",
 "A project with no saved profile is now treated as genuinely not saved. The badge reads 'Draft · "
 "not saved yet' until the first save, and the hint correctly says 'Saving will create v1'. After "
 "saving it shows '✓ Saved · v1', and v2 on the next edit.",
 "1. Create a brand-new project. You land on Project Profile.\n"
 "2. WITHOUT saving anything, read the badge at the top and the hint at the bottom.\n"
 "PASS: top says 'Draft · not saved yet'; bottom says 'Saving will create v1'.\n"
 "3. Fill something in and Save. Read both again.\n"
 "PASS: top says '✓ Saved · v1'.\n"
 "4. Change something without saving. Read the bottom hint.\n"
 "PASS: it now says 'Saving will create v2'.\n"
 "FAIL: any 'Saved' claim or a v2 hint before the first save."),

10: ("DIRECT",
 "Tech stack was a single-line box squeezed in beside Domain, so a realistic multi-line technology "
 "list would not fit and could not be read back.",
 "Tech stack is now a full-width, six-line box like the other long fields, with an example hint.",
 "1. Open Project Profile.\n"
 "2. Paste a realistic multi-line technology list into Tech stack - several lines, e.g. your own "
 "stack, or the list in the Reference column of this row's original bug report.\n"
 "PASS: the box is full width, about six lines tall, and the whole list is visible without "
 "scrolling inside the box.\n"
 "3. Save, leave the page, and come back.\n"
 "PASS: the full text is still there and still readable.\n"
 "FAIL: a one-line box, or text you have to scroll inside the field to read."),

33: ("DIRECT",
 "Only the tech-stack field of the Project Profile had an example. Description, domain, coding "
 "standards, non-functional requirements, constraints, glossary and important context gave the "
 "user no idea what good input looks like.",
 "Every Project Profile field now shows a realistic example when empty - for instance domain: "
 "'Personal finance, Healthcare, E-commerce'; NFRs: response-time, uptime and accessibility "
 "examples.",
 "1. Open Project Profile on a project whose profile is empty (or clear a field).\n"
 "2. Go through all eight fields one by one.\n"
 "PASS: every empty field shows a grey, realistic example - not a repeat of the field name, and "
 "not blank.\n"
 "3. Type into a field.\n"
 "PASS: the example disappears and does not get saved as your value.\n"
 "FAIL: any empty field with no example."),

211: ("DIRECT",
 "Nothing stopped two projects in one workspace having the same name. Every screen that names a "
 "project - the project switcher, the board header, an invitation - then named two different "
 "things identically, and the wrong one could be worked on for days before anyone noticed.",
 "The database now enforces one name per workspace and the API returns the conflict the Create "
 "Project screen was already waiting for - so the message it shows was already built and simply "
 "never fired. Blank and whitespace-only names are refused too. Deliberately case-insensitive: "
 "'Billing Service' and 'billing service' are the same project to a person reading a list. Team "
 "decision: an archived project KEEPS its name reserved.",
 "1. Create a project called (say) 'Billing Service'.\n"
 "2. Try to create a second project with exactly the same name.\n"
 "PASS: it is refused, and the screen says 'A project named Billing Service already exists in this "
 "workspace'.\n"
 "3. Try again with 'billing service' - all lower case.\n"
 "PASS: refused the same way. (This is deliberate.)\n"
 "4. Try to create a project with an empty name, then with only spaces.\n"
 "PASS: both refused.\n"
 "5. If you can archive a project, archive 'Billing Service' and try to create a new one with that "
 "name.\n"
 "PASS: still refused - the archived project keeps its name. This is a team decision, not a bug.\n"
 "FAIL: any duplicate is created, or the refusal happens with no message on screen."),

221: ("DIRECT",
 "'Onboarding' is the wizard for bringing an EXISTING codebase into the platform. It was offered "
 "to everybody, including projects started from scratch that morning - and it did not merely "
 "appear where it should not, it ASSERTED the wrong thing, putting a 'Brownfield' badge at the top "
 "and saying 'Brownfield project. Let's assess what already exists' over whatever project you had "
 "open.",
 "Team chose 'hide it' over 'grey it out'. The sidebar no longer offers Onboarding on a project "
 "started from scratch; all three onboarding addresses explain themselves if reached directly "
 "rather than running a wizard; and the server refuses too, and says why. A deliberate detail: it "
 "hides only on an explicit 'greenfield', so if the server is briefly older than the app during a "
 "deployment the item STAYS - a brownfield team must never be locked out of the screen that starts "
 "their lifecycle.",
 "1. Open a GREENFIELD project (one created from scratch) and look at the sidebar.\n"
 "PASS: there is no Onboarding entry.\n"
 "2. Type the onboarding address directly into the browser: /onboarding\n"
 "PASS: the screen explains that this project has no existing code and does not apply - it does "
 "NOT run a wizard and does NOT claim the project is brownfield.\n"
 "3. Try /onboarding/documents too.\n"
 "PASS: same - explains itself.\n"
 "4. Now open a BROWNFIELD project.\n"
 "PASS: Onboarding IS in the sidebar and works normally. That is correct.\n"
 "FAIL: a greenfield project is shown a 'Brownfield' badge, or the wizard runs on it."),

13: ("DIRECT",
 "On the Connect Machine page the Copy button beside the generated token did nothing when clicked, "
 "and on the token card it was almost invisible - white text on a pale background, styled for the "
 "dark command block and reused on the light card.",
 "The Copy buttons on both the token and the command blocks now genuinely copy to the clipboard "
 "(with a fallback for older browsers) and briefly show '✓ Copied!'. The button on the light token "
 "card was given proper contrast so it is clearly visible.",
 "1. Open Connect Machine and generate an enrolment token.\n"
 "2. Look at the Copy button beside the token WITHOUT hovering over it.\n"
 "PASS: it is clearly visible against the light card.\n"
 "3. Click it.\n"
 "PASS: it briefly shows '✓ Copied!'.\n"
 "4. Paste into a text editor.\n"
 "PASS: the pasted text is exactly the token shown on screen.\n"
 "5. Repeat 2-4 for the Copy button on the dark command block.\n"
 "FAIL: an invisible button, no confirmation, or nothing on the clipboard."),

14: ("DIRECT",
 "The command shown for connecting your machine had a fake web address written into it - "
 "https://app.acme.com - so anyone copying it verbatim pointed their machine at a site that is not "
 "ours.",
 "The command now builds its address from the app's own configured location instead of a hardcoded "
 "URL.",
 "1. Open Connect Machine and generate a token so the command block appears.\n"
 "2. Read the command carefully, particularly the address after --api-url.\n"
 "PASS: it is the address of the app you are actually using (for example http://localhost:8000 on "
 "a local stack, or your team's server address).\n"
 "FAIL: it contains 'acme.com', or any address that is not the one you are working against.\n"
 "3. Copy the command and run it - it should reach the app rather than failing to resolve."),

15: ("DIRECT",
 "After generating a token, TWO spinning loaders appeared beside 'Waiting for first check-in - run "
 "the command above...'. The waiting component drew its own spinner and the page was passing in a "
 "second one.",
 "The extra spinner was removed. The waiting status now shows a single loader.",
 "1. Open Connect Machine and generate a token. Do NOT start your companion yet.\n"
 "2. Look at the 'Waiting for first check-in' line.\n"
 "PASS: exactly ONE spinner is animating.\n"
 "FAIL: two spinners side by side."),

61: ("DURING A RUN",
 "After connecting a machine and running one phase, the app reported the companion disconnected "
 "and asked the user to connect again. Worse, the NEXT phase then showed as running but never "
 "produced any artifacts or a gate. Four separate faults were behind it, the main one being that "
 "the companion CRASHED after the first phase because a billing guard misfired on a subscription "
 "that is not billed per token.",
 "The crashing guard was removed; the companion now sends a heartbeat every 30 seconds on its own "
 "thread so a long phase never makes it look offline; a run left claimed by a dead companion is "
 "re-claimed after 15 minutes instead of being stranded forever; and the offline message now shows "
 "the REAL time since the machine was last seen rather than a hardcoded 'last seen 5m ago'.",
 "This is the single most valuable end-to-end check in this sheet. Allow an hour.\n"
 "1. Connect your companion machine and confirm the top-bar pill reads Ready.\n"
 "2. Create a work item and trigger the Ideation phase.\n"
 "3. WHILE IT RUNS, watch the companion pill continuously for the whole phase - especially any "
 "quiet stretch longer than two minutes.\n"
 "PASS: the pill stays Ready for the entire run. It must never flip to Offline mid-phase.\n"
 "4. When Ideation finishes, check the companion process on your machine is STILL RUNNING.\n"
 "PASS: it is still serving. It must not have exited.\n"
 "5. Now trigger the next phase (Requirements) on the same work item.\n"
 "PASS: it starts, produces artifacts, and opens a gate - exactly like the first one.\n"
 "FAIL: the pill flips to Offline while a phase is genuinely running; the companion process exits "
 "after a phase; or the second phase shows 'running' forever with no artifacts and no gate.\n"
 "6. Separately: stop the companion and open Connect Machine. Read the offline message.\n"
 "PASS: it shows a real elapsed time that grows as you wait, not a fixed '5m ago'."),

84: ("SET UP FIRST",
 "The trigger routed work to the most recently created machine registration even if that "
 "registration had never actually connected. So if you opened Connect Machine to copy a token "
 "while your companion was already running on an older one, the work could be sent to a "
 "registration whose companion never existed - and the live companion sat there receiving nothing. "
 "The run stuck at 'pending' and the build never started.",
 "The trigger now prefers, in order: the newest registration that is ONLINE right now; then the "
 "newest that has ever checked in; then the newest overall (nothing connected yet, so the work "
 "waits, as before). Applies to both phase and build triggers.",
 "SET UP: your companion must be running and connected (pill reads Ready).\n"
 "1. With the companion still running, open Connect Machine and generate a NEW token. Do NOT use "
 "it - do not restart your companion with it.\n"
 "2. Go to Phases & Runs, pick a work item, and trigger a phase.\n"
 "PASS: the run is picked up by your ALREADY-RUNNING companion within a minute or so, and the run "
 "console starts showing progress.\n"
 "FAIL: the run sits at 'pending' or 'Queued' and never starts, while your companion is plainly "
 "alive and polling.\n"
 "NOTE: this used to require wiping the extra registrations by hand to recover. If it fails, say "
 "so rather than clearing them - the whole point is that clearing should no longer be necessary."),

105: ("SET UP FIRST",
 "Restarting the app's backend dropped the local companion and it did NOT come back on its own. It "
 "stopped checking in, and a phase triggered right afterwards sat unclaimed until somebody "
 "manually restarted the companion.",
 "The companion now survives a backend restart. Its work-poll retries with a widening pause "
 "(logging 'backend unreachable... reconnecting in Ns' and then 'backend reconnected; resuming'), "
 "and a finished phase's report is retried through about two minutes of outage so completed work "
 "is not lost to a restart at exactly the wrong moment. A plain backend restart now needs NO "
 "manual companion action.",
 "SET UP: companion running and connected. You will need to restart the backend - ask whoever runs "
 "the stack if that is not you.\n"
 "1. With the companion connected and idle, restart the backend and worker.\n"
 "2. Watch the companion's own terminal window.\n"
 "PASS: it logs something like 'backend unreachable... reconnecting in Ns', then 'backend "
 "reconnected; resuming'. It does NOT exit.\n"
 "3. Wait for the app to come back, then check the top-bar pill.\n"
 "PASS: it returns to Ready by itself, without you touching the companion.\n"
 "4. Trigger a phase.\n"
 "PASS: it is claimed and runs normally.\n"
 "FAIL: the companion process exits, or you have to restart it before anything will run."),

198: ("SET UP FIRST",
 "A brand-new member who had not created a project yet opened Connect Machine and clicked Generate "
 "token. The screen appeared to produce a token and showed the command - but the token was a "
 "hardcoded placeholder written into the code, 'rnr_3f9a…b2', complete with a literal ellipsis. "
 "Generation had actually FAILED, and the failure was rendered as a success. The user copied it to "
 "their machine and got an unexplained failure there instead, with nothing connecting the two.",
 "The placeholder is deleted outright, not replaced with a better placeholder. The success view is "
 "now reachable only by a genuine success; a failure shows the server's own message; and the "
 "command shown before a token exists says <your-token> rather than pretending to be one. Also "
 "guarded: a workspace with no project now says 'create a project first', with a link, and sends "
 "nothing.",
 "SET UP: a brand-new workspace with NO project created. Sign up a fresh account for this.\n"
 "1. Log in and go straight to Connect Machine without creating a project.\n"
 "2. Look at the screen.\n"
 "PASS: it tells you to create a project first, and offers a link to do so.\n"
 "3. Look for a token or a Generate button.\n"
 "PASS: no token is shown, and nothing resembling 'rnr_3f9a…b2' appears anywhere.\n"
 "4. If a command block is visible before any token exists, read it.\n"
 "PASS: it says <your-token> as an obvious placeholder, not a fake real-looking token.\n"
 "FAIL: any token appears; especially one with a '…' in the middle.\n"
 "5. Now create a project and generate a token properly.\n"
 "PASS: a real token appears - roughly 43 characters, no 'rnr_' prefix, no ellipsis - and it "
 "actually authenticates your companion."),

206: ("DIRECT",
 "A run could be dispatched before any machine was known, and then no companion could ever claim "
 "it. It sat 'running and pending' forever, invisible in the interface, and blocked any new "
 "trigger on the same work item.",
 "The claim now also matches a waiting job that names no particular machine, for the same "
 "workspace and project, and binds it to whichever companion picks it up. A retry after an "
 "exhausted remediation also carries the original requester through, so it routes back to the "
 "right machine.",
 "1. Make sure your companion is NOT running.\n"
 "2. Trigger a phase on a work item. It should sit waiting.\n"
 "3. NOW start your companion.\n"
 "PASS: within a minute or so the waiting run is picked up and starts running - you did not have "
 "to re-trigger it.\n"
 "4. Let it finish, then try to trigger another phase on the same work item.\n"
 "PASS: it is allowed and runs.\n"
 "FAIL: the run never starts after the companion comes up, or the work item refuses all further "
 "triggers because something is stuck on it."),

223: ("DIRECT",
 "The Connect Machine screen showed a 'Projects' picker that did nothing at all - no value, no "
 "handler, no state behind it. Whatever you chose, the token was always issued against the FIRST "
 "project in your list. It also showed a made-up project name in the list. A developer on several "
 "projects would connect their machine, believe it was enrolled for the project they picked, and "
 "find their phases dispatched somewhere else.",
 "The picker is real, it drives what is sent, and it defaults to the project you currently have "
 "open. The invented project name is gone. Made SINGLE-select deliberately: the enrolment binds "
 "one machine registration to one project, so a multi-select was a promise the server cannot keep.",
 "SET UP: you need an account that is a member of at least TWO projects.\n"
 "1. Select project A in the top bar, then open Connect Machine.\n"
 "PASS: the project picker already shows project A.\n"
 "2. Read the whole list of projects in the picker.\n"
 "PASS: every entry is a project you really have. No unfamiliar or made-up name.\n"
 "3. Change the picker to project B and generate a token.\n"
 "4. Connect your companion with that token, then trigger a phase on a work item in PROJECT B.\n"
 "PASS: it is claimed and runs.\n"
 "FAIL: the picker ignores your choice and the token binds to project A; or a project you do not "
 "recognise appears in the list; or the picker allows several projects at once."),

19: ("DIRECT",
 "The Users & Invitations page said 'Everyone in the Acme Corp workspace' - a demo name typed into "
 "the code - regardless of what your workspace is actually called.",
 "The subtitle now shows the real workspace name from your signed-in session.",
 "1. Note the name of your workspace (shown at signup, and in the top bar).\n"
 "2. Open Users & Invitations and read the subtitle under the heading.\n"
 "PASS: it names YOUR workspace.\n"
 "FAIL: it says 'Acme Corp', or any name that is not yours."),

20: ("DIRECT",
 "On the invite form the roles dropdown offered only four roles, showed them as raw keys with "
 "underscores ('product_owner'), and once you added a second role row with 'grant another role' "
 "there was no way to remove it.",
 "The dropdown now lists the full set of ten roles from one shared source, every role shows a "
 "readable label (Product Owner, Security Engineer, ...) with no underscores, and each granted-role "
 "row has an X to remove it once there is more than one. The same labels are used everywhere a "
 "user's roles are listed.",
 "1. Open Users & Invitations and start an invite.\n"
 "2. Open the role dropdown and count the options.\n"
 "PASS: ten roles are listed.\n"
 "3. Read every one of them.\n"
 "PASS: all readable - 'Product Owner', 'Tech Lead', 'Security Engineer' - with no underscores.\n"
 "4. Click 'Grant another role' to add a second row.\n"
 "PASS: an X appears on the rows so you can remove one.\n"
 "5. Click the X.\n"
 "PASS: that row is removed.\n"
 "6. Complete the invite, then look at where the user's roles are listed on the page.\n"
 "PASS: the same readable labels, not raw keys.\n"
 "FAIL: four options, any underscore, or no way to remove an added row."),

30: ("DIRECT",
 "The Workspace Admin page did not list registered or invited users - it showed an 'It's just you "
 "so far' empty state, and the users only appeared behind the drawer once you clicked Invite. The "
 "empty state was being shown whenever there was at most one user and no still-pending invite, "
 "which hid the admin's own row.",
 "The table now shows whenever there is anyone to list - and the signed-in admin always is one. "
 "The empty state appears only when the list is genuinely empty.",
 "1. Sign in as a workspace admin and open Users & Invitations / Workspace Admin.\n"
 "PASS: you can see YOUR OWN row in the table, straight away, without opening the invite drawer.\n"
 "2. Invite someone, then revoke that invite.\n"
 "PASS: the revoked invite is still visible in the list - it does not make the whole table "
 "disappear.\n"
 "3. Invite a second person and have them accept.\n"
 "PASS: both users are listed.\n"
 "FAIL: an 'It's just you so far' empty state while there is plainly at least one user to show."),

46: ("DIRECT",
 "The gate-role coverage notes on the Roles Matrix leaked raw role keys - text like 'no tech_lead "
 "assigned ...' - even though the label beside it was readable.",
 "The note is now built with the readable role name, e.g. 'no Product Owner assigned - an admin "
 "can approve the planning gate'.",
 "1. Open the Roles Matrix / Roles & memberships screen on a project where at least one gate role "
 "is not assigned to anybody.\n"
 "2. Read the coverage notes.\n"
 "PASS: role names read like 'Product Owner' and 'Tech Lead'.\n"
 "FAIL: any note containing an underscore, such as 'tech_lead' or 'product_owner'."),

47: ("SET UP FIRST",
 "In the Gates decided-history, the 'By' column showed a fragment of a database id for anybody "
 "else's decision. Only your own decisions said 'You'.",
 "The approval data now carries the approver's name, and the Gates history shows it.",
 "SET UP: you need a SECOND user in the workspace who can decide a gate.\n"
 "1. Have the second user approve or reject a gate.\n"
 "2. Sign in as yourself and open the Gates page.\n"
 "3. Find that decision in the decided history and read the 'By' column.\n"
 "PASS: it shows the other person's name.\n"
 "4. Find one of your own decisions.\n"
 "PASS: it says 'You'.\n"
 "FAIL: a long string of letters and numbers in the 'By' column."),

51: ("SET UP FIRST",
 "A signed-in user who is NOT an admin could still reach the admin screens by typing their address "
 "- and got a blank, broken page, because the screens fetch a users list that refuses them and "
 "nothing handled the refusal.",
 "All admin addresses now render a clear 'Admin access needed' panel for non-admins - saying what "
 "the page is, who can use it, and offering a button back to the Dashboard - instead of mounting "
 "the broken screen.",
 "SET UP: sign in as a user who is NOT a workspace admin.\n"
 "1. Confirm the admin entries are correctly hidden from your sidebar.\n"
 "2. Now type the address directly: /admin/roles\n"
 "PASS: a clear panel appears saying admin access is needed, explaining what the page is and who "
 "can use it, with a button back to the Dashboard.\n"
 "3. Try /admin/users as well.\n"
 "PASS: the same panel.\n"
 "4. Sign in as an admin and open both addresses.\n"
 "PASS: the real screens load normally.\n"
 "FAIL: a blank white page, a spinner that never resolves, or a broken-looking screen."),

52: ("DIRECT",
 "While a role change was saving, the banner always read 'Saving role change for Tom Reyes "
 "(reviewer @ ...)' - a static placeholder - regardless of who was actually being changed. The "
 "project name also fell back to the sample 'Payment Gateway v2'.",
 "The screen now tracks which user and role are actually being saved and builds the banner from "
 "that real change; the project-name fallback is a neutral 'this project'.",
 "1. Open the Roles & memberships screen.\n"
 "2. Toggle a role on for a real user and watch the banner that appears while it saves.\n"
 "PASS: it names the REAL user, the REAL role and the REAL project - e.g. 'Saving role change for "
 "Priya Nair (Reviewer @ Billing Service)...'.\n"
 "FAIL: it says 'Tom Reyes', 'reviewer @ ...' or 'Payment Gateway v2'.\n"
 "3. Check the project selector on the same screen shows your real project name.\n"
 "TIP: the banner is brief - watch closely, or throttle the network in developer tools if you miss "
 "it."),

214: ("SET UP FIRST",
 "A string of actions that change things needed no login at all: creating a project, rewriting the "
 "project profile that every agent reads, creating and editing work items, starting a phase run, "
 "taking over a run, and registering a companion machine. A plain engineer with no admin grant "
 "could do all of it - and so, for most of them, could somebody with no session whatsoever.",
 "Two layers. Everything above now requires a signed-in session. On top of that, editing the "
 "project profile additionally requires tech lead or admin, because it re-steers every agent that "
 "will ever run on the project. Triggering, building, taking over and resuming require project "
 "MEMBERSHIP rather than a lead role - each role drives its own phase, so a lead-only bar would "
 "lock most of the team out of ordinary work. Membership also closed a hole of its own: the old "
 "check only ever asked whether you were signed in, so a signed-in user could act on a project "
 "they were not a member of.",
 "SET UP: you need (a) a signed-in user who is NOT a member of some project X, and (b) a member of "
 "project X who is NOT a tech lead or admin.\n"
 "1. As the NON-MEMBER, try to open project X and trigger a phase on one of its work items.\n"
 "PASS: refused, with a message explaining why.\n"
 "2. As the non-member, try to edit project X's Project Profile.\n"
 "PASS: refused.\n"
 "3. As the MEMBER who is not a lead, trigger a phase.\n"
 "PASS: ALLOWED. This is deliberate - an ordinary member must be able to do ordinary work.\n"
 "4. As that same member, try to edit the Project Profile.\n"
 "PASS: refused - profile editing needs tech lead or admin.\n"
 "5. Sign out entirely and try to reach any of those actions.\n"
 "PASS: you are sent to sign in.\n"
 "FAIL: any of steps 1, 2, 4 or 5 succeeds - or step 3 is refused, which would be over-correction.\n"
 "KNOWN AND DELIBERATE: registering a companion machine from the command line still takes no "
 "login. That is recorded against S.No 35 and is not a failure of this row."),

252: ("SET UP FIRST",
 "A person's roles on a project are stored as separate records - one for 'tech lead', one for "
 "'product owner'. Three screens read that list as though it held one row per project and took "
 "whichever came back first. So a tech lead who is also product owner, opening a gate that needs "
 "tech lead, was told 'you don't hold the tech_lead role on this project' and shown a disabled "
 "Approve. They do hold it. The server always agreed they hold it. The same root cause listed "
 "their project once per role in the project switcher.",
 "The question now lives in one place: the app knows every role you hold on the selected project, "
 "and asks one shared question that also honours the workspace-admin override - matching exactly "
 "what the server already did. Both screens ask that question instead of comparing a single role. "
 "The project switcher uses a deduplicated list.",
 "SET UP: one user who is NOT a workspace admin and holds TWO OR MORE roles on the same project - "
 "for example tech_lead and product_owner. Grant this in Roles & memberships.\n"
 "1. Sign in as that user and open the project switcher in the top bar.\n"
 "PASS: the project appears exactly ONCE, not once per role.\n"
 "2. Get a gate open that requires the SECOND of their roles (not whichever the app happens to "
 "list first) - a tech-lead merge gate is a good one.\n"
 "3. Open Gates and select that gate.\n"
 "PASS: the Approve, Reject and Request-changes buttons are LIVE, and there is no banner saying "
 "you do not hold the role.\n"
 "4. Approve it.\n"
 "PASS: the decision is accepted.\n"
 "5. Control check - sign in as someone who genuinely does NOT hold the required role.\n"
 "PASS: they still get the read-only panel. The fix must not open the door to everybody.\n"
 "6. Control check - a workspace admin can still decide anything.\n"
 "FAIL: the two-role user is refused a decision the server would have accepted, or their project "
 "is listed several times in the switcher."),

}
