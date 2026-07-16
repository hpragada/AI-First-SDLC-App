// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import { Clarifications, isOtherOption } from "./Clarifications";
import { CriteriaGate } from "./CriteriaGate";
import { Gates } from "./Gates";
import { PhasesAndRuns } from "./PhasesAndRuns";
import { RunConsole } from "./RunConsole";
import { TaskBreakdown } from "./TaskBreakdown";
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
    expect(screen.getByText(/Paused — no usage billed/)).toBeDefined();

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
    expect(screen.getByText("Rejected — sent back for rework")).toBeDefined();
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
