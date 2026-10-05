// @vitest-environment jsdom
//
// S.No 317/318/319 — three screens that stated something untrue, found in the 2026-10-05 live
// pass. They share a cause with S.No 306-311: each was truthful about its own data and wrong
// about the world.
//
//   317  a document with no content of its own showed the RUN's report under its own title
//   318  "Waiting for approval" on documents whose gate had already been decided and removed
//   319  a notice offering to send you where you already are
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { artifactStatusBadge } from "./artifactStatus";
import { Clarifications } from "../lifecycle/Clarifications";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

// ── 318 · the status stops promising a decision nobody can give ─────────────
describe("S.No 318 · a document whose gate is already decided", () => {
  it("does not invite an approval that no longer exists", () => {
    const { container } = render318(true);
    expect(container.textContent).toContain("Approved");
    expect(container.textContent).not.toContain("Waiting for approval");
  });

  it("still says 'Waiting for approval' while the gate is genuinely open", () => {
    const { container } = render318(false);
    expect(container.textContent).toContain("Waiting for approval");
  });

  it("leaves a published document alone", () => {
    const { container } = renderWithProviders(
      <>{artifactStatusBadge("published", true)}</>);
    expect(container.textContent).toContain("Published");
  });
});

function render318(gateDecided: boolean) {
  return renderWithProviders(<>{artifactStatusBadge("staged", gateDecided)}</>);
}

// ── 319 · the notice knows when it has done its job ─────────────────────────
const PROJECT = "22222222-2222-2222-2222-222222222222";
const ME = {
  user: { id: "u1", email: "a@b.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "PeopleDesk", role: "product_owner" }],
};

function stubEmpty() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = /\/auth\/me\//.test(url) ? ME : [];
    return {
      ok: true, status: 200, statusText: "stub",
      text: async () => JSON.stringify(body),
    } as Response;
  });
}

describe("S.No 319 · arriving from a link to an answered question", () => {
  it("explains itself, then stops once you have followed it", async () => {
    localStorage.setItem("selectedProjectId", PROJECT);
    vi.stubGlobal("fetch", stubEmpty());
    renderWithProviders(<Clarifications />, { route: "/clarifications?clarification=gone" });

    // On the questions tab the notice is doing real work: it stops you hunting for a form that
    // is no longer there.
    expect(await screen.findByText(/already been answered/)).toBeTruthy();
    const go = await screen.findByRole("button", { name: /answered history/i });

    await userEvent.click(go);

    // Having arrived, it has nothing left to say — and its button, which only switches to the
    // tab you are now on, would do nothing at all when pressed. That was the defect.
    expect(screen.queryByText(/already been answered/)).toBeNull();
  });
});
