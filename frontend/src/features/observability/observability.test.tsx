// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import { ArtifactPreviewScreen } from "./ArtifactPreviewScreen";
import { ArtifactsRegistry } from "./ArtifactsRegistry";
import { ContractsDrift } from "./ContractsDrift";
import { Dashboard } from "./Dashboard";
import { ExportPublish } from "./ExportPublish";
import { GapReportScreen } from "./GapReportScreen";
import { OfflineTakeover } from "./OfflineTakeover";
import { OnboardingHub, RegisterToolsStep } from "./OnboardingHub";
import { RunTranscriptScreen } from "./RunTranscriptScreen";
import { badgeFor, fileKindLabel, guessAdoptType, SourceDocuments } from "./SourceDocuments";
import type { OnboardingRegister, SourceDocument } from "../../types";
import { TraceabilityView } from "./TraceabilityView";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(stubFetchJson(401, { detail: "no session" })));
});
afterEach(() => vi.unstubAllGlobals());

describe("S-25 adopt — guessAdoptType (Brownfield B2-1)", () => {
  it("pre-selects a canonical type from the filename", () => {
    expect(guessAdoptType("System Architecture v2.pdf")).toBe("architecture");
    // Full lifecycle vocabulary now supports finer types than the original 5.
    expect(guessAdoptType("Billing ADR-004.docx")).toBe("adr");
    expect(guessAdoptType("Product PRD.docx")).toBe("prd");
    expect(guessAdoptType("Login wireframe.pdf")).toBe("wireframe");
    expect(guessAdoptType("UX design notes.docx")).toBe("ux_design");
    expect(guessAdoptType("Q3 Test Cases.xlsx")).toBe("test_case");
    expect(guessAdoptType("Security Review 2026.docx")).toBe("security_review");
    expect(guessAdoptType("Product Vision.pdf")).toBe("ideation");
    // Everything else defaults to requirements (the most common upload).
    expect(guessAdoptType("Legacy Billing Requirements v3.docx")).toBe("requirements");
    expect(guessAdoptType("random notes.docx")).toBe("requirements");
  });
});

describe("S-25 source doc — fileKindLabel (BF-BUG-1)", () => {
  it("shows a short human label, never the raw MIME string", () => {
    const docxMime =
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    expect(fileKindLabel(docxMime, "05_Deployment.docx")).toBe("Word (DOCX)");
    expect(fileKindLabel("application/pdf", "06_PRD.pdf")).toBe("PDF");
    expect(fileKindLabel("text/html", "wireframes.html")).toBe("HTML");
    expect(fileKindLabel("text/plain", "notes.txt")).toBe("Text");
    // falls back to the extension when the MIME is empty/unknown
    expect(fileKindLabel("", "backlog.xlsx")).toBe("Excel (XLSX)");
  });
});

