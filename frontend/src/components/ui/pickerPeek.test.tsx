// @vitest-environment jsdom
/**
 * The work-item picker's cut-off titles (the team's option A).
 *
 * A dropdown row is one line as wide as its field, so a long label was cut with an ellipsis and
 * the rest was unreachable: no hover, no wrap, nothing. That is fine for the platform's own short
 * choices and wrong for work items, whose titles agents write from findings — they are long, and
 * the words that tell two of them apart are at the END ("ExpenseResponse missing created_at" vs
 * "ExpenseResponse missing currency"). A wrong pick starts a phase run on the wrong work item.
 *
 * The row now opens out over itself and shows the whole title, on hover AND on arrow-key
 * highlight, because a keyboard user cannot hover. It opens only when the label is ACTUALLY cut,
 * so short lists behave exactly as before.
 *
 * jsdom lays nothing out — every element reports zero width — so the measurements the component
 * reads are stubbed here per test: that is the ONLY thing faked, and each test says which rows it
 * is claiming are cut.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Combobox } from "./index";

const LONG = "WI-158 · ExpenseResponse missing created_at field required by API spec";
const OPTIONS = [
  { value: "a", label: LONG },
  { value: "b", label: "WI-12 · Login" },
];

/** Make every element claim its text is wider than its box — i.e. "everything here is cut". */
function stubEverythingCut() {
  Object.defineProperty(HTMLElement.prototype, "scrollWidth",
                        { configurable: true, get: () => 400 });
  Object.defineProperty(HTMLElement.prototype, "clientWidth",
                        { configurable: true, get: () => 200 });
}

/** ...and the opposite: nothing is cut, so nothing should open out. */
function stubNothingCut() {
  Object.defineProperty(HTMLElement.prototype, "scrollWidth",
                        { configurable: true, get: () => 100 });
  Object.defineProperty(HTMLElement.prototype, "clientWidth",
                        { configurable: true, get: () => 200 });
}

function restoreMeasurements() {
  for (const prop of ["scrollWidth", "clientWidth"]) {
    Object.defineProperty(HTMLElement.prototype, prop,
                          { configurable: true, get: () => 0 });
  }
}

/** The opened-out copy, which is the `.peek` drawn in the floating layer. */
const peek = () => document.querySelector(".peek");

function open(value = "") {
  return render(<Combobox id="wi" options={OPTIONS} value={value} onChange={() => {}} />);
}

beforeEach(() => vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
  cb(0);
  return 0;
}));
afterEach(() => {
  cleanup();
  restoreMeasurements();
  vi.unstubAllGlobals();
});

describe("a cut-off row", () => {
  it("shows its whole title when the pointer is on it", async () => {
    stubEverythingCut();
    const user = userEvent.setup();
    open();

    await user.click(screen.getByRole("combobox"));
    expect(peek()).toBeNull();                       // nothing hovered yet

    await user.hover(screen.getByRole("option", { name: LONG }));
    expect(peek()?.textContent).toBe(LONG);          // in full — not cut, not ellipsised
  });

  it("follows the arrow keys, so it works without a mouse", async () => {
    stubEverythingCut();
    const user = userEvent.setup();
    open();

    // The list opens with the first row highlighted, so the first ArrowDown moves to the second
    // and the second wraps back to the first. The opened-out copy tracks that highlight.
    await user.click(screen.getByRole("combobox"));
    await user.keyboard("{ArrowDown}");
    expect(peek()?.textContent).toBe("WI-12 · Login");

    await user.keyboard("{ArrowDown}");
    expect(peek()?.textContent).toBe(LONG);
  });

  it("is hidden again once the pointer leaves the list", async () => {
    stubEverythingCut();
    const user = userEvent.setup();
    open();

    await user.click(screen.getByRole("combobox"));
    await user.hover(screen.getByRole("option", { name: LONG }));
    expect(peek()).not.toBeNull();

    await user.unhover(screen.getByRole("option", { name: LONG }));
    expect(peek()).toBeNull();
  });

  it("closes with Escape, like every other popup", async () => {
    stubEverythingCut();
    const user = userEvent.setup();
    open();

    await user.click(screen.getByRole("combobox"));
    await user.keyboard("{ArrowDown}");
    expect(peek()).not.toBeNull();

    await user.keyboard("{Escape}");
    expect(peek()).toBeNull();
  });

  it("is not announced twice — the row's own text is already its name", async () => {
    stubEverythingCut();
    const user = userEvent.setup();
    open();

    await user.click(screen.getByRole("combobox"));
    await user.hover(screen.getByRole("option", { name: LONG }));

    expect(peek()?.getAttribute("aria-hidden")).toBe("true");
    // The option keeps its full accessible name, as it always had: only the CSS was cutting it.
    expect(screen.getByRole("option", { name: LONG })).toBeDefined();
  });

  it("also opens out on the closed field, once a long title is chosen", async () => {
    stubEverythingCut();
    const user = userEvent.setup();
    open("a");

    await user.hover(screen.getByRole("combobox"));

    expect(peek()?.textContent).toBe(LONG);
  });
});

describe("a row that fits", () => {
  it("does nothing at all, so short lists look exactly as they did", async () => {
    stubNothingCut();
    const user = userEvent.setup();
    open();

    await user.click(screen.getByRole("combobox"));
    await user.hover(screen.getByRole("option", { name: "WI-12 · Login" }));

    expect(peek()).toBeNull();
  });

  it("leaves the closed field alone too", async () => {
    stubNothingCut();
    const user = userEvent.setup();
    open("b");

    await user.hover(screen.getByRole("combobox"));

    expect(peek()).toBeNull();
  });
});

describe("picking", () => {
  it("takes the opened-out row away with the list", async () => {
    stubEverythingCut();
    const picked: string[] = [];
    const user = userEvent.setup();
    render(<Combobox id="wi" options={OPTIONS} value="" onChange={(v) => picked.push(v)} />);

    await user.click(screen.getByRole("combobox"));
    await user.hover(screen.getByRole("option", { name: LONG }));
    expect(peek()).not.toBeNull();

    await user.click(screen.getByRole("option", { name: LONG }));

    expect(picked).toEqual(["a"]);
    expect(peek()).toBeNull();
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("resting the pointer on the opened-out title", () => {
  // The flicker the team saw (2026-09-21). The peek is drawn OVER the row, so if it takes the
  // pointer, the list sees a mouse-leave and closes it, the row sees the mouse again and reopens
  // it — on every movement. jsdom has no hit-testing, so the loop cannot be driven here; what
  // prevents it is one style rule, and this pins it.
  it("lets the pointer through to the row, so it neither flickers nor swallows a click", async () => {
    const { readFileSync } = await import("node:fs");
    const css = readFileSync("src/styles/components.css", "utf-8");
    const rule = /\.peek\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(rule).toMatch(/pointer-events:\s*none/);
  });
});

describe("changing your mind", () => {
  // Found live by the team (2026-09-21): after a pick, focus stays in the field, and the list
  // opened only when the field GAINED focus — so clicking the field again did nothing.
  it("reopens the list when you click the field again after a pick", async () => {
    stubNothingCut();
    const user = userEvent.setup();
    function Picker() {
      const [v, setV] = useState("");
      return <Combobox id="wi" options={OPTIONS} value={v} onChange={setV} />;
    }
    render(<Picker />);
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: LONG }));
    expect(screen.queryByRole("listbox")).toBeNull();

    await user.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox")).not.toBeNull();
  });
});
