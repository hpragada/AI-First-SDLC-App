// @vitest-environment jsdom
/**
 * Bugs S.No 218 — a document waiting for you read "Draft", and two messages that were wrong.
 *
 * Opening a gate did not change a document's status at all, so a planning document sitting at an
 * open gate read "Draft" — indistinguishable from a draft nobody had looked at. The platform now
 * marks it `staged` when the gate opens, and the team chose option A for the words: "Waiting for
 * approval". Three screens read one shared map, so they change together: the Artifacts list, the
 * preview screen, and the traceability map (whose own copy knew only two statuses, so approved,
 * waiting and superseded documents all drew as "Draft").
 *
 * The preview: "no such document" and "its body can't be read" were one 404, worded as three
 * explanations at once. They are now two answers, each true.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { ArtifactPreviewScreen } from "./ArtifactPreviewScreen";
import { ArtifactsRegistry } from "./ArtifactsRegistry";
import { ARTIFACT_STATUSES, artifactStatusBadge, artifactStatusLabel } from "./artifactStatus";
import { TraceabilityView } from "./TraceabilityView";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Checkout", role: "product_owner" }],
};

/** Answers the first route whose needle is in the URL — order matters ("/preview/" before
 *  "/artifacts/"). */
function stub(routes: Array<[string, number, unknown]>) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const res = (status: number, body: unknown) =>
      ({ ok: status < 400, status, statusText: "stub",
         text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return res(200, me);
    for (const [needle, status, body] of routes) if (u.includes(needle)) return res(status, body);
    return res(200, []);
  }));
}

const preview = (over: Record<string, unknown> = {}) => ({
  body: "", content_type: "", status: "staged", version: 1, title: "PRD — Checkout",
  versions: [], sor_link: null, phase: "prd", artifact_type: "prd", export_target: null,
  states: [], source: "", rendered: false, render_summary: {}, ...over,
});

function openPreview() {
  return renderWithProviders(
    <Routes>
      <Route path="/artifacts/:id" element={<ArtifactPreviewScreen />} />
    </Routes>,
    { route: "/artifacts/a1" },
  );
}

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the status words (option A)", () => {
  it("calls a document at an open gate 'Waiting for approval'", () => {
    render(<>{artifactStatusBadge("staged")}</>);
    expect(screen.getByText("Waiting for approval")).toBeDefined();
    expect(screen.queryByText(/Staged|Pending gate/)).toBeNull();
  });

  it("has a word for every status an artifact can have", () => {
    expect(ARTIFACT_STATUSES.map(artifactStatusLabel)).toEqual(
      ["Published", "Approved", "Waiting for approval", "Draft", "Superseded"]);
  });
});

describe("the Artifacts list", () => {
  it("shows the waiting document in words, and filters by the same words", async () => {
    stub([["/artifacts/", 200, [{
      id: "a1", project: "p1", run: "r1", phase: "prd", type: "prd", title: "PRD — Checkout",
      status: "staged", sor: "internal", s3_key: "k", content_hash: "h", version: 1,
      created_at: "2026-09-01T00:00:00Z", previewable: true, external_ref: {},
    }]]]);
    renderWithProviders(<ArtifactsRegistry />);

    await waitFor(() => expect(screen.getByText("PRD — Checkout")).toBeDefined());
    expect(screen.getAllByText("Waiting for approval").length).toBeGreaterThan(0);
    expect(screen.getByRole("option", { name: "Waiting for approval" })).toBeDefined();
    expect(screen.queryByText("Staged")).toBeNull();
  });
});

describe("the traceability map", () => {
  const node = (id: string, title: string, status: string) => ({
    id, kind: "artifact", phase: "prd", type: "prd", title, status, sor: "internal",
    external_ref: null, url: null,
  });

  it("explains every status in its legend, and draws each node in that status's colour", async () => {
    stub([["/traceability/", 200, {
      nodes: [node("a1", "PRD — Checkout", "staged"), node("a2", "Architecture", "approved")],
      edges: [],
    }]]);
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(document.querySelectorAll("svg g[role=button]").length).toBe(2));
    // Only the statuses on the map are explained (2026-10-08).
    const legend = document.querySelector(".graph-legend") as HTMLElement;
    for (const word of ["Approved", "Waiting for approval"]) {
      expect(legend.textContent).toContain(word);
    }
    for (const word of ["Published", "Draft", "Superseded"]) {
      expect(legend.textContent).not.toContain(word);
    }
    expect(legend.textContent).not.toContain("Pending gate");

    const byTitle = (text: string) => [...document.querySelectorAll("svg g[role=button]")]
      .find((g) => g.querySelector("title")?.textContent?.startsWith(text)) as SVGGElement;
    const waiting = byTitle("PRD — Checkout");
    expect(waiting.querySelector("title")?.textContent).toContain("Waiting for approval");
    expect((waiting.querySelector("rect") as SVGRectElement).style.stroke).toBe("var(--warning)");
    // Approved used to draw in the Draft colour.
    expect((byTitle("Architecture").querySelector("rect") as SVGRectElement).style.stroke)
      .toBe("var(--brand-navy-500)");
    // The machine token is never printed.
    expect(document.body.textContent).not.toMatch(/· staged|· approved/);
  });
});

describe("the preview screen's messages", () => {
  it("says plainly when there is no such document — one explanation, not three", async () => {
    stub([["/preview/", 404, { detail: "Not found." }]]);
    openPreview();

    expect(await screen.findByText("We couldn't find that document")).toBeDefined();
    expect(screen.getByText(/may have been removed, or you may not have access/)).toBeDefined();
    expect(screen.queryByText(/doesn't exist, has no body/)).toBeNull();
  });

  it("says 'Preview unavailable' when the document exists but its body can't be read", async () => {
    stub([["/preview/", 200, preview()]]);
    openPreview();

    expect(await screen.findByText("Preview unavailable")).toBeDefined();
    expect(screen.getByText(/Its record and version are intact/)).toBeDefined();
    expect(screen.queryByText("We couldn't find that document")).toBeNull();
  });

  it("does not call a failed request a missing document", async () => {
    stub([["/preview/", 500, { detail: "boom" }]]);
    openPreview();

    expect(await screen.findByText(/Something went wrong on our side/)).toBeDefined();
    expect(screen.queryByText("We couldn't find that document")).toBeNull();
  });

  it("names every version's status in words", async () => {
    stub([["/preview/", 200, preview({
      body: "# PRD", content_type: "text/markdown",
      versions: [
        { artifact_id: "a1", version: 2, status: "staged", run_id: "r2", created_at: "2026-09-02T00:00:00Z" },
        { artifact_id: "a0", version: 1, status: "superseded", run_id: "r1", created_at: "2026-09-01T00:00:00Z" },
      ],
    })]]);
    openPreview();

    await waitFor(() => expect(screen.getByText("Version history")).toBeDefined());
    expect(screen.getAllByText("Waiting for approval").length).toBe(2);   // badge + v2's row
    expect(screen.getByText("Superseded")).toBeDefined();
    expect(screen.queryByText("staged")).toBeNull();
    expect(screen.queryByText("superseded")).toBeNull();
  });
});
