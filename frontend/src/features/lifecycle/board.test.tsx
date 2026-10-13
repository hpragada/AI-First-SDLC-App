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
 *
 * The follow-up the team then chose (option A): "Waiting for you" is a claim about the person
 * READING the board, and the board never checked. It said that to everyone — so a Designer read it
 * on a build gate only a Tech Lead can approve, while their own dashboard, which does check, said
 * nothing was waiting. Each waiting card now carries `needs.yours`, decided by the same rule as
 * the Approve and Answer buttons; work that is somebody else's still shows as waiting, in the
 * quiet grey, because the FACT is true and only the claim about whose it was is not.
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
         run_status: "awaiting_gate",
         needs: { gate: true, label: "Requirements gate", yours: true } }),
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
    expect(pillOn("Basket totals")).toBe("You can act on this: Waiting for review");
    expect(pillOn("Gift vouchers")).toBe("Failed");
    expect(pillOn("Address book")).toBe("Done");
  });

  it("never calls a finished phase that is waiting for a reviewer 'Done'", async () => {
    stub([card({ id: "s9", title: "Awaiting sign-off", current_phase: "03_prd",
                 run_status: "awaiting_gate" })]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Awaiting sign-off")).toBeDefined());
    // The run is at a gate, but no pending approval reached this card, so there is nobody to
    // name: it states the fact and claims nothing about whose it is.
    expect(pillOn("Awaiting sign-off")).toBe("Waiting for review");
  });

  it("marks a gate as yours only when this person may actually decide it", async () => {
    stub([
      card({ id: "m1", title: "Mine to approve", current_phase: "02_requirements",
             run_status: "awaiting_gate",
             needs: { gate: true, label: "Requirements gate", yours: true } }),
      card({ id: "m2", title: "Someone else's gate", current_phase: "07_implementation",
             run_status: "awaiting_gate",
             needs: { gate: true, label: "Build gate", yours: false } }),
    ]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Mine to approve")).toBeDefined());
    expect(pillOn("Mine to approve")).toBe("You can act on this: Waiting for review");
    // Still honestly waiting — just not on this person.
    expect(pillOn("Someone else's gate")).toBe("Waiting for review");
  });

  it("does the same for a question: the same words, marked when it is mine", async () => {
    stub([
      card({ id: "q1", title: "Mine to answer", current_phase: "02_requirements",
             run_status: "running",
             needs: { clarification: true, label: "Needs answer", yours: true } }),
      card({ id: "q2", title: "Not my project's question", current_phase: "02_requirements",
             run_status: "running",
             needs: { clarification: true, label: "Needs answer", yours: false } }),
    ]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Mine to answer")).toBeDefined());
    expect(pillOn("Mine to answer")).toBe("You can act on this: Waiting for answer");
    expect(pillOn("Not my project's question")).toBe("Waiting for answer");
  });

  it("keeps the neutral wording when an older API sends no 'yours' at all", async () => {
    stub([card({ id: "o1", title: "Older API gate", current_phase: "02_requirements",
                 run_status: "awaiting_gate",
                 needs: { gate: true, label: "Requirements gate" } })]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Older API gate")).toBeDefined());
    // Unknown is not the same as yours: it must not guess in the flattering direction.
    expect(pillOn("Older API gate")).toBe("Waiting for review");
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

describe("the person marker and the new pills (2026-10-08)", () => {
  it("draws the marker only on work that is yours, with a hover title", async () => {
    stub([
      card({ id: "y1", title: "Mine", current_phase: "02_requirements", run_status: "awaiting_gate",
             needs: { gate: true, label: "Requirements gate", yours: true } }),
      card({ id: "y2", title: "Theirs", current_phase: "02_requirements", run_status: "awaiting_gate",
             needs: { gate: true, label: "Requirements gate", yours: false } }),
    ]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Mine")).toBeDefined());
    const mine = screen.getByText("Mine").closest(".wi-card") as HTMLElement;
    const theirs = screen.getByText("Theirs").closest(".wi-card") as HTMLElement;
    expect(mine.querySelector(".badge__mine")?.getAttribute("title")).toBe("You can act on this");
    expect(theirs.querySelector(".badge__mine")).toBeNull();
  });

  it("names a paused run and a run that stopped responding", async () => {
    stub([
      card({ id: "p1", title: "Held", current_phase: "04_architecture", run_status: "paused" }),
      card({ id: "p2", title: "Gone quiet", current_phase: "03_prd", run_status: "stalled" }),
    ]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Held")).toBeDefined());
    expect(pillOn("Held")).toBe("Paused");
    expect(pillOn("Gone quiet")).toBe("Stopped responding");
  });
});

describe("the Phase, Role and Status filters (2026-10-08)", () => {
  // The filters are the app's own dropdown (FilterSelect), so each row is read as "label count".
  type User = ReturnType<typeof userEvent.setup>;
  const rowsOf = async (user: User, label: string) => {
    await user.click(screen.getByRole("button", { name: label }));
    const list = await screen.findByRole("listbox", { name: label });
    const rows = within(list).getAllByRole("option").map((o) =>
      Array.from(o.querySelectorAll("span")).map((sp) => sp.textContent).join(" "));
    await user.keyboard("{Escape}");
    return rows;
  };
  const choose = async (user: User, label: string, choice: string) => {
    await user.click(screen.getByRole("button", { name: label }));
    const list = await screen.findByRole("listbox", { name: label });
    const row = within(list).getAllByRole("option")
      .find((o) => o.querySelector("span")?.textContent === choice);
    if (!row) throw new Error(`no choice ${choice} in ${label}`);
    await user.click(row);
  };

  it("list every phase in lifecycle order, with counts, Backlog first, and no onboarding phase", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    expect(await rowsOf(user, "Filter by phase")).toEqual([
      "All phases 5", "Backlog 1", "Ideation 1", "Requirements 2", "PRD 1",
      "Architecture 0", "UX Design 0", "Task Breakdown 0", "Implementation 0",
      "Code Review 0", "Testing 0", "Test Automation 0", "Security 0", "CI/CD 0",
      "Deployment 0",
    ]);
  });

  it("list every status in the card's own words, and filter by them", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    expect(await rowsOf(user, "Filter by status")).toEqual([
      "All statuses 5", "Not started 1", "Running 1", "Paused 0",
      "Stopped responding 0", "Waiting for answer 0", "Waiting for review 1", "Done 1",
      "Failed 1", "Cancelled 0",
    ]);

    await choose(user, "Filter by status", "Waiting for review");
    expect(screen.getByText("Basket totals")).toBeDefined();
    expect(screen.queryByText("Address book")).toBeNull();
    // The closed box names the choice and its count — no brackets.
    expect(screen.getByRole("button", { name: "Filter by status" }).textContent)
      .toBe("Status: Waiting for review1");
  });

  it("count each choice under the OTHER filters already set", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    await choose(user, "Filter by phase", "Requirements");
    const statuses = await rowsOf(user, "Filter by status");
    expect(statuses[0]).toBe("All statuses 2");
    expect(statuses).toContain("Failed 1");
    expect(statuses).toContain("Done 0");
    // The phase list itself is not narrowed by its own choice.
    expect((await rowsOf(user, "Filter by phase"))[0]).toBe("All phases 5");
  });

  it("list the roles that sign off phases, in lifecycle order — never Engineer or Admin", async () => {
    const entry = (key: string, gate_role: string) => ({ key, label: key, agent_key: key, gate_role });
    const catalog = {
      plan: [entry("01_ideation", "product_owner"), entry("02_requirements", "product_owner"),
             entry("03_prd", "product_owner"), entry("04_architecture", "architect"),
             entry("05_ux_design", "designer"), entry("06_task_breakdown", "tech_lead"),
             entry("00_onboarding", "product_owner")],
      build: [entry("07_implementation", "tech_lead"), entry("08_code_review", "reviewer"),
              entry("09_testing", "qa_lead"), entry("09b_test_automation", "qa_lead"),
              entry("10_security", "security_engineer"), entry("11_cicd", "devops"),
              entry("12_deployment", "devops")],
      remediation: [],
    };
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
      if (u.includes("/auth/me")) return ok(me);
      if (u.includes("/phases")) return ok(catalog);
      if (u.includes("/work-items")) return ok(STORIES);
      return ok([]);
    }));
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    await waitFor(async () => expect((await rowsOf(user, "Filter by role")).length).toBeGreaterThan(1));
    expect(await rowsOf(user, "Filter by role")).toEqual([
      "All roles 5", "Product Owner 4", "Architect 0", "Designer 0", "Tech Lead 0",
      "Reviewer 0", "QA Lead 0", "Security Engineer 0", "DevOps 0",
    ]);
  });

  it("filter down to the Backlog", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    await choose(user, "Filter by phase", "Backlog");
    expect(screen.getByText("Saved payment methods")).toBeDefined();
    expect(screen.queryByText("Discount codes")).toBeNull();
  });

  it("works from the keyboard: open, move, pick, and focus returns to the box", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Address book")).toBeDefined());
    const box = screen.getByRole("button", { name: "Filter by phase" });
    box.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("listbox", { name: "Filter by phase" })).toBeDefined();
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");   // All phases → Backlog → Ideation
    expect(screen.queryByRole("listbox", { name: "Filter by phase" })).toBeNull();
    expect(document.activeElement).toBe(box);
    expect(box.textContent).toBe("Phase: Ideation1");
    expect(screen.queryByText("Saved payment methods")).toBeNull();
  });
});

