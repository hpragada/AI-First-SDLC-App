// @vitest-environment jsdom
//
// S-38 — Pages & audit (task 8a).
//
// The brownfield way in: register the pages of an application the platform cannot see, and run
// an audit on a machine that can. These assert the sentences, because every state here is a
// place where a screen that rendered "successfully" could still mislead — an empty page list
// that reads as an application with no pages, an audit that failed for a reason nobody is told,
// a corrected path that quietly becomes a second page, or a scope that shrank between two
// audits whose numbers are then compared as though they measured the same thing.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { A11yAudit } from "./A11yAudit";

const PROJECT = "11111111-1111-1111-1111-111111111111";

const ME = {
  user: { id: "u1", email: "aisha@acme.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "Meridian", role: "qa_lead" }],
};

function stubRoutes(routes: Array<[RegExp, unknown, number?]>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    void init;
    for (const [pattern, body, status = 200] of routes) {
      if (pattern.test(url)) {
        return {
          ok: status < 400,
          status,
          statusText: "stub",
          text: async () => JSON.stringify(body),
        } as Response;
      }
    }
    return { ok: false, status: 404, statusText: "stub", text: async () => "{}" } as Response;
  });
}

const CONNECTED = [{ id: "r1", machine: "dev-1", last_seen: "2026-08-18T14:00:00Z", online: true, projects: [] }];