describe("S-25 source doc — honest status badge (A4)", () => {
  const base: SourceDocument = {
    id: "d1", project: "p1", filename: "x.pdf", mime: "application/pdf",
    status: "extracted", extracted_artifact_ids: [], provenance: {}, created_at: "",
    has_original: true, page_images: [], fidelity: "text", vision: null,
  };
  it("distinguishes text / images-only / empty instead of one blanket label", () => {
    // Screen Words group 4: "Extracted" said what the platform did; "Ready to adopt" says what
    // the reader can now do. Same word as the onboarding hub, which is where most people see it.
    expect(badgeFor({ ...base, fidelity: "text" }).label).toBe("Ready to adopt");
    expect(badgeFor({ ...base, fidelity: "images_only" }).label).toBe("Needs AI read");
    expect(badgeFor({ ...base, fidelity: "empty" }).label).toBe("No text found");
    expect(badgeFor({ ...base, status: "adopted" }).label).toBe("Adopted");
  });

  // Reported from live testing: pressing Adopt said "Adopted" straight away while the document
  // was plainly still being worked on. It was not only early — for a document with pages the
  // vision run is what registers the artifact, so the row offered "View artifact" for an
  // artifact that did not exist yet, directly above its own notice saying it was still reading.
  it("says 'Adopting…' while the document is still being read", () => {
    const doc: SourceDocument = {
      ...base, status: "adopted",
      vision: { state: "running", message: "Reading the diagrams…" },
    };
    expect(badgeFor(doc).label).toBe("Adopting…");
    expect(badgeFor(doc).variant).toBe("running");
  });

  it("says 'Adopted' once the reading has finished", () => {
    const done: SourceDocument = {
      ...base, status: "adopted", vision: { state: "done", message: "" },
    };
    expect(badgeFor(done).label).toBe("Adopted");
    expect(badgeFor(done).variant).toBe("done");
  });

  it("still says 'Adopted' for a document that never needed reading", () => {
    // A .docx with no pictures dispatches no vision run at all, so `vision` stays null. If that
    // read as "Adopting…" the badge would hang there for ever on the commonest document of all.
    expect(badgeFor({ ...base, status: "adopted", vision: null }).label).toBe("Adopted");
    expect(badgeFor({
      ...base, status: "adopted", vision: { state: "no_visuals", message: "" },
    }).label).toBe("Adopted");
  });

  it("does not let a stalled reading hide a failure", () => {
    // `failed` is checked before `adopted`, and a vision run that failed must not read as
    // in-progress — the user has to know the reading is over and did not work.
    expect(badgeFor({
      ...base, status: "adopted", vision: { state: "failed", message: "no companion" },
    }).label).toBe("Adopted");
  });
});

// Reported from live testing: the step offered "Connect Jira", and the pop-up behind it said
// "Connect Task tracker — choose a vendor". The button was promising a choice the user had not
// made. CLAUDE.md's ninth non-negotiable is "capabilities, not vendors"; this step was the one
// screen breaking it.
describe("Register existing tools — capabilities before connecting, vendors after", () => {
  // render() queries bind to document.body, so without this each test also sees the previous
  // test's markup and every getByText finds two of everything.
  afterEach(cleanup);

  const nothingConnected: OnboardingRegister = {
    docstore_connected: false, tasktracker_connected: false, designsource_connected: false,
    docstore_vendor: null, tasktracker_vendor: null, designsource_vendor: null,
    pages_registered: 0, issues_registered: 0,
  };

  it("offers to connect a CAPABILITY, matching the pop-up it opens", () => {
    renderWithProviders(<RegisterToolsStep projectId="p1" register={nothingConnected} />);
    expect(screen.getByRole("button", { name: "Connect task tracker" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Connect documentation store" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Connect design source" })).toBeDefined();
  });

  it("names no vendor while nothing is connected", () => {
    renderWithProviders(<RegisterToolsStep projectId="p1" register={nothingConnected} />);
    expect(screen.queryByText("Jira")).toBeNull();
    expect(screen.queryByText("Confluence")).toBeNull();
    expect(screen.queryByText("Figma")).toBeNull();
    expect(screen.getByText("Task tracker")).toBeDefined();
    expect(screen.getByText("Documentation store")).toBeDefined();
    expect(screen.getByText("Design source")).toBeDefined();
  });

  it("names the real tool once one is connected", () => {
    // "Import task tracker backlog" would be worse for somebody who plainly connected Jira. The
    // vendor comes from the server, so the day a second tracker exists this says its name
    // instead of a hardcoded one.
    renderWithProviders(
      <RegisterToolsStep
        projectId="p1"
        register={{
          ...nothingConnected,
          tasktracker_connected: true, tasktracker_vendor: "Jira",
          designsource_connected: true, designsource_vendor: "Figma",
        }}
      />,
    );
    expect(screen.getByText("Jira")).toBeDefined();
    expect(screen.getByRole("button", { name: "Import Jira backlog" })).toBeDefined();
    expect(screen.getByText("Figma")).toBeDefined();
  });
});

