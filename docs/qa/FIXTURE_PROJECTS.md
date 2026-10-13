# Fixture Projects — three test projects for the SDLC platform

Three projects to run the greenfield lifecycle against. They exist to **test the platform**, not to
ship product, so each one is chosen for coverage and for how quickly a tester can judge whether an
artifact is any good.

Copy each block field-for-field into **Create Project → Project Profile**. The field names below
match the screen exactly.

---

## Why these three, and why they differ

Each project changes **exactly one thing** from the baseline. If all three differed in several ways
at once, a failure could not be attributed.

| | Repos | Backend | Tech stack & standards | What it isolates |
|---|---|---|---|---|
| **1 · PeopleDesk** | 1 | **TypeScript / NestJS** | Fully specified | **Stack obedience.** Does the profile actually reach the agents, or do they default to what they know? |
| **2 · Returns Desk** | 3 | Python + TypeScript | Fully specified | **Multi-repo.** API contract, cross-repo drift gate, repo-assignment review at the Task Breakdown gate. |
| **3 · FleetCare** | 1 | *agent decides* | **Left to the agent** | **Underspecification.** Can the Architecture phase choose a stack and defend it at its gate? |

> **Leave the answer blank, not the question.** FleetCare has no tech stack, but it *does* have
> NFRs, constraints and context. An unconstrained choice is an unjudgeable one — the tester needs
> something to grade the agent's decision against.

> **Why one project is deliberately not Python.** The platform doing the building is itself Django
> and Python. If all three fixtures were Python too, a good-looking result would prove nothing —
> you could not separate "the agent read the profile" from "the agent wrote what it always writes".
> PeopleDesk is TypeScript end to end for exactly that reason, and it is the simplest of the three,
> so a stack-bias defect surfaces on day one rather than on the most expensive project in week two.
> **Any Python in PeopleDesk's output is a defect.**

> **Two things every fixture needs before accessibility testing works.** All three profiles target
> **WCAG 2.2 AA** (not 2.1) because the accessibility capability being built targets 2.2 — at 2.1
> the four criteria new in 2.2 would never be exercised. And each project must have **preview
> configuration** on its UI-serving repository, or the companion cannot start the app: 09b
> test-automation never runs, no scan happens, and you get silence rather than an error. The preview
> config is set on the Repositories screen, not in the profile. See each project's *Repository &
> preview configuration* section. Note these fixtures test that the accessibility pipeline **runs** —
> proving its findings are **correct** needs the hand-built A11y Proving Ground
> (`docs/web-accessibility/evaluation/PROVING_GROUND_APP_SPEC.md`), because here the platform wrote the app and
> you have no independent answer key.


---
---

# 1 · PeopleDesk — HR Portal

**Baseline / control · single repo · fully specified**

### Project name
```
PeopleDesk
```

### Track
```
Greenfield
```

### Description
```
PeopleDesk is an internal HR portal for a single company's employees. Authenticated staff can view
the employee directory, see their own leave balance, apply for leave, and track the status of their
requests. Managers see a queue of requests from their direct reports and approve or decline them
with a comment. HR administrators maintain the employee records, the annual holiday calendar, and
the leave policy values.

The application is deliberately narrow: it covers directory, leave and announcements only. It does
NOT cover payroll, recruitment, performance reviews, timesheets, expenses or benefits
administration. There is no employee self-service document vault and no integration with any
external HRIS — employee records are maintained inside the application.

Three roles exist: employee, manager, and HR admin. Every employee has exactly one manager, except
the CEO who has none.
```

### Domain
```
Human Resources
```

### Tech stack
```

Runtime: Node.js 22 LTS
Language: TypeScript 5 (backend and frontend)
Backend Framework: NestJS 10 — modules, controllers, providers, guards, DTOs
ORM / Migrations: Prisma 5
Database: PostgreSQL 16
Validation: class-validator + class-transformer on every DTO
Authentication: Passport JWT strategy; access and refresh tokens; argon2 password hashing
Authorisation: NestJS guards, one per role boundary
Frontend: React 18, TypeScript 5, Vite
State Management: TanStack Query for server state; React Context for session
Styling: Plain CSS with CSS custom properties — no UI component library
Testing: Jest + Supertest (backend); Vitest + React Testing Library (frontend)
Package manager: pnpm, with a workspace for the backend and frontend packages
Cloud / Hosting: one container per package on the company's internal Kubernetes cluster
```

