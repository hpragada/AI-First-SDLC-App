// @vitest-environment jsdom
/**
 * Pausing a run and picking it up again, plus the confirmation before every phase trigger.
 *
 * The two things worth knowing before changing anything here.
 *
 * 1. **The pause dialog's wording is under test, not just its existence.** Pause cannot interrupt
 *    an agent that is already working — there is no channel from the platform to a companion at all,
 *    and a terminated run once kept writing for 49 minutes. So the dialog says which of two things
 *    is actually true, and the screen knows which from `status`. A single vague sentence covering
 *    both would be a promise we break in front of the client.
 *
 * 2. **A paused run and a parked one must not read the same.** A parked run stopped because
 *    something went wrong and the reader has to be told what; a paused run stopped because they
 *    chose to, and showing them an error would be calling their own decision a fault.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";

import { renderWithProviders } from "../../test/utils";
import { RunConsole } from "./RunConsole";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "admin" }],
};

const posted: string[] = [];

function stub(status: string, outputs: Record<string, unknown> = {}) {
  posted.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (init?.method === "POST") posted.push(u);
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/pause/")) return ok({ run_id: "run-1", paused: true, was_claimed: false });
    if (u.includes("/resume/")) return ok({ run_id: "run-1", resumed: true, resume_from: "x" });
    if (u.includes("/runs/run-1")) {
      return ok({
        id: "run-1", work_item: "wi-1", agent_spec: "s1", agent_key: "06_task_breakdown",
        agent_phase: "Task Breakdown", engine: "claude", model: "", status, cost_usd: null,
        temporal_workflow_id: "wf-run-1", outputs, started_at: null, ended_at: null,
        created_at: "2026-10-03T06:00:00Z",
      });
    }
    if (u.includes("/work-items/wi-1")) {
      return ok({ id: "wi-1", project: "p1", type: "story", key: "WI-9", title: "Login",
                  state: "in_progress" });
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
});

// ── offering the button ─────────────────────────────────────────────
describe("the Pause button", () => {
  it("is offered while a run is running", async () => {
    stub("running");
    renderRun();
    expect(await screen.findByRole("button", { name: "Pause run" })).toBeTruthy();
  });

  it("is offered before the companion has picked the run up", async () => {
    stub("pending");
    renderRun();
    expect(await screen.findByRole("button", { name: "Pause run" })).toBeTruthy();
  });

  it("is NOT offered on a run waiting at its gate", async () => {
    // Already stopped, and costing nothing. Offering to pause it would be offering to stop
    // something that is not running; the backend refuses it for the same reason.
    stub("awaiting_gate");
    renderRun();
    await screen.findByText(/artifact is a draft until its gate is approved/i);
    expect(screen.queryByRole("button", { name: "Pause run" })).toBeNull();
  });

  it("is NOT offered on a finished run", async () => {
    stub("completed");
    renderRun();
    await screen.findByText("Completed");
    expect(screen.queryByRole("button", { name: "Pause run" })).toBeNull();
  });
});

// ── the dialog tells the truth about timing ─────────────────────────
describe("the pause confirmation", () => {
  it("asks before pausing, and pauses nothing if you decline", async () => {
    stub("running");
    const user = userEvent.setup();
    renderRun();
    await user.click(await screen.findByRole("button", { name: "Pause run" }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Keep running" }));

    expect(posted.filter((u) => u.includes("/pause/"))).toHaveLength(0);
  });

  it("says the work stops dead when the companion has not started", async () => {
    stub("pending");
    const user = userEvent.setup();
    renderRun();
    await user.click(await screen.findByRole("button", { name: "Pause run" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/hasn't started this yet/i)).toBeTruthy();
    // And NOT the other sentence, which would be false here.
    expect(within(dialog).queryByText(/few minutes to come to a stop/i)).toBeNull();
  });

  it("says the current step finishes first when the agent is already working", async () => {
    stub("running");
    const user = userEvent.setup();
    renderRun();
    await user.click(await screen.findByRole("button", { name: "Pause run" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/finish the step it's on/i)).toBeTruthy();
    expect(within(dialog).getByText(/may take a few minutes to come to a stop/i)).toBeTruthy();
    // The honest way out, in the reader's words: we cannot reach their companion, they can.
    expect(within(dialog).getByText(/close the companion on your machine/i)).toBeTruthy();
    expect(within(dialog).queryByText(/hasn't started this yet/i)).toBeNull();
  });

  it("pauses the run when confirmed", async () => {
    stub("running");
    const user = userEvent.setup();
    renderRun();
    await user.click(await screen.findByRole("button", { name: "Pause run" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Pause run" }));

    expect(posted.some((u) => u.includes("/runs/run-1/pause/"))).toBe(true);
  });
});

// ── the paused view ─────────────────────────────────────────────────
describe("a paused run", () => {
  const paused = { paused: { by: "Ada", at: "2026-10-03T09:42:00Z", was_claimed: false },
                   resumable: true, resume_from: "dispatch_phase" };

  it("says it was paused, not that anything went wrong", async () => {
    stub("paused", paused);
    renderRun();
    expect(await screen.findByText("Paused by you")).toBeTruthy();
    expect(screen.getByText(/Paused by Ada/)).toBeTruthy();
    // The words for a machine going quiet must not appear on a run somebody paused themselves.
    expect(screen.queryByText(/stopped reporting/i)).toBeNull();
    expect(screen.queryByText(/Run failed/i)).toBeNull();
  });

  it("offers Resume and Discard, and never 'Take over'", async () => {
    stub("paused", paused);
    renderRun();
    expect(await screen.findByRole("button", { name: "Resume run" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Discard this run" })).toBeTruthy();
    // "Take over" is wording about rescuing something broken. Nothing is broken here.
    expect(screen.queryByRole("button", { name: /take over/i })).toBeNull();
  });

  it("only warns about the step in flight when the companion had actually started", async () => {
    stub("paused", paused);
    renderRun();
    await screen.findByText("Paused by you");
    expect(screen.queryByText(/may still be finishing the step/i)).toBeNull();

    cleanup();
    stub("paused", { ...paused, paused: { ...paused.paused, was_claimed: true } });
    renderRun();
    expect(await screen.findByText(/may still be finishing the step/i)).toBeTruthy();
  });

  it("asks before resuming, and resumes when confirmed", async () => {
    stub("paused", paused);
    const user = userEvent.setup();
    renderRun();
    await user.click(await screen.findByRole("button", { name: "Resume run" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Task Breakdown/)).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Resume run" }));

    expect(posted.some((u) => u.includes("/runs/run-1/resume/"))).toBe(true);
  });

  it("asks before discarding, and says the run cannot come back", async () => {
    stub("paused", paused);
    const user = userEvent.setup();
    renderRun();
    await user.click(await screen.findByRole("button", { name: "Discard this run" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/can't be resumed afterwards/i)).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Keep it paused" })).toBeTruthy();
  });
});

// ── a parked run is still a parked run ──────────────────────────────
it("a run parked at an error keeps its own wording", async () => {
  // Pinned so the paused view cannot quietly take the error park's words with it: this reader needs
  // to be told what went wrong, which the paused reader does not.
  stub("stalled", { error: "the engine reached its usage limit", resumable: true,
                    resume_from: "dispatch_phase" });
  renderRun();
  expect(await screen.findByRole("button", { name: "Resume from where it stopped" })).toBeTruthy();
  expect(screen.getByText(/usage limit/)).toBeTruthy();
  expect(screen.queryByText("Paused by you")).toBeNull();
});
