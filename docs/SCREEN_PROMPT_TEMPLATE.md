# Per-Screen Prompt Template + How-To (for generating hi-fi screens with Claude)

This is the prompt the designer pastes **once per screen**. It pairs the shared design system with one screen's spec so every screen comes out consistent and on-brand.

---

## How to use it (5 steps — read once)

1. **Attach the design system every time.** Paste `DESIGN_SYSTEM.md` (or its §9 CSS variables block) at the top of *every* prompt, or attach it as a file. This is what keeps all screens visually identical. Don't skip it "because the last screen looked right."
2. **Do one screen per prompt.** Pick a single row from `SCREEN_INVENTORY.md` (e.g., S-15). Don't ask for multiple screens at once — quality drops and the look drifts.
3. **Fill the `{{…}}` slots** from that screen's inventory row (purpose, elements, states, sample data, role). The sample data matters — real-looking content >> lorem ipsum.
4. **Generate, then iterate in the same chat.** Ask for one state first (default), check it, then say "now add the 'awaiting gate' state" / "tighten spacing per the 4px scale" / "the status chip should use the run-state color map." Keep refining in-thread so context stays.
5. **Lock the shell first.** Generate the app shell (sidebar + top bar) as screen 0, get it right, then tell later prompts "reuse the shell from before" so every screen nests in the same chrome. Build the **signature screens** (board, work-item detail, connect-machine, gap report, dashboard) before the simple ones.

> Output format: ask for a **single self-contained HTML file** (inline `<style>` using the design-system CSS variables, no external assets) — easiest to preview, screenshot, and hand to engineering as a reference. Switch to "React + your component lib" only once the visual language is locked.

---

## The template (copy, fill the `{{…}}`, paste)

```
You are a senior product designer producing a HIGH-FIDELITY, production-grade screen
for the Edvensoft AI-First SDLC platform (an enterprise web app where teams run their
software lifecycle with AI agents and human approval gates).

== DESIGN SYSTEM (use ONLY these tokens for color/type/spacing/radius/shadow) ==
{{paste DESIGN_SYSTEM.md here, or at least its §9 :root CSS variables block}}

== GLOBAL RULES ==
- Enterprise, trustworthy, calm. 60% neutral / 30% navy / 10% orange. Orange = primary
  action + active state only; navy + neutrals carry the UI.
- App shell on every authed screen: 240px navy left sidebar (nav items: Workspace
  Dashboard, Work Items, Phases & Runs, Gates, Clarifications, Artifacts & Traceability,
  Workspace Admin; active item = orange left-bar + lighter navy) and a 56px white top bar
  (tenant switcher "AC Acme Corp ▾", project switcher "⚑ Payment Gateway v2 ▾", spacer,
  companion status pill "● Companion: Ready", notification bell with count, user avatar).
- Status/lifecycle colors MUST follow the design system's run-state color map.
- Never show an editable artifact body (previews are read-only). Never imply the AI runs
  in the browser. Pair every status color with a text label (accessibility).
- WCAG 2.2 AA: ≥4.5:1 text contrast, visible orange focus rings, hit targets at least 24×24px (2.5.8) and ≥40px by house style.

== SCREEN TO DESIGN ==
- Screen id & name: {{e.g., S-15 · Work Item Detail — Epic level}}
- Realizes journey: {{e.g., J11/J15 from UX_JOURNEYS_AND_IA_SPEC.md}}
- Primary user & role: {{e.g., Product Owner viewing an epic mid-pipeline}}
- Purpose (one line): {{what the user accomplishes here}}
- Required elements / layout: {{bullet the elements from the inventory row, in rough
  layout order — e.g., breadcrumb+title+meta; type-adaptive lifecycle rail; description
  panel; linked-artifacts panel with SoR chips; latest-run console; child-tasks section;
  right-side gate attention card}}
- Signature pattern(s) to include: {{e.g., type-adaptive lifecycle rail (plan-tier for an
  epic), gate attention card with orange accent + folded corner}}
- Sample data (use verbatim): {{paste the inventory row's sample data — real names, IDs,
  versions, statuses}}

== STATES TO RENDER ==
Render the DEFAULT state first. {{then list the extra states, e.g., "awaiting gate" with
the attention card; "a phase running" with a live console; "needs answer" purple badge}}.
Show each state as a separate full-screen section stacked vertically with a small label.

== OUTPUT ==
A single self-contained HTML file (inline <style> using the CSS variables above; system
fonts ok; inline SVG for icons; no external requests). Pixel-tidy, real content, no lorem
ipsum. Desktop width ~1280px. After the code, give a 3-bullet note on the design choices.
```

---

## Worked example (filled, for S-14 · Work Items board)

```
…(GLOBAL RULES + DESIGN SYSTEM as above)…

== SCREEN TO DESIGN ==
- Screen id & name: S-14 · Work Items board
- Realizes journey: J11 (two-tier model — see UX spec §6.0)
- Primary user & role: Tech lead triaging the project's work
- Purpose: see every work item across its phase, filter by level, spot what needs action.
- Required elements / layout: page header "Work Items" + subtitle + "New Work Item"
  (orange) ; filter row (Search, Phase ▾, Level ▾ [Epics/Tasks/Defects], Role ▾, Status ▾)
  + Board/List toggle ; horizontal Kanban columns titled by phase with a count chip ;
  cards = work items (WI id, title, level chip, status chip from color map, artifact count,
  owner avatar, "needs you" flags).
- Signature patterns: board-columns-are-phases; "needs you" chips (purple "1 Clarification",
  amber "Gate: PM Approval Req.").
- Sample data (verbatim):
  Col "1. Ideation" (2): WI-508 "Customer Loyalty Program" [Epic][Draft] · WI-521 "Dark Mode
  UI Theme Support" [Feature][Draft].
  Col "2. Requirements" (3): WI-510 "Analytics Dashboard PRD Generation" [AI Compiling Draft…]
  [1 Clarification] · WI-511 "Fix Session Timeout Logic" [Gate: PM Approval Req.][1 Artifact]
  · WI-499 "Multi-Currency Support" [Phase Complete][3 Artifacts].
  Col "3. Architecture" (1): WI-492 "Stripe Webhook Integration" (selected/outlined)
  [Review Architecture Gate][Jira STR-14].
  Col "4. UX Design": WI-487 "Checkout Flow Redesign" [AI Compiling Draft…].

== STATES TO RENDER ==
Default (board, all columns). Then: List view of the same data; Filtered to "Level: Tasks".

== OUTPUT == …single self-contained HTML… 
```

---

## Tips that materially improve output
- **Reference the mockups you already have:** add "Match the visual language of the attached reference screenshot" and attach your existing Work-Item-Detail / board mockups. Claude matches an example far better than prose alone.
- **Name the signature components** ("type-adaptive lifecycle rail", "gate attention card with folded corner", "dark run console") — they're defined in the design system, so Claude renders them consistently.
- **Keep a running "shell" snippet:** once the sidebar/top bar look right, save that HTML and tell each new prompt "use exactly this shell" — guarantees identical chrome.
- **Ask for states stacked in one file** so the designer can screenshot each without re-prompting.
- **For dev hand-off:** once visuals are locked, re-ask "convert this to a React component using these props {…}", keeping the same CSS variables.
- **Don't over-stuff one prompt:** if a screen has 6+ states, split into two prompts (core states, then edge/error states).