function authed(runners: unknown = CONNECTED): Array<[RegExp, unknown, number?]> {
  return [
    [/\/auth\/me\//, ME],
    [/\/runners\//, runners],
    [/\/dashboard\//, { needs_me: { gates: [], clarifications: [] } }],
    [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15 }],
  ];
}

function route(over: Record<string, unknown> = {}) {
  return {
    id: "route-1",
    path: "/catalogue",
    label: "Browse the catalogue",
    source: "manual",
    enabled: true,
    notes: "",
    example_path: "",
    last_visited: "2026-08-18T14:02:00Z",
    open_findings: 0,
    visits: 1,
    ...over,
  };
}

function routesBody(over: Record<string, unknown> = {}) {
  return {
    routes: [route()],
    summary: "1 route(s) registered for audit",
    scope_change: {},
    // The QA Lead's view by default. The read-only view is asserted on its own below, because
    // it is a state in its own right rather than the absence of one.
    can_manage: true,
    ...over,
  };
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", PROJECT);
});
afterEach(() => {
  // vitest runs without `globals: true` here, so RTL's automatic cleanup is not wired up and
  // every render would otherwise stack in one document.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("S-38 pages and audit", () => {
  it("empty · says the platform cannot discover the pages, rather than showing none", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ routes: [], summary: "no routes are registered" })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // The distinction this screen exists to make. "No pages" could mean an application with no
    // pages; it means nobody has said what they are, and the reason is deliberate.
    expect(await screen.findByText("No pages are registered yet")).toBeTruthy();
    expect(screen.getByText(/cannot discover its pages/)).toBeTruthy();
    // No run strip at all — running an audit over nothing would report no problems, which
    // reads exactly like an application with none.
    expect(screen.queryByRole("button", { name: "Run audit" })).toBeNull();
    // Both ways in are offered from empty: import a list, or add one page (task 8b).
    expect(screen.getByRole("button", { name: "Import a list" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add a page" })).toBeTruthy();
  });

  it("default · shows the pages, the passes, and what will be visited", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({
        routes: [route(), route({ id: "r2", path: "/admin/debug", label: "Internal debug page", enabled: false, last_visited: null })],
      })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("/catalogue")).toBeTruthy();
    expect(screen.getByText("Excluded")).toBeTruthy();
    expect(screen.getByText("Machine connected")).toBeTruthy();
    // One in scope of two registered — the arithmetic is the platform's, not a number the
    // reader has to take on trust.
    expect(screen.getByText("Pages in scope").nextElementSibling?.textContent).toBe("1 of 2");
    // 60 pages per pass, so one pass. Shown so nobody has to guess how a 68-page audit runs.
    expect(screen.getByText("Passes").nextElementSibling?.textContent).toContain("1");
    expect(screen.getByRole("button", { name: "Run audit" })).toBeTruthy();
  });

  it("a page that has never been opened says so instead of showing a blank", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ routes: [route({ last_visited: null })] })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Never visited")).toBeTruthy();
  });

  it("a pattern route says which real page stood in for it", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({
        routes: [route({ path: "/events/:id", label: "Event detail", example_path: "/events/482" })],
      })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // Without this the report would claim a page that cannot be opened had been checked.
    expect(await screen.findByText("checked using /events/482")).toBeTruthy();
  });

  it("blocked · no machine of yours is connected, and it says 'yours'", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed([]),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("You have no machine connected")).toBeTruthy();
    // The app can only see the caller's own enrollments, so it must not claim nobody has one.
    expect(screen.getByText(/only knows about yours/)).toBeTruthy();
  });

  it("the page list moving since the last audit is said before the button, not after", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({
        scope_change: { added: ["/checkout"], removed: ["/basket", "/login"], before: 3, now: 2 },
      })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // Otherwise the next report's Movement section reads as an improvement that is really a
    // smaller measurement.
    expect(await screen.findByText("The page list has changed since the last audit")).toBeTruthy();
    expect(screen.getByText(/1 added · 2 taken out of scope/)).toBeTruthy();
  });

  it("complete · a past audit accounts for the pages that never opened", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "complete", base_url: "http://localhost:4180",
        routes: ["/", "/login"], created_at: "2026-08-18T14:02:00Z",
        summary: { asked: 68, opened: 66, never_reported: ["/x", "/y"] },
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("68 asked for · 66 reported")).toBeTruthy();
    expect(screen.getByText("2 never opened")).toBeTruthy();
  });

  it("failed · the audit says why in the machine's own words", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "failed", base_url: "", routes: ["/"],
        created_at: "2026-08-18T14:02:00Z",
        summary: { asked: 1, opened: 0, reason: "Playwright is not installed in C:/work/meridian" },
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // The generic message blames the application and would send someone to check a server that
    // was never contacted. Said twice on purpose since the panel stays after the run: once in
    // the panel that led the screen, once on the audit's own row under Past audits.
    expect((await screen.findAllByText(/Playwright is not installed/)).length).toBe(2);
    expect(screen.getByText("Audit could not run")).toBeTruthy();
    expect(screen.getAllByText("Could not run").length).toBe(2);
  });

  it("a waiting audit says it is waiting for a machine, not that it is running", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "pending", base_url: "", routes: ["/"],
        created_at: "2026-08-18T14:02:00Z", summary: {},
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // Twice on purpose since the running panel was built: once in the panel that leads the
    // screen, once on the audit's own row under Past audits. Both are the same fact, and a
    // reader looking at either half must not have to go and find the other.
    expect((await screen.findAllByText("Waiting for a machine")).length).toBe(2);
    expect(screen.getByText("Audit running")).toBeTruthy();
  });

  // An audit whose machine went away. Until this, the panel went on saying "Visiting pages"
  // about a laptop that had been switched off — the same silence the panel was built against,
  // wearing the panel's own clothes. The row is closed for real the moment any companion on the
  // project reports in; this is the reading for the machine that never comes back.
  it("an audit nothing has been heard from says so instead of claiming to be running", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "capturing", base_url: "http://localhost:4180",
        routes: ["/", "/login", "/catalogue"],
        created_at: "2026-08-18T14:02:00Z", summary: {},
        progress: { visited: 1, unreachable: 0 }, stalled: true,
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Audit stopped reporting")).toBeTruthy();
    expect(screen.queryByText("Audit running")).toBeNull();
    // How far it actually got, said out loud — the pages it did report are not lost, and
    // knowing there was one is the difference between re-running and going to look for a fault.
    expect(screen.getByText("1 of 3")).toBeTruthy();
  });

  it("an audit that is genuinely running is not called stopped", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "capturing", base_url: "http://localhost:4180",
        routes: ["/", "/login"],
        created_at: "2026-08-18T14:02:00Z", summary: {},
        progress: { visited: 1, unreachable: 0 }, stalled: false,
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Audit running")).toBeTruthy();
    expect(screen.queryByText("Audit stopped reporting")).toBeNull();
  });

  it("an older payload with no stalled field reads as running, not as stopped", async () => {
    // The safe direction: an audit wrongly called stopped would send somebody to restart a run
    // that was working perfectly well.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "capturing", base_url: "http://localhost:4180",
        routes: ["/"], created_at: "2026-08-18T14:02:00Z", summary: {},
        progress: { visited: 1, unreachable: 0 },
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Audit running")).toBeTruthy();
  });

  // A pass that stopped at its own limit. The dispatch always recorded this and nothing on any
  // screen read it, so an audit that never asked about part of what it captured closed as
  // COMPLETE and said nothing at all. Found on the live run of 21 August.
  it("a complete audit that did not check everything says so", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "complete", base_url: "http://localhost:4180",
        routes: ["/", "/login"], created_at: "2026-08-18T14:02:00Z",
        summary: {
          asked: 2, opened: 2, unreachable: [], never_reported: [],
          ai_pass: {
            deferred: 5, dispatched: 200, distinct: 125,
            reason: "Stopped at this run's limit of 200 — 5 item(s) still need judging. Run the check again to continue from here; nothing was skipped.",
          },
        },
        outcome: { problems: 0, critical: 0, high: 0, waiting: 0 },
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Not everything captured was checked")).toBeTruthy();
    expect(screen.getAllByText(/5 item\(s\) still need judging/).length).toBeGreaterThan(0);
  });

  it("a complete audit that checked everything says nothing about limits", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "complete", base_url: "http://localhost:4180",
        routes: ["/"], created_at: "2026-08-18T14:02:00Z",
        summary: {
          asked: 1, opened: 1, unreachable: [], never_reported: [],
          ai_pass: { deferred: 0, dispatched: 12, distinct: 12 },
        },
        outcome: { problems: 0, critical: 0, high: 0, waiting: 0 },
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText(/Audit complete/)).toBeTruthy();
    expect(screen.queryByText("Not everything captured was checked")).toBeNull();
  });

  it("an abandoned audit that has been closed shows the machine's own reason", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [{
        id: "a1", status: "failed", base_url: "http://localhost:4180",
        routes: ["/", "/login"], created_at: "2026-08-18T14:02:00Z",
        summary: {
          asked: 2, opened: 1, unreachable: [], never_reported: ["/login"],
          abandoned: true,
          reason: "the machine visiting the pages stopped reporting — it was closed, restarted or disconnected part-way through.",
        },
      }] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Audit could not run")).toBeTruthy();
    expect(screen.getAllByText(/stopped reporting/).length).toBeGreaterThan(0);
  });
});

