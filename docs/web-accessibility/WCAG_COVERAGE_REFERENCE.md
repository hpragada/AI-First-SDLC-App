# WCAG 2.2 Coverage — what we actually check, and how to prove it

**Written 2026‑08‑27. Every number here was measured, not read.**

**What this file is for.** Three different questions in this project all got called "coverage", they give three different numbers, and the team was quoted a different one each time it asked. This is the single place that answers all three separately, says where each answer comes from in the code, and gives you the commands to re‑derive it yourself. Read it before quoting a coverage figure to anyone, and before deciding which criterion to build next.

**It is a reference, not a report.** It is expected to be edited whenever a check is added or removed. The tests named throughout are what stop it going stale silently.

---

## 1. The three questions people mean by "coverage"

| The question | Where the answer lives | Today's answer |
|---|---|---|
| **PLAN** — who *should* decide this criterion? | [ownership.json:35-49](../../backend/apps/a11y/data/ownership.json) `counts.by_owner` | the file says rule **14** · AI **11** · human **30**; routing is rule **13** · AI **12** · human **30** |
| **SCHEDULE** — when is a check *meant* to ship? | same file, `counts.by_tier` | POC **19** · Phase 2 **21** · human **15** |
| **REALITY** — what engine actually runs today? | the code, section 2 below | covered **27** · partial flag **5** · nothing **23** |

**All three are correct answers to different questions.** The confusion was never a mistake; it was three answers wearing one name.

> **Quote REALITY.** If you need the plan, say "the plan" out loud. The registry describes what the research report concluded was *possible*; it has never described what is *built*.

**The two PLAN numbers, and why there are two (noted 16 September 2026).** `ownership.json` is a derivation, rebuilt from the committed research report, so the team's corrections are applied as a layer over it rather than edited into it: `ENGINEERING_OVERRIDES` in [ownership.py](../../backend/apps/a11y/ownership.py) moves **1.4.11 Non-text Contrast** from `rule` to `ai` (correction **R14**, agreed 2026‑08‑27), recording `page_rules` as the rule engine's contribution. So every routing question — which criteria does the AI decide, which does the rule engine — is answered **13 rule / 12 AI**, while the data file's own `counts.by_owner` still reads 14 / 11 and will keep reading that until the registry is reconciled during the build. Quote whichever you mean, and say which one it is.

---

## 2. REALITY — the five buckets, as of 2026‑08‑28

> **Two of these buckets only became true on 28 August.** `1.3.4` and `2.5.3` were listed here as
> scanner-covered, and axe does ship a rule for each — but neither rule was running. axe holds
> `experimental` rules out of a tag-selected scan silently, and both of those rules are
> experimental. The scan now names them explicitly, so the buckets below describe what happens
> rather than what was meant to. See defect #10 in section 6.

Five buckets. They add to 55.

### Bucket 1 — the rule scanner decides it alone (12)

`1.3.4` `1.3.5` `1.4.2` `1.4.3` `1.4.4` `1.4.12` `2.4.1` `2.4.2` `2.5.8` `3.1.1` `3.1.2` `3.3.2`

Backed by axe‑core 4.13.0. **Six of these twelve are thinner than they look** — see section 5.

`1.3.4` rests on a single rule, `css-orientation-lock`, which axe marks experimental and does not run unless it is named. Until 28 August it was not named, so this criterion was recorded as machine-checked with nothing checking it — the same shape as 1.4.10 and 1.4.11 in section 4.

### Bucket 2 — the platform's own rule decides it alone (1)

`1.4.10` **Reflow** — axe has no rule for it, so we measure it ourselves: the browser narrows to 320×256, reports two numbers and what stuck out, and [page_rules.py](../../backend/apps/a11y/page_rules.py) rules on them. Deterministic, no AI, with the standard's own two‑dimensional exception applied from a fixed list of container kinds.

### Bucket 3 — a rule and a judge, together, and neither alone (1)

`1.4.11` **Non-text Contrast** — a criterion in two halves:

| Half | Who answers it |
|---|---|
| Can you see where the controls are? | [page_rules.contrast_failures](../../backend/apps/a11y/page_rules.py) — colours and a 3:1 threshold |
| Are the meaningful parts of icons and diagrams visible? | the `graphics` element checker — you must know which parts carry meaning before a ratio means anything |

### Bucket 4 — AI on top of the rule scanner (6)

| Criterion | The scanner does | The AI does |
|---|---|---|
| 1.1.1 Non-text Content | finds missing alt (7 rules) | judges whether the alt is *meaningful* |
| 1.3.1 Info & Relationships | 12 rules on lists and tables | two checkers: fake headings, and real table structure |
| 1.4.1 Use of Color | links in text blocks only | meaning carried by colour alone |
| 2.5.3 Label in Name | one string-match rule, `label-content-name-mismatch` — experimental, and only running since 28 Aug | judges the match properly |
| 4.1.2 Name, Role, Value | 29 rules on ARIA | catches a `div` pretending to be a button |
| 2.1.1 Keyboard | 3 narrow rules | the keyboard agent walks the app |

### Bucket 5 — AI alone; no scanner rule exists (7)

`2.1.2` `2.4.3` `2.4.7` `2.4.11` `3.2.1` `3.2.2` `4.1.3`

Two of them — `2.4.7` and `4.1.3` — also get a deterministic measurement the platform wrote itself ([journey_rules.py](../../backend/apps/a11y/journey_rules.py)). Not axe. Ours.

> **Buckets 1–5 = 27. That is the real coverage number.**

### Not covered — a corner is flagged, a human decides (5)

`1.2.1` `1.2.2` `2.2.1` `2.2.2` `2.4.4`

axe fires a rule, but it checks a sliver of the criterion. **Never count these as covered.** Until 2026‑08‑27 one of them could produce a "Supports" claim on its own — see section 6, defect #6.

### Not covered — nothing checks it (23)

`1.2.3` `1.2.4` `1.2.5` `1.3.2` `1.3.3` `1.4.5` `1.4.13` `2.1.4` `2.3.1` `2.4.5` `2.4.6` `2.5.1` `2.5.2` `2.5.4` `2.5.7` `3.2.3` `3.2.4` `3.2.6` `3.3.1` `3.3.3` `3.3.4` `3.3.7` `3.3.8`

Of these, **12 get a designer's question** at the design review, 4 more are written and switched off by default, and **7 are asked nowhere at any stage**.

---

## 3. How to re-derive every number in this file

Nothing here has to be trusted. Four commands.

**What the scanner actually covers** — regenerated from the installed axe, never hand-written:

```bash
python manage.py build_scanner_coverage --check
```

**The guard that proves no criterion is claimed by an engine that cannot check it:**

```bash
python -m pytest tests/test_a11y_owner_capability.py -q
```

**The guard that proves a narrow rule pass cannot claim conformance:**

```bash
python -m pytest tests/test_a11y_conformance_guard.py -q
```

**The two page-level rules, against known colours and known widths:**

```bash
python -m pytest tests/test_a11y_page_rules.py -q
```

**The single source of truth for each column:**

| Fact | Read it here |
|---|---|
| The 55 criteria, and their levels | `a11y_wcagcriterion` table · [wcag22.json](../../backend/apps/a11y/data/wcag22.json) |
| Who the plan says decides each one | [ownership.json](../../backend/apps/a11y/data/ownership.json) |
| What axe covers, per criterion, per rule | [scanner_coverage.json](../../backend/apps/a11y/data/scanner_coverage.json) — **generated** |
| The tags the audit scans with | [a11y_audit.mjs](../../runner/companion/assets/a11y_audit.mjs) — `values: [...]` |
| The element checkers | `A11Y_CHECKER_CRITERIA` in [types.py](../../backend/integrations/types.py) |
| The journey checkers | `A11Y_JOURNEY_CRITERIA` in the same file |
| The platform's own rules | `platform_rule_criteria()` in [scanner_coverage.py](../../backend/apps/a11y/scanner_coverage.py) |
| What the designer is asked | `DESIGN_CHECKS` in [gates/wcag.py](../../backend/apps/gates/wcag.py) |

