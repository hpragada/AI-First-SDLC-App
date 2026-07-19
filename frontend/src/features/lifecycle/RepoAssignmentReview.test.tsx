// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";

afterEach(cleanup);
import { RepoAssignmentReview } from "./RepoAssignmentReview";
import type { Repository, WorkItemCard } from "../../types";

const repos: Repository[] = [
  { id: "r-api", name: "acme/api", role: "backend", default_base: "main", status: "connected", is_default: true, preview_url: "" },
  { id: "r-web", name: "acme/web", role: "frontend", default_base: "main", status: "connected", is_default: false, preview_url: "" },
];

function wi(id: string, repo: string, confidence: string, rationale: string): WorkItemCard {
  return {
    id,
    project: "p1",
    feature_stream: "",
    type: "task",
    state: "proposed",
    created_at: "",
    title: `Task ${id}`,
    repo,
    external_ref: { repo_assignment: { suggested_repo_id: repo, rationale, confidence, source: "agent" } },
  };
}

describe("B2 · Task Breakdown repo-assignment review", () => {
  const items = [
    wi("WI-1", "r-api", "high", "server-side webhook logic"),
    wi("WI-2", "r-web", "high", "a screen the user sees"),
    wi("WI-3", "r-api", "low", "this could belong to either app"),
  ];

  it("surfaces low-confidence first, groups the rest by repo, shows the plain reason", () => {
    renderWithProviders(
      <RepoAssignmentReview items={items} repos={repos} confirmed={{}} onOverride={vi.fn()} onKeep={vi.fn()} busy={false} />,
    );
    // the low-confidence task is flagged for review, with its plain-language reason
    expect(screen.getByText("needs review")).toBeDefined();
    expect(screen.getByText(/could belong to either app/)).toBeDefined();
    // the confident tasks are grouped under their repo names
    expect(screen.getByText("acme/api")).toBeDefined();
    expect(screen.getByText("acme/web")).toBeDefined();
  });

  it("fires onOverride when a task's repo is changed via the dropdown", () => {
    const onOverride = vi.fn();
    renderWithProviders(
      <RepoAssignmentReview items={items} repos={repos} confirmed={{}} onOverride={onOverride} onKeep={vi.fn()} busy={false} />,
    );
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "r-web" } });
    expect(onOverride).toHaveBeenCalledWith(expect.any(String), "r-web");
  });

  it("once a low-confidence task is confirmed, it stops being flagged", () => {
    renderWithProviders(
      <RepoAssignmentReview
        items={items}
        repos={repos}
        confirmed={{ "WI-3": true }}
        onOverride={vi.fn()}
        onKeep={vi.fn()}
        busy={false}
      />,
    );
    // the "needs review" group header is gone once the only low-confidence task is confirmed
    expect(screen.queryByText(/the planner wasn't sure about/)).toBeNull();
  });
});