describe("S-38 adding pages", () => {
  it("shows what a paste would do before writing any of it", async () => {
    const fetchStub = stubRoutes([
      ...authed(),
      [/a11y-routes\/\?preview=1/, {
        preview: {
          adding: ["/catalogue/results"],
          updating: ["/", "/account/holds"],
          missing: [{ path: "/catalogue/search", label: "Search", enabled: true, open_findings: 3 }],
          ignored_keys: [],
          total_now: 4,
        },
      }],
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]);
    vi.stubGlobal("fetch", fetchStub);
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    await userEvent.click(screen.getByLabelText("Your pages"));
    await userEvent.paste('["/", "/account/holds", "/catalogue/results"]');
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    // The team's own scenario: one path edited, and the platform sees a new page plus one it
    // already has that nobody mentioned. Nothing is written until this is answered.
    expect(await screen.findByText("/catalogue/search")).toBeTruthy();
    expect(screen.getByText(/already have/)).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();   // the problems that would be left behind
    const writes = fetchStub.mock.calls.filter(
      (c) => /a11y-routes/.test(String(c[0])) && !/preview=1/.test(String(c[0]))
        && (c[1] as RequestInit | undefined)?.method === "PUT",
    );
    expect(writes).toHaveLength(0);
  });

  it("warns when a page being dropped would take its recorded problems with it", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes\/\?preview=1/, {
        preview: {
          adding: [], updating: ["/"],
          missing: [{ path: "/checkout", label: "Checkout", enabled: true, open_findings: 3 }],
          ignored_keys: [], total_now: 2,
        },
      }],
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    await userEvent.click(screen.getByLabelText("Your pages"));
    await userEvent.paste('["/"]');
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(await screen.findByLabelText(/Take them out of scope/));

    expect(screen.getByText("If you renamed a page")).toBeTruthy();
    expect(screen.getByText(/stay with the old address/)).toBeTruthy();
  });

  it("names a column it could not use rather than ignoring it in silence", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes\/\?preview=1/, {
        preview: {
          adding: ["/"], updating: [], missing: [],
          ignored_keys: [{ key: "inScope", entries: 69 }],
          total_now: 0,
        },
      }],
      [/a11y-routes/, routesBody({ routes: [] })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    await userEvent.click(screen.getByLabelText("Your pages"));
    await userEvent.paste('["/"]');
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    // If the ignored key is the in-scope flag, we would audit pages the client excluded and
    // nothing anywhere would say a flag had been dropped.
    expect(await screen.findByText("Some columns were not recognised")).toBeTruthy();
    expect(screen.getByText(/inScope \(69 entries\)/)).toBeTruthy();
  });

  it("a list that cannot be read is refused in the platform's words, not the browser's", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes\/\?preview=1/, { detail: "this could not be read as a list of pages" }, 400],
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    await userEvent.click(screen.getByLabelText("Your pages"));
    await userEvent.paste("/, /catalogue");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(screen.getByText("This could not be read")).toBeTruthy());
    // Still on the paste step, with the text intact — a refusal must not cost what was typed.
    expect((screen.getByLabelText("Your pages") as HTMLTextAreaElement).value).toBe("/, /catalogue");
  });
});


