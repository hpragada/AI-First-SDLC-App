# CONNECT MACHINE REDESIGN SPEC — from nine manual steps to two clicks and one sign-in

**Status:** Specified, not built. Parked by team decision (2026-09-04) for implementation later.
**Owns:** Bugs.xlsx **S.No 35** (Connect machine — enhancement) and **S.No 138** (two developers
share one enrollment), which the team folded into it.
**Unblocks:** the anonymous `POST /api/runners/` deliberately left open during the P1 batch — see
[ADR 0004](decisions/0004-authorization-membership-not-role.md).
**Team decision:** build **the full experience (layers 1–5)**, not the reduced pairing-only option.

---

## 0. Why this document exists

S.No 35 reads as one complaint: *the user has to paste a command containing a token, from inside
the backend repository.* Fixing that sentence literally would take onboarding from **nine manual
steps to eight**.

This spec exists so that does not happen. It records what the setup actually costs a developer
today, the three structural facts that constrain any fix, and the five layers that together get to
the team's stated goal — *"everything should happen in just a click of a button."*

It is written to be picked up cold, by whoever implements it, without this conversation.

---

## 1. The problem, measured

What a developer does today, from `runner/README.md` (Quick start, Prerequisites) and the code:

| # | Step | Source |
|---|---|---|
| 1 | Install **Python 3.12** | `runner/README.md` Prerequisites |
| 2 | **Clone the platform's own source repository** — the companion imports modules from `backend/`, so it cannot run without a checkout of the platform itself | `runner/companion/daemon.py:223-231` |
| 3 | Install the Python dependencies — there is **no companion-specific list**, so this pulls Django, psycopg, Temporal, boto3, PyMuPDF and the rest of `backend/requirements.txt` onto a laptop that uses none of them | `backend/requirements.txt` |
| 4 | Install **Claude Code** and sign in | `runner/README.md` Prerequisites |
| 5 | Install **git**, clone one local copy per project repository | `runner/README.md` Prerequisites |
| 6 | For test automation (09b): install **Node.js**, Playwright MCP, and browser binaries | `runner/README.md` "Additional prerequisites" |
| 7 | Run `enroll` — passing the **workspace UUID and project UUID on the command line** | `runner/companion/__main__.py:66-80` |
| 8 | **Copy the token** out of the terminal output | `__main__.py:78` — *"Store the token securely - it is shown only once."* |
| 9 | Run `serve` — passing the URL, workspace UUID, token, a worktrees path, and a path per repository | `__main__.py:184-203` |

**The token is step 8 of 9.** Steps 1, 2, 3, 5 and 9 each require knowing something the platform
already knows, or installing something the platform could install.

**Do not let this be re-scoped to "fix the token."** That is one ninth of the problem, and it is
not the ninth the user complained about — the complaint names the *repository checkout* (step 2).

---

## 2. Three findings that constrain any solution

Established by reading the code, not assumed. Each one rules an option in or out.

### 2.1 The companion is not a package — and this is the literal cause of the complaint

There is **no `pyproject.toml`, no `setup.py`, no packaging of any kind** under `runner/`. The
companion runs as `python -m runner.companion` from the root of a platform checkout, because
`ensure_backend_importable()` puts `<repo>/backend` on `sys.path` at runtime:

```python
# runner/companion/daemon.py:223-231
def ensure_backend_importable() -> None:
    """Put the repo's `backend/` on sys.path so `drivers.*` resolves. ..."""
    backend = Path(__file__).resolve().parents[2] / "backend"
```

So "the user has to be in the backend repository in the CLI" is not a documentation problem or a
UX oversight. **It is a structural property of how the companion is built**, and no amount of
installer polish removes it. Layer 1 exists to remove it.

### 2.2 The coupling is shallow and bounded — extraction is feasible

The companion imports exactly **four** things from the platform backend, and that is the whole list:

