"""Generate the AI-First SDLC Platform - QA Team Testing Guide (PDF).

Audience: two QA testers joining the team who will take over end-to-end testing.
They are NOT strong on dev tooling, so this is written in plain language, but it is
100%% accurate to the CURRENT code (audited 2026-07-22), not older docs.

Pure ReportLab (Platypus). Glyph-safe for built-in Helvetica/Courier (WinAnsi):
arrows are written "->", no emoji/checkmarks; use <b>/<i>/<tt> and &amp; &lt; &gt;.

Run from the repository root:  .venv/Scripts/python docs/build_qa_testing_guide.py
Out:  docs/AI-First-SDLC-Platform-QA-Testing-Guide.pdf
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
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

OUT = Path(__file__).resolve().parent / "AI-First-SDLC-Platform-QA-Testing-Guide.pdf"

# palette ------------------------------------------------------------
NAVY = colors.HexColor("#1e3a5f")
BLUE = colors.HexColor("#2563eb")
LIGHT = colors.HexColor("#eef2f7")
CODEBG = colors.HexColor("#f5f6f8")
NOTEBG = colors.HexColor("#fff8e6")
NOTEBORDER = colors.HexColor("#f59e0b")
OKBG = colors.HexColor("#eaf6ec")
OKBORDER = colors.HexColor("#3a9d54")
STEPBG = colors.HexColor("#eef4ff")
STEPBORDER = colors.HexColor("#2563eb")
GREY = colors.HexColor("#475569")
RULE = colors.HexColor("#cbd5e1")

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
STEP = _style("Step", parent=BODY, fontSize=10, leading=15, spaceAfter=4)
TOC_TITLE = _style("TocTitle", parent=H1, spaceAfter=12)

story: list = []


# helpers ------------------------------------------------------------
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


def numbered(items):
    flow = [ListItem(Paragraph(t, STEP), leftIndent=16) for t in items]
    story.append(ListFlowable(flow, bulletType="1", leftIndent=14))
    gap(6)


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


def callout(label, text, kind="note"):
    if kind == "ok":
        bg, border, lc = OKBG, OKBORDER, NAVY
    elif kind == "step":
        bg, border, lc = STEPBG, STEPBORDER, NAVY
    else:
        bg, border, lc = NOTEBG, NOTEBORDER, colors.HexColor("#92400e")
    inner = [Paragraph(f"<b>{label}</b>", _style("nl", parent=BODY, spaceAfter=2, textColor=lc)),
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


# ====================================================================
# COVER
# ====================================================================
def cover():
    story.append(Spacer(1, 3.2 * cm))
    rule = Table([[""]], colWidths=[16.4 * cm], rowHeights=[3])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE)]))
    story.append(Paragraph("QA TESTING GUIDE",
                           _style("cover1", fontName="Helvetica-Bold", fontSize=30, leading=34,
                                  textColor=NAVY, alignment=TA_LEFT)))
    gap(6)
    story.append(rule)
    gap(14)
    story.append(Paragraph("AI-First SDLC Platform &mdash; Set up, understand, and test the whole "
                           "application end to end",
                           _style("cover2", fontName="Helvetica", fontSize=14, leading=19,
                                  textColor=GREY)))
    gap(26)
    story.append(Paragraph(
        "A complete, plain-language handbook for the QA team. It takes you from an empty laptop to "
        "running the platform, understanding every feature, and testing each user journey from "
        "sign-up to deployment &mdash; so you can find and log issues on your own, without waiting "
        "on the development team.",
        _style("coverlead", parent=BODY, fontSize=11.5, leading=17)))
    gap(34)
    meta = [
        ["Prepared for", "The QA Testing Team &mdash; EdvenSoft"],
        ["What you will be able to do", "Install everything, create your own workspace, connect "
         "your machine, trigger every phase, and log bugs in a shared, review-ready format."],
        ["Assumed knowledge", "Comfortable using web apps and a terminal to copy-paste commands. "
         "No coding or platform-internals knowledge required &mdash; every term is explained."],
        ["Accuracy", "Audited directly against the live source code on the date below. Where an "
         "older internal doc disagrees, THIS guide is correct."],
        ["Date", date.today().strftime("%B %d, %Y")],
    ]
    t = Table([[Paragraph(k, _style("mk", parent=BODY, fontName="Helvetica-Bold",
                                    textColor=NAVY, fontSize=9.5)),
                Paragraph(v, _style("mv", parent=BODY, fontSize=9.5))] for k, v in meta],
              colWidths=[4.4 * cm, 12.0 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())


# ====================================================================
# TABLE OF CONTENTS
# ====================================================================
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


# ====================================================================
# 1. HOW TO USE THIS GUIDE
# ====================================================================
def section_1():
    h1("1. How to Use This Guide")
    lead("Read this page first. It tells you what this document is for, how the QA team fits into "
         "the project, and the one rule that makes your testing useful to the developers.")

    h2("1.1 Why you have this guide")
    p("This guide is written so you can do everything on your own: install the tools, create your "
      "own account, run the full application, and log the problems you find. You should only need "
      "to interrupt a developer for a genuinely critical blocker (and Section 12 lists the few "
      "things only they can hand you).")

    h2("1.2 What you are testing, in one line")
    p("The AI-First SDLC Platform is a web application where AI agents run a software project's "
      "whole lifecycle &mdash; from the first idea, through requirements, design, coding, testing, "
      "and security, to deployment &mdash; with a human approving every important step. Your job "
      "is to walk through all of that as a real user would and report anything that looks wrong, "
      "confusing, broken, or ugly.")

    h2("1.3 How to read it")
    bullets([
        "<b>Sections 2-4</b> explain <i>what</i> the platform is and define every word you will "
        "see on screen. Read these once to build a mental model.",
        "<b>Section 5</b> is the one-time <b>setup</b> of your laptop. Follow it top to bottom.",
        "<b>Sections 6-8</b> are the <b>reference</b>: every feature, every phase, and the exact "
        "end-to-end journeys. Keep these open while you test.",
        "<b>Section 9</b> is your <b>first smoke test</b> &mdash; a short golden path to confirm "
        "your setup works before you explore freely.",
        "<b>Sections 10-13</b> tell you what is <i>normal</i> vs. a <i>bug</i>, how to avoid "
        "stepping on each other, how to fix common setup snags yourself, and how to log a bug so "
        "the developers can act on it immediately.",
    ])

    callout("The one rule that makes your bugs useful",
            "Before you log something as a bug, check Section 10 (&ldquo;Is it a bug or is it "
            "meant to work that way?&rdquo;). Some behaviours look wrong but are deliberate design "
            "decisions (for example, a run can stop because of an AI usage limit &mdash; that is "
            "not an application bug). Logging those as defects wastes everyone's time.")


# ====================================================================
# 2. WHAT THE PLATFORM IS
# ====================================================================
def section_2():
    h1("2. What the SDLC Platform Is")
    lead("Before you can test something, you need a clear picture of what it is supposed to be. "
         "This section gives you that picture in everyday language.")

    h2("2.1 The big idea")
    p("&ldquo;SDLC&rdquo; stands for <b>Software Development Life Cycle</b> &mdash; the full "
      "journey a piece of software takes: somebody has an idea, it becomes written requirements, "
      "then a product spec, then an architecture and a design, then code, then it gets reviewed, "
      "tested, security-checked, and finally shipped. Traditionally a whole team of specialists "
      "does each step by hand.")
    p("This platform does that journey with a <b>team of AI agents</b> instead &mdash; one "
      "specialist agent per step (an &ldquo;ideation&rdquo; agent, a &ldquo;requirements&rdquo; "
      "agent, an &ldquo;architecture&rdquo; agent, and so on). But it is <b>not</b> &ldquo;an AI "
      "that writes code and hopes for the best.&rdquo; A human reviews and approves the output of "
      "every step before the project moves on. The platform's job is to keep all of this "
      "organised, safe, traceable, and repeatable.")

    h2("2.2 Who uses it and what makes it different")
    bullets([
        "It is <b>multi-tenant</b>: many separate companies (&ldquo;tenants&rdquo;) can use the "
        "same platform, and no tenant can ever see another's data. When you sign up, you create "
        "your <i>own</i> tenant &mdash; your own private workspace.",
        "It is <b>web-delivered</b>: the whole thing runs in a browser. There is one small helper "
        "program (the &ldquo;companion&rdquo;) that runs on your own laptop &mdash; more on that "
        "in Section 4.",
        "It works with a team's <b>real tools</b>: instead of inventing its own copies of your "
        "Jira, Confluence, Figma, GitHub, or Xray, it connects to the real ones and reads/writes "
        "them &mdash; but only after a human approves.",
        "It is <b>engine-agnostic</b>: the AI &ldquo;brain&rdquo; behind the agents can be swapped. "
        "Today it uses Claude; the platform is built so it could use another AI later without "
        "rewriting the agents.",
    ])

    h2("2.3 The seven house rules (why the app behaves the way it does)")
    p("The whole system obeys these locked principles. Knowing them helps you tell a real bug from "
      "intended behaviour.")
    table([
        ["#", "Rule", "What it means for you as a tester"],
        ["1", "State vs. content", "The platform stores <b>pointers and history</b> (who did what, "
         "when, which version). The actual documents live in the connected tools or a file store. "
         "So a &ldquo;PRD&rdquo; you see is a tracked pointer to a body of text, not a random file."],
        ["2", "Orchestration vs. execution", "The platform decides <i>what</i> runs and <i>when</i>. "
         "The AI only <i>does</i> the step. Approvals (&ldquo;gates&rdquo;) are always the "
         "platform's job, never the AI's."],
        ["3", "Memory = index, not copies", "It remembers <b>versions and fingerprints</b> of "
         "documents, not duplicate copies. This is how it can later flag &ldquo;this changed.&rdquo;"],
        ["4", "Work is a graph", "The unit of work is a <b>Work Item</b>. Items can depend on each "
         "other; they do not have to run in one rigid line."],
        ["5", "Every output is gated", "Draft -&gt; reviewed -&gt; approved -&gt; published. "
         "Nothing is auto-published. A human always approves before anything reaches a real tool."],
        ["6", "Strict tenant isolation", "Every record is tagged with its tenant and protected by "
         "the database. You will never see another workspace's data (if you do, that is a serious "
         "bug &mdash; log it P1)."],
        ["7", "Capabilities, not vendors", "The app thinks in <b>capabilities</b> "
         "(&ldquo;task tracker&rdquo;, &ldquo;doc store&rdquo;) and binds a vendor (Jira, "
         "Confluence) underneath. That is why the Integrations screen is organised by capability."],
    ], [0.8 * cm, 3.6 * cm, 12.0 * cm])


# ====================================================================
# 3. WHAT IT DOES FOR A USER
# ====================================================================
def section_3():
    h1("3. What the Application Does for a User")
    lead("This section is the &ldquo;menu&rdquo; of what a user can actually accomplish. Each item "
         "here becomes something you will test in detail later.")

    h2("3.1 The capabilities at a glance")
    bullets([
        "<b>Create a workspace and invite a team</b> &mdash; sign up, become the workspace admin, "
        "invite teammates, and assign each person roles (product owner, architect, QA lead, etc.).",
        "<b>Set up a project</b> &mdash; choose whether it is <b>greenfield</b> (brand new) or "
        "<b>brownfield</b> (existing code and docs), and whether it lives in <b>one repo</b> or "
        "<b>many repos</b>.",
        "<b>Connect your real tools</b> &mdash; attach Confluence, Jira, Figma, GitHub, and Xray "
        "so the platform can read and (after approval) write to them.",
        "<b>Connect your machine</b> &mdash; run the small &ldquo;companion&rdquo; so AI phases "
        "execute on your computer using your own Claude subscription.",
        "<b>Run the lifecycle</b> &mdash; trigger each phase (ideation, requirements, PRD, "
        "architecture, UX, task breakdown, implementation, testing, test automation, security, "
        "CI/CD, deployment) on a work item.",
        "<b>Stay in control</b> &mdash; answer the AI's clarifying questions, review its drafts, "
        "and approve or reject at each gate.",
        "<b>See everything</b> &mdash; a dashboard of what needs you, a full history of runs and "
        "transcripts, an artifact registry, and a traceability view linking requirements to code "
        "to tests.",
        "<b>Onboard existing projects</b> &mdash; for brownfield, ingest existing documents, index "
        "the code, and get a &ldquo;gap report&rdquo; of what is missing.",
    ])

    h2("3.2 The shape of a normal working session")
    p("Most of what you will test follows this rhythm, over and over:")
    numbered([
        "Pick or create a <b>work item</b> (a feature, story, or task).",
        "<b>Trigger a phase</b> on it (say, &ldquo;requirements&rdquo;).",
        "The AI may pause and <b>ask you clarifying questions</b> &mdash; you answer them.",
        "The AI produces a <b>draft artifact</b> (a document, a plan, code, etc.).",
        "A <b>gate</b> opens: the right role reviews the draft and <b>approves or rejects</b> it.",
        "On approval, the work item advances and (if you chose to) the result can be "
        "<b>published</b> to a real tool like Confluence or Jira.",
    ])
    callout("What you are really testing",
            "You are testing whether this rhythm is smooth, clear, and correct on every screen: do "
            "buttons work, is the wording clear, does the right thing happen, are errors handled "
            "gracefully, and does the UI look right? You do <b>not</b> need to judge whether the "
            "AI's writing is &ldquo;good&rdquo; &mdash; focus on the application around it.", "ok")


# ====================================================================
# 4. GLOSSARY
# ====================================================================
def section_4():
    h1("4. Glossary &mdash; Every Word You Will See")
    lead("The screens use a handful of special terms. Learn these ten and nothing in the app will "
         "feel foreign. Keep this page bookmarked.")
    table([
        ["Term", "Plain-language meaning"],
        ["Workspace / Tenant", "Your private company account on the platform. You create one at "
         "sign-up and become its admin. Everything you make lives inside it; no other workspace "
         "can see it."],
        ["Project", "A single software project inside your workspace. It is either "
         "<b>greenfield</b> (new) or <b>brownfield</b> (existing), and uses one or many repos."],
        ["Work Item", "The unit of work. Types you will see: <b>Epic</b> (big), <b>Story</b> "
         "(default), <b>Task</b>, <b>Defect</b> (a bug the platform raised), and <b>Test Case</b>. "
         "Each shows a friendly key like <tt>WI-14</tt>, never a raw ID."],
        ["Phase", "One step of the lifecycle done by one specialist AI agent &mdash; e.g. "
         "&ldquo;requirements&rdquo;, &ldquo;architecture&rdquo;, &ldquo;security&rdquo;. There are "
         "16 of them (Section 7)."],
        ["Run", "One execution of a phase on a work item. It has a live console and, afterwards, a "
         "full transcript and a cost record."],
        ["Artifact", "A thing a phase produces &mdash; a PRD, an architecture doc, a review, test "
         "cases, a security report. The platform tracks its version and fingerprint."],
        ["Gate (Approval)", "The human checkpoint after a phase. The right <b>role</b> reviews the "
         "draft, ticks any required criteria, and approves or rejects. Nothing moves on without it."],
        ["Clarification", "A question the AI asks you mid-run when it needs a decision. While it "
         "waits, nothing is being generated, so it costs nothing. You answer and the run resumes."],
        ["Companion (Runner)", "A small program you run on your own laptop. It lets AI phases "
         "execute on your machine using <b>your own Claude subscription</b> instead of a shared "
         "bill. The app shows &ldquo;Companion: Ready&rdquo; when it is running."],
        ["Integration / Capability", "A connection to a real external tool. The app groups them by "
         "<b>capability</b> (doc store, task tracker, code host, design source, test management, "
         "code intelligence) and binds a vendor (Confluence, Jira, GitHub, Figma, Xray) underneath. "
         "Code intelligence is built in and set up automatically, so it has no card to connect."],
        ["System of Record (SoR)", "The real external tool that officially owns a piece of content "
         "&mdash; e.g. Jira owns issues, Confluence owns pages. The platform publishes to the SoR "
         "only after a gate is approved."],
        ["Greenfield / Brownfield", "<b>Greenfield</b> = a brand-new project starting from an idea. "
         "<b>Brownfield</b> = an existing project with code and docs the platform must first "
         "ingest and understand."],
    ], [3.3 * cm, 13.1 * cm])


# ====================================================================
# 5. SETTING UP YOUR MACHINE
# ====================================================================
def section_5():
    h1("5. Setting Up Your Machine (one time)")
    lead("Do this once, carefully, top to bottom. At the end you will have the whole application "
         "running on your laptop and connected to the team's shared cloud. Budget about an hour "
         "the first time.")

    callout("The setup model, in one picture",
            "You do <b>not</b> install a database or the cloud services. Those live once in the "
            "team's shared AWS (Postgres + Temporal + S3). You only run the <b>app</b> on your "
            "laptop (backend, worker, frontend) pointed at that shared cloud, plus the "
            "<b>companion</b>. This is exactly how the two developers already work &mdash; you are "
            "joining the same shared brain.", "step")

    h2("5.1 What to install (with versions)")
    p("Install these five things first. The versions are what the project is built and tested "
      "against &mdash; using much older versions is the most common cause of setup pain.")
    table([
        ["Tool", "Version", "Why you need it", "Where to get it"],
        ["Docker Desktop", "Latest stable (4.x)", "Runs the app services (backend, worker, "
         "frontend) in containers so you don't hand-install Python/Node for the app.",
         "docker.com/products/docker-desktop"],
        ["Git", "Latest 2.x", "To clone the project code and for the companion to work with "
         "repos.", "git-scm.com"],
        ["Python", "3.12.x", "To run the <b>companion</b> on your laptop.", "python.org/downloads"],
        ["Node.js", "20 LTS or newer", "Needed to install the Claude Code CLI (below).",
         "nodejs.org"],
        ["Claude Code CLI", "Latest", "The AI engine the companion drives. You log into it with "
         "your own Claude subscription.", "npm i -g @anthropic-ai/claude-code"],
    ], [3.0 * cm, 2.6 * cm, 6.6 * cm, 4.2 * cm], font=8.3)

    callout("The two things only the dev team can give you",
            "Almost everything here you do yourself. The exception is a handful of <b>shared "
            "secrets</b> you cannot invent: (1) the shared database connection string and password, "
            "the shared Temporal address, and the shared file-store (S3) keys and bucket &mdash; "
            "these go into your <tt>.env</tt> file in Step 3; and (2) confirmation of your own "
            "Claude subscription login. Ask a developer for the filled-in <tt>.env</tt> values once; "
            "everything else in this guide you can do without them.")

    h2("5.2 Step 1 &mdash; Get the code")
    p("Open a terminal, go to the folder where you keep projects, and clone the repository (ask a "
      "developer for the exact repository URL if you don't have it):")
    code("git clone <the-repository-url> AI-First-SDLC-App\n"
         "cd AI-First-SDLC-App")

    h2("5.3 Step 2 &mdash; Log the Claude Code CLI into your own subscription")
    p("The companion runs AI phases using <b>your</b> Claude login, never a shared API key (the "
      "companion actually refuses to start if it detects an API key). Log in once:")
    code("claude       # then follow the prompt to sign in with your Claude account")
    p("Verify it worked by typing <tt>claude</tt> again &mdash; it should open without asking you "
      "to log in. Keep this account handy; each tester uses their own.")

    h2("5.4 Step 3 &mdash; Create your <tt>.env</tt> settings file")
    p("The project reads all its settings from a single file called <tt>.env</tt> in the project "
      "root. Copy the template and then fill in the shared values from the dev team:")
    code("cp .env.example .env      # (Windows PowerShell: copy .env.example .env)")
    p("Open <tt>.env</tt> in a text editor and set these to the <b>shared cloud</b> values the dev "
      "team gives you (leave the rest at their defaults for now):")
    table([
        ["Setting in .env", "What to put"],
        ["DATABASE_URL", "The shared AWS Postgres connection string (the <tt>sdlc_app</tt> role "
         "&mdash; the everyday, non-admin one). Example shape: "
         "<tt>postgres://sdlc_app:&lt;password&gt;@&lt;aws-host&gt;:5432/sdlc_platform</tt>"],
        ["TEMPORAL_HOST", "The shared Temporal address, e.g. <tt>&lt;aws-host&gt;:7233</tt>."],
        ["S3_ENDPOINT_URL / S3_BUCKET / S3_ACCESS_KEY / S3_SECRET_KEY / S3_REGION",
         "The shared file-store values. For real AWS S3, <tt>S3_ENDPOINT_URL</tt> is left empty."],
        ["CORS_ALLOWED_ORIGINS", "Leave as <tt>http://localhost:5173</tt> (that is your local "
         "frontend)."],
        ["ANTHROPIC_API_KEY", "You can leave the placeholder. Phases run through your companion "
         "(your Claude login), so a key is not needed for normal testing."],
    ], [5.6 * cm, 10.8 * cm], font=8.4)
    callout("Keep .env private",
            "Your <tt>.env</tt> holds real shared passwords. It is already excluded from Git &mdash; "
            "never paste its contents into a chat, screenshot, or bug report.")

    h2("5.5 Step 4 &mdash; Start the application")
    p("You do <b>not</b> start a local database. You start only the three app services and tell "
      "Docker <i>not</i> to spin up its own local infra (that is what <tt>--no-deps</tt> does), so "
      "everything points at the shared cloud:")
    code("docker compose --profile app up --no-deps backend worker frontend")
    p("The first run downloads and builds images, so give it a few minutes. When it settles, open "
      "your browser to:")
    code("http://localhost:5173")
    p("You should see the platform's <b>Log in</b> screen. If you do, your app is running. If not, "
      "jump to Section 12 (Troubleshooting) &mdash; it is almost always the <tt>.env</tt> values "
      "or Docker not being started.")

    h2("5.6 Step 5 &mdash; Create your own workspace")
    p("You are a brand-new user, so you make your own account (you do <b>not</b> reuse the "
      "developers' data):")
    numbered([
        "On the Log in screen, click <b>&ldquo;New to Edvensoft? Create a workspace.&rdquo;</b>",
        "On <b>Sign up</b>, enter your <b>Full name</b>, <b>Work email</b>, a <b>Password</b>, and "
        "a <b>Workspace / org name</b> (e.g. &ldquo;QA Sandbox &mdash; Priya&rdquo;). Click "
        "<b>Create workspace</b>.",
        "You become the <b>admin</b> of your new workspace. Click <b>Continue</b> to reach the "
        "<b>Setup checklist</b>.",
    ])
    callout("Give yourself a clearly-named workspace",
            "Since several people share the same cloud, name your workspace so it is obviously "
            "yours (your name + &ldquo;QA&rdquo;). This makes it easy to tell your test data apart "
            "and is important for testing in parallel (Section 11).", "ok")

    h2("5.7 Step 6 &mdash; Connect your machine (the companion)")
    p("The last setup piece lets AI phases actually run. The app walks you through it:")
    numbered([
        "From the Setup checklist (or the sidebar) open <b>Connect Machine</b>.",
        "Click <b>Generate enrollment token</b> and copy the one-time token it shows (it is shown "
        "only once).",
        "The screen shows you the exact command to run, already filled in with your workspace and "
        "token. Open a <b>second terminal</b>, go to the project folder, and run it (shape below).",
    ])
    p("The command looks like this &mdash; the app fills in the real values for you:")
    code("python -m runner.companion serve \\\n"
         "  --api-url http://localhost:8000 \\\n"
         "  --tenant <your-workspace-id> \\\n"
         "  --token <the-enrollment-token> \\\n"
         "  --worktrees C:\\path\\to\\sdlc-worktrees \\\n"
         "  --repo-path C:\\path\\to\\a-cloned-repo")
    p("Leave that terminal running. Back in the browser, the <b>Companion</b> pill in the top bar "
      "should switch to <b>&ldquo;Ready&rdquo;</b>. You are now fully set up. Section 8 explains "
      "the companion's options in detail (single-repo vs multi-repo, and when the "
      "<tt>--worktrees</tt> / <tt>--repo</tt> flags matter).")

    callout("First-time companion notes",
            "The companion needs the <tt>claude</tt> CLI logged in (Step 2) or it refuses to "
            "start with a clear &ldquo;CANNOT START&rdquo; message. For build and security phases "
            "it also needs a real cloned repo and the <tt>--worktrees</tt> folder &mdash; for "
            "pure planning phases (ideation, requirements, etc.) it does not.")


# ====================================================================
# 6. THE FEATURES YOU WILL TEST
# ====================================================================
def section_6():
    h1("6. The Features You Will Test (screen by screen)")
    lead("This is your reference map of the whole application. Each entry says what the screen is "
         "for and what to check. The left sidebar groups the screens; we follow that order.")

    h2("6.1 Signing in and onboarding")
    bullets([
        "<b>Sign up</b> (create workspace) &mdash; fields Full name, Work email, Password, "
        "Workspace/org name. Check validation (bad email, weak/blank password, duplicate email is "
        "rejected), the success state, and that <b>Continue</b> leads to the Setup checklist.",
        "<b>Log in</b> &mdash; Work email + Password. Check wrong-password handling and the "
        "account-locked state after several failed tries (you should see a clear message, not a "
        "raw error).",
        "<b>Forgot password / Reset</b> &mdash; request a reset, the &ldquo;check your email&rdquo; "
        "state, setting a new password, and the &ldquo;invalid/expired link&rdquo; state.",
        "<b>Accept invite</b> &mdash; if a teammate invites you, the link opens a join screen with "
        "your email pre-filled; you set a name and password to join their workspace. Test the "
        "expired-link path too.",
        "<b>Setup checklist</b> &mdash; the four guided steps (create project, connect machine, "
        "invite team, connect integrations). Check each link goes to the right place and the "
        "checklist reflects what you have done.",
    ])

    h2("6.2 Setting up a project")
    bullets([
        "<b>Create a project</b> &mdash; name it, choose <b>greenfield</b> or <b>brownfield</b>, "
        "and <b>single</b> or <b>multi</b>-repo. Greenfield sends you to the Project Profile; "
        "brownfield sends you to the Onboarding hub. Test all four combinations.",
        "<b>Project Profile</b> &mdash; the important context that guides the AI (what the project "
        "is, constraints, etc.). Check editing, saving, and that required context is enforced: "
        "<b>Description is required</b> &mdash; Save with it empty should say why, put the cursor "
        "there, and keep everything else you typed.",
        "<b>Integrations</b> &mdash; the five capabilities you connect (doc store, task tracker, "
        "design source, code host, test management). Each shows Connected / Not connected / "
        "Failed. Code intelligence has no card: it is set up automatically. See 6.3.",
        "<b>Repositories</b> &mdash; add and assign the code repo(s) for the project, mark a "
        "default with <b>Set default</b> (the default marker should move to that row), and "
        "(multi-repo) pin work items to a repo.",
        "<b>Connect Machine</b> &mdash; covered in setup (5.7); also test the <b>Disconnect</b> "
        "flow and the offline state.",
    ])

    h2("6.3 Connecting real tools (Integrations)")
    p("Integrations are organised by <b>capability</b>; each capability binds one vendor. All five "
      "below are wired to real APIs, so a wrong token should <b>fail the connection test</b> with "
      "a clear message. (Code intelligence is built in and set up automatically for every "
      "workspace, so it is not on this screen; an old link to it should return to the grid.)")
    table([
        ["Capability", "Vendor", "What you enter", "What to test"],
        ["Documentation store", "Confluence", "Space key, base URL, email + API token",
         "Connect, edit, disconnect; a bad token fails the test; secrets are never shown back."],
        ["Task tracker", "Jira", "Project key, base URL, email + API token",
         "Same as above; used later for publishing issues."],
        ["Design source", "Figma", "File key + access token", "Connect + test; read-only use."],
        ["Code host", "GitHub", "Repo (optional) + access token (repo scope)",
         "Connect; used by build phases to open PRs."],
        ["Test management", "Xray", "Project key + client id + client secret",
         "Connect + test; used to import test results."],
    ], [3.4 * cm, 2.0 * cm, 5.4 * cm, 5.6 * cm], font=8.2)
    callout("Good things to try to break here",
            "Enter a clearly wrong token and confirm the <b>Test</b> step fails with a helpful "
            "message (not a stack trace). Try connecting the same capability twice (should say "
            "&ldquo;already connected&rdquo;). Confirm that after saving, the secret is never "
            "displayed again &mdash; only an &ldquo;is configured&rdquo; indicator.")

    h2("6.4 Work Items")
    bullets([
        "<b>Work Items board</b> &mdash; columns are <b>Backlog</b> (nothing has run yet) followed "
        "by the lifecycle phases; the Tasks view is Backlog, Implementation, Review. Each card has "
        "a status pill: Not started, Running, <b>Waiting for you</b> (only when you may decide the "
        "gate or answer the question &mdash; otherwise a grey &ldquo;Waiting for review / for an "
        "answer&rdquo;), Done, Failed. Test creating each type and opening a card.",
        "<b>Work Item detail</b> &mdash; the view changes by type: <b>Epic</b>, <b>Task / Test "
        "case</b>, and <b>Defect</b> each render differently. Check the phases list and the "
        "<b>trigger</b> action.",
        "<b>Task breakdown</b> &mdash; review and accept the AI-generated breakdown of a work item "
        "into smaller pieces.",
        "<b>Test cases</b> &mdash; view and manage the generated test cases for a work item.",
    ])

    h2("6.5 Phases &amp; Runs")
    bullets([
        "<b>Phases &amp; Runs</b> &mdash; pick a work item, see the full phase catalog, and "
        "<b>trigger a phase</b>. If your companion is offline, this screen blocks triggering and "
        "shows an offline state (that is correct behaviour, not a bug).",
        "<b>Run console</b> &mdash; the live output of a running phase. Watch it stream, and check "
        "it reflects success, failure, and &ldquo;waiting for a clarification&rdquo; clearly.",
        "<b>Run transcripts</b> &mdash; the full history of a finished run, for later reading.",
    ])

    h2("6.6 Clarifications and Gates (staying in control)")
    bullets([
        "<b>Clarifications</b> &mdash; questions the AI asks, grouped in three tiers (Tier 1 "
        "must-answer, Tier 2 suggested, Tier 3 inferred defaults). Answering unblocks the run. "
        "Check the count badge in the sidebar and the notification bell update.",
        "<b>Gates</b> &mdash; approve or reject a phase's output. There are Pending and History "
        "tabs. Only a user holding the gate's <b>role</b> (or an admin) can decide &mdash; others "
        "should be blocked with a clear message.",
        "<b>Gate criteria checklist</b> &mdash; some gates require you to tick criteria before you "
        "can approve. Some criteria are computed by the platform and cannot be forced. Confirm "
        "&ldquo;Approve&rdquo; stays disabled until required criteria are met.",
    ])

    h2("6.7 Seeing everything (observability)")
    bullets([
        "<b>Workspace Dashboard</b> &mdash; the &ldquo;needs me&rdquo; rollup: gates awaiting you, "
        "clarifications, your runs, project health. It is <b>personal</b>: it counts only gates you "
        "may decide and questions you may answer (&ldquo;N waiting on you&rdquo;), each row names "
        "its work item by number and title, and a run row says how long it has been going. "
        "&ldquo;Published this week&rdquo; counts by publish date. Check it updates as you work.",
        "<b>Artifacts</b> &mdash; browse everything the phases produced; open one to preview the "
        "rendered content and its version.",
        "<b>Publish to system of record</b> &mdash; from an artifact, export it to a connected "
        "tool (e.g. Confluence). This is <b>user-triggered</b> and only works after the gate is "
        "approved and the integration is connected.",
        "<b>Traceability</b> &mdash; the links between requirements, artifacts, work items, and "
        "tests. Check the links are correct and clickable, and try the filters: Phase, Type, and "
        "Highlight work item (the rest of the map dims; onboarding documents are under "
        "&ldquo;Not tied to a work item&rdquo;).",
        "<b>Run transcripts</b>, <b>API Contracts &amp; Drift</b>, and <b>Run recovery</b> (take "
        "over a run whose companion went offline mid-phase).",
    ])

    h2("6.8 Brownfield onboarding")
    bullets([
        "<b>Onboarding hub</b> &mdash; for existing projects: connect sources, extract and index "
        "existing docs, and run a gap report.",
        "<b>Source documents</b> &mdash; review what was ingested.",
        "<b>Gap report</b> &mdash; see what is missing versus what a healthy project should have.",
    ])

    h2("6.9 Admin (workspace admins only)")
    bullets([
        "<b>Users &amp; invitations</b> &mdash; invite teammates and manage members.",
        "<b>Roles &amp; memberships</b> &mdash; assign each person roles per project (this decides "
        "who can approve which gates).",
        "<b>Test reporting</b> &mdash; CI test-result reporting and tokens (admin only).",
        "Non-admins should be politely blocked from all of the above &mdash; confirm that.",
    ])


# ====================================================================
# 7. THE PHASE CATALOG
# ====================================================================
def section_7():
    h1("7. The Phase Catalog (the 16 lifecycle steps)")
    lead("Each phase is one specialist AI agent. This table is the current, complete catalog. Most "
         "phases are &ldquo;planning&rdquo; phases that produce a document and stop at a gate. A few "
         "are &ldquo;build&rdquo; phases that actually change code. One reads your code without "
         "changing it.")

    table([
        ["#", "Phase (trigger)", "What it produces", "Reviewer role", "Kind"],
        ["1", "Ideation (ideate)", "The initial idea shaped into a starting point", "Product owner",
         "Planning"],
        ["2", "Requirements (requirements)", "Structured requirements", "Product owner", "Planning"],
        ["3", "PRD (prd)", "Product requirements document", "Product owner", "Planning"],
        ["4", "Architecture (architecture)", "Technical architecture", "Architect", "Planning"],
        ["5", "UX Design (ux-design)", "UX/design direction", "Designer", "Planning"],
        ["6", "Task Breakdown (task-breakdown)", "Work broken into buildable tasks", "Tech lead",
         "Planning"],
        ["7", "Implementation (implement)", "Actual code, via a branch and pull request", "Tech "
         "lead", "<b>Build</b>"],
        ["8", "Code Review (code-review)", "Review of the code (runs <i>inside</i> the build)",
         "Reviewer", "Auto (in build)"],
        ["9", "Testing (test)", "Test plan and test cases", "QA lead", "Planning"],
        ["10", "Test Automation (test-automation)", "Automated test scripts + imported results",
         "QA lead", "<b>Build</b>"],
        ["11", "Security (security)", "Threat model, SBOM, security review + findings",
         "Security engineer", "Scan (reads code)"],
        ["12", "CI/CD (cicd)", "Pipeline configuration", "DevOps", "<b>Build</b>"],
        ["13", "Deployment (deploy)", "Deployment step", "DevOps", "Planning"],
        ["14", "Onboarding (onboard)", "Sets up an existing project", "Product owner", "Planning"],
        ["15", "Context Bridge (context-bridge)", "Bridges existing context", "Architect",
         "Planning"],
        ["16", "Context Extractor (analyze)", "Extracts intelligence from existing code",
         "Tech lead", "Planning"],
    ], [0.7 * cm, 4.5 * cm, 5.4 * cm, 2.9 * cm, 2.9 * cm], font=8.0)

    h2("7.1 The three kinds of phase, in plain terms")
    bullets([
        "<b>Planning phase</b> &mdash; the AI thinks and writes a document. It never touches code. "
        "It produces a draft and stops at a human gate. Most phases are these.",
        "<b>Build phase</b> (Implementation, Test Automation, CI/CD) &mdash; the AI actually "
        "changes code: it creates a working copy, commits, pushes, and opens a <b>pull request</b>, "
        "which a human then reviews and merges. These <b>require</b> your companion to be started "
        "with a real repo and the <tt>--worktrees</tt> folder.",
        "<b>Security scan</b> (Security) &mdash; special: it reads your real source code in a "
        "<b>read-only</b> throwaway copy to scan for vulnerabilities, but never changes or pushes "
        "anything. If no repo is connected it falls back to a lighter, document-only scan.",
    ])

    callout("Two things not to test",
            "<b>Code Review</b> is not a button you press on its own &mdash; it runs automatically "
            "inside the build phase, so do not look for a standalone &ldquo;code-review&rdquo; "
            "trigger. And an old <b>Context Snapshot</b> phase has been retired &mdash; it will not "
            "appear anywhere; that is correct.")

    h2("7.2 The order you would run them")
    p("For a new (greenfield) project the natural order follows the numbers: ideation -&gt; "
      "requirements -&gt; PRD -&gt; architecture -&gt; UX -&gt; task breakdown -&gt; "
      "implementation -&gt; testing -&gt; test automation -&gt; security -&gt; CI/CD -&gt; "
      "deployment. For an existing (brownfield) project you first run the onboarding/context "
      "phases. The platform does not force a rigid sequence &mdash; you trigger each phase on a "
      "work item when you are ready &mdash; but this order is the intended flow to test.")


# ====================================================================
# 8. THE COMPANION IN DETAIL
# ====================================================================
def section_8():
    h1("8. The Companion, in Detail")
    lead("The companion is the one piece that runs on your laptop, and it is where build/security "
         "testing succeeds or fails. This section explains its commands so you can set it up right "
         "for each kind of testing.")

    h2("8.1 What it is and why it exists")
    p("The companion (also called the &ldquo;runner&rdquo;) is a small program that quietly waits "
      "for the platform to hand it work, runs that work on your machine using your Claude login, "
      "and reports the result back. It is why phases can run without the platform paying a shared "
      "AI bill &mdash; the work happens on your computer, on your subscription.")

    h2("8.2 The three commands")
    p("You run it as <tt>python -m runner.companion &lt;command&gt;</tt>. There are three commands, "
      "but for normal testing you mostly use the first two:")
    table([
        ["Command", "What it does", "When you use it"],
        ["enroll", "Registers your machine with the platform and prints a one-time token.",
         "Usually done <i>for</i> you by the <b>Connect Machine</b> screen; you rarely type it by "
         "hand."],
        ["serve", "The main worker. Waits for phases/builds and runs them. Keep it running while "
         "you test.", "Every testing session, after setup."],
        ["run", "Runs a single build task from a file, one-off.", "Advanced/manual; not needed for "
         "normal QA."],
    ], [2.2 * cm, 8.4 * cm, 5.8 * cm], font=8.4)

    h2("8.3 The <tt>serve</tt> options that matter")
    p("The <b>Connect Machine</b> screen builds most of this for you, but here is what each option "
      "means so you can adjust it:")
    table([
        ["Option", "Meaning"],
        ["--api-url", "Where the platform is &mdash; for you, <tt>http://localhost:8000</tt> (your "
         "local backend)."],
        ["--tenant", "Your workspace id (the app fills this in)."],
        ["--token", "The one-time enrollment token from the Connect Machine screen."],
        ["--worktrees", "A folder where the companion makes temporary working copies of repos. "
         "<b>Required for build and security phases.</b>"],
        ["--repo-path", "<b>Single-repo shorthand:</b> the one local clone that builds run against."],
        ["--repo NAME=PATH", "<b>Multi-repo:</b> maps each repo (e.g. <tt>acme/api=C:\\repos\\api</tt>) "
         "to its local clone. Repeat once per repo. An explicit map always wins over "
         "<tt>--repo-path</tt>."],
        ["--headed", "<b>Optional, for watching a test run:</b> shows the browser on screen during "
         "the Test Automation phase (09b) instead of running it invisibly, so you can watch the AI "
         "drive the app. Leave it off for normal testing."],
        ["--poll-interval / --heartbeat-interval", "How often it checks for work / signals it is "
         "alive. Defaults are fine; leave them."],
    ], [4.6 * cm, 11.8 * cm], font=8.3)

    h2("8.4 Which setup for which testing")
    bullets([
        "<b>Planning phases only</b> (ideation, requirements, PRD, architecture, UX, task "
        "breakdown, testing, deployment): the companion needs <b>no repo</b> &mdash; just "
        "<tt>serve</tt> with api-url, tenant, token. It reasons over the platform's stored context.",
        "<b>Build phases</b> (implementation, test automation, CI/CD): you <b>must</b> start "
        "<tt>serve</tt> with <tt>--worktrees</tt> <b>and</b> a repo (either <tt>--repo-path</tt> "
        "for single-repo, or one or more <tt>--repo NAME=PATH</tt> for multi-repo). Without them "
        "the build fails loudly &mdash; that is expected, not a bug.",
        "<b>Security phase</b>: give it <tt>--worktrees</tt> and the repo so it can scan real code. "
        "Without them it still runs but only does a lighter document-only scan.",
    ])
    callout("Multi-repo safety",
            "In a multi-repo project the companion will <b>never</b> guess which clone to use &mdash; "
            "if a repo isn't mapped, the build fails on purpose rather than pushing to the wrong "
            "GitHub repo. If you see that failure, add the missing <tt>--repo NAME=PATH</tt> and "
            "restart <tt>serve</tt>.", "ok")


# ====================================================================
# 9. END-TO-END USER JOURNEYS
# ====================================================================
def section_9():
    h1("9. End-to-End User Journeys (walk-throughs)")
    lead("These are the full journeys to test, written as a real user would perform them, click by "
         "click. Journey A is also your <b>smoke test</b> &mdash; do it first to prove your setup "
         "works, then explore the others.")

    h2("9.1 Journey A &mdash; Greenfield, single repo (the golden path / smoke test)")
    p("Goal: start from nothing and drive a brand-new project through the early lifecycle, proving "
      "sign-up, project setup, companion, triggering, clarifications, and gates all work.")
    numbered([
        "<b>Sign in.</b> App running at <tt>http://localhost:5173</tt>, you are logged into your "
        "own workspace (Section 5).",
        "<b>Create a project.</b> Sidebar -&gt; Work Items area, or Setup checklist -&gt; "
        "<b>Create your first project</b>. Name it (e.g. &ldquo;SpendLog&rdquo;), choose "
        "<b>Greenfield</b> and <b>Single repo</b>. It takes you to the <b>Project Profile</b>.",
        "<b>Fill the Project Profile.</b> Add the important context (what the project is about) and "
        "save.",
        "<b>Confirm the companion is Ready.</b> The top-bar pill should say <b>Companion: Ready</b>. "
        "If not, start <tt>serve</tt> (Section 8).",
        "<b>Create a work item.</b> Go to <b>Work Items</b>, create a <b>Story</b> (e.g. "
        "&ldquo;Track daily spending&rdquo;).",
        "<b>Trigger the first phase.</b> Open the item (or go to <b>Phases &amp; Runs</b>), pick "
        "the item, and trigger <b>Ideation</b>. Watch the <b>Run console</b> stream.",
        "<b>Answer clarifications if asked.</b> If a badge appears on <b>Clarifications</b>, open "
        "it, answer the Tier-1 questions, and the run resumes.",
        "<b>Approve the gate.</b> When the run finishes, a <b>gate</b> opens. Go to <b>Gates</b>, "
        "open the pending one, tick any required criteria, add a comment, and <b>Approve</b>. The "
        "work item advances.",
        "<b>Repeat down the lifecycle.</b> Trigger <b>Requirements</b>, then <b>PRD</b>, then "
        "<b>Architecture</b>, approving each gate. Each produces an artifact you can open under "
        "<b>Artifacts</b>.",
        "<b>Check traceability.</b> Open <b>Traceability</b> and confirm the artifacts link back "
        "to the work item and requirements.",
    ])
    callout("Smoke-test pass criteria",
            "If you reached an approved Architecture gate with artifacts visible and traceability "
            "linked &mdash; without an application error &mdash; your environment is healthy and "
            "you can test everything else with confidence.", "ok")

    h2("9.2 Journey B &mdash; A build phase (code actually changes)")
    p("Goal: prove the platform can make real code changes and open a pull request. Needs the "
      "companion started with a repo + <tt>--worktrees</tt> (Section 8), and a GitHub integration "
      "connected.")
    numbered([
        "Ensure your <tt>serve</tt> is running with <tt>--worktrees</tt> and <tt>--repo-path</tt> "
        "pointing at a real clone.",
        "Connect the <b>Code host (GitHub)</b> integration for the project (Integrations screen).",
        "On a work item that has been through task breakdown, trigger <b>Implementation</b>.",
        "Watch the run: the companion makes a working copy, writes code, commits, pushes, and opens "
        "a <b>pull request</b> on GitHub. <b>Code Review</b> runs automatically inside this build.",
        "A <b>merge gate</b> opens for a human. Review and decide.",
        "Verify on GitHub that the branch and PR were actually created.",
    ])
    callout("Multi-repo variant",
            "For a multi-repo project, start <tt>serve</tt> with one <tt>--repo NAME=PATH</tt> per "
            "repo, and make sure the work item is <b>pinned to a repo</b> (multi-repo items must be "
            "&mdash; an unpinned one is meant to be confirmed at the Task Breakdown gate). Confirm "
            "the change lands in the <i>correct</i> repo.")

    h2("9.3 Journey C &mdash; The security scan (read-only)")
    p("Goal: prove the security phase scans real code safely. Needs the companion with "
      "<tt>--worktrees</tt> and the repo.")
    numbered([
        "On a work item tied to a repo, trigger <b>Security</b> from Phases &amp; Runs.",
        "The companion makes a <b>read-only</b> throwaway copy and scans the code (it never "
        "commits or pushes).",
        "It produces security findings (and a threat model / SBOM / security review on a full "
        "run). Critical/High findings open <b>Defect</b> work items automatically.",
        "Review the findings, and check that any Defect children appear under the work item.",
    ])
    callout("Known behaviour on security runs",
            "A security run can be long and may stop early if the AI hits a usage limit &mdash; "
            "that is not an application bug. Defect items are only opened when a run finishes "
            "reporting; a partial run intentionally opens none. Re-trigger when you have usage "
            "headroom.")

    h2("9.4 Journey D &mdash; Brownfield onboarding")
    p("Goal: bring an existing project's docs and code into the platform.")
    numbered([
        "Create a project and choose <b>Brownfield</b>. It takes you to the <b>Onboarding hub</b>.",
        "Connect the source tools (e.g. Confluence/Jira) and your repo(s).",
        "Run the extraction/indexing, then open <b>Source documents</b> to see what was ingested "
        "and the <b>Gap report</b> for what is missing.",
        "From there, continue into the normal lifecycle phases.",
    ])

    h2("9.5 Journey E &mdash; Clarifications and offline takeover (cross-cutting)")
    p("These behaviours sit on top of any journey and are worth testing directly:")
    bullets([
        "<b>Clarification round-trip:</b> trigger a phase; if it asks, the <b>Clarifications</b> "
        "badge appears and the run idles (costing nothing). Answer -&gt; it resumes.",
        "<b>Offline takeover:</b> stop the companion (Ctrl-C), trigger a phase, and wait. After a "
        "timeout the run is parked for <b>human takeover</b> (visible on <b>Run recovery</b>) "
        "rather than hanging. Restart the companion to resume.",
        "<b>Companion status honesty:</b> the <b>Companion</b> pill should flip between Ready and "
        "Offline as you start/stop <tt>serve</tt>.",
    ])


# ====================================================================
# 10. IS IT A BUG OR BY DESIGN?
# ====================================================================
def section_10():
    h1("10. Is It a Bug, or Is It Meant to Work That Way?")
    lead("Read this before logging behaviour that merely looks wrong. These are deliberate design "
         "decisions &mdash; reporting them as defects slows everyone down. Anything <i>not</i> on "
         "this list that feels broken, however, is worth logging.")
    table([
        ["Behaviour you might see", "Verdict"],
        ["A run stops partway with a message about a usage or rate limit.",
         "<b>By design.</b> The AI has usage limits. Re-trigger later. Only log it if the "
         "<i>message</i> is a raw/technical error instead of a plain explanation."],
        ["A gate can be approved even though findings exist (e.g. security).",
         "<b>By design.</b> Gates are advisory human checkpoints; the human decides. Findings are "
         "tracked separately."],
        ["A security run that ended early opened no Defect items.",
         "<b>By design.</b> Defects are only opened when a run finishes reporting."],
        ["Phases &amp; Runs won't let you trigger and shows an offline state.",
         "<b>By design.</b> Your companion isn't running/enrolled. Start <tt>serve</tt>."],
        ["A build phase fails because no repo or no --worktrees was provided.",
         "<b>By design.</b> Build phases need a real repo and worktrees folder."],
        ["There is no standalone &ldquo;Code Review&rdquo; button.",
         "<b>By design.</b> Code review runs inside the build phase."],
        ["A saved integration secret is never shown back to you.",
         "<b>By design.</b> Secrets are write-only; only an &ldquo;is configured&rdquo; flag shows."],
        ["You cannot approve a gate and get a &ldquo;role&rdquo; error (403).",
         "<b>By design.</b> You need that gate's role on the project (or be an admin). Assign roles "
         "under Admin -&gt; Roles."],
        ["Nothing was pushed to Confluence/Jira after a gate approval.",
         "<b>By design.</b> Publishing is a separate, user-triggered step (Artifacts -&gt; "
         "Publish), and only if that integration is connected."],
        ["You see another workspace's data.",
         "<b>NOT by design &mdash; log P1 immediately.</b> Tenant isolation must be absolute."],
    ], [8.2 * cm, 8.2 * cm], font=8.3)


# ====================================================================
# 11. TESTING IN PARALLEL
# ====================================================================
def section_11():
    h1("11. Testing in Parallel Without Stepping on Each Other")
    lead("Two testers plus two developers all share the same cloud brain. A little discipline keeps "
         "your results clean and your bugs reproducible.")
    bullets([
        "<b>Use your own workspace.</b> Each tester signs up their own workspace (tenant). Your "
        "data is then fully separate from the other tester's and the developers'. Name it clearly "
        "(Section 5.6).",
        "<b>Keep your code in sync.</b> All of you run the app and companion from the same project "
        "code. Before a testing session, pull the latest (<tt>git pull</tt>) and restart your app "
        "and companion, so you are testing the current build. If in doubt about which version to "
        "test, ask the team for the &ldquo;known-good&rdquo; commit for the day.",
        "<b>Know that workers are shared.</b> Everyone's companion listens on the same shared work "
        "queue. A phase you trigger normally runs on <i>your</i> companion, but the system is "
        "shared, so if something behaves oddly, note the time and your workspace name so a "
        "developer can trace it.",
        "<b>Record your environment in every bug.</b> Because the environment is shared, always "
        "note your workspace name, the work item key (e.g. <tt>WI-14</tt>), the phase, and the "
        "run's time. This makes any bug reproducible.",
        "<b>Don't test destructive things on shared data.</b> Stick to your own workspace's "
        "projects and items.",
    ])
    callout("If two people report the same odd run",
            "Because runs can execute on different machines, the same symptom might have two "
            "different causes. Always keep your bug reports tied to <i>your</i> workspace and run "
            "&mdash; don't merge your report with another tester's until a developer confirms they "
            "are the same issue.", "ok")


# ====================================================================
# 12. TROUBLESHOOTING
# ====================================================================
def section_12():
    h1("12. Troubleshooting (fix it yourself first)")
    lead("Ninety percent of setup snags are one of these. Try the fix here before asking a "
         "developer &mdash; that is the whole point of having this guide.")
    table([
        ["Symptom", "Most likely cause &amp; fix"],
        ["Browser shows nothing at localhost:5173.",
         "The app didn't start. Make sure <b>Docker Desktop is running</b>, then re-run "
         "<tt>docker compose --profile app up --no-deps backend worker frontend</tt> and watch for "
         "errors in that terminal."],
        ["App loads but login/signup fails or errors.",
         "Your <tt>.env</tt> shared values are wrong or missing (database/Temporal). Re-check them "
         "against what the dev team gave you, then restart the app."],
        ["&ldquo;Socket is not connected&rdquo; or database errors.",
         "The shared cloud is unreachable from your machine (network) or Docker dropped. Confirm "
         "you can reach the shared host; restart Docker and the app."],
        ["Companion won't start; prints &ldquo;CANNOT START&rdquo;.",
         "The <tt>claude</tt> CLI isn't logged in, or an API key is set. Run <tt>claude</tt> to log "
         "in, and make sure no <tt>ANTHROPIC_API_KEY</tt> is forced in your shell."],
        ["A phase never runs / stays pending.",
         "Your companion isn't running or isn't enrolled for this project. Check the <b>Companion: "
         "Ready</b> pill, that <tt>serve</tt> is up in its terminal, and that you enrolled for "
         "this project."],
        ["A build or security phase fails immediately.",
         "You started <tt>serve</tt> without <tt>--worktrees</tt> and/or a repo. Restart it with "
         "both (Section 8)."],
        ["A live tool step (publish to Confluence/Jira) does nothing.",
         "That integration isn't connected for <i>your</i> project, or the token is wrong. Check "
         "Integrations shows it <b>Connected</b> and re-test the credentials."],
        ["Can't approve a gate (403 / role error).",
         "You don't hold that gate's role. As your own workspace admin, assign yourself the role "
         "under Admin -&gt; Roles &amp; memberships."],
        ["The frontend seems stuck on old code after a pull.",
         "Restart the frontend service (stop and re-run the compose command). On Windows the "
         "auto-reload sometimes misses changes."],
    ], [6.2 * cm, 10.2 * cm], font=8.3)
    callout("When to actually ask a developer",
            "Ask if: a shared secret in your <tt>.env</tt> looks wrong and you can't verify it; the "
            "shared cloud (database/Temporal) is down for everyone; or you hit an application error "
            "that this section doesn't cover and that blocks all testing. Everything else, try the "
            "fix above first.")


# ====================================================================
# 13. HOW TO REPORT A BUG
# ====================================================================
def section_13():
    h1("13. How to Report a Bug (the format that gets it fixed)")
    lead("Your bug reports are the product of all this testing. A good report gets fixed fast; a "
         "vague one bounces back with questions. Keep your own bug sheet in the shared format "
         "below.")

    h2("13.1 Keep your own bug sheet")
    p("Each tester keeps a spreadsheet (Excel) of the bugs they find. Use these columns, in this "
      "order &mdash; they match how the development team already tracks bugs, so your sheet drops "
      "straight into their workflow:")
    table([
        ["Column", "What goes in it"],
        ["S.No", "A running number (1, 2, 3, ...). Never reuse a number."],
        ["Bug / Issue", "A short, specific title. &ldquo;Approve button stays disabled after all "
         "criteria ticked&rdquo; &mdash; not &ldquo;gate broken&rdquo;."],
        ["Description", "Optional longer detail if the title isn't enough. Many teams leave this "
         "empty when the title is clear."],
        ["Feature", "Which area/screen (e.g. Gates, Integrations, Phases &amp; Runs, Sign up)."],
        ["Type", "UI issue, Functional bug, Content/wording, Performance, Crash/Error, etc."],
        ["Reference", "A screenshot pasted into the cell (see 13.3), or a note of where to look."],
        ["Priority", "P1 / P2 / P3 (see 13.2)."],
        ["Root Cause", "Leave blank &mdash; the developers fill this when they investigate."],
        ["Fix Implemented", "Leave blank &mdash; the developers fill this when they fix it."],
        ["Status", "Open (you), then Fixed / Won't fix (developers)."],
    ], [3.4 * cm, 13.0 * cm], font=8.4)

    h2("13.2 Priority &mdash; how bad is it?")
    table([
        ["Priority", "Use it when...", "Examples"],
        ["P1 (Critical)", "Blocks testing, loses data, or breaks a core promise of the platform.",
         "Can't log in; a phase can never be triggered; you can see another workspace's data; the "
         "app crashes."],
        ["P2 (Major)", "A feature is clearly wrong or broken, but you can still work around it.",
         "A gate approves without enforcing a required criterion; a wrong error message; a broken "
         "link on a key screen."],
        ["P3 (Minor)", "Cosmetic or low-impact polish.",
         "Misaligned button, typo, inconsistent spacing, slightly confusing label."],
    ], [3.0 * cm, 6.6 * cm, 6.8 * cm], font=8.3)

    h2("13.3 Attaching screenshots (important gotcha)")
    p("Screenshots make a report ten times more useful. You can paste an image directly into a "
      "spreadsheet cell, but be aware of one trap the team has hit:")
    callout("The in-cell image trap",
            "If you paste images <i>inside</i> cells, do <b>not</b> edit and re-save that sheet "
            "with automated tools &mdash; some tools silently drop in-cell images on save. If you "
            "hand your sheet to a developer, tell them it has in-cell screenshots so they preserve "
            "them. A safe alternative: keep screenshots in a folder and reference the filename in "
            "the <b>Reference</b> column.")

    h2("13.4 What makes a report actionable")
    bullets([
        "<b>Steps to reproduce</b> &mdash; numbered, from a known starting point (&ldquo;From "
        "Dashboard, click X, then Y&rdquo;).",
        "<b>What you expected</b> vs. <b>what actually happened</b> &mdash; state both.",
        "<b>Environment</b> &mdash; your workspace name, the work item key (e.g. <tt>WI-14</tt>), "
        "the phase, and roughly when it happened (because the cloud is shared).",
        "<b>Evidence</b> &mdash; a screenshot, and the exact error text if any (type it out; don't "
        "just say &ldquo;it errored&rdquo;).",
        "<b>One bug per row</b> &mdash; don't combine several issues into one line.",
        "<b>Check Section 10 first</b> &mdash; make sure it isn't intended behaviour.",
    ])

    h2("13.5 A worked example")
    callout("Good bug report",
            "<b>S.No:</b> 7 &nbsp; <b>Bug:</b> &ldquo;Approve stays disabled after all gate "
            "criteria are ticked&rdquo; &nbsp; <b>Feature:</b> Gates &nbsp; <b>Type:</b> Functional "
            "&nbsp; <b>Priority:</b> P2<br/><b>Steps:</b> 1) Workspace &ldquo;QA-Priya&rdquo;, item "
            "WI-14, run Requirements to a gate. 2) Open Gates -&gt; the pending gate -&gt; criteria "
            "checklist. 3) Tick all required criteria. <b>Expected:</b> Approve becomes clickable. "
            "<b>Actual:</b> Approve stays greyed out; had to refresh the page to enable it. "
            "<b>Evidence:</b> screenshot gate-approve-disabled.png; no console error.", "ok")

    gap(6)
    p("That is the whole job: set up once, understand the map, walk the journeys, and log what you "
      "find in this format. Welcome to the team &mdash; happy testing.", LEAD)


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
    canvas.drawString(2 * cm, 1.0 * cm, "AI-First SDLC Platform - QA Team Testing Guide")
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
                   title="AI-First SDLC Platform - QA Team Testing Guide",
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
    section_6()
    section_7()
    section_8()
    section_9()
    section_10()
    section_11()
    section_12()
    section_13()

    doc.multiBuild(story)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
