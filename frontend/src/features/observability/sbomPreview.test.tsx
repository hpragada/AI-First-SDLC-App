// @vitest-environment jsdom
//
// Bugs S.No 187 — a machine-readable artifact (a CycloneDX SBOM) is RENDERED for people and
// the raw file is kept. Kept where nobody could see it, though: there is no download and the
// publish step is the only other reader. These cover the "View raw" control that makes the
// stored file reachable, and the promise that the rendered view is never mistaken for it.
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import type { ArtifactPreview } from "../../types";
import { ArtifactPreviewScreen } from "./ArtifactPreviewScreen";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const RAW = '{"bomFormat":"CycloneDX","components":[{"name":"django","version":"5.1.4"}]}';

const RENDERED: ArtifactPreview = {
  body: "| Package | Version |\n| --- | --- |\n| django | 5.1.4 |\n",
  content_type: "text/markdown", status: "draft", version: 1,
  title: "SBOM", versions: [], artifact_type: "sbom", phase: "security",
  source: "", rendered: true,
  render_summary: { components: 1, licences: 1, tool: "syft 1.9.0",
                    taken: "2026-09-04T11:22:08Z", spec_version: "1.5" },
};

const RAW_PAYLOAD: ArtifactPreview = {
  ...RENDERED, body: RAW, content_type: "application/json", rendered: false,
};

/** Routes by URL so AuthProvider settles unauthenticated, and by `?raw=1` so the toggle
 *  really exercises the second request rather than a re-render of the same payload. */
function renderPreview(rendered: ArtifactPreview, raw: ArtifactPreview = RAW_PAYLOAD) {
  const authStub = stubFetchJson(401, { detail: "no session" });
  const renderedStub = stubFetchJson(200, rendered);
  const rawStub = stubFetchJson(200, raw);
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/")) return authStub();
      return url.includes("raw=1") ? rawStub() : renderedStub();
    }),
  );
  return renderWithProviders(
    <Routes>
      <Route path="/artifacts/:id" element={<ArtifactPreviewScreen />} />
    </Routes>,
    { route: "/artifacts/a1" },
  );
}

describe("S-29 preview · machine-readable artifacts", () => {
  it("shows the readable report first, with a way to reach the stored file", async () => {
    renderPreview(RENDERED);
    await waitFor(() => expect(screen.getByText("Components")).toBeDefined());
    // The headline figures render as labelled numbers, not a run-on line of prose.
    expect(screen.getByText("Scanned by")).toBeDefined();
    expect(screen.getByText("syft 1.9.0")).toBeDefined();
    // ...and the timestamp is formatted for a person, never shown as a raw ISO string.
    expect(document.body.textContent ?? "").not.toContain("2026-09-04T11:22:08Z");
    expect(screen.getByRole("button", { name: "View raw" })).toBeDefined();
    // The raw file is NOT on screen until asked for.
    expect(screen.queryByText(/bomFormat/)).toBeNull();
  });

  it("swaps to the stored file, and back", async () => {
    const user = userEvent.setup();
    renderPreview(RENDERED);
    await waitFor(() => expect(screen.getByRole("button", { name: "View raw" })).toBeDefined());

    await user.click(screen.getByRole("button", { name: "View raw" }));
    await waitFor(() => expect(screen.getByText(/bomFormat/)).toBeDefined());
    expect(screen.getByText(/exactly as it was saved/)).toBeDefined();

    // The control must not vanish once used — going back is the whole point of a toggle.
    await user.click(screen.getByRole("button", { name: "View report" }));
    await waitFor(() => expect(screen.getByText("Components")).toBeDefined());
    expect(screen.queryByText(/bomFormat/)).toBeNull();
  });

  it("offers nothing extra on an ordinary document", async () => {
    renderPreview({ ...RENDERED, body: "# PRD\n\nSome prose.", artifact_type: "prd",
                    title: "PRD", rendered: false, render_summary: null });
    await waitFor(() => expect(screen.getByText(/Some prose/)).toBeDefined());
    expect(screen.queryByRole("button", { name: "View raw" })).toBeNull();
    // and the usual read-through banner is untouched
    expect(screen.getByText(/Read-through from the system-of-record/)).toBeDefined();
  });
});
