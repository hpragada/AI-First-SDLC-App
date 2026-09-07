# ADR 0005 — The platform **observes** the code host; it never polices it, and only a person decides a gate

- **Status:** Accepted (2026-09-07)
- **Deciders:** Build team
- **Context task:** Bugs.xlsx S.No 88 (a pull request merged on GitHub left its run waiting for
  ever), fixed on `SDLC_Bug_Fix_Enhancements`.

## Problem

A developer merges the build's pull request directly on GitHub. This happens, and the team was
explicit that it must keep happening: *"we should not change a developer habit because sometimes
they might do the merges directly in the GitHub or git."*

The platform's merge gate then waited for an approval nobody would ever give, because the thing it
was asking about had already happened. The run sat at `awaiting_gate` indefinitely, the work item
never reached `done`, its artifacts stayed drafts, and the preview environment was never torn down.
The reviewer saw a gate asking them to approve a merge, with nothing anywhere on screen saying it
had been merged two hours earlier.

A correction to what was first reported: there is **no 405 merge loop**. `merge_build_pr_core`
already reads the pull request first and short-circuits on `if not pr.merged:`. The workflow needs
no change at all — the moment *any* approval arrives, the run completes correctly on its own. The
bug is not that approving breaks; it is that **nobody ever approves, and nothing tells anybody they
should**.

## Decision

Three rules, in order of how much they matter.

**1. Detection annotates. Only a person decides.**
A merged pull request that meets a pending merge gate writes a *note* on that gate
(`Approval.external_merge`: who merged it, when, which PR, and what noticed). It does not approve,
does not transition the work item, and does not signal the workflow. The reviewer then acknowledges
through the **existing** decision endpoint — the same role check, the same `gate.decided` event, the
same Temporal signal. Only the wording on the button changes, because "Approve" is the wrong word
for something already done.

**2. The platform observes the code host; it does not police it.**
An external merge is a legitimate outcome to be absorbed, not a violation to be prevented or
reverted. Nothing here tries to stop, undo, or warn against merging outside the platform.

**3. A webhook is a hint, never the only path.**
The sweep in `apps/gates/reconcile.py` re-checks stranded merge gates against the code host, because
the webhook cannot be relied on: a delivery can be missed, the endpoint can be unreachable, the
secret can be wrong — and a webhook that *fails* is never redelivered, because the dedup row is
written before the handler runs. No webhook fires retroactively either, so the sweep is also the
only thing that will ever recover a run stranded before this existed.

## Why rule 1 is a security property, not process for its own sake

`GITHUB_WEBHOOK_SECRET` is a **single global setting** (`config/settings.py`), not per-tenant, and
the tenant rides in the **URL path**. Anyone able to sign a payload can therefore aim a delivery at
any workspace.

Because the webhook can only ever add a note that a human must still act on, the worst a forged or
mis-addressed delivery achieves is a false line on a gate screen that a reviewer will not recognise.
Had we let detection approve the gate itself, that same weakness would have become **a way to
complete somebody else's run and publish their artifacts** — a gate bypass reachable by anyone
holding one shared secret.

This is the reason the human-acknowledgement option was the right one, and it is recorded here so
that "the platform could just close it automatically" is not re-proposed as a simplification later.
Per-tenant webhook secrets would narrow the exposure, but they would not change this decision: the
platform still would not decide a gate.

## Consequences

- A run whose PR was merged externally is completed by a person, not by the platform. That person
  sees who merged it and when, so the acknowledgement is an informed one and the ledger records both
  names (`webhook.pr_merged_while_gated`, then the ordinary `gate.decided`).
- The sweep costs one network call per candidate, unlike every other reconciler check, which is
  local. It is therefore age-gated to an hour, capped at three per pass, and hung off the **Gates**
  read rather than registered in `_CAPABILITY_CHECKS` — the cost belongs on the screen that wants
  the answer, not on an unrelated page load.
- `Approval.external_merge` is nullable, so a rolling deploy is safe under ADR 0003.
- Deploying the webhook needs a reachable URL and `GITHUB_WEBHOOK_SECRET` set. Until then the sweep
  is the only detector, and it works — just an hour later rather than instantly.
