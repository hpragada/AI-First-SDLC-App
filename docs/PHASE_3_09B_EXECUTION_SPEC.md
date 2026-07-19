# Phase 3 Supplement — 09b Test **Execution**: CI results ingestion (lighting up the defect loop)

> **Purpose:** define the seam that runs the automated suite for real and feeds its results into
> the platform's **defect loopback** — the last dormant piece of the D4/D5 test loop. The runnable
> supplement (`PHASE_3_09B_RUNNABLE_SPEC.md`) made 09b **author** scripts against a live app; this
> makes those scripts **execute** and their failures become tracked defects. Decides nothing new
> about the loopback itself — `import_test_results` (the defect/flaky/quarantine machinery) is
> reused unchanged; this adds the *caller* that was missing.
>
> **Builds on Phase 3 — not re-opened.** `import_test_results`, `TestExecution`, `TestQuarantine`,
> the `test_report` artifact, the defect loopback, and the qa_lead gate are all present and frozen.
> This is the ingestion caller + its auth, nothing more.

## 0. Decisions (LOCKED for this supplement, 2026-07-18)

- **Where/when tests run: the client's CI, post-merge / scheduled.** Not on the PR, not in the build
  worktree. Rationale (user + QA): E2E/Playwright suites are slow and flaky and belong in the
  tool-of-record (CI) against a real/staging environment, run repeatedly — which is also what makes
  flaky-quarantine (D9) meaningful. The fast pre-PR **sanity check** is 09b's existing compile/
  dry-run (author-time "does the script even run?"), **not** a defect source.
- **Transport: CI pushes JUnit.** CI posts its JUnit XML to a platform endpoint — provider-agnostic
  (GitHub Actions / GitLab / Jenkins), no per-provider connector. (A pull-connector is a later
  option behind the same import seam.)
- **Auth: a dedicated per-project CI ingest token.** CI is not a Claude Code companion, so it does
  not reuse a runner enrollment token — a purpose-scoped token (ingestion only) is issued per
  project and stored in the CI secret store.
- **Reuse the locked loopback rules:** `push_to_sor=False` (Xray export stays user-triggered,
  team decision 2026-07-07); an empty report is never a green run; a FAIL on a non-quarantined test
  opens a `defect`, a later PASS closes it.

## 0.1 In / out of scope

**In:** a per-project **CI ingest token** (issue/revoke/reveal-once) + `authenticate_ci_token`; a
**results-ingestion endpoint** that accepts JUnit XML + provenance and is idempotent per CI run; a
**shared, framework-agnostic JUnit parser** (one parser for both the companion and the endpoint);
correlation of a regression run to a per-project **Regression** container WorkItem so failures
become tracked defects; the small `import_test_results` extension for **run-less idempotency**
(by `execution_ref`).