### Coding standards
```
Style Guide (Backend): ESLint with @typescript-eslint recommended-type-checked + Prettier
Style Guide (Frontend): ESLint with the Airbnb TypeScript config + Prettier
Type checking: TypeScript strict mode in both packages. noImplicitAny, strictNullChecks and
noUncheckedIndexedAccess all on. The `any` type is not permitted; use `unknown` and narrow
Structure (Backend): NestJS convention — one module per domain area, controllers hold no business
logic, all logic lives in providers/services, all input crosses the boundary as a validated DTO
Commits: Conventional Commits (feat / fix / chore / docs / test / refactor)
Branching: short-lived feature branches off main; squash merge; no direct pushes to main
Test coverage: minimum 80% line coverage on backend business logic; every API endpoint has at
least one happy-path and one failure-path test
API design: REST, plural nouns, camelCase JSON keys, ISO-8601 UTC timestamps everywhere
Error responses: a consistent { "message": string, "code": string } shape on every 4xx and 5xx,
produced by a global exception filter — never a raw framework error
```

### NFRs
```
API Response Time (P95): < 300 ms
Dashboard Page Load (LCP): < 2.5 s
Accessibility: WCAG 2.2 Level AA on every screen, including the criteria new in 2.2 — focus not
obscured (2.4.11), dragging movements (2.5.7), target size (2.5.8) and redundant entry (3.3.7)
Availability: 99.5% during business hours (08:00-20:00 IST, Mon-Fri)
Audit: every leave approval and every change to an employee record is written to an immutable
audit log, retained for 7 years
Concurrency: up to 500 employees, up to 50 concurrent users
Data residency: all employee data stays within the company's own infrastructure
Session: idle timeout of 30 minutes; re-authentication required after that
```

### Constraints
```
Budget: Minimal — runs on the company's existing internal Kubernetes cluster, no new spend
Timeline: 2-3 weeks — a full SDLC demo cycle (ideation through deployment)
Access: internal-only. The application is not reachable from the public internet; it sits behind
the corporate VPN
Privacy: employee personal data must never leave company infrastructure. No third-party analytics,
no external error-reporting SaaS, no CDN-hosted fonts or scripts
Integration: none. There is no existing HRIS to integrate with in this phase
Localisation: English only. Dates displayed as DD-MMM-YYYY. Currency is INR where amounts appear
Leave year: runs 01 January to 31 December
```

### Glossary
```
Leave balance — the number of leave days an employee currently has available to apply for.
Casual Leave (CL) — short-notice personal leave. Accrues monthly.
Sick Leave (SL) — leave for illness. May require a medical certificate beyond a threshold.
Earned Leave (EL) — leave accrued through service, and the only type that can be carried over.
Loss of Pay (LOP) — an approved absence taken when the balance is exhausted; unpaid.
Comp-off — a compensatory day off granted for working on a holiday or weekend.
Carry-over — unused Earned Leave moved into the next leave year, subject to a cap.
Encashment — converting unused leave into a payment. OUT OF SCOPE for this application.
Probation — an initial employment period during which leave entitlement may differ.
Notice period — the period between resignation and the last working day.
Holiday calendar — the list of company holidays for a leave year. Varies by office location.
Reporting manager — the single employee who approves another employee's leave requests.
Direct report — an employee whose reporting manager is you.
```