// Reported from live testing: the connect-your-machine card opened with forty-one words
// beginning "Some of this work runs…", and users read past it. The sentence people must read is
// now short; the detail moved into the platform's first tooltip.
describe("Connect your machine — one short line, the rest a keypress away", () => {
  afterEach(cleanup);

  it("leads with where the files go, in one sentence", () => {
    renderWithProviders(<OnboardingHub forceView="nothing-done" />);
    expect(
      screen.getByText(/Your documents and code are read on your own computer/),
    ).toBeDefined();
  });

  it("no longer opens with the wall of text", () => {
    renderWithProviders(<OnboardingHub forceView="nothing-done" />);
    expect(screen.queryByText(/Some of this work runs on your own machine/)).toBeNull();
  });

  it("keeps the detail reachable, and not only by mouse", () => {
    renderWithProviders(<OnboardingHub forceView="nothing-done" />);
    const tip = screen.getByRole("button", { name: "More information" });
    fireEvent.focus(tip);
    expect(
      screen.getByRole("tooltip").textContent,
    ).toContain("read the diagrams and screenshots inside your documents");
  });
});

describe("S-24 Onboarding hub", () => {
  it("nothing-done · in-progress · gap-ready", () => {
    const { rerender } = renderWithProviders(<OnboardingHub forceView="nothing-done" />);
    expect(screen.getByText(/Upload resources/)).toBeDefined();
    expect(screen.getByText(/Drag & drop documents/)).toBeDefined();

    rerender(<OnboardingHub forceView="in-progress" />);
    expect(screen.getByText(/Indexing 1,284 files/)).toBeDefined();

    rerender(<OnboardingHub forceView="gap-ready" />);
    expect(screen.getByText("Resume at: Architecture")).toBeDefined();
  });
});

describe("S-25 Source documents", () => {
  it("empty · uploading · extracted · adopt-gate · adopted", () => {
    const { rerender } = renderWithProviders(<SourceDocuments forceView="empty" />);
    expect(screen.getByText(/Drag & drop documents/)).toBeDefined();

    rerender(<SourceDocuments forceView="uploading" />);
    expect(screen.getByText("Extracting…")).toBeDefined();

    rerender(<SourceDocuments forceView="extracted" />);
    expect(screen.getByText("Adopt as Requirements artifact")).toBeDefined();

    rerender(<SourceDocuments forceView="adopt-gate" />);
    expect(screen.getByText("Adoption awaiting gate")).toBeDefined();

    rerender(<SourceDocuments forceView="adopted" />);
    expect(screen.getByText("Legacy Billing Requirements")).toBeDefined();
  });
});

describe("S-26 Gap report", () => {
  it("partial · empty · mature", () => {
    const { rerender } = renderWithProviders(<GapReportScreen forceView="partial" />);
    expect(screen.getAllByText("Resume at: Architecture").length).toBeGreaterThan(0);

    rerender(<GapReportScreen forceView="empty" />);
    expect(screen.getAllByText("Resume at: Ideation").length).toBeGreaterThan(0);

    rerender(<GapReportScreen forceView="mature" />);
    expect(screen.getAllByText("Resume at: Task Breakdown").length).toBeGreaterThan(0);
  });
});

describe("S-27 Contracts & drift", () => {
  it("healthy · drift-pending · wrong-role · decided", () => {
    const { rerender } = renderWithProviders(<ContractsDrift forceView="healthy" />);
    expect(screen.getByText("Payments API")).toBeDefined();

    rerender(<ContractsDrift forceView="drift-pending" />);
    expect(screen.getByText(/Payments API v2.0.0 — breaking change/)).toBeDefined();

    rerender(<ContractsDrift forceView="wrong-role" />);
    expect(screen.getByText("Awaiting architect")).toBeDefined();

    rerender(<ContractsDrift forceView="decided" />);
    expect(screen.getByText("Accepted by Marcus Lee")).toBeDefined();
  });
});

