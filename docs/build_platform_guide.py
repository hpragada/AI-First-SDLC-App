"""Generate the AI-First SDLC Platform — Overview & Local Testing Guide (PDF).

Pure ReportLab (Platypus). Glyph-safe for the built-in Helvetica/Courier (WinAnsi):
em/en dashes and bullets are fine; arrows are written "->"; no emoji/checkmarks.
Run from the repository root:  .venv/Scripts/python docs/build_platform_guide.py
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
        ["Scope", "Phases 0–4.8 (complete &amp; tested); Phase 5 next. Brownfield code-intelligence "
         "dispatch is a documented, deliberately deferred decision (see 2.8 and ADR references) — "
         "everything else is UI-driven end to end."],
        ["Document", "Goal &amp; overview · phase build descriptions · what works today end-to-end · hands-on local testing guide (UI-first) · setup &amp; credentials"],
        ["Date", date.today().strftime("%B %d, %Y")],
        ["Source of truth", "/CLAUDE.md · /BUILD_PLAN.md · /docs/* (incl. /docs/decisions/*)"],
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
    h1("2. The Build, Phase by Phase (Phases 0–4.8)")
    lead("Each phase below lists the concrete components that were built and explains what each "
         "one does in everyday language, and closes with a <b>capstone slice</b> — the thin "
         "end-to-end demo that proves the phase works. (For a real, straight-through test pass — "
         "see the scenarios in <b>Section 5</b>.) Phases 0 through 4.8 are complete and tested. "
         "Phases 0–4 (2.1–2.5) built the platform's execution spine and connectors; Phases "
         "4.5/4.7/4.8 (2.6–2.8) turned it into a real, self-serve, browser-driven product — every "
         "screen in this guide from Section 3 onward is one of the hi-fi screens 4.8 shipped.")

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
        ["a11y (WCAG) gate", "The accessibility review is enforced as a <b>checklist of WCAG 2.2 "
         "AA conditions on the design Approval</b> — 22 required criteria, plus up to 5 optional "
         "AAA criteria a project can switch on. An approve is blocked until every required "
         "criterion is satisfied. It is a control-plane gate, not a prompt rule."],
        ["Per-tenant theming", "Design tokens + responsive breakpoints stored on the Project "
         "Profile flow verbatim into the manifest — one theme, no per-tenant code fork."],
        ["TestMgmt connector (Xray)", "Authors test cases as Xray tests and imports execution "
         "results (idempotently). Headless, per-tenant, rate-governed."],
        ["Result import + defect loopback", "A test run (Test Automation, <tt>09b</tt> &mdash; "
         "the only phase that produces one) records a <tt>TestExecution</tt> + a "
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

    # ---- Phase 4.5 ----
    h2("2.6 Phase 4.5 — Local-Engine Execution &amp; Interactive Clarifications")
    p("<b>Goal:</b> make “agents run on your own Claude Code” real end-to-end, and let an agent "
      "ask a genuine question mid-run instead of guessing — without ever billing while it waits.")
    table([
        ["Component", "What it is / does"],
        ["Companion-routed trigger", "The REST trigger (and the UI) now resolves the acting user "
         "and routes the run to <i>their</i> enrolled companion (<tt>execution_mode=companion</tt>) "
         "instead of a server-side engine call — this is what makes Section 3's “run a phase” "
         "actually execute on your machine."],
        ["Interactive <tt>ask_human</tt>", "An agent can open a pending <b>Clarification</b> "
         "mid-run and pause — the companion is idle and <b>no tokens are spent while it waits</b>. "
         "Answering (REST or the Clarifications screen) lets the companion pick the answer up on "
         "its next poll and resume in the same session."],
        ["Cost accounting fix", "A run's cost is only set from the companion's final report — a "
         "paused clarification never shows a phantom cost."],
        ["Offline -> human takeover", "If the companion never reports (laptop closed, network "
         "down), the run parks the WorkItem for human takeover instead of hanging forever."],
    ], [4.4 * cm, 12.0 * cm])
    callout("Phase 4.5 — capstone slice (what this phase proves)",
            "Trigger a phase as yourself -> it routes to your companion -> the agent asks a "
            "question -> the run shows “needs answer” at <b>zero cost</b> while it waits -> you "
            "answer -> it resumes and completes -> gate -> publish. Plus: an offline companion "
            "parks the run for takeover instead of hanging.", ok=True)

    # ---- Phase 4.7 ----
    h2("2.7 Phase 4.7 — Web-App Productization: Auth &amp; Admin (backend)")
    p("<b>Goal:</b> replace the pre-4.8 “paste a tenant id into a header” acceptance-slice shell "
      "with the real auth/admin backend a proper product needs — session login, self-serve "
      "signup, invitations, and role management — as the <b>design-invariant</b> contract the "
      "Phase 4.8 hi-fi screens are built against.")
    table([
        ["Component", "What it is / does"],
        ["Server-session auth", "<tt>POST /auth/signup</tt> (atomically creates a new Tenant + its "
         "first admin User), <tt>POST /auth/login</tt>, <tt>GET /auth/me</tt>, "
         "<tt>POST /auth/logout</tt> — a real browser session (cookie), not a header you type in."],
        ["Invitations", "Admin invites by email with initial project/role grants; the invitee "
         "accepts (sets their password) via a tokenised link; resend/revoke; no account "
         "enumeration on password reset."],
        ["User &amp; role management", "Users list, per-project role grants (<tt>Membership</tt>), "
         "gate-role coverage (flags e.g. “no reviewer -> merge gate unactionable”), the "
         "tenant-admin flag with a <b>last-admin guard</b> (can't demote the only admin) — both a "
         "tenant-admin <i>and</i> a project-admin can approve <b>any</b> gate on their scope."],
        ["Companion status + connect", "The Connect-Machine flow (enrollment token, online/offline "
         "status) is now session-scoped to the logged-in developer instead of an ungated, "
         "tenant-wide list."],
        ["Tenant context from the session (hardened 2026-07-02)", "How RLS learns which tenant a "
         "request belongs to was corrected after this Guide's own testing pass exercised it "
         "for the first time against the real (non-superuser) database role — see "
         "<tt>/docs/decisions/0002-rls-tenant-bootstrap-session.md</tt> for the full root cause "
         "and fix; the short version is in Section 4.4."],
    ], [4.4 * cm, 12.0 * cm])
    callout("Phase 4.7 — capstone slice (what this phase proves)",
            "From scratch, no shell step: signup -> admin invites a user -> user accepts + sets a "
            "password -> admin grants gate roles -> connect-machine status -> create a project -> "
            "trigger a phase as the authenticated user (routes to their companion) -> answer a "
            "clarification -> decide a gate -> preview the published artifact. This is exactly "
            "Section 5's Scenario 1, driven by the real REST surface underneath the 4.8 screens.",
            ok=True)

    # ---- Phase 4.8 ----
    h2("2.8 Phase 4.8 — Hi-Fi Web App (the UI in this guide)")
    p("<b>Goal:</b> build the real product UI — every journey (J1–J22) as a signed-off, hi-fi "
      "screen wired to live data — replacing the placeholder “Tenant + Project bar” shell that "
      "earlier guide revisions walked through.")
    table([
        ["Component", "What it is / does"],
        ["App shell + navigation", "Login/Signup/AcceptInvite/ResetPassword (pre-auth) and, once "
         "signed in, a persistent sidebar (Dashboard, Work Items, Phases &amp; Runs, Gates, "
         "Clarifications, Artifacts &amp; Traceability, plus Project and Admin sections) with a "
         "tenant/project switcher — this is what Section 3.2 walks through screen by screen."],
        ["Work Items board + detail", "Create/list/filter work items (Epic/Task/Defect), a "
         "type-adaptive lifecycle rail per item, in-place edit, and a task-breakdown fan-out from "
         "an approved epic into build-tier tasks."],
        ["Phases &amp; Runs", "Pick a work item, trigger any phase for it (blocked with a link to "
         "Connect Machine if your companion is offline), and watch the run timeline live."],
        ["Gates, Clarifications, Criteria-gate", "Real approve/reject with the required role "
         "enforced, a generalized checklist-condition gate (e.g. the WCAG gate), and a live answer "
         "form for pending questions."],
        ["Artifacts, Traceability, Publish", "Registry + preview + version history, a lineage "
         "graph, and a gate-respecting publish action to the live system of record."],
        ["Onboarding (brownfield front door)", "Upload-and-extract source documents behind an "
         "adopt gate, register existing Confluence/Jira (no duplicates), a gap report with a "
         "resume-phase recommendation. <b>Code-intelligence indexing is the one still-open piece</b> "
         "— see the callout below."],
        ["Setup: Integrations, Repositories, Connect Machine", "Attach Confluence/Jira/GitHub/"
         "Figma/Xray from a form (no shell script), manage the project's repositories, and "
         "generate a companion enrollment token with the exact two terminal commands to run."],
        ["Admin: Users &amp; Invitations, Roles &amp; Memberships", "Invite teammates (multiple "
         "project/role grants per invite), see pending invitations alongside active members, and "
         "grant/revoke per-project roles or the tenant-admin flag from a matrix."],
    ], [4.4 * cm, 12.0 * cm])
    callout("What's genuinely still not UI-driven — brownfield code-intelligence dispatch",
            "Every brownfield onboarding step above works from the browser <b>except</b> triggering "
            "the built-in code-intelligence analyzer itself: the backend endpoint only "
            "<i>records</i> an already-computed result, and there is deliberately no live command "
            "channel yet from the platform to a developer's companion to run it on demand (a "
            "<b>documented, deferred architecture decision</b>, not an oversight — Phase 4.7's own "
            "spec calls it out). Because of this, Section 5's brownfield scenarios (5.4/5.5) are "
            "left as they were in the previous guide revision — API/shell-annotated — rather than "
            "rewritten to a UI flow that doesn't fully exist yet. Everything else in this guide, "
            "greenfield and brownfield alike, is UI-first.")
    callout("Phase 4.8 — capstone slice (what this phase proves)",
            "Every screen renders every labelled state from the hi-fi design gallery with visual "
            "parity, wired to live endpoints — not mock data. Section 3.2 and Section 5's "
            "greenfield scenarios are a straight-through click-path proof of this.", ok=True)


def section_3():
    h1("3. The Local Execution &amp; Testing Guide")
    lead("This is a hands-on guide for a developer to run the platform locally and <i>see</i> "
         "every workflow work — in the browser, the API, the Temporal dashboard, and the object "
         "store. It is not about unit tests. Follow Part A to get the core running with zero "
         "external accounts; Part C adds the optional live connectors.")
    callout("Before you start",
            "Complete the prerequisites in <b>Section 4</b> first (Docker Desktop running, "
            "<tt>.env</tt> created). <b>Agents run on your own Claude Code</b> (req #1): every "
            "phase — planning, build, and review — executes on the machine running the "
            "<b>companion</b> daemon, using your <b>logged-in local <tt>claude</tt></b> (your "
            "subscription), <b>not</b> an API key. So instead of setting <tt>ANTHROPIC_API_KEY</tt>, "
            "you log in once (<tt>claude</tt> / <tt>claude setup-token</tt>) and run the companion "
            "(Step 4). A server-side <tt>ANTHROPIC_API_KEY</tt> path still exists as a headless/CI "
            "fallback only. On Windows without <tt>make</tt>, use <tt>./make.ps1 &lt;target&gt;</tt>.")

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

    h3("Step 4 — Run your local companion (so phases execute on YOUR Claude Code)")
    p("Every phase the platform dispatches runs on the machine running the companion, against "
      "your logged-in <tt>claude</tt> — no API key. Log in once, enroll this machine for your "
      "user, then leave the daemon running:")
    code("# 1) log Claude Code in once (interactive, or a long-lived token for headless):\n"
         "claude            # sign in to your subscription   (or: claude setup-token)\n\n"
         "# 2) enroll this machine for YOUR user (prints a one-time token):\n"
         "python -m runner.companion enroll --api-url http://localhost:8000 \\\n"
         "    --tenant $TENANT --project $PROJECT --label my-laptop --developer-id $USER\n\n"
         "# 3) run the headless daemon — it claims your dispatched phases and runs them locally:\n"
         "python -m runner.companion serve --api-url http://localhost:8000 \\\n"
         "    --tenant $TENANT --token <enrollment-token>   # add --repo-path/--worktrees for builds")
    p("<b>What you should see:</b> the daemon logs that it preflighted <tt>claude</tt> on PATH "
      "(and dropped any <tt>ANTHROPIC_API_KEY</tt> so your subscription is used), then idles "
      "polling for work. When you trigger a phase (next), it claims and runs it; an agent that "
      "needs input surfaces a question on the <b>Clarifications</b> tab and waits at no cost.")

    h2("3.2 Part B — Drive the planning slice in the browser (real Phase 4.8 screens)")
    p("This is the core, no-external-accounts workflow, entirely in the browser — the only "
      "exceptions anywhere in this walkthrough are the two local terminal commands in Step 4 above "
      "(<tt>claude</tt> login and running the companion). Open "
      "<tt>http://localhost:5173</tt>: you land on <b>Login</b>. This guide builds "
      "<b>your own</b> tenant from scratch rather than the seeded demo — click "
      "<b>“Create a workspace”</b> to reach <b>Signup</b>.")
    callout("Cost &amp; interaction note",
            "Phases run on your <b>local Claude Code subscription</b> via the companion — there is "
            "no per-call API charge and no <tt>ANTHROPIC_API_KEY</tt> needed. If an agent needs "
            "information it cannot find, it asks on the <b>Clarifications</b> screen and <b>pauses "
            "at zero cost</b> until you answer (the model is idle while it waits) — then continues "
            "in the same session. To see the whole loop quickly, trigger a single phase (Ideation).")
    table([
        ["Screen", "What to do", "What you should see (the proof)"],
        ["Signup (<tt>/signup</tt>)", "Full name, work email, a password, and your workspace/org "
         "name; <b>Create workspace</b>.", "You land signed in as the tenant's first admin — no "
         "shell step created you. A confirmation screen hands you to the Setup Checklist."],
        ["Setup Checklist (<tt>/setup</tt>)", "Follow its steps in order: create a project, "
         "connect your machine, invite teammates (optional for a solo test), connect "
         "integrations (optional — Part C).", "Each step ticks off as you complete it."],
        ["Create Project (<tt>/projects/new</tt>)", "Name it, pick Greenfield, Save.", "You land on "
         "the new project's Project Profile, and it becomes your selected project everywhere "
         "(top-bar switcher) — as the creator you're automatically granted the project-admin "
         "role, so you can approve every gate on it yourself."],
        ["Connect Machine (<tt>/connect</tt>)", "Pick this project, <b>Generate enrollment "
         "token</b>.", "A one-time token is shown once, with the exact two commands to paste into "
         "your terminal — the same <tt>claude</tt> + <tt>companion serve</tt> pair from Step 4, "
         "now pre-filled with your token. Once the daemon checks in, this screen (and the sidebar) "
         "shows <b>Connected</b>."],
        ["Project Profile (<tt>/profile</tt>)", "Fill description, tech stack, important context; "
         "Save.", "A new profile version is saved; it becomes the agent's context next run."],
        ["Work Items (<tt>/work-items</tt>)", "<b>+ New Work Item</b> -> a title, type "
         "<b>Epic</b> -> Create.", "You land on the new epic's detail page with a full 16-phase "
         "lifecycle rail, all <tt>Upcoming</tt>."],
        ["Phases &amp; Runs (<tt>/runs</tt>)", "Pick your work item, click <b>Ideation</b> to "
         "trigger it.", "A Run appears and moves <tt>running -> awaiting_gate</tt> as your "
         "companion executes it. In the Temporal UI (:8080) a new <tt>AgentRunWorkflow</tt> is "
         "visible. A <b>“needs answer”</b> badge appears on the Clarifications nav item if the "
         "agent asks a question."],
        ["Clarifications (<tt>/clarifications</tt>)", "If the badge is showing, open this screen, "
         "answer the question(s), Send.", "The agent resumes in the same session (it was paused at "
         "zero cost); the badge clears."],
        ["Gates (<tt>/gates</tt>)", "Find the pending approval; Approve (you hold the role — "
         "project-admin can approve any gate).", "The run resumes to <tt>completed</tt>; the "
         "workflow finishes in the Temporal UI."],
        ["Artifacts &amp; Traceability (<tt>/artifacts</tt>, <tt>/traceability</tt>)", "Open the "
         "ideation artifact; open the lineage view.", "The artifact's status flips <tt>draft -> "
         "published</tt> (body in MinIO under <tt>drafts/</tt> and <tt>snapshots/</tt>); the "
         "traceability graph shows it and its <tt>derives/tests/...</tt> edges — once external "
         "SoRs are connected, nodes deep-link to the live Confluence/Jira items."],
    ], [3.6 * cm, 5.4 * cm, 7.4 * cm])
    p("Repeat the trigger for <b>Requirements -> PRD -> Architecture</b> from Phases &amp; Runs to "
      "walk the full planning chain. Each run reads the artifacts the previous phase published "
      "(proving the platform — not a local file — is the source of truth), and each is "
      "independently gated. This exact walkthrough, scripted start to finish, is Section 5's "
      "Scenario 1.")

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
            "(1) infra healthy; (2) migrate + seed succeed; (3) UI loads and the tabs work; "
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
        "<b>Login/signup returning 401 or “Invalid email or password” with correct credentials</b> "
        "on an older local database means migration "
        "<tt>apps/tenancy/migrations/0005_user_rls_auth_bootstrap.py</tt> hasn't run yet — "
        "<tt>make migrate</tt> (as the <tt>postgres</tt> superuser, same as above) applies it. See "
        "<tt>/docs/decisions/0002-rls-tenant-bootstrap-session.md</tt> for why this exists: "
        "resolving who's logged in has to work *before* the tenant is known, which the original "
        "RLS policy on the users table didn't allow for.",
    ])
    callout("Quick start, condensed",
            "<tt>cp .env.example .env</tt> (set ANTHROPIC_API_KEY) -> <tt>docker compose up -d"
            "</tt> -> <tt>make migrate</tt> -> <tt>make seed</tt> -> <tt>make dev</tt> -> open "
            "<tt>http://localhost:5173</tt> and run a phase through its gate.", ok=True)
    gap(8)
    p("<i>This document describes Phases 0–4.8 (complete and tested). Section 5 is an explicit "
      "test-through inventory of what works today. The next milestone is Phase 5 — Enterprise "
      "Hardening &amp; Cloud Migration (RBAC + segregation of duties, secrets vault, "
      "prompt-injection hardening, immutable audit/compliance, the eval harness, and the cloud "
      "runner fleet).</i>", LEAD)


def section_5():
    story.append(PageBreak())
    h1("5. End-to-End Testing — Scenario Playbook")
    lead("This section is a hands-on playbook for an engineer to test the platform across the "
         "scenarios that matter, <b>each built from scratch</b> — you create your own tenant, "
         "user, project and companion; nothing here uses the seeded demo tenant. Do <b>Section "
         "3</b> bring-up once, then the shared <b>5.1 preflight</b>, then run whichever scenarios "
         "you need. Scenarios 1, 2, and 5 (greenfield + cross-cutting) are <b>UI-only</b> except "
         "the two irreducible local commands (<tt>claude</tt> login, running the companion — "
         "Section 3.1 Step 4). Scenarios 3 and 4 (brownfield) still carry API/shell steps for the "
         "one piece that isn't wired to the browser yet — code-intelligence indexing — a "
         "deliberate, documented scope decision explained in 2.8; those two scenarios are "
         "otherwise unchanged from the previous guide revision pending that follow-up.")
    callout("Two ground rules for every scenario",
            "(1) <b>From scratch:</b> you create the tenant/user/project yourself, via the real "
            "Signup screen — do not use the seed demo tenant. (2) <b>Agents run on your Claude "
            "Code:</b> every phase executes on your machine via the <b>companion</b> daemon using "
            "your logged-in <tt>claude</tt> (no API key); you only ever click and type in the web "
            "app. The handful of remaining API calls (brownfield code-intel only) carry "
            "<tt>-H \"X-Tenant-ID: $TENANT\"</tt>.")

    h2("5.1 Preflight — build your own world (shared by all scenarios)")
    p("<b>Step 1 (infra).</b> Bring the stack up once (Section 3.1): <tt>docker compose up -d</tt> "
      "-> <tt>make migrate</tt> -> <tt>make dev</tt>. You do <b>not</b> run <tt>make seed</tt> — you "
      "are building everything yourself.")
    p("<b>Step 2 (UI) — sign up.</b> Open <tt>http://localhost:5173/signup</tt>: name, work email, "
      "password, workspace name -> <b>Create workspace</b>. This atomically creates your tenant "
      "and you as its first admin (and seeds that tenant's agent specs) — no <tt>curl</tt>, no "
      "shell. You're signed in immediately. As the tenant's sole admin, and as the project-admin "
      "you're automatically granted on any project you create (5.2's first step), you can approve "
      "<b>every</b> gate yourself — invite a teammate only if you specifically want to test "
      "role-scoped gating.")
    p("<b>Step 3 (UI, optional) — invite a teammate + grant roles.</b> Only needed if you want "
      "more than one person: <b>Users &amp; Invitations</b> (sidebar -> Workspace Admin) -> "
      "<b>+ Invite</b> -> email + one or more project/role grants -> Send invite. The invite "
      "shows as <b>Invited · pending</b> with Resend/Revoke until accepted. To change anyone's "
      "roles later, <b>Roles &amp; Memberships</b> is a live grant/revoke matrix per project, plus "
      "the tenant-admin toggle (guarded — you can't demote the last admin).")
    p("<b>Step 4 (CLI, irreducible) — log in Claude Code and run your companion.</b> This is what "
      "makes phases run on your machine. In the UI, open <b>Connect Machine</b> (sidebar), pick "
      "your project, and click <b>Generate enrollment token</b> — it shows the token once, with "
      "the exact two commands below already filled in for you to paste into your terminal:")
    code("claude            # sign in to your subscription   (or: claude setup-token for headless)\n"
         "python -m runner.companion serve --api-url http://localhost:8000 \\\n"
         "    --tenant $TENANT --token <enrollment-token>      # add --repo-path/--worktrees for builds")
    p("Once the daemon checks in, Connect Machine (and the sidebar) shows <b>Connected</b>.")
    callout("How a gate or a question is handled (the same in every scenario)",
            "When a run reaches a human gate it appears on the <b>Gates</b> screen — Approve "
            "(project-admin/tenant-admin can approve any gate; otherwise you must hold that gate's "
            "role). If an agent needs information it posts a question on the "
            "<b>Clarifications</b> screen and the run shows a <b>“needs answer”</b> badge; answer "
            "it and the run continues at no extra cost.")

    h2("5.2 Scenario 1 — Greenfield, NO external integrations")
    p("Prove the full <b>planning/doc lifecycle</b> with everything kept internal — no Confluence/"
      "Jira/Figma/Xray. Artifacts publish to the platform's internal store (bodies in MinIO). "
      "Every step below is a click in the browser.")
    bullets([
        "<b>Create Project</b> (<tt>/projects/new</tt>): name it, Track <b>Greenfield</b>, Save. "
        "You're auto-granted project-admin on it (5.1 Step 2), and it becomes your selected "
        "project. Then <b>Connect Machine</b> (5.1 Step 4) so phases have somewhere to run.",
        "<b>Project Profile</b> (<tt>/profile</tt>): fill description, tech stack, important "
        "context; Save.",
        "<b>Work Items</b> (<tt>/work-items</tt>): <b>+ New Work Item</b> -> title, type Epic -> "
        "Create. You land on its detail page with the full lifecycle rail.",
        "<b>Phases &amp; Runs</b> (<tt>/runs</tt>): select the work item, trigger phases in order: "
        "<b>Ideation -> Requirements -> PRD -> Architecture</b> (and 05/06 if you wish). Each runs "
        "on your companion.",
        "<b>Clarifications</b> (<tt>/clarifications</tt>): if a run shows “needs answer”, answer "
        "it -> the run resumes in the same session.",
        "<b>Gates</b> (<tt>/gates</tt>): approve each phase's gate -> the run completes and its "
        "artifact flips <tt>draft -> published</tt>.",
        "<b>Artifacts &amp; Traceability</b> (<tt>/artifacts</tt>, <tt>/traceability</tt>): see "
        "each artifact (body in the MinIO console :9001) and the lineage graph (<tt>derives</tt> "
        "edges) — all <tt>sor=internal</tt>.",
    ])
    callout("Scenario 1 proof",
            "A greenfield project went idea -> requirements -> PRD -> architecture entirely on "
            "your local Claude Code, each phase human-gated, every artifact published internally "
            "with full lineage — <b>zero external accounts</b>, and every step above was a click, "
            "not a shell command. (The build/merge + live-SoR phases are Scenario 2.)", ok=True)

    h2("5.3 Scenario 2 — Greenfield, WITH external integrations")
    p("Same lifecycle as Scenario 1, but real systems of record: PRD -> Confluence, backlog -> "
      "Jira, UX from live Figma, build -> a GitHub PR, tests -> Xray. Put the credentials in "
      "<tt>.env</tt> first (Section 4.2 — the connect form below still needs somewhere to source "
      "tokens/URLs from), then <b>attach each connector to YOUR project from the browser</b>:")
    bullets([
        "<b>Integrations</b> (sidebar, under Project): a card per capability (Docs, Task Tracker, "
        "Code Host, Design Source, Test Mgmt), each showing <b>Not connected</b>.",
        "Click a card -> <b>Connect a capability</b> (<tt>/integrations/&lt;capability&gt;</tt>): "
        "pick the vendor, fill its binding fields (e.g. Confluence's space key, Jira's project "
        "key, GitHub's repo) and the secret (API token/PAT), <b>Test connection</b>, then Save.",
        "Repeat per capability you want live: Docs -> Confluence, Task Tracker -> Jira, "
        "Code Host -> GitHub, Design Source -> Figma, Test Mgmt -> Xray. The Integrations grid "
        "now shows each as <b>Connected</b>.",
    ])
    p("Now run the lifecycle exactly as Scenario 1 (Phases &amp; Runs + Clarifications + Gates). "
      "The same two moves per phase — <b>trigger</b>, then <b>approve</b> — now also write to the "
      "live tools. Per-phase agent keys, gate roles, and the live proof:")
    table([
        ["Phase — <tt>agent_key</tt>", "Gate role", "Live proof on approval"],
        ["PRD — <tt>03_prd</tt>", "product_owner", "A <b>Confluence page</b> is created; the "
         "artifact's <tt>external_ref.url</tt> + the Traceability node deep-link to it."],
        ["UX Design — <tt>05_ux_design</tt>", "designer", "Reads your <b>live Figma</b> tokens/"
         "components; the <b>WCAG gate</b> blocks approval until every required criterion is ticked."],
        ["Task Breakdown — <tt>06_task_breakdown</tt>", "tech_lead", "<b>Epics/stories appear in "
         "Jira</b>; child WorkItems + story-&gt;requirement trace links are created."],
        ["Implementation — <tt>07_implementation</tt>", "tech_lead", "Runs on your companion "
         "worktree -> a <b>draft PR opens on GitHub</b> (start the companion with "
         "<tt>--repo-path/--worktrees</tt>)."],
        ["Code Review — <tt>08_code_review</tt>", "reviewer", "Runs on your companion; findings "
         "become child WorkItems; the 07&lt;-&gt;08 loop re-runs until clean."],
        ["Testing — <tt>09_testing</tt>", "qa_lead", "<b>Authors the test plan and test cases</b> "
         "(planning only; a reviewer exports accepted cases to Xray). <b>Test Automation "
         "(<tt>09b</tt>)</b> then runs the tests, imports results to Xray, and a failing test opens "
         "a linked, traced defect that closes on a clean re-run."],
        ["Merge", "reviewer", "Approve the merge gate -> the <b>GitHub PR merges</b>; the "
         "WorkItem moves to <tt>done</tt>."],
    ], [5.6 * cm, 2.8 * cm, 8.0 * cm])
    callout("Scenario 2 proof",
            "The same greenfield run now produced a <b>Confluence PRD</b>, a <b>Jira backlog</b>, "
            "<b>UX from live Figma</b> behind a WCAG gate, a <b>merged GitHub PR</b>, and <b>Xray "
            "tests with a linked defect</b> — each gated, each on your local Claude Code.", ok=True)

    h2("5.4 Scenario 3 — Brownfield, uploaded resources only (no external tools)")
    p("Onboard an existing project using only what you <b>upload</b> — no Confluence/Jira. The "
      "platform assesses what exists and tells you which phase to resume. Brownfield onboarding "
      "services have no dedicated UI yet, so the onboarding steps are API/shell; gates are "
      "approved in the UI. <b>Test onboarding at different stages</b> by varying what you provide:")
    bullets([
        "<b>(API) Create the brownfield project</b> + grant roles + enroll/serve the companion "
        "(5.1): <tt>curl -s $H -X POST $API/projects/ -d '{\"name\":\"Legacy Shop\","
        "\"track\":\"brownfield\"}'</tt>.",
        "<b>(API) Upload static resources:</b> <tt>curl -s -H \"X-Tenant-ID:$TENANT\" -F "
        "file=@./old-spec.docx $API/projects/$PROJECT/source-documents/</tt> (repeat for .xlsx/"
        ".pdf). Each is extracted into reviewable draft artifacts.",
        "<b>(UI) Adopt them behind a gate:</b> approve adoption — or "
        "<tt>POST /source-documents/{id}/adopt/ {\"user_id\":\"$USER\"}</tt>.",
        "<b>(shell) Optional code intelligence</b> on a local clone (built-in analyzer; the "
        "platform stores the analysis + index, never your source): run "
        "<tt>BuiltinCodeIntel().index(workspace=...)</tt> + <tt>tools.register_artifact(...)</tt> "
        "(see the snippet in 5.5).",
        "<b>(shell) Gap report -> resume phase:</b> <tt>build_gap_report(tenant_id=$TENANT,"
        "project_id=$PROJECT)</tt> returns <tt>resume_phase</tt> + the blocking gaps.",
        "<b>(UI) Resume mid-pipeline:</b> trigger the phase it named (e.g. <tt>04_architecture</tt>) "
        "on a WorkItem and approve its gate — onboarding hands straight into the normal pipeline.",
    ])
    callout("Onboarding at different stages — vary the inputs",
            "<b>Empty</b> (upload nothing) -> the gap report resumes at <tt>ideation</tt>. "
            "<b>Partial</b> (upload a requirements doc only) -> it resumes at <tt>prd</tt>/"
            "<tt>architecture</tt>. <b>Mature</b> (docs + code intelligence) -> it assesses "
            "implementation/testing as present and resumes later. Run the gap report after each "
            "upload to watch the resume point move.")

    h2("5.5 Scenario 4 — Brownfield, WITH external tools")
    p("As Scenario 3, plus live tools: register the project's <b>existing</b> Confluence/Jira "
      "(register-don't-recreate — no duplicates), and exercise the multi-repo API-contract + "
      "live drift gate. Attach connectors to your tenant (5.3 snippet) first.")
    code("# 1) (shell) register repos (multi-repo) + (API) register existing Confluence/Jira\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from apps.projects.repos import add_repository as A;\\\n"
         "A(tenant_id='$TENANT',project_id='$PROJECT',name='owner/web',role='frontend');\\\n"
         "A(tenant_id='$TENANT',project_id='$PROJECT',name='owner/api',role='backend')\"\n"
         "curl -s $H -X POST $API/projects/$PROJECT/onboard-atlassian/   # existing items, deduped\n\n"
         "# 2) (shell) code intel on a clone -> gap report -> versioned API contract (read-through)\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from integrations.onboarding import build_gap_report;\\\n"
         "from integrations.api_contract import export_api_contract, read_api_contract;\\\n"
         "print('RESUME ->', build_gap_report(tenant_id='$TENANT',project_id='$PROJECT')"
         "['resume_phase']);\\\n"
         "c=export_api_contract(tenant_id='$TENANT',project_id='$PROJECT',body='GET /users',"
         "source_commit='abc123'); print('contract', c['semver'])\"")
    code("# 3) (shell) breaking contract change -> drift gate with cross-repo impact -> architect decides\n"
         "docker compose exec backend python manage.py shell -c \"\\\n"
         "from integrations.api_contract import export_api_contract;\\\n"
         "from integrations.drift import detect_contract_drift, decide_drift;\\\n"
         "b=export_api_contract(tenant_id='$TENANT',project_id='$PROJECT',"
         "body='GET /users (v2)',change='major');\\\n"
         "d=detect_contract_drift(tenant_id='$TENANT',contract_artifact_id=b['artifact_id'],"
         "new_semver='2.0.0');\\\n"
         "print('impacted ->', d['impacted']);\\\n"
         "print(decide_drift(tenant_id='$TENANT',drift_id=d['drift_id'],user_id='$USER',"
         "decision='accept'))\"\n"
         "#   live alternative: push to the provider repo so the signed GitHub webhook opens the drift gate")
    p("<b>(UI) Resume mid-pipeline</b> at the gap-report phase and continue exactly as Scenario 2 "
      "(phases run on your companion; PRD/backlog/PR/tests hit the live tools).")
    callout("Scenario 4 proof",
            "An existing multi-repo project was onboarded with its real Confluence/Jira "
            "registered (no duplicates) and its code indexed, produced a <b>gap report + resume "
            "phase</b>, exported a <b>versioned API contract read across repos</b>, and a "
            "<b>breaking change opened a drift gate</b> whose impact spanned both repos.", ok=True)

    h2("5.6 Scenario 5 — Interactive clarifications &amp; offline takeover (cross-cutting)")
    p("These prove the two Phase-4.5 guarantees directly and apply on top of any scenario above. "
      "Everything except stopping/restarting the companion itself is a click.")
    bullets([
        "<b>Zero-cost clarification (UI):</b> trigger any phase; if the agent asks, the "
        "Clarifications nav item shows a <b>“needs answer”</b> badge and the run sits idle (your "
        "<tt>claude</tt> is not generating, so nothing is billed). Open <b>Clarifications</b>, "
        "answer -> the run resumes in the same session.",
        "<b>Durability (no re-ask):</b> stop the companion (<tt>Ctrl-C</tt>) while a clarification "
        "is answered but the phase hasn't reported, then re-trigger the phase from <b>Phases &amp; "
        "Runs</b> — the agent reuses your earlier answer (folded into its manifest) instead of "
        "asking again.",
        "<b>Offline takeover:</b> stop the companion, trigger a phase, and leave it; after the "
        "report timeout the run parks the WorkItem for <b>human takeover</b> (visible on the "
        "<b>Offline Takeover</b> screen — Run status <tt>failed</tt> + a takeover flag) rather "
        "than hanging — restart the companion, or take it over by hand, to resume.",
        "<b>Local engine, not the API (verify):</b> the companion log shows it dropped "
        "<tt>ANTHROPIC_API_KEY</tt> and used <tt>claude</tt> on PATH; usage shows on your Claude "
        "subscription, not an API bill. Connect Machine shows <b>Connected</b> while it's up.",
    ])

    h2("5.7 If something stalls")
    p("Almost always it is the environment, not the platform. Quick checks:")
    bullets([
        "<b>Infra down:</b> a “Socket is not connected” on :5433 means Docker Desktop stopped — "
        "start it and <tt>docker compose up -d</tt> again.",
        "<b>Migrations:</b> if <tt>make migrate</tt> errors on an ALTER, run it with the "
        "<tt>postgres</tt> superuser DSN (Section 4.4).",
        "<b>Login/signup fails with correct credentials:</b> a stale local database is missing the "
        "RLS-auth-bootstrap migration — see the Section 4.4 gotcha and ADR 0002.",
        "<b>Phase never runs / stays pending:</b> your <b>companion isn't running</b> or isn't "
        "enrolled for this project — check <b>Connect Machine</b> shows <b>Connected</b>, that "
        "<tt>serve</tt> is up in your terminal, and that <tt>claude</tt> is logged in on that "
        "machine.",
        "<b>Live SoR step does nothing:</b> the connector isn't attached to <i>your</i> project — "
        "check <b>Integrations</b> shows it <b>Connected</b> (5.3) — or the creds aren't in "
        "<tt>.env</tt>; restart <tt>make dev</tt> after editing <tt>.env</tt>.",
        "<b>Gate won't approve (403):</b> you don't hold that gate's role on the project and "
        "aren't a project-/tenant-admin — grant the role via <b>Roles &amp; Memberships</b> (5.1 "
        "Step 3).",
        "<b>Full automated proof anytime:</b> <tt>cd backend &amp;&amp; pytest -q</tt> — including "
        "<tt>tests/test_acceptance_phase47.py</tt> (the full from-scratch REST spine: signup -> "
        "invite -> roles -> connect -> trigger -> clarify -> gate -> preview) and "
        "<tt>tests/test_acceptance_phase4.py</tt> (brownfield/multi-repo).",
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