### Important context
```
Platform & Layout Philosophy:
This is a web-first application. The primary experience is designed for desktop and laptop browsers
at 1280px and above. All screens must also work correctly on mobile browsers (375px minimum) — but
this is a responsive adaptation, not a mobile-first design. There is no native mobile app.

Repository topology:
A single repository. Backend and frontend live in one repo, as two pnpm workspace packages.

Sensitivity:
Employee records are personal data. Leave records reveal health information by implication (sick
leave patterns). Access control is not a nice-to-have — an employee must never be able to read
another employee's leave records, and a manager must only see their own direct reports.

Deliberate ambiguities left for the clarification loop:
The leave policy is NOT fully specified above. Accrual rate, carry-over cap, whether half-days are
supported, what happens to a pending request when the approving manager themselves goes on leave,
and whether an employee on probation may apply at all — none of these are stated. The agents are
expected to ask.

Out of scope, do not build:
Payroll, recruitment, performance reviews, timesheets, expense claims, benefits administration,
org-chart visualisation, employee self-service document vault, HRIS integration, mobile app.
```

### Repository & preview configuration

| Name | Role | Base branch |
|---|---|---|
| `acme/peopledesk` | frontend | `main` |

Set on the repository (S-13 Repositories), **not** in the profile. Without it the companion cannot
start the app, so 09b test-automation and every accessibility scan silently never run:

```json
{
  "command": "pnpm dev",
  "port": 5173,
  "health_path": "/",
  "ready_timeout_s": 120,
  "ready_log": "Local:"
}
```

> Role is `frontend` deliberately — preview config belongs to the repo that serves the UI, and this
> repo serves both packages.





---
---

# 2 · Returns Desk — Retail Returns & Exchange Counter

**Microservices · three repos · fully specified**

### Project name
```
Returns Desk
```

### Track
```
Greenfield
```

### Description
```
Returns Desk is the in-store counter application a retail staff member uses when a customer brings
an item back. Staff look up the original purchase by receipt number, select which lines are being
returned, record a reason and the item's condition, and the application decides the outcome against
the store's returns policy: accept automatically, refer to a manager, or refuse. Managers work a
separate override queue where they can approve an out-of-policy return with a recorded
justification. Once accepted, the application chooses a refund method — original payment method,
store credit, or a straight exchange — and records a refund instruction.

This is a back-office counter application. It is NOT an e-commerce site and it is NOT a point of
sale. It never creates orders; it only reads them. Original purchase data is supplied by a separate
Order Lookup service, which is part of this project and reads from a seeded order dataset.

The application does not process payments. It records a refund instruction with a reference and
marks it issued — handing off to a payment processor is out of scope.

Three roles exist: counter staff, store manager, and regional viewer (read-only reporting).
```

### Domain
```
Retail
```

### Tech stack
```
This project is deliberately split across three services. Each repository has its own stack.

--- retail/order-lookup-svc (role: service) ---
Language: Python 3.12
Framework: FastAPI
Database: PostgreSQL 16, read-only to this service
API: REST, documented as an OpenAPI 3.1 specification — this specification is the published
     contract that returns-api consumes
Testing: pytest + httpx

--- retail/returns-api (role: backend) ---
Language: Python 3.12
Framework: Django 5, Django REST Framework
Database: PostgreSQL 16 (its own database — services do not share a database)
Consumes: the order-lookup-svc OpenAPI contract over HTTP
Authentication: JWT access and refresh tokens; bcrypt password hashing
Testing: pytest + pytest-django

--- retail/returns-web (role: frontend) ---
Language: TypeScript 5
Framework: React 18, Vite
State Management: TanStack Query for server state; React Context for session
Styling: Plain CSS with CSS custom properties — no UI component library
Testing: Vitest + React Testing Library

--- shared ---
Inter-service communication: synchronous HTTP over the internal network. No message broker.
Contract: OpenAPI 3.1, published by order-lookup-svc, consumed by returns-api.
Cloud / Hosting: one container per service
```

