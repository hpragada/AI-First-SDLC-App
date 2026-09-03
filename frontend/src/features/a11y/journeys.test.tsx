// @vitest-environment jsdom
//
// G6c — the keyboard-journeys panel on S-38.
//
// Eight WCAG criteria cannot be answered by reading a page standing still. They are only
// answerable by OPERATING the application, and until this panel there was no way for a person to
// ask for that — `start_journey_check` had no caller anywhere in the platform.
//
// These assert the sentences, not just the rendering, because every state here is one where a
// screen that renders "successfully" could still mislead: a project whose Testing phase has not
// run looking like a project with no keyboard problems, a test case that cannot be walked
// quietly absent, a journey silently not started, or a reader given a button that fails on click.
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

// Enough of the rest of the screen to render. The page list is deliberately EMPTY in most of
// these: a journey follows a test case, not the page list, so the panel must be there anyway.
function base(): Array<[RegExp, unknown, number?]> {
  return [
    [/\/auth\/me\//, ME],
    [/\/runners\//, [{ id: "r1", machine: "dev-1", online: true, projects: [] }]],
    [/\/dashboard\//, { needs_me: { gates: [], clarifications: [] } }],
    [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15 }],
    [/a11y-routes\/$/, { routes: [], summary: "", scope_change: {} }],
    [/a11y-audits\/$/, { audits: [] }],
  ];
}

function journey(over: Record<string, unknown> = {}) {
  return {
    id: "art-1",
    test_ref: "TC-031",
    title: "Register to first expense",
    artifact_id: "art-1",
    steps: 9,
    last_walked: null,
    status: "",
    summary: {},
    ...over,
  };
}

function list(over: Record<string, unknown> = {}) {
  return {
    journeys: [journey()],
    unwalkable: [],
    over_cap: [],
    max_journeys: 10,
    base_url: "http://127.0.0.1:5173",
    base_url_source: "the repository acme/web",
    base_url_reason: "",
    can_start: true,
    ...over,
  };
}

describe("Keyboard journeys (G6c)", () => {
  beforeEach(() => vi.restoreAllMocks());
  // vitest has no `globals: true` here, so RTL's auto-cleanup does not run.
  afterEach(cleanup);

  it("says why there is nothing to walk, instead of looking like nothing is wrong", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({ journeys: [] })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("No journeys to walk yet");
    expect(screen.getByText(/run the Testing phase/i)).toBeDefined();
    // The distinction the whole panel exists to make.
    expect(screen.getByText(/covers one of the eight/i)).toBeDefined();
  });

  it("lists the journeys with the address pre-filled and where it came from", async () => {
    vi.stubGlobal("fetch", stubRoutes([...base(), [/a11y-journeys\/$/, list()]]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-031");
    const address = screen.getByLabelText("Address to walk") as HTMLInputElement;
    expect(address.value).toBe("http://127.0.0.1:5173");
    expect(screen.getByText(/Pre-filled from the repository acme\/web/)).toBeDefined();
    expect(screen.getByText("Never walked")).toBeDefined();
    // Still said before the button, because it is the one thing the platform cannot do for
    // them — but folded into the panel's expander rather than standing as a full-width banner
    // on every visit. It is in the document either way, which is what a screen reader and a
    // find-in-page both go by; `<details>` hides its contents visually, not from the tree.
    expect(screen.getByText(/Start your application first/)).toBeDefined();
  });

  // ── the explanation, folded ────────────────────────────────────────────────
  //
  // A third of this panel used to be prose above the table people come here for. It is now one
  // sentence and an expander. What must not happen is the detail being quietly deleted along
  // with the space it took, so these hold both halves: the summary states the point, and
  // everything that was there before is still reachable and still in the accessibility tree.

  it("opens with one sentence and keeps the rest behind an expander", async () => {
    vi.stubGlobal("fetch", stubRoutes([...base(), [/a11y-journeys\/$/, list()]]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-031");
    // A real control to assistive technology — a native <summary>, not a div with a click
    // handler. This platform does not get to ship the defect it sells finding.
    const summary = screen.getByText("What this means");
    expect(summary.tagName).toBe("SUMMARY");
    expect(summary.closest("details")).not.toBeNull();
    // Closed by default: that is the space this was meant to give back.
    expect(summary.closest("details")!.hasAttribute("open")).toBe(false);
  });

  it("keeps every fact the long version carried", async () => {
    vi.stubGlobal("fetch", stubRoutes([...base(), [/a11y-journeys\/$/, list()]]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-031");
    expect(screen.getByText(/focus can get out of a menu/)).toBeDefined();
    expect(screen.getByText(/covers one of the eight/)).toBeDefined();
    expect(screen.getByText(/records no steps/)).toBeDefined();
  });

  it("shows the E2E cases it could NOT walk, and why", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({
        unwalkable: [{
          artifact_id: "art-9", title: "TC-077 Checkout", test_ref: "TC-077",
          reason: "declares Type: E2E but no steps could be read from it",
        }],
      })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-077");
    expect(screen.getByText(/no steps could be read/)).toBeDefined();
  });

  it("starts the ticked journeys and says what happened to each", async () => {
    const fetchMock = stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({ journeys: [journey(), journey({
        id: "art-2", test_ref: "TC-044", title: "Borrow and return",
      })] })],
    ]);
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-031");
    await userEvent.click(screen.getByLabelText("Walk TC-031"));
    await userEvent.click(screen.getByLabelText("Walk TC-044"));
    expect(screen.getByRole("button", { name: "Walk 2 selected journeys" })).toBeDefined();

    // The POST answers with one started and one refused — both must be said out loud.
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (/a11y-journeys\/$/.test(url) && init?.method === "POST") {
        return {
          ok: true, status: 200, statusText: "stub",
          text: async () => JSON.stringify({
            started: [{ name: "TC-031", test_ref: "TC-031", run_id: "r", journey_run_id: "j",
                        steps: 9 }],
            refused: [{ name: "TC-044", test_ref: "TC-044",
                        reason: "TC-044 is already being walked." }],
            over_cap: [], unwalkable: [], reason: "",
          }),
        } as Response;
      }
      return stubRoutes([...base(), [/a11y-journeys\/$/, list()]])(input, init);
    });

    await userEvent.click(screen.getByRole("button", { name: "Walk 2 selected journeys" }));

    await screen.findByText("Walking 1 journey(s)");
    // …and the one that did NOT start, by name and with its reason. A journey silently not run
    // reads exactly like one that passed.
    expect(await screen.findByText("1 was not started")).toBeDefined();
    expect(screen.getByText(/already being walked/)).toBeDefined();
  });

  it("a reader sees the list, is told why, and cannot press the button", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({ can_start: false })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-031");
    expect(screen.getByText("You can see these; the QA Lead starts them")).toBeDefined();
    const run = screen.getByRole("button", { name: /Walk 0 selected journeys/ });
    expect((run as HTMLButtonElement).disabled).toBe(true);
  });

  it("a journey being walked cannot be started again from the screen", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({
        journeys: [journey({ status: "walking", last_walked: "2026-08-20T09:00:00Z" })],
      })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("Walking now");
    expect((screen.getByLabelText("Walk TC-031") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Select all walkable (0)" })).toBeDefined();
  });

  it("a finished walk shows what it found, and a blocked one is not a clean result", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({
        journeys: [
          journey({ status: "complete", last_walked: "2026-08-20T09:00:00Z",
                    summary: { asked: 9, walked: 9, blocked: [], findings: 0 } }),
          journey({ id: "art-2", test_ref: "TC-044", status: "complete",
                    last_walked: "2026-08-20T09:10:00Z",
                    summary: { asked: 6, walked: 4, findings: 3,
                               blocked: [{ step: 5, reason: "cannot tab to Continue" }] } }),
        ],
      })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("Walked · nothing found");
    expect(screen.getByText("1 blocked · 3 finding(s)")).toBeDefined();
  });

  it("names what the cap left out rather than dropping it", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({ over_cap: ["TC-099", "TC-100"] })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("More journeys than one run can take");
    expect(screen.getByText(/TC-099, TC-100/)).toBeDefined();
  });

  it("with no address on record it says what to set, and will not start", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({
        base_url: "", base_url_source: "",
        base_url_reason: "this project has no application address on record",
      })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("TC-031");
    expect(screen.getByText(/no application address on record/)).toBeDefined();
    await userEvent.click(screen.getByLabelText("Walk TC-031"));
    const run = screen.getByRole("button", { name: "Walk 1 selected journey" });
    expect((run as HTMLButtonElement).disabled).toBe(true);
  });

  it("says there is no machine BEFORE the button, not after pressing it", async () => {
    // The audit strip above does this; the journey needs it more, because a walk is a real
    // browser on the user's own machine against an application only that machine can reach.
    vi.stubGlobal("fetch", stubRoutes([
      [/\/auth\/me\//, ME],
      [/\/runners\//, []],
      [/\/dashboard\//, { needs_me: { gates: [], clarifications: [] } }],
      [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15 }],
      [/a11y-routes\/$/, { routes: [], summary: "", scope_change: {} }],
      [/a11y-audits\/$/, { audits: [] }],
      [/a11y-journeys\/$/, list()],
    ]));
    renderWithProviders(<A11yAudit />);

    // The banner, which is the one that says what to do about it. There used to be a badge in
    // the panel corner saying the same three words with no advice attached; it was removed, and
    // this asserts the half that was worth keeping is the half that survived.
    await screen.findByText("You have no machine connected");
    expect(screen.getByText(/Connect it first/)).toBeTruthy();
    expect(screen.queryByText("No machine connected")).toBeNull();
  });

  it("a dispatched journey no machine has taken says so, not \"Walking now\"", async () => {
    // The row is marked walking the moment the run is triggered, which is right — the platform
    // has handed the work over. But rendering that as "Walking now" meant a journey dispatched
    // with no companion online read as a browser stepping through the application, for ever.
    // The audit strip directly above has told those two states apart since task 8a.
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({
        journeys: [journey({ status: "queued", last_walked: "2026-08-20T09:00:00Z" })],
      })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("Waiting for a machine");
    expect(screen.queryByText("Walking now")).toBeNull();
  });

  it("a journey waiting for a machine cannot be ticked again either", async () => {
    // It is already spoken for, so ticking it would only earn an "already being walked"
    // refusal — the same reason a walking one is locked.
    vi.stubGlobal("fetch", stubRoutes([
      ...base(),
      [/a11y-journeys\/$/, list({
        journeys: [journey({ status: "queued", last_walked: "2026-08-20T09:00:00Z" })],
      })],
    ]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("Waiting for a machine");
    expect((screen.getByLabelText("Walk TC-031") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Select all walkable (0)" })).toBeDefined();
  });

  it("the panel is there even when no pages are registered", async () => {
    // A journey follows a TEST CASE, not the page list. This is the state a greenfield project
    // is in after the Testing phase and before anybody registers a page.
    vi.stubGlobal("fetch", stubRoutes([...base(), [/a11y-journeys\/$/, list()]]));
    renderWithProviders(<A11yAudit />);

    await screen.findByText("No pages are registered yet");
    await waitFor(() => expect(screen.getByText("TC-031")).toBeDefined());
  });
});
