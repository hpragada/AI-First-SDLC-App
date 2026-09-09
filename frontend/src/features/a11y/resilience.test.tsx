// @vitest-environment jsdom
//
// What the accessibility screens say when they have NO DATA — and the difference between the
// two reasons they might not.
//
// Every one of them used to fall through to its empty state when the server did not answer:
// undefined data, an empty list, and "No pages are registered yet" / "Nothing is waiting on
// you" / "There is nothing to compile yet" / "No journeys to walk yet" rendered on top of a
// broken system. A failure looked exactly like a clean, empty, working one.
//
// That is the single thing this whole capability exists to refuse — *a criterion nobody looked
// at must never look like a criterion that passed* — happening at the outermost layer of the
// screens that make the argument. And it was not hypothetical: with the accessibility tables
// unmigrated on an environment, every one of these endpoints returns 500, so this is what the
// first person to open the feature would have been told.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { A11yAudit } from "./A11yAudit";
import { A11yReview } from "./A11yReview";
import { A11yConformanceScreen } from "./A11yConformance";

const PROJECT = "11111111-1111-1111-1111-111111111111";

const ME = {
  user: { id: "u1", email: "aisha@acme.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "Meridian", role: "qa_lead" }],
};

function stubRoutes(routes: Array<[RegExp, unknown, number?]>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    const url = String(input);
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

// Everything the shell needs, with each accessibility endpoint answering healthily. Individual
// tests break exactly one of them.
function base(): Array<[RegExp, unknown, number?]> {
  return [
    [/\/auth\/me\//, ME],
    [/\/runners\//, []],
    [/\/dashboard\//, { needs_me: { gates: [], clarifications: [] } }],
    [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15, ever_checked: true }],
    [/a11y-routes\/$/, { routes: [], summary: "", scope_change: {}, can_manage: true }],
    [/a11y-audits\/$/, { audits: [] }],
    [/a11y-journeys\/$/, {
      journeys: [], unwalkable: [], over_cap: [], max_journeys: 10,
      base_url: "", base_url_source: "", base_url_reason: "", can_start: true,
    }],
    [/a11y-conformance\/$/, {
      totals: { total: 55, evaluated: 0, not_evaluated: 55, awaiting_a_person: 0 },
      rows: [], signed: false, stale: false, can_sign: false, disclaimer: "d",
      required_role: "qa_lead", scope: "", body: "", signed_name: "", signed_role: "",
    }],
  ];
}

// A route that 500s, replacing the healthy one of the same shape.
function broken(pattern: RegExp): Array<[RegExp, unknown, number?]> {
  return [[pattern, { detail: 'relation "a11y_route" does not exist' }, 500], ...base()];
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", PROJECT);
});
afterEach(() => {
  // vitest runs without `globals: true`, so RTL's auto-cleanup is not wired up.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("A failed load is said as a failure, never as an empty result", () => {
  // REWORDED 8 September (Bugs S.No 248). These screens used to own their own failure copy —
  // "The page list could not be loaded", three sentences of defence, and a hint about database
  // migrations — and printed whatever the failure threw. The wording now comes from the one
  // shared panel every screen uses, and it is written for the client. What these tests pin is
  // unchanged in substance: a failure must never read as a clean, empty, passing screen.
  it("the page list says the app failed, not that no pages are registered", async () => {
    vi.stubGlobal("fetch", stubRoutes(broken(/a11y-routes\/$/)));
    renderWithProviders(<A11yAudit />);

    await screen.findByText(/Something went wrong on our side/i);
    expect(screen.queryByText("No pages are registered yet")).toBeNull();
    // The load-bearing sentence, in its shorter form. Without it a reader still walks away with
    // an impression of their application, formed from a screen that had no data at all — and on
    // THIS capability that impression can end up in a conformance statement.
    expect(
      screen.getByText(/says nothing about your application's accessibility/i),
    ).toBeDefined();
  });

  it("★ never shows the client what our database said", async () => {
    // This used to assert the opposite — `getByText(/a11y_route/)` — and the stub above is why
    // that was wrong: the server's honest answer to a missing table is
    // `relation "a11y_route" does not exist`, which is our problem described in our words. A
    // client who did not build this can do nothing with it. It stays in the server log.
    vi.stubGlobal("fetch", stubRoutes(broken(/a11y-routes\/$/)));
    renderWithProviders(<A11yAudit />);

    await screen.findByText(/Something went wrong on our side/i);
    expect(screen.queryByText(/a11y_route/)).toBeNull();
    expect(screen.queryByText(/relation/i)).toBeNull();
    expect(screen.queryByText(/migrated/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
  });

  it("the review queue says so too, not that nothing is waiting", async () => {
    vi.stubGlobal("fetch", stubRoutes(broken(/a11y-review\/$/)));
    renderWithProviders(<A11yReview />);

    await screen.findByText(/Something went wrong on our side/i);
    expect(screen.queryByText("Nothing is waiting on you")).toBeNull();
  });

  it("the conformance statement says so too, not that there is nothing", async () => {
    vi.stubGlobal("fetch", stubRoutes(broken(/a11y-conformance\/$/)));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText(/Something went wrong on our side/i);
    expect(screen.queryByText("There is nothing to compile yet")).toBeNull();
  });

  it("the keyboard journeys say so too, on a page list that loaded fine", async () => {
    // The panel fails on its own, inside a screen whose other half is healthy — so this must
    // not take the page list down with it, and must not read as "no journeys".
    vi.stubGlobal("fetch", stubRoutes(broken(/a11y-journeys\/$/)));
    renderWithProviders(<A11yAudit />);

    await screen.findByText(/Something went wrong on our side/i);
    expect(screen.queryByText("No journeys to walk yet")).toBeNull();
    expect(screen.getByText("No pages are registered yet")).toBeDefined();
  });
});

describe("An empty queue: two reasons, two sentences", () => {
  it("a project where nothing has run is pointed at the starting line", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15, ever_checked: false }],
      ...base(),
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("Nothing has been checked yet");
    // The old single sentence told THIS reader that "every check so far was sure enough to
    // answer on its own" — vacuously true, and read as reassurance.
    expect(screen.queryByText(/every check so far was sure enough/)).toBeNull();
    expect(screen.getByText(/nothing here says whether the application is accessible/)).toBeDefined();
    expect(
      screen.getByRole("link", { name: "Go to Pages & audit" }).getAttribute("href"),
    ).toBe("/a11y/pages");
  });

  it("a project that HAS been checked keeps the sentence that is true of it", async () => {
    vi.stubGlobal("fetch", stubRoutes(base()));
    renderWithProviders(<A11yReview />);

    await screen.findByText("Nothing is waiting on you");
    expect(screen.getByText(/every check so far was sure enough/)).toBeDefined();
    expect(screen.queryByText("Nothing has been checked yet")).toBeNull();
  });
});

describe("The conformance statement with no evidence at all", () => {
  it("names the audit as the way in, not only the Testing phase", async () => {
    // The brownfield reader is the one most likely to arrive here with nothing compiled, and
    // their route to evidence is an audit. The old text sent them to a phase they never run.
    vi.stubGlobal("fetch", stubRoutes([
      [/a11y-conformance\/$/, null],
      ...base(),
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("There is nothing to compile yet");
    expect(screen.getByText(/Register the pages of the application and run an audit/)).toBeDefined();
    expect(
      screen.getByRole("link", { name: "Go to Pages & audit" }).getAttribute("href"),
    ).toBe("/a11y/pages");
  });
});
