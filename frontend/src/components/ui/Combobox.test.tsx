// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Combobox } from "./index";

// This project doesn't enable testing-library's auto-cleanup, so unmount between cases —
// otherwise a second render leaves two comboboxes in the document.
afterEach(cleanup);

// Bugs S.No 150: the work-item picker was a plain <select> over every work item in the project,
// so finding one meant scrolling and eyeballing dozens of entries. The search must live IN the
// dropdown.
const OPTIONS = [
  { value: "1", label: "TASK-001 · Add login" },
  { value: "2", label: "TASK-002 · Stripe webhook integration" },
  { value: "3", label: "TASK-003 · Verify signing secret" },
];

const input = () => (screen.getByRole("combobox") as HTMLInputElement).value;

function Harness({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <Combobox id="wi" options={OPTIONS} value={value} onChange={setValue} />
      <span data-testid="value">{value}</span>
    </>
  );
}

describe("Combobox", () => {
  it("filters the options as you type and picks the one you click", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("combobox"));
    expect(screen.getAllByRole("option")).toHaveLength(3);

    await user.keyboard("stripe");                       // case-insensitive substring match
    const shown = screen.getAllByRole("option");
    expect(shown).toHaveLength(1);
    expect(shown[0].textContent).toContain("Stripe webhook integration");

    await user.click(shown[0]);
    expect(screen.getByTestId("value").textContent).toBe("2");
    // Closed again, showing the chosen label rather than the raw id.
    expect(screen.queryByRole("option")).toBeNull();
    expect(input()).toBe("TASK-002 · Stripe webhook integration");
  });

  it("is keyboard operable — arrows move, Enter picks", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("combobox"));
    await user.keyboard("{ArrowDown}{Enter}");           // active starts at 0 → ArrowDown → 1

    expect(screen.getByTestId("value").textContent).toBe("2");
  });

  it("says so when nothing matches, instead of showing an empty box", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("combobox"));
    await user.keyboard("zzz");

    expect(screen.queryByRole("option")).toBeNull();
    expect(screen.getByText("No matches")).toBeTruthy();
  });

  it("shows the current selection when closed", () => {
    render(<Harness initial="3" />);
    expect(input()).toBe("TASK-003 · Verify signing secret");
  });
});