### Coding standards
```
Style Guide (Python services): PEP 8 + Black formatter + isort + ruff
Style Guide (Frontend): ESLint with the Airbnb TypeScript config + Prettier
Type checking: mypy in strict mode (Python); TypeScript strict mode, no implicit any
Commits: Conventional Commits (feat / fix / chore / docs / test / refactor)
Branching: short-lived feature branches off main; squash merge; no direct pushes to main
Test coverage: minimum 80% line coverage on business logic in every repository

Contract discipline (this project's most important rule):
- order-lookup-svc owns its OpenAPI specification. It is the single source of truth for the
  interface.
- returns-api must NOT copy the specification into its own repository. It reads it.
- Any breaking change to the contract is a change to the published specification first, and the
  consumer is updated second.
- No service reads another service's database. Ever. All access is through the published API.

Money handling:
- All monetary amounts are stored as integer minor units (paise), never as floats.
- Rounding is half-up, applied once, at the point of display.

API design: REST, plural nouns, snake_case JSON keys, ISO-8601 UTC timestamps everywhere.
Error responses: a consistent { "detail": str, "code": str } shape on every 4xx and 5xx.
```

### NFRs
```
Order Lookup Response Time (P95): < 200 ms — a queue is forming at the counter while this runs
Returns API Response Time (P95): < 300 ms
Counter Screen Page Load (LCP): < 2.0 s
Accessibility: WCAG 2.2 Level AA on every screen, including the criteria new in 2.2 — focus not
obscured (2.4.11), dragging movements (2.5.7), target size (2.5.8) and redundant entry (3.3.7).
Counter staff work standing at a shared terminal and must be able to complete a return using the
keyboard alone
Availability: 99.9% during store trading hours
Degraded operation: if order-lookup-svc is unavailable, the counter application must say so
explicitly and remain usable for anything that does not need an order lookup. It must never show a
blank screen or a raw error
Idempotency: a refund instruction must never be issued twice for the same return, even if the
counter staff double-submits or the network retries
Audit: every policy decision, every manager override, and every refund instruction is written to an
immutable audit log with the acting user and a timestamp
Concurrency: up to 40 stores, up to 5 counter terminals per store
```

### Constraints
```
Budget: Minimal — free-tier or lowest-tier hosting per service
Timeline: 2-3 weeks — a full SDLC demo cycle (ideation through deployment)
Payments: no real payment processing. The application records a refund instruction with a reference
and marks it issued. It never contacts a payment gateway
Card data: never stored. The last four digits of the original tender may be displayed for staff to
match against the customer's card, and nothing more. PCI-DSS scope is therefore deliberately avoided
Order data: read-only and seeded. There is no order creation path anywhere in this project
Localisation: English only. Currency INR. Dates displayed as DD-MMM-YYYY
Hardware: no receipt printer, barcode scanner or cash drawer integration. Receipt numbers are typed
Offline: not supported. The counter terminal is assumed to have network connectivity
```

### Glossary
```
RMA — Return Merchandise Authorisation. The record created when a return is accepted.
Return window — the number of days after purchase within which an item may be returned.
Final sale — an item sold on terms that exclude it from return. Clearance stock is usually final sale.
Restocking fee — an amount deducted from a refund to cover the cost of returning stock to shelf.
Original tender — the payment method the customer originally paid with.
Store credit — a refund issued as credit for future purchase rather than money returned.
Exchange — swapping the returned item for another, with any price difference settled.
Partial refund — a refund of some but not all lines on an original order.
Manager override — acceptance of an out-of-policy return on a manager's recorded authority.
Condition — the state of the returned item: unopened, opened, used, or damaged.
Receipt number — the human-readable reference printed on the customer's original receipt.
Order line — one product and quantity within an original order. Returns operate on lines.
SKU — Stock Keeping Unit. The identifier for a specific product variant.
Gift purchase — an order with no payer identity available at the counter.
```

