// @vitest-environment jsdom
//
// S-20 Clarifications — the LIVE screen, against a stubbed API.
//
// The gallery tests next door render fixed views. These render the real one, because the bug
// this file exists for lived entirely in how the live screen chose what to show: the sidebar
// badge counted the project's pending questions server-side, and the page narrowed the whole
// tenant's down to the work items on the visible backlog. A run on a HIDDEN carrier work item —
// accessibility judging, code indexing, the gap report — is deliberately absent from that
// backlog, so its question was counted and then filtered away. The badge said 1, the page said
// none, and the run waited for an answer the screen would not let anybody give.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { Clarifications } from "./Clarifications";

const PROJECT = "22222222-2222-2222-2222-222222222222";

const ME = {
  user: { id: "u1", email: "aisha@acme.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "Meridian", role: "qa_lead" }],
};

// The question a judging run asks. Its work item is the hidden carrier — never on the board,
// which is the whole point of a carrier and was also the whole bug.
const CARRIER_QUESTION = {
  id: "c1",
  run: "run-1",
  run_status: "running",
  work_item: "99999999-9999-9999-9999-999999999999",
  work_item_title: "Accessibility judging - WCAG-Audit",
  phase: "a11y_judge",
  status: "pending",
  questions: [{ id: "q1", text: "Is the interior photo decorative?", kind: "text", required: true }],
  answers: {},
  context: "1.1.1 on /about/history",
  answered_by: null,
  answered_at: null,
  created_at: "2026-08-21T09:00:00Z",
};

/** Records every URL asked for, so a test can assert what the screen asked the API — which is
 *  where this fix actually lives. */
function stub(clarifications: unknown[], seen: string[]) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    seen.push(url);
    const body = /\/auth\/me\//.test(url)
      ? ME
      : /\/clarifications\//.test(url)
        ? clarifications
        : /\/work-items\//.test(url)
          ? []              // the backlog, with the carrier correctly absent from it
          : {};
    return {
      ok: true, status: 200, statusText: "stub",
      text: async () => JSON.stringify(body),
    } as Response;
  });
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", PROJECT);
});
afterEach(() => {
  // vitest runs without `globals: true`, so RTL's automatic cleanup is not wired up.
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("S-20 Clarifications · a question from a headless run", () => {
  it("shows a question whose work item is not on the backlog", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", stub([CARRIER_QUESTION], seen));
    renderWithProviders(<Clarifications />);

    expect(await screen.findByText(/Is the interior photo decorative/)).toBeTruthy();
    // …and it is answerable, not merely visible. A question nobody can answer stalls the run
    // exactly as effectively as one nobody can see.
    expect(screen.getByRole("button", { name: /Submit answer/i })).toBeTruthy();
  });

  it("names the run in words, rather than showing a bare id", async () => {
    // The label used to be looked up in the backlog, so a carrier's — the one kind of work item
    // guaranteed not to be there — fell through to eight characters of uuid.
    const seen: string[] = [];
    vi.stubGlobal("fetch", stub([CARRIER_QUESTION], seen));
    renderWithProviders(<Clarifications />);

    expect(await screen.findByText(/Accessibility judging - WCAG-Audit/)).toBeTruthy();
  });

  it("asks the API for this project's questions instead of narrowing them here", async () => {
    // The fix itself. Scoping in the browser is what dropped the carrier's question, and it is
    // also what made the page and the sidebar badge answer differently from the same data.
    const seen: string[] = [];
    vi.stubGlobal("fetch", stub([CARRIER_QUESTION], seen));
    renderWithProviders(<Clarifications />);
    await screen.findByText(/Is the interior photo decorative/);

    const asked = seen.find((u) => u.includes("/clarifications/")) ?? "";
    expect(asked).toContain(`project=${PROJECT}`);
    expect(asked).toContain("status=pending");
  });

  it("with nothing pending, still says so rather than showing a stale question", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", stub([], seen));
    renderWithProviders(<Clarifications />);

    expect(await screen.findByText("No questions waiting")).toBeTruthy();
  });

  it("with no project chosen yet, shows nothing rather than another project's questions", async () => {
    // The query drops an empty filter instead of sending one, so an unscoped fetch would return
    // the whole workspace. That is a second project's private question on this project's screen.
    localStorage.removeItem("selectedProjectId");
    const seen: string[] = [];
    vi.stubGlobal("fetch", stub([CARRIER_QUESTION], seen));
    renderWithProviders(<Clarifications />);

    expect(await screen.findByText(/Loading/i)).toBeTruthy();
    expect(screen.queryByText(/Is the interior photo decorative/)).toBeNull();
  });
});

