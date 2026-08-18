// @vitest-environment jsdom
//
// S-37 — the conformance statement (QA-24).
//
// These assert the sentences a signed compliance document lives or dies by. A screen that
// rendered "successfully" while quietly folding "nobody looked" into "supports", or promising an
// export it will refuse, or leaking our model versions onto a client's page, would be worse than
// no screen at all — it would be a document someone puts their name to.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import { A11yConformanceScreen } from "./A11yConformance";

const PROJECT = "11111111-1111-1111-1111-111111111111";

const ME = {
  user: { id: "u1", email: "aisha@acme.test", name: "Aisha Khan", is_tenant_admin: false },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: PROJECT, project_name: "Payments", role: "qa_lead" }],
};

function row(over: Record<string, unknown> = {}) {
  return {
    criterion: "1.1.1",
    handle: "Non-text Content",
    level: "A",
    evidence: "Checked on 3 pages with nothing wrong.",
    established_by: ["rule"],
    routes_checked: 3,
    open_failures: 0,
    human_decisions: 0,
    suggested: "supports",
    verdict: null,
    effective: "supports",
    needs_a_person: false,
    ...over,
  };
}

function conformance(over: Record<string, unknown> = {}) {
  return {
    scope: "Payment Gateway v2",
    body: "# Accessibility conformance statement",
    drafted: true,
    rows: [
      row(),
      row({
        criterion: "3.3.7",
        handle: "Redundant Entry",
        evidence: "Nothing checked this.",
        established_by: [],
        routes_checked: 0,
        suggested: "not_evaluated",
        effective: "not_evaluated",
      }),
    ],
    totals: {
      supports: 1,
      partially_supports: 0,
      does_not_support: 0,
      not_applicable: 0,
      not_evaluated: 54,
      total: 55,
      evaluated: 1,
      awaiting_a_person: 2,
      platform_suggested: 55,
    },
    disclaimer:
      "This is risk reduction, not certification. Automated and AI-assisted checks cover part of WCAG 2.2.",
    signed: false,
    signed_name: "",
    signed_role: "",
    signed_at: null,
    stale: false,
    artifact_id: null,
    required_role: "qa_lead",
    can_export: false,
    export_refused_because:
      "This cannot be exported unsigned. A conformance statement carries someone's professional judgement, and the platform has none to give.",
    can_sign: true,
    ...over,
  };
}

function stubRoutes(routes: Array<[RegExp, unknown, number?]>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [pattern, body, statusCode = 200] of routes) {
      if (pattern.test(url)) {
        return {
          ok: statusCode < 400,
          status: statusCode,
          statusText: "stub",
          text: async () => JSON.stringify(body),
        } as Response;
      }
    }
    return { ok: false, status: 404, statusText: "stub", text: async () => "{}" } as Response;
  });
}