// ── the New work item drawer ────────────────────────────────────────
//
// Two gaps the QA team found on a demo project, in the same small panel.
//
// A work item could be created with no description, and then no screen could add one: the drawer
// had no field, and there was no edit surface anywhere (S.No 76). The API had accepted
// `description` on create all along — only the input was missing.
//
// And the four type definitions were concatenated into one string, rendered as help text AND as
// the select's hover tooltip, unchanged by what you picked. QA read it as "plain text all mixed
// which is not readable", and the real cost is that the choice being made is a COMPARISON between
// four things, which a wall of prose makes hardest of all.
describe("creating a work item", () => {
  function stubWrites(writes: Array<{ url: string; body: unknown }>) {
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      const ok = (body: unknown) =>
        ({ ok: true, status: 200, statusText: "ok",
           text: async () => JSON.stringify(body) }) as Response;
      if ((init?.method ?? "GET").toUpperCase() !== "GET") {
        writes.push({ url: u, body: JSON.parse(String(init?.body ?? "{}")) });
        return ok({ id: "new-1" });
      }
      if (u.includes("/auth/me")) return ok(me);
      return ok([]);
    }));
  }

  it("sends the description typed into the drawer", async () => {
    const writes: Array<{ url: string; body: unknown }> = [];
    stubWrites(writes);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    await user.type(screen.getByLabelText(/Title/), "Stripe webhooks");
    await user.type(screen.getByLabelText(/Description/), "Verify the signing secret.");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].body).toMatchObject({
      title: "Stripe webhooks",
      description: "Verify the signing secret.",
    });
  });

  it("leaves the description optional", async () => {
    // A quick task should not be blocked by a prose field — and since it can now be edited
    // afterwards, an item created without one is no longer stuck that way.
    const writes: Array<{ url: string; body: unknown }> = [];
    stubWrites(writes);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    await user.type(screen.getByLabelText(/Title/), "Quick fix");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(writes.length).toBe(1));
    expect(writes[0].body).toMatchObject({ title: "Quick fix", description: "" });
  });

  // 2026-09-30: the legend moved behind an ⓘ beside the Type label. Somebody creating their
  // fiftieth work item does not need four definitions re-explained every time. The contract is
  // otherwise unchanged and is still tested in full — four rows, each carrying its own
  // definition, and the highlight following the select — only now it has to be opened first.
  const legendTip = () => screen.getByRole("button", { name: /what the work item types mean/i });

  it("keeps the definitions out of the way until they are asked for", async () => {
    stubWrites([]);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));

    // Nothing on screen until the ⓘ is used — that is the whole point of the change.
    expect(document.querySelectorAll(".wi-type-legend__row").length).toBe(0);
    expect(legendTip()).toBeDefined();
  });

  it("shows all four type definitions as separate, readable rows", async () => {
    stubWrites([]);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    // `hover`, not `click`: a click fires focus (which opens it) and then the trigger's own
    // toggle (which closes it again). Hover and focus are how this is actually reached.
    await user.hover(legendTip());

    const rows = document.querySelectorAll(".wi-type-legend__row");
    expect(rows.length).toBe(4);
    expect([...rows].map((r) => r.querySelector(".wi-type-legend__term")?.textContent))
      .toEqual(["Epic", "Story", "Task", "Defect"]);
    // Each row carries its own definition, not all four.
    const epic = rows[0].querySelector(".wi-type-legend__desc")?.textContent ?? "";
    expect(epic).toContain("large feature or initiative");
    expect(epic).not.toContain("bug fix");
  });

  it("opens the definitions from the keyboard, and closes them with Escape", async () => {
    // The reason this is a `Tooltip` and not a `title=` attribute or a hover-only bubble. A
    // product that sells finding this defect on other people's sites does not get to ship one.
    stubWrites([]);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    legendTip().focus();

    await waitFor(() => expect(document.querySelectorAll(".wi-type-legend__row").length).toBe(4));

    await user.keyboard("{Escape}");

    await waitFor(() => expect(document.querySelectorAll(".wi-type-legend__row").length).toBe(0));
  });

  it("marks the row for the type currently chosen", async () => {
    stubWrites([]);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    await user.hover(legendTip());
    // The drawer opens on Epic.
    expect(document.querySelector(".wi-type-legend__row.is-selected")
      ?.querySelector(".wi-type-legend__term")?.textContent).toBe("Epic");

    await user.unhover(legendTip());
    await user.selectOptions(screen.getByLabelText("Type"), "defect");
    await user.hover(legendTip());

    expect(document.querySelectorAll(".wi-type-legend__row.is-selected").length).toBe(1);
    expect(document.querySelector(".wi-type-legend__row.is-selected")
      ?.querySelector(".wi-type-legend__term")?.textContent).toBe("Defect");
  });
});

