// @vitest-environment jsdom
//
// S-37 — the conformance statement (QA-24).
//
// These assert the sentences a signed compliance document lives or dies by. A screen that
// rendered "successfully" while quietly folding "nobody looked" into "supports", or promising an
// export it will refuse, or leaking our model versions onto a client's page, would be worse than
// no screen at all — it would be a document someone puts their name to.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen, waitFor } from "@testing-library/react";
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
    audit_in_progress: false,
    has_evidence: true,
    // Which pass the numbers were compiled from. The default is a project that has had one
    // audit, because that is the ordinary case and the one the section is written for.
    basis: {
      latest: {
        id: "48506881-0000-0000-0000-000000000000",
        label: "the audit of 21 Aug 2026",
        started_at: "2026-08-21T11:40:00Z",
        finished_at: "2026-08-21T12:01:00Z",
        asked: 12,
        opened: 12,
      },
      audits: 1,
      runs: 0,
    },
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
    // The tile's label reads "Not settled yet" (mockup M6) and its figure carries "of 55" beside it, so the
    // reader can see this is 54 OUT OF the whole standard. What is being guarded is unchanged:
    // the count is on the headline as itself, never folded into a supporting result.
    const tile = screen
      .getAllByText("Not settled yet")
      .map((el) => el.closest(".tile"))
      .find(Boolean);
    expect(tile).toBeDefined();
    expect(tile?.querySelector(".tile__num")?.textContent).toContain("54");
    expect(tile?.querySelector(".tile__of")?.textContent).toBe("of 55");
    // The row agrees with the headline. A reviewer may change it — that is the whole design —
    // but nothing has softened it into "supports" on their behalf.
    const level = screen.getByLabelText("Conformance level for 3.3.7 Redundant Entry");
    expect((level as HTMLSelectElement).value).toBe("not_evaluated");
  });

  it("marks the criteria waiting on a person, so the tile's count can be found", async () => {
    // The tile says N criteria are waiting on a person. Before this, nothing in the list of 55
    // said WHICH ones, so the number could be read but not acted on.
    const waiting = row({
      criterion: "1.2.2",
      handle: "Captions (Prerecorded)",
      evidence: "94 pages had nothing for this rule to apply to.",
      suggested: null,
      verdict: null,
      effective: "not_evaluated",
      needs_a_person: true,
    });
    vi.stubGlobal(
      "fetch",
      stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance({ rows: [row(), waiting] })]]),
    );
    renderWithProviders(<A11yConformanceScreen />);

    const cell = await screen.findByText("1.2.2 Captions (Prerecorded)");
    const tr = cell.closest("tr");
    expect(tr?.className).toContain("conf-row--needs-you");
    // Colour is never the only cue: the row says so in words as well.
    expect(screen.getByText("needs your decision")).toBeDefined();

    // ...and a row that has a suggestion is NOT marked, or the marking would mean nothing.
    const plain = screen.getByText("1.1.1 Non-text Content").closest("tr");
    expect(plain?.className ?? "").not.toContain("conf-row--needs-you");
  });

  it("gives the conformance control the dropdown class, not the text-field one", async () => {
    // With `.input` it never got `appearance: none` or the padding the chevron needs, so the
    // browser drew its own arrow over the words and "Partially supports" rendered as "Partial".
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);

    const level = await screen.findByLabelText("Conformance level for 1.1.1 Non-text Content");
    expect(level.className).toContain("select");
    expect(level.className).not.toContain("input");
    // Stacked above its chip rather than beside it, so the chip can never squeeze it.
    expect(level.closest(".conf-level")).toBeDefined();
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

  it("names the role that signs in words, not as the stored key (Screen Words group 8)", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("Sign this statement");
    expect(screen.getByText(/required role: QA Lead/)).toBeDefined();
    expect(screen.queryByText(/qa_lead/)).toBeNull();
  });

  it("will not let anyone sign until they say what they are signing for", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);

    const signButton = await screen.findByRole("button", { name: "Sign" });
    expect((signButton as HTMLButtonElement).disabled).toBe(true);

    // Both counts are stated on the checkbox rather than implied — the second is the one a
    // reviewer is least likely to have noticed, and it is what they are taking on.
    expect(screen.getByText(/criteria were not/)).toBeDefined();
    expect(screen.getByText(/results\s+were suggested/)).toBeDefined();

    const boxes = screen.getAllByRole("checkbox");
    await userEvent.click(boxes[0]);
    expect((screen.getByRole("button", { name: "Sign" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(boxes[1]);
    expect((screen.getByRole("button", { name: "Sign" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("signed · offers the export and a link to the statement, without engine talk", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({
        signed: true, signed_name: "Aisha Khan", signed_role: "qa_lead",
        signed_at: "2026-08-18T16:20:00Z", can_export: true, export_refused_because: "",
        artifact_id: "a-1",
      })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("Signed by Aisha Khan · QA Lead");
    expect(screen.getByRole("button", { name: "Export" })).toBeDefined();
    // Recon 2026-10-10: "View statement" opens the statement itself — no "publish gate" link,
    // and no sentence about engine or prompt versions on a client's screen.
    expect(screen.getByRole("link", { name: "View statement" }).getAttribute("href")).toBe("/artifacts/a-1");
    expect(screen.queryByText(/publish gate/)).toBeNull();
    expect(screen.queryByText(/prompt version/)).toBeNull();
    expect(screen.getByText("Export downloads the signed statement and marks it Published.")).toBeDefined();
  });

  it("exported · says when, and offers to export again", async () => {
    vi.stubGlobal("fetch", stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/$/, conformance({
        signed: true, signed_name: "Aisha Khan", signed_role: "qa_lead",
        signed_at: "2026-08-18T16:20:00Z", can_export: true, export_refused_because: "",
        artifact_id: "a-1", exported_at: "2026-08-18T16:30:00Z",
      })],
    ]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText(/^Exported 18 Aug 2026, /);
    expect(screen.getByRole("button", { name: "Export again" })).toBeDefined();
  });

  it("export publishes, then downloads the signed wording", async () => {
    const routes = stubRoutes([
      ...AUTHED,
      [/a11y-conformance\/export\/$/, { artifact_id: "a-1", exported_at: "2026-08-18T16:30:00Z" }],
      [/a11y-conformance\/$/, conformance({
        signed: true, signed_name: "Aisha Khan", signed_role: "qa_lead",
        signed_at: "2026-08-18T16:20:00Z", can_export: true, export_refused_because: "",
        artifact_id: "a-1",
      })],
    ]);
    vi.stubGlobal("fetch", routes);
    const calls = () => routes.mock.calls.map(([u]) => String(u));
    renderWithProviders(<A11yConformanceScreen />);

    await userEvent.click(await screen.findByRole("button", { name: "Export" }));
    await waitFor(() => expect(calls().some((u) => /artifacts\/a-1\/download\/$/.test(u))).toBe(true));
    expect(calls().some((u) => /a11y-conformance\/export\/$/.test(u))).toBe(true);
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

describe("S-37 · which run this statement was compiled from", () => {
  it("names the audit and when it finished", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);

    // Mockup M4: named by when it ran, in the reader's clock — never by its id.
    await screen.findByText(/^the audit of /);
    expect(screen.queryByText(/48506881/)).toBeNull();
    expect(screen.getByText("12 of 12")).toBeDefined();
  });

  it("counts the earlier audits rather than claiming this one is all of it", async () => {
    // The findings ledger is cumulative, so "this is what was checked" would be untrue the
    // moment a project has had two.
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance({
      basis: {
        latest: {
          id: "48506881-0000-0000-0000-000000000000",
          label: "the audit of 21 Aug 2026",
          started_at: "2026-08-21T11:40:00Z",
          finished_at: "2026-08-21T12:01:00Z",
          asked: 12,
          opened: 12,
        },
        audits: 3,
        runs: 0,
      },
    })]]));
    renderWithProviders(<A11yConformanceScreen />);

    // Mockup M4: named by when it ran, in the reader's clock — never by its id.
    await screen.findByText(/^the audit of /);
    expect(screen.queryByText(/48506881/)).toBeNull();
    expect(screen.getByText("2 earlier audit(s)")).toBeDefined();
  });

  it("says plainly when nothing has ever been audited", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance({
      basis: { latest: null, audits: 0, runs: 0 },
    })]]));
    renderWithProviders(<A11yConformanceScreen />);

    await screen.findByText("No completed audit is recorded for this project");
  });
});

