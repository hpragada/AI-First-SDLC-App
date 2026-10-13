# Get Started flow — "return to checklist" wireframe (row 12)

Approved approach for the Bugs.xlsx row-12 Design Issue. The **Get Started checklist is the hub**; every step returns to it. No rigid wizard.

```
                    ┌─────────────────────────────────────────┐
                    │   GET STARTED · 1 of 4 complete   (/setup)│
                    │                                           │
                    │  ✓  1. Create your first project   [Done] │
                    │  ●  2. Connect your machine     [Connect] │
                    │  ○  3. Invite your team          [Invite] │
                    │  ○  4. Connect integrations     [Connect] │  (optional)
                    └─────────────────────────────────────────┘
                       ▲  click a step ↓      auto-return when done ▲
        ┌──────────────┴───────┬───────────────┬──────────────────┐
        │                      │               │                  │
   Step 1                 Step 2           Step 3             Step 4
 Create project        Connect machine   Invite team       Integrations
      │                      │               │                  │
 Project Profile      (token + wait for   Send invite      Connect a tool
   [ Save ] ──────►    first check-in)      │                  │
 returns to /setup     "Back to Get         "Back to Get      "Back to Get
 (step 1 ✓)             started" link       started" link     started" link
                        returns (step 2 ✓)  returns (3 ✓)     returns (4 ✓)
```

## The one shared mechanism
- **Step 1** navigates back to the checklist automatically on profile **Save**.
- **Steps 2–4** each show a persistent **"Back to Get started"** link on their screen, visible only while setup is still incomplete.
- The checklist **auto-detects** each step's completion from existing data (a project membership exists, a runner has checked in, more than one user exists). So the ticks light up on return — no extra state, no new backend.

## Why this and not the alternatives
- **Persistent banner everywhere** — noisier; the link on the three destination screens is enough.
- **Skip profile, go straight to checklist** — loses the natural "fill in your project" moment right after creating it.

Result: the checklist is a true home base a new user can always get back to, closing the dead-end the UX dev reported.
