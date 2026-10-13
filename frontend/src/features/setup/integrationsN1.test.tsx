// @vitest-environment jsdom
/**
 * N1 — Code intelligence removed from the Integrations grid.
 *
 * Its card was hard-wired to read "Connected · Built-in" whatever the platform knew. It was not a
 * control — there is nothing to connect; the analyser runs on the developer's own machine — and on
 * a real workspace, which was only ever given the accessibility capability automatically, it could
 * say "Connected" about a record that did not exist. It is now provisioned automatically like
 * accessibility, and like accessibility it is not on this grid. The team chose option A: the other
 * five cards stay exactly as they were.
 *
 * Found with it: the connect page read its capability straight from the address with no check, so
 * `/integrations/codeintel` — an old bookmark — or any typo drew a full page with an undefined title.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { ConnectCapability } from "./ConnectCapability";
import { Integrations } from "./Integrations";

const FIVE = ["Documentation store", "Task tracker", "Design source", "Code host", "Test management"];

const row = (capability: string, status: string, extra: Record<string, unknown> = {}) => ({
  id: `i-${capability}`, capability, connector: "x", vendor: "Vendor", status,
  configured: status === "connected", binding: {}, ...extra,
});

function stub(integrations: unknown[]) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const body = u.includes("/integrations/catalog/") ? [] : u.includes("/integrations/") ? integrations : [];
    return { ok: true, status: 200, statusText: "ok",
             text: async () => JSON.stringify(body) } as Response;
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the Integrations grid", () => {
  it("shows the five capabilities a person connects, and no Code intelligence card", async () => {
    stub([row("docstore", "connected"), row("codeintel", "connected", { vendor: "Built-in" })]);
    renderWithProviders(<Integrations />);

    await waitFor(() => expect(screen.getByText("Documentation store")).toBeDefined());
    for (const label of FIVE) expect(screen.getByText(label)).toBeDefined();
    expect(screen.queryByText("Code intelligence")).toBeNull();
    expect(screen.queryByText("Built-in")).toBeNull();
  });

  it("is not collapsed by a failure on a capability it does not show", async () => {
    // A failed row collapses the grid to that one card, so a failure on an automatically
    // provisioned capability must not collapse it to a card that is no longer drawn.
    stub([row("codeintel", "failed", { fail_reason: "no analyser" })]);
    renderWithProviders(<Integrations />);

    await waitFor(() => expect(screen.getByText("Documentation store")).toBeDefined());
    for (const label of FIVE) expect(screen.getByText(label)).toBeDefined();
    expect(screen.queryByText("no analyser")).toBeNull();
  });
});

describe("an address naming a capability the grid does not offer", () => {
  function at(route: string) {
    return renderWithProviders(
      <Routes>
        <Route path="/integrations" element={<Integrations />} />
        <Route path="/integrations/:capability" element={<ConnectCapability />} />
      </Routes>,
      { route },
    );
  }

  it("goes back to the grid instead of drawing a page with no title", async () => {
    stub([]);
    at("/integrations/codeintel");

    expect(await screen.findByRole("heading", { name: "Integrations" })).toBeDefined();
    expect(screen.queryByText("Connect a capability")).toBeNull();
  });

  it("still opens the connect page for a real capability", async () => {
    stub([]);
    at("/integrations/docstore");

    expect(await screen.findByText("Connect a capability")).toBeDefined();
  });
});