describe("S-28 Artifacts registry", () => {
  it("populated · internal-only · empty", () => {
    const { rerender } = renderWithProviders(<ArtifactsRegistry forceView="populated" />);
    expect(screen.getByText("Artifacts")).toBeDefined();

    rerender(<ArtifactsRegistry forceView="internal-only" />);
    expect(screen.getByText("Ideation Brief — Loyalty Program")).toBeDefined();

    rerender(<ArtifactsRegistry forceView="empty" />);
    expect(screen.getByText("No artifacts yet")).toBeDefined();
  });
});

describe("S-29 Artifact preview", () => {
  it("markdown · diagram · external · unavailable", () => {
    const { rerender } = renderWithProviders(<ArtifactPreviewScreen forceView="markdown" />);
    expect(screen.getAllByText(/PRD: Stripe Webhook Integration/).length).toBeGreaterThan(0);
    expect(screen.getByText("Version history")).toBeDefined();

    rerender(<ArtifactPreviewScreen forceView="diagram" />);
    expect(screen.getByText("System Sequence Diagram")).toBeDefined();

    rerender(<ArtifactPreviewScreen forceView="external" />);
    expect(screen.getByText("Multi-Currency Requirements")).toBeDefined();

    rerender(<ArtifactPreviewScreen forceView="unavailable" />);
    expect(screen.getByText("Preview unavailable")).toBeDefined();
  });
});

describe("S-30 Traceability", () => {
  it("small · highlighted · large-cluster · empty", () => {
    const { rerender } = renderWithProviders(<TraceabilityView forceView="small" />);
    expect(screen.getByText("Traceability")).toBeDefined();

    rerender(<TraceabilityView forceView="highlighted" />);
    expect(screen.getAllByText("Requirements").length).toBeGreaterThan(0);

    rerender(<TraceabilityView forceView="large-cluster" />);
    expect(screen.getByLabelText("Large lineage cluster")).toBeDefined();

    rerender(<TraceabilityView forceView="empty" />);
    expect(screen.getByText("No lineage yet")).toBeDefined();
  });
});

describe("S-31 Dashboard", () => {
  it("busy · calm · new-project", () => {
    const { rerender } = renderWithProviders(<Dashboard forceView="busy" />);
    expect(screen.getByText(/Gates need your approval/)).toBeDefined();
    expect(screen.getByText("Needs me")).toBeDefined();

    rerender(<Dashboard forceView="calm" />);
    expect(screen.getByText("You're all caught up")).toBeDefined();

    rerender(<Dashboard forceView="new-project" />);
    expect(screen.getByText("Get started")).toBeDefined();
    expect(screen.getByText("Not connected yet")).toBeDefined();
  });
});

