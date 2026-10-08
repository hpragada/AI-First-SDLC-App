// @vitest-environment jsdom
//
// 2026-10-08 — Connect Machine after Disconnect.
//
// Disconnect cancelled only the newest of the machine's keys, so the page fell back to an older
// key and said "Offline · last seen 16m ago" — that older key's heartbeat, not the disconnect.
// Disconnect now cancels them all (backend), and the page says when it happened: green right
// after the click, a quiet note with the date on any later visit. Every time on the page is
// worded by one rule (`when.ts`), in the viewer's own time zone.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { ConnectMachine } from "./ConnectMachine";
import { fullWhen, whenLabel } from "./when";

const ME = {
  user: { id: "u1", email: "dev@acme.test", name: "Dev", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "PeopleDesk", role: "engineer" }],
};

function stubApi({ runners, disconnectedAt }: { runners: unknown[]; disconnectedAt: string | null }) {
  let current = runners;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const json = (status: number, body: unknown) =>
      ({ ok: status < 400, status, statusText: "stub", text: async () => JSON.stringify(body) }) as Response;
    if (url.includes("/auth/me")) return json(200, ME);
    if (url.includes("/last-disconnect")) return json(200, { disconnected_at: disconnectedAt });
    if (url.includes("/revoke")) {
      current = [];
      disconnectedAt = new Date().toISOString();
      return json(200, { status: "revoked" });
    }
    if (url.includes("/runners") && (init?.method ?? "GET") === "GET") return json(200, current);
    return json(401, { detail: "no session" });
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Connect Machine · after Disconnect", () => {
  it("lands on setup and says, in green, that it was disconnected just now", async () => {
    const live = { id: "r1", machine: "", last_seen: new Date().toISOString(), online: true, projects: [] };
    stubApi({ runners: [live], disconnectedAt: null });
    const user = userEvent.setup();
    renderWithProviders(<ConnectMachine />);

    await user.click(await screen.findByRole("button", { name: /disconnect machine/i }));

    const note = await screen.findByText(/disconnected just now/);
    expect(note.className).toContain("disconnect-note--fresh");
    // Not the old fallback that showed another key's heartbeat.
    expect(screen.queryByText(/Offline/)).toBeNull();
    expect(screen.getByRole("button", { name: /generate enrollment token/i })).toBeDefined();
  });

  it("on a later visit, says when as a quiet note, with the full time on hover", async () => {
    const iso = "2025-07-08T09:09:00Z";
    stubApi({ runners: [], disconnectedAt: iso });
    renderWithProviders(<ConnectMachine />);

    const note = await screen.findByText(/Your machine was disconnected/);
    expect(note.className).not.toContain("disconnect-note--fresh");
    expect(note.textContent).toBe(`Your machine was disconnected ${whenLabel(iso)}.`);
    expect(note.querySelector("time")?.getAttribute("title")).toBe(fullWhen(iso));
  });

  it("says nothing about a disconnect when none is recorded", async () => {
    stubApi({ runners: [], disconnectedAt: null });
    renderWithProviders(<ConnectMachine />);

    await screen.findByRole("button", { name: /generate enrollment token/i });
    await waitFor(() => expect(screen.queryByText(/disconnected/)).toBeNull());
  });

  it("no longer promises anything about API keys or billing in the sub-heading", async () => {
    stubApi({ runners: [], disconnectedAt: null });
    renderWithProviders(<ConnectMachine />);

    await screen.findByRole("button", { name: /generate enrollment token/i });
    expect(document.body.textContent).not.toMatch(/no API\s+key/);
    expect(document.body.textContent).toMatch(/Two one-time steps, like pairing a device\./);
  });
});

describe("the time wording (when.ts)", () => {
  // Local-time construction, so these hold in any time zone the suite runs in.
  const now = new Date(2026, 9, 8, 14, 49);     // Thu 8 Oct 2026, 2:49 PM local
  const at = (y: number, mo: number, d: number, h = 14, mi = 39) =>
    new Date(y, mo, d, h, mi).toISOString();

  it("follows the agreed table", () => {
    expect(whenLabel(new Date(now.getTime() - 20_000).toISOString(), now)).toBe("just now");
    expect(whenLabel(at(2026, 9, 8), now)).toBe("today at 2:39 PM");
    expect(whenLabel(at(2026, 9, 7), now)).toBe("yesterday at 2:39 PM");
    expect(whenLabel(at(2026, 9, 5), now)).toBe("on Monday at 2:39 PM");
    expect(whenLabel(at(2026, 8, 8), now)).toBe("on 8 Sep");
    expect(whenLabel(at(2025, 6, 8), now)).toBe("on 8 Jul 2025");
  });

  it("gives the full date, time and zone for the hover", () => {
    expect(fullWhen(at(2025, 6, 8))).toMatch(/^8 Jul 2025, 2:39 PM \S+/);
  });

  it("says nothing it cannot back up", () => {
    expect(whenLabel(null, now)).toBeNull();
    expect(whenLabel("not a date", now)).toBeNull();
  });
});
