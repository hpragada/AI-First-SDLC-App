# User Journeys — Web Accessibility POC & Phase 2

**What this is.** The end‑to‑end journeys the build plans and backlogs deliver — written so anyone (engineer or not) can follow exactly what happens, who does it, and why, at each step. Each journey is a plain‑language walk‑through, not a table of shorthand.

**One correction to note up front — the golden dataset.** The "golden set" (a hand‑labelled answer‑key used to measure how accurate the AI checks are) is an **Edvensoft‑internal** thing. It is used only in our own testing to prove the checkers work before we release them. **It is not part of any tenant's journey and never appears in the platform** — a tenant never creates, imports, or sees one.

**Who's in these journeys.** Project Owner/Admin (sets up the project), UX Designer (design phase), Developer (writes/fixes code), Tech Lead and Reviewer (approve gates), QA Lead (owns the test gate), and a new **Accessibility SME** role (reviews the AI's uncertain calls and signs the conformance report — for the POC this can be the QA Lead wearing a second hat).

**The one new thing we build.** A capability called `a11yai` — the AI checks that judge the accessibility things the rule scanner can't (is the alt text meaningful, is this really a button, is meaning carried by colour alone, does the label match what a screen reader says). Everything else in these journeys is the platform's existing design → build → review → test → fix‑loop → gate machinery, with accessibility woven through it.

---

## J1 — Set up a project to be held to WCAG accessibility  *(foundation · greenfield & brownfield)*

**What this delivers:** a project that is ready to be checked against WCAG 2.2, with the AI checks switched on and a clear pass/fail gate, so every later journey has something to run against.

1. The **Project Owner** opens the project's settings and sets its accessibility target to **WCAG 2.2 AA** — the standard everything will be measured against — and chooses how strict the accessibility gate should be (for example, "block anything serious, but don't block on the AI's unsure guesses").
2. The platform switches on the **`a11yai`** checks for this tenant. Because the AI models sit behind a swappable "capability," the owner doesn't pick a model — they just get working checks, and Edvensoft can change the model underneath later without disturbing the project.
3. The owner assigns who is accountable for accessibility sign‑off (the **Accessibility SME**, or the QA Lead for the POC).
4. The platform loads the WCAG 2.2 rulebook into its knowledge base so that, later, every AI finding can quote the exact rule it's judging against.

**Done when:** the project has a WCAG 2.2 target, the AI checks resolve for that tenant (and can't see any other tenant's data), the gate strictness and the accessibility reviewer are set, and the WCAG rulebook is loaded. *There is no golden‑set step here — the accuracy of the checks is proven internally by Edvensoft, not by the tenant.*

---

## J2 — Design a screen accessibly and clear the design gate  *(greenfield)*

**What this delivers:** accessibility problems caught while the screen is still a wireframe — the cheapest possible place to fix them.

1. The **UX Designer** runs the design phase for the feature's screens as they do today, producing the wireframes and the design system.
2. The design agent writes the screen's accessibility spec (`ACCESSIBILITY.md`) — but now at **WCAG 2.2** — listing, criterion by criterion, what this screen must do (contrast levels, keyboard behaviour, text alternatives, and so on).
3. The **AI design checks** look at the wireframes themselves and flag design‑level problems: an image whose intended alt text wouldn't be meaningful, a status shown only by colour, a heading or label that isn't descriptive, a tap target that's too small. Each flag says which WCAG rule it relates to and how confident the AI is.
4. The designer reviews the flags in the design console, fixes the design, and — if the AI is unsure about something — sends that one to the Accessibility SME rather than guessing.
5. The **design gate** lets the phase move on once there are no unresolved serious (Level‑A) design problems.

**Done when:** the screen has a WCAG 2.2 accessibility spec, the AI has checked every wireframe state, each flag cites a rule and a confidence, and the design can't proceed while a serious AI‑confirmed problem is open.

---

## J3 — Build and review a screen with accessibility caught early  *(greenfield)*

**What this delivers:** the "meaning" accessibility defects (a fake button, a mislabelled field) caught at code review, before testing.

1. The **Developer** builds the screen in their normal working copy, following the accessibility spec and the design system.
2. When they open a pull request, the **code review** step runs its usual accessibility code checks **plus** the AI's "meaning" checks (is this really a button? does this label match its accessible name?) against the actual rendered page. The findings are added to the review with the rule they relate to and a confidence.
3. Any serious AI‑confirmed problem automatically becomes a **fix item** that blocks the merge; smaller ones are tracked but don't block.
4. The developer fixes the flagged items in their working copy, and only the changed files are re‑reviewed.
5. The **merge gate** opens once the accessibility (and other) findings are resolved or consciously accepted, and the code merges.

