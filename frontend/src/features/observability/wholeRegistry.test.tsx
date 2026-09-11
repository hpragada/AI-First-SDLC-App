// @vitest-environment jsdom
/**
 * "Show the whole registry" did nothing (QA, 11 Sep).
 *
 * A gate's Preview link opens the Artifacts screen narrowed to what one phase, run or work item
 * produced, with a banner saying so and a button to see everything. The button is a link to plain
 * `/artifacts` — and the screen ignored it: the scope was read through a helper built for a list's
 * selection, which deliberately keeps its last value when the parameter leaves the address. So the
 * address changed and the screen stayed narrowed. The scope is now read from the address itself.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { ArtifactsRegistry } from "./ArtifactsRegistry";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "reviewer" }],
};

const artifact = (id: string, title: string, phase: string) => ({
  id, project: "p1", run: "r1", phase, type: "code_review", title, status: "draft",
  sor: "internal", s3_key: "k", content_hash: "h", version: 1,
  created_at: "2026-09-01T00:00:00Z", previewable: true, external_ref: {},
});
const REVIEW = artifact("a1", "Code Review — PR #34 · Cycle 3", "Code Review");
const PRD = artifact("a2", "PRD — Checkout", "PRD");

let asked: string[] = [];

/** Answers like the API does: a scoped request gets `scoped`, an unscoped one gets everything. */
function stub(scoped: unknown[]) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/artifacts/")) {
      asked.push(u);
      return ok(/[?&](phase|run|type|work_item)=/.test(u) ? scoped : [REVIEW, PRD]);
    }
    return ok([]);
  }));
}

function openAt(route: string) {
  return renderWithProviders(
    <>
      {/* A second deep link on the page, to prove a NEW scope still takes after clearing one. */}
      <Link to="/artifacts?run=r1">another deep link</Link>
      <Routes>
        <Route path="/artifacts" element={<ArtifactsRegistry />} />
      </Routes>
    </>,
    { route },
  );
}

const lastAsked = () => asked[asked.length - 1] ?? "";

beforeEach(() => {
  localStorage.setItem("selectedProjectId", "p1");
  asked = [];
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("Show the whole registry", () => {
  it("clears the scope a gate's Preview link applied, and shows everything", async () => {
    stub([REVIEW]);
    const user = userEvent.setup();
    openAt("/artifacts?phase=Code%20Review");

    // Wait for the narrowed LIST, not just the banner — the banner is drawn from the address before
    // the request has even gone out.
    await waitFor(() => expect(screen.getByText("Code Review — PR #34 · Cycle 3")).toBeDefined());
    expect(screen.getByText("Showing part of the registry")).toBeDefined();
    expect(screen.queryByText("PRD — Checkout")).toBeNull();
    expect(lastAsked()).toContain("phase=Code");

    await user.click(screen.getByRole("link", { name: "Show the whole registry" }));

    await waitFor(() => expect(screen.getByText("PRD — Checkout")).toBeDefined());
    expect(screen.getByText("Code Review — PR #34 · Cycle 3")).toBeDefined();
    expect(screen.queryByText("Showing part of the registry")).toBeNull();
    expect(lastAsked()).not.toMatch(/[?&](phase|run|type|work_item)=/);
  });

  it("works for a work item's scope too", async () => {
    stub([REVIEW]);
    const user = userEvent.setup();
    openAt("/artifacts?work_item=w1");

    await user.click(await screen.findByRole("link", { name: "Show the whole registry" }));

    await waitFor(() => expect(screen.getByText("PRD — Checkout")).toBeDefined());
    expect(screen.queryByText("Showing part of the registry")).toBeNull();
  });

  it("also works from the 'nothing matched' panel", async () => {
    stub([]);
    const user = userEvent.setup();
    openAt("/artifacts?run=r9");

    await waitFor(() => expect(screen.getByText("Nothing matched this filter")).toBeDefined());
    // Two buttons with this name — the banner's and the empty panel's. Use the panel's.
    const buttons = screen.getAllByRole("link", { name: "Show the whole registry" });
    await user.click(buttons[buttons.length - 1]);

    await waitFor(() => expect(screen.getByText("PRD — Checkout")).toBeDefined());
    expect(screen.queryByText("Nothing matched this filter")).toBeNull();
  });

  it("still lets a later deep link narrow the registry again", async () => {
    stub([REVIEW]);
    const user = userEvent.setup();
    openAt("/artifacts?phase=Code%20Review");

    await user.click(await screen.findByRole("link", { name: "Show the whole registry" }));
    await waitFor(() => expect(screen.getByText("PRD — Checkout")).toBeDefined());
    await user.click(screen.getByRole("link", { name: "another deep link" }));

    await waitFor(() => expect(screen.getByText("Showing part of the registry")).toBeDefined());
    expect(lastAsked()).toContain("run=r1");
  });
});
