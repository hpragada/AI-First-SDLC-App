# SDLC Companion (local runner)

The companion runs the platform's build/plan phases on the developer's **own machine**, against
the **local logged-in Claude Code** (no API key) — the user drives everything from the web app.
It claims work dispatched to its enrollment, runs the agent in a managed git **worktree**, and
reports back; the platform owns all git side-effects (commit/push/PR) — the agent never runs git.

## Quick start

```bash
# 1. Enroll (returns a one-time token — store it securely)
python -m runner.companion enroll --api-url https://PLATFORM --tenant T --project P --label laptop

# 2. Serve (headless daemon; claims + runs dispatched phases)
python -m runner.companion serve --api-url https://PLATFORM --tenant T --token TOK \
    --worktrees ~/sdlc --repo-path ~/repos/api                    # single-repo
python -m runner.companion serve --api-url https://PLATFORM --tenant T --token TOK \
    --worktrees ~/sdlc --repo acme/api=~/repos/api --repo acme/web=~/repos/web   # multi-repo

# (optional) run a single BuildTask locally
python -m runner.companion run --task task.json --repo-path ~/repos/api --worktrees ~/sdlc
```

## Prerequisites

- **Python 3.12** and the repo checked out (the companion imports `runner.companion` from the root).
- **Claude Code** logged in on this machine (subscription auth; the companion uses it, not an API key).
- **git** on `PATH` (the platform commits/pushes through the local clone).
- One local **clone per repo** the project builds (passed via `--repo-path` / `--repo`).

### Additional prerequisites for Test Automation (09b)

The **Test Automation** phase (09b) explores the running app to discover real DOM locators, so a
companion that will run 09b needs two more things:

1. **Playwright MCP + browsers.** The build driver launches `npx @playwright/mcp@latest` as a
   phase-scoped MCP server (only for 09b — 07/11 builds never start a browser). Install once:

   ```bash
   npm i -g @playwright/mcp        # or rely on `npx -y` to fetch it on first run
   npx playwright install          # download the browser binaries
   ```

   Node.js (with `npx`) must be on `PATH`. If these are missing, 09b's Live Application Exploration
   **halts by design** with a clear message rather than guessing locators — install them and re-run.
   The browser is **origin-scoped to the preview host** (`--allowed-origins`), so it can reach only
   the app under test.

2. **A preview-start config on the project** so the companion can bring the app up from the worktree
   (the live target 09b explores). Configure it **per repo** (the served thing is a repo — the
   frontend repo runs the UI) on `Repository.preview_start`, or on `ProjectProfile.preview_start` as
   a single-target fallback:

   ```json
   {
     "command": "npm run dev",
     "port": 5173,
     "health_path": "/",
     "ready_timeout_s": 120,
     "ready_log": "Local:"
   }
   ```

   The companion runs `command` in the worktree, waits until the app is ready (a `2xx/3xx` at
   `port` + `health_path`, **or** a line containing `ready_log` appears in the server output, up to
   `ready_timeout_s`), and hands the resulting `http://127.0.0.1:<port>` URL to the agent. The app
   is torn down when the build finishes. **No config ⇒ a 09b build fails loud** rather than run
   without a target. Secrets the run needs are injected as env for the server process (never written
   into the repo).

See `docs/PHASE_3_09B_RUNNABLE_SPEC.md` for the full contract.

## Reporting automated-test results from CI (09b execution)

09b **authors** the automated scripts (above); the client's **CI runs them** post-merge against a
real/staging environment and **posts the JUnit results back** to the platform, which turns failures
into tracked defects (the defect loopback). This keeps execution in the tool-of-record — slow, flaky
E2E suites don't sit in the build path — while the platform still owns the defect state.

**1. Issue a CI token** (project admin), in the app's project settings or via the API:

```bash
curl -sf -X POST "$SDLC_URL/api/projects/$SDLC_PROJECT/ci-tokens/" \
  -H "X-Tenant-ID: $SDLC_TENANT" -H "Cookie: $SESSION" \
  -H "Content-Type: application/json" --data '{"label":"GitHub Actions"}'
# → {"id": "...", "token": "SHOWN-ONCE-COPY-IT-NOW", ...}   (the secret is never returned again)
```

Store the returned `token` in your CI secret store (e.g. `SDLC_CI_TOKEN`). Revoke with
`DELETE /api/projects/<id>/ci-tokens/<token-id>/`.

**2. Post JUnit at the end of the CI job.** Run the suite with a JUnit reporter, then upload the
report — the `execution_ref` (any stable CI run id) makes re-runs idempotent:

```yaml
# e.g. GitHub Actions — the platform is CI-agnostic; any runner that can curl works
- run: npx playwright test --reporter=junit --output-file=results.xml   # or: pytest --junitxml=results.xml
  # (run against your deployed preview/staging env; a red suite here still uploads its results)
- if: always()
  run: |
    curl -sf -X POST \
      "$SDLC_URL/api/projects/$SDLC_PROJECT/test-results/?execution_ref=$GITHUB_RUN_ID&branch=$GITHUB_REF_NAME&commit_sha=$GITHUB_SHA" \
      -H "Authorization: CI $SDLC_CI_TOKEN" -H "X-Tenant-ID: $SDLC_TENANT" \
      -H "Content-Type: application/xml" --data-binary @results.xml
```

The platform parses the report, and for each **failing** test opens a `defect` on the project's
**CI Regression** work item (the TC-ID + failure evidence identify the test); a later run reporting
the test **passing closes** it, and a test that flips across runs is **quarantined**. Cases whose
name carries no `TC-…` are reported as `unmapped` (counted, but never turned into a phantom defect).
Nothing is pushed to Xray — exporting results there stays a user-triggered action.

**Responses:** `200` imported · `422` the body had no parseable test cases · `400` missing
`execution_ref` or empty body · `401` bad/cross-project token.

The **11_cicd** phase can generate and maintain this post-results step in the client's pipeline as
part of its CI config — the platform never runs the client's CI itself. Full contract:
`docs/PHASE_3_09B_EXECUTION_SPEC.md`.