| Import | Used for | Call sites |
|---|---|---|
| `drivers.claude_driver.ClaudeDriver` | Running the engine | `daemon.py:236-239`, `__main__.py:87` |
| `apps.a11y.capture` (`parse_capture`, `summarize`, `MAX_SCREENS`, `CaptureError`) | Parsing accessibility captures | `a11ycapture.py:55,72`, `a11yaudit.py:132,213` |
| `apps.quality.junit` (`parse_junit`, `summarize`) | Parsing JUnit results | `testresults.py:53,67` |
| `integrations.codeintel.builtin.BuiltinCodeIntel` | The built-in code analyzer | `codeintel_mcp.py:38`, `daemon.py:693` |

> **Correction (2026-09-07).** This was recorded as **three** imports when the spec was first
> written. `integrations.codeintel.builtin` arrived with brownfield code intelligence and is the
> fourth — it also has its own `sys.path` bootstrap in `codeintel_mcp.py:29-33`, a second copy of
> the one in §2.1, so layer 1 has two of them to delete rather than one. The conclusion below is
> unchanged; the count was not.

**All four are Django-free at runtime** — verified by reading their import blocks. Two caveats an
implementer needs, neither of which changes the answer:

- `claude_driver` **names** two Django models, `apps.registry.models.AgentSpec` and
  `apps.workitems.models.WorkItem` — but only inside `if TYPE_CHECKING:`, so the import never
  executes. It is a **type-only** dependency. This is the single place where "move the file" is not
  the whole answer: the shared package either carries a small protocol for those two, or the
  annotations become strings. **Decide which before starting**, because discovering it mid-extraction
  is what turns a bounded job into an open-ended one.
- `integrations.codeintel.builtin` imports `integrations.types`, which is plain Python and travels
  with it.

**Therefore extraction into a small shared package is bounded, low-risk work — not a rewrite.**
This is the single most important finding in this document, because it is what makes the whole
plan affordable.

### 2.3 Two things can never be automated away

**Signing in to Claude Code.** The engine is the developer's own subscription, not an API key. The
driver locates it on the machine:

```python
# backend/drivers/claude_driver.py:229-235
#   explicit cli_path arg  ->  CLAUDE_CLI_PATH env  ->  the `claude` on PATH.
_cli = cli_path or os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
```

That sign-in belongs to Anthropic and to the user. **We can launch it with a button; we cannot
perform it.**

**Consent to code access.** Builds run against real local clones. The platform can clone the repos
*for* the developer — it already knows which ones — but a human must agree and choose where.

> **State this plainly wherever the goal is restated: "the user does nothing manually" is not
> reachable. "Two clicks and one sign-in" is.** Nine steps to two clicks is the win; promising
> zero sets the project up to be judged a failure for delivering exactly what was possible.

**A third thing that is *not* a constraint but is often mistaken for one:** running the engine on
the platform's servers would give genuinely zero setup — and would move every run from the user's
subscription onto a metered API key. That is a business-model change, not a technical one. It is
out of scope for this spec and should be a separate decision if ever wanted.

---

## 3. The target experience

1. In the platform: **Connect machine** → **Download** (the page detects the OS)
2. Double-click the installer
3. The browser opens; the user is already signed in; they click **Approve**
4. A readiness checklist appears. Each unmet item is a **button**: *Sign in to Claude* (their own
   sign-in, once), *Clone repositories* (they pick a folder)
5. Green tick. They trigger phases from the web app and never open a terminal again

**Two clicks, one sign-in, one folder choice.** No terminal, no UUIDs, no token, no prerequisites.

---

## 4. The five layers

Each layer has standalone value and each depends only on the ones before it. **Layer 1 can ship
alone and is worth shipping alone.**

### Layer 1 — Make the companion installable

**Contract:** `pip install sdlc-companion` succeeds on a machine with no platform checkout, and
`sdlc-companion --help` runs.

