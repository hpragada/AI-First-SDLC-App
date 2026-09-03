# Incident — "the audit judged all 41 elements and never completed"

**Date:** 2026-08-26 · **Branch:** `web-accessibility-build` · **Reported by:** the team, after a
client demo

A baseline accessibility audit ran in front of a client. Every element was judged. The audit then
sat on *Checking what was found* and never finished. The client was told the shared Temporal
server had dropped.

**It had not.** The workflow completed cleanly in 8m49s with zero failures. The cause was two
workers polling one task queue, one of them running older code — and nothing in the platform
could notice, because from the outside the run had *succeeded*.

This is not an accessibility defect. Any activity that an older worker handles differently is
silently wrong, in any phase: greenfield ideation, a build, a gate, an artifact index. The fixes
below are therefore platform-wide.

---

## 1. What was observed

```
audit  · status "judging" for ever · 41/41 elements judged
judge run · status "completed" · workflow CLOSED, 8m49s, zero failures
report    · never published
```

Both halves looked healthy in isolation. The run had ended, the workflow had ended, and no error
existed anywhere. Only the audit underneath was stranded, and nothing reads that.

Two audits were left in this state:

| Tenant | Judge run |
|---|---|
| `600202c3-4493-4c3c-8607-4b64f2981be1` | `0a0602b6-0bb5-4d49-a270-9985acce7572` |
| `b02a2997-ae79-4c3e-8d16-bff8c0edbebb` | `edaa9422-eaa3-4f47-b24c-09437d808ae6` |

---

## 2. Root cause — two workers, one queue, one of them stale

Two containers were polling `sdlc-planning`:

| Container | Code |
|---|---|
| `f7ae08010f84` | older |
| `29339a86a915` | current |

Temporal load-balances, so each run landed on whichever worker was free. The correlation was
perfect across four runs:

| `verify_writes` ran on | returned | outcome |
|---|---|---|
| `29339a86a915` | `{"present": ["41 judged"], "expected": ["41 dispatched"]}` | completed |
| `f7ae08010f84` | `{"present": ["non-empty artifact"], "expected": ["non-empty artifact"]}` | **stranded** |

That second string appears in exactly one place in the codebase: the `auto_approve` branch of
`verify_write_completeness_core` (`orchestration/activities.py:786`). The older worker had no judging branch to
take, so it fell through to the generic one, reported success, and never ran the judge's
accounting — which is what publishes the report and completes the audit. Independently
corroborated by artifact status: `published` on the runs that landed on the current worker,
`draft` on the ones that stranded.

**The engine was never involved.** Temporal did exactly what it was asked to do.

---

## 3. The design gap this exposed

`apps/a11y/baseline.py` documents `judging` as having two exits:

