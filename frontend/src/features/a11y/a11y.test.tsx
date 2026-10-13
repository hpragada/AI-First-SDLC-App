// @vitest-environment jsdom
//
// S-36 — the accessibility review console (QA-23).
//
// These assert the sentences, not the styling. Every one of them is a place where a screen that
// rendered "successfully" would still have told the reviewer something untrue: an empty queue
// that reads as a clean bill of health, a "0%" that reads as "the AI was 0% confident", a
// promised defect that this project's policy will never raise, an empty picture frame with no
// reason, or editable controls for someone who is not the reviewer.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AppShell } from "../../components/AppShell";
import { renderWithProviders } from "../../test/utils";
import { A11yReview } from "./A11yReview";

const PROJECT = "11111111-1111-1111-1111-111111111111";
const FINDING = "22222222-2222-2222-2222-222222222222";

const ME = {
  user: { id: "u1", email: "aisha@acme.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "Payments", role: "qa_lead" }],
};

// One row of the QUEUE, and deliberately not the same shape as `item()`. The server sends the
// list WITHOUT any capture (G3b) — the rail draws no picture, so it does not go and find one.
// Kept apart so a component that reached for a picture in the list fails here, in a test, and
// not in front of a reviewer.
function row(over: Record<string, unknown> = {}) {
  return {
    id: FINDING,
    criterion: "1.1.1",
    criterion_handle: "Non-text Content",
    wcag_level: "A",
    route: "/checkout",
    selector: "img.hero",
    stable_selector: true,
    checker: "alt",
    verdict: "uncertain",
    confidence: null,
    severity_if_confirmed: "critical",
    evidence: "The alt reads like a filename rather than a description.",
    suggested_fix: "Describe it, or mark it decorative.",
    // A baseline audit's finding: no story, no test case, no run. The default here is that
    // shape deliberately, so every other test in this file proves the console still renders
    // when there is nothing to link to.
    source_run: null,
    work_item_id: null,
    work_item_label: null,
    work_item_title: null,
    lock: { held: false, by_me: false, held_by: null, held_by_name: "", expires_at: null },
    ...over,
  };
}

// The single-item read: the row, plus the capture the reviewer judges it by. Only this call
// carries it, and only this call pays for it.
function item(over: Record<string, unknown> = {}) {
  return {
    ...row(),
    page_image: false,
    element_image: false,
    box: null,
    url: "http://localhost:3000/checkout",
    capture_reason: "",
    ...over,
  };
}

// A fetch stub that answers by URL, because this screen makes three different calls and a
// single blanket response cannot tell them apart.
function stubRoutes(routes: Array<[RegExp, unknown, number?]>) {
  return vi.fn(async (input: RequestInfo | URL) => {
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

const AUTHED: Array<[RegExp, unknown, number?]> = [
  [/\/auth\/me\//, ME],
  [/\/runners\//, []],
  [/\/dashboard\//, { needs_me: { gates: [], clarifications: [] } }],
];

beforeEach(() => {
  localStorage.setItem("selectedProjectId", PROJECT);
});
afterEach(() => {
  // This repo runs vitest without `globals: true`, so RTL's automatic cleanup is not wired up
  // and every render would otherwise stack in one document — the second test then finds two of
  // every button and fails for a reason that has nothing to do with the screen.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("S-36 accessibility review console", () => {
  it("empty · refuses to read as a clean bill of health", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15 }],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("Nothing is waiting on you");
    // D-A11Y-93. This is the whole reason the empty state has a sentence rather than a shrug.
    expect(
      screen.getByText(/not that no problems were found/),
    ).toBeDefined();
  });

  it("default · the queue lists the work, worst first, with the criterion named", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, {
        queue: [row(), row({ id: "other", criterion: "1.4.3", criterion_handle: "Contrast (Minimum)", wcag_level: "AA", confidence: 0.58, verdict: "fail" })],
        can_review: true,
        lock_minutes: 15,
      }],
      [/a11y-review\/22222222/, item({ can_review: true, locked_out: "" })],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("1.1.1 Non-text Content");
    expect(screen.getByText("1.4.3 Contrast (Minimum)")).toBeDefined();
    // An `uncertain` verdict has a confidence of 0 by construction. "0%" would read as "the AI
    // was 0% confident" when it means "the AI gave no verdict" (D-A11Y-95).
    expect(screen.getAllByText("No verdict").length).toBeGreaterThan(0);
    expect(screen.getByText("Not sure · 58%")).toBeDefined();
  });

  // 31 August: four of the nineteen items in a real review queue were PASSES the check was only
  // 75–80% sure of — under the bar the platform needs before acting alone. The banner pasted the
  // verdict label into one sentence for every case, so those read "The check gave not sure · 75%"
  // — broken English that also hid the one fact the reviewer needs: the check said it was fine.
  it("a low-confidence pass says the check DID decide, and how sure it was", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: true, verdict: "pass", confidence: 0.75 })],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("The check said this is fine, and was 75% sure");
    expect(screen.queryByText(/The check gave/)).toBeNull();
    expect(screen.getByText(/under the confidence this check needs/)).toBeDefined();
  });

  it("an uncertain still says the check reached no answer at all", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: true, verdict: "uncertain", confidence: 0 })],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("The check gave no verdict");
    expect(screen.getByText(/did not act on it either way/)).toBeDefined();
  });

  it("no capture · says why, instead of showing an empty frame", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({
        can_review: true,
        capture_reason: "the capture recorded no on-screen rectangle for this element",
      })],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("There is no picture of this one");
    expect(screen.getByText(/no on-screen rectangle/)).toBeDefined();
    expect(screen.getByText(/You can still judge it/)).toBeDefined();
  });

  it("greenfield · names the test case that found it, and links to it and its run", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({
        can_review: true,
        source_run: "33333333-3333-3333-3333-333333333333",
        work_item_id: "44444444-4444-4444-4444-444444444444",
        work_item_label: "TC-031",
        work_item_title: "Checkout with valid card",
      })],
    ]));
    renderWithProviders(<A11yReview />);

    const link = await screen.findByRole("link", { name: /TC-031/ });
    expect(link.getAttribute("href")).toBe("/work-items/44444444-4444-4444-4444-444444444444");
    expect(link.textContent).toContain("Checkout with valid card");
    // A new tab on purpose: the reviewer holds a 15-minute claim on this item and a place in a
    // long queue, and neither should be spent to glance at a test case.
    expect(link.getAttribute("target")).toBe("_blank");

    const run = screen.getByRole("link", { name: "View run" });
    expect(run.getAttribute("href")).toBe("/runs/33333333-3333-3333-3333-333333333333");
  });

  it("brownfield · shows nothing at all rather than an empty link", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: true })],   // the audit shape: all null
    ]));
    renderWithProviders(<A11yReview />);

    // The panel is up — so the absence below is the screen's answer, not a slow render.
    await screen.findByText("img.hero");
    expect(screen.queryByText(/Found by/)).toBeNull();
    expect(screen.queryByRole("link", { name: "View run" })).toBeNull();
  });

  it("read-only · someone who is not the reviewer gets no controls, and is told why", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: false, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: false })],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("You are not the accessibility reviewer");
    expect(screen.queryByRole("button", { name: /this is a real problem/ })).toBeNull();
    // Read-only, not blind — the evidence is still on screen.
    expect(screen.getByText(/reads like a filename/)).toBeDefined();
  });

  it("locked · the second reviewer is told who has it, and cannot answer", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({
        can_review: true,
        locked_out: "Tom Reyes is reviewing this one. It returns to the queue on its own if they stop.",
        lock: { held: true, by_me: false, held_by: "u2", held_by_name: "Tom Reyes", expires_at: null },
      })],
    ]));
    renderWithProviders(<A11yReview />);

    await screen.findByText("Someone else is already on this one");
    expect(screen.getByText(/Tom Reyes is reviewing this one/)).toBeDefined();
    expect(screen.queryByRole("button", { name: /this is a real problem/ })).toBeNull();
  });

  it("confirmed · says a defect was opened only when one really was", async () => {
    // The POST shares the item's GET url, so this stub branches on the METHOD.
    const base = stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: true })],
    ]);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        return {
          ok: true,
          status: 200,
          statusText: "stub",
          text: async () =>
            JSON.stringify({ id: FINDING, adjudication: "confirmed", outcome: "failure",
                             status: "open", severity: "critical", opens_defect: true }),
        } as Response;
      }
      return base(input);
    }));
    renderWithProviders(<A11yReview />);

    const yes = await screen.findByRole("button", { name: /this is a real problem/ });
    await userEvent.click(yes);
    await screen.findByText("Recorded as a real problem");
    expect(screen.getByText(/A defect has been opened/)).toBeDefined();
  });

  it("confirmed · promises nothing when the project's policy raises no ticket", async () => {
    const base = stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: true })],
    ]);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        return {
          ok: true, status: 200, statusText: "stub",
          text: async () =>
            JSON.stringify({ id: FINDING, adjudication: "confirmed", outcome: "failure",
                             status: "open", severity: "low", opens_defect: false }),
        } as Response;
      }
      return base(input);
    }));
    renderWithProviders(<A11yReview />);

    await userEvent.click(await screen.findByRole("button", { name: /this is a real problem/ }));
    await screen.findByText("Recorded as a real problem");
    // A project may block on nothing at all (QA-08). Saying "a defect has been opened" there
    // would be the console lying about its own consequence.
    expect(screen.getByText(/does not raise a ticket at this severity/)).toBeDefined();
    expect(screen.queryByText(/A defect has been opened/)).toBeNull();
  });

  it("error · a refused decision says nothing was changed and keeps the note", async () => {
    const base = stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row()], can_review: true, lock_minutes: 15 }],
      [/a11y-review\/22222222/, item({ can_review: true })],
    ]);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        return {
          ok: false, status: 409, statusText: "stub",
          text: async () =>
            JSON.stringify({ detail: "Tom Reyes is reviewing this one, so your answer was not saved." }),
        } as Response;
      }
      return base(input);
    }));
    renderWithProviders(<A11yReview />);

    const note = await screen.findByPlaceholderText(/Why is this a real problem/);
    await userEvent.type(note, "the heading already says it");
    await userEvent.click(screen.getByRole("button", { name: /this is fine/ }));

    await screen.findByText("The decision could not be saved");
    await waitFor(() =>
      expect((note as HTMLTextAreaElement).value).toBe("the heading already says it"),
    );
  });
});

