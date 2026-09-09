// @vitest-environment jsdom
//
// S-39 — one finding, opened to be read (the "where is the screenshot?" observation).
//
// Every AI finding an audit produces opens with "Screenshot shows…", and there was nowhere to
// go and see it: the only screen that drew a capture was the review console, which holds
// nothing except items awaiting a person, and a report is mostly confirmed failures.
//
// These assert the two things a screen like this can get wrong. It must not quietly take a
// review claim — a failure nobody is reviewing acquiring a reviewer's name is worse than no
// screen at all — and it must open by saying what the finding IS, because a failure and an
// unanswered question look identical below that line.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { api } from "../../api";
import { A11yFinding } from "./A11yFinding";

const PROJECT = "11111111-1111-1111-1111-111111111111";
const FINDING = "22222222-2222-2222-2222-222222222222";
const AUDIT = "48506881-0000-0000-0000-000000000000";

const ME = {
  user: { id: "u1", email: "aisha@acme.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "Payments", role: "qa_lead" }],
};

function finding(over: Record<string, unknown> = {}) {
  return {
    id: FINDING,
    criterion: "1.1.1",
    criterion_handle: "Non-text Content",
    wcag_level: "A",
    route: "/reports/lending-summary",
    selector: "#chart-lending",
    stable_selector: true,
    checker: "alt",
    verdict: "fail",
    confidence: 0.97,
    severity_if_confirmed: "critical",
    outcome: "failure",
    status: "open",
    evidence:
      'Screenshot shows a bar chart titled "Loans per month, 2026". The element carries ' +
      'alt="", hiding all chart data from assistive technology.',
    suggested_fix: 'Replace alt="" with descriptive alt text conveying the chart\'s data.',
    source_run: null,
    work_item_id: null,
    work_item_label: null,
    work_item_title: null,
    lock: { held: false, by_me: false, held_by: null, held_by_name: "", expires_at: null },
    page_image: false,
    element_image: false,
    box: null,
    url: "http://localhost:4180/reports/lending-summary",
    capture_reason: "",
    capture_key: AUDIT,
    can_review: true,
    locked_out: "",
    adjudication: "pending",
    note: "",
    captured_by: {
      id: AUDIT,
      label: "audit 48506881",
      finished_at: "2026-08-21T12:01:00Z",
      status: "complete",
      asked: 12,
      opened: 12,
    },
    ...over,
  };
}

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
  [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15, ever_checked: true }],
];