// ── editing one page (task 8b) ──────────────────────────────────────────────
//
// Registering works by path and cannot tell a corrected path from a new page. Editing a named
// row can — so these are about what the row editor makes possible, and about the one thing it
// still cannot do.

describe("S-38 editing one page", () => {
  it("editing a row opens it with its own values, not an empty form", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({
        routes: [route({ label: "Browse the catalogue", example_path: "" })],
      })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    expect((screen.getByLabelText("Path") as HTMLInputElement).value).toBe("/catalogue");
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Browse the catalogue");
  });

  it("renaming a page that has recorded problems says what stays behind", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({
        routes: [route({ path: "/catalogue/search", open_findings: 3, visits: 2 })],
      })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const path = screen.getByLabelText("Path");
    await userEvent.clear(path);
    await userEvent.paste("/catalogue/results");

    // A problem is identified by the page it was found on, so the history cannot follow. That
    // is correct and it is not obvious, which is exactly why it is said before it happens.
    expect(screen.getByText("This page has a history")).toBeTruthy();
    expect(screen.getByText(/3 recorded problems stay with/)).toBeTruthy();
    expect(screen.getByText(/starts with no history/)).toBeTruthy();
  });

  it("a page with no history is renamed without a warning nobody needs", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({
        routes: [route({ path: "/catalouge", open_findings: 0, visits: 0, last_visited: null })],
      })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await userEvent.clear(screen.getByLabelText("Path"));
    await userEvent.paste("/catalogue");

    // A warning on every rename is a warning nobody reads by the third one.
    expect(screen.queryByText("This page has a history")).toBeNull();
  });

  it("adding one page does not make anyone write a list", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Add a page" }));
    // By heading, because the button that opened it says the same thing.
    expect(screen.getByRole("heading", { name: "Add a page" })).toBeTruthy();
    expect((screen.getByLabelText("Path") as HTMLInputElement).value).toBe("");
    // The example field is here rather than hidden behind an advanced panel: a pattern route is
    // the one case where a page cannot be audited at all without it.
    expect(screen.getByLabelText("Example page")).toBeTruthy();
  });

  it("removing a page that was audited says it was kept, not removed", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes\/[0-9a-z-]+\/$/, {
        removed: false, excluded: true, path: "/catalogue",
        reason: "/catalogue has been audited, so it is kept and taken out of scope rather than deleted. What was found there stays on the record.",
      }],
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Remove" }));

    // The answer depends on what the page has accumulated, which the person asking cannot be
    // expected to know — so it is said afterwards rather than guessed at beforehand.
    await waitFor(() => expect(screen.getByText("Kept, and taken out of scope")).toBeTruthy());
    expect(screen.getByText(/stays on the record/)).toBeTruthy();
  });

  it("an excluded page still says Excluded, not just an off switch", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ routes: [route({ enabled: false })] })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // A toggle that is off reads as "not set yet". Excluded is a decision somebody took.
    expect(await screen.findByText("Excluded")).toBeTruthy();
  });

  it("a change the platform refuses leaves the page as it was, and says why", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes\/[0-9a-z-]+\/$/, { detail: "/a is already registered on this project" }, 400],
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
    await userEvent.clear(screen.getByLabelText("Path"));
    await userEvent.paste("/a");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText("Nothing was changed")).toBeTruthy());
    expect(screen.getByText(/already registered/)).toBeTruthy();
  });
});

