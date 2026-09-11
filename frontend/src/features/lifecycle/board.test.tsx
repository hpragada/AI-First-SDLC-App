// @vitest-environment jsdom
/**
 * Bugs S.No 117 — the Work Items board.
 *
 * A work item's column comes from the phase of its latest run. A brand-new item has no run, so no
 * phase — and the board dropped it into whichever column happened to be FIRST: Ideation on the
 * default board, Implementation once filtered to Tasks. Both reported symptoms were that one line.
 * A second fault sat on the same line: the Tasks view's columns were keyed `implementation` and
 * `review`, while a code-review run reduces to `code_review`, so code-review tasks landed in
 * Implementation even when they DID have a run.
 *
 * The team chose option B: a Backlog column, and a status pill on each card saying what its phase
 * is doing — Running · Waiting for you · Done · Failed (four, because a phase that has finished
 * but waits for a person is not "Done").
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { WorkItemsBoard } from "./WorkItemsBoard";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Checkout", role: "product_owner" }],
};

const card = (over: Record<string, unknown>) => ({
  id: "wi", key: "ST-1", number: 1, project: "p1", feature_stream: "", type: "story",
  state: "in_progress", created_at: "2026-09-01T00:00:00Z", title: "Item", artifact_count: 0,
  current_phase: "", run_status: "", needs: null, ...over,
});

const STORIES = [
  card({ id: "s1", key: "ST-114", title: "Saved payment methods", state: "proposed" }),
  card({ id: "s2", key: "ST-101", title: "Discount codes", current_phase: "01_ideation",
         run_status: "running" }),
  card({ id: "s3", key: "ST-098", title: "Basket totals", current_phase: "02_requirements",
         run_status: "awaiting_gate", needs: { gate: true, label: "Requirements gate" } }),
  card({ id: "s4", key: "ST-093", title: "Gift vouchers", current_phase: "02_requirements",
         run_status: "failed" }),
  card({ id: "s5", key: "ST-090", title: "Address book", current_phase: "03_prd",
         run_status: "completed" }),
];

const TASKS = [
  card({ id: "t1", key: "TASK-1", type: "task", title: "Not picked up yet", state: "proposed" }),
  card({ id: "t2", key: "TASK-2", type: "task", title: "Under review",
         current_phase: "08_code_review", run_status: "running" }),
  card({ id: "t3", key: "TASK-3", type: "task", title: "Being built",
         current_phase: "07_implementation", run_status: "running" }),
  card({ id: "t4", key: "TASK-4", type: "task", title: "Pipeline work",
         current_phase: "11_cicd", run_status: "completed" }),
];

function stub(stories: unknown[] = STORIES, tasks: unknown[] = TASKS) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/work-items") && u.includes("type=task")) return ok(tasks);
    if (u.includes("/work-items")) return ok(stories);
    return ok([]);
  }));
}

/** The board column with this exact title. */
function column(title: string): HTMLElement {
  const heading = screen.getAllByText(title).find((el) => el.classList.contains("board__col-title"));
  if (!heading) throw new Error(`no column titled ${title}`);
  return heading.closest(".board__col") as HTMLElement;
}

/** The pill on the card with this title, wherever it sits. */
function pillOn(title: string): string {
  const cardEl = screen.getByText(title).closest(".wi-card") as HTMLElement;
  return (cardEl.querySelector(".wi-card__top .badge") as HTMLElement).textContent ?? "";
}

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("where a card sits", () => {
  it("puts an item nothing has run on in Backlog, not in the first phase", async () => {
    stub();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Saved payment methods")).toBeDefined());
    expect(within(column("Backlog")).getByText("Saved payment methods")).toBeDefined();
    expect(within(column("1. Ideation")).queryByText("Saved payment methods")).toBeNull();
    // ...and the items that HAVE a phase are in it.
    expect(within(column("1. Ideation")).getByText("Discount codes")).toBeDefined();
    expect(within(column("2. Requirements")).getByText("Basket totals")).toBeDefined();
    expect(within(column("3. PRD")).getByText("Address book")).toBeDefined();
  });

  it("keeps an unstarted item in Backlog when the view is filtered to Tasks — it no longer jumps", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: "Tasks" }));

    await waitFor(() => expect(screen.getByText("Not picked up yet")).toBeDefined());
    expect(within(column("Backlog")).getByText("Not picked up yet")).toBeDefined();
    expect(within(column("Implementation")).queryByText("Not picked up yet")).toBeNull();
  });

  it("puts a task in code review in Review, not Implementation", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: "Tasks" }));

    await waitFor(() => expect(screen.getByText("Under review")).toBeDefined());
    expect(within(column("Review")).getByText("Under review")).toBeDefined();
    expect(within(column("Implementation")).getByText("Being built")).toBeDefined();
    expect(within(column("Implementation")).queryByText("Under review")).toBeNull();
  });

  it("gives a phase this view has no column for a column of its own, rather than a wrong one", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: "Tasks" }));

    await waitFor(() => expect(screen.getByText("Pipeline work")).toBeDefined());
    expect(within(column("CI/CD")).getByText("Pipeline work")).toBeDefined();
    expect(within(column("Backlog")).queryByText("Pipeline work")).toBeNull();
    expect(within(column("Implementation")).queryByText("Pipeline work")).toBeNull();
  });
});

describe("what each card says (option B, a status pill)", () => {
  it("says what its phase is doing, in words", async () => {
    stub();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    expect(pillOn("Saved payment methods")).toBe("Not started");
    expect(pillOn("Discount codes")).toBe("Running");
    expect(pillOn("Basket totals")).toBe("Waiting for you");
    expect(pillOn("Gift vouchers")).toBe("Failed");
    expect(pillOn("Address book")).toBe("Done");
  });

  it("never calls a finished phase that is waiting for a reviewer 'Done'", async () => {
    stub([card({ id: "s9", title: "Awaiting sign-off", current_phase: "03_prd",
                 run_status: "awaiting_gate" })]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Awaiting sign-off")).toBeDefined());
    expect(pillOn("Awaiting sign-off")).toBe("Waiting for you");
  });

  it("keeps the work item's own badge when an older API sends no run status", async () => {
    const legacy = { ...card({ id: "s8", title: "Older API", current_phase: "03_prd" }) };
    delete (legacy as Record<string, unknown>).run_status;
    stub([legacy]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Older API")).toBeDefined());
    expect(pillOn("Older API")).toBe("In progress");
  });
});
