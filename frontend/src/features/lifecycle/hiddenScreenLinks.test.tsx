// @vitest-environment jsdom
/**
 * Screen Words group 7, Option A — two built screens nobody could reach now have a way in.
 *
 *   * Contracts & drift (`/contracts`) is linked from Repositories, on split and multi-repo
 *     projects only: contracts exist between repositories, so a single-repo project has nothing
 *     there to open.
 *   * Run transcripts (`/transcripts/:id`) are linked from a run's own console once it has
 *     completed or been approved — the only runs the transcript screen lists.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { Repositories } from "../setup/Repositories";
import { RunConsole } from "./RunConsole";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const ok = (body: unknown) =>
  ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;

function stub(routes: (u: string) => unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    if (u.includes("/auth/me")) return ok(me);
    const body = routes(u);
    return ok(body === undefined ? [] : body);
  }));
}

const repo = (id: string, name: string) =>
  ({ id, name, role: "backend", default_base: "main", preview_url: "", status: "connected",
     is_default: id === "r1" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("Repositories links to contracts & drift", () => {
  const renderWith = (topology: string, repos: unknown[]) => {
    localStorage.setItem("selectedProjectId", "p1");
    stub((u) => (u.includes("/repositories")
      ? { repo_topology: topology, repositories: repos } : undefined));
    renderWithProviders(<Repositories />);
  };

  it("offers the link on a split project", async () => {
    renderWith("split", [repo("r1", "acme/api"), repo("r2", "acme/web")]);
    const link = await screen.findByRole("link", { name: /API contracts & drift/ });
    expect(link.getAttribute("href")).toBe("/contracts");
  });

  it("does not offer it on a single-repo project, where there are no contracts", async () => {
    renderWith("single", [repo("r1", "acme/api")]);
    await waitFor(() => expect(screen.getByText("acme/api")).toBeDefined());
    expect(screen.queryByRole("link", { name: /API contracts & drift/ })).toBeNull();
  });
});

describe("a run's console links to its transcript", () => {
  const renderRun = (status: string) => {
    localStorage.setItem("selectedProjectId", "p1");
    stub((u) => {
      if (u.includes("/runs/run-1")) {
        return {
          id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "03_prd",
          agent_phase: "PRD", engine: "claude", model: "", status, cost_usd: null,
          temporal_workflow_id: "run-1", outputs: {}, started_at: null, ended_at: null,
          created_at: "2026-09-18T06:00:00Z",
        };
      }
      if (u.includes("/work-items/wi-1")) {
        return { id: "wi-1", project: "p1", type: "epic", title: "Rounding", state: "in_progress" };
      }
      return undefined;
    });
    renderWithProviders(
      <Routes>
        <Route path="/runs/:id" element={<RunConsole />} />
      </Routes>,
      { route: "/runs/run-1" },
    );
  };

  it.each(["completed", "approved"])("offers it once the run is %s", async (status) => {
    renderRun(status);
    const link = await screen.findByRole("link", { name: /Full transcript/ });
    expect(link.getAttribute("href")).toBe("/transcripts/run-1");
  });

  it.each(["running", "failed"])("does not offer it while the run is %s", async (status) => {
    renderRun(status);
    await waitFor(() => expect(screen.getByText("Progress")).toBeDefined());
    expect(screen.queryByRole("link", { name: /Full transcript/ })).toBeNull();
  });
});
