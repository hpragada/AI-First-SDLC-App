// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import { ArtifactPreviewScreen } from "./ArtifactPreviewScreen";
import { ArtifactsRegistry } from "./ArtifactsRegistry";
import { ContractsDrift } from "./ContractsDrift";
import { Dashboard } from "./Dashboard";
import { ExportPublish } from "./ExportPublish";
import { GapReportScreen } from "./GapReportScreen";
import { OfflineTakeover } from "./OfflineTakeover";
import { OnboardingHub } from "./OnboardingHub";
import { RunTranscriptScreen } from "./RunTranscriptScreen";
import { badgeFor, fileKindLabel, guessAdoptType, SourceDocuments } from "./SourceDocuments";
import type { SourceDocument } from "../../types";
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
  it("distinguishes text / images-only / empty instead of a blanket 'Extracted'", () => {
    expect(badgeFor({ ...base, fidelity: "text" }).label).toBe("Extracted");
    expect(badgeFor({ ...base, fidelity: "images_only" }).label).toBe("Needs AI read");
    expect(badgeFor({ ...base, fidelity: "empty" }).label).toBe("No text found");
    expect(badgeFor({ ...base, status: "adopted" }).label).toBe("Adopted");
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
    expect(screen.getByText("Can't publish — not gate-approved")).toBeDefined();
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
