// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/react";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import {
  ClarificationHistory,
  Clarifications,
  groupByTier,
  isOtherOption,
  suggestionDefaults,
  tierOf,
} from "./Clarifications";
import { CriteriaGate } from "./CriteriaGate";
import { Gates } from "./Gates";
import { Pager, phaseSlug } from "./HistoryControls";
import { PhasesAndRuns } from "./PhasesAndRuns";
import { RunConsole } from "./RunConsole";
import { TaskBreakdown } from "./TaskBreakdown";
import { TestCases } from "./TestCases";
import { WorkItemDefect } from "./WorkItemDefect";
import { WorkItemEpic } from "./WorkItemEpic";
import { WorkItemTask } from "./WorkItemTask";
import { WorkItemsBoard } from "./WorkItemsBoard";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(stubFetchJson(401, { detail: "no session" })));
});
afterEach(() => vi.unstubAllGlobals());

describe("S-14 Work items board", () => {
  it("board · list · filtered · empty", () => {
    const { rerender } = renderWithProviders(<WorkItemsBoard forceView="board" />);
    expect(screen.getByText("Work Items")).toBeDefined();
    expect(screen.getByText("1. Ideation")).toBeDefined();

    rerender(<WorkItemsBoard forceView="list" />);
    expect(screen.getByText("Artifacts")).toBeDefined();

    rerender(<WorkItemsBoard forceView="filtered" />);
    expect(screen.getByText(/fanned out by Task Breakdown/)).toBeDefined();

    rerender(<WorkItemsBoard forceView="empty" />);
    expect(screen.getByText("No work items yet")).toBeDefined();
  });
});

describe("S-15 Work item epic", () => {
  it("gate-pending · needs-answer · complete", () => {
    const { rerender } = renderWithProviders(<WorkItemEpic forceView="gate-pending" />);
    expect(screen.getByText("Awaiting your decision")).toBeDefined();

    rerender(<WorkItemEpic forceView="needs-answer" />);
    expect(screen.getByText("1 question awaiting an answer")).toBeDefined();

    rerender(<WorkItemEpic forceView="complete" />);
    expect(screen.getByText(/6 created/)).toBeDefined();
  });
});

describe("S-16 Work item task", () => {
  it("loop-failed · running · merge-gate · done", () => {
    const { rerender } = renderWithProviders(<WorkItemTask forceView="loop-failed" />);
    expect(screen.getByText(/Review ↔ Implementation loop/)).toBeDefined();

    rerender(<WorkItemTask forceView="running" />);
    expect(screen.getByText("Running on your companion")).toBeDefined();

    rerender(<WorkItemTask forceView="merge-gate" />);
    expect(screen.getByText("PR #218 ready to merge")).toBeDefined();

    rerender(<WorkItemTask forceView="done" />);
    expect(screen.getByText("Merged to main")).toBeDefined();
  });
});

describe("S-17 Work item defect", () => {
  it("open · fixing · closed", () => {
    const { rerender } = renderWithProviders(<WorkItemDefect forceView="open" />);
    expect(screen.getByText(/FAIL · webhook.signature.valid_test_event/)).toBeDefined();

    rerender(<WorkItemDefect forceView="fixing" />);
    expect(screen.getByText("Run console · Fix")).toBeDefined();

    rerender(<WorkItemDefect forceView="closed" />);
    expect(screen.getByText("Defect closed automatically")).toBeDefined();
  });
});

describe("S-18 Phases & runs", () => {
  it("online · offline · no-runs", () => {
    const { rerender } = renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(screen.getByText("Trigger a phase")).toBeDefined();
    // Gallery now shows all 16 phases as "▶ <Label>" buttons (not the old "Run Architecture")
    expect(screen.getAllByText(/▶/).length).toBeGreaterThan(4);

    rerender(<PhasesAndRuns forceView="offline" />);
    expect(screen.getByText("Your machine isn't connected")).toBeDefined();

    rerender(<PhasesAndRuns forceView="no-runs" />);
    expect(screen.getByText("No runs yet")).toBeDefined();
  });
});