// ── Who may operate this screen, and who may only read it ───────────────────
//
// These four endpoints had no role check of any kind: they fell through the viewset default and
// were open to any session in the tenant, while starting a keyboard journey on the very same
// screen was refused for anyone but the accessibility reviewer. The screen matched the code —
// every control rendered live for everybody, with none of the "you can see these; the QA Lead
// starts them" wording the journeys panel below has always carried.
//
// Page scope is the input every later number depends on. A page quietly taken out of scope
// makes the next baseline read as an improvement.

describe("S-38 read-only", () => {
  it("a reader is told whose call it is, before any button", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ can_manage: false })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("You can see this; the QA Lead or Tech Lead runs it");
    expect(screen.getByText(/readable by anyone on the project/)).toBeTruthy();
  });

  it("a reader gets disabled controls, not controls that fail on click", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ can_manage: false })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    for (const name of ["Run audit", "Add a page", "Import a list", "Edit", "Remove"]) {
      const button = await screen.findByRole("button", { name });
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
    // Including the in-scope switch, which is the quietest way to change what an audit covers.
    // `Switch` puts the label on the wrapping <label>, so reach the control it wraps.
    const toggle = screen.getByLabelText("Audit /catalogue").querySelector("input");
    expect((toggle as HTMLInputElement).disabled).toBe(true);
  });

  it("a reader still sees every page — read-only, never hidden", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ can_manage: false })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("/catalogue")).toBeTruthy();
    expect(screen.getByText("Browse the catalogue")).toBeTruthy();
  });

  it("with no pages at all, a reader is told who registers them", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ routes: [], can_manage: false })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("No pages are registered yet");
    expect(screen.getByText(/QA Lead or Tech Lead on this project registers the pages/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Import a list" })).toBeNull();
  });

  it("an operator keeps every control", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    const run = await screen.findByRole("button", { name: "Run audit" });
    expect((run as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText("You can see this; the QA Lead or Tech Lead runs it")).toBeNull();
  });
});

// ── What this machine needs, said before the audit rather than after it ─────