// ── Bugs S.No 184 — a sentence-long choice stays on the card, and "Other" still works ──────────
// The answer control was the browser's own <select>; the operating system draws that list, so an
// agent's whole-sentence option ran off the card on one line. It is now drawn by the platform. The
// part that must NOT change is what gets submitted: picking the "something else" option reveals a
// box, and it is the typed text — never the option's label — that the agent receives.
const LONG_OPTION =
  "Create a new backlog task for expenses CRUD router (GET/POST/PATCH/DELETE /api/v1/expenses) " +
  "and merge TASK-033 as-is";

const CHOICE_QUESTION = {
  ...CARRIER_QUESTION,
  id: "c2",
  work_item_title: "Expenses",
  context: "",
  questions: [{
    id: "q1", text: "How should the expenses backlog be split?", kind: "choice", required: true,
    options: [LONG_OPTION, "Extend TASK-033 to cover the full router", "Something else — please specify"],
  }],
};

function stubRecordingWrites(writes: Array<{ url: string; body: unknown }>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "stub", text: async () => JSON.stringify(body) }) as Response;
    if ((init?.method ?? "GET").toUpperCase() !== "GET") {
      writes.push({ url, body: JSON.parse(String(init?.body ?? "{}")) });
      return ok({ ...CHOICE_QUESTION, status: "answered" });
    }
    if (/\/auth\/me\//.test(url)) return ok(ME);
    if (/\/clarifications\//.test(url)) return ok(writes.length ? [] : [CHOICE_QUESTION]);
    return ok([]);
  });
}

describe("S-20 Clarifications · the answer control (S.No 184)", () => {
  it("is no longer the browser's own dropdown, and shows a long option whole", async () => {
    vi.stubGlobal("fetch", stubRecordingWrites([]));
    const user = userEvent.setup();
    renderWithProviders(<Clarifications />);

    const box = await screen.findByRole("combobox", { name: /expenses backlog/ });
    expect(document.querySelector("select")).toBeNull();
    await user.click(box);

    expect(screen.getByRole("option", { name: LONG_OPTION }).textContent).toBe(LONG_OPTION);
  });

  it("submits what was typed against 'something else', not the option's label", async () => {
    const writes: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal("fetch", stubRecordingWrites(writes));
    const user = userEvent.setup();
    renderWithProviders(<Clarifications />);

    await user.click(await screen.findByRole("combobox", { name: /expenses backlog/ }));
    await user.click(screen.getByRole("option", { name: /Something else/ }));
    await user.type(await screen.findByLabelText("Please specify"), "Split it into two tasks");
    await user.click(screen.getByRole("button", { name: /Submit answer/ }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].url).toContain("/clarifications/c2/answer/");
    expect(writes[0].body).toEqual({ answers: { q1: "Split it into two tasks" } });
  });

  it("still treats 'something else' with nothing typed as unanswered", async () => {
    const writes: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal("fetch", stubRecordingWrites(writes));
    const user = userEvent.setup();
    renderWithProviders(<Clarifications />);

    await user.click(await screen.findByRole("combobox", { name: /expenses backlog/ }));
    await user.click(screen.getByRole("option", { name: /Something else/ }));
    await user.click(screen.getByRole("button", { name: /Submit answer/ }));

    expect(await screen.findByText(/This answer is required/)).toBeTruthy();
    expect(writes.length).toBe(0);
  });

  it("submits an ordinary option exactly as it reads", async () => {
    const writes: Array<{ url: string; body: unknown }> = [];
    vi.stubGlobal("fetch", stubRecordingWrites(writes));
    const user = userEvent.setup();
    renderWithProviders(<Clarifications />);

    await user.click(await screen.findByRole("combobox", { name: /expenses backlog/ }));
    await user.click(screen.getByRole("option", { name: LONG_OPTION }));
    await user.click(screen.getByRole("button", { name: /Submit answer/ }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].body).toEqual({ answers: { q1: LONG_OPTION } });
  });
});
