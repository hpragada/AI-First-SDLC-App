import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";

interface Call {
  url: string;
  opts: { method: string; headers: Record<string, string>; body?: string };
}

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn(async (url: string, opts: Call["opts"]) => ({
    ok: status < 400,
    status,
    statusText: "stub",
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
    _seen: { url, opts },
  }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends X-Tenant-ID on tenant-scoped calls", async () => {
    const f = stubFetch(200, []);
    await api.listProjects("t-123");
    const [url, opts] = f.mock.calls[0];
    expect(url).toContain("/projects/");
    expect(opts.headers["X-Tenant-ID"]).toBe("t-123");
  });

  it("omits the tenant header on tenant-create and posts the name", async () => {
    const f = stubFetch(201, { id: "x", name: "Acme" });
    await api.createTenant("Acme");
    const [url, opts] = f.mock.calls[0];
    expect(url).toContain("/tenants/");
    expect(opts.headers["X-Tenant-ID"]).toBeUndefined();
    expect(JSON.parse(opts.body as string).name).toBe("Acme");
  });

  it("builds query strings, dropping empty params", async () => {
    const f = stubFetch(200, []);
    await api.listArtifacts("t", { project: "p1", phase: "prd", status: undefined });
    const [url] = f.mock.calls[0];
    expect(url).toContain("project=p1");
    expect(url).toContain("phase=prd");
    expect(url).not.toContain("status=");
  });

  it("triggerPhase posts the agent_key and returns the run id", async () => {
    const f = stubFetch(202, { run_id: "r1", workflow_id: "agent-run-r1" });
    const out = await api.triggerPhase("t", "wi-1", "03_prd");
    expect(JSON.parse(f.mock.calls[0][1].body as string).agent_key).toBe("03_prd");
    expect(out.run_id).toBe("r1");
  });

  it("raises ApiError on a non-2xx response", async () => {
    stubFetch(400, { detail: "bad request" });
    await expect(api.listProjects("t")).rejects.toBeInstanceOf(ApiError);
  });

  it("maps a 404 profile to null", async () => {
    stubFetch(404, { detail: "not found" });
    await expect(api.getProfile("t", "p1")).resolves.toBeNull();
  });

  it("fetches the traceability graph for a project", async () => {
    const f = stubFetch(200, { nodes: [], edges: [] });
    await api.getTraceability("t", "p1");
    const [url, opts] = f.mock.calls[0];
    expect(url).toContain("/projects/p1/traceability/");
    expect(opts.headers["X-Tenant-ID"]).toBe("t");
  });
});