> **Never write a criterion list into a document by hand.** Every list above is derived from something that would break if it were wrong. A list typed into a slide is a list that goes stale in silence, which is the whole subject of section 4.

---

## 4. Why 1.4.10 and 1.4.11 were missed — the failure mode to watch for

Nobody made a mistake. **A true statement about the plan was inherited as a true statement about the build**, in four steps, each reasonable on its own.

1. **The research said a rule could decide them, and it was right.** Addendum A defines RULE as *"a deterministic engine can decide the typical case with high confidence"*. True of resizing a window and of comparing two colours. **It never said which rule, or that anyone had written one.**
2. **We proved the list very carefully, and proved the wrong thing.** The registry is generated by parsing that report with eight cross-checks. Every one asks *does our list match the paper?* Not one asks *does the paper match our scanner?*
3. **"The rule engine" quietly became "axe-core."** A correct decision (D‑A11Y‑9) that was never re-checked against what axe ships. It ships no rule tagged `wcag1410` and none tagged `wcag1411`; both are well-known gaps, and non-text contrast is in Deque's paid product.
4. **The report stayed honest, and that hid it.** Both printed as **"Not evaluated"** — correctly. On a real audit around thirty criteria print that, and two more inside a list of thirty were indistinguishable.

**And one compounding factor.** The design review deliberately skipped Reflow, on the written grounds that *"a rule scanner decides this on the built page"*. So it was the one criterion in the standard that every net was built to let through.

### What now makes it impossible to recur

Two completeness proofs already existed and neither caught it:

| Proof | What it guarantees |
|---|---|
| `ownership.verify_complete()` | every criterion has an owner |
| `gates.wcag.verify_complete()` | every criterion is asked at design, or recorded as deliberately not asked |

**Neither asked whether the named owner is *able*.** That question is now [test_a11y_owner_capability.py](../../backend/tests/test_a11y_owner_capability.py), which fails by name against a generated inventory of what the pinned scanner really covers. Run against axe alone it reports exactly `['1.4.10', '1.4.11']` — it reproduces the original bug.

It also checks the design gate's own excuses: a criterion skipped at design because "something checks it on the built page" must have something that does. **That check found three more** — see defect #3.

> **The lesson, in one line: a claim about a tool is not a test of the tool.** If a document, a comment or a bucket name asserts that some engine handles something, there should be a test that asks the engine.

---

## 5. The six criteria whose scanner coverage is thinner than it looks

A rule fires for each of these and can fail the page, so **none is a hole**. But the registry's rationale describes more than the rule does. Recorded in `THIN_SCANNER_COVERAGE` in the capability test, with an assertion that fails if an axe upgrade *deepens* one — so this list shrinks when reality improves.

| Criterion | The plan says | The rule actually does |
|---|---|---|
| **1.3.5** Identify Input Purpose | check autocomplete tokens | checks tokens that are **present**; a field with no `autocomplete` raises nothing |
| **1.4.4** Resize Text | render at 200%, detect clipping | checks only that zoom is not disabled |
| **1.4.12** Text Spacing | apply spacing overrides, detect clipping | checks only for inline `!important` that would block an override |
| **2.4.2** Page Titled | title present and non-empty | presence only; descriptiveness is the unbuilt AI half |
| **3.1.2** Language of Parts | detect lang on foreign passages | validates values that exist; a passage with **no** `lang` raises nothing |
| **3.3.2** Labels or Instructions | catches missing labels | only "field has two labels". **The missing label IS caught** — by axe's `label` rule — but axe tags that to **4.1.2**, so it is filed under a different criterion |

**Not "fixed" in code, deliberately.** Re-tagging a vendor's own rule inside our reader would be the platform quietly disagreeing with the scanner it names in a signed statement.

---

