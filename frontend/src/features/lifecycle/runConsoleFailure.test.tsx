// @vitest-environment jsdom
/**
 * Run-console wording (2026-09-21, option A). Two real screens showed the problem: a rejected
 * GitHub token printed "pr/gate setup failed: CapabilityError: GitHub GET … -> 401" run straight
 * into "Nothing you've done is lost", and a review stopped by a session limit pasted ten lines of
 * engine output into the banner.
 *
 * Now: the reason is one sentence of its own; "Nothing you've done is lost" is a separate line
 * naming what the platform says is kept; the raw text sits under a CLOSED "Technical details".
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { RunConsole } from "./RunConsole";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const SENTENCE =
  "The code review stopped because the AI engine reached its usage limit (resets 1:20 AM, " +
  "Asia/Kolkata). The code has not been reviewed yet. Resume once the limit resets.";
const RAW = "Command failed with exit code 1 (exit code: 1)\nLast agent output: …session limit";

function stub(outputs: Record<string, unknown>, status = "stalled") {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/runs/run-1")) {
      return ok({
        id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "07_implementation",
        agent_phase: "Implementation", engine: "claude", model: "", status, cost_usd: null,
        temporal_workflow_id: "build-run-1", outputs, started_at: null, ended_at: null,
        created_at: "2026-09-21T06:00:00Z",
      });
    }
    if (u.includes("/work-items/wi-1")) {
      return ok({ id: "wi-1", project: "p1", type: "task", title: "Login", state: "in_progress" });
    }
    return ok([]);
  }));
}

const renderRun = () =>
  renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunConsole />} />
    </Routes>,
    { route: "/runs/run-1" },
  );

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("a run paused on an error", () => {
  it("says the reason as its own sentence, then what is kept, with the raw text closed away", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ error: SENTENCE, error_detail: RAW, resumable: true, resume_from: "run_code_review",
           kept: "the build, branch and pull request are kept" });
    renderRun();

    const sentence = await screen.findByText(SENTENCE);
    expect(sentence.tagName).toBe("P");
    expect(screen.queryByText(/^Reason:/)).toBeNull();
    expect(screen.getByText(/Nothing you.ve done is lost — the build, branch and pull request are kept\./))
      .toBeDefined();

    const details = screen.getByText("Technical details").closest("details") as HTMLDetailsElement;
    expect(details).not.toBeNull();
    expect(details.open).toBe(false);                  // closed by default
    expect(details.textContent).toContain("Command failed with exit code 1");
  });

  it("falls back to the general line when the platform did not say what is kept", async () => {
    localStorage.setItem("selectedProjectId", "p1");
    stub({ error: "The phase stopped.", resumable: true });
    renderRun();

    expect(await screen.findByText(/Nothing you.ve done is lost — the work already finished is kept\./))
      .toBeDefined();
    expect(screen.queryByText("Technical details")).toBeNull(); // nothing raw to show
  });
});
