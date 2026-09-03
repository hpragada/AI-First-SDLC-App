// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

// Bugs.xlsx row 28.1: markdown artifacts must render (GFM), not show raw source.
describe("Markdown", () => {
  it("renders headings, GFM tables and inline code as HTML (not raw markdown)", () => {
    const md = [
      "# PRD",
      "",
      "Body with `inline` code.",
      "",
      "| Field | Value |",
      "| ----- | ----- |",
      "| ack   | 500ms |",
    ].join("\n");
    render(<Markdown>{md}</Markdown>);

    expect(screen.getByRole("heading", { level: 1, name: "PRD" })).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("cell", { name: "500ms" })).toBeTruthy();
    // the literal pipe-table source must not survive as text
    expect(screen.queryByText(/\| Field \| Value \|/)).toBeNull();
  });

  it("accepts a mermaid fenced block without throwing", () => {
    const md = ["```mermaid", "graph TD; A-->B;", "```"].join("\n");
    expect(() => render(<Markdown>{md}</Markdown>)).not.toThrow();
  });

  it("renders embedded markdown (bold/inline-code) without the doc-preview card when given a className (S.No 167)", () => {
    // Work-item descriptions embed markdown inside an existing Panel and pass "prose md-body".
    const md = "This is **bold** with `code`.";
    const { container } = render(<Markdown className="prose md-body">{md}</Markdown>);
    // no nested card wrapper
    expect(container.querySelector(".doc-preview")).toBeNull();
    expect(container.querySelector(".md-body")).toBeTruthy();
    // the ** and ` are rendered, not shown literally
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("code")?.textContent).toBe("code");
    expect(screen.queryByText(/\*\*bold\*\*/)).toBeNull();
  });

  it("wraps tables in a horizontal scroll container so they can't over-extend (S.No 165)", () => {
    const md = ["| A | B |", "| - | - |", "| 1 | 2 |"].join("\n");
    const { container } = render(<Markdown>{md}</Markdown>);
    const wrap = container.querySelector(".md-body__table-wrap");
    expect(wrap).toBeTruthy();
    // the table lives INSIDE the scroll wrapper
    expect(wrap?.querySelector("table")).toBeTruthy();
  });

  it("renders a mermaid diagram without the placeholder frame class that shrank it (S.No 165)", async () => {
    const md = ["```mermaid", "graph TD; A-->B;", "```"].join("\n");
    const { container } = render(<Markdown>{md}</Markdown>);
    // mermaid renders async; whether it succeeds (SVG in .md-body__mermaid) or fails in jsdom
    // (falls back to <pre> source), the output must NOT carry the `diagram-frame` class whose
    // `svg { 40px }` rule shrank real diagrams.
    await Promise.resolve();
    expect(container.querySelector(".diagram-frame")).toBeNull();
  });
});