- Extract the four modules from §2.2 into a shared distributable package that both the backend and
  the companion import. They are Django-free at runtime today; a test must assert they stay that
  way, or this layer silently un-does itself. Settle `claude_driver`'s two type-only model
  references first (§2.2) — it is the only part of the move that needs a decision.
- Delete **both** `sys.path` bootstraps (`daemon.py:223-231` and `codeintel_mcp.py:29-33`) rather
  than leaving either as a fallback. A fallback that still works is a path that still gets used,
  and the whole point of this layer is that a platform checkout stops being a prerequisite.
- Add `pyproject.toml` with a console entry point, so the invocation stops being
  `python -m runner.companion` from a specific directory.
- Give the companion **its own dependency list** — approximately `claude-agent-sdk`, `mcp`,
  `anyio`, `pydantic`. **Not** Django, psycopg, Temporal, boto3, PyMuPDF or the PDF/Office
  toolchain. A developer laptop should not acquire a database driver to run a build.
- Delete `ensure_backend_importable()` and its three call sites.

**Kills steps 2 and 3.** **Closes the structural cause of S.No 35's original complaint.**

### Layer 2 — A real installer

**Contract:** a signed, per-OS installer that requires no Python on the target machine.

- Bundle a self-contained Python runtime with the companion.
- Serve it from the Connect Machine page, with OS detection choosing the artifact.
- Sign it. See §9 — this is procurement, and it is the long pole.

**Kills step 1.**

### Layer 3 — Browser-initiated pairing

**Contract:** a machine is connected without any secret being displayed, copied or typed.

Flow:
1. The installer finishes and starts the companion, which has no credential.
2. The companion requests a **pairing code** — short, single-use, short-lived (minutes).
3. It opens the user's browser at the platform's pairing URL, carrying the code.
4. The user is already signed in. They see the machine's name and the workspace/project it will be
   connected to, and click **Approve**.
5. The platform issues the credential to the companion over the pairing channel; the companion
   writes it to a permission-restricted file.

**Nothing is ever shown to the user to copy.** The credential does not appear in the browser, the
terminal, the process list or the shell history.

**Kills steps 7, 8 and 9.** **Closes all four S.No 35 security findings and S.No 138** — see §5.

### Layer 4 — The setup assistant

**Contract:** every remaining prerequisite is a button in the UI, not an instruction in a README.

The companion self-checks and reports; the platform renders a checklist:

| Check | If unmet |
|---|---|
| Claude Code installed | **Install** — runs the official installer |
| Claude Code signed in | **Sign in** — launches the login flow in the user's browser |
| git present | **Install** |
| Project repositories cloned | **Clone them** — the platform supplies the repository list from `projects.Repository`; the user picks a parent folder |
| Node + Playwright | **Install** — shown **only if** the project actually runs test automation (09b), so a project that never will is never asked |

The repository step is the one that most repays automation: the platform already holds the
repository list, so the developer should never be looking one up.

**Kills steps 4, 5 and 6 as manual work.** The Claude sign-in remains the user's action, by
necessity (§2.3).

### Layer 5 — Keep it running

**Contract:** the machine stays connected across reboots without the user thinking about it.

- Register as a background service (Windows) or login item / launch agent (macOS/Linux).
- Auto-update, so a companion never falls behind the platform it talks to.
- Status, last-seen and **Disconnect** live in the platform UI. `RunnerEnrollment.last_seen`
  (`backend/apps/runs/models.py:71`) already backs the status display.

---

## 5. What this closes

### The four findings on S.No 35

| # | Finding | Closed by |
|---|---|---|
| 1 | **Disconnect revokes one enrollment row**, so a developer who generated three tokens keeps two working ones | Layer 3 + §6: disconnect revokes **every** active credential for that developer+project |
| 2 | **The token travels on the command line**, so any process listing reveals it | Layer 3: no secret is ever an argument |
| 3 | **Enrollment tokens never expire** | Layer 3 + §6: credentials expire and refresh |
| 4 | **`POST /api/runners/` accepts an anonymous caller** | Layer 3: pairing is authenticated by the browser session, so the anonymous path can be **removed** |