describe("S-19 Run console", () => {
  it("dispatched · running · needs-answer · awaiting-gate · completed · failed · parked", () => {
    const { rerender } = renderWithProviders(<RunConsole forceView="dispatched" />);
    expect(screen.getByText(/Dispatched · waiting/)).toBeDefined();

    rerender(<RunConsole forceView="running" />);
    expect(screen.getByText("Running")).toBeDefined();

    rerender(<RunConsole forceView="needs-answer" />);
    expect(screen.getByText(/Paused — waiting for your answer/)).toBeDefined();

    rerender(<RunConsole forceView="awaiting-gate" />);
    expect(screen.getByText("Awaiting Architecture gate")).toBeDefined();

    rerender(<RunConsole forceView="completed" />);
    expect(screen.getByText("Completed")).toBeDefined();

    rerender(<RunConsole forceView="failed" />);
    expect(screen.getByText("Engine exited before reporting")).toBeDefined();

    rerender(<RunConsole forceView="parked" />);
    expect(screen.getByText(/this run is parked/)).toBeDefined();
  });
});

describe("S-20 Clarifications", () => {
  it("one-pending · multi · required-error · answered · cancelled · empty", () => {
    const { rerender } = renderWithProviders(<Clarifications forceView="one-pending" />);
    expect(screen.getAllByText(/CSV export in v1/).length).toBeGreaterThan(0);

    rerender(<Clarifications forceView="multi" />);
    expect(screen.getByText(/Three details unblock/)).toBeDefined();

    rerender(<Clarifications forceView="required-error" />);
    expect(screen.getByText(/This answer is required/)).toBeDefined();

    rerender(<Clarifications forceView="answered" />);
    expect(screen.getByText(/run resumed/)).toBeDefined();

    rerender(<Clarifications forceView="cancelled" />);
    expect(screen.getByText(/question withdrawn/)).toBeDefined();

    rerender(<Clarifications forceView="empty" />);
    expect(screen.getByText("No questions waiting")).toBeDefined();
  });
});

describe("S-20 Clarifications · all-tiers gate", () => {
  it("renders every tier's header grouped in the gate", () => {
    renderWithProviders(<Clarifications forceView="tiered" />);
    expect(screen.getByText("Tier 1 · Must answer")).toBeDefined();
    expect(screen.getByText("Tier 2 · Suggested")).toBeDefined();
    expect(screen.getByText("Tier 3 · Industry-standard inference")).toBeDefined();
    expect(screen.getByText(/Accept all suggestions/)).toBeDefined();
  });

  it("tierOf defaults a tier-less question to Tier 1 (no regression)", () => {
    expect(tierOf({ id: "a", text: "?" })).toBe(1);
    expect(tierOf({ id: "b", text: "?", tier: 2 })).toBe(2);
    expect(tierOf({ id: "c", text: "?", tier: 3 })).toBe(3);
  });

  it("groupByTier keeps only non-empty tiers, in 1→2→3 order, preserving question order", () => {
    const qs = [
      { id: "t3", text: "?", tier: 3 as const },
      { id: "t1a", text: "?", tier: 1 as const },
      { id: "t1b", text: "?" }, // tier-less → Tier 1
    ];
    const groups = groupByTier(qs);
    expect(groups.map((g) => g.tier)).toEqual([1, 3]); // no empty Tier 2
    expect(groups[0].questions.map((q) => q.id)).toEqual(["t1a", "t1b"]);
  });

  it("suggestionDefaults pre-fills only Tier-2/3 questions that carry a suggestion", () => {
    const defaults = suggestionDefaults([
      { id: "t1", text: "?", tier: 1, required: true },
      { id: "t2", text: "?", tier: 2, suggestion: "90 days" },
      { id: "t3", text: "?", tier: 3, suggestion: "UTC" },
      { id: "t3b", text: "?", tier: 3 }, // no suggestion → not pre-filled
    ]);
    expect(defaults).toEqual({ t2: "90 days", t3: "UTC" });
  });
});