function show(body: unknown, status = 200) {
  const fetchMock = stubRoutes([...AUTHED, [/a11y-finding\//, body, status]]);
  vi.stubGlobal("fetch", fetchMock);
  renderWithProviders(
    <Routes>
      <Route path="/a11y/finding/:findingId" element={<A11yFinding />} />
    </Routes>,
    { route: `/a11y/finding/${FINDING}` },
  );
  return fetchMock;
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", PROJECT);
});
afterEach(() => {
  // vitest runs here without `globals: true`, so RTL's automatic cleanup is not wired up.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("S-39 one accessibility finding", () => {
  it("prints the whole of what the check saw and what to change", async () => {
    show(finding());

    await screen.findByText("1.1.1 Non-text Content");
    expect(screen.getByText(/hiding all chart data from assistive technology/)).toBeDefined();
    expect(screen.getByText(/Replace alt="" with descriptive alt text/)).toBeDefined();
  });

  it("reads the finding without ever asking for the review claim", async () => {
    // The whole reason this screen has an endpoint of its own. `a11y-review/<id>` claims the
    // item as a side effect, and following a link out of a report must not do that.
    const fetchMock = show(finding());

    await screen.findByText("1.1.1 Non-text Content");
    const asked = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(asked.some((u) => u.includes(`a11y-finding/${FINDING}`))).toBe(true);
    expect(asked.some((u) => u.includes(`a11y-review/${FINDING}`))).toBe(false);
  });

  it("says which audit took the picture, and when", async () => {
    show(finding());

    await screen.findByText("audit 48506881");
    expect(screen.getByText(/12 of 12 page\(s\)/)).toBeDefined();
  });

  it("names no audit at all rather than an empty one on a greenfield finding", async () => {
    show(finding({ captured_by: null }));

    await screen.findByText("1.1.1 Non-text Content");
    expect(screen.queryByText(/Found by/)).toBeNull();
  });

  it("opens by saying this is a failure, not by looking like an open question", async () => {
    show(finding());

    await screen.findByText("This is recorded as a failure");
  });

  it("says when it is still waiting on a person instead", async () => {
    show(finding({ outcome: "needs_review", verdict: "uncertain", confidence: null }));

    await screen.findByText("This one is still waiting on a person");
    expect(screen.getByText("Answer it in the review queue")).toBeDefined();
  });

  it("does not offer the review queue to somebody who cannot answer", async () => {
    show(finding({ outcome: "needs_review", can_review: false }));

    await screen.findByText("This one is still waiting on a person");
    expect(screen.queryByText("Answer it in the review queue")).toBeNull();
  });

  it("says why there is no picture rather than showing an empty frame", async () => {
    show(finding({ capture_reason: "the page would not screenshot within the time allowed" }));

    await screen.findByText("There is no picture of this one");
    expect(
      screen.getByText("the page would not screenshot within the time allowed"),
    ).toBeDefined();
  });

  it("a finding that cannot be loaded is not a finding that is fine", async () => {
    // Reports link here. A dead link out of a conformance document has to say it is dead.
    show({ detail: "no such finding on this project" }, 404);

    // A 404 is the one failure where the server's own sentence IS the right thing to show: it
    // describes the reader's data in plain words rather than our machinery (Bugs S.No 248).
    await screen.findByText(/This didn't load/i);
    expect(screen.getByText(/no such finding on this project/i)).toBeDefined();
  });
});

// ── the ring on the capture ─────────────────────────────────────────────────
//
// The ring is placed in PERCENTAGES of the capture's own pixels, so it is only right if the box
// it is positioned inside is exactly the size of the picture. It was not: it sat directly in
// `.shot__stage`, whose height CSS clamps to 340px while a full-page capture renders several
// times taller — so every percentage resolved against the clamp instead of the image. Measured
// on a real 1280x1144 shot in this panel: the ring landed 237.8px down where the element was at
// 461.3px, drawn 17.8px tall where the element was 34.6px. Every finding, since this shipped.
//
// jsdom computes no layout, so none of these can catch the pixels being wrong. What they hold is
// the ARRANGEMENT the corrected CSS depends on — the picture and the ring alone together inside
// `.shot__frame` — which is what a later edit would break without meaning to. A note in the
// stylesheet is not a test.
describe("the capture's ring", () => {
  beforeEach(() => {
    // jsdom implements no object URLs. The capture hook revokes its blob when the screen goes
    // away, so without this every test in here dies on unmount rather than on its assertion.
    URL.revokeObjectURL = vi.fn();
  });

  // The image never really loads here, and the screen deliberately draws no ring until it knows
  // the capture's true size — a box positioned before that is a guess. So the load is staged:
  // real dimensions, then the event the browser would have sent.
  const load = async (w: number, h: number) => {
    const image = await screen.findByAltText(/Captured screen/);
    Object.defineProperty(image, "naturalWidth", { value: w, configurable: true });
    Object.defineProperty(image, "naturalHeight", { value: h, configurable: true });
    await act(async () => {
      fireEvent.load(image);
    });
    return image as HTMLImageElement;
  };

  const withCapture = () => {
    vi.spyOn(api, "getA11yCaptureUrl").mockResolvedValue("blob:capture");
    return show(finding({
      page_image: true,
      box: { x: 320, y: 800, width: 300, height: 60 },
    }));
  };

  it("draws the ring inside the frame that wraps the picture, never loose in the stage", async () => {
    withCapture();
    const image = await load(1280, 1144);
    const frame = image.parentElement!;
    expect(frame.className).toContain("shot__frame");
    expect(frame.className).not.toContain("shot__stage");

    const ring = document.querySelector(".shot__marker");
    expect(ring).not.toBeNull();
    // Being a child of the frame is what makes the frame the box its percentages resolve
    // against. Being a child of the stage is the defect.
    expect(ring!.parentElement).toBe(frame);
  });

  it("puts nothing but the picture and the ring inside the frame", async () => {
    withCapture();
    const image = await load(1280, 1144);
    // Anything else in here has its own height and pushes the picture off the frame's origin,
    // which shifts every ring by however tall that thing is. The frame is not a layout container
    // and must never quietly become one.
    expect([...image.parentElement!.children].map((c) => c.className.split(" ")[0]))
      .toEqual(["shot__img", "shot__marker"]);
  });

  it("takes the ring's percentages from the capture's own pixels, not the panel's", async () => {
    withCapture();
    await load(1280, 1144);
    const ring = document.querySelector(".shot__marker") as HTMLElement;
    // 320/1280 and 300/1280 — exact, because the arithmetic is the picture's width and nothing
    // on screen is allowed into it.
    expect(ring.style.left).toBe("25%");
    expect(ring.style.width).toBe("23.4375%");
    // 800/1144 and 60/1144. This is the axis that was wrong: the stage's clamped height used to
    // stand in for 1144 here, and 800 came out at roughly half of where it belonged.
    expect(ring.style.top.startsWith("69.93")).toBe(true);
    expect(ring.style.height.startsWith("5.24")).toBe(true);
  });

  it("draws no ring at all until the capture's real size is known", async () => {
    withCapture();
    await screen.findByAltText(/Captured screen/);
    // Before the load event there is no natural size, and a box placed from a guessed one is
    // worse than no box — the reviewer would be shown a ring around the wrong element and told
    // it is evidence.
    expect(document.querySelector(".shot__marker")).toBeNull();
  });
});
