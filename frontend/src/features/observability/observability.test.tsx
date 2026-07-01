// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

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
import { SourceDocuments } from "./SourceDocuments";
import { TraceabilityView } from "./TraceabilityView";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(stubFetchJson(401, { detail: "no session" })));
});
afterEach(() => vi.unstubAllGlobals());

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
