# -*- coding: utf-8 -*-
"""Pass 11: build, code review and merge."""

ROWS = {

72: ("DIRECT",
 "There was no way to START implementation on a work item from the app at all. The machinery "
 "existed but had no button or address behind it, so the whole 'run implementation on one task' "
 "flow was blocked - for both platform-managed and Jira-managed work.",
 "A proper entry point was added, which fills in sensible defaults (the implementation agent, the "
 "work item's repository, its base branch) and returns a clear, friendly message when the work item "
 "has no repository to build into.",
 "1. Open a TASK work item that has a repository.\n"
 "2. Find and click the Implementation trigger.\n"
 "PASS: a build run starts, and you are given a run to watch.\n"
 "3. Now try it on a work item with NO repository, on a single-repo project.\n"
 "PASS: it falls back to the project's default repository and builds.\n"
 "4. Try it on a work item with no repository on a MULTI-repo project.\n"
 "PASS: it is refused with a friendly message telling you to assign the repository (see S.No 108) - "
 "NOT a raw error.\n"
 "FAIL: no way to start implementation, or an unreadable error."),

73: ("DURING A RUN",
 "During implementation the companion wrote code into a folder on your machine on a branch, but "
 "never PUSHED that branch anywhere. The platform then tried to open a pull request for a branch "
 "that did not exist on GitHub, which failed. The code landed on the developer's machine and "
 "nothing else in the pipeline could happen.",
 "The companion now does the git work: after the code is written and the secret scan passes, it "
 "commits with a proper message derived from the task, pushes the branch, and reports the commit "
 "back, so the platform opens the pull request against a branch that really exists. Nothing is "
 "committed or pushed if the secret scan blocks, or if the agent produced no change.",
 "SET UP: a real GitHub repository connected, and a task ready to build.\n"
 "1. Trigger implementation and let it run.\n"
 "2. Open GitHub and look at the repository's branches.\n"
 "PASS: a new branch appears, named after the work item.\n"
 "3. Look at its commit.\n"
 "PASS: a real commit with a sensible message derived from the task's title and type - not a "
 "placeholder.\n"
 "4. Back in the app, wait for the pull request step.\n"
 "PASS: a pull request opens on GitHub against that branch.\n"
 "5. NEGATIVE CHECK: if you can make a build produce no changes, confirm nothing is pushed for it.\n"
 "PASS: no empty branch appears.\n"
 "FAIL: code only on the local machine, or a pull request step that fails because the branch is not "
 "on GitHub."),

86: ("DURING A RUN",
 "The build committed and pushed code to GitHub, but NO pull request was opened and the run then "
 "failed. The implementation agent registers an early code marker before the pull request exists; "
 "the platform mistook that marker for 'the pull request is already open' and skipped opening it, "
 "and the code review step then crashed looking for pull-request details that were never there.",
 "The platform now distinguishes a real pull-request reference from the agent's early marker. It "
 "skips only when a genuine pull request is already open; when it finds the early marker it OPENS "
 "the pull request and updates that marker in place rather than skipping or duplicating. The code "
 "review step now gives a clear error rather than crashing if the reference is not a real one.",
 "1. Trigger implementation on a task and let the build finish.\n"
 "2. Watch the run through to the pull request step.\n"
 "PASS: a pull request IS opened on GitHub.\n"
 "3. Check the code documents on Artifacts & Traceability.\n"
 "PASS: there is ONE code document, and it points at the real pull request - not two, one of which "
 "is an empty early marker.\n"
 "4. Let the code review step run.\n"
 "PASS: it starts normally - no crash.\n"
 "5. Repeat on a second task.\n"
 "PASS: same.\n"
 "FAIL: code pushed but no pull request; a duplicate code document; or a run failing at the code "
 "review step."),

87: ("DURING A RUN",
 "The AI agent that writes the code could also change the STATUS of the work item it was working "
 "on. It could mark its own task finished, push it back to 'not started', or park it in a state "
 "nothing ever moves it out of. Whether a piece of work is done is a decision for a person at a "
 "gate, not for the thing doing the work - an agent marking its own homework is how a task reaches "
 "'done' with nobody having reviewed it.",
 "The rule was INVERTED. Instead of a list of states the agent may NOT set - which has to be "
 "remembered and extended every time a state is added - there is now a list of the one state it "
 "MAY set: 'in progress', when it starts work, which is the single move its own instructions tell "
 "it to make. Everything else is refused with a message saying what it is allowed to do, so a state "
 "added later is refused by default rather than quietly permitted. That prediction was tested "
 "immediately: the 'cancelled' state added later was refused by this rule with no extra code.",
 "1. Trigger implementation on a task.\n"
 "2. Watch the work item's state closely for the WHOLE build.\n"
 "PASS: it moves to 'in progress' when the agent starts - that IS allowed and correct.\n"
 "PASS: it NEVER reaches done, cancelled, blocked, in review, accepted or proposed by itself.\n"
 "3. Let the build finish and the code review run, with the merge gate still pending.\n"
 "PASS: still not done.\n"
 "4. Approve the merge gate.\n"
 "PASS: NOW the platform marks it done. That is the legitimate path.\n"
 "5. Repeat on a couple more tasks, including one whose build FAILS.\n"
 "PASS: a failed build does not leave the item in a strange state the app cannot move it out of.\n"
 "FAIL: the item reaching any state other than 'in progress' before your gate decision."),

88: ("SET UP FIRST",
 "The intended flow is: pull request, code review, merge gate approved in the platform, platform "
 "merges, work item done. If a developer merged the pull request BY HAND on GitHub instead, the "
 "platform never learned of it. The run sat waiting for an approval nobody would ever give, the "
 "work item never reached done, its documents stayed drafts, and the reviewer was looking at a "
 "panel asking them to approve a merge that had already happened, with nothing on screen saying so.",
 "The platform now DETECTS the external merge and says so; a HUMAN still decides. Nothing in the "
 "platform ever approves a gate itself. The Gates screen shows 'Already merged on GitHub - merged "
 "outside the platform by <name> on <date>' and the button becomes 'Acknowledge merge & complete', "
 "using the same endpoint, role check and audit trail as any other approval. Because webhooks are "
 "not guaranteed, a sweep also runs whenever the Gates screen is read: it finds gates stuck past an "
 "hour, asks GitHub whether the pull request was merged, and ANNOTATES only - it never decides.\n\n"
 "CORRECTION TO WHAT WAS REPORTED EARLIER: it was said that approving after an external merge would "
 "hit GitHub, get an error, and loop. It would not - the merge step already does nothing if the "
 "pull request is already merged. The real bug was that nobody ever approves, and nothing tells "
 "anybody they should.",
 "SET UP: a build that has reached the merge gate. You will merge its pull request by HAND.\n"
 "1. Get a task to the point where its merge gate is pending.\n"
 "2. Go to GitHub and MERGE the pull request yourself, without approving in the platform.\n"
 "3. Wait a few minutes, then open the Gates screen.\n"
 "PASS: the gate now says it was already merged on GitHub, naming WHO merged it and WHEN.\n"
 "PASS: the button reads 'Acknowledge merge & complete', not a plain Approve.\n"
 "4. Click it.\n"
 "PASS: the run completes and the work item reaches done.\n"
 "5. Check the documents.\n"
 "PASS: published, not left as drafts.\n"
 "IMPORTANT: the notice may take up to an hour if the GitHub webhook is not configured on your "
 "deployment - that is by design; the sweep runs when the Gates screen is read. If it is "
 "configured, expect it within seconds.\n"
 "FAIL: the gate keeps asking for a plain approval with no indication the merge already happened."),

110: ("DURING A RUN",
 "The automated code review was given only eight minutes to report. A first review on a cold "
 "machine legitimately takes longer, so it timed out - and a timeout was treated as 'no problems "
 "found', so the merge gate opened with ZERO findings and no review document, and the reviewer "
 "approved with no automated review having run at all. Worse, if the review arrived after the "
 "timeout its findings were recorded but never read, so they were silently lost.",
 "The review window is now configurable per run with a realistic default of thirty minutes, and on "
 "timeout the platform does one final read - so a verdict landing moments after the last check "
 "still drives the fix-and-re-review loop instead of being orphaned. The surrounding time limit was "
 "raised too, so the review can never be cut short and restarted mid-flight.",
 "1. Trigger implementation on a task and let it reach the code review step.\n"
 "2. TIME the review, particularly the first one on a freshly started companion.\n"
 "PASS: it completes rather than timing out, even if it takes ten to twenty minutes.\n"
 "3. When the merge gate opens, look at the review result.\n"
 "PASS: a real code review document exists and you can read it.\n"
 "PASS: the finding count reflects a real review, not a bare zero from a timeout.\n"
 "4. If findings were raised, check the fix-and-re-review loop actually starts.\n"
 "PASS: it does.\n"
 "FAIL: a merge gate that opens with zero findings and NO review document - that is the review "
 "having silently not happened."),

111: ("DURING A RUN",
 "A follow-on from the previous fix. A phase that legitimately runs longer than fifteen minutes - "
 "for instance a code review now allowed up to thirty - had its hold on the job expire while it was "
 "still working, so the job was taken away from a machine that was alive and healthy. That produced "
 "duplicate empty documents, a failed final review, and a merge gate opening with no valid review "
 "behind it.",
 "The heartbeat now RENEWS the machine's hold on its in-flight work, so a live, heartbeating "
 "companion's claim never goes stale however long the phase runs - while a genuinely dead companion "
 "still has its work recovered about fifteen minutes after its last heartbeat. This ties the hold "
 "to whether the machine is ALIVE, not to how long the task takes, so it is robust for any long "
 "phase.",
 "SET UP: you need a phase that runs longer than fifteen minutes. A first code review, a UX Design "
 "run, or a large implementation will do it.\n"
 "1. Trigger a long-running phase and let it run past twenty minutes.\n"
 "2. Watch the run console throughout.\n"
 "PASS: the run continues on ONE attempt. It is not taken away and restarted mid-flight.\n"
 "3. When it completes, check Artifacts & Traceability.\n"
 "PASS: no DUPLICATE or EMPTY documents from that run.\n"
 "4. If it was a code review, check its result.\n"
 "PASS: a real review with a proper verdict - not a failed or empty one.\n"
 "5. Check the companion pill stayed Ready throughout.\n"
 "FAIL: a run restarting itself while the companion is plainly alive, or duplicate empty documents "
 "appearing."),

114: ("DURING A RUN",
 "A code review that FOUND SERIOUS PROBLEMS could silently pass. The platform read the blocking "
 "findings only from a machine-readable block at the very end of the review agent's final message. "
 "When the agent ended with prose instead, the platform parsed ZERO findings, counted zero blocking "
 "problems, SKIPPED the fix loop entirely and opened the merge gate. Seen live: the review really "
 "did report five blocking findings including a pull request aimed at the wrong branch and "
 "documentation exposed in production - and the merge gate opened as though the code were clean.",
 "Three layers. The review agent's instructions were hardened: its final message must END with "
 "exactly one machine-readable verdict block and nothing after it, and it may not deliver the "
 "verdict some other way or append a prose summary. The reading is now robust - it scans all such "
 "blocks and takes the last one that both parses and looks like a verdict. And most importantly it "
 "now FAILS CLOSED: if the review text signals blocking problems but no blocking findings parse, "
 "the platform raises an error and retries, then fails the build - so the merge gate is NEVER "
 "opened on a review it could not read.",
 "1. Trigger implementation on a task with a real defect in it, so the review has something to "
 "find. (Deliberately introducing one is the reliable way.)\n"
 "2. Let the code review run.\n"
 "PASS: the blocking findings are correctly counted - the run console shows a real number, not "
 "zero.\n"
 "3. Check what happens next.\n"
 "PASS: the fix-and-re-review loop STARTS. The merge gate must NOT open while blocking problems "
 "are outstanding.\n"
 "4. Read the review document itself and compare it against the count.\n"
 "PASS: they agree. If the report describes problems, the count is not zero.\n"
 "5. Let the loop run until the review passes.\n"
 "PASS: only then does the merge gate open.\n"
 "FAIL: a merge gate opening while the review report plainly describes blocking problems. That is "
 "the exact bug and it is the most serious kind - it lets unreviewed code through."),

115: ("DURING A RUN",
 "When the code review returned blocking findings, the platform was supposed to re-run the "
 "implementation agent on the same branch to fix them. It never did - the hand-off to your machine "
 "was simply never wired up, so there was nothing for the companion to pick up. The agent never "
 "re-ran, no second report ever came, and the build waited until it timed out. The fix loop could "
 "never complete.",
 "The remediation hand-off now mirrors the initial one: it rebuilds the briefing with a "
 "'remediation items' section listing the open findings with their severity, file and line, "
 "rebuilds the full task payload, and marks the work as waiting for a machine - so the companion "
 "claims it and re-runs the implementation agent on the SAME branch. The pull request just gets new "
 "commits.",
 "SET UP: a build whose code review WILL return blocking findings. Introduce a defect deliberately.\n"
 "1. Trigger implementation and let the code review find blocking problems.\n"
 "2. Watch what happens next - this is the whole test.\n"
 "PASS: within a few minutes the companion CLAIMS a new piece of work and the implementation agent "
 "runs AGAIN.\n"
 "FAIL: nothing happens; the run sits waiting until it times out. That is the bug.\n"
 "3. Check GitHub.\n"
 "PASS: NEW COMMITS appear on the SAME branch and the SAME pull request - not a new branch and not "
 "a new pull request.\n"
 "4. Let the review run again.\n"
 "PASS: a second review happens, and the finding count comes down.\n"
 "5. Let it converge.\n"
 "PASS: the merge gate eventually opens with the problems resolved."),

116: ("DURING A RUN",
 "The code review flagged the SIZE of the pull request as a blocking critical problem. But the "
 "platform's only response to a blocking finding is to re-run the implementation agent on the same "
 "branch - and that agent cannot split a pull request, rename a branch or rewrite a "
 "platform-generated commit message. So the finding came back every cycle, the loop churned until "
 "it ran out of attempts, and the build FAILED even though the code was fine. Seen live: three real "
 "defects were fixed across the cycles while 'pull request too large' stayed blocking every time, "
 "because a legitimate first-time scaffold cannot be made smaller.",
 "The review agent's first-step housekeeping checks - pull request size, commit message format, "
 "branch name, description, history - are now NON-BLOCKING SUGGESTIONS for the human reviewer at "
 "the merge gate, never blocking findings. The reasoning is written into its instructions: these "
 "are either platform-owned or not about code, so the fix loop cannot resolve them, and blocking on "
 "them guarantees an unwinnable loop. A genuinely unreviewable pull request is now RETURNED BY THE "
 "HUMAN at the gate rather than by the automated loop. Size is still REPORTED, as a suggestion.",
 "SET UP: a task that will produce a LARGE pull request - a first-time scaffold or a big feature is "
 "ideal, over about 400 changed lines.\n"
 "1. Trigger implementation and let the code review run.\n"
 "2. Read the review's findings.\n"
 "PASS: pull-request size may be MENTIONED, but as a suggestion - not as a blocking critical.\n"
 "3. Watch the fix loop.\n"
 "PASS: it does NOT churn on the size finding. If there are real code defects it fixes those and "
 "converges.\n"
 "4. Let it run to the end.\n"
 "PASS: the merge gate OPENS. The build does not fail with 'remediation cycles exhausted' on a "
 "large-but-correct pull request.\n"
 "5. At the merge gate, look for the size suggestion.\n"
 "PASS: it is visible to you as the human reviewer, so you can decide whether to send it back.\n"
 "FAIL: a build failing after several cycles where the only remaining finding is about size, "
 "formatting or naming."),

127: ("DURING A RUN",
 "After a human approved the merge gate, the platform tried to merge and GitHub refused, so the work "
 "item never reached done. During the automated review-and-fix loop the pull request is opened as a "
 "DRAFT - deliberately, so nobody merges it prematurely - and GitHub does not allow a draft to be "
 "merged. So the moment anyone approved, the final merge always failed. This was the single blocker "
 "stopping ANY build from finishing.",
 "A step was added that takes the pull request out of draft immediately before merging - the one "
 "legitimate moment to do so, since the gate is already approved - and confirms it really came out "
 "of draft before merging.",
 "SET UP: a build that has reached the merge gate with its pull request still in draft on GitHub.\n"
 "1. Before approving, check the pull request on GitHub.\n"
 "PASS: it shows as a DRAFT. That is correct at this point.\n"
 "2. Approve the merge gate in the app.\n"
 "3. Watch GitHub.\n"
 "PASS: the pull request comes out of draft, and THEN merges.\n"
 "4. Check the work item.\n"
 "PASS: it reaches DONE.\n"
 "5. Check the run.\n"
 "PASS: it completes, with no error.\n"
 "FAIL: the merge fails after approval, or the work item is stuck at the very last step. This is "
 "the make-or-break of the whole build flow - if it fails, nothing else in this pass matters."),

128: ("DURING A RUN",
 "During the fix-and-re-review loop the reviewer was sometimes pointed at an empty placeholder "
 "instead of the real pull request, and reported 'no opened PR to review', which broke the cycle. A "
 "work item can have more than one code record - an early placeholder the agent registers before "
 "the pull request exists, and the real one carrying the pull-request link - and nothing said which "
 "to use, so the database returned them in an arbitrary order.",
 "The lookup now orders them and explicitly PREFERS the one carrying a real pull-request reference, "
 "falling back to the earliest only if none does.",
 "SET UP: a build that goes through at least one fix-and-re-review cycle.\n"
 "1. Trigger implementation on a task with a defect so the review returns findings.\n"
 "2. Let the fix loop run through several cycles.\n"
 "PASS: every review cycle finds the pull request and reviews it.\n"
 "FAIL: any cycle reporting 'no opened PR to review'.\n"
 "3. Read the review documents from each cycle.\n"
 "PASS: each reviews the real code - none is empty or confused about what it was looking at.\n"
 "4. Check Artifacts & Traceability for that work item.\n"
 "PASS: the code document that the reviews used is the one pointing at the real pull request."),

129: ("DURING A RUN",
 "The safety guard that blocks bad code was rejecting GOOD code. The guard deliberately fails "
 "closed: if a review's wording looks like it demands changes but the structured verdict does not "
 "clearly say so, it blocks. But it scanned the WHOLE review text for blocking-sounding words - so "
 "an APPROVED review that merely MENTIONED an already-resolved finding by its reference was judged "
 "to be demanding changes, and a legitimately approved review was blocked. The pipeline stalled for "
 "no real reason.",
 "The guard now trusts a present, structured APPROVED verdict. A verdict is treated as demanding "
 "changes only when a verdict is actually there and its status genuinely says so. The loose "
 "word-scan is now only a fallback for when there is no structured verdict at all. An approved "
 "review is honoured even if it mentions resolved findings, while a review that truly downgrades "
 "still fails closed.",
 "SET UP: a build that goes through at least ONE fix cycle and then passes - so the final approving "
 "review can naturally mention the findings it resolved.\n"
 "1. Trigger implementation on a task with a defect.\n"
 "2. Let the fix loop resolve the findings.\n"
 "3. Watch the FINAL review, the one that approves.\n"
 "PASS: the build proceeds and the merge gate OPENS.\n"
 "FAIL: the build is blocked or fails even though the review approved - that is the false positive.\n"
 "4. Read the final review document.\n"
 "PASS: it mentions the resolved findings by reference (that is normal and good) AND the build "
 "still went through.\n"
 "5. CONTROL CHECK: a review that genuinely demands changes must still BLOCK.\n"
 "PASS: it does. The guard must not have been loosened into uselessness."),

130: ("SET UP FIRST",
 "Before pushing code the companion scans it for hardcoded passwords, keys and tokens. When it "
 "found one it correctly blocked the push - but reported only a bare count, 'N finding(s)'. It did "
 "not say which secret, which file or which line, and it then deleted the temporary work folder, so "
 "the evidence was gone. Operators saw 'build failed' with no way to know why or how to fix it.",
 "The companion now prints a redacted summary to its own terminal - '[companion] SECRET SCAN "
 "BLOCKED push (N finding(s)) - branch NOT pushed' - listing each finding as '[kind] path:line - "
 "preview', and the same redacted detail travels back so it also appears in the platform's run "
 "console. Only the already-redacted preview is shown, never the raw secret, and the list is capped "
 "at eight with a '(+N more)' tail so the message stays readable.",
 "SET UP: you need a build that WILL trip the secret scanner. The reliable way is to have a task "
 "whose code legitimately writes a config file, then plant an obvious fake key in the repository "
 "the agent will edit - e.g. a line reading AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE in a real source "
 "file (NOT in a .env.example, which is deliberately exempt).\n"
 "1. Run the build and let the scanner block it.\n"
 "2. Read your COMPANION'S terminal.\n"
 "PASS: a line saying the secret scan blocked the push, with the count, and that the branch was NOT "
 "pushed.\n"
 "PASS: each finding is listed with its KIND, its FILE AND LINE, and a redacted preview.\n"
 "PASS: the actual secret value is NOT printed in full.\n"
 "3. Now read the RUN CONSOLE in the app.\n"
 "PASS: the same detail is there - you do not have to be at the machine to diagnose it.\n"
 "4. Check GitHub.\n"
 "PASS: nothing was pushed.\n"
 "FAIL: a bare 'build failed' with no detail, or a raw secret printed anywhere."),

133: ("SET UP FIRST",
 "If the AI build agent errored, the WHOLE companion process died and needed a manual restart. "
 "Because the companion is a long-lived worker handling one build at a time, a single agent error "
 "took the entire worker down: it stopped picking up work, the current run was left hanging, and a "
 "human had to notice and restart it before anything else could proceed.",
 "The companion now catches a build-agent error, reports that build as failed with a message, and "
 "KEEPS RUNNING - mirroring what the planning path already did. An authentication or subscription "
 "problem still stops it deliberately, because that must never be downgraded to a single build's "
 "failure.",
 "SET UP: you need a build agent to error. The most reliable way is to restart the backend "
 "mid-build, which breaks the agent's connection to the platform.\n"
 "1. Start a build and let it get going.\n"
 "2. Restart the backend while the agent is working.\n"
 "3. Watch the COMPANION process.\n"
 "PASS: it reports that build as failed and KEEPS RUNNING. It does NOT exit.\n"
 "4. Check the app.\n"
 "PASS: the run shows as failed with a message - not left hanging for ever.\n"
 "5. Trigger another build WITHOUT restarting the companion.\n"
 "PASS: it is picked up and runs.\n"
 "FAIL: the companion process exits, or you must restart it before any further work will run."),

134: ("DURING A RUN",
 "A worker could DEADLOCK a job by holding on to it while making no progress. The heartbeat that "
 "renews a worker's hold was based on the worker still running, not on the work actually "
 "advancing - so if the worker got wedged while its heartbeat kept ticking, it renewed its hold "
 "indefinitely. The job stayed held, the timeout could not fire because the hold looked fresh, and "
 "no other worker could take it. A silent deadlock only a human would notice.",
 "A first-claim time is now stamped and never touched by the heartbeat, and renewal is capped at "
 "sixty minutes - past that the heartbeat stops renewing, the hold ages out, and the run becomes "
 "recoverable well before the two-hour backstop. The cap is set ABOVE the longest legitimate build, "
 "which the team confirmed is under an hour, so a healthy long build is never cut off.",
 "1. Run several builds of normal length.\n"
 "PASS: none of them is cut off by this cap. Healthy builds must finish - that is the first thing "
 "to confirm.\n"
 "2. Run the LONGEST build you realistically have.\n"
 "PASS: still finishes, as long as it is under an hour.\n"
 "3. If a build ever appears WEDGED - claimed, running, but making no progress for a long time:\n"
 "PASS: within about an hour it becomes recoverable rather than being held forever. You should be "
 "able to retry or take it over.\n"
 "FAIL: a healthy build under an hour being interrupted - or a wedged one still held after several "
 "hours with nothing you can do.\n"
 "NOTE: the wedged case is hard to create deliberately. Watch for it across your testing rather "
 "than trying to force it."),

136: ("SET UP FIRST",
 "The platform merged the feature branch AS IT WAS, never updating it against the current state of "
 "the main branch first. If the main branch had moved on since the branch was cut - normal in any "
 "team - the pull request could be in a conflicted state and the merge failed with an unhelpful "
 "error. It had to be resolved by hand.",
 "Before merging, the platform now checks the pull request's state. If the branch is merely BEHIND, "
 "it updates it against the base and re-checks. If it is genuinely CONFLICTED, it fails fast with a "
 "clear 'merge conflict - needs manual resolution' message rather than an unreadable error code. It "
 "merges only when the pull request is genuinely mergeable.",
 "SET UP: you need a branch that is behind its base. Merge something else into the main branch "
 "while a build's pull request is open.\n"
 "PART A - BEHIND BUT NOT CONFLICTING\n"
 "1. With a build's pull request open, commit an unrelated change to the main branch on GitHub.\n"
 "2. Approve the merge gate.\n"
 "PASS: the platform brings the branch up to date and THEN merges. It succeeds.\n"
 "PART B - GENUINE CONFLICT\n"
 "3. With another build's pull request open, edit THE SAME FILE the build changed, on the main "
 "branch, so the two genuinely conflict.\n"
 "4. Approve the merge gate.\n"
 "PASS: you get a clear message saying there is a MERGE CONFLICT needing manual resolution.\n"
 "PASS: NOT a raw error code or an unreadable exception.\n"
 "5. Resolve the conflict on GitHub and approve again (see S.No 141).\n"
 "PASS: it merges without rebuilding anything.\n"
 "FAIL: an unreadable error, or a merge that silently does nothing."),

137: ("DIRECT",
 "A report that two work items had been planned to create the SAME file, which would guarantee a "
 "conflict when both were built.",
 "Not reproducible - verified against the stored work-item data and closed. The two tasks create "
 "files in DIFFERENT repositories: one is a frontend configuration file, the other is a backend "
 "database task. Different files, different repositories, no collision. The likely confusion was "
 "two correctly-separate files that merely share a NAME. (A genuine instance of this class of "
 "problem was later found and is recorded separately as S.No 210, which remains open.)",
 "There is no fix to test here - the row was closed as not-a-bug after checking the real data.\n"
 "The useful check is the GENERAL one, and it is worth doing while you run builds:\n"
 "1. As you take several tasks through implementation, watch for two builds that genuinely try to "
 "create the SAME file in the SAME repository.\n"
 "PASS: you do not see this.\n"
 "2. If you DO see it, do not record it here - record it as a NEW finding against S.No 210, which "
 "is the open row for exactly this problem, and note the two task numbers and the file.\n"
 "Mark this row 'Verified - not reproducible' unless you find a real instance, in which case say "
 "which tasks and which file."),

139: ("DURING A RUN",
 "When a build failed for any reason other than a blocked secret, you were shown 'build failed' or "
 "a raw error string. A permission problem, a merge conflict, an agent error or an empty build were "
 "all technically present but buried in cryptic text rather than named. An operator had to dig "
 "through logs to work out what had gone wrong.",
 "Every failure path now maps to a plain-language classified reason - merge conflict, permission "
 "problem, remediation exhausted, empty build, agent error - with the good secret-scan message "
 "passing through unchanged. A hidden gap was fixed at the same time: the run console was not even "
 "showing the reason field, so it displayed only 'Build failed'. A follow-up correction unwrapped "
 "the real message from inside the platform's own error wrapper, which had been hiding it; and an "
 "EMPTY build now fails fast with a clear 'no changes' message rather than a cryptic error after "
 "three retries.",
 "Collect failure reasons as you go, across all your build testing. For EVERY failed build:\n"
 "1. Open the Run Console and read the failure line.\n"
 "PASS: a plain-language reason naming what went wrong.\n"
 "FAIL: a bare 'Build failed', a raw exception, a stack trace, or an error code with no "
 "explanation.\n"
 "Specific cases worth deliberately producing if you can:\n"
 "  - EMPTY BUILD: build a task the agent has nothing to do for.\n"
 "    PASS: fails quickly with a clear 'no changes' message - and it FAILS rather than pretending "
 "to succeed.\n"
 "  - MERGE CONFLICT: see S.No 136.  PASS: says 'merge conflict'.\n"
 "  - PERMISSION: use a token without access to the repository.  PASS: says it is a permission "
 "problem.\n"
 "Record every failure reason you saw in your comment - that list is the real evidence for this "
 "row."),

141: ("SET UP FIRST",
 "A merge conflict marked the ENTIRE build failed and ended it, so finishing meant re-running "
 "everything - the AI rewriting the code, re-reviewing it, re-opening the pull request - just to "
 "retry one merge.",
 "A merge conflict is now NON-TERMINAL. The platform detects it, RE-OPENS the merge gate (resetting "
 "the approval to pending and recording the conflict), and WAITS. You resolve the conflict on "
 "GitHub and approve again, and the platform retries ONLY the merge - no rebuild, no re-review. The "
 "merge gate shows a warning banner explaining the conflict and the retry, and only on a re-opened "
 "merge gate, never on other gates. Proven live: a conflict was injected, the gate re-opened, the "
 "conflict was resolved, and the platform merged - with no rebuild across the retries.",
 "SET UP: a build at its merge gate. You will create a conflict deliberately.\n"
 "1. With the pull request open, edit the SAME file the build changed, on the main branch, so they "
 "genuinely conflict.\n"
 "2. Approve the merge gate.\n"
 "PASS: the build does NOT fail. The merge gate RE-OPENS and waits.\n"
 "PASS: a warning banner on that gate explains there is a conflict and that you can retry after "
 "resolving it.\n"
 "3. Check the run.\n"
 "PASS: still alive - not failed, not ended.\n"
 "4. Resolve the conflict on GitHub.\n"
 "5. Approve the gate again.\n"
 "PASS: the platform merges. The work item reaches done.\n"
 "6. THE KEY CHECK: confirm NO rebuild happened.\n"
 "PASS: the AI did NOT rewrite the code and the review did NOT run again. Only the merge was "
 "retried.\n"
 "7. Look at a DIFFERENT gate that has no conflict.\n"
 "PASS: no conflict banner there - it appears only where it applies.\n"
 "FAIL: the build failing outright on a conflict, or a full rebuild being required."),

144: ("SET UP FIRST",
 "The secret scanner flagged an obvious PLACEHOLDER as a real secret and blocked the push, failing "
 "the build. The value was 'change-me-minimum-32-characters-long' in an example configuration file "
 "- unmistakably a placeholder. The scanner's list of known placeholders recognised 'changeme' but "
 "not the far more common hyphenated 'change-me'. The build agent had done nothing wrong; the "
 "scanner was too aggressive.",
 "Two changes. The placeholder list was broadened to cover change-me, replace-me, to-be-changed / "
 "set / replaced / filled / generated, secret-here, dummy, sample and redacted, in any hyphenated "
 "or underscored form. And committed TEMPLATE files - .env.example, .sample, .template, .dist, "
 ".tpl - now skip the general guesswork, since placeholders are expected there, while STILL running "
 "the precise checks for real key shapes, so an actual AWS or GitHub key or a private key pasted "
 "into an example file is still blocked.",
 "SET UP: a repository where you can add files, and a task that will build.\n"
 "1. Add a .env.example containing placeholder values in the common styles: "
 "JWT_SECRET=change-me-minimum-32-characters-long, API_KEY=replace-me, DB_PASSWORD=to-be-set\n"
 "2. Run a build that includes that file.\n"
 "PASS: the push is NOT blocked. The build proceeds.\n"
 "3. NOW THE CONTROL TEST, which matters just as much. Put a REAL-SHAPED key into the SAME "
 ".env.example - e.g. AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE, or a line beginning "
 "'-----BEGIN RSA PRIVATE KEY-----'.\n"
 "4. Run a build including that.\n"
 "PASS: the push IS BLOCKED. The scanner must not have been weakened into letting real keys "
 "through - that would be a far worse outcome than the original bug.\n"
 "5. Put a genuinely random-looking secret into an ORDINARY source file (not a template).\n"
 "PASS: blocked.\n"
 "FAIL: a placeholder blocking a build - or, much worse, a real key shape getting through."),

161: ("DURING A RUN",
 "When the fix-and-re-review loop ran out of attempts, the build hard-failed and stopped. The run "
 "console showed only the COUNTS of blocking findings across the cycles - 2, then 1, then 3, then 3 "
 "- with no visibility into what the findings actually were, and there was no automatic retry, so a "
 "human had to step in. If the loop kept exhausting, the work item was simply stuck.",
 "The actual blocking-finding detail - reference, severity, title, file and line - is now recorded "
 "per cycle rather than just counts. And on exhaustion the platform now starts a FRESH ATTEMPT "
 "automatically (up to two by default), marking the current run failed with a clear 'auto-retrying' "
 "message and seeding the new attempt with a summary of what blocked the previous one. Only after "
 "all automatic attempts are used up does it park for a human.",
 "SET UP: a task whose review findings are hard to resolve, so the loop exhausts. Introducing "
 "several defects at once helps.\n"
 "1. Trigger implementation and let the fix loop run to exhaustion.\n"
 "2. Read the run console.\n"
 "PASS: you can see WHAT the blocking findings were in each cycle - reference, severity, title, "
 "file and line.\n"
 "FAIL: only bare numbers such as '2 -> 1 -> 3 -> 3'.\n"
 "3. Watch what happens after exhaustion.\n"
 "PASS: the platform starts a FRESH ATTEMPT on its own, with a clear message saying it is "
 "auto-retrying. You did not have to do anything.\n"
 "4. Follow the link to the new attempt (see S.No 208).\n"
 "PASS: it is there and running.\n"
 "5. Let both automatic attempts be used up.\n"
 "PASS: only THEN does it stop and wait for you, with a clear explanation.\n"
 "FAIL: a hard failure on the first exhaustion with no diagnostics and no retry."),

162: ("SET UP FIRST",
 "A build's remediation could start from an EMPTY folder, or fail to push, when a different machine "
 "continued a work item than the one that started it. Each companion set up its work folder from "
 "its own local copy of the branch, so a second machine either had a stale copy or none at all - "
 "producing an empty build, or a push that was rejected.",
 "The companion now asks the REMOTE authoritatively whether the branch exists. If it does, it "
 "fetches and bases the work folder on the remote's version, so ANY machine continues from the true "
 "shared state; it falls back to the base branch only for a genuinely new branch.",
 "SET UP: this needs TWO machines, or one machine whose local copy you can deliberately stale. If "
 "you have only one machine, do the single-machine half.\n"
 "TWO MACHINES:\n"
 "1. Start a build on machine A and let it push its branch.\n"
 "2. Stop machine A's companion. Start machine B's, mapped to the same repository.\n"
 "3. Let the remediation cycle run on machine B.\n"
 "PASS: it continues from the work already pushed - it does NOT produce an empty build and its push "
 "is NOT rejected.\n"
 "PASS: new commits land on the SAME branch.\n"
 "ONE MACHINE:\n"
 "4. After a build pushes its branch, delete the local branch and the work folder on your machine.\n"
 "5. Let the remediation cycle run.\n"
 "PASS: it fetches the branch from GitHub and continues from there.\n"
 "FAIL: an empty build, or a push rejected as out of date."),

199: ("DURING A RUN",
 "A test-automation run failed with a database error about an unsupported character, AFTER the pull "
 "request and its documents had already been created - even when the generated test itself had "
 "passed. The review briefing includes the content of every changed file, and a test-automation "
 "build commits screenshots and videos into the pull request; those binary files contain characters "
 "the database cannot store, so saving the briefing failed and the run parked.",
 "Binary files are now SKIPPED in the review briefing, with a '(binary file - omitted from review)' "
 "note in their place, and the whole payload is cleaned of those characters before saving as a "
 "second line of defence. The companion's own reports are cleaned the same way. (The related fix "
 "that stops the binaries being committed in the first place is S.No 201.)",
 "SET UP: a test-automation build - the one that generates and runs browser tests, which produce "
 "screenshots and videos.\n"
 "1. Trigger the test-automation phase on a suitable work item.\n"
 "2. Let it run all the way through the pull request and into code review.\n"
 "PASS: the run does NOT fail with a database or character error after the pull request is created.\n"
 "PASS: the code review runs normally.\n"
 "3. Read the code review's briefing or report where it lists the changed files.\n"
 "PASS: any binary file is noted as omitted rather than causing a failure.\n"
 "4. Check the run reaches its merge gate.\n"
 "PASS: it does.\n"
 "FAIL: a run parking with an error mentioning an unsupported character or an escape sequence."),

200: ("DURING A RUN",
 "A test-automation build that was automatically fixing a review finding failed IMMEDIATELY with "
 "'no preview target for this repo - set the repo's Preview URL...', even though the Preview URL "
 "was already set and the first build had just run against it successfully. The re-dispatch for the "
 "fix cycle simply did not carry the preview address through.",
 "The remediation dispatch now carries the same preview address as the initial one, applied to the "
 "same phase.",
 "SET UP: a repository with its Preview URL set, and a running application at that address.\n"
 "1. Trigger the test-automation phase and let the FIRST build succeed.\n"
 "PASS: it runs against your preview address.\n"
 "2. Let the code review return a finding, so a fix cycle starts.\n"
 "3. Watch the remediation build.\n"
 "PASS: it starts normally and runs against the SAME preview address.\n"
 "FAIL: it fails instantly saying there is no preview target, even though the Preview URL is "
 "plainly set on the repository."),

201: ("DURING A RUN",
 "The test-automation agent committed its own generated OUTPUT into the pull request alongside the "
 "test script it wrote - the browser test report, the results folder, exploration snapshots. Those "
 "are bulky (one pull request carried a 533 KB report page plus screenshots and a video) and can be "
 "binary, which was the root cause of the failure in S.No 199. The code review independently "
 "flagged it as a problem too.",
 "The agent is now required to create or extend a .gitignore at the top of the work folder excluding "
 "the generated report and results folders and the framework's build and cache folders, while still "
 "committing the test scripts, page objects and configuration it authored.",
 "SET UP: a test-automation build on a FRESH branch. Note: on a branch where an earlier run already "
 "committed those files, they stay tracked - that is a separate open row, S.No 205.\n"
 "1. Trigger test automation on a work item that has NOT been built before.\n"
 "2. Let it finish and open the pull request on GitHub.\n"
 "3. Look at the files it changed.\n"
 "PASS: the authored test scripts, page objects and configuration ARE there.\n"
 "PASS: generated output is NOT - no report folder, no results folder, no screenshots, no videos, "
 "no exploration snapshots.\n"
 "4. Look for a .gitignore in the pull request.\n"
 "PASS: one exists (or was extended) and lists those folders.\n"
 "5. Check the pull request's size.\n"
 "PASS: reasonable - not hundreds of kilobytes of report files.\n"
 "FAIL: generated reports, screenshots or videos committed into the pull request."),

203: ("SET UP FIRST",
 "The companion always ran the browser automation invisibly, so a developer sitting at the machine "
 "could not watch the agent explore the app or see the generated tests run, even when they were "
 "there and wanted to.",
 "A flag was added that runs the browser visibly, and 'serve --headed' was made a first-class option "
 "so no separate setup is needed. The generated test configuration is written so that it still runs "
 "invisibly in automation. The default stays invisible.",
 "SET UP: run your companion with the --headed option: python -m runner.companion serve --headed ... "
 "(plus your usual options).\n"
 "1. Trigger the test-automation phase.\n"
 "2. WATCH YOUR SCREEN while it runs.\n"
 "PASS: a browser window opens and you can SEE the agent exploring the app and the tests running.\n"
 "3. Let it finish and look at the generated test configuration in the pull request.\n"
 "PASS: it is written so the same tests still run invisibly when run automatically - it is not "
 "hardcoded to be visible.\n"
 "4. Now restart the companion WITHOUT --headed and run test automation again.\n"
 "PASS: nothing visible - the default is unchanged.\n"
 "FAIL: --headed shows nothing, or the default suddenly opens browser windows on everybody."),

207: ("DIRECT",
 "Clicking 'Retry run' on a build whose branch a previous attempt had already pushed failed with "
 "'Empty build: the agent produced no changes to commit' - even though real work already existed on "
 "that branch. The retry correctly picked up the pushed branch, but because the agent made no NEW "
 "local commit, the guard that catches genuinely empty builds fired even though the branch was "
 "plainly ahead of the base.",
 "The companion now reports the existing branch tip when there is no new local commit but the branch "
 "is already ahead of its base, so the pipeline opens or continues the pull request against the work "
 "that exists instead of falsely failing.",
 "SET UP: a build that has pushed its branch and then failed for some other reason - a review "
 "problem or a merge issue will do.\n"
 "1. Confirm the branch exists on GitHub with real commits on it.\n"
 "2. Click 'Retry run' on that build.\n"
 "PASS: it does NOT fail with 'Empty build: the agent produced no changes to commit'.\n"
 "PASS: it continues against the existing branch and the pull request opens or continues.\n"
 "3. CONTROL CHECK: retry a build whose agent genuinely produced nothing and has NO branch.\n"
 "PASS: THAT one still correctly fails as empty - the guard must not have been removed, only "
 "corrected.\n"
 "FAIL: a false empty-build failure on a branch that plainly has commits."),

208: ("DIRECT",
 "A follow-on. When the fix loop exhausted an attempt and the platform automatically started a "
 "FRESH run, you got no signal: the failed run's console said 'auto-retrying' but gave no link to "
 "the new run, so a work item appeared to show a failed run AND a separate pending gate with "
 "nothing connecting them.",
 "The failed view now reads the retry run's reference and shows an information banner - 'The "
 "platform started a fresh attempt...' - with a live status link to the retry run, and the main "
 "button becomes 'Go to the retry run' when one exists.",
 "SET UP: a build whose fix loop exhausts, so the platform starts a fresh attempt automatically "
 "(see S.No 161).\n"
 "1. When the first attempt fails, open its Run Console.\n"
 "PASS: an information banner says the platform has started a fresh attempt.\n"
 "PASS: there is a LINK to the new run, showing its live status.\n"
 "PASS: the main button reads 'Go to the retry run', not just 'Retry'.\n"
 "2. Click it.\n"
 "PASS: it takes you to the new run, which is genuinely running.\n"
 "3. Open the work item.\n"
 "PASS: you can tell the failed run and the new run belong together - they do not look like two "
 "unrelated things.\n"
 "FAIL: a failed run with no link to the attempt that replaced it."),

239: ("SET UP FIRST",
 "The secret scanner kept blocking legitimate builds - FIVE times across two workspaces, each time "
 "in a new shape. The latest blocked on the text 'configService.getOrThrow' - the code that READS a "
 "secret from configuration, not a secret at all. Earlier ones: 535 findings across one dependency "
 "install (all just variable names), a variable called refresh_token_expiry_seconds, a change-me "
 "placeholder, and mock tokens in a test file. Each previous fix had added a narrower exception "
 "than the actual problem, so the problem came back in a new shape every time.",
 "The rule was corrected at the root rather than exception by exception. A hardcoded credential in "
 "code is ALWAYS a quoted string; an unquoted value after a secret-sounding name is an expression "
 "and can never be a leak. So the scanner now scores STRING LITERALS only, with the unquoted form "
 "checked only where an unquoted value can genuinely be a literal - configuration-shaped files, or "
 "a comment line. Detection is unchanged on every genuine leak. A test corpus now pins every shape "
 "that has ever wrongly blocked. Two more things shipped with it: the implementation agent was "
 "never told the scanner exists (only the CI/CD agent was) and now carries the same rule; and a "
 "block now gets one bounded automatic retry seeded with the redacted findings instead of being a "
 "dead end.",
 "This is the FALSE-POSITIVE test. The true-positive test is S.No 144 - do both.\n"
 "SET UP: a repository you can add files to.\n"
 "1. Add code containing all of these, in ordinary source files:\n"
 "   - a call that READS a secret, e.g. const secret = configService.getOrThrow('JWT_SECRET')\n"
 "   - a variable named for a token, e.g. self.refresh_token_expiry_seconds = 3600\n"
 "   - a mock token in a TEST file\n"
 "   - a comment mentioning a token by name\n"
 "2. Run a build that includes them.\n"
 "PASS: the push is NOT blocked. None of these is a secret.\n"
 "3. THE CONTROL TEST: add a genuine hardcoded credential as a QUOTED STRING in an ordinary source "
 "file - e.g. const password = \"hR7$kLm2!pQ9zXw4\"\n"
 "4. Run a build.\n"
 "PASS: BLOCKED. The scanner must still catch real leaks.\n"
 "5. When a block does happen, watch what follows.\n"
 "PASS: one automatic retry runs, and the agent is told what tripped - it is not a dead end.\n"
 "FAIL: a legitimate build blocked - or, far worse, a real quoted credential getting through."),

240: ("DURING A RUN",
 "NINE builds across two workspaces failed with a byte-for-byte identical message and none could be "
 "diagnosed. They lasted anywhere from 12 seconds to 75 minutes, so they cannot all have shared one "
 "cause - at least two different problems were wearing the same label. The worst case destroyed a "
 "run that already had a working pull request and a completed code review, 12 minutes into a fix "
 "cycle. Three losses stacked: the real cause travelled on a channel that was being discarded "
 "outright; the library hardcoded a placeholder where the real error should have been; and "
 "everything the run had accomplished was held in memory and thrown away when it failed. On top of "
 "that the platform ASSERTED 'the most common cause is a usage limit' - a guess stated as a "
 "finding, which steered the investigation the wrong way.",
 "Five changes. The engine's own diagnostic output is now captured for the duration of a run. What "
 "the run had achieved - how many messages, how many documents registered, the cost, the tail of "
 "the agent's last output - is now folded into the error, so a 12-second failure can never again "
 "read like a 12-minute one. A rotating companion log FILE was added: there was no log file at all "
 "before, which is why eight of the nine were unrecoverable. The failure message stops asserting a "
 "cause, shows the engine's own output, decodes the usage-limit reset time when there is one, and "
 "names the log file. And an engine exit now PARKS rather than ending the run, so the pull request "
 "and review survive and Resume re-dispatches.",
 "1. Run several builds. If any fails with the engine having exited, read the Run Console.\n"
 "PASS: the message shows the ENGINE'S OWN output - not a generic placeholder.\n"
 "PASS: it does NOT assert 'the most common cause is a usage limit' as though that were a finding.\n"
 "PASS: it says how far the run got - messages, documents registered, cost.\n"
 "PASS: it NAMES the log file to look in.\n"
 "2. Go and find that log file on the companion machine.\n"
 "PASS: it exists and contains the engine's diagnostics.\n"
 "3. Check what happened to the run.\n"
 "PASS: it PARKED rather than ending. The pull request and any completed review SURVIVE, and there "
 "is a Resume option.\n"
 "4. Click Resume.\n"
 "PASS: it re-dispatches and carries on - it does not rebuild from scratch.\n"
 "5. If you hit a genuine USAGE LIMIT:\n"
 "PASS: the message says so, and gives the reset time.\n"
 "FAIL: an identical opaque message with no detail, no log file, and a run that ended for good."),

241: ("DURING A RUN",
 "One task ran for TWENTY-SIX HOURS across two runs, twenty review cycles and fifteen rebuilds "
 "without ever clearing review. A QA member resumed it four times; each resume granted a fresh "
 "budget and hit the same wall. The reviewer was blocking on one thing while the implementation "
 "agent was repeatedly asked to fix a DIFFERENT thing it had already fixed fifteen cycles earlier. "
 "The loop could not converge by construction. The cause: a finding's reference is a POSITION in "
 "one review's output, not an identity - the reviewer numbers its findings from 1 every time - and "
 "the remediation item was written once at creation and never updated, so its title, description, "
 "file and line stayed frozen at cycle 1 for ever, while the agent was briefed from exactly those "
 "frozen fields.",
 "Three parts. The remediation item's title, description, severity, file and line are now rewritten "
 "from the CURRENT finding every cycle, and it is recorded when the meaning behind a reference "
 "really changes, so a collision is visible rather than hidden. The review briefing gained a "
 "'findings already open from your previous review' section listing the live references with their "
 "file and line, so the reviewer can reuse them as its own instructions require. And the open "
 "remediation board is CLOSED before a fresh attempt starts, so a new attempt does not inherit the "
 "previous one's stale items.",
 "SET UP: a build that goes through SEVERAL review cycles - three or more. Introduce a couple of "
 "defects.\n"
 "1. Trigger implementation and let the review loop run.\n"
 "2. After EACH cycle, open the remediation work items on the board and read them.\n"
 "PASS: their titles, descriptions, files and lines reflect the CURRENT cycle's findings.\n"
 "FAIL: a remediation item still describing something from cycle 1 that has since been fixed. That "
 "is the exact bug.\n"
 "3. Watch the finding count across cycles.\n"
 "PASS: it comes DOWN and the loop converges.\n"
 "FAIL: it plateaus at the same number cycle after cycle - the sign of an unwinnable loop.\n"
 "4. Compare what the review is blocking on against what the remediation item says.\n"
 "PASS: they are the SAME thing.\n"
 "5. If a fresh attempt starts automatically, check the remediation board.\n"
 "PASS: the previous attempt's items are closed - the new attempt starts clean.\n"
 "6. Note the total elapsed time.\n"
 "PASS: it converges in a sensible number of cycles - nothing like twenty."),

243: ("DURING A RUN",
 "A task's description told the implementation agent, in one sentence carrying four requirements, "
 "to do four things. Three were delivered. The fourth - configuring the API to accept requests from "
 "the web app's address - was silently dropped, the review agent PASSED the pull request, the merge "
 "gate was approved, and the task was marked done and merged. The miss stayed invisible for "
 "EIGHTEEN DAYS and twenty-nine further tasks, because nothing in the pipeline ever opens a "
 "browser. It surfaced only when a QA member tried to open the product for the first time and every "
 "request died before it left the browser. The requirement had been stated twice and missed both "
 "times, so this is a systematic gap, not a slip.",
 "The cause recorded on this row turned out to be WRONG, and building to it would have fixed "
 "nothing: the review agent IS given the acceptance criteria and always had the instruction to "
 "cross-check them. The real gap was the OUTPUT contract - nothing required a per-criterion "
 "verdict, so an approving verdict with no findings looked identical whether the agent had checked "
 "four criteria or skimmed the diff. Two halves shipped: the review agent must now emit a "
 "PER-CRITERION verdict - the criterion's text verbatim, met / not met / not verifiable, concrete "
 "evidence, and any 'not met' also raised as a blocking finding - and the build FAILS CLOSED when "
 "an approving verdict does not satisfy that. It deliberately does not fire when no criteria can be "
 "found, or when the review already demands changes. This also needed the fix at S.No 251, which "
 "was letting the criteria be cut off before any agent read them.",
 "SET UP: a task whose description contains a SENTENCE WITH SEVERAL REQUIREMENTS IN IT - that is "
 "the shape that broke. For example: 'Add a health endpoint, enable request validation, publish the "
 "API documentation at /docs, and configure CORS for the front-end address.'\n"
 "1. Trigger implementation on that task and let it run to code review.\n"
 "2. Open the code review document.\n"
 "PASS: it contains a PER-CRITERION list: each acceptance criterion quoted, marked met / not met / "
 "not verifiable, with concrete EVIDENCE for each.\n"
 "FAIL: an approving verdict with no per-criterion breakdown - that is the exact gap.\n"
 "3. Count them against the task's criteria.\n"
 "PASS: every criterion is accounted for. None is silently missing.\n"
 "4. Check each 'met' against the actual code in the pull request.\n"
 "PASS: the evidence is real.\n"
 "5. THE NEGATIVE TEST: deliberately have the agent miss one - the simplest way is a criterion "
 "buried at the very end of a long multi-part sentence.\n"
 "PASS: the review marks it NOT MET, raises it as a blocking finding, and the build does NOT sail "
 "through to the merge gate.\n"
 "6. Finally, open the finished product in a BROWSER and use it end to end.\n"
 "PASS: it actually works. This row exists because everything passed and the product could not be "
 "opened."),

}
