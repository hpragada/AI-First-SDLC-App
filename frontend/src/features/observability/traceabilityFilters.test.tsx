// @vitest-environment jsdom
/**
 * P3 — the traceability map had no way in (the team's option A-full).
 *
 * Filters were drawn for this screen during the build and only ever landed in the component
 * gallery at /dev/components, wired to nothing, one of them offering "Highlight: WI-492 lineage" —
 * a work item invented for that gallery, which exists in no project. The live screen shipped with
 * the colour legend alone, so on a real project it is a few hundred boxes with no way to narrow
 * them and no way to follow one work item's chain, which is the question the map exists to answer.
 *
 * Phase and type NARROW the map. A work item HIGHLIGHTS: its documents stay lit and the rest dims
 * rather than disappearing, so the chain is readable without losing the surrounding shape. The
 * documents adopted during brownfield onboarding belong to no work item — no run produced them —
 * so they are offered as a group of their own instead of being the one set the filter cannot
 * reach.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { TraceabilityView } from "./TraceabilityView";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "SpendLog", role: "product_owner" }],
};

const node = (over: Record<string, unknown>) => ({
  id: "n", kind: "artifact", phase: "prd", type: "prd", title: "A document", status: "draft",
  sor: "internal", external_ref: null, url: null,
  work_item: "w1", work_item_key: "WI-152", work_item_title: "Currency rounding rule", ...over,
});

const NODES = [
  node({ id: "a1", title: "PRD — Currency rounding" }),
  node({ id: "a2", title: "Requirements — Rounding rule", phase: "requirements",
         type: "requirements" }),
  node({ id: "a3", title: "Architecture — Payments", phase: "architecture", type: "architecture",
         work_item: "w2", work_item_key: "WI-158", work_item_title: "Saved cards" }),
  // Adopted in onboarding: no run produced it, so it belongs to no work item.
  node({ id: "a4", title: "Legacy spec.pdf", phase: "00_onboarding", type: "source_document",
         work_item: null, work_item_key: "", work_item_title: "" }),
];

function stub(nodes: unknown[] = NODES) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (body: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(body) }) as Response;
    if (u.includes("/auth/me")) return ok(me);
    if (u.includes("/traceability/")) return ok({ nodes, edges: [] });
    return ok([]);
  }));
}

/** Every drawn node's full <title> — "<name> — <phase> · <status>". Not split on " — ": a
 *  document's own name contains that dash ("PRD — Currency rounding"). */
function drawn(): string[] {
  return [...document.querySelectorAll("svg g[role=button] title")]
    .map((t) => t.textContent ?? "");
}

function nodeFor(title: string): SVGGElement {
  return [...document.querySelectorAll("svg g[role=button]")]
    .find((g) => g.querySelector("title")?.textContent?.startsWith(title)) as SVGGElement;
}

const isDim = (title: string) => Number(nodeFor(title).style.opacity) < 1;

beforeEach(() => localStorage.setItem("selectedProjectId", "p1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("the filters are real controls now", () => {
  it("offers only the phases and types actually on the map", async () => {
    stub();
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(4));
    const phase = screen.getByLabelText("Filter by phase") as HTMLSelectElement;
    const options = [...phase.options].map((o) => o.textContent);
    expect(options).toContain("PRD");
    expect(options).toContain("Architecture");
    expect(options).not.toContain("Deployment");     // nothing on this map is a deployment
  });

  it("narrows the map by phase, and says how much is showing", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(4));
    await user.selectOptions(screen.getByLabelText("Filter by phase"), "prd");

    expect(drawn().length).toBe(1);
    expect(drawn()[0]).toContain("PRD — Currency rounding");
    expect(screen.getByText("1 of 4 shown")).toBeDefined();
  });

  it("says so plainly when a filter matches nothing, instead of 'no lineage yet'", async () => {
    stub([NODES[0]]);
    const user = userEvent.setup();
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(1));
    await user.selectOptions(screen.getByLabelText("Filter by type"), "prd");
    expect(drawn().length).toBe(1);

    // Now filter to a phase this single node does not have: the map has lineage, this view has
    // none of it.
    await user.selectOptions(screen.getByLabelText("Filter by phase"), "prd");
    expect(screen.queryByText("No lineage yet")).toBeNull();
  });
});

describe("highlighting one work item", () => {
  it("lists the project's real work items — never an invented sample", async () => {
    stub();
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(4));
    const highlight = screen.getByLabelText("Highlight work item") as HTMLSelectElement;
    const options = [...highlight.options].map((o) => o.textContent);
    expect(options[0]).toBe("Highlight: All work items");
    expect(options).toContain("Highlight: WI-152 Currency rounding rule");
    expect(options).toContain("Highlight: WI-158 Saved cards");
    expect(document.body.textContent).not.toContain("WI-492");
  });

  it("dims what is outside the chain instead of hiding it", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(4));
    await user.selectOptions(screen.getByLabelText("Highlight work item"), "w1");

    // Everything is still drawn — that is the point of dimming.
    expect(drawn().length).toBe(4);
    expect(isDim("PRD — Currency rounding")).toBe(false);
    expect(isDim("Requirements — Rounding rule")).toBe(false);
    expect(isDim("Architecture — Payments")).toBe(true);
    expect(isDim("Legacy spec.pdf")).toBe(true);
  });

  it("offers the adopted documents as a group of their own", async () => {
    stub();
    const user = userEvent.setup();
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(4));
    await user.selectOptions(screen.getByLabelText("Highlight work item"),
                             screen.getByRole("option", { name: "Highlight: Not tied to a work item" }));

    expect(isDim("Legacy spec.pdf")).toBe(false);
    expect(isDim("PRD — Currency rounding")).toBe(true);
  });

  it("does not offer that group when every document has a work item", async () => {
    stub(NODES.slice(0, 3));
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(3));
    expect(screen.queryByRole("option", { name: "Highlight: Not tied to a work item" })).toBeNull();
  });
});

describe("the map's boxes and legend (2026-10-08)", () => {
  it("puts the whole name in the box for the browser to wrap, never a letter-count cut", async () => {
    const long = "PeopleDesk — Market Sizing & Organizational Value";
    stub([{ ...NODES[0], title: long }]);
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(1));
    const title = document.querySelector(".gnode__title") as HTMLElement;
    expect(title.textContent).toBe(long);
    expect(document.body.textContent).not.toContain("PeopleDesk — Market Si…");
  });

  it("explains only the statuses that are on the map", async () => {
    stub(NODES.map((n) => ({ ...n, status: "published" })));
    renderWithProviders(<TraceabilityView />);

    await waitFor(() => expect(drawn().length).toBe(4));
    const legend = document.querySelector(".graph-legend") as HTMLElement;
    expect(legend.textContent).toBe("Published");
  });
});

describe("the gallery states", () => {
  it("no longer show three controls that do nothing", () => {
    renderWithProviders(<TraceabilityView forceView="small" />);

    expect(screen.queryByLabelText("Filter by phase")).toBeNull();
    expect(screen.queryByLabelText("Highlight work item")).toBeNull();
    expect(document.body.textContent).not.toContain("WI-492");
  });
});
