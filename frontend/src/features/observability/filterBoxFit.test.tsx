// @vitest-environment jsdom
/**
 * N — a filter box cut the choice it was showing.
 *
 * These are the browser's own dropdowns, and the open list is fine: the browser widens it to the
 * longest choice. The closed box was the problem — `.select` is full-width, so every filter row
 * capped each box with a fixed `max-width` picked by eye, and the box then cut the chosen value
 * with no ellipsis and no way to read the rest ("Intelligent Context Extra…", "Waiting for
 * approva…"). The team chose N-A: each box sizes itself to its content.
 *
 * jsdom does no layout, so what is pinned here is the rule rather than the pixels — that no filter
 * carries a hand-picked width any more, and that they all opt into sizing to their content.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { ArtifactsRegistry } from "./ArtifactsRegistry";
import { WorkItemsBoard } from "../lifecycle/WorkItemsBoard";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "product_owner" }],
};

const ARTIFACT = {
  id: "a1", project: "p1", run: "r1", phase: "00c_intelligent_context_extractor",
  type: "codebase_intelligence", title: "Codebase intelligence", status: "staged",
  sor: "internal", s3_key: "k", content_hash: "h", version: 1,
  created_at: "2026-09-01T00:00:00Z", previewable: true, external_ref: {},
};

const CARD = {
  id: "w1", key: "WI-1", number: 1, project: "p1", type: "story", state: "in_progress",
  title: "Basket totals", created_at: "2026-09-01T00:00:00Z",
  current_phase: "00c_intelligent_context_extractor", run_status: "running", needs: null,
};

function stub() {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/artifacts/")) return ok([ARTIFACT]);
    if (u.includes("/work-items")) return ok([CARD]);
    return ok([]);
  }));
}

/** The inline `max-width` these boxes used to carry, and the class that replaces it. */
function expectFits(select: HTMLElement) {
  expect(select.className).toContain("select--fit");
  expect(select.style.maxWidth).toBe("");
}

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the Artifacts filters", () => {
  it("size themselves to their longest choice", async () => {
    stub();
    renderWithProviders(<ArtifactsRegistry />);

    await waitFor(() => expect(screen.getByText("Codebase intelligence")).toBeDefined());
    for (const label of ["Filter by phase", "Filter by type", "Filter by status"]) {
      expectFits(screen.getByLabelText(label));
    }
    // The choice that was being cut is present in full.
    expect(screen.getByRole("option", { name: "Waiting for approval" })).toBeDefined();
    expect(screen.getByRole("option", { name: "Context Extraction" })).toBeDefined();
  });
});

describe("the Work Items filters", () => {
  it("do the same", async () => {
    stub();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Basket totals")).toBeDefined());
    for (const label of ["Filter by phase", "Filter by role", "Filter by status"]) {
      // The app's own dropdown since 2026-10-08, so the box is a button — still sized to fit.
      expectFits(screen.getByRole("button", { name: label }));
    }
  });
});