### Important context
```
Platform & Layout Philosophy:
This is a web-first application. The primary experience is designed for desktop and laptop browsers
at 1280px and above — counter terminals are desktop machines. All screens must also work correctly
on tablet browsers (768px minimum) for staff using handhelds on the shop floor. There is no native
mobile app.

Repository topology:
THREE repositories. This is a microservices project and the split is deliberate:
  retail/order-lookup-svc  (service)   — owns and publishes the order contract
  retail/returns-api       (backend)   — owns returns policy, decisions and refund instructions
  retail/returns-web       (frontend)  — the counter and manager screens

The interesting architectural question, which the Architecture phase is expected to decide and
defend at its gate: does returns-api call order-lookup-svc synchronously on every lookup, or does it
cache order data? What happens to the counter when order-lookup-svc is down mid-transaction?

Seed data — make it awkward on purpose:
The seeded order dataset must include cases that force the policy engine to branch, otherwise every
test path is "in policy, accept" and the Testing phase generates nothing interesting. Include at
minimum: an order 45 days old (outside a 30-day window); an order where the customer has no receipt,
only a card; an order already partially refunded; a gift purchase with no payer on file; a
clearance/final-sale item; and a mixed order with one returnable line and one final-sale line.

Deliberate ambiguities left for the clarification loop:
The returns policy is NOT fully specified above. The length of the return window, whether a receipt
is mandatory, how opened items are treated, whether a restocking fee applies and at what rate, which
refund method is chosen when the original tender is unavailable, and what authority level an
override needs — none of these are stated. The agents are expected to ask.

Out of scope, do not build:
Storefront, shopping cart, checkout, payment processing, inventory management, stock movements,
shipping, customer accounts, loyalty points, gift cards, warranty claims, supplier returns.
```

### Repositories
| Name | Role | Base branch |
|---|---|---|
| `retail/returns-web` | frontend | `main` |
| `retail/returns-api` | backend | `main` |
| `retail/order-lookup-svc` | service | `main` |

**Preview configuration — on `retail/returns-web` only.** The served thing is the UI; a backend or
service repo has no UI to preview. Without this the companion cannot start the app, so 09b
test-automation and every accessibility scan silently never run:

```json
{
  "command": "npm run dev",
  "port": 5173,
  "health_path": "/",
  "ready_timeout_s": 120,
  "ready_log": "Local:"
}
```

> The counter screens call `returns-api`, which calls `order-lookup-svc`, so all three services must
> be up for the preview to be usable. How that is orchestrated locally is a genuine question for the
> Architecture gate — and if the scan runs against a UI whose backend is down, expect findings about
> error states rather than about the screens you meant to test.

> Register all three **before** the first phase run. Topology is derived from the repo count
> (0-1 `single` · 2 `split` · 3+ `multi`), so three repos gives you `multi` — the mode that
> enables the repo-assignment review at the Task Breakdown gate and the cross-repo API contract.

### Epics
| # | Epic | Why |
|---|---|---|
| 1 | `Return at the Counter` | Primary, UI-bearing, and it **spans all three repos** — which is the point. Task Breakdown must assign tasks across them and a reviewer must confirm at the gate. |
| 2 | `Order Lookup Contract v2` | Secondary. Changes the published contract, which should open a **cross-repo drift gate** on the consumer. Also the epic to use for the gate rejection and re-trigger path. |

---
---

# 3 · FleetCare — Preventive Maintenance Scheduler

**Underspecified on purpose · single repo · the agent chooses the stack**

### Project name
```
FleetCare
```

### Track
```
Greenfield
```

### Description
```
FleetCare tells a fleet operator which vehicles are due for servicing and turns that into work.
Each vehicle has one or more maintenance schedules — an oil change every 6 months or every 10,000
km, whichever comes first. Odometer readings are entered by staff or loaded from a seeded reading
set. The application continuously determines which vehicles are approaching due, due, or overdue,
and presents a due board to the maintenance planner.

From the due board the planner raises a work order against a vehicle, assigns it to a garage, and
tracks it through to completion. Completing a work order resets the relevant schedule's clock. A
vehicle that goes past its overdue grace window is flagged Vehicle Off Road and must not be
dispatched.

The application is deliberately narrow: schedules, due calculation, work orders and the off-road
flag. It does NOT cover trip dispatch, driver management, fuel cards, telematics ingestion, parts
inventory, or garage invoicing. Odometer readings arrive by manual entry or seeded data — there is
no integration with any telematics provider.

Three roles exist: maintenance planner, garage technician, and fleet manager (read-only oversight).
```

