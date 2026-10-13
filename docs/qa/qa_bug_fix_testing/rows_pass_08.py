# -*- coding: utf-8 -*-
"""Pass 8: planning phases, clarifications and the run console."""

ROWS = {

24: ("DIRECT",
 "When a clarification question offered an 'Other (please specify)' choice, picking it gave you "
 "nowhere to type the specifics - and the words 'Other (please specify)' would have been submitted "
 "as your answer.",
 "Choosing an 'Other / please specify' option now reveals a text box, and what you type is "
 "submitted as the answer. An empty box counts as unanswered, so a required question still blocks.",
 "SET UP: a pending clarification whose question offers an 'Other' choice. Trigger Ideation on a "
 "new work item and wait for the questions.\n"
 "1. Open Clarifications and select an 'Other (please specify)' option.\n"
 "PASS: a text box appears immediately.\n"
 "2. Leave it empty and try to submit a REQUIRED question.\n"
 "PASS: it is still treated as unanswered - you are not allowed through.\n"
 "3. Type a real answer and submit.\n"
 "PASS: your typed text is recorded as the answer, not the words 'Other (please specify)'.\n"
 "4. Re-open the clarification and read it back.\n"
 "PASS: your own words are shown.\n"
 "5. If the agent labelled the option with a letter, e.g. 'd) Other', try that one too.\n"
 "PASS: the box still appears - the letter prefix does not break it.\n"
 "FAIL: no text box, or the option's own words submitted as your answer."),

25: ("DURING A RUN",
 "While registering the documents it had produced, the agent stopped and asked the USER for the "
 "project's internal id - something no user can possibly know. It asked because the registration "
 "step required it and the agent had not been given it.",
 "The platform now supplies the project and run identity automatically from the run the phase is "
 "executing under - the same way the workspace is already supplied - so registration fills them in "
 "itself and never asks. Done on both the machine-side and server-side paths.",
 "1. Run any planning phase (Ideation is quickest) through to completion.\n"
 "2. Watch the Clarifications page throughout.\n"
 "PASS: no question ever asks you for a project id, a run id, a UUID, or 'the project identifier'.\n"
 "3. Let it finish and check the artifacts registered.\n"
 "PASS: they registered without you supplying any identifier.\n"
 "FAIL: any question containing a long string of letters and dashes, or asking which project this "
 "is.\n"
 "NOTE: S.No 53 is the same bug on a different launch path - test both."),

32: ("DIRECT",
 "On Phases & Runs, when no machine was connected the screen did not match the agreed design: the "
 "Runs panel still showed made-up sample runs instead of an empty state, and the disabled phase "
 "list did not match either.",
 "With the companion offline, or simply with no runs yet, the Runs panel now shows the 'No runs "
 "yet' empty state instead of demo rows, and the disabled phase buttons were brought in line with "
 "the design. Phase names on this screen go through the shared readable-name helper.",
 "SET UP: a project with NO runs yet, and your companion NOT running.\n"
 "1. Open Phases & Runs.\n"
 "2. Look at the Runs panel.\n"
 "PASS: it shows a clear 'No runs yet' empty state.\n"
 "PASS: it does NOT list any run you did not create - no sample or demo rows.\n"
 "3. Read the phase names in the Trigger a Phase card.\n"
 "PASS: readable names - Ideation, Requirements, PRD, UX Design - no underscores, no lower case.\n"
 "FAIL: invented runs on screen, or raw phase names.\n"
 "NOTE: which phases appear while offline is S.No 173 - check both together."),

44: ("DIRECT",
 "The Trigger-a-phase buttons on Phases & Runs showed the raw lower-case phase names - 'ideation', "
 "'requirements', 'prd'.",
 "The buttons now show the readable name - Ideation, Requirements, PRD.",
 "1. Open Phases & Runs and read every button in the Trigger a Phase card.\n"
 "PASS: all properly capitalised, with acronyms correct - 'PRD' not 'Prd', 'UX Design' not 'Ux "
 "Design'.\n"
 "PASS: no underscores and no number prefixes.\n"
 "FAIL: any lower-case or raw phase name on a button."),

53: ("DURING A RUN",
 "Registering a phase's documents failed with a server error, and the agent then fell back to "
 "asking the user for the project's internal id. An earlier fix (S.No 25) had covered three of the "
 "four ways a phase can be launched but missed the one your local machine actually uses for "
 "planning and review runs.",
 "The project identity is now supplied on that last launch path too, so registration fills it in "
 "automatically and never asks the user.",
 "This is the same visible symptom as S.No 25 but on the path your COMPANION uses, so it must be "
 "tested with a real connected machine rather than a server-side run.\n"
 "1. Connect your companion machine.\n"
 "2. Trigger a planning phase (Ideation or Requirements) on a work item.\n"
 "3. Let it run all the way through registering its documents.\n"
 "PASS: the documents register successfully - they appear on Artifacts & Traceability.\n"
 "PASS: no server error at the registration step.\n"
 "PASS: no clarification asks you for a project id.\n"
 "FAIL: the run fails at registration, or a question appears asking for an identifier."),

55: ("DIRECT",
 "In the Runs table on Phases & Runs, values were printed exactly as stored: the status as "
 "'awaiting_gate' with an underscore; the run and workflow shown as full long ids nobody can "
 "interpret; and the created time as an unformatted machine timestamp.",
 "The table is now readable for every run: the status reads 'Awaiting gate'; the run shows a short "
 "reference such as 'Run 6b6443fa' that links to the run console, with the full value on hover; the "
 "workflow id is shortened the same way; and Created shows a proper date and time.",
 "SET UP: at least one run, ideally one waiting at a gate.\n"
 "1. Open Phases & Runs and read the Runs table.\n"
 "2. Read the STATUS column.\n"
 "PASS: 'Awaiting gate', 'Completed', 'Running' - no underscores.\n"
 "3. Read the RUN column.\n"
 "PASS: a short reference, not a 36-character id. Hovering shows the full value.\n"
 "4. Click it.\n"
 "PASS: it opens the run console for that run.\n"
 "5. Read the CREATED column.\n"
 "PASS: a readable date and time, e.g. 'Jul 7, 2026, 9:38 PM' - not a raw machine timestamp with a "
 "T and a Z in it.\n"
 "FAIL: an underscore, a full-length id on screen, or an unformatted timestamp."),

60: ("DURING A RUN",
 "Three things the team asked about how clarification questions are presented. The 'Other' option "
 "gave no text box when the agent had labelled it with a letter, e.g. 'd) Other'. The questions "
 "themselves were badly formed - the agent wrote the options INTO the question text as well as "
 "offering them as choices, so you read the same list twice. And the presentation was confusing.",
 "Fixed on two fronts. On screen, the 'Other' text box now appears even when the option carries a "
 "letter prefix. In the agent's instructions, the contract now tells every phase agent to write ONE "
 "short plain-language question and put the choices ONLY in the structured options, never inlined "
 "in the question text - which is what caused the duplicated-options wall of text.",
 "1. Trigger Ideation on a new work item and wait for the clarification questions.\n"
 "2. Read each QUESTION carefully.\n"
 "PASS: each is ONE short question in plain language.\n"
 "PASS: the choices are NOT also written out inside the question text - you should not read the "
 "same list twice.\n"
 "PASS: no shouting capitals, no wall of text.\n"
 "3. Find a question with an 'Other' option - especially one labelled 'd) Other' or similar - and "
 "select it.\n"
 "PASS: a text box appears.\n"
 "4. Answer everything and submit.\n"
 "PASS: accepted.\n"
 "FAIL: options repeated inside the question, or an 'Other' option with nowhere to type."),

62: ("DURING A RUN",
 "The Requirements phase ran a SECOND time by itself. Its document was approved at the gate and the "
 "phase showed as done; a few minutes later the same document was generated again as a 'version 2' "
 "draft with nobody triggering it, and the companion then crashed and went offline. This was caused "
 "by the safety net added for S.No 61: a phase that ran longer than the 15-minute recovery window "
 "had its own just-finished work re-claimed as if it were abandoned.",
 "Three parts. The report is now marked as received the instant your machine reports, so the next "
 "poll can never still see it as unfinished - this closes the race however long the phase ran. The "
 "automatic recovery only applies to runs that are genuinely still going, never one that has "
 "reached a gate or completed. And the companion no longer crashes on a late or duplicate report: "
 "the platform answers gracefully and the companion logs it and keeps running.",
 "SET UP: this needs a phase that runs LONGER THAN 15 MINUTES - a UX Design or a large Requirements "
 "run is ideal. A short phase will not exercise it.\n"
 "1. Trigger a long phase and let it run to completion.\n"
 "2. Note the time it took. If it was under 15 minutes, try a bigger one - this test is only "
 "meaningful past that.\n"
 "3. Approve its gate.\n"
 "4. Now WAIT at least 20 more minutes, doing nothing.\n"
 "5. Open Artifacts & Traceability and look at that phase's documents.\n"
 "PASS: there is ONE version. No 'version 2' appeared on its own.\n"
 "6. Check your companion process.\n"
 "PASS: still running. It did not crash.\n"
 "7. Check Phases & Runs.\n"
 "PASS: no second run for that phase that you did not trigger.\n"
 "FAIL: a duplicate draft appears, or the companion exits after the phase completed."),

63: ("DURING A RUN",
 "A planning phase was running with far more capability than it should have - it could start "
 "sub-agents of its own and read and run things on your machine. In practice this made runs slow, "
 "unpredictable and empty: one Requirements re-run spent over twenty minutes drafting everything "
 "internally through eight sub-agents and registered NOTHING, so the Artifacts page stayed empty "
 "and it looked stalled. It is also a security concern - a planning phase has no business reaching "
 "your file system or shell.",
 "Planning and review phases now run in a proper sandbox: the tools that let them wander are "
 "explicitly blocked, and the engine loads settings only from the empty run folder, never your "
 "personal configuration. So a planning agent can use only the platform's own tools - read the "
 "context, register its documents. Implementation is deliberately NOT sandboxed, because it must "
 "write real code in a real repository.",
 "1. Trigger a PLANNING phase (Requirements or UX Design) and watch the run console.\n"
 "PASS: the run registers its documents steadily as it goes - things appear on Artifacts & "
 "Traceability within minutes, not at the very end.\n"
 "PASS: the console shows platform tool activity, not long stretches of nothing.\n"
 "2. Compare the elapsed time against what this phase used to take.\n"
 "PASS: no twenty-minute stretch producing nothing.\n"
 "3. When it finishes, check the Artifacts page.\n"
 "PASS: the phase's documents are all there.\n"
 "4. CONTROL CHECK - trigger an IMPLEMENTATION phase.\n"
 "PASS: it still writes real code, commits and pushes. Build must NOT have been sandboxed by "
 "mistake - if implementation can no longer write files, that is a serious failure of this row.\n"
 "FAIL: a planning run that produces nothing for twenty minutes, or a build that can no longer "
 "write code."),

64: ("DURING A RUN",
 "The UX Design phase failed the moment it started, saying the AI engine could not be found - even "
 "though the engine was installed and every other phase ran fine. The real cause was that this "
 "agent's instructions are unusually large (about 36,000 characters) and were being passed on the "
 "command line, which Windows caps at about 32,000. Windows refused to start the process and the "
 "error was reported as 'not found'.",
 "The instructions are now delivered as a FILE rather than on the command line, so there is no size "
 "limit for any agent. (The first attempt at this used a file the engine does not automatically "
 "read, which fixed the crash but meant the instructions still never reached the model - that "
 "second problem is S.No 65. Both are now resolved by the same file-based delivery.)",
 "1. Trigger the UX DESIGN phase on a work item that has its upstream phases done.\n"
 "PASS: it STARTS. No 'Claude Code not found' error, and no immediate failure.\n"
 "2. Let it run to completion.\n"
 "PASS: it produces its wireframe documents.\n"
 "3. Try the other large phases too - Architecture, Security, Code Review, Testing, Implementation "
 "and Task Breakdown.\n"
 "PASS: all of them start.\n"
 "FAIL: any phase failing at launch with an engine-not-found message.\n"
 "NOTE: this matters most on WINDOWS. If your team runs the companion on Windows, that is the "
 "important environment to test."),

65: ("DURING A RUN",
 "Seven of the sixteen agents were running WITHOUT their role instructions or their project "
 "context. The interim fix for S.No 64 had moved large instruction sets into a file the engine does "
 "not automatically read, and a sandboxed planning agent has no way to read files - so for every "
 "large agent the instructions reached the model through NO channel at all. The composed project "
 "briefing had the same problem. The result was generic or empty output from agents built to do "
 "specialist work - including Implementation and Task Breakdown.",
 "The agent's instructions AND the full project briefing are now delivered as a genuine system "
 "prompt through a file the engine really does read. Size-independent, so it works for any agent, "
 "and it is the strongest form of instruction available. The project briefing - including its rules "
 "section - reaches the model properly for the first time.",
 "This is judged by OUTPUT QUALITY, so compare against what the phase used to produce.\n"
 "1. Run UX DESIGN on a work item with its upstream phases complete.\n"
 "PASS: the output is role-appropriate - real wireframes and design work, not generic prose that "
 "could have come from any assistant.\n"
 "2. Read the output for evidence it knew the project.\n"
 "PASS: it references your project's actual profile, constraints and earlier phases - not generic "
 "placeholders.\n"
 "3. Repeat for ARCHITECTURE and TASK BREAKDOWN.\n"
 "PASS: same - specific to your project.\n"
 "4. Check that any project constraint you entered in the Project Profile is genuinely respected in "
 "the output.\n"
 "PASS: it is.\n"
 "FAIL: output that ignores your project entirely, or reads like a generic template."),

66: ("DURING A RUN",
 "A phase failed part-way through with 'Run failed - Unknown message type: rate_limit_event', even "
 "though the agent and the machine were both healthy. The AI engine had sent a routine notification "
 "the platform's library did not recognise, and it treated the unknown message as fatal. It could "
 "strike ANY phase, at random.",
 "Message handling is now tolerant: an unrecognised notification is ignored harmlessly instead of "
 "killing the run, while genuinely malformed messages still raise properly so real errors are not "
 "hidden. It tolerates any future unknown notification, not just this one.",
 "This one cannot be triggered on demand - it depends on the AI engine choosing to send a "
 "notification. Treat it as a WATCH ITEM across your whole test pass.\n"
 "1. Over all the phase runs you do while testing this sheet, watch for any run that fails with a "
 "message containing 'Unknown message type'.\n"
 "PASS: you never see one.\n"
 "2. It is most likely on LONG runs and when the engine is under heavy use, so your longest runs "
 "are the best evidence.\n"
 "FAIL: any run failing with 'Unknown message type: ...' - record the exact message.\n"
 "NOTE: mark this Pass only at the END of your testing, once you have several long runs behind "
 "you. A single short run proves nothing here."),

69: ("DURING A RUN",
 "The UX Design phase ran for about fifteen minutes and registered NOTHING. The agent generated its "
 "screens fine but could not read its own project context: as earlier phases piled up documents, "
 "the context call was returning the FULL content of up to fifty of them at once - responses of "
 "400,000 characters and more - which is far beyond what the engine can accept, so every call "
 "failed. The agent then improvised shortened ids and those failed too.",
 "The context and listing calls now return POINTERS ONLY - small pieces of information about each "
 "document - and the actual content is fetched on demand, one document at a time. Measured on the "
 "real project: one listing dropped from 401,397 characters to 20,725, and the context call from "
 "420,594 to 35,702. The read calls also now return a clear 'pass the full id' message instead of a "
 "server error when given a shortened one.",
 "SET UP: this needs a MATURE project - several phases already complete with a good pile of "
 "documents. On a brand-new project the bug could not occur.\n"
 "1. On a project with Ideation, Requirements, PRD and Architecture all complete, trigger UX "
 "DESIGN.\n"
 "2. Watch the run console.\n"
 "PASS: the agent reads its context successfully and gets on with the work.\n"
 "PASS: it registers documents as it goes.\n"
 "3. Let it complete.\n"
 "PASS: its documents are on Artifacts & Traceability and preview correctly.\n"
 "4. Try TASK BREAKDOWN on the same project - it reads even more upstream material.\n"
 "PASS: same.\n"
 "FAIL: a long run that registers nothing; a run that loops; or a failure mentioning a token or "
 "size limit."),

71: ("DURING A RUN",
 "The Task Breakdown agent's instructions told it to fetch the earlier phases' documents with a "
 "tool that no longer returns document content - it returns only pointers. As written, the agent "
 "would receive nothing to work from and would either stall or invent a backlog.",
 "Both references in the agent's instructions were corrected to the tool that actually returns "
 "content, with a note that the other one returns pointers only.",
 "SET UP: a project with PRD, Requirements, Architecture and UX Design all complete.\n"
 "1. Trigger TASK BREAKDOWN.\n"
 "2. Let it complete and open the backlog it produced.\n"
 "PASS: the epics, stories and tasks clearly derive from YOUR project's actual PRD and "
 "requirements - you can trace items back to features you recognise.\n"
 "PASS: nothing reads like a generic invented backlog.\n"
 "3. Check the wireframes were used too - tasks that build screens should reference the real "
 "screens from UX Design.\n"
 "PASS: they do.\n"
 "4. Check the run did not stall.\n"
 "PASS: it completed in a reasonable time and registered its four planning documents.\n"
 "FAIL: an invented backlog with no relationship to your project, or a run that stalls reading its "
 "inputs."),

80: ("DURING A RUN",
 "The same problem as S.No 71, but across the whole suite: the project briefing told EVERY agent to "
 "fetch document content with the pointer-only tool, and fifteen of the sixteen agent instruction "
 "sets repeated it. Earlier phases had appeared to work only because they ran before the change; a "
 "fresh end-to-end run would put every phase under the new rules and hit the failure.",
 "All twenty-seven references were swept to the correct content-fetching tool - the briefing "
 "generator plus the fifteen agent instruction sets. Verified that none remain.",
 "This is the FRESH END-TO-END check, and it is the strongest single test in this sheet.\n"
 "1. Create a BRAND-NEW project and work item - not one that already has history.\n"
 "2. Run every planning phase in order: Ideation, Requirements, PRD, Architecture, UX Design, Task "
 "Breakdown, approving each gate as you go.\n"
 "PASS: EVERY phase reads its upstream inputs successfully.\n"
 "PASS: each phase's output clearly builds on the one before - the PRD reflects the requirements, "
 "the architecture reflects the PRD, and so on.\n"
 "PASS: no phase stalls, and no phase produces content that ignores what came before.\n"
 "3. Pay particular attention to the LATER phases, where the most upstream material has to be read.\n"
 "FAIL: any phase that cannot read its inputs, stalls, or invents content unrelated to the earlier "
 "phases."),

82: ("DURING A RUN",
 "The Task Breakdown agent was told 'the platform persists the bodies' - but the platform does not; "
 "it stores pointers, and the agent must hand over each document explicitly. Task Breakdown had no "
 "instructions for doing that (UX Design had three such steps; Task Breakdown had none). So its "
 "four full deliverables risked not being saved at all - at best one would show and the rest would "
 "be empty.",
 "The agent's instructions gained a 'how bodies are persisted' protocol mirroring UX Design's: each "
 "of the four full documents - the backlog, the sprint plan, the definition of done and the "
 "dependency map - is handed over one at a time and then registered with the reference that came "
 "back.",
 "1. Run TASK BREAKDOWN to completion.\n"
 "2. Open Artifacts & Traceability and find that run's documents.\n"
 "PASS: all FOUR are there - backlog, sprint plan, definition of done, dependency map.\n"
 "3. Open the PREVIEW of each one in turn.\n"
 "PASS: every one of the four has real content. None is blank or 'no body to preview'.\n"
 "4. Read each briefly.\n"
 "PASS: real, substantial content, not a one-line stub.\n"
 "FAIL: fewer than four documents, or any of them empty when previewed."),

83: ("DIRECT",
 "Clicking 'Implementation' on a work item started the WRONG kind of run. Build phases must run "
 "through the path that creates a code branch, commits, pushes and opens a pull request - but every "
 "phase went through the planning path, which is sandboxed and cannot write code at all. So "
 "clicking Implementation could never produce any code. The same applied to CI/CD and Test "
 "Automation.",
 "The platform now records explicitly which agents ride the build path - implementation, test "
 "automation and CI/CD - and the trigger routes them there, with everything else going to the "
 "planning path. The existing buttons work for both with no change on screen, and a future build "
 "agent only has to set the flag. A build on a task with no repository now falls back to the "
 "project's default repository.",
 "SET UP: a project with a Code host connection and at least one task ready to build.\n"
 "1. Open a TASK and click Implementation.\n"
 "PASS: a BUILD run starts - the console shows worktree, commit and push activity, and a pull "
 "request eventually opens on GitHub.\n"
 "FAIL: it runs like a planning phase, produces a document, and no code or pull request appears "
 "anywhere.\n"
 "2. Trigger TEST AUTOMATION on a suitable item.\n"
 "PASS: also a build run - it commits a test script and opens a pull request.\n"
 "3. Trigger CI/CD.\n"
 "PASS: also a build run.\n"
 "4. CONTROL CHECK: trigger a PLANNING phase (Task Breakdown, Testing, Security, Deployment).\n"
 "PASS: those still run as planning phases and open a review gate - they must NOT try to open a "
 "pull request."),

150: ("DIRECT",
 "On Phases & Runs every work item in the project was listed in one plain dropdown. With fifty-odd "
 "items, finding yours meant scrolling and squinting. The team asked for search inside the dropdown "
 "itself.",
 "A searchable picker was built: type to filter the list in the dropdown, arrow keys move, Enter "
 "picks, Esc closes and reverts, clicking outside closes. It uses the standard accessibility roles "
 "so a screen reader announces it properly, it looks identical to the other controls, and it says "
 "'No work items match' rather than showing an empty box.",
 "SET UP: a project with many work items - twenty or more makes the difference obvious.\n"
 "1. Open Phases & Runs and click the work-item picker.\n"
 "PASS: you can TYPE into it.\n"
 "2. Type part of a work item's title.\n"
 "PASS: the list narrows as you type.\n"
 "3. Type something that matches nothing.\n"
 "PASS: it says 'No work items match' - not a blank box.\n"
 "4. Clear it, then use the ARROW keys to move down the list and press Enter.\n"
 "PASS: that item is selected.\n"
 "5. Open it again, type something, then press Esc.\n"
 "PASS: it closes and goes back to what was selected before.\n"
 "6. Open it and click somewhere else on the page.\n"
 "PASS: it closes.\n"
 "7. Close it and look at the control.\n"
 "PASS: it shows the currently selected work item, and looks like the other inputs on the page.\n"
 "KNOWN ISSUE, NOT A FAILURE OF THIS ROW: with only a few items the dropdown can be clipped at the "
 "panel edge - that is S.No 166, still open."),

163: ("DURING A RUN",
 "The platform promises a person is always in the loop and it never silently assumes. But the "
 "agents sorted every gap in their knowledge into three tiers and only ever ASKED about tier 1. "
 "Tier 2 - the agent's own suggestions - was written inside the document, and tier 3 - "
 "industry-standard assumptions - was recorded silently where the user never saw it. So you could "
 "not confirm or overrule the agent's tier 2 and 3 choices, and the 'no silent assumptions' promise "
 "was only partly true.",
 "The agent now brings ALL THREE tiers into ONE clarifications gate before starting work, each "
 "question tagged with its tier. Tier 1 stays required; tiers 2 and 3 are optional and carry the "
 "agent's PROPOSED ANSWER pre-filled as a suggestion you can accept, edit or overrule, with an "
 "'Accept all' in one click. Anything you leave untouched falls back to the suggestion, and the "
 "confirmed tier-3 values are still recorded as assumptions for the record. The gate groups the "
 "questions under tier headings.",
 "1. Trigger IDEATION on a new work item and wait for the clarifications gate.\n"
 "2. Look at the shape of the page.\n"
 "PASS: questions are grouped under Tier 1, Tier 2 and Tier 3 headings.\n"
 "PASS: there are questions in more than one tier - not tier 1 only.\n"
 "3. Read a TIER 2 or TIER 3 question.\n"
 "PASS: it comes with the agent's own proposed answer already filled in as a suggestion.\n"
 "PASS: it is marked optional.\n"
 "4. Edit one tier-3 suggestion to something different.\n"
 "5. Look for an 'Accept all' control.\n"
 "PASS: it is there and accepts the remaining suggestions in one click.\n"
 "6. Submit and let the phase run.\n"
 "PASS: the phase uses YOUR edited value, not the agent's original suggestion.\n"
 "7. Open the run's Assumptions document.\n"
 "PASS: the confirmed tier-3 values are recorded there.\n"
 "FAIL: only tier-1 questions appear; no suggestions pre-filled; or your edit is ignored."),

172: ("DIRECT",
 "The Run Console showed bare identifiers with no labels - the run's id, the workflow id, the "
 "engine - and never said WHICH WORK ITEM the run belonged to. If you triggered a phase on work "
 "item 10 and went to the console, you had no way to confirm the right thing was running.",
 "The header now leads with the work item's key and title so you can confirm at a glance, and there "
 "is a properly labelled row - Work item / Run ID / Engine / Workflow - with the long values "
 "shortened and the full value on hover. The identifiers are kept, now labelled, because the team "
 "asked to keep them for debugging.",
 "1. Note a work item's key and title, e.g. 'WI-10 - Add expense filtering'.\n"
 "2. Trigger a phase on it and open the Run Console.\n"
 "3. Read the header.\n"
 "PASS: it names WI-10 and its title. You can confirm the right item is running WITHOUT checking "
 "anywhere else.\n"
 "4. Read the meta row below.\n"
 "PASS: every value has a LABEL - you can tell what each one is.\n"
 "PASS: long identifiers are shortened, with the full value shown on hover.\n"
 "5. Trigger a phase on a DIFFERENT work item and open its console.\n"
 "PASS: the header names that item instead - it is not stuck on the first one.\n"
 "FAIL: unlabelled identifiers, or no way to tell which work item is running."),

173: ("DIRECT",
 "With the companion offline, the Trigger a Phase card showed only three phases as greyed "
 "placeholders instead of the full list - so you could not even see what phases exist. And the Runs "
 "card kept showing a label on the right that was not needed while offline. (The team also asked "
 "what that label actually was: it is the currently SELECTED work item's title, not a 'most recent "
 "run'.)",
 "The offline Trigger card now shows the FULL phase list, greyed and non-interactive, so you can "
 "see every phase that exists; they become clickable once the machine is connected. The Runs-card "
 "right-side label is hidden when offline and shown only when online, by team decision.",
 "1. Make sure your companion is NOT running.\n"
 "2. Open Phases & Runs and read the Trigger a Phase card.\n"
 "PASS: EVERY phase is listed - Ideation through Deployment - all greyed out and not clickable.\n"
 "FAIL: only three phases shown.\n"
 "3. Look at the right-hand side of the Runs card.\n"
 "PASS: no work-item label is shown while offline.\n"
 "4. Now start your companion and wait for Ready.\n"
 "PASS: the phases become clickable.\n"
 "PASS: the work-item label reappears on the right of the Runs card, and it matches the work item "
 "you have SELECTED."),

190: ("DURING A RUN",
 "The briefing each agent receives kept only the 50 newest documents and then trimmed those to the "
 "top 20, purely by how recent they were, with no awareness of what the agent actually needs. On a "
 "mature project the oldest-but-essential documents - the architecture, say - were pushed out by "
 "newer ones, so a late phase might never receive the exact inputs its own instructions tell it to "
 "read. A definite, silent loss affecting every agent.",
 "Each agent now DECLARES the document types it needs, once. Those are built into a guaranteed tier "
 "that is always included and can never be pushed out by more recent material, so a late-lifecycle "
 "phase always receives the inputs its instructions name.",
 "SET UP: a MATURE project - many phases complete and a lot of documents. The bug could not happen "
 "on a fresh project.\n"
 "1. On a project that has run through to Task Breakdown or beyond, trigger a LATE phase - CI/CD, "
 "Deployment, Security or Testing.\n"
 "2. Read its output closely.\n"
 "PASS: it clearly reflects the ARCHITECTURE and the earlier decisions, even though those documents "
 "are among the oldest on the project.\n"
 "PASS: it does not contradict, ignore or reinvent a decision that was already made.\n"
 "3. Look for anything in the output saying it could not find an input it needed.\n"
 "PASS: nothing of the kind.\n"
 "FAIL: a late phase that plainly has not seen the architecture, or that reinvents something "
 "already decided.\n"
 "NOTE: judge this on OUTPUT QUALITY. It is a fair one to mark as 'looks right' with a comment "
 "rather than a hard pass."),

191: ("DURING A RUN",
 "If a document an agent needed was not already in its briefing, the agent had no precise way to go "
 "and get it - the listing tool could not filter by document TYPE, so 'fetch the architecture "
 "document' was not expressible. It had to scan by recency and guess. Without this, the guaranteed "
 "briefing tier (S.No 190) had no reliable fallback.",
 "The listing now takes a type filter, so an agent can pull a specific upstream document on demand "
 "and then read it. The briefing also instructs agents to use it for anything not already provided. "
 "That completes the design: push what is needed, and let the agent pull anything else.",
 "This is the fallback half of S.No 190 and is not directly visible on screen. Judge it by "
 "behaviour on a mature project.\n"
 "1. On a project with many documents, run a late phase.\n"
 "PASS: the output correctly reflects specific upstream documents, including ones unlikely to be in "
 "the recent set.\n"
 "2. Watch the run console for signs the agent went and fetched something.\n"
 "PASS: no error about a document it could not find or could not read.\n"
 "3. Check no run fails with a server error while reading a document.\n"
 "PASS: none.\n"
 "FAIL: a run that reports it could not obtain an input it needed, or that errors while fetching "
 "one. Test alongside S.No 190 and record one result for both if that is easier."),

226: ("DURING A RUN",
 "Sometimes - not always - Ideation skipped the clarification questions entirely. Instead of "
 "opening the questions gate, the run went straight to a review gate holding ONE document whose "
 "content WAS the questions, ending 'I will not produce or register any artifact until you answer "
 "them'. The same code produced a correct gate on other runs, which is why it was chased as a "
 "prompt problem for days. Two developers reported it independently.",
 "The cause was that the AI engine's newer versions hold some tools back from the agent's starting "
 "context to save space, and load them back only through one particular mechanism - which the "
 "platform had on its blocked list, added long before the engine used it that way. So granting the "
 "agent its tools guaranteed nothing: whatever the engine had held back was permanently invisible. "
 "Proof came from the run itself, where the agent said the tools for asking and registering were "
 "not present while successfully using the reading tools in the same run. It was intermittent "
 "because what the engine holds back varies run to run. The mechanism was removed from the blocked "
 "list and added to the allowed lists; the sandbox is NOT widened, because it only returns "
 "descriptions of tools the agent already has.",
 "This is the single most important run-level check in this sheet, and it is INTERMITTENT - so run "
 "it several times.\n"
 "1. Create a new work item and trigger IDEATION.\n"
 "2. Wait for it to reach a gate.\n"
 "PASS: the CLARIFICATIONS gate opens with real tiered questions.\n"
 "FAIL: it goes straight to a REVIEW gate holding a single document whose content is the questions "
 "themselves.\n"
 "3. Answer the questions and let the phase complete.\n"
 "PASS: it registers its full set of Ideation documents - roughly seven of them (ideation, "
 "feasibility, stakeholder map, success metrics, market sizing, competitive analysis, "
 "assumptions) - not one.\n"
 "4. REPEAT THIS AT LEAST THREE TIMES on different work items. Because it was intermittent, one "
 "good run is not proof.\n"
 "PASS: all three behave the same.\n"
 "FAIL: even ONE run that skips the questions. Record which run, and the exact document you got."),

227: ("DURING A RUN",
 "The safety net behind S.No 226, and the reason that bug survived for weeks. When the agent's "
 "tools were unreachable, the platform still filed the agent's closing message as though it were "
 "the phase's deliverable and opened a normal review gate on it - so a completely failed run looked "
 "like a successful one. Nothing ever failed visibly, and a reviewer would have approved a document "
 "containing the agent's own questions.",
 "The platform's own copy of a closing message is now marked as such, and the completeness check "
 "requires at least ONE document the AGENT actually registered. If the only thing on record is the "
 "platform's copy, the run FAILS with a message naming what to check, and NO gate opens. The bar was "
 "set from evidence: across 47 successful runs spanning 13 phases the minimum was always two "
 "documents; the failed run had exactly one. Replayed against every past successful run - 49 pass, "
 "none broken.",
 "1. Run several planning phases normally.\n"
 "PASS: none of them is wrongly failed by this check. That is the first thing to confirm - the "
 "guard must not fire on healthy runs.\n"
 "2. If you ever DO hit the S.No 226 problem (a run where the agent cannot reach its tools):\n"
 "PASS: the run FAILS with a clear reason naming what to check.\n"
 "PASS: NO gate opens on it.\n"
 "PASS: you are NOT presented with an approvable document containing the agent's questions.\n"
 "3. Look at Artifacts & Traceability after any failed run.\n"
 "PASS: anything the platform filed itself is clearly marked as run output rather than a "
 "deliverable (see S.No 232).\n"
 "FAIL: a healthy run wrongly failed - or a failed run that still opens an approvable gate."),

228: ("DURING A RUN",
 "The briefing given to every run is built in seven sections, each with a size limit. Two sections "
 "were over their limit on an ordinary project, so real content was cut - including the end of the "
 "user's OWN project constraints and the tail of the agent's operating rules. Nothing logged it and "
 "nothing showed it, so the only symptom was an agent that seemed to have forgotten something. "
 "Measured on a live run: the project section stopped mid-sentence inside the user's constraints at "
 "'Authentication: Email + password only. No OTP, no'. The whole briefing was under 2% of what the "
 "model can hold, so a document with no size problem was being cut.",
 "The limits were raised where the content is authored by us and left alone where it grows without "
 "bound. Cutting now happens at a line boundary rather than mid-word, and a record is written "
 "naming any section that was cut, so it can never be silent again.",
 "SET UP: fill your Project Profile properly - a long, detailed 'Constraints' and 'Important "
 "context', several hundred words each. A sparse profile will not exercise this.\n"
 "1. Write a distinctive sentence at the very END of your Constraints field - something you will "
 "recognise, e.g. 'All dates must be shown in the user's local timezone.'\n"
 "2. Save the profile and run a planning phase.\n"
 "3. Read the phase's output for evidence it saw that final constraint.\n"
 "PASS: the constraint is respected or referenced. It was not cut off.\n"
 "4. Read the whole output for signs the agent missed a rule it should have followed.\n"
 "PASS: none.\n"
 "5. Look at the run console for any note about the briefing being shortened.\n"
 "PASS: either none, or one that NAMES the section - never a silent cut.\n"
 "FAIL: your last constraint is ignored, or a cut is reported with no indication of what was lost."),

229: ("DURING A RUN",
 "Hardening found while investigating S.No 226. The companion starts the process that provides "
 "EVERY tool an agent has, and it was passing that process's whole configuration on the command "
 "line, with only seven environment values. Two real risks: on Windows a command line is capped at "
 "about 32,000 characters (the same ceiling that caused S.No 64), and a command line is READABLE BY "
 "ANY USER from a process list - so the configuration published the machine's access token. Also, "
 "handing a process only seven environment values can stop Python starting on Windows at all.",
 "The environment is now inherited from the machine and then overlaid with the seven values, and "
 "the whole configuration is written to a temporary FILE whose path goes on the command line - the "
 "same shape already adopted for the agent's instructions. The file is deleted on every exit path, "
 "because it carries the token. Applied to both the planning and the build paths. Measured: the "
 "command line went from 6,708 characters to 59.",
 "Best tested on WINDOWS, where the original risk lives.\n"
 "1. Trigger a PLANNING phase with your companion running.\n"
 "PASS: it starts and runs normally.\n"
 "2. Trigger a BUILD phase.\n"
 "PASS: same.\n"
 "3. While a phase is running, open Task Manager (Details tab, with the Command line column shown) "
 "or run: wmic process get commandline\n"
 "PASS: the command line for the platform-state process is SHORT - a file path, not a long block of "
 "configuration.\n"
 "PASS: NO access token is visible in any command line.\n"
 "4. After the run finishes, check the temporary folder.\n"
 "PASS: the configuration file has been deleted.\n"
 "FAIL: a token visible in a process list, a leftover file, or a phase that will not start.\n"
 "If reading process command lines is not something you want to do, run steps 1-2 only and mark it "
 "partially tested - say so in your comment."),

231: ("DURING A RUN",
 "A single momentary error while waiting for you to answer a clarification killed the whole wait. "
 "The agent then carried on with no answers - and, obeying its own rule not to produce anything "
 "before the answers come back, registered nothing and closed with a status message, which the "
 "platform then filed as the phase's document. The clarification was still sitting on the "
 "Clarifications screen, unanswered and now pointless.",
 "The waiting now distinguishes a temporary failure from a permanent one. Temporary problems - a "
 "momentary server error, a dropped connection - are retried; genuine refusals fail fast. Any "
 "successful check resets the clock, and it gives up only after fifteen minutes of continuous "
 "failure. Creating the clarification is retried too, since a failed create means the question "
 "never exists at all. Safe because waiting costs nothing - the model is idle on an open question.",
 "SET UP: you need a clarification pending, and the ability to interrupt the connection briefly.\n"
 "1. Trigger a phase and wait for the clarification questions to appear. Do NOT answer yet.\n"
 "2. Briefly interrupt the connection between the companion and the app - restart the backend, or "
 "disconnect the network for about thirty seconds.\n"
 "3. Restore it and watch the companion's terminal.\n"
 "PASS: it logs retries and keeps waiting. It does NOT give up.\n"
 "4. Now answer the clarification.\n"
 "PASS: the phase picks up your answers and carries on to produce its real documents.\n"
 "5. Check Artifacts & Traceability.\n"
 "PASS: real phase documents - NOT a single document containing a status report.\n"
 "FAIL: the agent gave up on one blip; or the phase completed with a status message instead of its "
 "deliverables.\n"
 "If you cannot safely interrupt the connection, do steps 1 and 4 only (the normal path) and say so "
 "in your comment."),

233: ("DURING A RUN",
 "When a run stopped because nothing had been registered, the message blamed the agent's writing "
 "tools - even when those tools had worked perfectly and something else had failed. In the run this "
 "was found on, the tools were fine and the question-asking had broken, so the message sent the "
 "reader hunting the wrong thing while the real evidence - a clarification sitting unanswered on "
 "the run - went unmentioned.",
 "The message is now derived from the evidence rather than asserting a remembered cause. If there "
 "is an unanswered clarification on the run, the message NAMES it, says plainly that this is not a "
 "tooling failure, and points at the recovery that actually works: answer it, then re-run - because "
 "answered clarifications carry into the new run. With no pending clarification, the original "
 "wording is unchanged.",
 "SET UP: you need a run that stops on the completeness check WITH an unanswered clarification on "
 "it. Trigger a phase, wait for the questions, and then LEAVE THEM UNANSWERED long enough for the "
 "run to end.\n"
 "1. Once the run has stopped, open the Run Console and read the failure reason.\n"
 "PASS: it NAMES the unanswered clarification.\n"
 "PASS: it says plainly that this is not a problem with the agent's tools.\n"
 "PASS: it tells you to answer the question and re-run.\n"
 "FAIL: it blames the agent's write tools, or the missing register step, when a clarification is "
 "plainly sitting there unanswered.\n"
 "2. Follow the advice: answer the clarification, then re-run the phase.\n"
 "PASS: the new run picks up your answers and completes."),

234: ("DIRECT",
 "The Clarifications screen said 'Answering resumes the run in the same session' and showed 'Paused "
 "- waiting for your answer'. Once the run had actually ENDED, both were false: there was nothing "
 "left to resume, so a person answered and then waited for something that could never happen.",
 "The screen now knows whether the run is still listening. If it has ended it says so, and explains "
 "that answering STILL HELPS because your answers carry into the next run. The clarification "
 "deliberately stays answerable and nothing is cancelled - the obvious fix of cancelling an orphaned "
 "question would have destroyed the one recovery that works.",
 "SET UP: a clarification whose run has ENDED. Trigger a phase, wait for the questions, then let "
 "the run end without answering.\n"
 "1. Open Clarifications and find that question.\n"
 "PASS: the screen says the run has ENDED.\n"
 "PASS: it explains that answering still helps because your answers will be used on the next run.\n"
 "PASS: it does NOT claim answering will resume the run.\n"
 "2. Check you can still answer it.\n"
 "PASS: the question is still answerable - it was not cancelled or greyed out.\n"
 "3. Answer it, then re-run the phase.\n"
 "PASS: the new run uses your answers - it does not ask the same questions again.\n"
 "4. CONTROL CHECK: with a run genuinely still RUNNING, open its clarification.\n"
 "PASS: THAT one correctly says answering resumes the run.\n"
 "FAIL: an ended run still promising to resume, or an orphaned question you can no longer answer."),

251: ("DURING A RUN",
 "The work item's description was cut before any agent read it - and acceptance criteria are "
 "conventionally written at the END, which is exactly the part a cut removes. So a build agent "
 "could work from a description whose acceptance criteria had silently vanished, produce plausible "
 "code that misses the actual requirement, and nothing downstream could tell, because the criteria "
 "it would have been checked against were gone too. Measured on a real task, the section was "
 "already at 56% of its limit on an ordinary item; descriptions imported from Jira can run to "
 "32,767 characters.",
 "The description is now rendered WHOLE, outside the size limit, so it can never be cut. The "
 "metadata lines around it are still capped. When the whole thing fits, the briefing is "
 "byte-for-byte what it was before - and there is a test asserting that rather than assuming it. "
 "This is HALF the fix for S.No 243 (the CORS requirement that shipped unbuilt); the other half is "
 "the per-criterion verdict the review agent must now produce.",
 "SET UP: a task with a LONG description whose acceptance criteria are at the very end. Write one "
 "deliberately, or use a long one imported from Jira. Put a distinctive, easily-checked criterion "
 "LAST - e.g. 'The page title must read Expenses Overview.'\n"
 "1. Trigger IMPLEMENTATION on that task.\n"
 "2. When the build completes, check whether the LAST acceptance criterion was implemented.\n"
 "PASS: it was. The agent saw the end of the description.\n"
 "3. Read the code review's verdict.\n"
 "PASS: it lists that last criterion among the ones it checked (see S.No 243).\n"
 "4. Repeat with an even longer description - a few thousand words.\n"
 "PASS: the last criterion is still honoured.\n"
 "FAIL: the final criterion is silently ignored while the earlier ones are delivered. That is "
 "exactly the failure this row exists to prevent."),

}