* success → `finish_ai_pass` (from the run's write-completeness step)
* failure → `close_unfinished_ai_pass` (called only from `fail_run_core`)

The demo hit a third case that had no name and no owner:

> **the run succeeded, but the accounting never ran.**

A run that neither succeeds *at the thing it was for* nor fails is invisible to both exits. The
same shape exists wherever a phase's closing work lives inside a branch an older worker may not
have.

---

## 4. Fix A — a worker knows which code it is running  ✅ FIXED (`bd38e87`)

`orchestration/version.py` + `orchestration/worker_election.py`.

Before it polls for anything, a worker computes a **badge** for the code it is actually running
and asks Temporal who owns the queue:

| Outcome | Meaning |
|---|---|
| `VERSIONED` | I am the newest code; registered my badge as the queue default |
| `UNVERSIONED` | the server has versioning switched off; behave exactly as before, and say so |
| `STAND_DOWN` | someone newer owns this queue — **do not poll at all**, exit |

The badge is `<YYYYmmddTHHMMSSZ>-<fingerprint12>`: a content hash of the ~296 behaviour-defining
`.py` files, plus an orderable timestamp. Line endings are normalised so a Windows host and a
Linux container agree — **confirmed in production**: the host and the container independently
computed `20260826T104430Z-1633c7c8f386`.

**The timestamp dates the code the worker LOADED, not the image it came from.** `docker-compose.yml`
mounts the repo at `/repo` and runs from `/repo/backend`, while `backend/Dockerfile` bakes a
separate copy at `/app`. The worker does not run the code in its own image, so a build-only stamp
would confidently describe code that is not executing. The image stamp is used only when its
fingerprint matches what is actually loaded.

A superseded worker **drains** rather than exiting at once: workflows already assigned to its
build keep running on it, and killing it mid-activity would strand exactly the kind of run this
change exists to protect. It leaves once it has been idle, with a backstop for a worker that
never goes quiet.

Deploying is therefore just *start the new worker*.

---

## 5. Fix B — notice when the two stories disagree  ✅ FIXED (`25cdebc`)

`apps/runs/reconcile.py` + `apps/a11y/reconcile.py`.

> A run the platform still shows as live, whose workflow has already ended, is lying.

Both facts (`Run.status`, `Run.temporal_workflow_id`) were already in the database; nothing
compared them. When they disagree the run is closed out through the **same path a reported
failure uses**, the run console gets a reason a person can act on, and a `run.reconciled` event
records what changed.

**It runs on a read, not on a timer.** A background sweep is not available: the app's database
role is subject to RLS and cannot enumerate tenants at all (`select count(*) from tenancy_tenant`
with no tenant context returns 0, by design). A sweeper would need an elevated role — a security
decision that should be taken deliberately, not smuggled in with a bug fix. So the check hangs off
the runs list, which is already tenant-scoped and already polled. Bounded to long-untouched runs,
a handful per call, and it swallows its own errors so it cannot break the page it rides on.

**The generic check would NOT have caught this incident** — that run's status was `completed` and
its workflow had closed, which is perfectly consistent. So capabilities register their own
invariants. Accessibility's is: *an audit still in `judging` whose judging run has already
finished is an audit nothing will move*, repaired with the recovery the crash path already had.
Whatever is built next registers its own check.

Nothing is repaired on a guess: if Temporal cannot be reached, the run is left exactly as it is.

---

## 6. Fix C — identical code must not evict itself  ✅ FIXED (`613e4bb`)

Caught by the team before the workers were restarted, from Fix A's own design.

The election compared badges as whole strings. Two developers who pull the **same commit** at
different times get different file dates, so the same code produced two different badges and one
worker would have stood down for nothing — and `deploy/shared-aws/README.md` has two devs sharing
a queue on purpose. That would have quietly halved the team's workers with no safety gained.

A badge carries a fingerprint as well as a date. When the fingerprint matches the build already
serving, the worker now **joins** that build and polls under the same id. Identical code is the
same build, not a later one. Older code is still kept off the queue — the fingerprint has to
match, so this cannot be a way back in.

---

## 7. Measured facts about Temporal 1.25.2 — do not re-derive these

Established against our own server, several of them contradicting the documentation-level
assumption they replaced:

1. **A registered default build fences out UNVERSIONED workers too**, not just older versioned
   ones. This is what makes the fix work against workers deployed before it existed — no
   permanent manual stop is required.
2. **Version-set changes take seconds to reach the matching service.** Tests that register a build
   and dispatch immediately will appear to show versioning failing completely. Two of the first
   experiments did exactly this and were nearly reported as a dead end.
3. **`get_worker_task_reachability` is unusable as a drain signal** — it reported a *non-default*
   build as still reachable for new workflows. Drain is self-observed idleness instead.
4. **`default_build_id()` raises `IndexError`**, not `None`, on a queue nobody has claimed — the
   first case every new queue hits. Found only by running the shipped code against a live server,
   after a friendlier test double had let it through.
5. **Workflows already in flight survive versioning being switched on.** Measured directly:
   an in-flight workflow on an unversioned worker stayed queryable, accepted a signal and
   completed, while a *new* workflow on the same worker was correctly refused.

---

## 8. Prerequisite — the server ships this switched off

Temporal 1.25.2 has the feature compiled in (`build_id_based_versioning: true`) but gated. Until
both flags are set, every versioning call answers `PERMISSION_DENIED` and workers run unversioned:

```yaml
frontend.workerVersioningDataAPIs:
  - value: true
    constraints: {}
frontend.workerVersioningWorkflowAPIs:
  - value: true
    constraints: {}
```

In `docker/temporal/dynamicconfig/development-sql.yaml` (local) and the copy at
`~/temporal/dynamicconfig/` on the shared box — see `deploy/shared-aws/README.md`.

**No restart is needed.** Measured: Temporal re-read the file in 12s. This is a zero-downtime
change, safe to make while work is running.

The worker degrades deliberately where the flags are absent — a safety feature that takes every
worker offline over a missing server flag would be worse than the problem it prevents.

---

## 9. Corrections recorded on purpose

- I first concluded the demo worker **was not running this branch's code** and pointed at the
  dev's commit. Wrong. The team pushed back with three further runs on the same commit, and
  re-recon found the real cause: not *which* commit, but *two workers*, one of them holding stale
  code in a process started before that commit existed. The dev was on the right commit.
- I first scoped the fix to accessibility, because that is where the symptom appeared. Also wrong
  — the bug is in the platform. The team rejected the a11y-shaped fix and asked for the general
  one, which is what shipped.
- I proposed `get_worker_task_reachability` as the drain signal in the approved design, then found
  by measurement that it does not answer the question. Replaced with self-observed idleness before
  any code was written.
- **Rule reaffirmed:** the first two experiments appeared to disprove the entire approach. They
  were wrong because of propagation timing, not because the approach was wrong. Measure, then
  measure the measurement.

---

## 10. STILL OPEN

- **`sdlc-planning` is not yet protected.** Its workers have not been restarted onto this code, so
  that queue still behaves as it did on the day of the demo. `sdlc-brown` is verified live.
- **`f7ae08010f84` is still polling `sdlc-planning`.** It is fenced out automatically once a
  current worker claims that queue; until then it can still strand a run.
- **The two stranded audits above were left as they are** — the team moved to new tenants. Fix B
  would repair them once deployed and someone opens that tenant's runs.
- A worker that registers a build and then dies leaves new work **queued, not failed** — runs sit
  waiting rather than erroring, which reads as "nothing is starting". Make sure a worker is
  actually serving after it registers.

---

## 11. Files changed

| File | Change |
|---|---|
| `backend/orchestration/version.py` | **new** — build badge, fingerprint, `same_code`, `is_newer` |
| `backend/orchestration/worker_election.py` | **new** — `elect`, `drain_when_superseded`, `TrackingExecutor` |
| `backend/orchestration/worker.py` | elect before polling; versioned worker; drain alongside serving |
| `backend/config/settings.py` | `WORKER_VERSIONING_ENABLED` + three drain settings |
| `backend/Dockerfile` · `docker-compose.yml` | build stamp recorded into the image |
| `docker/temporal/dynamicconfig/development-sql.yaml` | the two flags, for local dev |
| `backend/apps/runs/reconcile.py` | **new** — the invariant, the repair, the capability seam |
| `backend/apps/a11y/reconcile.py` | **new** — audits stranded behind a finished judging run |
| `backend/api/views.py` | `RunViewSet.list` reconciles before listing |
| `backend/tests/test_worker_version.py` | **new** — 27 tests |
| `backend/tests/test_run_reconcile.py` | **new** — 17 tests, about half asserting nothing happened |

Commits: `bd38e87` (Fix A) · `25cdebc` (Fix B) · `613e4bb` (Fix C).
