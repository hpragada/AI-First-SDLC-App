"""Generate the AI-First SDLC Platform — Overview & Local Testing Guide (PDF).

Pure ReportLab (Platypus). Glyph-safe for the built-in Helvetica/Courier (WinAnsi):
em/en dashes and bullets are fine; arrows are written "->"; no emoji/checkmarks.
Run:  ../.venv/Scripts/python docs/build_platform_guide.py
Out:  docs/AI-First-SDLC-Platform-Guide.pdf
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

OUT = Path(__file__).resolve().parent / "AI-First-SDLC-Platform-Guide.pdf"

# ── palette ─────────────────────────────────────────────────────────
NAVY = colors.HexColor("#1e3a5f")
BLUE = colors.HexColor("#2563eb")
LIGHT = colors.HexColor("#eef2f7")
CODEBG = colors.HexColor("#f5f6f8")
NOTEBG = colors.HexColor("#fff8e6")
NOTEBORDER = colors.HexColor("#f59e0b")
OKBG = colors.HexColor("#eaf6ec")
OKBORDER = colors.HexColor("#3a9d54")
GREY = colors.HexColor("#475569")
RULE = colors.HexColor("#cbd5e1")

# ── styles ──────────────────────────────────────────────────────────
ss = getSampleStyleSheet()


def _style(name, **kw):
    kw.setdefault("parent", ss["Normal"])
    return ParagraphStyle(name, **kw)


BODY = _style("Body", fontName="Helvetica", fontSize=10, leading=15, spaceAfter=6,
              alignment=TA_LEFT, textColor=colors.HexColor("#1f2933"))
BODY_TIGHT = _style("BodyTight", parent=BODY, spaceAfter=2)
H1 = _style("H1", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY,
            spaceBefore=18, spaceAfter=8)
H2 = _style("H2", fontName="Helvetica-Bold", fontSize=13.5, leading=18, textColor=BLUE,
            spaceBefore=14, spaceAfter=5)
H3 = _style("H3", fontName="Helvetica-Bold", fontSize=11, leading=15,
            textColor=colors.HexColor("#0f172a"), spaceBefore=9, spaceAfter=3)
LEAD = _style("Lead", parent=BODY, fontSize=11, leading=16, textColor=GREY)
BULLET = _style("Bullet", parent=BODY, leftIndent=6, spaceAfter=3)
CELL = _style("Cell", parent=BODY, fontSize=8.8, leading=12, spaceAfter=0)
CELLB = _style("CellB", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
CODE = _style("Code", fontName="Courier", fontSize=8.4, leading=11.5,
              textColor=colors.HexColor("#0b2545"))
TOC_TITLE = _style("TocTitle", parent=H1, spaceAfter=12)

story: list = []


# ── helpers ─────────────────────────────────────────────────────────
def h1(text):
    story.append(Paragraph(text, H1))


def h2(text):
    story.append(Paragraph(text, H2))


def h3(text):
    story.append(Paragraph(text, H3))


def p(text, style=BODY):
    story.append(Paragraph(text, style))


def lead(text):
    story.append(Paragraph(text, LEAD))


def gap(h=6):
    story.append(Spacer(1, h))


def bullets(items, style=BULLET):
    flow = [ListItem(Paragraph(t, style), leftIndent=12, value="•") for t in items]
    story.append(ListFlowable(flow, bulletType="bullet", bulletFontName="Helvetica",
                              bulletFontSize=8, leftIndent=10, start="•"))
    gap(4)


def code(text):
    box = Table([[Preformatted(text.strip("\n"), CODE)]], colWidths=[16.4 * cm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODEBG),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(box)
    gap(6)


def callout(label, text, ok=False):
    bg, border = (OKBG, OKBORDER) if ok else (NOTEBG, NOTEBORDER)
    inner = [Paragraph(f"<b>{label}</b>", _style("nl", parent=BODY, spaceAfter=2,
                                                 textColor=NAVY if ok else colors.HexColor("#92400e"))),
             Paragraph(text, BODY_TIGHT)]
    box = Table([[inner]], colWidths=[16.4 * cm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, border),
        ("BOX", (0, 0), (-1, -1), 0.4, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(box)
    gap(8)


def table(rows, widths, header=True, font=8.8):
    data = []
    for ri, row in enumerate(rows):
        cells = []
        for c in row:
            st = CELLB if (header and ri == 0) else _style("c", parent=CELL, fontSize=font)
            cells.append(Paragraph(str(c), st))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    sty = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, LIGHT]),
    ]
    if header:
        sty += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
    t.setStyle(TableStyle(sty))
    story.append(t)
    gap(8)


# ════════════════════════════════════════════════════════════════════
# COVER
# ════════════════════════════════════════════════════════════════════
def cover():
    story.append(Spacer(1, 3.2 * cm))
    rule = Table([[""]], colWidths=[16.4 * cm], rowHeights=[3])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE)]))
    story.append(Paragraph("AI-FIRST SDLC PLATFORM",
                           _style("cover1", fontName="Helvetica-Bold", fontSize=30, leading=34,
                                  textColor=NAVY, alignment=TA_LEFT)))
    gap(6)
    story.append(rule)
    gap(14)
    story.append(Paragraph("Platform Overview, Phase-by-Phase Build, &amp; Local Execution Guide",
                           _style("cover2", fontName="Helvetica", fontSize=15, leading=20,
                                  textColor=GREY)))
    gap(28)
    story.append(Paragraph(
        "An engine-agnostic, multi-tenant, web-delivered agentic platform that runs the full "
        "software lifecycle&nbsp;&mdash; ideation through deployment&nbsp;&mdash; on a client's "
        "real tools of record, with a human review gate at every state change.",
        _style("coverlead", parent=BODY, fontSize=11.5, leading=17)))
    gap(40)
    meta = [
        ["Prepared for", "The Engineering Team — EdvenSoft"],
        ["Scope", "Phases 0–4 (complete &amp; tested); Phase 5 next"],
        ["Document", "Goal &amp; overview · phase build descriptions · what works today end-to-end · hands-on local testing guide · setup &amp; credentials"],
        ["Date", date.today().strftime("%B %d, %Y")],
        ["Source of truth", "/CLAUDE.md · /BUILD_PLAN.md · /docs/*"],
    ]
    t = Table([[Paragraph(k, _style("mk", parent=BODY, fontName="Helvetica-Bold",
                                    textColor=NAVY, fontSize=9.5)),
                Paragraph(v, _style("mv", parent=BODY, fontSize=9.5))] for k, v in meta],
              colWidths=[3.8 * cm, 12.6 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())


# ════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ════════════════════════════════════════════════════════════════════
def toc():
    story.append(Paragraph("Contents", TOC_TITLE))
    t = TableOfContents()
    t.levelStyles = [
        _style("toc1", fontName="Helvetica-Bold", fontSize=11, leading=20, textColor=NAVY),
        _style("toc2", fontName="Helvetica", fontSize=9.5, leading=15, leftIndent=14,
               textColor=GREY),
    ]
    story.append(t)
    story.append(PageBreak())


# ════════════════════════════════════════════════════════════════════
# CONTENT
# ════════════════════════════════════════════════════════════════════
def section_1():
    h1("1. What We Are Building — and What We Are Trying to Achieve")
    lead("The product is not “an AI that writes code.” It is a platform that runs your "
         "entire software lifecycle the way a disciplined engineering organisation does — with "
         "specialists, evidence, review gates, and an audit trail — but with AI agents doing the "
         "heavy lifting and humans staying in control of every decision that matters.")

    h2("1.1 The ultimate goal")
    p("We already had a powerful asset: a suite of <b>17 expert AI agents</b> (ideation, "
      "requirements, PRD, architecture, UX, task-breakdown, implementation, code review, "
      "testing, security, CI/CD, deployment, and more) plus the rules and gates that made them "
      "behave like senior engineers. The catch: that suite ran <i>locally</i>, glued to one "
      "developer's machine and Git checkout, with project context living in Markdown files.")
    p("The goal of this platform is to transform that suite into a <b>multi-tenant, "
      "web-delivered, engine-agnostic agentic SDLC platform</b> that:")
    bullets([
        "operates each client's <b>real tools of record</b> — Confluence, Jira, Figma, Xray, "
        "GitHub — bidirectionally, instead of inventing parallel copies;",
        "runs the <b>full lifecycle</b> (idea -> requirements -> PRD -> architecture -> UX -> "
        "build -> review -> test -> security -> CI/CD -> deploy) for both new (greenfield) and "
        "existing (brownfield) projects, single- or multi-repo;",
        "keeps a <b>human review gate</b> at every state change — nothing reaches a system of "
        "record without an approval;",
        "is <b>durable</b> (a run survives crashes, restarts, and an offline laptop) and "
        "<b>reproducible</b> (every run records the agent version, model, inputs, outputs, cost, "
        "and approver);",
        "treats the AI <b>engine as swappable</b> — Claude today, others later — without "
        "rewriting a single agent.",
    ])
    callout("In one sentence",
            "Take the intelligence of 17 senior-engineer AI agents, lift it off the laptop into "
            "a governed cloud-ready platform, point it at the client's real tools, and let teams "
            "ship software faster without giving up control, traceability, or quality.")

    h2("1.2 The seven non-negotiables (the rules the whole system obeys)")
    p("Every design decision serves these locked principles. They are worth internalising "
      "because they explain <i>why</i> the platform is shaped the way it is.")
    table([
        ["#", "Principle", "What it means in plain terms"],
        ["1", "State vs. content", "The platform owns <b>state</b> (pointers, provenance, "
         "events in Postgres). External tools own <b>content</b> (the actual Jira issue, "
         "Confluence page, Git PR). Local files are throwaway."],
        ["2", "Orchestration vs. execution", "The platform decides <i>what</i> happens and "
         "<i>when</i> (and runs the gates). The AI engine only <i>executes</i> a step. So engines "
         "stay interchangeable."],
        ["3", "Memory = index, not copies", "We store pointers + hashes + versions of artifacts, "
         "never copied bodies. This is what lets us detect drift and cross-check conflicts."],
        ["4", "Work is a graph", "The unit of work is a <b>WorkItem</b>; work is a per-item DAG, "
         "not a rigid linear pipeline — features can progress independently."],
        ["5", "Every artifact is gated", "draft -> reviewed -> gated -> published. No "
         "auto-publish, ever. Nothing reaches a system of record before an approval."],
        ["6", "Tenant isolation by RLS", "Every database table carries a tenant_id and a Postgres "
         "Row-Level-Security policy from its first migration. One client can never see another's "
         "rows."],
        ["7", "Capabilities, not vendors", "Business logic calls <tt>tasktracker.*</tt> / "
         "<tt>docstore.*</tt> / <tt>codehost.*</tt> — never <tt>jira.*</tt> directly — so a "
         "connector can be swapped by editing one row."],
    ], [0.8 * cm, 4.0 * cm, 11.6 * cm])
    p("Three more locked decisions round these out: the default engine is <b>Claude (Agent "
      "SDK)</b> behind an <tt>ExecutionDriver</tt> interface; durability is provided by "
      "<b>Temporal</b> from day one; and the agents are migrated by the <b>75 / 15 / 10</b> rule "
      "(reuse ~75% of an agent's reasoning verbatim, rewrite ~15% of its data references to the "
      "platform, replace ~10% of invocation glue).")

    h2("1.3 The architecture at a glance — seven planes")
    p("The platform is organised into seven cooperating layers. You will meet each of these in "
      "the phase descriptions and again in the testing guide.")
    table([
        ["Plane", "Responsibility", "Where it lives"],
        ["Experience", "What people see and click: project workspace, phase console, gate "
         "approvals, traceability viewer.", "React app (<tt>frontend/</tt>)"],
        ["Control", "The brain: Work-DAG state machine, Gate/Approval service, run scheduler, "
         "Manifest Composer, reconciliation, driver router.", "Django services "
         "(<tt>backend/</tt>)"],
        ["Execution", "Runs the agents: the ExecutionDriver interface + ClaudeDriver; planning "
         "runs server-side, build runs on a developer-machine companion.", "<tt>drivers/</tt>, "
         "<tt>runner/</tt>"],
        ["Integration", "Talks to the outside world through capability interfaces + connectors + "
         "the Platform-State MCP server + webhooks + a rate governor.", "<tt>backend/"
         "integrations/</tt>, <tt>mcp_platform_state/</tt>"],
        ["Memory / State", "Postgres (with pgvector) + an S3-compatible object store: project "
         "profile, artifact registry, traceability graph, work DAG, event ledger, run history.",
         "Postgres + MinIO"],
        ["Security &amp; Governance", "Tenant isolation (RLS), prompt-injection defences, "
         "secret scanning, egress control, audit. (Deepens in Phase 5.)", "across the stack"],
        ["Observability &amp; Quality", "Durable workflow visibility, run cost metering, and the "
         "test/quality plane. (Deepens in Phase 5.)", "Temporal + <tt>apps/quality/</tt>"],
    ], [3.0 * cm, 9.6 * cm, 3.8 * cm])

    h2("1.4 What “done” looks like at each milestone")
    p("The build proceeds phase by phase, each ending in a working <b>thin vertical slice</b> "
      "demonstrated end-to-end. The headline milestone:")
    callout("First usable product — after Phase 2",
            "A user can take a <b>greenfield</b> project from idea -> PRD -> architecture -> "
            "backlog in Jira -> an implemented GitHub PR, and can <b>onboard an existing "
            "single-repo</b> project (from local documents or live Atlassian). Phases 3–4 add "
            "design/test/security depth and brownfield-full/multi-repo; Phases 5–6 add enterprise "
            "hardening, the cloud runner fleet, and engine choice.", ok=True)


def section_2():
    story.append(Paragraph("", BODY))
    h1("2. The Build, Phase by Phase (Phases 0–4)")
    lead("Each phase below lists the concrete components that were built and explains what each "
         "one does in everyday language, and closes with a <b>capstone slice</b> — the thin "
         "end-to-end demo that proves the phase works. (For a real, straight-through test pass — "
         "greenfield and brownfield — see the two journeys in <b>Section 5</b>.) Phases 0 through "
         "4 are complete and tested.")

    # ---- Phase 0 ----
    h2("2.1 Phase 0 — The Platform Spine")
    p("<b>Goal:</b> move the source of truth off the filesystem and run the existing agents "
      "through a real platform with state, gates, and provenance — before adding any external "
      "tools. This phase builds the skeleton everything else hangs on.")
    table([
        ["Component", "What it is / does"],
        ["State plane (Postgres)", "The durable memory: Tenant, Project, <b>Project Profile</b> "
         "(the database record that replaces the old CLAUDE.md), Repository, <b>WorkItem</b> (the "
         "unit of work + its DAG), <b>Artifact Registry</b> (pointers + hashes + versions, never "
         "bodies), <b>Event Ledger</b> (append-only history), <b>Run History</b>, AgentSpec "
         "Registry."],
        ["Platform-State MCP server", "A small tool server the agents call to read/write platform "
         "state: <tt>get_context</tt>, <tt>register_artifact</tt>, <tt>log_event</tt>, "
         "<tt>add_trace_edge</tt>, <tt>list/transition_work_item</tt>, etc. Every call is "
         "tenant-scoped."],
        ["Manifest Composer", "Assembles a fresh, budget-bounded <tt>AGENTS.md</tt> per run from "
         "the Project Profile + relevant artifact pointers + recent events + rules. This is the "
         "context an agent reads — generated each run, never hand-maintained."],
        ["Temporal AgentRunWorkflow", "The durable orchestration of one agent run: compose "
         "context -> execute agent -> verify it wrote what it should -> open the gate -> wait for "
         "a human -> publish + advance. Survives restarts; retries are idempotent."],
        ["Gate / Approval service", "Gates are control-plane <tt>Approval</tt> objects, never "
         "engine hooks. A human with the right role decides; the decision signals the workflow "
         "to resume. (Phase 3 added WCAG checklist conditions to this.)"],
        ["ExecutionDriver + ClaudeDriver", "The seam that makes the engine swappable. Business "
         "logic calls the interface; the ClaudeDriver runs the Claude Agent SDK underneath."],
        ["Tenant isolation (RLS)", "A non-superuser database role the app connects as, plus a "
         "Row-Level-Security policy on every table. Unset tenant context fails closed (sees no "
         "rows)."],
        ["React Experience plane", "The web UI: create a project, edit its profile, a Phase "
         "Console to trigger phases and watch the run timeline, a gate-approval screen, an "
         "artifact view, and a traceability view."],
        ["Migrated agents 01–04", "Ideation, Requirements, PRD, Architecture — the first agents "
         "migrated by the 75/15/10 rule, plus the rules and per-agent triggers that replace the "
         "old slash commands."],
    ], [4.4 * cm, 12.0 * cm])
    callout("Phase 0 — capstone slice (what this phase proves)",
            "Run ideation -> requirements -> PRD -> architecture fully on platform state; "
            "artifacts registered as drafts in object storage; every step gated by a human; runs "
            "attributed; the manifest rendered per run. (This is exactly what you will click "
            "through in the testing guide, Section 3.)", ok=True)

    # ---- Phase 1 ----
    h2("2.2 Phase 1 — First System of Record (Atlassian)")
    p("<b>Goal:</b> make the platform operate a client's real Confluence and Jira, "
      "bidirectionally, with progress tracking and traceability — and let existing projects be "
      "onboarded.")
    table([
        ["Component", "What it is / does"],
        ["DocStore connector (Confluence)", "Creates/updates Confluence pages (versioned, "
         "read-through). The platform publishes a PRD page only after its gate is approved."],
        ["TaskTracker connector (Jira)", "Creates epics/stories/subtasks, transitions issues, "
         "comments, searches — headless via API token."],
        ["Capability abstraction", "<tt>docstore.*</tt> and <tt>tasktracker.*</tt> interfaces + a "
         "per-tenant <tt>get_capability()</tt> selector. Callers never name Jira or Confluence "
         "directly (non-negotiable #7)."],
        ["Artifact publish path", "The gate -> publish -> pointer+version lifecycle to the live "
         "SoR; idempotent; falls back to “internal” when no connector is configured."],
        ["Traceability graph + viewer", "requirement -> PRD -> epic -> story lineage, with "
         "deep-links into the live Confluence/Jira items."],
        ["Reconciliation service", "Turns proposed work into accepted SoR issues without ever "
         "duplicating something that already exists (register-don't-recreate)."],
        ["Brownfield-lite onboarding", "Adopt an existing project: register what is already in "
         "Atlassian, and extract structured artifacts from static <b>Word/PDF/Excel</b> "
         "documents (with provenance + a review gate)."],
        ["Rate governor", "A per-(tenant, capability) token bucket + backoff + short-lived read "
         "cache, so live API calls stay within limits and don't flake."],
        ["Migrated agent 06", "Task Breakdown — decomposes the PRD/architecture into a "
         "vertically-sliced backlog that reconciliation pushes into Jira on approval."],
    ], [4.4 * cm, 12.0 * cm])

    # ---- Phase 2 ----
    h2("2.3 Phase 2 — Build Execution (real code, real PRs, durably)")
    p("<b>Goal:</b> produce real code — implementation, review, test — as GitHub pull requests, "
      "durably, <i>without changing how a developer works day to day</i>.")
    table([
        ["Component", "What it is / does"],
        ["CodeHost connector (GitHub)", "Owns the PR / branch / status / comment / merge surface "
         "via the GitHub REST API. The engine never calls Git directly; the platform does, behind "
         "the <tt>codehost.*</tt> capability."],
        ["Local-companion runner", "A small daemon a developer runs on <b>their own machine</b>. "
         "It enrolls with the platform, pulls a build task, and works in a clean, "
         "platform-managed <b>git worktree</b> (a <tt>feature/&lt;key&gt;</tt> branch) so the "
         "developer can run and test the change locally before any PR. Their main checkout is "
         "never touched."],
        ["Remote Platform-State serving", "The companion uses the state tools over an "
         "authenticated remote transport — the dev machine needs no database credentials; tenant "
         "binding and RLS stay server-side."],
        ["<tt>run_build_task</tt>", "The build-mode driver call: launches the agent in the "
         "worktree with file + shell tools, under a per-phase tool allowlist (no CodeHost, no "
         "arbitrary network)."],
        ["Temporal BuildWorkflow (saga)", "Durable build orchestration: dispatch to the companion "
         "-> await its report (or park for human takeover if the laptop is offline) -> open a "
         "draft PR -> review -> remediation loop -> reviewer merge gate -> merge. Idempotent; "
         "compensating on failure."],
        ["07 &lt;-&gt; 08 remediation loop", "Implementation (07) and Code Review (08) cooperate: "
         "each blocking finding becomes a child WorkItem; 07 re-runs in remediation mode until 08 "
         "is clean — then the merge gate can be granted."],
        ["Injection guardrails v1", "Secret-scan before push (blocks credentials reaching "
         "GitHub), an egress allowlist (only approved hosts), and the per-phase tool allowlist."],
        ["Human takeover + webhook reconcile", "A developer can take a WorkItem over and just "
         "work by hand; a signed GitHub webhook reconciles their commits/PR/CI status back into "
         "the registry (register-don't-recreate)."],
        ["Light multi-repo", "One project can target several repositories (one repo per "
         "WorkItem); each builds on its own branch/PR independently."],
        ["Migrated agents 07, 08, 11, 12", "Implementation, Code Review, CI/CD, Deployment — with "
         "their reasoning (Clean Code/TDD, the eleven review dimensions, the Jenkins/Actions "
         "templates, blue-green/canary releases) preserved verbatim."],
    ], [4.4 * cm, 12.0 * cm])
    callout("Phase 2 — capstone slice (the stop-and-dogfood MVP)",
            "WorkItem -> companion worktree -> local build/test -> PR -> CI status -> review -> "
            "remediation -> reviewer merge gate -> merge, with a forced mid-run failure recovered "
            "idempotently, a human commit reconciled via webhook, and two repos in one project "
            "building independently.", ok=True)

    # ---- Phase 3 ----
    h2("2.4 Phase 3 — Design &amp; Test Loops")
    p("<b>Goal:</b> close the UX and QA loops — read a client's live design, push tests and "
      "results to Xray, and turn a failing test into a tracked, linked bug.")
    table([
        ["Component", "What it is / does"],
        ["DesignSource connector (Figma)", "<b>Read-as-SoR</b>: the platform reads the client's "
         "<i>current</i> Figma design at run time (frames, design tokens, components) rather than "
         "regenerating it. Canvas write-back is a deferred seam."],
        ["Design-System / tokens + Code Connect", "Aggregates the current design into a "
         "<tt>design_system</tt> artifact (tokens) and a <tt>code_connect</tt> mapping that links "
         "design components to code components."],
        ["a11y (WCAG) gate", "The accessibility review is enforced as a <b>checklist of WCAG 2.1 "
         "AA conditions on the design Approval</b> — an approve is blocked until every required "
         "criterion is satisfied. It is a control-plane gate, not a prompt rule."],
        ["Per-tenant theming", "Design tokens + responsive breakpoints stored on the Project "
         "Profile flow verbatim into the manifest — one theme, no per-tenant code fork."],
        ["TestMgmt connector (Xray)", "Authors test cases as Xray tests and imports execution "
         "results (idempotently). Headless, per-tenant, rate-governed."],
        ["Result import + defect loopback", "A test run records a <tt>TestExecution</tt> + a "
         "<tt>test_report</tt> artifact; a <b>failing test opens a linked, traced defect</b> "
         "(a child WorkItem tied to the test and traced to the code); a later pass closes it."],
        ["Test-impact selection", "Given a changed piece of code, walks the traceability graph to "
         "select just the tests that cover it."],
        ["Flaky quarantine", "A test that flips pass/fail within one run is quarantined and "
         "excluded from the blocking gate (never silently blocks a merge, never silently passes)."],
        ["Ephemeral preview env per PR", "A companion-local seam: the app is brought up from the "
         "worktree, the URL is posted on the PR, and torn down on close. (Cloud preview is a "
         "Phase-5 drop-in behind the same seam.)"],
        ["Migrated agents 05, 09, 09b, 10", "UX Design (read-as-SoR + HTML wireframes), Testing, "
         "Test Automation (Playwright-MCP locator discovery + Page Object Model preserved), and "
         "Security (the nine review tracks + SBOM, with criticals opening defects)."],
    ], [4.4 * cm, 12.0 * cm])
    callout("Phase 3 — capstone slice (what this phase proves)",
            "Design produced and gated through the WCAG checklist -> implementation reads the "
            "current design -> tests author to Xray and results import -> a failing test opens a "
            "traced defect that closes on a clean re-run -> a standalone security review -> a "
            "companion-local preview env. Verified end-to-end, with the full platform suite green "
            "across all phases.", ok=True)

    # ---- Phase 4 ----
    h2("2.5 Phase 4 — Brownfield-Full &amp; Multi-Repo")
    p("<b>Goal:</b> the client front door. Onboard an <i>existing</i> project — any number of "
      "repositories — understand its code, <b>resume the lifecycle from the middle</b> instead "
      "of starting over, and keep cross-repo API contracts honest with <b>live drift "
      "detection</b>. This is the entry point most real clients will use.")
    table([
        ["Component", "What it is / does"],
        ["CodeIntel capability + built-in analyzer", "A fixed 8-tool <tt>codeintel.*</tt> surface "
         "with a <b>built-in SOTA analyzer</b> (no license needed): git/Tornhill <b>hotspots</b> "
         "(churn × complexity), a dependency graph with <b>PageRank</b> + communities, dead-code "
         "and complexity, and decision archaeology. It runs in the <b>companion worktree</b> on a "
         "real clone; the platform stores only the index + artifacts, <b>never the source</b>. "
         "Repowise (or another engine) plugs in behind the same seam."],
        ["Knowledge Index", "An RLS-aware chunk store with an always-on, <b>zero-cost keyword "
         "(BM25) baseline</b> plus an optional embedding seam (Voyage / Gemini). It feeds the "
         "manifest's retrieved-knowledge section and is <b>project-wide shared memory</b> across "
         "all of a project's repos."],
        ["Agent 00c — Intelligent Context Extractor", "Migrated: turns a raw codebase into five "
         "intelligence layers (dependency graph, git analytics, dead code, decisions, health) "
         "registered as platform artifacts + indexed into the Knowledge Index. <tt>tech_lead</tt> "
         "gate."],
        ["Agent 00 — Onboarding (full)", "The brownfield front door: <b>discover</b> across the "
         "connected systems of record + code-intel, <b>register</b> what already exists "
         "(register-don't-recreate), <b>reconcile</b>, detect the <b>gaps</b>, and emit a "
         "<b>gap report</b> that assesses every lifecycle phase Complete/Partial/Missing and "
         "names the correct <b>resume phase</b>. <tt>product_owner</tt> gate."],
        ["Agent 00b -> API-Contract artifact", "Cross-repo contracts as a <b>versioned "
         "<tt>api_contract</tt> registry artifact</b> (read-through, never a copied file): the "
         "provider repo exports it (semver-bumped); consumer repos read the current version at "
         "run time and record an <tt>implements</tt> edge. <tt>architect</tt> gate. (Agent 00d "
         "Snapshot is retired — continuity is now the database + durable runs.)"],
        ["Multi-repo project model + per-repo manifest", "One project owns <b>N repositories</b> "
         "(frontend/backend/service); topology reconciles to single/split/multi. The composed "
         "manifest is <b>scoped per repo</b> (that repo's artifacts + project-shared ones + the "
         "shared contract), while the registry, traceability, and Knowledge Index stay "
         "<b>project-wide shared memory</b>."],
        ["Cross-repo DAG edges", "Dependencies that span repositories: <tt>implements</tt> "
         "traceability edges across repos + <tt>WorkItem.depends_on</tt> — the basis for "
         "cross-repo change-impact."],
        ["Live drift detection + drift gate", "Two detectors: <b>contract drift</b> (an "
         "<tt>api_contract</tt> diverges from its consumers) and <b>pointer/hash drift</b> (a SoR "
         "artifact's external content changed since we indexed it). On detection the platform "
         "writes a <b>DriftRecord</b>, computes <b>change-impact via the traceability graph</b> "
         "(every downstream consumer/repo), and opens a <tt>decide_drift</tt> gate — "
         "<tt>architect</tt> for contract, <tt>tech_lead</tt> for pointer/hash. <b>Accept</b> "
         "re-indexes; <b>reject</b> flags for revert; nothing is silently written to a system of "
         "record. The signed Git push webhook is the live trigger (built on the Phase-2 "
         "reconcile)."],
    ], [4.4 * cm, 12.0 * cm])
    callout("Phase 4 — capstone slice (what this phase proves)",
            "Onboard a <b>split FE/BE</b> project -> register-don't-recreate + the built-in "
            "code-intel running for real in a companion worktree -> a <b>gap report</b> with a "
            "resume phase -> the backend exports an <tt>api_contract</tt>, the frontend reads it "
            "read-through and records a cross-repo <tt>implements</tt> edge -> <b>resume "
            "mid-pipeline</b> triggers the next phase to its gate -> a <b>contract change opens a "
            "drift gate</b> whose change-impact <b>spans both repos</b>, decided by the architect. "
            "Verified end-to-end; the full platform suite is green across all phases.", ok=True)


def section_3():
    h1("3. The Local Execution &amp; Testing Guide")
    lead("This is a hands-on guide for a developer to run the platform locally and <i>see</i> "
         "every workflow work — in the browser, the API, the Temporal dashboard, and the object "
         "store. It is not about unit tests. Follow Part A to get the core running with zero "
         "external accounts; Part C adds the optional live connectors.")
    callout("Before you start",
            "Complete the prerequisites and credentials in <b>Section 4</b> first (Docker "
            "Desktop running, <tt>.env</tt> created, and — for live AI runs — an "
            "<tt>ANTHROPIC_API_KEY</tt>). On Windows without <tt>make</tt>, use the shim "
            "<tt>./make.ps1 &lt;target&gt;</tt> in place of <tt>make &lt;target&gt;</tt>.")

    h2("3.1 Part A — Bring up the platform (no external accounts needed)")
    h3("Step 1 — Start the infrastructure")
    code("# from the repo root\ndocker compose up -d        # postgres (:5433), temporal "
         "(:7233 + UI :8080), minio (:9000 + console :9001)\ndocker compose ps              "
         "# all services should be 'running' / healthy")
    p("<b>What you should see:</b> open the <b>Temporal UI</b> at "
      "<tt>http://localhost:8080</tt> (empty workflow list for now) and the <b>MinIO console</b> "
      "at <tt>http://localhost:9001</tt> (login <tt>minioadmin</tt> / <tt>minioadmin</tt>; the "
      "<tt>sdlc-artifacts</tt> bucket already exists).")

    h3("Step 2 — Migrate the database and seed the demo tenant")
    code("make migrate     # creates every table + its RLS policy (runs as the DB owner)\n"
         "make seed        # seeds a demo tenant, project, profile, agent specs, connectors")
    p("<b>What you should see:</b> <tt>seed</tt> prints the created tenant/project ids and a "
      "connector count. (If <tt>make migrate</tt> reports an ownership error on an ALTER, run it "
      "as the <tt>postgres</tt> superuser — see Section 4.4.)")

    h3("Step 3 — Run the application (API + worker + frontend)")
    code("make dev         # = docker compose --profile app up\n"
         "#   backend API  -> http://localhost:8000\n"
         "#   React UI     -> http://localhost:5173\n"
         "#   worker       -> connects to Temporal (durable runs execute here)")
    p("<b>What you should see:</b> the React app loads at <tt>http://localhost:5173</tt>; the "
      "worker logs “started” and registers with Temporal. A quick API smoke check:")
    code("curl http://localhost:8000/api/projects/ -H \"X-Tenant-ID: <demo-tenant-id>\"\n"
         "# -> JSON list including the seeded demo project")

    h2("3.2 Part B — Drive the planning slice in the browser (Phase 0 end-to-end)")
    p("This is the core, no-external-accounts workflow. Open <tt>http://localhost:5173</tt> and "
      "work left to right through the five tabs.")
    callout("Cost note",
            "Triggering a phase runs the <b>real Claude agent</b> via the ClaudeDriver, so it "
            "needs a valid <tt>ANTHROPIC_API_KEY</tt> in <tt>.env</tt> and incurs a small API "
            "cost per run. To keep cost minimal, trigger a single phase (Ideation) first; that is "
            "enough to see the whole gate -> publish -> traceability loop.")
    table([
        ["Tab / action", "What to do", "What you should see (the proof)"],
        ["Tenant + Project bar", "Create or select a tenant, then a project (the seeded demo is "
         "fine).", "The five tabs unlock."],
        ["1. Project Profile", "Fill description, tech stack, important context; Save.", "A new "
         "profile version is saved; it becomes the agent's context next run."],
        ["2. Phase Console", "Add a WorkItem (a feature stream), then click <b>Ideation</b>.",
         "A Run appears in the Run Timeline and moves <tt>running -> awaiting_gate</tt> as you "
         "poll. In the Temporal UI (:8080) a new <tt>AgentRunWorkflow</tt> is visible and "
         "<i>waiting</i> at the gate."],
        ["3. Gate Approvals", "Find the pending approval; approve it as a user holding the "
         "required role.", "The run resumes to <tt>completed</tt>; the workflow finishes in the "
         "Temporal UI."],
        ["4. Artifacts", "Look at the ideation artifact.", "Its status flips <tt>draft -> "
         "published</tt>; its body is stored in MinIO (visible in the :9001 console under "
         "<tt>drafts/</tt> and <tt>snapshots/</tt>)."],
        ["5. Traceability", "Open the lineage view.", "A graph of artifacts and their "
         "<tt>derives/tests/...</tt> edges; once external SoRs are connected, nodes deep-link to "
         "the live Confluence/Jira items."],
    ], [3.4 * cm, 5.6 * cm, 7.4 * cm])
    p("Repeat the trigger for <b>Requirements -> PRD -> Architecture</b> to walk the full "
      "planning chain. Each run reads the artifacts the previous phase published (proving the "
      "platform — not a local file — is the source of truth), and each is independently gated.")

    h2("3.3 Part C — Optional: exercise the live connectors")
    p("These steps need real (test) cloud accounts. Each is independent — do only the ones you "
      "have credentials for. Set the relevant variables in <tt>.env</tt> (Section 4) and "
      "<tt>make seed</tt> again so the demo tenant gets the connector, then restart "
      "<tt>make dev</tt>.")

    h3("Atlassian — Confluence + Jira (Phase 1)")
    bullets([
        "Set <tt>ATLASSIAN_*</tt>, <tt>CONFLUENCE_SPACE_KEY</tt>, <tt>JIRA_PROJECT_KEY</tt>.",
        "<b>Greenfield:</b> approve the PRD gate -> the PRD <b>publishes as a Confluence page</b>; "
        "approve the backlog -> epics/stories <b>appear in Jira</b>. The Traceability tab now "
        "deep-links to those live items.",
        "<b>Brownfield:</b> POST a Word/Excel document to <tt>/api/source-documents/</tt> -> it "
        "is extracted into reviewable internal artifacts (gated before adoption); existing Jira "
        "issues are registered without duplicates.",
    ])

    h3("GitHub — the build path (Phase 2)")
    p("Set <tt>GITHUB_API_URL</tt>, <tt>GITHUB_TOKEN</tt> (a PAT with repo scope), "
      "<tt>GITHUB_REPO</tt> (“owner/name”), <tt>GITHUB_DEFAULT_BASE</tt>, "
      "<tt>GITHUB_WEBHOOK_SECRET</tt>. Then enroll a companion on your machine and run a build:")
    code("# 1) enroll this machine as a runner (prints a one-time token)\n"
         "python -m runner.companion enroll --api-url http://localhost:8000 \\\n"
         "    --tenant <tenant-id> --project <project-id> --label my-laptop --repos owner/name\n\n"
         "# 2) run an assigned build task in a managed worktree\n"
         "python -m runner.companion run --task task.json \\\n"
         "    --repo-path ~/repos/your-clone --worktrees ~/sdlc")
    p("<b>What you should see:</b> a <tt>feature/&lt;key&gt;</tt> branch is created in a "
      "worktree, tests run locally, a <b>draft PR opens on GitHub</b>, code review runs, and the "
      "Temporal UI shows the <tt>BuildWorkflow</tt> parked at the <b>reviewer merge gate</b>. "
      "Approve it (Gate Approvals) and the PR <b>merges</b>. Push a manual commit to the branch "
      "and the signed webhook reconciles it (the artifact's sha pointer moves; no duplicate).")

    h3("Figma + Xray (Phase 3)")
    bullets([
        "<b>Figma:</b> set <tt>FIGMA_TOKEN</tt> + <tt>FIGMA_FILE_KEY</tt> (a personal-access "
        "token + a test file). The design phase reads the <i>current</i> design tokens/components "
        "from that file (read-as-SoR) instead of inventing them.",
        "<b>Xray:</b> set <tt>XRAY_CLIENT_ID</tt> + <tt>XRAY_CLIENT_SECRET</tt> + "
        "<tt>XRAY_PROJECT_KEY</tt>. The test phase authors tests into Xray and imports results; "
        "a failing import opens a defect WorkItem linked to the test and traced to the code, "
        "which closes automatically on a clean re-run.",
    ])

    h2("3.4 Part D — See the cross-cutting guarantees with your own eyes")
    table([
        ["Guarantee", "How to observe it"],
        ["Durability", "In the Temporal UI (:8080), open a running workflow — it shows each "
         "activity, retries, and the gate wait. Restart the <tt>worker</tt> container mid-run; "
         "the workflow resumes where it left off."],
        ["Gate-then-publish", "On the Artifacts tab, an artifact stays <tt>draft</tt> until you "
         "approve its gate — then it becomes <tt>published</tt>. There is no way to publish "
         "without an approval."],
        ["Tenant isolation (RLS)", "Create a second tenant and call the API with its "
         "<tt>X-Tenant-ID</tt>: it sees none of the first tenant's projects, runs, artifacts, or "
         "defects."],
        ["Provenance / cost", "The Run Timeline shows each run's engine, model, cost (USD), and "
         "Temporal workflow id; the Event ledger records who approved what and when."],
        ["Artifact bodies in S3", "The MinIO console (:9001) shows artifact draft bodies and "
         "immutable post-approval snapshots — the registry holds only pointers + hashes."],
    ], [4.0 * cm, 12.4 * cm])
    callout("“Everything works” checklist",
            "(1) infra healthy; (2) migrate + seed succeed; (3) UI loads and the five tabs work; "
            "(4) a planning phase runs to <tt>completed</tt> through its gate and publishes an "
            "artifact; (5) traceability shows the lineage; (6) the Temporal UI shows the durable "
            "workflow; (7) MinIO shows the artifact body; (8) optional: a live PRD reaches "
            "Confluence, a backlog reaches Jira, a build reaches a GitHub PR, and a failing test "
            "opens a linked defect.", ok=True)


def section_4():
    h1("4. Setup, Credentials &amp; Prerequisites")
    lead("Everything a developer must install, configure, or obtain before running Section 3. "
         "Copy <tt>.env.example</tt> to <tt>.env</tt> and fill the values below.")

    h2("4.1 Prerequisites to install")
    table([
        ["Tool", "Why", "Notes"],
        ["Docker Desktop", "Runs the whole stack (Postgres, Temporal, MinIO, API, worker, "
         "frontend).", "Must be <b>running</b> before <tt>docker compose up</tt>. Windows: WSL2 "
         "backend recommended."],
        ["Python 3.12 + a repo-root <tt>.venv</tt>", "Local tooling: fast pytest/ruff, the "
         "companion runner CLI.", "<tt>python -m venv .venv</tt> then install "
         "<tt>backend/requirements-dev.txt</tt>. Tooling only — the app runs in Docker."],
        ["Git", "Version control + the companion's managed worktrees.", "Any recent version."],
        ["make (optional)", "Convenience targets.", "Windows without make: use "
         "<tt>./make.ps1 &lt;target&gt;</tt>."],
    ], [4.2 * cm, 6.2 * cm, 6.0 * cm])

    h2("4.2 Environment variables (<tt>.env</tt>)")
    h3("Required for the core local run")
    table([
        ["Variable", "Purpose", "Default / value"],
        ["DJANGO_SECRET_KEY", "Django signing key (dev).", "any dev string"],
        ["POSTGRES_* / DATABASE_URL", "App database + the non-superuser RLS role.", "preset in "
         "<tt>.env.example</tt> (app uses <tt>sdlc_app</tt>; host port 5433)"],
        ["TEMPORAL_HOST / NAMESPACE / TASK_QUEUE", "Durable workflow engine.", "<tt>temporal:7233"
         "</tt> / <tt>default</tt> / <tt>sdlc-planning</tt>"],
        ["CORS_ALLOWED_ORIGINS", "Lets the React app call the API.", "<tt>http://localhost:5173"
         "</tt>"],
        ["S3_* (MinIO)", "Object store for artifact bodies + snapshots.", "<tt>minioadmin</tt> / "
         "<tt>minioadmin</tt>, bucket <tt>sdlc-artifacts</tt>"],
        ["ANTHROPIC_API_KEY", "<b>Required to actually run agents</b> (the ClaudeDriver). Each "
         "run costs a little.", "<tt>sk-ant-...</tt> from console.anthropic.com"],
        ["DEFAULT_PLANNING_MODEL", "Which Claude model planning runs use.", "<tt>claude-opus-4-8"
         "</tt> (use a cheaper model to reduce cost)"],
    ], [4.6 * cm, 6.6 * cm, 5.2 * cm])

    h3("Optional — only for the live connector walkthroughs (Part C)")
    table([
        ["Variable group", "Enables", "Where to get it"],
        ["ATLASSIAN_SITE_URL, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN, ATLASSIAN_CLOUD_ID, "
         "CONFLUENCE_SPACE_KEY, JIRA_PROJECT_KEY",
         "Phase 1: PRD -> Confluence, backlog -> Jira, traceability deep-links, brownfield "
         "onboarding.", "API token: id.atlassian.com -> Security -> API tokens. Use a TEST "
         "space/project."],
        ["GITHUB_API_URL, GITHUB_TOKEN, GITHUB_REPO, GITHUB_DEFAULT_BASE, GITHUB_WEBHOOK_SECRET",
         "Phase 2: companion build -> draft PR -> review -> merge gate -> merge; webhook "
         "reconcile.", "A PAT with <tt>repo</tt> scope (github.com -> Settings -> Developer "
         "settings). Add these keys to <tt>.env</tt> (not in the template by default)."],
        ["FIGMA_TOKEN, FIGMA_FILE_KEY", "Phase 3: read the current design as the source of truth.",
         "Figma -> Settings -> Personal access tokens; a test file's key from its URL."],
        ["XRAY_CLIENT_ID, XRAY_CLIENT_SECRET, XRAY_PROJECT_KEY", "Phase 3: author tests + import "
         "results; failing test -> linked defect.", "Xray Cloud -> Global Settings -> API Keys. "
         "Use a TEST project."],
    ], [5.2 * cm, 6.2 * cm, 5.0 * cm])
    callout("Security",
            "Real credentials live only in <tt>.env</tt>, which is git-ignored — never commit "
            "them. Always use <b>test</b> spaces/projects/repos, not production ones. Without any "
            "connector creds the core local run (Parts A &amp; B) still works fully on the "
            "internal source of truth.")

    h2("4.3 Ports reference")
    table([
        ["Service", "URL", "Login"],
        ["React UI (Experience plane)", "http://localhost:5173", "—"],
        ["Backend API", "http://localhost:8000/api", "<tt>X-Tenant-ID</tt> header"],
        ["Temporal Web UI", "http://localhost:8080", "—"],
        ["MinIO console (object store)", "http://localhost:9001", "minioadmin / minioadmin"],
        ["Postgres (host-mapped)", "localhost:5433", "postgres / postgres (admin)"],
    ], [6.4 * cm, 6.0 * cm, 4.0 * cm])

    h2("4.4 Manual setup notes &amp; gotchas")
    bullets([
        "<b>Migrate as the DB owner.</b> The app connects as the non-superuser <tt>sdlc_app</tt> "
        "role (so RLS applies). Schema changes (ALTER) must run as the <tt>postgres</tt> "
        "superuser. If <tt>make migrate</tt> fails on an ALTER, run migrations with the superuser "
        "DSN: <tt>DATABASE_URL=postgres://postgres:postgres@localhost:5433/sdlc_platform</tt>.",
        "<b>Postgres is on host port 5433</b>, not 5432, to avoid clashing with a native "
        "Postgres. In-container services still use <tt>postgres:5432</tt>.",
        "<b>If the stack drops</b> (a “Socket is not connected” error on :5433 usually "
        "means Docker Desktop stopped), start Docker Desktop and run "
        "<tt>docker compose up -d</tt> again.",
        "<b>Windows without make:</b> use <tt>./make.ps1 &lt;target&gt;</tt> (e.g. "
        "<tt>./make.ps1 dev</tt>).",
        "<b>First frontend start</b> runs <tt>npm install</tt> inside the container — the very "
        "first <tt>make dev</tt> takes a few minutes while node modules download.",
        "<b>The companion runner</b> runs on the developer's own machine (not in Docker) via "
        "<tt>python -m runner.companion ...</tt>; it connects outbound to the platform API.",
    ])
    callout("Quick start, condensed",
            "<tt>cp .env.example .env</tt> (set ANTHROPIC_API_KEY) -> <tt>docker compose up -d"
            "</tt> -> <tt>make migrate</tt> -> <tt>make seed</tt> -> <tt>make dev</tt> -> open "
            "<tt>http://localhost:5173</tt> and run a phase through its gate.", ok=True)
    gap(8)
    p("<i>This document describes Phases 0–4 (complete and tested). Section 5 is an explicit "
      "test-through inventory of what works today. The next milestone is Phase 5 — Enterprise "
      "Hardening &amp; Cloud Migration (RBAC + segregation of duties, secrets vault, "
      "prompt-injection hardening, immutable audit/compliance, the eval harness, and the cloud "
      "runner fleet).</i>", LEAD)


def section_5():
    story.append(PageBreak())
    h1("5. End-to-End Testing — Two Full Journeys")
    lead("This section is for an engineer running a real, straight-through test pass with the "
         "live credentials configured — not slice by slice. Each journey runs the whole lifecycle "
         "end to end: <b>Journey A</b> takes a brand-new (greenfield) project from an idea to a "
         "merged, tested change; <b>Journey B</b> onboards an existing (brownfield) project and "
         "resumes it from the middle. Complete <b>Section 3</b> (bring-up) once first, then follow "
         "the preflight below.")
    callout("Conventions used in every command",
            "All API calls carry <tt>-H \"X-Tenant-ID: $TENANT\"</tt> (the only exception is "
            "creating a tenant). Human gates are shown as a browser action on the <b>Gate "
            "Approvals</b> tab, with the equivalent <tt>POST /approvals/{id}/decide/</tt> next to "
            "it. A gate decision must be made by a user who <b>holds the gate's role</b> on the "
            "project — the preflight grants the demo user every role so one person can approve the "
            "whole run. Phase-4 brownfield services have no dedicated UI yet, so Journey B uses a "
            "few <tt>manage.py shell</tt> calls (clearly marked) alongside the REST routes.")

    h2("5.1 Preflight (live mode) — do this once")
    p("Put the live credentials in <tt>.env</tt> (see Section 4.2: Atlassian, GitHub, Figma, "
      "Xray, plus <tt>ANTHROPIC_API_KEY</tt>), then re-seed so the demo tenant picks up the "
      "connectors, and restart the app:")
    code("cp .env.example .env          # then fill the live values from Section 4.2\n"
         "docker compose up -d          # infra: postgres:5433, temporal:7233/8080, minio:9001\n"
         "make migrate && make seed     # seed attaches the connectors to the demo tenant\n"
         "make dev                      # API :8000, React UI :5173, Temporal worker")
    p("Set a few shell variables and grant the seeded demo user every gate role (so a single "
      "approver can pass every gate in the run):")
    code("export API=http://localhost:8000/api\n"
         "export TENANT=00000000-0000-0000-0000-0000000000d1   # the seeded demo tenant\n"
         "export H=\"-H X-Tenant-ID:$TENANT -H Content-Type:application/json\"\n"
         "# the demo user (demo@demo.test) seeds with product_owner+architect; add the rest:\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from apps.tenancy.models import Membership, User; from apps.projects.models import "
         "Project;\\\n"
         "u=User.objects.get(email='demo@demo.test');\\\n"
         "[Membership.objects.get_or_create(tenant_id=p.tenant_id,user=u,project=p,role=r) \\\n"
         " for p in Project.objects.all() \\\n"
         " for r in ['product_owner','architect','designer','tech_lead','reviewer','qa_lead',"
         "'security_engineer','devops']]\"")
    callout("Get the demo user id for gate decisions",
            "<tt>curl -s $API/../ &nbsp;</tt> &mdash; the gate-decision body needs the approver's "
            "<tt>user_id</tt>. Fetch it once: <tt>docker compose exec backend python manage.py "
            "shell -c \"from apps.tenancy.models import User; "
            "print(User.objects.get(email='demo@demo.test').id)\"</tt> and export it as "
            "<tt>USER</tt>.")

    h2("5.2 Journey A — Greenfield (new project, full lifecycle)")
    p("A new project from scratch, idea through a merged + tested change. Steps 1–3 create the "
      "project, its profile, and a work item; copy the returned ids into the shell variables.")
    code("# 1) create a greenfield project\n"
         "curl -s $H -X POST $API/projects/ -d '{\"name\":\"Acme Shop\",\"track\":\"greenfield\"}'\n"
         "export PROJECT=<id-from-response>\n\n"
         "# 2) set the project profile (becomes the agents' context)\n"
         "curl -s $H -X PUT $API/projects/$PROJECT/profile/ -d '{\"description\":\"A web shop\","
         "\"tech_stack\":{\"backend\":\"Django\",\"frontend\":\"React\"},"
         "\"important_context\":\"Web-first, desktop primary.\"}'\n\n"
         "# 3) create a feature WorkItem\n"
         "curl -s $H -X POST $API/work-items/ -d '{\"project\":\"'$PROJECT'\","
         "\"type\":\"story\",\"feature_stream\":\"checkout\",\"title\":\"Guest checkout\"}'\n"
         "export WI=<id-from-response>")
    p("Now walk the lifecycle. Each phase is the <i>same</i> two moves — <b>trigger</b> the agent "
      "on the work item, then <b>approve</b> its gate — so the pattern is shown once and the "
      "per-phase agent keys, gate roles, and live proofs follow in the table:")
    code("# the repeating pattern (run once per phase, substituting AGENT below):\n"
         "curl -s $H -X POST $API/work-items/$WI/trigger/ -d '{\"agent_key\":\"01_ideation\"}'\n"
         "#   -> 202 with a run_id; the run moves running -> awaiting_gate\n"
         "curl -s $H \"$API/runs/?work_item=$WI\"            # watch status; also Temporal UI :8080\n"
         "curl -s $H \"$API/approvals/?decision=pending&work_item=$WI\"   # get the approval id\n"
         "curl -s $H -X POST $API/approvals/<approval-id>/decide/ \\\n"
         "     -d '{\"user_id\":\"'$USER'\",\"decision\":\"approved\"}'   # or the Gate Approvals tab")
    table([
        ["#", "Phase — <tt>agent_key</tt>", "Gate role", "What you should see (the live proof)"],
        ["1", "Ideation — <tt>01_ideation</tt>", "product_owner", "Run completes; an "
         "<tt>ideation</tt> artifact flips draft -> published (Artifacts tab / MinIO body)."],
        ["2", "Requirements — <tt>02_requirements</tt>", "product_owner", "A "
         "<tt>requirements</tt> artifact published; Traceability shows it derives from ideation."],
        ["3", "PRD — <tt>03_prd</tt>", "product_owner", "<b>A Confluence page is created</b> on "
         "approval; the artifact's <tt>external_ref.url</tt> and the Traceability node deep-link "
         "to it."],
        ["4", "Architecture — <tt>04_architecture</tt>", "architect", "An <tt>architecture</tt> "
         "(+ ADR/data-model/api-spec) artifact set published."],
        ["5", "UX Design — <tt>05_ux_design</tt>", "designer", "<b>Reads your live Figma</b> "
         "(tokens/components); the <b>WCAG gate</b> blocks approval until every required criterion "
         "is satisfied (send them in the decide call's <tt>conditions</tt>, or tick them in the "
         "UI)."],
        ["6", "Task Breakdown — <tt>06_task_breakdown</tt>", "tech_lead", "<b>Epics/stories appear "
         "in Jira</b> on approval; child WorkItems are created and Traceability links story -> "
         "requirement."],
        ["7", "Implementation — <tt>07_implementation</tt>", "tech_lead", "Runs on the "
         "<b>companion</b> (next code block) -> a <b>draft PR opens on GitHub</b>; the "
         "BuildWorkflow is visible in the Temporal UI."],
        ["8", "Code Review — <tt>08_code_review</tt>", "reviewer", "Review findings become child "
         "WorkItems; the 07 &lt;-&gt; 08 remediation loop re-runs until clean."],
        ["9", "Testing — <tt>09_testing</tt> (+ <tt>09b_test_automation</tt>)", "qa_lead",
         "<b>Tests author to Xray + results import</b>; a failing test opens a linked, traced "
         "defect WorkItem that closes on a clean re-run."],
        ["10", "Security — <tt>10_security</tt>", "security_engineer", "A security review + "
         "<b>SBOM</b>; any Critical/High finding opens a defect and blocks the gate until "
         "resolved."],
        ["11", "Merge", "reviewer", "Approve the <b>reviewer merge gate</b> -> the GitHub PR "
         "<b>merges</b>; the WorkItem moves to <tt>done</tt>."],
        ["12", "CI/CD + Deploy — <tt>11_cicd</tt>, <tt>12_deployment</tt>", "devops", "Pipeline "
         "config + a release/deployment artifact are produced (real cloud deploy is Phase 5)."],
    ], [0.7 * cm, 4.7 * cm, 3.0 * cm, 8.0 * cm])
    p("<b>The build step (phase 7), on your machine.</b> After triggering "
      "<tt>07_implementation</tt>, run the companion against your real clone — it works in a "
      "platform-managed worktree branch, builds/tests locally, and opens the PR:")
    code("# enroll this machine once (prints a one-time token)\n"
         "python -m runner.companion enroll --api-url http://localhost:8000 \\\n"
         "    --tenant $TENANT --project $PROJECT --label my-laptop --repos owner/name\n\n"
         "# fetch the assigned build task for the run, then execute it in a managed worktree\n"
         "curl -s $H \"$API/runner/builds/<run_id>/\" > task.json\n"
         "python -m runner.companion run --task task.json \\\n"
         "    --repo-path ~/repos/your-clone --worktrees ~/sdlc")
    callout("Greenfield journey — done",
            "You have taken a brand-new project idea -> requirements -> <b>PRD in Confluence</b> "
            "-> architecture -> <b>UX from live Figma + WCAG gate</b> -> <b>backlog in Jira</b> -> "
            "<b>a built, reviewed GitHub PR</b> -> <b>tests in Xray with a linked defect</b> -> a "
            "security review -> <b>merge</b> -> CI/CD + deploy artifacts. Every transition was "
            "human-gated and recorded in the Event ledger and Run timeline.", ok=True)

    h2("5.3 Journey B — Brownfield (existing project, resume mid-pipeline)")
    p("Onboard a real existing project, let the platform tell you where to resume, then carry on. "
      "The Phase-4 onboarding / API-contract / drift services have no dedicated UI yet, so this "
      "journey mixes the REST routes that exist with a few marked <tt>manage.py shell</tt> calls; "
      "the human gates are still approved in the browser. (The single self-contained proof of the "
      "whole flow is <tt>pytest tests/test_acceptance_phase4.py -v</tt>.)")
    code("# 1) create a brownfield project, then register its repositories (one or many)\n"
         "curl -s $H -X POST $API/projects/ -d '{\"name\":\"Legacy Shop\",\"track\":\"brownfield\"}'\n"
         "export PROJECT=<id-from-response>\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from apps.projects.repos import add_repository as A;\\\n"
         "print(A(tenant_id='$TENANT',project_id='$PROJECT',name='owner/web',role='frontend'));\\\n"
         "print(A(tenant_id='$TENANT',project_id='$PROJECT',name='owner/api',role='backend'))\"\n"
         "#   -> repo_topology reconciles to split/multi")
    code("# 2) code intelligence (00c): run the built-in analyzer on your clone, register it,\n"
         "#    and index it into the Knowledge Index (platform stores intel + chunks, not source)\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from integrations.codeintel.builtin import BuiltinCodeIntel;\\\n"
         "from mcp_platform_state import tools; from apps.knowledge.index import index_artifact;\\\n"
         "idx=BuiltinCodeIntel().index(workspace='/path/to/your/clone', repo='owner/api');\\\n"
         "print(idx.file_count, idx.commits, idx.hotspots);\\\n"
         "a=tools.register_artifact('$TENANT','$PROJECT',None,'context_extraction',"
         "'codebase_intelligence','internal','h');\\\n"
         "index_artifact(tenant_id='$TENANT',project_id='$PROJECT',artifact_id=a['id'],"
         "text='backend exposes GET /users')\"")
    code("# 3) register what already exists (register-don't-recreate) + adopt static docs\n"
         "curl -s $H -X POST $API/projects/$PROJECT/onboard-atlassian/   # existing Confluence/Jira\n"
         "curl -s -H \"X-Tenant-ID:$TENANT\" -F file=@./old-spec.docx \\\n"
         "     $API/projects/$PROJECT/source-documents/                  # extract -> draft\n"
         "curl -s $H -X POST $API/source-documents/<id>/adopt/ -d '{\"user_id\":\"'$USER'\"}'  # gate")
    code("# 4) gap report -> the resume phase; 5) cross-repo API-contract read-through\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from integrations.onboarding import build_gap_report;\\\n"
         "from integrations.api_contract import export_api_contract, read_api_contract, "
         "record_implements;\\\n"
         "r=build_gap_report(tenant_id='$TENANT',project_id='$PROJECT');\\\n"
         "print('RESUME PHASE ->', r['resume_phase'], '| gaps:', r['blockers']);\\\n"
         "c=export_api_contract(tenant_id='$TENANT',project_id='$PROJECT',body='GET /users',"
         "source_commit='abc123');\\\n"
         "print('contract', c['semver']);\\\n"
         "print('read-through', read_api_contract(tenant_id='$TENANT',project_id='$PROJECT')"
         "['external_ref']['semver'])\"")
    p("<b>6) Resume mid-pipeline.</b> Trigger the phase the gap report named (e.g. if it says "
      "<tt>architecture</tt>, trigger <tt>04_architecture</tt> on a work item) and approve its "
      "gate in the browser — onboarding has handed straight to the same pipeline Journey A used.")
    code("curl -s $H -X POST $API/work-items/$WI/trigger/ -d '{\"agent_key\":\"04_architecture\"}'\n"
         "#   then approve the architect gate (Gate Approvals tab / the decide call from 5.2)")
    code("# 7) contract change -> a drift gate with cross-repo change-impact -> architect decides\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from integrations.api_contract import export_api_contract;\\\n"
         "from integrations.drift import detect_contract_drift, open_drift_records, decide_drift;\\\n"
         "b=export_api_contract(tenant_id='$TENANT',project_id='$PROJECT',"
         "body='GET /users (v2 breaking)',change='major');\\\n"
         "d=detect_contract_drift(tenant_id='$TENANT',contract_artifact_id=b['artifact_id'],"
         "new_semver='2.0.0');\\\n"
         "print('impacted repos/artifacts ->', d['impacted']);\\\n"
         "print(decide_drift(tenant_id='$TENANT',drift_id=d['drift_id'],user_id='$USER',"
         "decision='accept'))\"\n"
         "#   (or trigger it live: push to the provider repo so the signed GitHub webhook fires)")
    callout("Brownfield journey — done",
            "You onboarded an existing multi-repo project, indexed its code, registered its "
            "existing Confluence/Jira + static docs without duplicates, got a <b>gap report with "
            "a resume phase</b>, exported a <b>versioned API contract read across repos</b>, "
            "<b>resumed mid-pipeline</b> into the normal gated flow, and watched a <b>contract "
            "change open a drift gate</b> whose impact spanned both repos. Re-running any "
            "register step adds nothing (register-don't-recreate).", ok=True)

    h2("5.4 If something stalls")
    p("Almost always it is the environment, not the platform. Quick checks:")
    bullets([
        "<b>Infra down:</b> a “Socket is not connected” on :5433 means Docker Desktop stopped — "
        "start it and <tt>docker compose up -d</tt> again.",
        "<b>Migrations:</b> if <tt>make migrate</tt> errors on an ALTER, run it with the "
        "<tt>postgres</tt> superuser DSN (Section 4.4).",
        "<b>No agent output / 500 on trigger:</b> <tt>ANTHROPIC_API_KEY</tt> is missing or the "
        "model id is wrong (Section 4.2).",
        "<b>Live SoR step does nothing:</b> the connector creds aren't set, or you didn't "
        "<tt>make seed</tt> after adding them — reseed and restart <tt>make dev</tt>.",
        "<b>Gate won't approve (403):</b> the <tt>user_id</tt> doesn't hold that gate's role on "
        "the project — re-run the role-grant snippet in 5.1.",
        "<b>Full automated proof anytime:</b> <tt>cd backend &amp;&amp; pytest -q</tt> "
        "(<b>423 passed, 3 skipped</b>; the 3 skips are external-SaaS live round-trips).",
    ])


# ── doc template with TOC + bookmarks + footer ──────────────────────
class GuideDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name not in ("H1", "H2"):
            return
        text = flowable.getPlainText()
        level = 0 if name == "H1" else 1
        key = f"sec-{self.seq.nextf('toc')}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page, key))


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(2 * cm, 1.0 * cm, "AI-First SDLC Platform — Overview & Local Testing Guide")
    canvas.drawRightString(A4[0] - 2 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 1.0 * cm, A4[0], 1.0 * cm, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.rect(0, 0, A4[0], 0.5 * cm, fill=1, stroke=0)
    canvas.restoreState()


def build():
    doc = GuideDoc(str(OUT), pagesize=A4,
                   leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                   title="AI-First SDLC Platform — Overview & Local Testing Guide",
                   author="EdvenSoft")
    frame = Frame(2 * cm, 2 * cm, A4[0] - 4 * cm, A4[1] - 4 * cm, id="main")
    cover_frame = Frame(2 * cm, 2 * cm, A4[0] - 4 * cm, A4[1] - 4 * cm, id="cover")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_cover_bg),
        PageTemplate(id="body", frames=[frame], onPage=_footer),
    ])

    cover()
    toc()
    section_1()
    section_2()
    section_3()
    section_4()
    section_5()

    doc.multiBuild(story)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