## 6. The nine defects found on 2026‑08‑27, and what happened to each

| # | What was wrong | Outcome |
|---|---|---|
| **1** | 1.4.10 and 1.4.11 marked `rule` + `in_poc` with no engine behind either | **Fixed** — both now measured by `page_rules`; `graphics` checker added for 1.4.11's other half |
| **2** | 1.4.11's own rationale said review was needed, yet it was labelled rule-only | **Fixed** — built as rule + judge; recorded as **R14** in `RESEARCH_CORRECTIONS.md`. The derived registry is *not* hand-edited (regenerating would revert it) |
| **3** | Design gate skipped 1.4.10 because "a scanner decides this on the built page" — untrue | **Fixed**, and the same check found **three more**: 1.3.2, 1.3.3 and 1.4.5 were skipped on the same false reason. Split into a new `deferred_to_a_later_phase` bucket whose reason is true. Recorded as **R17** |
| **4** | No proof that a named owner can actually perform its check | **Fixed** — `test_a11y_owner_capability.py` plus the generated scanner inventory |
| **5** | 3.3.2's rationale overstates its rule backing | **Recorded** as R15 + pinned in `THIN_SCANNER_COVERAGE`. No code change — see section 5 |
| **6** | A narrow rule pass could claim **"Supports"** for a criterion only a human can settle | **Fixed** — `conformance._can_claim_positive`. See below |
| **7** | 1.4.4 and 1.4.12 rationales describe work axe does not do | **Recorded** as R15 + pinned |
| **8** | OP‑02 told us to reuse an AI check that was never built (2.4.6) | **Fixed** in `TASK_BACKLOG_OTHER_PHASES.md`; recorded as **R16** |
| **9** | Coverage rows written for 2.1.3, a Level AAA criterion no report reads | **Fixed** — `coverage.record` filters to the levels the audit is about |
| **10** | Five axe rules matched our tag filter and never ran. Two criteria — **1.3.4 Orientation** and **2.5.3 Label in Name** — have no other rule, so both were reported as scanner-covered with nothing behind them. Found 2026‑08‑28 | **Fixed** — the scan now names all five; `scanner_inventory.mjs`, which had been counting them without checking they run, corrected; a parity test added so the two lists cannot drift again. Recorded as **R18** |

### Defect #6 in detail, because it was the worst one

axe ships `video-caption`, which proves a `<video>` carries a caption **track**. That pass was recorded as coverage for **1.2.2 Captions**, no failure existed, and the conformance statement suggested **"Supports"** — telling a buyer the captions met Level A when nobody had watched a second of the video. The same shape applied to 1.2.1, to 2.2.1 on the strength of a `meta refresh` rule, and to 2.4.4 on the strength of a link having *any* accessible name.

`ownership.partially_flaggable`'s own docstring had promised for months that a partial flag *"never licenses reporting a pass"*. It and `needs_human_always` were imported by the test suite **and by nothing else**.

The fix guards **only the positive direction**: a proven failure is a fact about the product whichever engine proved it, so `does_not_support` and `partially_supports` are untouched. Two questions now gate a positive claim:

- is this one of the 15 criteria a person must always settle? → the platform suggests nothing
- did the engine that can decide this criterion actually look? → if not, the platform suggests nothing

> **Reflow produced an honest silence. This produced a false claim in a client-facing document.** That is why it jumped the queue.

---

## 7. The other-phases backlog adds no new criteria — and why that is fine

Nine tasks (OP‑01 … OP‑09) in [TASK_BACKLOG_OTHER_PHASES.md](TASK_BACKLOG_OTHER_PHASES.md). **Every one moves an existing check earlier in the lifecycle.** Same checks, cheaper moment.

