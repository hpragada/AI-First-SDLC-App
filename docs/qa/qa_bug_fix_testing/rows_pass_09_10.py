# -*- coding: utf-8 -*-
"""Passes 9-10: artifacts, traceability, what the agents write; gates and approvals."""

ROWS = {

22: ("DIRECT",
 "After a phase had run, its documents were listed on Artifacts & Traceability but Preview did not "
 "work - it returned 'artifact has no body to preview' even though the text was plainly there. The "
 "team also asked whether the object store was working at all.",
 "The preview now also reads a draft's text from where the agent actually left it, when nothing has "
 "been staged to the object store yet, and picks the right content type from the draft's declared "
 "format. Nothing is copied or moved - it is read where it already lives. On the object store: it "
 "is up and healthy, and documents that DO have a stored file still preview from it. Both paths "
 "work.",
 "1. Run any planning phase to completion.\n"
 "2. Open Artifacts & Traceability and find its documents.\n"
 "3. Click Preview on EACH of them.\n"
 "PASS: every one opens and shows real content.\n"
 "FAIL: any 'artifact has no body to preview' or 'Artifact not found'.\n"
 "4. Try an OLD document from a run done before this fix.\n"
 "PASS: it previews too - no data migration was needed.\n"
 "5. Try documents from several DIFFERENT phases.\n"
 "PASS: all preview."),

23: ("DIRECT",
 "On Artifacts & Traceability the search box and the Phase, Type and Status filters did nothing, "
 "and the filter dropdowns had no options to choose from.",
 "Search and all three filters now work. Search matches on the document's type and phase; the "
 "dropdowns are filled from the documents actually present, with readable labels; the filters "
 "combine; and a combination that excludes everything says 'No artifacts match these filters' "
 "rather than looking broken.",
 "SET UP: a project with documents from several phases.\n"
 "1. Open Artifacts & Traceability and type into the search box.\n"
 "PASS: the list narrows as you type.\n"
 "2. Clear it and open the PHASE dropdown.\n"
 "PASS: it lists real phases that exist here, with readable names - not empty, not raw keys.\n"
 "3. Pick one.\n"
 "PASS: only that phase's documents remain.\n"
 "4. Repeat for TYPE and STATUS.\n"
 "5. Combine two filters that cannot both be true.\n"
 "PASS: 'No artifacts match these filters' - a clear message, not a blank page.\n"
 "6. Clear everything.\n"
 "PASS: the full list returns.\n"
 "FAIL: an inert control, or an empty dropdown."),

27: ("DIRECT",
 "Two problems. The generated documents are written in Markdown, but the preview showed the raw "
 "source in a plain text box - so headings, tables and any architecture diagram were unreadable. "
 "And re-running the same phase created a SECOND document still labelled version 1 instead of "
 "version 2, with the version history showing v1 twice.",
 "The preview now renders Markdown properly - headings, lists, tables, code - and diagrams written "
 "as mermaid blocks are drawn as actual diagrams instead of shown as text. A newly registered "
 "document now takes the next version number after the highest existing one, so re-running a phase "
 "gives v2, v3 and so on.",
 "1. Run a phase that produces a document with headings, a table and ideally a diagram - "
 "Architecture is the best one.\n"
 "2. Preview it.\n"
 "PASS: headings look like headings; the table is laid out as a table; code is in a code style.\n"
 "PASS: any diagram is DRAWN as a diagram, not shown as text starting with 'graph TD'.\n"
 "PASS: no stray # characters, ** or | pipes.\n"
 "3. Now RE-RUN the same phase on the same work item and let it finish.\n"
 "4. Look at that document type on the Artifacts page.\n"
 "PASS: the new one is version 2.\n"
 "5. Open the preview and check the version history.\n"
 "PASS: it lists both v2 and v1 - not v1 twice.\n"
 "FAIL: raw Markdown on screen, a diagram shown as text, or two documents both called v1."),

59: ("DIRECT",
 "Two compounding problems. Preview failed with 'Artifact not found' after a long spinner, because "
 "the step that stores the phase's text skipped itself whenever the agent had already registered a "
 "document of that type - so the text was never written anywhere and NO document of the run had a "
 "body at all. And export: automatic export to Confluence only ever covered a few document types, "
 "and the manual Publish button was a stub that flipped a status and made up a link without ever "
 "contacting Confluence.",
 "Preview now always works: the phase's text is always stored, the agent's document is filled in "
 "with the reference, and preview falls back through several places to find a body, with the "
 "storage read guarded so a missing file degrades rather than erroring. On export, both answers are "
 "now yes: after gate approval the mapped document types export to your connected Confluence "
 "automatically, and the manual push genuinely calls Confluence, honours the space, records the "
 "real page id and link, and allows re-export of documents that were published internally before a "
 "connector existed.",
 "SET UP: Confluence connected, with a space you can write to.\n"
 "PART A - PREVIEW\n"
 "1. Run a phase and preview EVERY document it produced.\n"
 "PASS: all open with real content, and quickly - no long spinner ending in 'Artifact not found'.\n"
 "2. Try documents from an OLDER run too.\n"
 "PASS: they preview as well.\n"
 "PART B - EXPORT\n"
 "3. Approve a gate for a phase producing a document type mapped to the document store "
 "(requirements, PRD, architecture or an ADR).\n"
 "PASS: it exports to Confluence automatically. Open the link and confirm the page exists in YOUR "
 "space.\n"
 "4. Find a document that is NOT auto-exported and use the manual Publish action.\n"
 "PASS: a real Confluence page is created, and the returned link opens it.\n"
 "PASS: the recorded reference is a real page id, not an invented one.\n"
 "5. Find a document that published internally BEFORE Confluence was connected, and publish it "
 "again now.\n"
 "PASS: allowed, and it reaches Confluence.\n"
 "FAIL: an invented link, a page that does not exist, or a preview that 404s."),

67: ("DIRECT",
 "Some documents could not be previewed - 'artifact has no body to preview' - even though they "
 "clearly had content, which blocked reviewing and approving the gate. The content of many planning "
 "sub-documents (assumptions register, user journeys, stakeholder map, accessibility spec) is "
 "structured data rather than prose, and the preview had no way to display that.",
 "A general renderer turns any structured content into readable text - a title heading, labelled "
 "fields, lists as bullets, and lists of records as titled sections - and a sub-document's OWN "
 "content is preferred over the whole phase document, so it previews itself rather than its parent. "
 "Internal reference fields are excluded so no raw identifiers leak into what you read.",
 "1. Run a planning phase that produces several sub-documents - Ideation is ideal (assumptions "
 "register, stakeholder map, success metrics, market sizing, competitive analysis).\n"
 "2. Preview EVERY document, including the small sub-documents.\n"
 "PASS: every one opens with readable content.\n"
 "FAIL: any 'no body to preview'.\n"
 "3. Read a structured one, e.g. the stakeholder map.\n"
 "PASS: it reads as a proper document - a title, labelled fields, bullets - not a run-on blob of "
 "brackets and quotes.\n"
 "PASS: NO long internal identifiers appear in the text.\n"
 "4. Check a sub-document shows ITS OWN content.\n"
 "PASS: previewing the stakeholder map shows the stakeholder map, not the whole phase document."),

68: ("DURING A RUN",
 "The UX Design agent generated about twenty-five full screen designs exactly as instructed, but "
 "they were never saved - each design document ended up holding only a short written description. "
 "The rendered screens were effectively lost, so nobody could preview them and the implementation "
 "phase had nothing to work from. There was simply no way for an agent to hand a large document to "
 "the platform.",
 "The missing capability was added: an agent can now hand over one document at a time to be stored, "
 "and gets back a reference to register. UX Design hands over each screen state and registers one "
 "design document per screen listing its states. A matching read capability lets the task-breakdown "
 "and implementation agents read the actual screen. Preview shows all the states, and the interface "
 "has a state switcher rendering each screen in an isolated frame, so you can preview and approve "
 "the real screens.",
 "SET UP: a project with Requirements, PRD and Architecture complete.\n"
 "1. Run UX DESIGN to completion.\n"
 "2. Open Artifacts & Traceability and find the wireframe documents.\n"
 "PASS: there is one per SCREEN, named for that screen - not one generic 'wireframe' row.\n"
 "3. Preview one.\n"
 "PASS: an actual RENDERED SCREEN appears - not a written description of a screen.\n"
 "4. Look for a state switcher on the preview.\n"
 "PASS: you can switch between the screen's states (default, loading, empty, error, success) and "
 "each renders.\n"
 "5. Preview several different screens.\n"
 "PASS: each shows its own design.\n"
 "6. Now run TASK BREAKDOWN and read the tasks that build screens.\n"
 "PASS: they reference the real screens, showing the design was readable downstream.\n"
 "FAIL: a wireframe document containing only prose, or a preview with nothing to look at."),

120: ("DIRECT",
 "The document names on Artifacts & Traceability were not readable. Every screen design was called "
 "'Wireframe' with no indication of WHICH screen, so a list of twenty-five was useless. The team "
 "asked for names like 'Wireframe (login-page)', and for the same to apply to what you see inside "
 "the preview.",
 "Documents now carry a real title. The registration step takes one, seven agents were taught to "
 "author human titles ('Wireframe - Login Page', 'ADR-003 - Event Sourcing', 'TC-014 - ...'), and "
 "everything that lists a document prefers the title, falling back to a readable type. A "
 "versioning collision was fixed at the same time: per-item siblings such as ADRs, test cases and "
 "security findings each start at version 1 instead of wrongly superseding one another.",
 "1. Run UX Design and Architecture on a project.\n"
 "2. Open Artifacts & Traceability and read the document names.\n"
 "PASS: each wireframe names its SCREEN - e.g. 'Wireframe - Login Page'.\n"
 "PASS: each ADR names its decision - e.g. 'ADR-003 - Event Sourcing'.\n"
 "PASS: no two rows are indistinguishable.\n"
 "3. Open a preview and read its heading.\n"
 "PASS: the same readable title.\n"
 "4. Check the Traceability graph.\n"
 "PASS: nodes show readable titles, not raw types or identifiers.\n"
 "5. Open the Export/Publish screen.\n"
 "PASS: readable titles there too.\n"
 "6. VERSIONING CHECK: on a phase that produces several ADRs or test cases, confirm each is at "
 "version 1.\n"
 "PASS: they are - one has not superseded another.\n"
 "FAIL: repeated identical names, or siblings incorrectly versioned over each other."),

121: ("DURING A RUN",
 "The Requirements agent wrote its user stories, functional requirements, acceptance criteria and "
 "non-functional requirements for an engineer - formal 'SHALL' boilerplate and bare Given/When/Then "
 "stubs - yet the person who REVIEWS them is the Product Owner. Same problem as the task breakdown "
 "one, on a different agent.",
 "The agent now has a writing standard with worked examples: lead every user story, functional "
 "requirement and acceptance criterion with ONE plain-language sentence of intent, then keep the "
 "full formal precision. The standard adds a sentence; it removes no rigour. Worked examples were "
 "included deliberately, because with agent 06 the instruction alone did not change the output.",
 "1. Run the REQUIREMENTS phase and open its documents.\n"
 "2. Read several user stories.\n"
 "PASS: each OPENS with a plain sentence saying what it is for, before the formal wording.\n"
 "3. Read several functional requirements.\n"
 "PASS: same - a plain sentence first, THEN the 'SHALL' wording. The formal wording is still "
 "there; it has not been dumbed down.\n"
 "4. Read the acceptance criteria.\n"
 "PASS: plain intent first, then the precise Given/When/Then.\n"
 "5. THE REAL TEST: hand it to someone non-technical, or read it as if you were the Product Owner.\n"
 "PASS: they can tell what is being asked for without an engineer translating.\n"
 "FAIL: bare SHALL statements with no plain-language lead - or the opposite failure, plain language "
 "that has LOST the technical precision."),

122: ("DURING A RUN",
 "The Testing agent writes acceptance-test scenarios FOR the Product Owner, plus defect reports "
 "and test-case descriptions - all to a two-engineer precision bar, with nothing requiring the "
 "Product Owner-facing material to be readable by a Product Owner.",
 "A clarity standard with worked examples, covering acceptance-test scenarios, defect reports and "
 "expected results. Deliberately kept TECHNICAL but clear, rather than plain language: a QA reader "
 "has to interpret precise detail correctly, and flattening it into everyday words causes "
 "misreading. A test pins that this register stays distinct from the Requirements agent's, so a "
 "later tidy-up cannot collapse the two into one voice.",
 "1. Run the TESTING phase and open its documents.\n"
 "2. Read the acceptance-test (UAT) scenarios - the ones written for the Product Owner.\n"
 "PASS: clear and well structured, and a business person could follow the steps.\n"
 "PASS: they still carry the precise detail a tester needs - this is deliberately NOT simplified "
 "into vagueness.\n"
 "3. Read a defect report.\n"
 "PASS: you can tell what is wrong and how to reproduce it.\n"
 "4. Read the expected results on some test cases.\n"
 "PASS: specific and checkable - not 'it works correctly'.\n"
 "FAIL: scenarios only an engineer could execute - or ones so simplified you could not actually "
 "verify them."),

123: ("DURING A RUN",
 "The Context Extractor agent writes the executive summary, health dashboard and module "
 "documentation that people read when joining a project - and had no instruction to keep any of it "
 "plain, so it was jargon-prone.",
 "It must now lead in plain language while keeping the technical nuance, give every number its "
 "MEANING rather than the bare figure, and never present an unmeasured value as zero - it must say "
 "the value is unavailable, and why. A worked example and a counter-example are included.",
 "NOTE: this is a BROWNFIELD phase - it needs a project with existing code.\n"
 "1. On a brownfield project, run the context-extraction phase.\n"
 "2. Read the Executive Summary.\n"
 "PASS: it opens in plain language. Somebody joining the project could follow it.\n"
 "3. Read the health dashboard figures.\n"
 "PASS: every number is explained - what it means and whether it is good - not a bare figure.\n"
 "4. LOOK FOR ZEROS. Find a metric shown as 0.\n"
 "PASS: if it could not be measured, it SAYS unavailable and why - it does not report zero.\n"
 "5. Read the module documentation.\n"
 "PASS: plain-language lead, technical detail kept.\n"
 "FAIL: unexplained jargon, bare numbers, or a 0 that really means 'we could not measure this'."),

124: ("DURING A RUN",
 "The Architecture agent's decision records - the context, rationale and consequences that people "
 "read to understand WHY something was decided - had no readability standard. Only the top-level "
 "diagram was required to be readable by a non-technical stakeholder.",
 "The same 'readable by a non-technical stakeholder' bar now applies to the decision records: name "
 "the constraint that forced the decision, name the alternatives that were rejected and why they "
 "lost, and state the cost accepted. A decision record whose consequences are all positive is "
 "incomplete, and whoever inherits it finds the cost the hard way.",
 "1. Run the ARCHITECTURE phase and open its decision records (ADRs).\n"
 "2. Read the CONTEXT of one.\n"
 "PASS: it names the constraint that forced the decision, in plain words.\n"
 "3. Read the RATIONALE.\n"
 "PASS: it names the alternatives considered and says why each lost.\n"
 "4. Read the CONSEQUENCES - this is the important one.\n"
 "PASS: it states a COST that was accepted, not only benefits.\n"
 "FAIL: an ADR whose consequences are all positive - that is the specific thing this fix exists to "
 "prevent.\n"
 "5. Read the Executive Summary of the architecture document.\n"
 "PASS: a non-technical stakeholder could follow it."),

125: ("DURING A RUN",
 "The PRD agent writes well overall, but the per-feature ACCEPTANCE CRITERIA were left as terse "
 "placeholders - and those criteria are copied downstream into the backlog and checked by the "
 "review agent, so vagueness there spreads.",
 "A writing standard scoped to the per-feature acceptance criteria only, since the rest of the PRD "
 "was already good. Each criterion must state an OBSERVABLE outcome someone could verify by hand; "
 "at least one per feature must cover the unhappy path; and the template scaffolding must never "
 "ship as written.",
 "1. Run the PRD phase and open the PRD.\n"
 "2. Go to the per-feature acceptance criteria.\n"
 "3. Read the criteria for several features.\n"
 "PASS: each states something you could OBSERVE and check by hand - not 'the feature works "
 "correctly'.\n"
 "4. For each feature, look for an UNHAPPY-PATH criterion - what happens when something goes wrong, "
 "or input is invalid.\n"
 "PASS: at least one per feature.\n"
 "5. Look for leftover template text - angle brackets, 'TBD', 'describe here'.\n"
 "PASS: none.\n"
 "FAIL: vague criteria, no unhappy path, or template scaffolding shipped as written."),

126: ("DURING A RUN",
 "The Security agent's executive summary and its 'impact' statements reach stakeholders, with no "
 "readability standard - so a decision-maker could be handed a report they cannot act on.",
 "Two registers, used deliberately. FINDINGS stay technical but clear: keep the vulnerability "
 "category AND say what an attacker actually gains and what they need in order to get it. The "
 "stakeholder EXECUTIVE SUMMARY is plain language, with no unexplained acronyms and no severity "
 "table standing in for a conclusion.",
 "1. Run the SECURITY phase and open the security review.\n"
 "2. Read the Executive Summary FIRST.\n"
 "PASS: plain language. A manager could read it and know what to do.\n"
 "PASS: no unexplained acronyms.\n"
 "PASS: it reaches a CONCLUSION in words - a table of severities on its own is not a conclusion.\n"
 "3. Now read individual findings.\n"
 "PASS: each keeps its technical category AND says what an attacker actually GAINS, and what they "
 "would NEED in order to get it.\n"
 "PASS: still technical - findings are for security engineers and must not be flattened.\n"
 "FAIL: a summary a non-specialist cannot act on, or findings that name a category without saying "
 "what it means in practice."),

131: ("DIRECT",
 "The code review report is produced and recorded, but there appeared to be no way to open and read "
 "it in the app - so the person approving the merge gate could not see the evidence behind it.",
 "Verified already working - no code change was needed. Cross-checked against a live run: the "
 "review document IS registered with a rendered report (a ~22 KB report file was confirmed to exist "
 "for the latest run) and the general preview reads it, so the report opens in the app. The earlier "
 "analysis had looked only at one of the two ways the report can be filed and missed the one the "
 "companion actually uses.",
 "SET UP: a build that has been through code review.\n"
 "1. Open Artifacts & Traceability and find the code review document for that run.\n"
 "PASS: it is listed.\n"
 "2. Preview it.\n"
 "PASS: the full review report opens and is readable - findings, severities, verdict.\n"
 "PASS: it is not blank and does not say there is no body.\n"
 "3. Open the merge gate for the same work item and look for a way to reach the review.\n"
 "PASS: you can get to the report from where you are being asked to approve.\n"
 "FAIL: the report cannot be opened from anywhere in the app."),

151: ("DURING A RUN",
 "On Artifacts & Traceability the code review and pull request documents were named only by an "
 "internal work-item reference, so you could not tell which task they belonged to. That same "
 "reference was also used as the PULL REQUEST TITLE on GitHub, so it leaked out of the platform "
 "into the code host.",
 "The task's real title is now carried through and used for the code document, the code review "
 "document and the pull request title. The short reference still names the branch, and it is kept "
 "in the pull request body for traceability.",
 "SET UP: a task with a clear title, taken through a build and a code review.\n"
 "1. Open Artifacts & Traceability and find the CODE REVIEW document for that build.\n"
 "PASS: its name includes the task's real TITLE, not just a short reference.\n"
 "2. Find the CODE document.\n"
 "PASS: same.\n"
 "3. Open the pull request on GitHub.\n"
 "PASS: its TITLE reads as the task title, not an internal reference.\n"
 "4. Read the pull request BODY.\n"
 "PASS: the short reference is still there for traceability - it should not have been removed, only "
 "moved out of the title.\n"
 "5. Check the branch name.\n"
 "PASS: still uses the short reference. That is correct.\n"
 "FAIL: a pull request titled with an internal reference, or documents you cannot match to a task."),

152: ("DURING A RUN",
 "After the merge gate was approved for an implementation phase, its documents - the assumptions "
 "and the implementation record - were still sitting as DRAFTS rather than published. The build "
 "path had no publish step at all: the planning path publishes every document of a run, while the "
 "build path published exactly one, the code pointer. So everything else stayed a draft for ever "
 "even though its gate had been approved.",
 "A publish step was added to the build path mirroring the planning one: after the merge it "
 "publishes every document of the run, skips ones already published, and takes a permanent snapshot "
 "of any document that has a body. The run is now marked completed at publish rather than at merge, "
 "so a run can no longer report 'completed' while its documents are still drafts.",
 "SET UP: a task taken all the way through build, code review, merge gate and merge.\n"
 "1. Approve the merge gate and let the merge complete.\n"
 "2. Open Artifacts & Traceability and filter to that run's documents.\n"
 "3. Check the status of EVERY one - the code pointer, the code review, the assumptions, and any "
 "implementation notes.\n"
 "PASS: all of them read PUBLISHED. None is still Draft.\n"
 "FAIL: the code pointer published but the others left as drafts - that is the exact bug.\n"
 "4. Check the run's own status.\n"
 "PASS: it reads completed, and its documents really are published - the two agree.\n"
 "5. Check the code pointer still points at the pull request on GitHub.\n"
 "PASS: it does - publishing must not have overwritten where the code lives."),

165: ("DIRECT",
 "In the Architecture phase's system architecture document, the container and component diagrams "
 "did not render properly and a wide traceability table overflowed its panel. Curiously it happened "
 "for one test account and not another - because that account's document simply had no diagrams in "
 "it, so it never hit the bug. The cause was a styling rule meant for a small placeholder icon "
 "shrinking every real diagram to a 40x40 pixel smudge.",
 "Fixed in the SHARED renderer, so it covers every phase and every document rather than this one "
 "case. Diagrams now size themselves properly, and every table is wrapped in its own scrolling "
 "container so a wide table scrolls inside its panel instead of spilling out.",
 "1. Run the ARCHITECTURE phase and preview the system architecture document.\n"
 "2. Look at the container and component diagrams.\n"
 "PASS: they render at a proper readable size. Not a tiny smudge.\n"
 "3. Find a WIDE table - the traceability matrix is the widest.\n"
 "PASS: it stays inside its panel and scrolls SIDEWAYS within its own box.\n"
 "PASS: the PAGE itself does not scroll sideways.\n"
 "4. Narrow the browser window right down and check again.\n"
 "PASS: still contained.\n"
 "5. Preview a diagram-bearing document from a DIFFERENT phase.\n"
 "PASS: same correct behaviour - the fix is shared, so it must hold everywhere.\n"
 "FAIL: a shrunken diagram, or a table pushing the page sideways.\n"
 "TIP: if you tested this before the frontend was restarted, do it again after a restart and a hard "
 "refresh. The stored document is unchanged - only the rendering."),

187: ("DIRECT",
 "The security phase produces a bill of materials - the list of every third-party package the "
 "product depends on, and its licence. It is written as JSON because machines read it. The preview "
 "screen had been told, by a hardcoded assumption, that EVERY internal document is Markdown, so the "
 "JSON was handed to the Markdown renderer and collapsed into one unreadable run-on blob. This is "
 "the document somebody opens to answer 'what are we shipping, and are we allowed to ship it'.",
 "The platform now tells the truth about a document's format instead of assuming, and an agent can "
 "declare it outright. The bill of materials is RENDERED for people: headline figures (how many "
 "components, how many licences, which scanner produced it and when), then a components table, then "
 "any known vulnerabilities. A large one is SUMMARISED rather than cut off, with the count stated, "
 "so you are never silently shown a partial inventory. 'View raw' shows the stored file exactly as "
 "saved, and switches back. The renderer is attached to the PREVIEW only - the publish step and the "
 "agents still get the raw file, and a test asserts that.",
 "SET UP: a completed SECURITY phase that produced a bill of materials (SBOM).\n"
 "1. Open Artifacts & Traceability and preview the bill of materials.\n"
 "PASS: it is RENDERED - headline figures first, then a components table, then vulnerabilities.\n"
 "PASS: it is NOT a run-on wall of brackets, quotes and braces.\n"
 "2. Read the headline figures.\n"
 "PASS: how many components, how many licences, which scanner, when, which standard.\n"
 "3. If it is large, look at how the table is handled.\n"
 "PASS: it says how many components there are in total - it does not silently show you part of the "
 "list.\n"
 "4. Click 'View raw'.\n"
 "PASS: the stored file appears exactly as saved.\n"
 "5. Switch back.\n"
 "PASS: the rendered view returns.\n"
 "6. Try previewing any other non-Markdown document you can find.\n"
 "PASS: it renders sensibly too.\n"
 "FAIL: an unreadable blob, or a truncated list with no count.\n"
 "OPEN QUESTION FOR THE TEAM, recorded not answered: when a bill of materials is PUBLISHED to "
 "Confluence, should it push the raw file or the rendered table? It currently pushes raw."),

232: ("DIRECT",
 "After the fix that stopped a failed run opening a gate on the platform's own copy of the agent's "
 "closing message, that copy still EXISTED and was still browsable. The Artifacts screen showed it "
 "as an ordinary draft deliverable - 'Requirements - v1 draft' - with eight unanswered clarification "
 "questions in the body reading as though they were the phase document. Half the reported symptom "
 "was fixed; the visible half was not.",
 "The marker the platform puts on its own copy is now visible to the interface. The Artifacts list "
 "shows 'Run output - not a deliverable' with its own badge instead of Draft, and the preview "
 "replaces the usual banner with a warning naming what the row is and telling the reader to re-run "
 "the phase.",
 "SET UP: a run that FAILED without the agent registering anything - the easiest way is to let a "
 "clarification go unanswered until the run ends.\n"
 "1. Open Artifacts & Traceability and find the row for that failed run.\n"
 "PASS: it is labelled 'Run output - not a deliverable', with its own badge.\n"
 "PASS: it does NOT read as an ordinary Draft alongside the real documents.\n"
 "2. Preview it.\n"
 "PASS: a warning explains what this row actually is and tells you to re-run the phase.\n"
 "PASS: it does NOT show the usual 'read-through from the system of record' banner, which would "
 "imply it is a real deliverable.\n"
 "3. Ask yourself: could a reviewer mistake this for the phase's document?\n"
 "PASS: no.\n"
 "FAIL: it looks like any other draft."),

253: ("DURING A RUN",
 "An agent could not tell the platform what format it had saved. The instruction to declare it "
 "existed and two agents were told to use it - but the tool they actually call never accepted that "
 "argument, and the toolkit silently discards anything a tool does not accept. No error, no "
 "warning: the declaration simply vanished. It made no difference for JSON, which the platform "
 "recognises by itself, which is why it hid behind S.No 187's fix. It mattered for YAML and CSV, "
 "which the platform deliberately refuses to guess at - a Markdown document full of 'Key: value' "
 "lines parses as valid YAML - so a declared-but-discarded YAML file still previewed as a wall of "
 "text.",
 "One parameter, passed through, plus the guidance telling the agent when to use it. The regression "
 "test goes through the tool an agent actually calls, not the function behind it - the old test "
 "called the layer below the break and reported green the whole time it was broken.",
 "SET UP: a phase that produces a non-Markdown, non-JSON document. YAML is the case that matters - "
 "the architecture or CI/CD phases are the likely producers.\n"
 "1. Run a phase that produces a YAML or CSV document.\n"
 "2. Preview it.\n"
 "PASS: it renders as what it is - structured and readable - not as an unbroken wall of text.\n"
 "3. Preview a JSON document (the bill of materials).\n"
 "PASS: still renders correctly - this always worked and must not have broken.\n"
 "4. Preview an ordinary Markdown document.\n"
 "PASS: renders as Markdown.\n"
 "FAIL: a YAML or CSV document shown as a wall of text.\n"
 "IF NO YAML OR CSV DOCUMENT EXISTS in your project, say so in your comment and mark this 'could "
 "not test' rather than passing it - a JSON document passing proves nothing here, because JSON "
 "worked all along."),

45: ("DIRECT",
 "On the Gates page the required role was shown as a raw key with an underscore - 'product_owner'.",
 "The required-role chip and the decision panel now show the readable label, e.g. 'Product Owner'.",
 "1. Open Gates with at least one pending gate.\n"
 "2. Read the required-role chip on the row.\n"
 "PASS: readable - 'Product Owner', 'Tech Lead', 'Security Engineer'.\n"
 "3. Select the gate and read the role in the decision panel.\n"
 "PASS: the same readable label.\n"
 "4. Check gates requiring several different roles.\n"
 "PASS: all readable.\n"
 "FAIL: any underscore, e.g. 'product_owner' or 'tech_lead'."),

56: ("DIRECT",
 "On the Gates page, the approval box on the right had the word 'gate' twice in its heading - "
 "'Phase Gate gate' - because the label already ended in 'Gate' and the screen appended another.",
 "One shared helper now produces the whole phrase with exactly one lower-case 'gate' and no "
 "underscores, and the extra word the panel was adding was removed. The box now reads 'Phase gate'.",
 "1. Open Gates and select a pending gate.\n"
 "2. Read the heading of the approval box on the right.\n"
 "PASS: 'Phase gate' - the word appears once.\n"
 "3. Try a MERGE gate too.\n"
 "PASS: reads cleanly, with no doubled word.\n"
 "FAIL: 'Phase Gate gate', 'phase_gate gate', or any doubled word."),

58: ("DIRECT",
 "On the Workspace Dashboard, the 'Needs me' section showed 'Phase Gate gate' - the word twice - and "
 "the runs list showed the raw status 'awaiting_gate' with an underscore.",
 "Both now go through the shared helpers, so 'Needs me' reads 'Phase gate' and runs read 'Awaiting "
 "gate'.",
 "1. Get a gate pending and a run awaiting a gate.\n"
 "2. Open the Workspace Dashboard and read the 'Needs me' section.\n"
 "PASS: 'Phase gate' - once.\n"
 "3. Read the runs list.\n"
 "PASS: 'Awaiting gate' - no underscore.\n"
 "FAIL: a doubled 'gate', or an underscore anywhere on this screen."),

70: ("DIRECT",
 "The UX Design gate could not be approved at all. Clicking Approve returned 'cannot approve: 9 "
 "required gate condition(s) unmet' and there was nothing on screen to satisfy them. By design that "
 "gate carries a nine-point accessibility checklist the reviewer must tick - but the approval panel "
 "showed only a comment box and the buttons, so the criteria could never be ticked and the gate was "
 "un-approvable. The checklist component existed but had never been connected to anything.",
 "The checklist is now built into the approval panel. When the selected gate has conditions, the "
 "panel fetches them and renders each as a tick box, shows an 'X of N met' progress count, keeps "
 "Approve disabled until every required one is ticked, and sends the ticked criteria with the "
 "decision. Gates with no conditions are unchanged.",
 "SET UP: a completed UX DESIGN phase with its gate pending.\n"
 "1. Open Gates and select the UX Design gate.\n"
 "PASS: a CHECKLIST of accessibility criteria is shown in the approval panel - 22 required items. "
 "(A project may also switch on up to 5 optional AAA criteria, so a higher total is not a "
 "failure - count the REQUIRED ones.)\n"
 "2. Look at the Approve button before ticking anything.\n"
 "PASS: it is disabled.\n"
 "3. Look for a progress indicator.\n"
 "PASS: something like '0 of 22 met', and it moves as you tick.\n"
 "4. Tick them all.\n"
 "PASS: Approve becomes enabled.\n"
 "5. Approve.\n"
 "PASS: it goes through - no 'required gate condition(s) unmet' error.\n"
 "6. CONTROL CHECK: select an ordinary gate with no conditions.\n"
 "PASS: no checklist, and Approve works directly.\n"
 "FAIL: no checklist, or an Approve that errors with unmet conditions and no way to meet them."),

189: ("DIRECT",
 "When several phases run at once, several gates open - but you could only act on the TOP one. The "
 "decision panel was tied to the first pending gate, so a reviewer wanting to handle the third gate "
 "first simply could not. Clicking the work item's name took you off the Gates screen entirely.\n\n"
 "REOPENED 2026-09-09. The earlier fix was PARTIAL and this row was closed too early: what shipped "
 "was a small button in the FIRST COLUMN only, while the rest of the row stayed inert and the work "
 "item name was still a link that navigated away. The complaint was still literally true after the "
 "fix, and the team hit it again.",
 "The WHOLE ROW is now the control. Clicking anywhere in a row - the gate name, the role chip, the "
 "work item, the empty space - loads that gate into the right-hand decision panel, and the page "
 "does NOT navigate. The selected row keeps a tint and gains an orange left rail, so with five "
 "gates on screen it is unmistakable which row the panel belongs to. Keyboard: Tab reaches the list "
 "as ONE stop, Up/Down move between rows, Enter or Space selects, the focused row shows a visible "
 "ring, and a screen reader announces which row is selected. The work-item cell is no longer a "
 "link - opening the work item moved into the panel as 'Open work item', beside 'Preview artifact "
 "under review'. 'Preview' in the last column is still a link and still navigates, and clicking a "
 "link inside a row never also changes the selection.",
 "SET UP: THREE OR MORE gates pending at once. Trigger phases on several work items and let them "
 "all reach their gates. With only one gate this row cannot be tested.\n"
 "1. Open Gates. Note which gate the panel starts on.\n"
 "2. Click the THIRD row - anywhere in it, e.g. the empty space.\n"
 "PASS: the right-hand panel switches to THAT gate.\n"
 "PASS: the page does NOT navigate away.\n"
 "3. Click the GATE NAME on another row.  PASS: selects it.\n"
 "4. Click the ROLE CHIP on another row.  PASS: selects it.\n"
 "5. Click the WORK ITEM name on another row.\n"
 "PASS: it SELECTS that gate. It must NOT take you to the work item page - that is the specific "
 "thing this row was reopened for.\n"
 "6. Look at the selected row.\n"
 "PASS: it is tinted AND has an orange bar down its left edge - obvious at a glance among five "
 "rows.\n"
 "7. Decide the third gate WITHOUT touching the others.\n"
 "PASS: it works, in whatever order you like.\n"
 "8. KEYBOARD: press Tab repeatedly until focus reaches the list.\n"
 "PASS: the list is ONE tab stop, not one per row.\n"
 "9. Press Down, then Up.  PASS: focus moves between rows with a visible ring.\n"
 "10. Press Enter (and on another row, Space).  PASS: selects that gate.\n"
 "11. Click 'Preview' in the last column.  PASS: it DOES navigate - that is correct - and does not "
 "also change the selection.\n"
 "12. In the panel, find 'Open work item'.  PASS: it is there, and it opens the work item.\n"
 "13. Check any OTHER table in the app (Work Items list, Artifacts, Runs).\n"
 "PASS: unchanged - rows there are not selectable, because selection was added as opt-in.\n"
 "FAIL: any of 2-5 not selecting; clicking the work item navigating away; no visible selected "
 "state; keyboard not working; or another table's behaviour changed."),

195: ("DIRECT",
 "The Deployment agent's whole philosophy is 'never deploy without a completed readiness "
 "checklist' - but the deployment gate carried NO conditions at all, so a DevOps approver could "
 "approve a release with nothing checked. The readiness verdict the agent produces was narrative "
 "only; the platform never enforced it.",
 "A reviewer-attested readiness checklist was added, mirroring the agent's own list: code quality, "
 "testing and acceptance testing, security, migrations, rollback, on-call and communications, and "
 "deliverables. Enforcement and display are automatic - approval is blocked until every required "
 "item is ticked, and the Gates page renders the criteria.",
 "SET UP: a completed DEPLOYMENT phase with its gate pending.\n"
 "1. Open Gates and select the deployment gate.\n"
 "PASS: a READINESS CHECKLIST is shown, covering code quality, testing/UAT, security, migrations, "
 "rollback, on-call and communications, and deliverables.\n"
 "2. Look at Approve before ticking anything.\n"
 "PASS: disabled.\n"
 "3. Tick SOME but not all.\n"
 "PASS: still disabled.\n"
 "4. Tick them all.\n"
 "PASS: Approve becomes enabled.\n"
 "5. Approve.\n"
 "PASS: accepted.\n"
 "FAIL: an empty checklist, or a deployment gate you can approve with nothing ticked - that is the "
 "exact bug."),

249: ("DIRECT",
 "A reviewer approved one gate. The green banner correctly named it - but that gate then left the "
 "pending list, the panel automatically selected the NEXT gate, and the blue 'Decision recorded' "
 "banner came with it, sitting inside the next gate's panel. Nothing had been decided there. A "
 "reviewer working down a queue of five reads 'Decision recorded' on the gate that just opened, "
 "reasonably concludes it is handled, and moves on - leaving a gate pending they believe they "
 "approved. Separately, one click produced THREE confirmations, two of them identical every single "
 "time.",
 "ONE confirmation, and it names its own gate: a single banner at PAGE level above the list, never "
 "inside a gate's panel - which is what makes the drift impossible rather than merely unlikely. It "
 "holds the gate's label, the kind of decision and whether it was a merge gate, all captured BEFORE "
 "the decision is sent. The in-panel banner is gone - it was the third telling of one click and the "
 "one that drifted. The footer line is now guidance, not a report: 'Decisions are recorded with "
 "your name and role.' The paused-task warning line was removed as the team asked; the Paused chip "
 "stays.",
 "SET UP: TWO OR MORE gates pending at once. This cannot be tested with one gate.\n"
 "1. Open Gates. Note the work items of the first two pending gates.\n"
 "2. APPROVE the first one.\n"
 "3. Read the confirmation.\n"
 "PASS: exactly ONE confirmation on screen, at PAGE level above the list.\n"
 "PASS: it names the gate you actually approved - the FIRST work item.\n"
 "4. Now look at the panel on the right, which has auto-selected the NEXT gate.\n"
 "PASS: it says NOTHING about a decision. No 'Decision recorded' inside it.\n"
 "THIS IS THE WHOLE POINT OF THIS ROW - if the second gate's panel claims a decision, FAIL it.\n"
 "5. Count the confirmations after that single click.\n"
 "PASS: one. Not three.\n"
 "6. Read the grey line in the footer of the panel.\n"
 "PASS: 'Decisions are recorded with your name and role.' - guidance, and it does not repeat the "
 "confirmation above it.\n"
 "7. Click to a different gate manually.\n"
 "PASS: the confirmation clears.\n"
 "8. Repeat with REJECT and with REQUEST CHANGES.\n"
 "PASS: each gets its own wording, and neither leaks to the next gate.\n"
 "9. If the task is paused, check the panel.\n"
 "PASS: the Paused chip is there; the paragraph of warning text is gone."),

250: ("DIRECT",
 "A link whose text named one thing opened a different thing, or nothing at all - about FIFTY "
 "navigations across roughly twenty files. Four were worse than merely landing on a list: the "
 "onboarding hub linked to an address that does not exist, so the primary action on a BLOCKING "
 "onboarding step bounced you to the Dashboard without a word; and twelve links opened a DIFFERENT "
 "item than the one you clicked, because the Gates and Clarifications screens always selected the "
 "first pending item - so clicking 'Answer' beside a question you had just read could open a "
 "different question, inviting the wrong answer into the wrong box.",
 "A rule now written into the code: a link's text is a promise. If the id of the thing promised is "
 "in hand, link to its DETAIL page; if only a scope is in hand, link to the list carrying that "
 "scope, and the list must honour it. Never link to a bare list from text that names one thing. A "
 "stale deep link now selects NOTHING and says so, rather than falling back to the first pending "
 "item - which would have re-introduced the original bug one level down. Forty links that were "
 "full page reloads are now proper in-app navigation. Two automatic guards were added so this "
 "cannot creep back.",
 "SET UP: several pending gates AND several pending clarifications, so 'the first one' and 'the one "
 "you clicked' are different things.\n"
 "1. On the Dashboard 'Needs me' list, find a link naming a SPECIFIC gate that is NOT the first "
 "pending one. Click it.\n"
 "PASS: it opens THAT gate, not the first in the list.\n"
 "2. Do the same for a specific CLARIFICATION.\n"
 "PASS: it opens the question you clicked.\n"
 "THIS IS THE IMPORTANT ONE - answering the wrong question is a real risk.\n"
 "3. On a gate, click 'Preview artifact under review'.\n"
 "PASS: it opens THAT artifact, not a list of everything.\n"
 "4. On the Traceability graph, click a node.\n"
 "PASS: it opens that specific item.\n"
 "5. Walk the app clicking links whose text names one specific thing - a run, an artifact, a work "
 "item, a gate.\n"
 "PASS: each opens the thing it named.\n"
 "6. Note whether the page RELOADS (a white flash, the whole app re-drawing) on any of them.\n"
 "PASS: none do - navigation stays inside the app.\n"
 "7. Take a link you used above, then delete or complete the thing it pointed at, and use the link "
 "again.\n"
 "PASS: it says clearly that the item is no longer there. It must NOT silently open a different "
 "one.\n"
 "8. On a BROWNFIELD project, use the onboarding hub's main action link.\n"
 "PASS: it goes somewhere real - you are not dumped on the Dashboard with no explanation.\n"
 "FAIL: any link opening something other than what its text named."),

}