Finding 4 is the one with a debt attached. It was **deliberately left open** in the P1 batch —
`RunnerEnrollmentView.get_permissions` (`backend/api/runner_views.py:220-240`) carries a long
comment explaining that gating it would break the documented CLI onboarding, which sends only an
`X-Tenant-ID` header and has no session to present. **This spec is what allows that comment to be
deleted.** Until then, the hole stays open by design.

### S.No 138 — shared enrollment identity

Two developers currently operate under one enrollment record, so runs, claims and attribution are
conflated. Layer 3 fixes it structurally: a credential is issued **to the browser session that
approved it**, so it is bound to a real user by construction. `RunnerEnrollment.developer`
(`models.py:63-65`) is already nullable and already exists — pairing simply always populates it.

**Do independently of this spec, now:** audit which existing runs used the shared enrollment, so
the team knows what is mis-attributed. That is a read-only query and needs no design decision.

---

## 6. Data model and API contracts

Deliberately sketched, not fixed — the implementer should confirm against the code of the day.
What is **not** negotiable is the security model in §7.

### Model

`RunnerEnrollment` (`backend/apps/runs/models.py:49-75`) already carries `project`, `developer`,
`label`, `enroll_token_hash`, `repos`, `status` (`active`/`revoked`) and `last_seen`. It stores a
**hash, never the secret** — that seam is correct and stays.

Additions:
- **credential expiry** — an `expires_at`, so finding 3 is closed at the model rather than by
  convention
- **a pairing request record** — code hash, requested machine label, created-at, expiry,
  single-use marker, and the resulting enrollment once approved

> **Migration discipline (ADR 0003):** any additive column on a table that already has rows must
> be **nullable** or carry a **database-level default**. Branches share one Postgres, and a branch
> that does not know a `NOT NULL` column with no default cannot insert. This bit the team once
> already on `projects/0012`.

### Endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/runners/pair/request` | none — the companion has no credential yet | Returns a short-lived, single-use pairing code. Rate-limited per source. |
| `GET /api/runners/pair/{code}` | **session** | Renders what is being approved: machine label, workspace, project |
| `POST /api/runners/pair/{code}/approve` | **session** + project membership | Creates the enrollment bound to the session user; issues the credential |
| `POST /api/runners/pair/{code}/claim` | pairing code | The companion collects its credential exactly once |
| `POST /api/runners/{id}/revoke/` | session | Extended: revokes **all** of that developer's active credentials for the project (finding 1) |
| `POST /api/runners/` | — | **Removed** once pairing ships (finding 4) |

The existing `GET /api/runners/` (the caller's own enrollments,
`RunnerEnrollmentView.get:242-247`) is unchanged.

---

## 7. Security model

**Non-negotiable, because the installer is powerful software: it installs tools and clones
repositories onto a developer's machine.**

1. **A pairing code is short-lived, single-use, and bound to the approving user.** It is an
   authorization to connect *one* machine, once.
2. **The code is not a credential.** Holding it lets a machine *ask*; only a human clicking Approve
   in an authenticated session grants anything.
3. **What is being approved must be shown before it is approved** — machine label, workspace,
   project. A user must never approve an opaque request.
4. **The credential is written to a permission-restricted file**, never an environment variable,
   never a command-line argument, never printed.
5. **Membership is checked at approval.** The current anonymous endpoint cannot check membership
   because it has no session (`runner_views.py:258-260` says so explicitly). Pairing has one, so
   this hole closes for free.
6. **`pair/request` is unauthenticated and therefore rate-limited**, per source and globally. It
   mints nothing; it must still not be a free amplifier.
7. **Revocation is complete.** Disconnect ends every credential that machine and developer hold for
   the project — the fix for finding 1, and the reason revocation must be modelled per developer,
   not per row.

---