| Task | In one line |
|---|---|
| **OP‑01** | Move the design phase's accessibility spec from WCAG 2.1 to 2.2 so everyone aims at one target |
| **OP‑02** | Run the AI checks we already have against the **wireframes**, before code exists |
| **OP‑03** | Stop a design moving into build while it has a confirmed serious flaw |
| **OP‑04** | Run the AI "meaning" checks at **code review**, on the PR preview |
| **OP‑05** | Feed those findings into the existing fix-and-recheck loop |
| **OP‑06** | When an existing app is imported, record where it stands and register its screens |
| **OP‑07** | Offer to generate a missing accessibility spec, review-gated |
| **OP‑08** | Turn an inherited app's audit backlog into a managed remediation campaign |
| **OP‑09** | Hold new features on an onboarded app to the same standard as greenfield |

**Shift-left is worth doing on its own merits** — a contrast failure caught in the design system costs one palette change instead of one change per screen — but it does not move the 27.

---

## 8. The roadmap: what the remaining 28 would take

**This is the section to read when deciding what to build next.**

| Group | Count | What it means |
|---|---|---|
| 🟢 **A — AI can decide it** | **15** | good enough to raise a defect and gate on it |
| 🟡 **B — AI decides most; a person confirms** | **7** | AI narrows it to a yes/no a person signs in seconds |
| 🔴 **C — AI assists; a person decides** | **6** | media accuracy and seizure risk — judgment, always |

Building group A takes coverage from **27 to 42 of 55**. With group B, **49 of 55** reach a person pre-answered. *(Cross-check: our own Addendum B predicted "40 of 55 (~73%)". Group A alone beats it.)*

### 🟢 Group A — AI can decide it (15)

| Criterion | What it is | How AI checks it | What to build | Effort |
|---|---|---|---|---|
| **1.3.2** Meaningful Sequence | does reading order match what you see? | browser reports element positions and DOM order; AI rules on disagreements | position probe + judge | **M** |
| **1.3.3** Sensory Characteristics | "click the round button on the right" | AI reads page copy for shape/size/position-only wording | new element checker | **S** |
| **1.4.5** Images of Text | real text baked into a picture | vision model reads images we already capture | vision checker | **M** |
| **2.4.4** Link Purpose | does "click here" say where it goes? | AI reads link text plus surroundings | 7th element checker | **S** |
| **2.4.6** Headings and Labels | are headings and labels descriptive? | AI judges each against what it introduces | 8th element checker | **S** |
| **2.4.5** Multiple Ways | more than one route to a page? | count nav / search / sitemap across the site | cross-page stage | **S** |
| **3.2.3** Consistent Navigation | same nav, same order, every page | compare across pages; AI settles near-matches | cross-page stage | **M** |
| **3.2.4** Consistent Identification | same function, same name and icon | match components across pages | cross-page stage | **M** |
| **3.2.6** Consistent Help | help in the same place everywhere | position comparison across pages | cross-page stage | **S** |
| **3.3.8** Accessible Authentication | no memory games to log in | check paste/autofill work; AI reads the login for puzzles | journey + judge | **M** |
| **1.4.13** Content on Hover/Focus | can a tooltip be dismissed and stay? | agent hovers and tries to dismiss | 9th journey check | **M** |
| **3.3.1** Error Identification | is a form error explained in words? | agent fills a form wrongly and reads the result | 10th journey check | **M** |
| **3.3.3** Error Suggestion | does it say how to fix it? | same run as 3.3.1 | rides on 3.3.1 | **S** |
| **3.3.7** Redundant Entry | asked the same thing twice? | agent walks a multi-step flow comparing fields | journey extension | **M** |
| **2.5.2** Pointer Cancellation | does it fire on press-down? | press down, slide off, release | journey check | **M** |

> **The single biggest lever: a cross-page stage.** Four of these fifteen need it, and today every check looks at one page in isolation. One new capability, four criteria.

### 🟡 Group B — AI does most, a person confirms (7)

