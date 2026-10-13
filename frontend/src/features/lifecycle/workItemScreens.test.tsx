// @vitest-environment jsdom
//
// The work-item screens, after the 2026-10-06 live pass.
//
// The team opened a task and a defect for the first time on a clean tenant and found one action
// wearing two names, no way to cancel an epic at all, an open defect drawn in the failure
// colour, a raw id on screen, and a greenfield project being offered four phases that read an
// existing codebase it does not have.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, within } from "@testing-library/react";

import { renderWithProviders } from "../../test/utils";
import { PhasesAndRuns } from "./PhasesAndRuns";

const PROJECT = "22222222-2222-2222-2222-222222222222";

function me(track?: "greenfield" | "brownfield") {
  return {
    user: { id: "u1", email: "a@b.test", name: "Aisha Khan", is_tenant_admin: false },
    tenant: { id: "t1", name: "Acme" },
    memberships: [
      { project_id: PROJECT, project_name: "PeopleDesk", role: "product_owner", track },
    ],
  };
}

const CATALOG = {
  plan: [
    { key: "00_onboarding", label: "onboarding", agent_key: "00_onboarding", gate_role: "tech_lead" },
    { key: "00b_context_bridge", label: "context_bridge", agent_key: "00b_context_bridge", gate_role: "tech_lead" },
    { key: "00c_intelligent_context_extractor", label: "context_extraction", agent_key: "00c_intelligent_context_extractor", gate_role: "tech_lead" },
    { key: "00e_document_vision", label: "document_vision", agent_key: "00e_document_vision", gate_role: "product_owner" },
    { key: "01_ideation", label: "ideation", agent_key: "01_ideation", gate_role: "product_owner" },
  ],
  build: [
    { key: "09c_a11y_judge", label: "a11y_judge", agent_key: "09c_a11y_judge", gate_role: "qa_lead" },
  ],
  remediation: [],
};

function stub(track?: "greenfield" | "brownfield") {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = /\/auth\/me\//.test(url)
      ? me(track)
      : /\/phases\//.test(url)
        ? CATALOG
        : /\/work-items\//.test(url)
          // The phase buttons only render once a work item is selected, and the screen selects
          // the first one it is given. Without this the screen renders no buttons at all and
          // every "does not contain" assertion below passes for the wrong reason.
          ? [{ id: "wi-1", key: "WI-1", title: "People Desk - Ideation", type: "epic",
               state: "proposed", project: PROJECT }]
          : [];
    return {
      ok: true, status: 200, statusText: "stub",
      text: async () => JSON.stringify(body),
    } as Response;
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function renderPhases(track?: "greenfield" | "brownfield") {
  localStorage.setItem("selectedProjectId", PROJECT);
  vi.stubGlobal("fetch", stub(track));
  const view = renderWithProviders(<PhasesAndRuns />);
  // Anchor on a phase that ONLY the real catalog produces. While it loads, this screen renders
  // a hardcoded gallery list that happens to contain Ideation — so waiting on that returned
  // before the catalog landed and every assertion below ran against the fallback.
  await screen.findByText(/Accessibility Judge/);
  return view;
}

describe("phases offered on a project that was started from scratch", () => {
  it("does not offer the four phases that read an existing codebase", async () => {
    const { container } = await renderPhases("greenfield");
    const text = container.textContent ?? "";
    expect(text).toContain("Ideation");
    expect(text).not.toContain("Onboarding");
    expect(text).not.toContain("Context Bridge");
    expect(text).not.toContain("Context Extraction");
    expect(text).not.toContain("Document Vision");
  });

  it("still offers them on a brownfield project", async () => {
    const { container } = await renderPhases("brownfield");
    const text = container.textContent ?? "";
    expect(text).toContain("Onboarding");
    expect(text).toContain("Document Vision");
  });

  it("still offers them when the API is too old to say which track this is", async () => {
    // S.No 221. Hiding on a MISSING track would lock a brownfield team out of their own
    // onboarding during a rolling deploy — the reason every other reader of `track` checks
    // `=== "greenfield"` rather than `!== "brownfield"`.
    const { container } = await renderPhases(undefined);
    expect(container.textContent ?? "").toContain("Onboarding");
  });

  it("names the accessibility phase in words wherever it is offered", async () => {
    const { container } = await renderPhases("greenfield");
    expect(container.textContent ?? "").toContain("Accessibility Judge");
    expect(container.textContent ?? "").not.toContain("A11y Judge");
  });
});

describe("the trigger buttons still work the way they did", () => {
  it("renders the phases that are left, not an empty screen", async () => {
    const { container } = await renderPhases("greenfield");
    const buttons = within(container).getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });
});

// ── "At a glance" asks the same questions on every screen ───────────────────
//
// The three screens were written separately and never compared: an epic answered four
// questions, a task three, a defect one. The team asked whether a task can have clarifications
// and whether a defect can have artifacts or a gate — and the answer to all of them is yes, so
// the differences were accidental rather than meaningful.
import { Route, Routes } from "react-router-dom";
import { waitFor } from "@testing-library/react";

import { WorkItemDefect } from "./WorkItemDefect";
import { boardStatusLabel } from "./WorkItemsBoard";
import { WorkItemEpic } from "./WorkItemEpic";
import { WorkItemTask } from "./WorkItemTask";

const ME_DETAIL = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

const item = (over: Record<string, unknown> = {}) => ({
  id: "wi-1", key: "WI-1", number: 1, project: "p1", feature_stream: "",
  type: "task", state: "proposed", created_at: "2026-09-01T00:00:00Z",
  title: "Export to CSV", current_phase: "07_implementation", artifact_count: 0,
  ...over,
});

function stubDetail(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    const ok = (b: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(b) }) as Response;
    if (u.includes("/auth/me")) return ok(ME_DETAIL);
    for (const [needle, value] of Object.entries(routes)) if (u.includes(needle)) return ok(value);
    return ok([]);
  }));
}