### Domain
```
Fleet Management
```

### Tech stack
```
TBD — to be determined by the  Agent.

No stack is prescribed for this project. The agent should select the language, framework, database,
frontend approach and hosting, and justify the choice against the NFRs and Constraints below at the
Architecture gate.

The shape of the problem, to inform the choice — not to constrain it:
- A web application with an authenticated multi-role UI
- Relational, strongly consistent data: vehicles, schedules, readings, work orders
- A recurring evaluation that recomputes due status as time passes and readings arrive
- Modest scale, small team, minimal budget
```

### Coding standards
```
TBD — to be determined by the Agent.

No standards are prescribed. Once the stack is chosen, the agent should propose the formatter,
linter, type-checking approach, commit convention, branching model and test-coverage expectation
that suit it, and record them so later phases can be held to them.
```

### NFRs
```
API Response Time (P95): < 400 ms
Due Board Page Load (LCP): < 2.5 s
Accessibility: WCAG 2.2 Level AA on every screen, including the criteria new in 2.2 — focus not
obscured (2.4.11), dragging movements (2.5.7), target size (2.5.8) and redundant entry (3.3.7)
Availability: 99.5%
Correctness: the due calculation is the heart of this application. A vehicle must never be shown as
compliant when it is overdue on either the date rule or the odometer rule
Freshness: due status must reflect an odometer reading within 5 minutes of it being entered
Audit: every work order completion and every off-road flag change is written to an immutable audit
log with the acting user and a timestamp
Scale: up to 2,000 vehicles, up to 8,000 schedules, up to 50 concurrent users
Data retention: maintenance history is retained for the life of the vehicle plus 3 years
```

### Constraints
```
Budget: Minimal — free-tier hosting preferred
Timeline: 2-3 weeks — a full SDLC demo cycle (ideation through deployment)
Team: two developers, neither with deep operations experience. Anything chosen must be operable by
a small team without a dedicated platform engineer
Integration: none. No telematics provider, no ERP, no garage management system. Odometer readings
arrive by manual entry or seeded data
Deployment: a single deployable unit is acceptable and preferred. This project does not need to be
split into services
Localisation: English only. Distances in kilometres. Dates displayed as DD-MMM-YYYY
Offline: not supported
```

### Glossary
```
Preventive Maintenance (PM) — servicing performed on a schedule to prevent failure, as opposed to
  repairing after a breakdown.
PM schedule — a rule attaching a service type to a vehicle with an interval.
Interval — how often a service falls due. May be by time, by distance, or both.
Whichever comes first — the rule that a schedule is due as soon as EITHER its time interval OR its
  distance interval is reached, not both.
Due — a schedule has reached its interval and the service should be performed.
Approaching due — within a warning threshold before due.
Overdue — past due and not yet completed.
Grace window — the tolerance allowed past due before a vehicle is taken off road.
Vehicle Off Road (VOR) — a vehicle flagged as unavailable for dispatch.
Work order — the record of a service to be performed: vehicle, service type, garage, status.
Odometer reading — a recorded distance for a vehicle at a point in time. Readings only increase.
Service type — the category of work, e.g. oil change, brake inspection, tyre rotation.
Garage — the workshop a work order is assigned to. May be in-house or external.
Reset — completing a work order restarts its schedule's interval from the completion point.
```

