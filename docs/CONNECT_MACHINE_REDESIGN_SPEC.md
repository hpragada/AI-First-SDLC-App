# CONNECT MACHINE REDESIGN SPEC — getting a developer's machine onto the platform

**Status:** Approved in principle (full experience, layers 1–5), **parked** — written up for a later
phase, not built in the P2 bug batch. **Owns:** `docs/Bugs.xlsx` S.No 35 (all four findings) and
S.No 138. **Read before starting any of it.**

This is a contract, not a proposal. The team has already chosen the destination; what is fixed here
is the shape of each layer, the order they can be built in, and the facts about today's code that
constrain all of them. What is deliberately *not* fixed is listed in §7 — those are open questions,
recorded rather than guessed.

---

## 1. The problem, measured

The bug row says it plainly:

> the user has to connect to claude code by giving a command containing a token … the user has to
> be in the backend repository in the CLI to perform this. This is not a user friendly approach

"Connect Machine" reads like one step. It is not. Here is what a developer actually does today,
from `runner/README.md` and the code behind it. Every line is a thing that can go wrong on a
Monday morning:

| # | Step | Where it is written down |
|---|---|---|
| 1 | Install Python 3.12 | `runner/README.md` — Prerequisites |
| 2 | Clone **the platform's own repository** onto the laptop | Prerequisites: *"the companion imports `runner.companion` from the root"* |
| 3 | Install the Python dependencies that repo needs | implied by 2 — there is no companion-only dependency list |
| 4 | Install Claude Code and **sign in** to it | Prerequisites |
| 5 | Put `git` on `PATH` | Prerequisites |
| 6 | Clone **one local checkout per repository the project builds** | Prerequisites (`--repo-path` / `--repo`) |
| 7 | Open a terminal **inside the platform repo** and run `python -m runner.companion enroll …` with the tenant id and project id | Quick start, step 1 |
| 8 | Copy the one-time token out of the terminal | Quick start, step 1 |
| 9 | Run `python -m runner.companion serve …` with that token, a worktrees directory and every repo path, **on the command line** | Quick start, step 2 |

…and, only for a project that runs **Test Automation (09b)**, three more:

| # | Step |
|---|---|
| 10 | Install Node.js with `npx` on `PATH` |
| 11 | `npm i -g @playwright/mcp` and `npx playwright install` |
| 12 | Configure `preview_start` on the repository or project profile so the app can be brought up |

**Nine steps for everyone, twelve for a project that automates its tests.** The token — the thing the
Connect Machine screen is about — is step 8 of nine.

Any proposal that "fixes the token" has fixed one ninth of this. That sentence is in this spec so
that the scope cannot quietly shrink back to it later.

---

## 2. Three findings that constrain every solution

These came out of reading the code, and each one rules something in or out. **Read them before
designing anything**, because two of them are load-bearing and the third sets the honest goal.

### 2.1 The companion is not a package — and that is literally the user's complaint

There is no `pyproject.toml`, no `setup.py`, and no wheel anywhere under `runner/`. It is a
directory of modules inside the platform's repository, run as `python -m runner.companion` from the
repository root, because it reaches back into `backend/` at runtime:

```python
# runner/companion/daemon.py — ensure_backend_importable()
backend = Path(__file__).resolve().parents[2] / "backend"
if backend.is_dir() and str(backend) not in sys.path:
    sys.path.insert(0, str(backend))
```

`runner/companion/codeintel_mcp.py` does the same thing for its own import.

**This is the mechanism behind "the user has to be in the backend repository in the CLI".** It is
not a documentation problem or a UX problem. The companion cannot run anywhere else, because the
code it imports is only on disk if you cloned the whole platform. Nothing else in this spec is
reachable until that is fixed, which is why it is layer 1.

### 2.2 The coupling is shallow, bounded, and countable

Four modules, and that is the entire list:

| Imported from `backend/` | By | For |
|---|---|---|
| `drivers.claude_driver` | `daemon.py`, `__main__.py` | running the engine |
| `apps.a11y.capture` | `a11yaudit.py`, `a11ycapture.py` | parsing a screen capture |
| `apps.quality.junit` | `testresults.py` | parsing a JUnit report |
| `integrations.codeintel.builtin` | `codeintel_mcp.py`, `daemon.py` | the built-in code analyzer |

**None of them imports Django at runtime.** `claude_driver` names two Django models
(`apps.registry.models.AgentSpec`, `apps.workitems.models.WorkItem`) but only inside
`if TYPE_CHECKING:`, so the import never executes; `integrations.codeintel.builtin` imports
`integrations.types`, which is plain Python.

**Extraction is bounded work, not a rewrite.** Four modules move to a shared package that both the
backend and the companion depend on. The one thing that needs a decision rather than a move is
`claude_driver`'s two type-only references — either the shared package carries a small protocol, or
those annotations become strings. Neither is hard; both should be decided before anyone starts,
because it is the only place where "just move the file" is not the whole answer.

> **Correction to earlier notes.** These were previously described as **three** modules.
> `integrations.codeintel.builtin` arrived with brownfield code intelligence and is the fourth. The
> conclusion is unchanged; the count in the plan was wrong.