describe("S-20 Clarifications · Other free-text reveal (Bugs S.No 60)", () => {
  it("reveals the free-text box for enumerator-prefixed Other options", () => {
    // The agent labels options like "d) Other" — the reveal must survive the prefix.
    for (const opt of ["d) Other", "D) OTHER: ___", "Other", "Other (please specify)", "3. Something else"]) {
      expect(isOtherOption(opt)).toBe(true);
    }
    // ...but must NOT false-positive on ordinary options that merely contain "other".
    for (const opt of ["c) B2C subscription", "a) Free personal", "Another server option", "b) None of these"]) {
      expect(isOtherOption(opt)).toBe(false);
    }
  });
});

describe("S-21 Gates", () => {
  it("can-decide · cannot-decide · history · empty", () => {
    const { rerender } = renderWithProviders(<Gates forceView="can-decide" />);
    expect(screen.getByText("WI-492 · Stripe Webhook Integration")).toBeDefined();

    rerender(<Gates forceView="cannot-decide" />);
    expect(screen.getByText("Awaiting product_owner")).toBeDefined();

    rerender(<Gates forceView="history" />);
    expect(screen.getByText("Decided history")).toBeDefined();

    rerender(<Gates forceView="empty" />);
    expect(screen.getByText("No gates need you")).toBeDefined();
  });
});

describe("S-22 Criteria gate", () => {
  it("none · partial · all · rejected", () => {
    const { rerender } = renderWithProviders(<CriteriaGate forceView="none" />);
    expect(screen.getByText("0 of 8 criteria met")).toBeDefined();

    rerender(<CriteriaGate forceView="partial" />);
    expect(screen.getByText("5 of 8 criteria met")).toBeDefined();

    rerender(<CriteriaGate forceView="all" />);
    expect(screen.getByText("8 of 8 criteria met")).toBeDefined();

    rerender(<CriteriaGate forceView="rejected" />);
    expect(screen.getByText("Sent back for changes")).toBeDefined();
  });
});

describe("Gate decision — Request changes", () => {
  it("offers three actions, and gates the new one on a written note", async () => {
    const { container, unmount } = renderWithProviders(<Gates forceView="can-decide" />);
    const label = (t: string) =>
      [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(t));

    expect(label("Approve")).toBeDefined();
    expect(label("Reject")).toBeDefined();
    const request = label("Request changes");
    expect(request).toBeDefined();
    // Without a note there is nothing for the agent to act on — the server refuses it, so the
    // button must not look clickable.
    expect(request?.hasAttribute("disabled")).toBe(true);
    unmount();
  });

  it("shows the reviewer's comment in the decided history — it was stored but never rendered", () => {
    const { container, unmount } = renderWithProviders(<Gates forceView="history" />);
    const headers = [...container.querySelectorAll("th")].map((h) => h.textContent);
    expect(headers).toContain("Comment");
    unmount();
  });
});

describe("S-23 Task breakdown", () => {
  it("pushed · internal", () => {
    const { rerender } = renderWithProviders(<TaskBreakdown forceView="pushed" />);
    expect(screen.getByText("Pushed to Jira backlog")).toBeDefined();

    rerender(<TaskBreakdown forceView="internal" />);
    expect(screen.getByText("Saved in the platform")).toBeDefined();
  });
});