describe("S-32 Offline takeover", () => {
  it("parked · reconnecting · resumed", () => {
    const { rerender } = renderWithProviders(<OfflineTakeover forceView="parked" />);
    expect(screen.getByText(/this run is parked for takeover/)).toBeDefined();

    rerender(<OfflineTakeover forceView="reconnecting" />);
    expect(screen.getByText(/Reconnecting Sarah's MacBook/)).toBeDefined();

    rerender(<OfflineTakeover forceView="resumed" />);
    expect(screen.getByText("Run resumed")).toBeDefined();
  });
});

describe("S-33 Run transcript", () => {
  it("runs-list · transcript · empty", () => {
    const { rerender } = renderWithProviders(<RunTranscriptScreen forceView="runs-list" />);
    expect(screen.getByText("Run transcripts")).toBeDefined();
    expect(screen.getByText("RUN-42")).toBeDefined();

    rerender(<RunTranscriptScreen forceView="transcript" />);
    expect(screen.getAllByText(/Read-only replay/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Agent").length).toBeGreaterThan(0);

    rerender(<RunTranscriptScreen forceView="empty" />);
    expect(screen.getByText("No transcripts yet")).toBeDefined();
  });
});

describe("S-34 Export / publish", () => {
  it("choose-target · publishing · success · blocked", () => {
    const { rerender } = renderWithProviders(<ExportPublish forceView="choose-target" />);
    expect(screen.getByText("Publish artifact")).toBeDefined();
    expect(screen.getByText("Gate approved")).toBeDefined();

    rerender(<ExportPublish forceView="publishing" />);
    expect(screen.getByText(/Publishing to Confluence/)).toBeDefined();

    rerender(<ExportPublish forceView="success" />);
    expect(screen.getByText("Published to Confluence")).toBeDefined();

    rerender(<ExportPublish forceView="blocked" />);
    // Screen Words group 2: the banner no longer uses "gate-approved" as a compound adjective,
    // and the status inside it is a label rather than the stored word.
    expect(screen.getByText("Can't publish yet")).toBeDefined();
  });
});

// Team flow decision 2026-07-07: the live modal is driven by the phase's export policy.
// Per-URL stub: the preview endpoint returns the payload; /auth/me/ (AuthProvider) and
// everything else stay 401 so the auth context settles to unauthenticated.
function stubPreview(preview: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL) => {
      const href = String(url);
      const hit = href.includes("/preview/");
      return {
        ok: hit,
        status: hit ? 200 : 401,
        statusText: "stub",
        text: async () => JSON.stringify(hit ? preview : { detail: "no session" }),
      } as Response;
    }),
  );
}

function renderLivePublish() {
  return renderWithProviders(
    <Routes>
      <Route path="/artifacts/:id/publish" element={<ExportPublish />} />
    </Routes>,
    { route: "/artifacts/a1/publish" },
  );
}

describe("S-34 Export / publish — policy-driven live modal", () => {
  // render() queries bind to document.body; without explicit cleanup the first test's
  // DOM leaks into the second and absence assertions lie.
  afterEach(cleanup);

  it("offers only Internal + the phase's single policy target", async () => {
    stubPreview({
      body: "# PRD", content_type: "text/markdown", status: "approved", version: 1,
      versions: [], sor_link: null, phase: "03_prd", artifact_type: "prd",
      export_target: "docstore",
    });
    const { findByText, queryByText } = renderLivePublish();
    expect(await findByText("Internal (platform)")).toBeDefined();
    expect(queryByText("Documentation store · Confluence")).not.toBeNull();
    // No other capability is offered — the policy allows exactly one target.
    expect(queryByText("Task tracker · Jira")).toBeNull();
    expect(queryByText("Test management · Xray")).toBeNull();
  });

  it("internal-only phase shows the policy banner, with the Figma note for ux_design", async () => {
    stubPreview({
      body: "# UX", content_type: "text/markdown", status: "approved", version: 1,
      versions: [], sor_link: null, phase: "05_ux_design", artifact_type: "design_system",
      export_target: null,
    });
    const { findByText, queryByText } = renderLivePublish();
    expect(await findByText(/publishes internally only/)).toBeDefined();
    expect(queryByText(/Figma export is coming later/)).not.toBeNull();
    expect(queryByText("Target capability")).toBeNull();
  });
});


// ── B4 · the way anyone finds the accessibility work (task 8a) ───────────────
//
// The audit screen lived behind a tab nothing pointed at, which is found only by someone who
// already knew it was there. These assert the step exists, says the right thing in each of its
// three states, and — the one that would silently break the hub — that a payload without the
// field still renders.

const HUB_PROJECT = "11111111-1111-1111-1111-111111111111";

function stubHub(a11y: unknown) {
  const hub: Record<string, unknown> = {
    upload: [], adopt: [], adopt_types: [],
    register: { docstore_connected: false, tasktracker_connected: false,
                designsource_connected: false, pages_registered: 0, issues_registered: 0 },
    index: { status: "not_started", artifact_id: null, repos: [] },
    gap: { ready: false },
  };
  if (a11y !== undefined) hub.a11y = a11y;
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body =
      /auth\/me\//.test(url)
        ? {
            user: { id: "u1", email: "a@acme.test", name: "A", is_tenant_admin: false },
            tenant: { id: "t1", name: "Acme" },
            memberships: [{ project_id: HUB_PROJECT, project_name: "Meridian", role: "engineer" }],
          }
        : /onboarding\//.test(url) ? hub
        : /runners\//.test(url) ? []
        : /repositories\//.test(url) ? []
        : {};
    return { ok: true, status: 200, statusText: "stub",
             text: async () => JSON.stringify(body) } as Response;
  });
}