describe("the Accessibility destination", () => {
  it("is in the sidebar from day one, not revealed by a run", async () => {
    // D-A11Y-94. If the item only appeared after the first accessibility run, then "no menu"
    // and "nothing has ever been checked" would look identical — the exact silence this build
    // exists to prevent. Nothing here has ever run a check, and it is still there.
    vi.stubGlobal("fetch", stubRoutes([...AUTHED]));
    renderWithProviders(<AppShell />);
    const link = await screen.findByRole("link", { name: /Accessibility/ });
    // `/a11y/pages`, not `/a11y`. The tab strip puts Pages & audit first because that is where
    // the work starts, and the sidebar used to disagree — landing every first visit on the
    // review queue, the one tab with nothing on it until an audit has run.
    expect(link.getAttribute("href")).toBe("/a11y/pages");
    // Present, and with no badge, because nothing is waiting. The two facts are different and
    // the sidebar has to be able to say both.
    expect(link.querySelector(".nav-item__count")).toBeNull();
  });

  it("carries the count of findings waiting on this reviewer", async () => {
    // D-A11Y-94: "the count is how the reviewer learns there is work without going to look."
    // The item shipped as a plain link with no count — this is the regression test for that.
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row(), row({ id: "b" }), row({ id: "c" })],
                           can_review: true, lock_minutes: 15 }],
    ]));
    renderWithProviders(<AppShell />);

    const link = await screen.findByRole("link", { name: /Accessibility/ });
    await waitFor(() =>
      expect(link.querySelector(".nav-item__count")?.textContent).toBe("3"),
    );
  });

  it("shows no count to someone who cannot act on it", async () => {
    // The badge means "waiting on YOU". A developer can still open the queue and read every
    // finding; an alert for work they cannot do would just be noise on their sidebar.
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-review\/$/, { queue: [row(), row({ id: "b" })], can_review: false,
                           lock_minutes: 15 }],
    ]));
    renderWithProviders(<AppShell />);

    const link = await screen.findByRole("link", { name: /Accessibility/ });
    await waitFor(() => expect(link.querySelector(".nav-item__count")).toBeNull());
  });
});
