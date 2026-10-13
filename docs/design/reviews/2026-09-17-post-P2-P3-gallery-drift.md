# Gallery drift after the P2/P3 batches — 17 September 2026

> **Team decision, 21 September 2026: LEAVE — record it and move on, for every item below.**
> - Items 1–3 (the side menu, the gate panel's *Request changes*, the registry's five statuses):
>   the differences are accepted as they ship; the mockups are **not** edited.
> - S-06 Connect your machine, S-11 Integrations grid, S-14 Work Items board: the team compared each
>   mockup with the running screen and **confirmed they have drifted**; same decision — recorded,
>   not re-drawn.
>
> So the gallery is knowingly behind the app in these six places. Anyone using a mockup here as a
> spec for new work should check the running screen first.

**Status:** report only. **No mockup file has been edited**, and none should be until the team says
so, per item by item.

## Why nothing was changed here

The mockups in `docs/design/screens/` are the **approval record** — they are what the team looked at
and said yes to, under the mockups-before-any-frontend-change rule. Editing one to match what
shipped destroys the evidence of what was agreed, and turns the gallery into a mirror of the code.
A mirror can never catch drift again, because it is downstream of the thing it is supposed to check.

So each item below needs a decision, and there are only three available:

- **Re-approve** — the shipped screen is right and the mockup should be brought up to it.
- **Defect** — the mockup is right and the shipped screen is wrong; raise a bug row.
- **Leave** — the difference is immaterial; record it and move on.

---

## Verified against the files

### 1. `shell.js` — the app shell, which every screen in the gallery inherits

| | Gallery | Shipped app |
|---|---|---|
| Accessibility | present (`a11y`, count 7) | present — **agrees** |
| Test Reporting | **absent** | present, admin only |
| Connect Machine | **absent** | present |
| Onboarding | always shown | **hidden on greenfield** (`AppShell.tsx:96`) |
| Second group heading | `Project` | `Project` — agrees |

*Evidence:* `docs/design/shell.js:47-66` against `frontend/src/components/AppShell.tsx:63-112`.
This one difference propagates to **every screen in the gallery**, which is why it is first.

### 2. `S-21-gates.html` — the gate decision panel

The mockup offers **Approve** and **Reject**. The shipped panel has a **third action, `Request
changes`** (`Gates.tsx:477` and `:806`), which rejects *and* re-runs the phase with the reviewer's
comment as the agent's direction, and is disabled until a comment is typed.

*Evidence:* no occurrence of "Request changes" anywhere in the mockup file.

### 3. `S-28-artifacts.html` — the artifact registry

The mockup shows two statuses, **Draft** and **Published**. The model has **five**: `draft ·
staged · approved · published · superseded` (`backend/apps/registry/models.py:36-46`). `superseded`
matters most — it marks a draft whose gate was rejected.

### 4. `index.html` — S-38 badge and the file count *(already fixed)*

S-38 was badged `Proposed` while the accessibility audit screen is built and running; the README
said the gallery held 39 files when it holds 40. **Both corrected on 2026-09-17** — they are
catalogue metadata, not a design decision, so they did not need an approval.

---

## Flagged but NOT re-verified — these need a person to look

The sweep flagged **S-06 Connect your machine**, **S-11 Integrations grid** and **S-14 Work Items
board** as having drifted after the P2/P3 batches. **I could not confirm that from the files**, and
I am not willing to assert a difference I have not seen: these three are visual-layout screens whose
drift would show up in rendering rather than in a text search, and the shell they show is injected
at runtime rather than written into them.

**What they need is someone opening the mockup and the running screen side by side.** Until that
happens, treat this as an open question, not a finding.

---

## Recommendation

Take item 1 first. The shell is inherited by all forty screens, so one decision there is worth more
than the rest of the list combined — and of the three differences, **Onboarding being hidden on
greenfield is the one that changes what a person sees**, because it is a deliberate behaviour change
(S.No 221) that the gallery still contradicts.
