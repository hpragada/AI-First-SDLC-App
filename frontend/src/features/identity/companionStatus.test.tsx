// @vitest-environment jsdom
// `useCompanionStatus` is the one place the product answers "is my machine there?", so this is
// where that answer is pinned down. The first test is the reported bug; the rest are the edges
// that made the old two-line derivation wrong in ways nobody noticed.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCompanionStatus } from "./hooks";
import type { Runner } from "../../types";

const PROJECT = "p1";
const OTHER = "p2";

const runner = (over: Partial<Runner> = {}): Runner => ({
  id: "r1",
  machine: "Dev laptop",
  last_seen: "2026-10-05T09:00:00Z",
  age_s: 3,
  online: true,
  projects: [{ project_id: PROJECT, project_name: "SpendLog" }],
  ...over,
});

function Probe({ projectId }: { projectId?: string }) {
  const s = useCompanionStatus(projectId);
  return <output>{`${s.state}|${s.machine}|${s.everConnected}`}</output>;
}

// Reads through the render's OWN container rather than the global `screen`. Two tests below
// render twice (the same data seen from two projects), and `screen` searches the whole document,
// so it finds both probes and throws "found multiple elements" instead of comparing them.
function show(rows: Runner[], projectId: string | undefined = PROJECT) {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true, status: 200, statusText: "ok",
    text: async () => JSON.stringify(rows),
  }) as Response));
  // A fresh QueryClient per render, so one test's cached ["runners"] answer cannot be read by
  // the next — which would make these pass for the wrong reason.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container } = render(
    <QueryClientProvider client={qc}>
      <Probe projectId={projectId} />
    </QueryClientProvider>,
  );
  return () => container.querySelector("output")?.textContent ?? "";
}

async function stateOf(rows: Runner[], projectId: string | undefined = PROJECT) {
  const read = show(rows, projectId);
  await waitFor(() => expect(read()).not.toContain("unknown"));
  return read().split("|")[0];
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("whose machine, and for which project", () => {
  it("does NOT call it connected because a machine on ANOTHER project is alive", async () => {
    // THE REPORTED BUG, as a named regression. The old reading was
    // `runners.some(r => r.online)` — "is any machine of mine alive anywhere?" — so a companion
    // serving a different project kept the pill green while the one running the phase on screen
    // was dead. Every other defect in this sweep corrected itself within 2¼ minutes. This one
    // never did.
    const rows = [
      runner({ id: "dead", online: false, age_s: 600 }),
      runner({
        id: "alive", online: true, age_s: 2,
        projects: [{ project_id: OTHER, project_name: "Other project" }],
      }),
    ];
    expect(await stateOf(rows, PROJECT)).toBe("offline");
    // And the same data from the other project's point of view, so this is scoping rather than
    // a blanket pessimism that happens to pass.
    expect(await stateOf(rows, OTHER)).toBe("ready");
  });

  it("reads one machine serving two projects as connected for both", async () => {
    // A labelled machine bound to several projects is ONE process, so its single liveness is
    // true everywhere it serves. Scoping must not turn that into a false offline.
    const both = [runner({
      projects: [
        { project_id: PROJECT, project_name: "SpendLog" },
        { project_id: OTHER, project_name: "Other project" },
      ],
    })];
    expect(await stateOf(both, PROJECT)).toBe("ready");
    expect(await stateOf(both, OTHER)).toBe("ready");
  });

  it("ignores a machine that names no project rather than crashing", async () => {
    // A row without `projects` must not take down the app shell, which mounts this on every
    // screen in the product. It reads as serving nothing — the safe answer.
    const noProjects = [{ ...runner(), projects: undefined as unknown as Runner["projects"] }];
    expect(await stateOf(noProjects)).toBe("offline");
  });
});

describe("the three bands", () => {
  it("is ready when the machine called in moments ago", async () => {
    expect(await stateOf([runner({ online: true, age_s: 3 })])).toBe("ready");
  });

  it("is checking once it has gone quiet but before the server gives up", async () => {
    // The band that closes the 2¼-minute blind window. A companion heartbeats every 30s but is
    // only called offline after 2 minutes, so a machine dead for 90s still reports `online`.
    // Amber says so at ~40s without touching that threshold — which also drives dispatch
    // routing and the claim lease, and was not worth disturbing for this.
    expect(await stateOf([runner({ online: true, age_s: 75 })])).toBe("checking");
  });

  it("is offline once the server stops calling it online", async () => {
    expect(await stateOf([runner({ online: false, age_s: 300 })])).toBe("offline");
  });

  it("stays ready when the server sends no age at all", async () => {
    // An API too old to send `age_s` degrades to the two states it always had. It must not
    // fall into the amber band and tell everybody their machine is dying.
    expect(await stateOf([runner({ online: true, age_s: undefined })])).toBe("ready");
  });
});

describe("before it knows", () => {
  it("claims nothing while the first answer is still in flight", async () => {
    // "unknown" is rendered as not-connected everywhere it is shown. The important half is that
    // it is never rendered as READY: a pill that says connected before asking is the hardcoded
    // green badge that was fixed once already (S.No 18).
    const read = show([runner()]);
    expect(read().split("|")[0]).toBe("unknown");
    await waitFor(() => expect(read().split("|")[0]).toBe("ready"));
  });

  it("claims nothing when no project is selected", async () => {
    const read = show([runner()], undefined);
    await waitFor(() => expect(read()).toBeTruthy());
    expect(read().split("|")[0]).toBe("unknown");
  });
});

describe("dropped versus never set up", () => {
  it("knows a machine was once connected, so the words can say reconnect", async () => {
    const read = show([runner({ online: false, age_s: 900 })]);
    await waitFor(() => expect(read()).toContain("offline"));
    expect(read().split("|")[2]).toBe("true");
  });

  it("knows a token was minted and never used, so the words can say connect", async () => {
    // Identical by "is it online", opposite in what to tell somebody. Telling a new user to
    // RE-connect a machine they never connected is its own small dead end.
    const read = show([runner({ online: false, age_s: undefined, last_seen: null })]);
    await waitFor(() => expect(read()).toContain("offline"));
    expect(read().split("|")[2]).toBe("false");
  });
});