| Criterion | What it is | How AI checks it | Effort |
|---|---|---|---|
| **2.2.2** Pause, Stop, Hide | moving content must be stoppable | detect animation; agent hunts for the control | **M** |
| **2.2.1** Timing Adjustable | time limits must be extendable | detect session timers; agent waits and watches | **L** |
| **2.1.4** Character Key Shortcuts | single-letter shortcuts must be switchable | read the page's keyboard handlers | **M** |
| **2.5.1** Pointer Gestures | swipe/pinch needs a simple alternative | detect gesture handlers; AI looks for the alternative | **M** |
| **2.5.4** Motion Actuation | shake-to-undo needs a button too | detect motion listeners | **S** |
| **2.5.7** Dragging Movements | drag-and-drop needs a click alternative | detect drag handlers; AI looks for the alternative | **M** |
| **3.3.4** Error Prevention | legal/financial actions reversible | AI spots the risky flows; agent checks for a confirm step | **L** |

### 🔴 Group C — AI assists, a person decides (6)

| Criterion | What AI can honestly do | Effort |
|---|---|---|
| **1.2.1** Audio/Video-only Alternative | detect whether an alternative exists — never whether it is adequate | **L** |
| **1.2.2** Captions (Prerecorded) | transcribe the audio, compare to the caption track, flag drift and gaps. **Accuracy stays a person's call** | **L** |
| **1.2.3** Audio Description or Alternative | detect presence; adequacy is judgment | **L** |
| **1.2.4** Captions (Live) | sample live captions; largely operational | **L** |
| **1.2.5** Audio Description | detect a description track; sufficiency is human | **L** |
| **2.3.1** Three Flashes | measure flash rate from video frames — real arithmetic, but needs a frame pipeline, and seizure risk is not a thing to be wrong about | **L** |

All six need a **media pipeline** we do not have. Biggest lift on the board, for the six lowest-frequency criteria. **Recommendation: last, or never.**

---

## 8b. Accuracy evidence — which checkers have any, as of 2026‑08‑28

Coverage and accuracy are different claims, and this document is mostly about the first. A
criterion can be fully covered by a checker that is wrong most of the time, and nothing above
would show it.

The golden set (`evaluation/golden/`, v0.2.0, 173 records) is what turns coverage into accuracy.
As of today it can produce a number for **five of the six AI checkers**:

| Checker | Criteria | Records that can score | Measurable? |
|---|---|---|---|
| `alt` | 1.1.1 | 30 | yes |
| `color` | 1.4.1 | 32 | yes |
| `label` | 2.5.3 | 20 | **recall only** — see below |
| `semantics` | 1.3.1, 4.1.2 | 31 | yes |
| `structure` | 1.3.1 | 30 | yes |
| **`graphics`** | **1.4.11** | **0** | **no — none, ever** |

**`label` is short by ten and cannot be made otherwise.** The rule correctly skips any control
whose accessible name already contains its visible label, so the only controls that reach the
judge are ones where the words genuinely differ — and those are either real failures or
genuinely arguable. A clearly-correct example is, by definition, one the check skips. **Recall
for 2.5.3 is meaningful; precision is not**, because no correct examples remain that it could
get wrong. Recorded in `evaluation/scorer/selectable.py`; see `RESEARCH_CORRECTIONS.md` R21.

**`graphics` has no accuracy evidence of any kind and this is deliberate.** The checker and the
answer key would have the same author, which measures self-consistency rather than correctness.
The fixture already holds the material to label — the `#9a958c` field border, 2.98:1 on the
content surface — and it is asserted in the harness so it stays there. The one constraint on
closing this is that the records must be written by someone who did not write the checker. Full
note: **"Not covered, and how to add it"** in `evaluation/golden/README.md`.

**Three cautions before anyone quotes a number from that set.** It is unadjudicated — every
record is a draft awaiting expert sign-off. It has had no blind re-label round. And 30 records
with ~15 failures means one miss moves recall by 6–7 points. Internally useful; not a client
figure.

---

## 9. Three things to know before quoting any of this

### The audits HAVE run, and counting them wrongly is easy — here is how to count them

Real data on the shared database (`13.203.56.29`), 2026‑08‑27:

| Table | Live rows | Ever inserted |
|---|---|---|
| `a11y_a11yscreenscan` | 24 | 149 |
| `a11y_a11ycandidatebundle` | 343 | 2,291 |
| `a11y_a11ycriterioncoverage` | 496 | 3,177 |
| `a11y_a11yfinding` | 49 | 137 |
| `a11y_a11yjudgmentcache` | 215 | 1,118 |
| `a11y_a11yroute` | 104 | 104 |
| `a11y_a11ybaselineaudit` | 8 | 20 |
| `a11y_a11yconformancestatement` | 7 | 15 |
| **`a11y_a11yjourneyrun`** | **0** | **0** |
| **`a11y_a11yjourneystepresult`** | **0** | **0** |

> ⚠️ **`SELECT count(*)` on any of these returns 0 unless you set the tenant first, and it does not warn you.** Every tenant-scoped a11y table has `rls=True, forced=True` with the policy
> `tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`.
> With no setting, that comparison is `tenant_id = NULL` — false for every row. **An empty result and an empty table look identical.**
>
> This is not hypothetical: on 2026‑08‑27 it produced a written claim to the team that *"no accessibility audit has ever run on this database"*, which was wrong. The four a11y tables that DID return rows were `actrule`, `criterionownership`, `wcagcriterion` and `wcagterm` — **exactly the four with RLS off**, because they are platform-wide under the `0006_wcag_platform_wide` carve-out. The pattern was the evidence and it was there to be read.

**How to count honestly:**

```bash
docker exec sdlc-platform-backend-1 python -c "import os,psycopg; u=os.environ['DATABASE_URL'].replace('postgres://','postgresql://'); c=psycopg.connect(u); print([(r[0],r[1]) for r in c.execute(\"select relname,n_live_tup from pg_stat_user_tables where relname like 'a11y!_%' escape '!' order by 1\")])"
```

`pg_stat_user_tables` is not subject to RLS. Its counts are approximate (they drift with vacuum), so use it to answer *"has anything ever run?"* — then set `app.tenant_id` and query the table for anything exact.

**What is genuinely unproven:** the **keyboard journey has never executed** — both journey tables are zero, ever. So the eight journey criteria in buckets 4 and 5 are built and unit-tested but never run against a real app. That part of the original caveat stands.

### The running stack is this branch — check the mount, not the image

The backend image was baked on 2026‑08‑12 and its `/app` has no `a11y` directory. **That is not what runs.** `docker-compose.yml` bind-mounts the repo (`.:/repo`) with `working_dir: /repo/backend`, so the container serves the checked-out branch live.

```bash
# WRONG — reads the stale baked copy, reports "No installed app with label 'a11y'"
docker exec sdlc-platform-backend-1 sh -c 'cd /app && python manage.py showmigrations a11y'
# RIGHT — reads what is actually being served
docker exec sdlc-platform-backend-1 sh -c 'cd /repo/backend && python manage.py showmigrations a11y'
```

This mistake was also made on 2026‑08‑27 and produced a second wrong claim, that the stack could not run an accessibility audit at all.

### Migration 0031 is written and not applied

The shared database is at `0030_unpublish_a11y_run_artifacts` (applied 2026‑08‑25), so **`0031_page_measurements` is the single pending migration**. It is additive: one JSON column defaulting to `{}`, no index, no constraint. Every reader treats `{}` as *not measured* rather than *measured and clean*, so no historical screen starts claiming a criterion nobody checked — until it is applied, 1.4.10 and 1.4.11 simply report as not evaluated. **Running migrations is the team's job, not the assistant's.**

---

**Cross-refs:** what the reports got wrong = [RESEARCH_CORRECTIONS.md](RESEARCH_CORRECTIONS.md) (**R13–R17 are this work**) · the QA backlog = [TASK_BACKLOG_QA.md](TASK_BACKLOG_QA.md) · the shift-left backlog = [TASK_BACKLOG_OTHER_PHASES.md](TASK_BACKLOG_OTHER_PHASES.md) · the journeys these serve = [USER_JOURNEYS.md](USER_JOURNEYS.md)