describe("S-38 what your machine needs", () => {
  it("says the audit prefers the application's own scanner and names the fallback", async () => {
    // The audit and the keyboard journey below it need genuinely different setups, and the
    // difference used to be invisible — discovered from an audit that failed minutes later.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("Run an audit");
    expect(screen.getByText(/Your machine needs a browser and the/)).toBeTruthy();
    expect(screen.getByText(/falls back to the companion's own/)).toBeTruthy();
  });
});

// ── Saying which of the two ways in you want, and what each one takes ───────
//
// Every assertion here comes from two people on the team reading these dialogs and coming away
// with the wrong idea — one that the paste box took JSON only, the other that the single-page
// form was for URL patterns only. Neither was true, and nothing on either screen was broken:
// the words were. A screen that is understood backwards by the people who asked for it is not
// a screen that works, so the wording is pinned here like any other behaviour.

describe("S-38 registering pages — the two ways in", () => {
  it("the import dialog is named after the button that opens it", async () => {
    // It was titled "Add pages", which is nearly the name of the OTHER button on this screen.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ routes: [], summary: "no routes are registered" })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    expect(screen.getByRole("heading", { name: "Import a list" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Add pages" })).toBeNull();
  });

  it("the paste box shows BOTH formats, because both are accepted", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    const box = screen.getByLabelText("Your pages") as HTMLTextAreaElement;

    // One path per line, and a JSON list, in one placeholder — a reader holding either kind of
    // list can see theirs.
    expect(box.placeholder).toContain("/catalogue");
    expect(box.placeholder).toContain('"path"');
    expect(screen.getByText(/Either format works/)).toBeTruthy();
  });

  it("a pattern is shown only in the format that can carry its example", async () => {
    // The trap this closes: line mode returns bare paths, so there is nowhere to say what
    // `/events/:id` should open. The placeholder used to demonstrate a pattern in the LINE
    // half, which registers a page no browser can open and reports it unreachable forever.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Import a list" }));
    const box = screen.getByLabelText("Your pages") as HTMLTextAreaElement;
    const [lines, json] = box.placeholder.split("— or a JSON list —");

    expect(lines).not.toContain(":id");            // nothing pattern-shaped in the line half
    expect(json).toContain('"example"');           // and the JSON half carries the way to visit it
    expect(screen.getByText(/needs the JSON form/)).toBeTruthy();
  });

  it("the single-page form says what to do when the page is a normal one", async () => {
    // Read scanning downward, "Only for a pattern like /events/:id" described the DIALOG, and
    // two readers concluded the form accepted nothing else.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Add a page" }));
    expect(screen.getByRole("heading", { name: "Add a page" })).toBeTruthy();
    expect(screen.getByText(/Leave this empty for a normal page/)).toBeTruthy();
    expect(screen.queryByText(/^Only for a pattern like/)).toBeNull();
  });

  it("more than one pattern shape, because the platform does not parse any of them", async () => {
    // `normalise_path` wants a leading `/` and nothing else — `:id`, `[isbn]` and `{id}` are all
    // stored as written. Naming one framework's syntax made it read as the only one allowed.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Add a page" }));
    for (const shape of ["/events/:id", "/books/[isbn]", "/users/{id}/loans"]) {
      expect(screen.getByText(shape)).toBeTruthy();
    }
  });

  it("with nothing registered, the empty state says which button to press", async () => {
    // Two buttons that both add pages, and nothing anywhere saying what separates them.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ routes: [], summary: "no routes are registered" })],
      [/a11y-audits/, { audits: [] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("No pages are registered yet");
    expect(screen.getByText(/If you already have the list/)).toBeTruthy();
    expect(screen.getByText(/Otherwise add them one page at a time/)).toBeTruthy();
  });

  // ── the audit that is running now (S-38 line 598) ─────────────────────────
  //
  // Until this panel existed the only thing on screen while an audit ran was a status word in a
  // list, in a 320px rail below the page table. The team's first live run spent forty minutes on
  // "Checking what was found" with no way to see that the judge was at 81 of 144 — or that it
  // had stopped. These assert the counts, because a panel that renders without them is the same
  // silence with more furniture.

  function audit(over: Record<string, unknown> = {}) {
    return {
      id: "a1",
      status: "capturing",
      base_url: "http://localhost:4180",
      routes: ["/", "/catalogue", "/about/history"],
      summary: {},
      progress: { visited: 0, unreachable: 0 },
      created_at: "2026-08-21T09:00:00Z",
      ...over,
    };
  }

  it("running · shows the pass, the pages visited and the ones that would not open", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [audit({ progress: { visited: 2, unreachable: 1 } })] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Audit running")).toBeTruthy();
    expect(screen.getByText("Pages visited").previousElementSibling?.textContent)
      .toContain("2");
    expect(screen.getByText("Pages visited").nextElementSibling?.textContent)
      .toBe("of 3 asked for");
    // A page that would not open is a RESULT, and it is counted and named rather than left to
    // look like progress that has not happened yet.
    expect(screen.getByText("Would not open").previousElementSibling?.textContent).toBe("1");
    expect(screen.getByText("Pass").previousElementSibling?.textContent).toContain("of 1");
    // Nothing here asks the person to sit and watch.
    expect(screen.getByText(/You can leave this page/)).toBeTruthy();
  });

  it("judging · shows how far the AI half has got, against what was dispatched", async () => {
    // The number that could not be seen at all yesterday.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, {
        audits: [audit({
          status: "judging",
          progress: { visited: 3, unreachable: 0, judged: 81, dispatched: 144 },
        })],
      }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText("Elements judged")).toBeTruthy();
    expect(screen.getByText("Elements judged").previousElementSibling?.textContent)
      .toContain("81");
    expect(screen.getByText("Elements judged").previousElementSibling?.textContent)
      .toContain("of 144");
    // The capture is finished, so the pass tile has nothing left to say and gives up its slot.
    expect(screen.queryByText("Pass")).toBeNull();
    // The panel and the row under Past audits say the same thing, in the same words.
    expect(screen.getAllByText("Checking what was found").length).toBe(2);
  });

  it("finished · the panel stays and says what the audit came to", async () => {
    // It used to disappear the moment the run ended, which is the worst possible moment for the
    // panel somebody has been watching to vanish: the answer arrives and the screen goes blank.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, {
        audits: [audit({
          status: "complete", progress: null,
          summary: { asked: 3, opened: 3, never_reported: [] },
          outcome: { problems: 4, critical: 1, high: 3, waiting: 2 },
        })],
      }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText(/Audit complete/)).toBeTruthy();
    expect(screen.queryByText("Audit running")).toBeNull();
    expect(screen.getByText("Pages reported").previousElementSibling?.textContent).toBe("3");
    expect(screen.getByText("Problems open").previousElementSibling?.textContent).toBe("4");
    expect(screen.getByText("Problems open").nextElementSibling?.textContent)
      .toContain("1 critical");
    // The two are counted apart: a problem the platform is sure about and a question it is
    // asking a person are different things, and the way through to answering them is offered.
    expect(screen.getByText("Waiting on a person").previousElementSibling?.textContent).toBe("2");
    expect(screen.getByRole("link", { name: /Answer the 2 waiting/ })).toBeTruthy();
  });

  it("finished with nothing waiting · does not read as an application with no problems", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, {
        audits: [audit({
          status: "complete", progress: null,
          summary: { asked: 3, opened: 2, never_reported: ["/admin/reports"] },
          outcome: { problems: 0, critical: 0, high: 0, waiting: 0 },
        })],
      }],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText(/Audit complete/);
    expect(screen.getByText("every check answered on its own")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /waiting/ })).toBeNull();
    // A page that never opened is stated, never absorbed into a clean-looking result.
    expect(screen.getByText("One page was asked for and never opened")).toBeTruthy();
    expect(screen.getByText(/nothing they might have contained is treated as passing/))
      .toBeTruthy();
  });

  // ── asking again about what nothing looked at (task R1) ───────────────────
  //
  // A judging run that dies leaves everything it never reached filed as `uncertain — not
  // judged`, so nothing dispatched vanishes. Those elements then sit on a person for a reason
  // that has nothing to do with them: not "a check could not decide", but "nothing looked".
  // This is the offer to ask the machine again — and NOT an offer to re-run the audit, because
  // no page needs visiting.

  function closed(over: Record<string, unknown> = {}) {
    return audit({ status: "complete", progress: null,
                   summary: { asked: 3, opened: 3, never_reported: [] }, ...over });
  }

  it("offers to check the rest, and says how many were never looked at", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [closed({ unanswered: 12 })] }],
    ]));
    renderWithProviders(<A11yAudit />);

    expect(await screen.findByText(/12 elements were never looked at/)).toBeTruthy();
    // The distinction the whole task rests on, said on the screen and not only in the code.
    expect(screen.getByText(/never checked at all/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Check the rest" })).toBeTruthy();
  });

  it("pressing it asks that audit, and says no page is visited", async () => {
    const fetchStub = stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/rejudge/, { started: true, asked: 12 }],
      [/a11y-audits/, { audits: [closed({ unanswered: 12 })] }],
    ]);
    vi.stubGlobal("fetch", fetchStub);
    renderWithProviders(<A11yAudit />);

    await userEvent.click(await screen.findByRole("button", { name: "Check the rest" }));

    await waitFor(() =>
      expect(fetchStub.mock.calls.some(([url]) =>
        String(url).includes("/a11y-audits/a1/rejudge/"))).toBe(true));
    expect(await screen.findByText(/No page is visited/)).toBeTruthy();
  });

  it("an audit where everything was looked at offers nothing", async () => {
    // A button that is always there, usually with nothing to do, is a button nobody reads.
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody()],
      [/a11y-audits/, { audits: [closed({ unanswered: 0 })] }],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("Past audits");
    expect(screen.queryByRole("button", { name: "Check the rest" })).toBeNull();
    expect(screen.queryByText(/never looked at/)).toBeNull();
  });

  it("a reader sees it, cannot press it, and is told whose call it is", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...authed(),
      [/a11y-routes/, routesBody({ can_manage: false })],
      [/a11y-audits/, { audits: [closed({ unanswered: 1 })] }],
    ]));
    renderWithProviders(<A11yAudit />);

    // One element, said in the singular — a count is not a place to be careless.
    expect(await screen.findByText(/1 element was never looked at/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Check the rest" })).toHaveProperty("disabled", true);
    expect(screen.getByText(/The QA Lead or Tech Lead on this project runs this/)).toBeTruthy();
  });
});