// -- no raw UUID reaches a card (2026-09-30) -------------------------
//
// `WorkItemSerializer.key` carries the comment "so the UI never has to show the UUID". The chip
// naming a card's parent printed all 36 characters of `parent`, because the parent had no key of
// its own to print. It does now.
describe("the parent chip on a card", () => {
  it("names the parent by its key", async () => {
    stub([card({ id: "c1", key: "WI-9", title: "Child item",
                 parent: "65db8214-f26c-4246-b63e-81297b5f50df", parent_key: "WI-2" })]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Child item")).toBeDefined());
    const cardEl = screen.getByText("Child item").closest(".wi-card") as HTMLElement;

    expect(cardEl.textContent).toContain("WI-2");
    expect(cardEl.textContent).not.toContain("65db8214");
  });

  it("draws no chip at all when there is no key to draw", async () => {
    // An older API sending `parent` without `parent_key`. A chip reading "↖ 65db8214" tells the
    // reader nothing, so nothing is the better answer.
    stub([card({ id: "c1", key: "WI-9", title: "Child item",
                 parent: "65db8214-f26c-4246-b63e-81297b5f50df" })]);
    renderWithProviders(<WorkItemsBoard />);

    await waitFor(() => expect(screen.getByText("Child item")).toBeDefined());
    const cardEl = screen.getByText("Child item").closest(".wi-card") as HTMLElement;

    expect(cardEl.textContent).not.toContain("65db8214");
    expect(cardEl.textContent).not.toContain("↖");
  });
});

// ── one Escape dismisses one layer (2026-09-30) ─────────────────────
//
// Every overlay listens for Escape on `window`, so they all fired at once: opening the type
// tooltip inside the drawer and pressing Escape shut the tooltip AND the drawer, throwing away
// whatever had been typed. The tooltip is the app's first overlay-inside-an-overlay, which is why
// this surfaced now; the fix is in `useEscapeToClose` and covers every future pair.
describe("Escape inside the create drawer", () => {
  it("closes the tooltip and leaves the drawer, and what was typed, alone", async () => {
    stub([]);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    await user.type(screen.getByLabelText(/Title/), "Half-written title");
    screen.getByRole("button", { name: /what the work item types mean/i }).focus();
    await waitFor(() => expect(document.querySelectorAll(".wi-type-legend__row").length).toBe(4));

    await user.keyboard("{Escape}");

    // The tooltip went...
    await waitFor(() => expect(document.querySelectorAll(".wi-type-legend__row").length).toBe(0));
    // ...and the drawer, with the typing still in it, did not.
    expect(screen.getByDisplayValue("Half-written title")).toBeDefined();
  });

  it("still closes the drawer itself on the next Escape", async () => {
    // The fix must not make the drawer un-closable — one press per layer, from the top down.
    stub([]);
    const user = userEvent.setup();
    renderWithProviders(<WorkItemsBoard />);

    await user.click(await screen.findByRole("button", { name: /New Work Item/ }));
    expect(screen.getByLabelText(/Title/)).toBeDefined();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByLabelText(/Title/)).toBeNull());
  });
});


// ── Recon 2026-10-10, mockup M9 — one status everywhere ────────────────────────────────────
//
// A new accessibility defect is stored "in progress" (nothing has run on it yet). The Board read
// "Not started", the List read "In progress" and the defect page said "In progress" — one item,
// two statuses. Every screen now takes the Board's word.
describe("a work item's status reads the same on every screen", () => {
  it("an untouched defect is 'Not started', whatever its stored state says", async () => {
    const { boardStatusLabel } = await import("./WorkItemsBoard");
    expect(boardStatusLabel(card({ type: "defect", state: "in_progress" }) as never))
      .toBe("Not started");
    expect(boardStatusLabel(card({ state: "cancelled" }) as never)).toBe("Cancelled");
    expect(boardStatusLabel(card({ current_phase: "01_ideation", run_status: "running" }) as never))
      .toBe("Running");
  });
});
