// @vitest-environment jsdom
/**
 * Bugs S.No 166 + 184 — popups no panel can clip, and a dropdown whose options wrap.
 *
 * 166: a panel hides whatever crosses its edge (`.panel { overflow: hidden }`), so a dropdown
 * opened inside one was cut off — and because a long list scrolls, it was the SHORT lists that
 * broke. The sweep found a second instance nobody had reported (the Work Items row menu). Every
 * popup now draws in one floating layer at the top of the page, which is what these tests pin:
 *   * the popup is not inside the panel it was opened from;
 *   * clicking INSIDE it still counts as inside — the classic way this change goes wrong is that
 *     "was the click inside the component?" starts answering no, and the menu closes under the
 *     pointer choosing from it;
 *   * near the bottom of the window it flips upwards (the team's option A), and only scrolls when
 *     it fits neither way.
 *
 * 184: the clarification answer control was the browser's own <select>, which the operating
 * system draws — nothing could keep a sentence-long option inside the card. `ChoiceSelect` is
 * drawn by the platform, and everything a native select gives for free is checked here.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";

import { ChoiceSelect, Combobox, Panel, RowMenu, Tooltip } from "./index";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** Puts the trigger (the input or button) at `trigger` on screen and makes every floating popup
 *  `popupHeight` tall — jsdom lays nothing out, so geometry has to be supplied. */
function geometry(trigger: Partial<DOMRect>, popupHeight: number) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const box = this.matches("input, button") ? trigger : {};
    return {
      top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0,
      toJSON() { return {}; },
      ...box,
    } as DOMRect;
  });
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (
    this: HTMLElement,
  ) {
    return this.classList.contains("popover-layer") ? popupHeight : 0;
  });
}

const ITEMS = [
  { value: "1", label: "ST-098 — Basket totals" },
  { value: "2", label: "ST-101 — Discount codes" },
  { value: "3", label: "ST-114 — Saved payment methods" },
];

function Picker() {
  const [value, setValue] = useState("");
  return (
    <Panel title="Trigger a phase">
      <Combobox id="wi" options={ITEMS} value={value} onChange={setValue} />
      <span data-testid="picked">{value}</span>
    </Panel>
  );
}

// ── 166: nothing clips a popup any more ─────────────────────────────
describe("a dropdown opened inside a panel", () => {
  it("is drawn outside the panel, so the panel cannot cut it off", async () => {
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("combobox"));

    const list = screen.getByRole("listbox");
    expect(list.closest(".panel")).toBeNull();
    expect(list.parentElement).toBe(document.body);
    expect(list.classList.contains("popover-layer")).toBe(true);
  });

  it("still picks the option you click — a click on the list is not an outside click", async () => {
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: "ST-114 — Saved payment methods" }));

    expect(screen.getByTestId("picked").textContent).toBe("3");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("closes on a click anywhere else", async () => {
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("combobox"));
    await user.click(document.body);

    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("where a dropdown opens (the team's option A: flip upwards)", () => {
  it("opens below the field when it fits there, as wide as the field", async () => {
    geometry({ top: 100, bottom: 140, left: 20, right: 320, width: 300, height: 40 }, 200);
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("combobox"));

    const list = screen.getByRole("listbox");
    expect(list.dataset.side).toBe("below");
    expect(list.style.top).toBe("144px");
    expect(list.style.width).toBe("300px");
    expect(list.style.maxHeight).toBe("");
  });

  it("flips above the field near the bottom of the window, whole, without a scrollbar", async () => {
    geometry({ top: 700, bottom: 740, left: 20, right: 320, width: 300, height: 40 }, 200);
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("combobox"));

    const list = screen.getByRole("listbox");
    expect(list.dataset.side).toBe("above");
    expect(list.style.top).toBe(`${700 - 4 - 200}px`);
    expect(list.style.maxHeight).toBe("");        // it fits above, so it is never squeezed
  });

  it("scrolls only when it fits neither way, on the side with more room", async () => {
    geometry({ top: 380, bottom: 420, left: 20, right: 320, width: 300, height: 40 }, 700);
    const user = userEvent.setup();
    render(<Picker />);

    await user.click(screen.getByRole("combobox"));

    const list = screen.getByRole("listbox");
    const above = 380 - 4 - 8;
    expect(list.dataset.side).toBe("above");      // 368px above beats 336px below
    expect(list.style.maxHeight).toBe(`${above}px`);
    expect(list.style.top).toBe(`${380 - 4 - above}px`);
  });
});