**Out (later / unchanged):** per-PR (pre-merge) gate-blocking execution and per-PR preview envs
(needs the P5 cloud env; the runnable spec's `PreviewEnv` is the seam); **per-story defect
attribution via traceability** (v1 attaches regression failures to the Regression container — the
TC-ID + evidence on each defect still identifies the failing test; traceability-walk attribution is
a flagged enhancement, §6); pull-from-CI connectors; the CI **workflow file** itself (client-owned;
the 11_cicd agent can generate the post-results step — §5).

## 0.2 Assets already present (reuse, do not rebuild)

| Asset | Location | Role here |
|---|---|---|
| `import_test_results` | `backend/apps/quality/services.py` | The loopback caller — ingestion invokes it |
| `TestExecution` / `TestQuarantine` / `test_report` | `apps/quality/` | Recorded/reconciled by the above |
| JUnit parser (`parse_junit`, `test_ref_for`) | `runner/companion/testresults.py` | Framework-agnostic + **Django-free** → lift to shared |
| Runner-token auth pattern | `apps/runs/enrollment.authenticate_runner` + `X-Tenant-ID` | The shape the CI token mirrors |
| qa_lead gate + `no_blocking_test_failures` | `apps/gates/testgate.py` | Unchanged — reacts to open test defects already |

---

## 1. CI ingest token (E-X1)

A purpose-scoped credential, separate from runner enrollment.

```python
# apps/projects/models.py (or apps/integrations) — RLS-scoped like every table
class ProjectCIToken(TenantScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ci_tokens")
    label = models.CharField(max_length=120, blank=True)      # "GitHub Actions"
    token_hash = models.CharField(max_length=128)              # store a hash, never the secret
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)
```

- **Issue** (project settings UI / API): generate a high-entropy secret, return it **once**, store
  only its hash. `authenticate_ci_token(*, tenant_id, project_id, token) -> ProjectCIToken | None`
  mirrors `authenticate_runner` (constant-time compare; touch `last_used_at`).
- **Scope:** results ingestion **only** — never the generic runner state route or build claim.
- **Revoke:** flips `revoked`; a revoked token 401s.

## 2. Results-ingestion endpoint (E-X2)

```
POST /api/projects/<project_id>/test-results/
Authorization: CI <token>
X-Tenant-ID: <tenant>
Content-Type: application/xml   (a single JUnit file)   — or multipart for a bundle
Body: <JUnit XML>
Query/headers (provenance): execution_ref=<ci-run-id|commit-sha>  [required — idempotency key]
                            commit_sha=<sha>  branch=<name>  environment=<staging|…>  summary=<text>
```

- **Auth:** `authenticate_ci_token` resolves tenant + project (server-side; never from the body).
- **Parse** the JUnit server-side with the shared parser (§3) → `[{test_ref, status, evidence}]`.
- **Correlate + import** (§4).
- **Idempotent by `(project, execution_ref)`** — a re-post of the same CI run updates the same
  `TestExecution` rather than duplicating (mirrors the build path's run-idempotency).
- **Response:** `{execution_id, status, defects_opened, defects_closed, flaky, quarantined,
  unmapped}` — the same shape callers already get from `import_test_results`.

## 3. Shared JUnit parser (E-X3)

One parser, two callers. The functions in `runner/companion/testresults.py` (`parse_junit`,
`test_ref_for`, evidence capping, the `_TC_ID` lookbehind) are already **pure and Django-free** —
lift them into a neutral module both import, so the companion's worktree collection and the server
ingestion can never drift on how a `<testcase>` maps to a `TC-ID`.

- Home: a Django-free module (e.g. `apps/quality/junit.py`); the companion imports it via the
  existing `ensure_backend_importable()` path, or the module lives under a shared top-level `lib/`.
  **No behavior change** — same regexes, same TC-ID padding rule, same evidence cap.

## 4. Correlation → tracked defects (E-X4)

Post-merge results are **project-level regression**, so there is no single build run to attach to.
v1 keeps this simple and honest:

- **Ensure a per-project `Regression` WorkItem** (get-or-create; `type=TASK` or a dedicated kind,
  `feature_stream="regression"`). It is the container the loopback reconciles against.
- **One `import_test_results` call** with `work_item_id=<Regression container>`, `run_id=None`,
  `execution_ref=<ci-run>`, `results=<parsed>`, `push_to_sor=False`.
- The **existing loopback does the rest**: a FAIL on a non-quarantined test opens a `defect` child
  of the Regression container (its TC-ID + evidence on the defect identify the failing test); a
  later CI run reporting PASS closes it; conflicting statuses across the run quarantine as flaky.
- **`import_test_results` extension (small):** support **run-less idempotency** — when `run_id` is
  `None`, upsert the `TestExecution` by `(work_item, execution_ref)` (add `TestExecution.execution_ref`,
  or reuse `external_ref`). Today it dedupes by `(run, work_item)`; this adds the CI case without
  touching the build case.
- **Unmapped test refs** (a JUnit case with no `TC-…`): still counted in the execution + summary,
  reported as `unmapped` — they don't silently vanish, and they don't fabricate a defect against a
  TC that doesn't exist.

**Gate semantics (per the LOCKED decision):** post-merge regression defects are **tracked work on
the QA board**, surfaced in the existing UI automatically — they are *not* merge-gate blockers (the
merge already happened). They will, however, block a *subsequent* qa_lead `testing` gate for the
same work item exactly as any open test defect does (`testgate.py`, unchanged) — no new gate code.

## 5. CI-side wiring (client-owned; E-X5)

The platform's scope ends at ingestion. The CI **workflow** that runs the suite and posts results is
the client's (their infra, their staging env). The platform provides:

- The **token** (§1) + a copy-paste **post step**, e.g.:
  ```yaml
  - run: npx playwright test --reporter=junit --output-file=results.xml   # or pytest --junitxml=…
  - run: |
      curl -sf -X POST "$SDLC_URL/api/projects/$SDLC_PROJECT/test-results/?execution_ref=$GITHUB_RUN_ID" \
        -H "Authorization: CI $SDLC_CI_TOKEN" -H "X-Tenant-ID: $SDLC_TENANT" \
        -H "Content-Type: application/xml" --data-binary @results.xml
  ```
- **11_cicd** may generate/maintain this step in the client's pipeline as part of its phase (it
  already owns CI config) — the platform never runs the client's CI itself.

## 6. Testing + Definition of Done

- **Unit (auth):** `authenticate_ci_token` accepts a valid token, rejects revoked/wrong/wrong-project;
  the secret is stored hashed and revealed only on issue.
- **Unit (parser):** the shared parser produces identical results for the companion and the endpoint
  (parametrized over the same fixtures already in `test_testresults_parser.py`).
- **Unit (ingestion):** a JUnit post opens a defect on the Regression container + records a
  `TestExecution`; a re-post with the same `execution_ref` is idempotent (no duplicate execution/
  defect); a later post with the test PASSing closes the defect; an empty/no-`TC` report is handled
  (skipped / `unmapped`), never a false green; `push_to_sor` is never reached.
- **API/contract:** the endpoint is tenant/project-scoped (a token for project A cannot post to B);
  malformed JUnit → 400 with a clear message; missing `execution_ref` → 400.
- **DoD:** `make test` green; a real JUnit file posted with a project CI token opens a defect that
  appears on the QA board, and a follow-up green run closes it — end to end, no manual step. The
  loopback, flaky-quarantine, and qa_lead gate are reused unchanged.

## 7. Decisions ledger

- **Reuses D4/D5 (LOCKED):** worktree/CI executes, results import on report; failing test → traced
  `defect`, passing closes it; flaky-quarantine excludes from the blocking gate.
- **Reuses the 2026-07-07 team decision:** `push_to_sor=False` on import (Xray export user-triggered).
- **New (2026-07-18):** CI runs **post-merge/scheduled**; **push** transport; **dedicated per-project
  CI ingest token**; v1 attributes regression failures to a **Regression container** WorkItem
  (per-story traceability attribution deferred).

## 8. Task checklist (for `/BUILD_PLAN.md`)

- [ ] P3-09bX-1 — `ProjectCIToken` model + migration + `authenticate_ci_token` (hashed secret, revoke, last-used); issue/reveal-once + revoke API in project settings.
- [ ] P3-09bX-2 — Shared, Django-free JUnit parser (lift the pure functions from `runner/companion/testresults.py`); both the companion and the backend import the one module (no behavior change).
- [ ] P3-09bX-3 — `POST /api/projects/<id>/test-results/` ingestion endpoint (CI-token auth, JUnit parse, provenance, idempotent by `(project, execution_ref)`).
- [ ] P3-09bX-4 — Correlation: get-or-create per-project `Regression` container WorkItem; call `import_test_results` (run-less) → defects/flaky/quarantine; `unmapped` reporting.
- [ ] P3-09bX-5 — `import_test_results` run-less idempotency by `execution_ref` (`TestExecution.execution_ref` or reuse `external_ref`); the build path (`run+work_item`) unchanged.
- [ ] P3-09bX-6 — Tests (auth, shared-parser parity, ingestion open→close→idempotent→empty/unmapped, tenant scoping) + docs: `runner/README.md`/CI snippet + note 11_cicd can wire the post step.
- [ ] (enhancement, not v1) Per-story defect attribution via the traceability graph (TC-ID → `test_case` → requirement/story), replacing the Regression-container catch-all where a mapping exists.