**Done when:** review runs both the rule checks and the AI checks against the WCAG 2.2 spec, serious AI‑confirmed problems block the merge and open a tracked fix, every finding names its rule and confidence and a suggested fix, and re‑review only looks at what changed.

---

## J4 — Test the built screen against WCAG and clear the test gate  *(greenfield · the core POC)*

**What this delivers:** the implemented screen verified against WCAG 2.2 by the rules **and** the AI, in one place, with problems turning into tracked bugs automatically.

1. The **testing phase** runs the rule scanner (axe) against every screen — now at **WCAG 2.2**.
2. Straight after, the **AI checks** run on each screen's relevant parts — images for alt text, controls for "is this a real button / correct label," coloured indicators for colour‑only meaning — and their findings are merged into the **same report** as the rule findings. Each finding is marked as coming from the rules or the AI, with a confidence and the rule it relates to.
3. Real problems (a rule violation, or an AI finding the system is confident about) automatically open a **bug** with a severity based on the WCAG level; the AI's unsure calls go to the SME's review queue instead of becoming bugs; and a bug closes itself when a later run shows the problem fixed.
4. The **test‑automation** step generates scripts that run both the rule scan and the AI checks, so accessibility is part of the automated suite from then on.
5. The **QA Lead** approves the **accessibility test gate** once there are no real (rule or AI‑confirmed) serious problems left.

**Done when:** both the rules and the AI check every screen at WCAG 2.2, findings show their source/confidence/rule, bugs open and close themselves, and the gate blocks on real serious problems. (The keyboard/interaction checks are done by hand for now; the AI agent takes them over in J8.)

---

## J5 — Onboard an existing app and get a WCAG baseline  *(brownfield · "test it for WCAG")*

**What this delivers:** an honest "here's where your existing app stands on accessibility" report for an app that was never built through our pipeline.

1. The **Project Owner** starts onboarding the existing app: they confirm which repository/repositories and content sources are involved, and the platform does its usual discovery of what the project already has.
2. As part of that, the platform now also checks the app's **accessibility posture** — does it already have an accessibility spec? what WCAG level (if any) does it claim? does the rule scanner currently pass? — and records the answer, flagging a missing spec as a gap.
3. The platform registers the app's existing screens/pages so they can be tested — without needing them to have gone through our design phase.
4. The **accessibility checks run against the live app** (the same rule + AI checks from J4), producing a **baseline report** grouped by WCAG rule, with severities.
5. The findings become a prioritised **fix backlog**; on this first pass the gate is **informational** — it's a health‑check, not a pass/fail exam — and re‑running it later won't create duplicate tickets.

**Done when:** onboarding records the app's accessibility posture, the baseline audit runs the rules + AI on the existing screens with no prior design phase, and it produces a WCAG‑2.2 baseline report and a de‑duplicated fix backlog.

---

## J6 — Remediate an onboarded app to WCAG  *(brownfield · "fix it to WCAG")*

**What this delivers:** the existing app's accessibility debt worked down to the target, using the platform's normal fix‑and‑recheck loop.

1. The **Product Owner / SME** picks which items from the J5 baseline backlog to tackle first.
2. Each accessibility problem becomes a **fix item** that goes to a developer, who fixes it properly in the code (a real source‑level fix — not a cosmetic overlay), using the AI finding's suggested fix and the rule it cites as a starting point.
3. The fix is **re‑reviewed** and **re‑tested** only on the screens that changed; when the check passes, the item closes itself. The SME confirms any fixes the AI was unsure about, and the regression suite makes sure a fix didn't break something else.
4. As items close, progress is tracked against the original baseline.
5. Once the app clears the WCAG‑2.2 gate threshold, it's marked as conformant‑to‑target — a status a **human signs off**, never the platform on its own.

**Done when:** each accessibility item flows through the existing fix → review → re‑test loop, fixes are real code changes, re‑testing confirms them, a human signs off, and progress is visible against the baseline with no new regressions.

---

## J7 — Keep building an onboarded app accessibly  *(brownfield · "build it with WCAG")*

**What this delivers:** new features added to an imported app are held to the same accessibility standard as a brand‑new project.