### 2.3 Two steps can never be automated away — say so now

- **Signing in to Claude Code.** The engine is the developer's **own subscription**, found at
  `shutil.which("claude")` (`backend/drivers/claude_driver.py:234`). Anthropic owns that sign-in
  flow. The platform can detect whether it has happened; it cannot perform it.
- **Consenting to code access.** A person agrees to let software read and write their repositories.
  That is a decision, not a step.

**"Zero manual steps" is not reachable. "Two clicks and one sign-in" is.** This is written down so
the goal is not quietly restated as the former later in the project, and so nobody is measured
against a target that does not exist.

---

## 3. The five layers

Each layer has its own contract and its own value. They are ordered so that **each one ships alone**
and leaves the product better than it found it. Nothing here requires all five to be worth starting.

| Layer | What it delivers | Steps it removes |
|---|---|---|
| **1 · Make it installable** | Extract the four modules of §2.2 into a shared package. A companion-only dependency list. Real packaging (`pyproject.toml`, a wheel, a console entry point) so `pip install` works and `sdlc-companion` is a command. | **2, 3** |
| **2 · A bundled installer** | A signed, per-OS installer carrying its own Python runtime, downloadable from the Connect Machine screen. No Python prerequisite at all. | **1** |
| **3 · Browser pairing** | The screen shows a short, single-use, short-lived code. The companion asks for it once; the user is already signed in, so they click **Approve**. The credential is written to a permission-restricted file — never a command line. | **7, 8, 9** |
| **4 · A setup assistant** | The companion checks each prerequisite and offers a **button** for each unmet one: install Claude Code, sign in, install git, **clone the project's repositories** (the platform already knows them), and — only if the project runs 09b — install Node and Playwright. | **4, 5, 6**, and **10–12** where they apply |
| **5 · Keep it running** | Runs as a background service / login item. Auto-updates. The web app shows status and offers Disconnect. | — (removes the *recurring* cost) |

**Layer 1 is a third of the work and closes a security hole on its own** (§4). If only one layer is
ever built, it should be that one.

### Contracts, per layer

**Layer 1.**
- New shared distribution — name to be chosen (§7) — containing the four modules of §2.2 and nothing
  else. The backend depends on it; the companion depends on it; neither imports the other's tree.
- The companion's dependency list is its own and is **short**: the Agent SDK, an HTTP client, and
  the two parsers' needs. It must not pull Django, Postgres drivers, Temporal, boto3 or the PDF
  toolchain onto a laptop — the backend's list is for a server, and installing it on a developer
  machine is both slow and a much larger attack surface than the job requires.
- `ensure_backend_importable()` and its `codeintel_mcp.py` twin are **deleted**, not kept as a
  fallback. A fallback path that still works is a path that still gets used, and the whole point is
  that the platform repo stops being a prerequisite.
- Acceptance: a companion installed from a wheel, on a machine with **no clone of this repository**,
  enrolls and runs a phase end to end.

**Layer 2.**
- One installer per supported OS (§7 decides which), each carrying its own Python runtime.
- **Signed** — see §6.1, and start that before the engineering.
- Served from the Connect Machine screen, so the download and the pairing are one page.

**Layer 3.** The credential model, which is where all four S.No 35 findings actually live:
- The platform issues a **pairing code**: short, single-use, short-lived, and **bound to the user who
  is looking at the screen**.
- The companion exchanges it for a credential and stores it in a permission-restricted file. The
  secret never appears on a command line or in a process listing.
- Credentials **expire**, and can be renewed by a companion that is still trusted.
- **Disconnect means the machine, not the row.** Today's Disconnect revokes one enrollment record
  and leaves that machine's other tokens active. Whatever replaces it must revoke the *machine*.
- The enrollment is **owned by the approving user**, and there is no other way to create one — which
  is what closes S.No 138 (§4).

**Layer 4.**
- The companion reports what it found: engine present? signed in? git? repositories cloned? Node and
  Playwright, if this project needs them?
- Each unmet item is an action, not a sentence of documentation. **Whether the assistant may install
  Claude Code itself is an open question (§7)** — some organisations forbid software installing
  software.
- Cloning is the highest-value one and the easiest: the platform already knows the project's
  repositories, so "clone them" is a button with no typing.

**Layer 5.**
- Background service (launchd / systemd user unit / Windows service), auto-update, and a status +
  Disconnect surface in the web app that agrees with reality.

---

## 4. What this closes

**All four S.No 35 findings**, because they are one question — *how does a headless machine
authenticate?* — and layer 3 answers it once:

| Finding | Closed by |
|---|---|
| Disconnect revokes one enrollment row; a developer who generated three tokens still holds two working ones | Layer 3 — revoke the machine, not the row |
| The token is passed on the command line, so any process listing reveals it | Layer 3 — pairing code exchanged for a file-stored credential |
| Enrollment tokens never expire (`RunnerEnrollment` has no expiry field at all) | Layer 3 — credentials expire and renew |
| `POST /api/runners/` still accepts an anonymous caller | Layer 3 — pairing requires a signed-in user by construction |

