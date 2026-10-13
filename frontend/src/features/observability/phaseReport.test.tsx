// @vitest-environment jsdom
//
// The platform files the engine's closing message as a phase-typed artifact whatever that
// message says (orchestration.activities.PHASE_REPORT_SOURCE). The 2026-07-30 fix stamped it
// and stopped a review gate opening on it — but the marker never reached the UI, so a failed
// run's status text still rendered as "Requirements — SPENDLog · draft" with a list of
// unanswered clarification questions in the body. These cover the display half.
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import { isPhaseReport, PHASE_REPORT_ARTIFACT } from "../../types";
import type { Artifact, ArtifactPreview } from "../../types";
import { ArtifactPreviewScreen } from "./ArtifactPreviewScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function artifact(over: Partial<Artifact> = {}): Artifact {
  return {
    id: "a1", project: "p1", run: "r1", phase: "requirements", type: "requirements",
    title: "Requirements — SPENDLog", status: "draft", sor: "internal", s3_key: "k",
    content_hash: "h", version: 1, created_at: "2026-08-03T00:00:00Z", ...over,
  };
}

describe("isPhaseReport", () => {
  it("flags the platform's own copy on a registry row", () => {
    expect(isPhaseReport(artifact({ external_ref: { source: PHASE_REPORT_ARTIFACT } }))).toBe(true);
  });

  it("leaves a real agent-registered artifact alone", () => {
    expect(isPhaseReport(artifact())).toBe(false);
    expect(isPhaseReport(artifact({ external_ref: null }))).toBe(false);
    // A multi-repo work item carries external_ref with no `source` — must not be mistaken
    // for the platform's copy (that exact confusion cost Bugs S.No 142 a whole Jira push).
    expect(isPhaseReport(artifact({ external_ref: { sor: "jira", id: "ST-1" } }))).toBe(false);
  });

  it("reads the flattened `source` the preview payload uses", () => {
    expect(isPhaseReport({ source: PHASE_REPORT_ARTIFACT })).toBe(true);
    expect(isPhaseReport({ source: "" })).toBe(false);
  });

  it("keeps the marker string identical to the backend's", () => {
    // Shared with orchestration.activities.PHASE_REPORT_SOURCE — a contract, not a label.
    expect(PHASE_REPORT_ARTIFACT).toBe("phase_report");
  });
});

function preview(over: Partial<ArtifactPreview> = {}): ArtifactPreview {
  return {
    body: "The platform's database is currently unavailable (PostgreSQL connection error).",
    content_type: "text/markdown", status: "draft", version: 1,
    title: "Requirements — SPENDLog", versions: [], artifact_type: "requirements",
    phase: "requirements", source: "", ...over,
  };
}

function renderPreview(data: ArtifactPreview) {
  // Route by URL: AuthProvider must settle to "unauthenticated" (as every other screen test
  // assumes) while the preview request gets the real payload. A single-response stub would
  // hand this artifact body to /auth/me/ and crash AuthProvider on `memberships`.
  const authStub = stubFetchJson(401, { detail: "no session" });
  const previewStub = stubFetchJson(200, data);
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) =>
      String(input).includes("/auth/") ? authStub() : previewStub(),
    ),
  );
  return renderWithProviders(
    <Routes>
      <Route path="/artifacts/:id" element={<ArtifactPreviewScreen />} />
    </Routes>,
    { route: "/artifacts/a1" },
  );
}

describe("S-29 preview · the platform's copy is not a deliverable", () => {
  it("warns instead of presenting a phase_report as a read-through document", async () => {
    renderPreview(preview({ source: PHASE_REPORT_ARTIFACT }));
    await waitFor(() =>
      expect(screen.getByText(/Run output — not a deliverable/)).toBeDefined(),
    );
    expect(screen.getByText(/not an artifact the agent saved/)).toBeDefined();
    expect(screen.getByText(/Re-run the phase/)).toBeDefined();
    // The reassuring read-through copy must NOT appear on a failed run's status message.
    expect(screen.queryByText(/Read-through from the system-of-record/)).toBeNull();
  });

  it("leaves a genuine artifact's read-through banner untouched", async () => {
    renderPreview(preview());
    await waitFor(() =>
      expect(screen.getByText(/Read-through from the system-of-record/)).toBeDefined(),
    );
    expect(screen.queryByText(/Run output — not a deliverable/)).toBeNull();
  });
});