// ── A SAVE that fails says it in the product's words (Section 4, part B) ─────────────────────
//
// The accessibility screens were the only ones left rendering `(error as Error).message` straight
// into a banner. Every other screen sends a failure through `writeErrorSentence`, which keeps a
// 4xx verbatim — the server refused this particular thing and said why — and replaces the other
// two kinds. A dropped connection arrives as an ApiError whose own message is the BROWSER's
// "Failed to fetch", so rendering `.message` printed exactly that. Bugs S.No 248 fixed this
// everywhere else; these screens were missed.
describe("A save that fails speaks the product's language, not the browser's", () => {
  it("a dropped connection says the app could not be reached, never “Failed to fetch”", async () => {
    const healthy = stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      // Only the signature POST drops; everything the screen reads still answers, so the failure
      // under test is the SAVE and not the load.
      if (String(input).includes("/sign/")) throw new TypeError("Failed to fetch");
      return healthy(input);
    }));
    renderWithProviders(<A11yConformanceScreen />);

    const boxes = await screen.findAllByRole("checkbox");
    await userEvent.click(boxes[0]);
    await userEvent.click(boxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "Sign" }));

    await screen.findByText("Your browser couldn't connect, so nothing was saved. Try again.");
    expect(screen.queryByText(/Failed to fetch/)).toBeNull();
    // The banner's own title still frames it, which is the half that was already right.
    expect(screen.getByText("This was not signed")).toBeDefined();
  });

  it("a refusal in words is kept exactly as the server wrote it", async () => {
    // The case that must NOT be replaced: a 4xx is the server explaining this particular refusal,
    // and that sentence is the whole value of the banner.
    const said = "The evidence has changed since this statement was compiled.";
    const healthy = stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]);
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/sign/")) {
        return {
          ok: false, status: 409, statusText: "stub",
          text: async () => JSON.stringify({ detail: said }),
        } as Response;
      }
      return healthy(input);
    }));
    renderWithProviders(<A11yConformanceScreen />);

    const boxes = await screen.findAllByRole("checkbox");
    await userEvent.click(boxes[0]);
    await userEvent.click(boxes[1]);
    await userEvent.click(screen.getByRole("button", { name: "Sign" }));

    await screen.findByText(said);
  });
});