1. The onboarded project resumes the pipeline at whatever phase onboarding decided it was at.
2. Every **new** feature or screen flows through the same accessibility spine as greenfield: designed accessibly (J2), reviewed with the AI checks (J3), and tested against WCAG (J4).
3. The accessibility gate applies to the new pull requests; the app's pre‑existing debt (from J5/J6) is tracked separately, so old debt doesn't block unrelated new work.

**Done when:** new work on the imported app passes the same WCAG‑2.2 gates as greenfield, greenfield and brownfield share one set of checks and one gate, and legacy debt and new‑work status are reported separately.

---

## J8 — Test keyboard and interaction journeys with an AI agent  *(Phase 2 · greenfield & brownfield)*

**What this delivers:** the accessibility checks you can only do by *using* the app — full keyboard operation, focus behaviour, screen‑reader announcements — done automatically by an AI agent.

1. The **QA Lead** points the AI agent at a critical user journey (say, sign‑up or checkout).
2. The agent **operates the app** the way an assistive‑tech user would: it tabs through in order, checks nothing traps the keyboard, checks focus stays visible and isn't hidden behind sticky bars, watches for surprising changes when something gets focus or is typed into, confirms a pop‑up traps and returns focus, and watches that status messages are actually announced.
3. Anything it finds flows into the same bug loop and SME queue as the other checks; if two checks find the same thing, it's one bug, not two.
4. Because it's a new AI capability, it stays **advisory** — it can't block a merge — until it has proven itself accurate against Edvensoft's internal accuracy bar; then it's allowed to feed the gate.

**Done when:** the agent tests the keyboard/interaction rules on critical journeys with a confidence on each result, its findings flow into the bug loop, and it only starts blocking merges once it's proven reliable.

---

## J9 — Human review and a signed conformance report  *(Phase 2 · greenfield & brownfield)*

**What this delivers:** a human expert keeps the AI honest, and produces a defensible, human‑signed WCAG conformance report — with the platform never claiming compliance by itself.

1. The AI's **unsure findings** land in the **SME's review console**, which shows the element, a screenshot, the rule in question, and the AI's draft opinion. The SME marks each "yes, that's a real problem" or "no, that's fine." Those decisions are recorded (and, internally, feed Edvensoft's accuracy checks).
2. The SME pulls together the **conformance picture** for the project — for each WCAG rule, what was found and by whom (rule, AI, or human).
3. The platform **drafts** a conformance statement / VPAT from that picture; the SME edits and **signs** it. The platform never marks anything "compliant" on its own.
4. The signed report is exported through the normal review‑then‑publish flow, with a full audit trail (including which AI model and prompt produced each finding).

**Done when:** every AI‑confirmed finding is human‑reviewable, the conformance draft shows rule/AI/human provenance per WCAG rule, only a human can sign it, and the export is fully audit‑traceable. The language is always "we reduce and find issues" — never "we certify compliance."

---

## How the journeys map to the scopes you named
- **Start a new project and keep it WCAG‑compliant:** J1 → J2 → J3 → J4 (then J8/J9).
- **Onboard an existing app and test it for WCAG:** J1 → J5.
- **Onboard an existing app and remediate it to WCAG:** J5 → J6 (then J9).
- **Onboard an existing app and keep building it with WCAG:** J5 → J7 (which reuses J2–J4).

## Which build plan delivers which journey
- **QA plan** (`BUILD_PLAN_QA.md` / `TASK_BACKLOG_QA.md`): J1, J4, the J5 **audit run**, J8, J9 — plus the shared `a11yai` engine and Edvensoft's internal accuracy checks.
- **Other‑phases plan** (`BUILD_PLAN_OTHER_PHASES.md` / `TASK_BACKLOG_OTHER_PHASES.md`): J2 (design), J3 (review), the J5 **onboarding step**, J6, J7.

## Guardrails carried through every journey
- **Never over‑claim:** the product says "finds and helps fix issues; does not certify compliance." Only a human signs a conformance statement (J9).
- **The target standard/jurisdiction is set per project** (default WCAG 2.2 AA). Accessibility laws vary by country but almost all reference WCAG, so the engine is portable; which legal document you produce (a US‑style VPAT vs an EU accessibility statement) is a reporting choice.
- **Everything rides the platform's existing rules:** swappable capabilities (not vendors), gates in the control plane, tenant isolation on every new table, and the exact AI model/prompt logged on every finding.