describe("S-24 onboarding — the accessibility step (B4)", () => {
  beforeEach(() => localStorage.setItem("selectedProjectId", HUB_PROJECT));
  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("not started · offers to set the audit up, and says what it is for", async () => {
    vi.stubGlobal("fetch", stubHub({ routes_registered: 0, audits_run: 0, status: "not_started" }));
    renderWithProviders(<OnboardingHub />);

    expect(await screen.findByText("Check accessibility")).toBeTruthy();
    expect(screen.getByText(/where the application stands before you change anything/)).toBeTruthy();
    const link = screen.getByRole("link", { name: "Set up the audit" });
    expect(link.getAttribute("href")).toBe("/a11y/pages");
  });

  it("ready · pages are registered and no audit has run yet", async () => {
    vi.stubGlobal("fetch", stubHub({ routes_registered: 69, audits_run: 0, status: "ready" }));
    renderWithProviders(<OnboardingHub />);

    expect(await screen.findByText(/69 page\(s\) registered/)).toBeTruthy();
  });

  it("done · an audit has run, and it points at where the report is", async () => {
    vi.stubGlobal("fetch", stubHub({ routes_registered: 69, audits_run: 2, status: "done" }));
    renderWithProviders(<OnboardingHub />);

    expect(await screen.findByText(/2 audits run/)).toBeTruthy();
  });

  // An audit that is still going is NOT one that has run. The step counted `judging` as done
  // and then said "1 audit run - open the report from Artifacts" while the run was mid-flight:
  // there is no report until the judging ends, because the baseline is published only when the
  // position has settled. Seen on the live run of 21 August.
  it("running · says an audit is going, and does not offer a report that does not exist", async () => {
    vi.stubGlobal("fetch", stubHub({
      routes_registered: 12, audits_run: 0, running: true, status: "running",
    }));
    renderWithProviders(<OnboardingHub />);

    expect(await screen.findByText(/An audit is running now/)).toBeTruthy();
    expect(screen.queryByText(/open the report from Artifacts/)).toBeNull();
  });

  it("done and running at once · the tick stays, and the line says another is going", async () => {
    vi.stubGlobal("fetch", stubHub({
      routes_registered: 12, audits_run: 1, running: true, status: "done",
    }));
    renderWithProviders(<OnboardingHub />);

    expect(await screen.findByText(/1 audit run/)).toBeTruthy();
    expect(screen.getByText(/Another audit is running now/)).toBeTruthy();
  });

  it("a payload with no accessibility block still renders the hub", async () => {
    // A backend that predates this field must not blank the screen a brownfield user lands on.
    vi.stubGlobal("fetch", stubHub(undefined));
    renderWithProviders(<OnboardingHub />);

    expect(await screen.findByText("Check accessibility")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Set up the audit" })).toBeTruthy();
  });

  it("Resume moved to 7, so the numbering still reads in order", async () => {
    vi.stubGlobal("fetch", stubHub({ routes_registered: 0, audits_run: 0, status: "not_started" }));
    renderWithProviders(<OnboardingHub />);

    await screen.findByText("Check accessibility");
    const resume = screen.getByText("Resume").closest(".vstep");
    expect(resume?.querySelector(".vstep__num")?.textContent).toBe("7");
  });
});