**And S.No 138**, which the team folded in — two developers sharing one enrollment record.

It is worth being precise about why, because the two are the same bug wearing different clothes.
Enrollment ownership is decided here:

```python
# backend/api/runner_views.py — RunnerEnrollmentView.post
developer_id = str(user.id) if user is not None else request.data.get("developer_id")
```

The CLI enroll path **has no session**, so who owns an enrollment is whatever `--developer-id` a
human typed — or nobody, if they typed nothing. And a token, once minted, authenticates any machine
holding it. Two developers sharing one enrollment is the expected outcome of that design, not a
mishap. Dispatch routes by `developer_id` (`backend/orchestration/trigger.py::_resolve_enrollment`),
so the attribution is wrong from the first run.

Layer 3 makes the approving user the owner, with no other path to an enrollment. There is then no
way to produce a shared record.

> **A note on the anonymous endpoint.** The hold is deliberate and is recorded in
> `backend/api/runner_views.py::RunnerEnrollmentView.get_permissions`, in the code, where somebody
> tempted to "fix" it will read it. (Earlier notes attributed this to ADR 0004; that ADR is about
> membership-versus-role authorization and does not cover it.) Closing the POST on its own would
> break the documented onboarding path while answering none of the credential model — which is
> exactly why it waits for this work rather than being patched ahead of it.

---

## 5. Costing

**Layers 1–3: ~2.5–3 weeks. All five: ~6–8 weeks.** Excluding code-signing procurement (§6.1), which
is calendar time, not engineering time, and must start first.

> **Correction to earlier notes.** An earlier estimate of "7–9 days" was given for this work. It
> assumed the companion was already a package and only the credential flow needed replacing. §2.1
> shows it is not. The estimate above is the corrected one.

---

## 6. Three things that will bite if they are not started early

### 6.1 Code signing is procurement, not engineering

Certificates cost money, need an organisational identity, and have lead times measured in weeks.
Unsigned installers are blocked by SmartScreen on Windows and refused outright by Gatekeeper on
macOS — so an unsigned layer 2 is not a rough edge, it is a layer that does not work. **Start the
certificate before the code.** It is the only item here whose delay cannot be absorbed by working
harder.

### 6.2 The installer is powerful software

It installs tools and clones repositories onto a person's machine. That is a lot of authority, and
the pairing is the only thing standing between it and the wrong workspace. Short-lived, single-use,
and bound to the approving user are **security requirements**, not conveniences: a machine must
never be trickable into pairing with a workspace its owner did not choose.

### 6.3 Layer 1 ships alone, and should

It is roughly a third of the work, it makes the companion installable by anyone, and it is what
lets the anonymous-enrollment hole be closed. Sequencing it behind the installer would leave the
security finding open for the length of the whole project for no gain.

---

## 7. Open questions — for the team, recorded rather than guessed

1. **Which operating systems?** Every additional OS is another installer, another signing identity,
   and another support surface. macOS + Windows + Linux is not automatically the answer.
2. **May the setup assistant install Claude Code itself?** Some organisations forbid software that
   installs software, and some manage developer tooling centrally. If the answer is "no", layer 4
   detects and instructs rather than acting — a materially different build.
3. **Is a VS Code extension worth costing as a second front door?** It is a cheap one: the open
   workspace *is* the clone, which removes step 6 for free, and the extension host can run the
   companion. Worth a day of investigation before committing to installers alone.
4. **What is the shared package called, and where does it live?** In this repository as a workspace
   member, or its own? This decides how the backend consumes it and how the companion is versioned
   against a platform it talks to.
5. **How long should a credential live, and does a renewal need a human?** A companion that goes
   quiet for a fortnight and comes back is normal; one that goes quiet for six months is a laptop in
   a drawer.

---

## 8. Migration — nobody is stranded mid-sprint

Machines enrolled today are running real work. The rollout must not require a flag day.

- **Existing enrollment tokens keep working** until their machine is re-paired. The new credential
  path is added beside the old one; the old one is removed in a later, separate change once the
  fleet has moved.
- **The web app tells a developer their machine needs re-pairing**, in the place they already look
  at companion status, rather than failing a run and letting them work out why.
- **Shared enrollments (S.No 138) are identified and reported before they are broken up.** A run
  attributed to the wrong person is bad; a developer whose companion silently stops claiming work
  mid-sprint is worse. Audit first, migrate second, revoke third.
- **The 09b prerequisites are unaffected** — Node and Playwright are already on those machines and
  layer 4 only makes installing them easier for the next one.

---

## 9. Related

- `docs/Bugs.xlsx` — S.No 35 (this spec's owner, stays **Open** until built), S.No 138 (folded in).
- `backend/api/runner_views.py` — where the deliberate anonymous-POST hold is recorded.
- `runner/README.md` — the nine (twelve) steps this replaces.
- `docs/PHASE_3_09B_RUNNABLE_SPEC.md` — the 09b prerequisites layer 4 automates.
- `docs/decisions/0004-authorization-membership-not-role.md` — the authorization model layer 3's
  pairing must fit inside.