// ── Recon 2026-10-10: mockups M1, M2, M6, M7 ─────────────────────────────────────────────

describe("S-37 after the recon fixes", () => {
  it("names the criteria tile for what it counts (M1)", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("Criteria to decide");
    expect(screen.queryByText("Waiting on you")).toBeNull();
  });

  it("says an audit is running and holds the signature until it ends (M2)", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance({
      audit_in_progress: true,
    })]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("An audit is running — these numbers are still coming in");
    expect(screen.getByText("Checked so far")).toBeDefined();
    expect(screen.getByText("Sign opens when the audit finishes.")).toBeDefined();
    expect((screen.getByRole("button", { name: "Sign" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("asks for an audit first when nothing has been checked (M7)", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance({
      has_evidence: false,
    })]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("Run an audit first");
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign" })).toBeNull();
  });

  it("says why a row needs a decision (M6)", async () => {
    const base = conformance() as { rows: Record<string, unknown>[] };
    const rows = base.rows.map((r, i) => (i === 0
      ? { ...r, needs_a_person: true, suggested: null, verdict: null,
          why: "The automatic rule looked, but can't settle this criterion on its own. Pick its result in the Conformance column." }
      : r));
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, { ...base, rows }]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText(/can't settle this criterion on its own/);
  });
});


// ── Live retest 2026-10-12: mockups A1 and B ─────────────────────────────────────────────

describe("S-37 wording after the 12 Oct retest", () => {
  it("says the first audit is still running instead of 'no completed audit' (A1)", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance({
      audit_in_progress: true, basis: { latest: null },
    })]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("The first audit is still running");
    expect(screen.queryByText("No completed audit is recorded for this project")).toBeNull();
  });

  it("names the pick a conformance result, never a level (B)", async () => {
    vi.stubGlobal("fetch", stubRoutes([...AUTHED, [/a11y-conformance\/$/, conformance()]]));
    renderWithProviders(<A11yConformanceScreen />);
    await screen.findByText("Criteria to decide");
    expect(screen.queryByText(/choose a level/i)).toBeNull();
  });
});