describe("the row menu on the Work Items list (the unreported second instance)", () => {
  function Row({ onCancel }: { onCancel: () => void }) {
    return (
      <MemoryRouter>
        <Panel title="Work items">
          <RowMenu
            label="Actions for WI-1"
            items={[{ label: "Open", href: "/work-items/wi-1" }, { label: "Cancel…", onSelect: onCancel }]}
          />
        </Panel>
      </MemoryRouter>
    );
  }

  it("is drawn outside its panel", async () => {
    const user = userEvent.setup();
    render(<Row onCancel={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Actions for WI-1" }));

    expect(screen.getByRole("menu").closest(".panel")).toBeNull();
  });

  it("lets you click an item — the menu does not close under the pointer", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<Row onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "Actions for WI-1" }));
    await user.click(screen.getByRole("menuitem", { name: "Cancel…" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("hands Tab back to the trigger, so focus carries on from where the menu was opened", async () => {
    // Drawn at the end of the page, a menu would otherwise send Tab off the page entirely.
    const user = userEvent.setup();
    render(<Row onCancel={() => {}} />);
    const trigger = screen.getByRole("button", { name: "Actions for WI-1" });

    await user.click(trigger);
    fireEvent.keyDown(document.activeElement as Element, { key: "Tab" });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("the tooltip", () => {
  it("draws in the same floating layer as every other popup", () => {
    render(<Panel title="Machine"><Tooltip>Read on your own computer.</Tooltip></Panel>);

    fireEvent.focus(screen.getByRole("button", { name: "More information" }));

    const bubble = screen.getByRole("tooltip");
    expect(bubble.closest(".panel")).toBeNull();
    expect(bubble.classList.contains("popover-layer")).toBe(true);
  });
});

// ── 184: the clarification answer control ───────────────────────────
const LONG =
  "Create a new backlog task for expenses CRUD router (GET/POST/PATCH/DELETE /api/v1/expenses) " +
  "and merge TASK-033 as-is";
const CHOICES = [LONG, "Extend TASK-033 to cover the full router", "Something else — I'll describe it"]
  .map((v) => ({ value: v, label: v }));

function Answer({ invalid = false }: { invalid?: boolean }) {
  const [value, setValue] = useState("");
  return (
    <Panel title="Question">
      <label>
        How should the expenses backlog be split?
        <ChoiceSelect options={CHOICES} value={value} onChange={setValue} invalid={invalid} />
      </label>
      <span data-testid="answer">{value}</span>
    </Panel>
  );
}

describe("ChoiceSelect", () => {
  it("is announced as a list of choices, and says nothing is chosen yet", () => {
    render(<Answer />);
    const box = screen.getByRole("combobox", { name: /expenses backlog/ });
    expect(box.tagName).toBe("BUTTON");
    expect(box.getAttribute("type")).toBe("button");       // never submits a form it sits in
    expect(box.getAttribute("aria-haspopup")).toBe("listbox");
    expect(box.getAttribute("aria-expanded")).toBe("false");
    expect(box.textContent).toBe("Choose one…");
  });

  it("shows a sentence-long option whole, in a list as wide as its field", async () => {
    geometry({ top: 100, bottom: 143, left: 20, right: 340, width: 320, height: 43 }, 180);
    const user = userEvent.setup();
    render(<Answer />);

    await user.click(screen.getByRole("combobox"));

    const list = screen.getByRole("listbox");
    expect(list.style.width).toBe("320px");
    expect(list.closest(".panel")).toBeNull();
    const option = within(list).getByRole("option", { name: LONG });
    expect(option.textContent).toBe(LONG);                  // not cut, not ellipsised
    expect(option.className).toContain("choice-select__option");
  });

  it("is keyboard operable: arrows move the highlight, Enter picks, focus stays on the control", async () => {
    const user = userEvent.setup();
    render(<Answer />);
    const box = screen.getByRole("combobox");
    box.focus();

    await user.keyboard("{ArrowDown}");
    const options = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(box.getAttribute("aria-expanded")).toBe("true");
    expect(box.getAttribute("aria-activedescendant")).toBe(options[0].id);

    await user.keyboard("{ArrowDown}");
    expect(box.getAttribute("aria-activedescendant")).toBe(options[1].id);

    await user.keyboard("{Enter}");
    expect(screen.getByTestId("answer").textContent).toBe(CHOICES[1].value);
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(box);
  });

  it("opens from the keyboard with Enter, the way any button does", async () => {
    const user = userEvent.setup();
    render(<Answer />);
    screen.getByRole("combobox").focus();

    await user.keyboard("{Enter}");

    expect(screen.getByRole("listbox")).toBeDefined();
  });

  it("closes on Escape and changes nothing", async () => {
    const user = userEvent.setup();
    render(<Answer />);
    screen.getByRole("combobox").focus();

    await user.keyboard("{ArrowDown}{ArrowDown}{Escape}");

    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByTestId("answer").textContent).toBe("");
  });

  it("picks with the pointer too", async () => {
    const user = userEvent.setup();
    render(<Answer />);

    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: LONG }));

    expect(screen.getByTestId("answer").textContent).toBe(LONG);
    expect(screen.getByRole("combobox").textContent).toBe(LONG);
  });

  it("carries the field's error state to assistive technology", () => {
    render(<Answer invalid />);
    expect(screen.getByRole("combobox").getAttribute("aria-invalid")).toBe("true");
  });
});