function renderDetail(element: React.ReactElement) {
  return renderWithProviders(
    <Routes><Route path="/work-items/:id" element={element} /></Routes>,
    { route: "/work-items/wi-1" },
  );
}

const EMPTY_LIFECYCLE = { nodes: [], loops: [], children: [] };

describe("every work item screen answers the same questions", () => {
  const rows = ["State", "Artifacts", "Open gates", "Open clarifications"];

  it("on a task", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item({ parent_key: "WI-2" }) });
    const { container } = renderDetail(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    for (const row of [...rows, "Parent"]) expect(container.textContent).toContain(row);
    expect(container.textContent).toContain("WI-2");
  });

  it("on a defect", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE,
                 "/work-items/": item({ type: "defect", parent_key: "WI-2" }) });
    const { container } = renderDetail(<WorkItemDefect />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    for (const row of [...rows, "Parent"]) expect(container.textContent).toContain(row);
    // The id this used to print, cut to eight characters.
    expect(container.textContent).not.toMatch(/\bwi-1\b/);
  });

  it("on an epic, which counts children rather than naming a parent", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item({ type: "epic" }) });
    const { container } = renderDetail(<WorkItemEpic />);
    // Regex, not exact text: the epic screen prefixes its title with a glyph, so the title
    // lives in one text node with it.
    await waitFor(() => expect(screen.getByText(/Export to CSV/)).toBeDefined());
    for (const row of [...rows, "Children"]) expect(container.textContent).toContain(row);
  });
});

describe("a defect states its own condition once", () => {
  it("says nothing in the header while it is simply open", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item({ type: "defect" }) });
    const { container } = renderDetail(<WorkItemDefect />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    // "Open" above and "Proposed" beside it — one defect, two words — was the defect.
    expect(container.textContent).not.toContain("Open defect");
    // Mockup M9: the State row says what the Board and the List say for this same item.
    expect(container.textContent).toContain(`State${boardStatusLabel(item({ type: "defect" }))}`);
  });

  it("reports the run in the header when there is one to report", async () => {
    stubDetail({
      "/lifecycle": EMPTY_LIFECYCLE,
      "/runs": [{ id: "r1", status: "running", phase: "07_implementation",
                  work_item: "wi-1", inputs: { dispatch: { status: "claimed" } } }],
      "/work-items/": item({ type: "defect" }),
    });
    const { container } = renderDetail(<WorkItemDefect />);
    await waitFor(() =>
      expect(container.textContent).toContain("Fix running on your companion"));
  });
});

describe("the rails say what they are for", () => {
  it("in words about this item, not our own labels", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item({ type: "defect" }) });
    const { container } = renderDetail(<WorkItemDefect />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(container.textContent).toContain("The phases that fix this defect");
    expect(container.textContent).not.toContain("minimal rail");
    expect(container.textContent).not.toContain("Remediation");
  });
});

// ── "At a glance" counts: a link only when there is something to open ───────
//
// Found 2026-10-06 by the team: the artifact count was a link even at zero, and clicking it
// landed on "Nothing matched this filter" — a failure message for a work item that had simply
// not produced anything. The clarification count carried the opposite problem: it has always
// counted PENDING questions only, under a label that named the category.
import { clarificationsForWorkItem } from "../../links";

describe("the counts on the summary card", () => {
  it("does not link a zero artifact count", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item({ artifact_count: 0 }) });
    const { container } = renderDetail(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    const links = Array.from(container.querySelectorAll("a"));
    expect(links.some((a) => a.getAttribute("href")?.includes("/artifacts"))).toBe(false);
  });

  it("links an artifact count above zero", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item({ artifact_count: 7 }) });
    const { container } = renderDetail(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("7")).toBeDefined());
    const links = Array.from(container.querySelectorAll("a"));
    expect(links.some((a) => a.getAttribute("href")?.includes("/artifacts"))).toBe(true);
  });

  it("says OPEN clarifications, because that is what the number counts", async () => {
    stubDetail({ "/lifecycle": EMPTY_LIFECYCLE, "/work-items/": item() });
    const { container } = renderDetail(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(container.textContent).toContain("Open clarifications");
  });

  it("points an open clarification at the questions for this work item alone", async () => {
    stubDetail({
      "/lifecycle": EMPTY_LIFECYCLE,
      "/clarifications": [{ id: "c1", run: "r1", work_item: "wi-1", phase: "07_implementation",
                           status: "pending", questions: [], answers: {} }],
      "/work-items/": item(),
    });
    const { container } = renderDetail(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    const href = clarificationsForWorkItem("wi-1");
    await waitFor(() =>
      expect(Array.from(container.querySelectorAll("a"))
        .some((a) => a.getAttribute("href") === href)).toBe(true));
  });
});

describe("the lifecycle rail", () => {
  it("does not promise the future under every phase", async () => {
    stubDetail({
      "/lifecycle": { nodes: [{ phase: "07_implementation", label: "Implementation",
                                state: "not_started" }], loops: [], children: [] },
      "/work-items/": item(),
    });
    const { container } = renderDetail(<WorkItemTask />);
    await waitFor(() => expect(screen.getByText("Export to CSV")).toBeDefined());
    expect(container.textContent).toContain("Not started");
    expect(container.textContent).not.toContain("Upcoming");
  });
});
