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
});