const AUTHED: Array<[RegExp, unknown, number?]> = [
  [/\/auth\/me\//, ME],
  [/\/runners\//, []],
  [/\/dashboard\//, { needs_me: { gates: [], clarifications: [] } }],
  [/a11y-review\/$/, { queue: [], can_review: true, lock_minutes: 15 }],
];

beforeEach(() => localStorage.setItem("selectedProjectId", PROJECT));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("S-37 conformance statement", () => {
  it("prints “not evaluated” as itself and never as a pass", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("1.1.1 Non-text Content");
    expect(screen.getByText("3.3.7 Redundant Entry")).toBeDefined();
    // The evidence column says what happened, with no verdict in it.
    expect(screen.getByText("Nothing checked this.")).toBeDefined();
    expect(screen.getByText("— nothing checked this")).toBeDefined();
    // And the count is on the page, not buried — in the headline tile AND on the checkbox the
    // reviewer has to tick, which is why there are two of them.
    expect(screen.getAllByText("54").length).toBe(2);
    const tile = screen
      .getAllByText("Not evaluated")
      .map((el) => el.closest(".tile"))
      .find(Boolean);
    expect(tile?.querySelector(".tile__num")?.textContent).toBe("54");
    // The row agrees with the headline. A reviewer may change it — that is the whole design —
    // but nothing has softened it into "supports" on their behalf.
    const level = screen.getByLabelText("Conformance level for 3.3.7 Redundant Entry");
    expect((level as HTMLSelectElement).value).toBe("not_evaluated");
  });

  it("carries the risk-reduction wording, which is the whole disclaimer", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("This is risk reduction, not certification");
    expect(screen.getByText(/Automated and AI-assisted checks cover part of WCAG/)).toBeDefined();
  });

  it("shows which engine established each result", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({
        rows: [row({ established_by: ["rule", "AI", "human"] })],
      })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("Rule");
    expect(screen.getByText("AI")).toBeDefined();
    expect(screen.getByText("Human")).toBeDefined();
  });

  it("refuses to export unsigned, and says why in the reviewer's language", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("Sign this statement");
    // The export panel only appears once signed; before that the signing panel is the door.
    expect(screen.queryByRole("button", { name: "Export…" })).toBeNull();
  });

  it("will not let anyone sign until they say what they are signing for", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);

    const signButton = await screen.findByRole("button", { name: "Sign" });
    expect((signButton as HTMLButtonElement).disabled).toBe(true);

    // Both counts are stated on the checkbox rather than implied — the second is the one a
    // reviewer is least likely to have noticed, and it is what they are taking on.
    expect(screen.getByText(/criteria were not/)).toBeDefined();
    expect(screen.getByText(/levels/)).toBeDefined();

    const boxes = screen.getAllByRole("checkbox");
    await userEvent.click(boxes[0]);
    expect((screen.getByRole("button", { name: "Sign" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(boxes[1]);
    expect((screen.getByRole("button", { name: "Sign" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("signed · offers the export and says the versions are recorded but not shown", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({
        signed: true, signed_name: "Aisha Khan", signed_role: "qa_lead",
        signed_at: "2026-08-18T16:20:00Z", can_export: true, export_refused_because: "",
        artifact_id: "a-1",
      })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("Signed by Aisha Khan · qa_lead");
    expect(screen.getByRole("button", { name: "Export…" })).toBeDefined();
    // D-A11Y-96: the absence is explained, so nobody later reads it as an omission.
    expect(screen.getByText(/deliberately not shown here/)).toBeDefined();
  });

  it("stale · the signature stands, the export does not", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({
        signed: true, signed_name: "Aisha Khan", signed_role: "qa_lead",
        signed_at: "2026-08-18T16:20:00Z", stale: true, can_export: false,
        export_refused_because:
          "The evidence has changed since this was signed. The wording is still what Aisha Khan signed, but it no longer describes what the platform holds — read it again and re-sign.",
      })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("Signed · evidence has changed");
    expect(screen.getByText(/no longer describes what the platform holds/)).toBeDefined();
    const exportButton = screen.getByRole("button", { name: "Export" });
    expect((exportButton as HTMLButtonElement).disabled).toBe(true);
  });

  it("read-only · someone who is not the reviewer sees everything and edits nothing", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({ can_sign: false })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("You are not the accessibility reviewer");
    expect(screen.getByText("1.1.1 Non-text Content")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Sign" })).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("warns before an edit destroys a signature", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({
        signed: true, signed_name: "Aisha Khan", signed_role: "qa_lead",
        signed_at: "2026-08-18T16:20:00Z", can_export: true, export_refused_because: "",
      })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    const body = await screen.findByDisplayValue("# Accessibility conformance statement");
    await userEvent.type(body, " and more");
    await screen.findByText("Saving this will clear the signature");
  });

  it("marks the levels the platform suggested and the reviewer has not changed", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("1.1.1 Non-text Content");
    // Not hidden — it is exactly what the signature makes someone responsible for.
    expect(screen.getAllByText("suggested").length).toBe(2);
  });
});
