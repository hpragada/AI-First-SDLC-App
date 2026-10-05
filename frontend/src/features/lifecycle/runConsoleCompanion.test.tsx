// @vitest-environment jsdom
/**
 * A run handed to a machine that isn't there.
 *
 * The console used to show such a run as RUNNING, with a live spinner, for up to the two hours
 * until takeover — because dispatching sets the run's status to RUNNING while leaving
 * `inputs.dispatch.status` at "pending". By status alone a stranded run and a run being actively
 * worked on are the same thing, so every test here drives the two apart.
 *
 * Both conditions are tested in isolation as well as together, because each on its own is
 * normal: an unclaimed dispatch with a live machine is a run about to start (the claim poll is
 * ~5s), and an offline machine holding a CLAIMED dispatch is one working away that has gone
 * quiet — telling that reader to reconnect would throw away work in progress.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { RunConsole } from "./RunConsole";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const CONNECTED = [{
  id: "r1", machine: "Dev laptop", online: true, age_s: 3, last_seen: "2026-10-05T09:00:00Z",
  projects: [{ project_id: "p1", project_name: "Platform" }],
}];
const DROPPED = [{
  id: "r1", machine: "Dev laptop", online: false, age_s: 600, last_seen: "2026-10-05T08:50:00Z",
  projects: [{ project_id: "p1", project_name: "Platform" }],
}];

function stub({ dispatch, runners }: { dispatch: string; runners: unknown[] }) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok",
         text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/runners")) return ok(runners);
    if (u.includes("/events/")) return ok([]);
    if (u.includes("/runs/run-1")) {
      return ok({
        id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "01_ideation",
        agent_phase: "Ideation", engine: "claude", model: "claude-opus-5",
        // RUNNING with an unclaimed dispatch is the exact state the bug lived in, so it is the
        // state these tests use.
        status: "running", cost_usd: null, temporal_workflow_id: "agent-run-1",
        inputs: { dispatch: { kind: "plan", enrollment_id: "r1", status: dispatch } },
        outputs: {},
        started_at: "2026-10-05T09:00:00Z", ended_at: null, created_at: "2026-10-05T09:00:00Z",
      });
    }
    if (u.includes("/work-items/wi-1")) {
      return ok({ id: "wi-1", project: "p1", type: "task", title: "Login", key: "WI-265",
                  state: "in_progress" });
    }
    return ok([]);
  }));
}

function renderConsole() {
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunConsole />} />
    </Routes>,
    { route: "/runs/run-1" },
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const STRANDED = /Your machine isn't connected — this hasn't started/i;
const NOTHING_TO_DO = /nothing to do/i;

describe("a run nobody's machine picked up", () => {
  it("says so, and says what to do about it", async () => {
    stub({ dispatch: "pending", runners: DROPPED });
    renderConsole();
    await waitFor(() => expect(screen.getByText(STRANDED)).toBeTruthy());
    // The one thing that fixes it has to be reachable from here.
    expect(screen.getByRole("link", { name: /Reconnect your machine/i })).toBeTruthy();
  });

  it("stops telling the reader there is nothing to do", async () => {
    // The sentence it used to show instead, and the reason this is a bug rather than a gap:
    // "nothing to do" was not merely unhelpful, it was the opposite of the truth, and it was
    // shown for hours.
    stub({ dispatch: "pending", runners: DROPPED });
    renderConsole();
    await waitFor(() => expect(screen.getByText(STRANDED)).toBeTruthy());
    expect(screen.queryByText(NOTHING_TO_DO)).toBeNull();
  });

  it("names no machine word or id while doing it", async () => {
    stub({ dispatch: "pending", runners: DROPPED });
    renderConsole();
    await waitFor(() => expect(screen.getByText(STRANDED)).toBeTruthy());
    const html = document.body.innerHTML;
    expect(html).not.toContain("run-1");
    expect(html).not.toContain("dispatch");
    expect(html).not.toContain("pending");
    expect(html).not.toContain("01_ideation");
  });
});

describe("the two states that are NOT a problem", () => {
  it("leaves an unclaimed run alone while the machine is there", async () => {
    // About to start, not stranded. A machine claims within about five seconds, and a reconnect
    // banner in that window would be false and would flicker on every ordinary trigger.
    stub({ dispatch: "pending", runners: CONNECTED });
    renderConsole();
    await waitFor(() => expect(screen.getByRole("heading", { name: /Run console/i })).toBeTruthy());
    expect(screen.queryByText(STRANDED)).toBeNull();
  });

  it("says nothing when the machine went quiet but had already claimed the work", async () => {
    // The case that makes the dispatch check necessary rather than just correct. A claimed run
    // on a quiet machine is being worked on; a companion only reports at the end of a phase, so
    // telling this reader to reconnect would be wrong AND would discard real work.
    stub({ dispatch: "claimed", runners: DROPPED });
    renderConsole();
    await waitFor(() => expect(screen.getByRole("heading", { name: /Run console/i })).toBeTruthy());
    expect(screen.queryByText(STRANDED)).toBeNull();
  });
});