### Important context
```
Platform & Layout Philosophy:
This is a web-first application. The primary experience is designed for desktop and laptop browsers
at 1280px and above — the maintenance planner works at a desk. All screens must also work correctly
on mobile browsers (375px minimum), because garage technicians update work orders on a phone. This
is a responsive adaptation, not a mobile-first design. There is no native mobile app.

Repository topology:
A single repository.

Why the stack is blank:
This is deliberate, not an oversight. The Architecture phase is expected to CHOOSE a stack and
defend it at its gate against the NFRs and Constraints above. Do not treat the blank field as a
question to ask back through the clarification loop — treat it as the decision this phase exists to
make. Every later phase should then be consistent with whatever was chosen and approved.

Seed data — make it awkward on purpose:
Seed vehicles and odometer readings that force the due calculation to branch. Include at minimum: a
vehicle due on date but not on distance; one due on distance but not on date; one overdue on both;
one inside the grace window; one past the grace window and therefore off road; a vehicle with no
readings at all since registration; a vehicle whose readings arrived out of order; and a schedule
that was completed early, so its next due date is not a simple multiple of the interval.

Deliberate ambiguities left for the clarification loop:
The maintenance policy is NOT fully specified above. The length of the grace window, how far before
due counts as approaching, whether completing a service early shifts the whole future schedule or
only the next occurrence, what happens when a reading is entered that is lower than the previous
one, and who may clear a Vehicle Off Road flag — none of these are stated. The agents are expected
to ask.

Out of scope, do not build:
Trip dispatch, route planning, driver management, driver licence and compliance tracking, fuel
cards, fuel reconciliation, telematics or GPS ingestion, parts inventory, garage invoicing,
accident and incident reporting, vehicle acquisition and disposal, mobile app.
```

### Repositories
| Name | Role | Base branch |
|---|---|---|
| `fleet/fleetcare` | frontend | `main` |

**Preview configuration.** Without it the companion cannot start the app, so 09b test-automation and
every accessibility scan silently never run. The `command` and `port` below are **placeholders** —
this project's stack is chosen by the Architecture Agent, so fill them in from whatever it decided
and approved at its gate, before the build tier starts:

```json
{
  "command": "<the run command for the approved stack>",
  "port": 3000,
  "health_path": "/",
  "ready_timeout_s": 120,
  "ready_log": "<a line the chosen server prints when ready>"
}
```

> This is itself a small test. A project profile that leaves the stack open cannot have a preview
> command written in advance — so watch whether the Architecture artifact says enough to fill this
> in. If it names a framework but never says how the thing is started or on what port, the decision
> was less complete than it looked.


---
---

## What to watch, per project

**PeopleDesk (baseline + stack obedience)** — two things at once.

First, does the whole lifecycle complete? Every artifact produced, every gate decided by the right
role, nothing published before its gate. If anything here fails, fix it before running the other two.

Second, and the reason this project is TypeScript: **watch for Python leaking in.** Read the
Architecture artifact, the Task Breakdown tasks and the generated code. Any of the following is a
defect, and a serious one — it means the Project Profile is not reaching the agents:

- Python, Django, DRF, FastAPI or Flask named anywhere
- `requirements.txt`, `pyproject.toml`, `manage.py`, `settings.py`, `models.py`
- pytest, mypy, ruff, Black or isort in the testing or tooling plan
- snake_case JSON keys in an API design (this profile specifies camelCase)
- a `{ "detail": ... }` error shape (this profile specifies `{ "message": ..., "code": ... }`)

That last pair is the sharpest tell. `snake_case` and `detail` are Django REST Framework's defaults
and they are what the platform's own codebase uses — so if they appear here, the agent is echoing
its own repository rather than reading the profile in front of it.

**Returns Desk (multi-repo)** — three things nothing else tests:
1. The **repo-assignment review** appears on the Task Breakdown gate, proposes a repo per task with
   a rationale, flags the uncertain ones first, and lets the reviewer override before approving.
2. A work item with **no repo assigned** must refuse to run with a clear message, not silently pick
   one.
3. Changing the published contract in epic 2 should open a **drift gate on the consumer repo**.

**FleetCare (underspecified)** — does the Architecture phase actually decide, or does it stall,
hedge, or bounce the question back as a clarification? And do the phases *after* Architecture stay
consistent with what it chose — or does Implementation quietly pick something else?

## Glossary is not decorative

All three profiles have a real glossary. The example profile in the current app has `NA`, which
means that field has never been exercised. Watch whether the terms actually reach the agents — if
the Requirements artifact talks about "time off" when the glossary says "Earned Leave", the profile
is not being composed into the manifest properly.