## 8. Costing and sequencing

Ranges, not commitments. They assume the four S.No 35 findings and S.No 138 are done together.

| Layer | Effort |
|---|---|
| 1 · Extraction + packaging + companion dependency list | **3–4 days** |
| 3 · Pairing: endpoints, code lifecycle, approve screen, credential handover | **2–3 days** |
| Credential storage, expiry + refresh, revoke-all, per-developer enrollment | **3 days** |
| Remove the anonymous endpoint; migrate machines already enrolled | **1–1.5 days** |
| Tests, docs, and the `runner/README.md` rewrite | **1.5–2 days** |
| **Layers 1–3 subtotal** | **~2.5–3 weeks** |
| 2 · Bundled signed installer, per OS | **8–12 days** |
| 4 · Setup assistant (detect, install, sign-in trigger, clone, Node/Playwright) | **5–7 days** |
| 5 · Background service, auto-update | **4–6 days** |
| **All five layers** | **~6–8 weeks** |

**Correction on the record:** an earlier estimate of "7–9 days" for pairing assumed the companion
was already packaged. It is not (§2.1). The numbers above include Layer 1 and are the honest ones.

**Recommended sequencing: ship Layer 1 first, on its own.** It is roughly a third of the total, it
makes the companion installable, it removes the platform checkout from a developer's machine, and
combined with Layer 3 it closes the security hole. Layers 2, 4 and 5 are the experience; layers 1
and 3 are the correctness.

---

## 9. Dependencies to start before the code

**Code-signing certificates are procurement, not engineering.** They cost money and have lead
time. An unsigned installer is blocked by Windows SmartScreen and refused by macOS Gatekeeper — so
Layer 2 cannot ship without them, no matter how finished the code is.

**Start this the day Layer 2 is committed to, not the day it is coded.** It is the only item here
that cannot be compressed by working harder.

---

## 10. Migration and backward compatibility

- **Machines already enrolled must not be stranded mid-sprint.** Existing tokens keep working until
  their developer re-pairs; the platform shows a prompt to re-pair rather than cutting them off.
- **`POST /api/runners/` is removed only after** the pairing path is live and the documented
  onboarding has been rewritten. Removing it earlier reproduces exactly the breakage that caused it
  to be held open in the first place.
- **`runner/README.md` becomes wrong the day this ships.** Rewriting it is part of the work, not a
  follow-up.

---

## 11. Open questions for the team

Recorded rather than guessed. Each changes the cost.

1. **Which operating systems?** Windows only, or Windows + macOS + Linux. This is most of Layer 2's
   cost and all of its signing cost.
2. **May the assistant auto-install Claude Code**, or only detect it and link to the official
   installer? Auto-installing is friendlier; some organisations forbid software installing
   software.
3. **Is a VS Code extension worth costing as a second front door?** Many developers already have
   the editor open with the repository cloned — the workspace *is* the clone, which removes the
   most awkward step in Layer 4 for free. It would not replace the installer (the companion should
   run without an editor open), but it is cheap alongside it.
4. **Are the target developers already set up** — the team's own engineers with Python, git and
   Claude Code in place — or people meeting the platform cold? If cold, the setup assistant matters
   more than the pairing flow and Layer 4 should come before Layer 2.

---

## 12. Out of scope

- **Server-side execution of the engine.** It would eliminate setup entirely and change the cost
  model from a subscription to metered API usage (§2.3). A separate decision, not this spec.
- **Multi-project enrollment from one credential.** The current model binds one enrollment to one
  project (`models.py:60-62`), and the Connect Machine screen's multi-select is decorative — see
  Bugs.xlsx **S.No 223**, fixed separately by making it single and controlled. If multi-project
  machines are wanted, decide it here before Layer 3 fixes the shape.
- **S.No 198** (the placeholder token rendered on failure) is a straightforward bug in today's
  screen and is fixed in the current P2 batch. It is not deferred to this spec.
