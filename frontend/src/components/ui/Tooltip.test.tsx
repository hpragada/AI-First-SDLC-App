// @vitest-environment jsdom
/**
 * The platform's first tooltip — and the reason it took an argument to add one.
 *
 * `Disclosure` in this folder exists partly because the usual hover tooltip cannot be opened
 * from a keyboard and does not exist on a touch screen, and a product whose job is finding that
 * defect on other people's sites cannot ship it in its own UI. These tests are what make this
 * one different, so the next tooltip someone copies from it inherits the same behaviour rather
 * than the usual one.
 *
 * WCAG 2.2 §1.4.13 asks content shown on hover or focus to be dismissible, hoverable and
 * persistent. There is a test below for each.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { Tooltip } from "./index";

afterEach(cleanup);

const TEXT = "Read on your own computer.";

describe("Tooltip — reachable without a mouse", () => {
  it("says nothing until it is asked to", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("has a real button, so Tab reaches it", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    const trigger = screen.getByRole("button", { name: "More information" });
    expect(trigger.tagName).toBe("BUTTON");
    // type="button" or a tooltip inside a form would submit it.
    expect(trigger.getAttribute("type")).toBe("button");
  });

  it("opens on KEYBOARD FOCUS, not only on hover — the whole point", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    fireEvent.focus(screen.getByRole("button"));
    expect(screen.getByRole("tooltip").textContent).toBe(TEXT);
  });

  it("opens on tap, so it exists on a touch screen", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("tooltip")).toBeDefined();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("is announced as the trigger's description, not as loose text", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    const trigger = screen.getByRole("button");
    fireEvent.focus(trigger);
    const id = trigger.getAttribute("aria-describedby");
    expect(id).toBeTruthy();
    expect(screen.getByRole("tooltip").getAttribute("id")).toBe(id);
  });

  it("describes nothing while closed", () => {
    // A description that is always wired up is read out on every visit to the trigger, which
    // turns one helpful sentence into noise on a screen full of them.
    render(<Tooltip>{TEXT}</Tooltip>);
    expect(screen.getByRole("button").getAttribute("aria-describedby")).toBeNull();
  });
});

describe("Tooltip — WCAG 2.2 §1.4.13", () => {
  it("DISMISSIBLE: Escape closes it", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    fireEvent.focus(screen.getByRole("button"));
    expect(screen.getByRole("tooltip")).toBeDefined();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("HOVERABLE: moving the pointer onto the bubble does not close it", () => {
    // The listeners are on the wrapper, so travelling from the trigger into the bubble to read
    // a long sentence never counts as leaving. If they were on the trigger, the tooltip would
    // vanish the moment someone reached for it.
    const { container } = render(<Tooltip>{TEXT}</Tooltip>);
    const wrapper = container.querySelector(".tip") as HTMLElement;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole("tooltip")).toBeDefined();
    fireEvent.mouseEnter(screen.getByRole("tooltip"));
    expect(screen.getByRole("tooltip")).toBeDefined();
    fireEvent.mouseLeave(wrapper);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("PERSISTENT: it does not close itself while focus stays put", async () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    fireEvent.focus(screen.getByRole("button"));
    await new Promise((r) => setTimeout(r, 60));
    expect(screen.getByRole("tooltip")).toBeDefined();
  });
});

describe("Tooltip — shape", () => {
  it("takes its own trigger, with the label describing that instead", () => {
    render(<Tooltip trigger={<span>what is this?</span>}>{TEXT}</Tooltip>);
    const trigger = screen.getByRole("button", { name: "what is this?" });
    fireEvent.focus(trigger);
    expect(screen.getByRole("tooltip").textContent).toBe(TEXT);
  });

  it("can open downwards, for a trigger near the top of the page", () => {
    render(<Tooltip placement="below">{TEXT}</Tooltip>);
    fireEvent.focus(screen.getByRole("button"));
    expect(screen.getByRole("tooltip").className).toContain("tip__bubble--below");
  });

  it("closes when focus leaves", () => {
    render(<Tooltip>{TEXT}</Tooltip>);
    const trigger = screen.getByRole("button");
    fireEvent.focus(trigger);
    fireEvent.blur(trigger);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