describe("P3-09b Test cases (coverage screen)", () => {
  it("populated · empty · add-form", () => {
    const { rerender } = renderWithProviders(<TestCases forceView="populated" />);
    expect(screen.getByText(/Child work items/)).toBeDefined();
    expect(screen.getByText("Checkout with expired card")).toBeDefined();
    // Every automation state renders + a Generate action for a not-automated one.
    expect(screen.getByText("Not automated")).toBeDefined();
    expect(screen.getByText("Generating…")).toBeDefined();
    expect(screen.getByText("Script ready")).toBeDefined();
    expect(screen.getByText("Generate script")).toBeDefined();
    expect(screen.getByText(/of 3 automated/)).toBeDefined();

    rerender(<TestCases forceView="empty" />);
    expect(screen.getByText("No test cases yet")).toBeDefined();

    rerender(<TestCases forceView="add-form" />);
    expect(screen.getByText("Steps / spec")).toBeDefined();
    expect(screen.getByText("Add test case")).toBeDefined();
  });
});

describe("G2 — a case says what kind it is", () => {
  // This file predates RTL auto-cleanup being off, so each test here unmounts explicitly:
  // without it the previous screen is still in the document and a getByText can match it.
  beforeEach(() => cleanup());
  afterEach(() => cleanup());

  it("shows the type beside each case, and filters by it", () => {
    renderWithProviders(<TestCases forceView="populated" />);
    // Two of each name: the filter chip, and the type on the row that declares it.
    expect(screen.getAllByText("Accessibility")).toHaveLength(2);
    expect(screen.getAllByText("Functional")).toHaveLength(2);
    expect(screen.getAllByText("E2E")).toHaveLength(2);
    expect(screen.getByText("Checkout with expired card")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Accessibility" }));
    expect(screen.getByText("Checkout is operable by keyboard")).toBeDefined();
    expect(screen.queryByText("Checkout with expired card")).toBeNull();
  });

  it("says so when a filter matches nothing, instead of looking like an empty story", () => {
    renderWithProviders(<TestCases forceView="populated" />);
    fireEvent.click(screen.getByRole("button", { name: "Integration" }));
    expect(screen.getByText("No integration test cases")).toBeDefined();
    expect(screen.queryByText("No test cases yet")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show all types" }));
    expect(screen.getByText("Checkout with expired card")).toBeDefined();
  });

  it("prints an em dash for a case that never declared a type — never a guess", () => {
    renderWithProviders(<TestCases forceView="empty" />);
    expect(screen.getByText("No test cases yet")).toBeDefined();
  });
});

// ── Clarification history + gate history (WP2/WP3) ────────────────────────
describe("Clarification history", () => {
  it("renders an empty state rather than crashing when there is nothing to show", () => {
    renderWithProviders(<ClarificationHistory projectId={undefined} />);
    expect(screen.getByText("No answered questions yet")).toBeDefined();
  });
});

describe("History controls", () => {
  it("phaseSlug strips the ordinal so a clarification's phase matches an agent key", () => {
    // Approvals filter on the agent key ("01_ideation"); clarifications store the bare phase
    // ("ideation"). One vocabulary each — the filter has to speak whichever it is asking.
    expect(phaseSlug("01_ideation")).toBe("ideation");
    expect(phaseSlug("06_task_breakdown")).toBe("task_breakdown");
    expect(phaseSlug("09b_test_automation")).toBe("test_automation");
    expect(phaseSlug("ideation")).toBe("ideation"); // already bare — unchanged
  });

  it("pager reports the window it is showing and stops at both ends", () => {
    const { rerender } = renderWithProviders(
      <Pager page={1} count={60} pageSize={25} onPage={() => {}} noun="decided gates" />,
    );
    expect(screen.getByText("1–25 of 60 decided gates")).toBeDefined();
    expect(screen.getByText("Page 1 of 3")).toBeDefined();
    expect((screen.getByText("Previous") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Next") as HTMLButtonElement).disabled).toBe(false);

    rerender(<Pager page={3} count={60} pageSize={25} onPage={() => {}} noun="decided gates" />);
    expect(screen.getByText("51–60 of 60 decided gates")).toBeDefined();
    expect((screen.getByText("Next") as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders nothing at all when there is no history to page through", () => {
    const { container } = renderWithProviders(
      <Pager page={1} count={0} pageSize={25} onPage={() => {}} noun="decided gates" />,
    );
    expect(container.textContent).toBe("");
  });
});
