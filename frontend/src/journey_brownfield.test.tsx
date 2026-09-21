// @vitest-environment jsdom
/**
 * Brownfield journey — frontend screen tests.
 * Maps to docs/USER_JOURNEY_BROWNFIELD.md.
 *
 * Uses correct forceView literal values from each component's exported type.
 * All assertions use body.textContent (never-throws) or getAllByText (multi-safe).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, screen } from "@testing-library/react";
import { renderWithProviders, stubFetchJson } from "./test/utils";

import { OnboardingHub } from "./features/observability/OnboardingHub";
import { SourceDocuments } from "./features/observability/SourceDocuments";
import { GapReportScreen } from "./features/observability/GapReportScreen";
import { ContractsDrift } from "./features/observability/ContractsDrift";
import { ArtifactsRegistry } from "./features/observability/ArtifactsRegistry";
import { ArtifactPreviewScreen } from "./features/observability/ArtifactPreviewScreen";
import { ExportPublish } from "./features/observability/ExportPublish";
import { TraceabilityView } from "./features/observability/TraceabilityView";
import { Dashboard } from "./features/observability/Dashboard";
import { CreateProject } from "./features/setup/CreateProject";
import { Repositories } from "./features/setup/Repositories";
import { PhasesAndRuns } from "./features/lifecycle/PhasesAndRuns";
import { WorkItemEpic } from "./features/lifecycle/WorkItemEpic";

const bodyHas = (pattern: RegExp | string) => {
  const text = document.body.textContent ?? "";
  return typeof pattern === "string"
    ? text.toLowerCase().includes(pattern.toLowerCase())
    : pattern.test(text);
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(stubFetchJson(401, { detail: "no session" })));
});
afterEach(() => vi.unstubAllGlobals());


// ── BF-A-0: Brownfield project creation ──────────────────────────────────────

describe("BF-A-0 Brownfield project creation", () => {
  it("brownfield CreateProject shows brownfield track option", () => {
    renderWithProviders(<CreateProject forceView="brownfield" />);
    expect(bodyHas(/brownfield/i)).toBe(true);
  });

  it("multi Repositories shows multiple repos topology", () => {
    renderWithProviders(<Repositories forceView="multi" />);
    expect(bodyHas(/topology|repo/i)).toBe(true);
  });

  it("add-form Repositories shows add repo form", () => {
    renderWithProviders(<Repositories forceView="add-form" />);
    expect(bodyHas(/add|name|branch/i)).toBe(true);
  });

  it("duplicate Repositories shows conflict error", () => {
    renderWithProviders(<Repositories forceView="duplicate" />);
    expect(bodyHas(/duplicate|already|conflict/i)).toBe(true);
  });
});


// ── BF-A-1: Onboarding Hub (OnboardingView: "nothing-done"|"in-progress"|"gap-ready") ──

describe("BF-A-1 OnboardingHub — three view states", () => {
  it("nothing-done shows Upload resources and Drag & drop", () => {
    renderWithProviders(<OnboardingHub forceView="nothing-done" />);
    expect(screen.getAllByText(/Upload resources/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Drag & drop documents/i).length).toBeGreaterThan(0);
  });

  it("in-progress shows indexing file count", () => {
    renderWithProviders(<OnboardingHub forceView="in-progress" />);
    expect(screen.getAllByText(/Indexing 1,284 files/i).length).toBeGreaterThan(0);
  });

  it("gap-ready shows Resume at Architecture", () => {
    renderWithProviders(<OnboardingHub forceView="gap-ready" />);
    expect(screen.getAllByText(/Resume at: Architecture/i).length).toBeGreaterThan(0);
  });

  it("gap-ready shows link to view gap report", () => {
    renderWithProviders(<OnboardingHub forceView="gap-ready" />);
    expect(bodyHas(/gap|resume/i)).toBe(true);
  });
});


// ── BF-A-1/A-2: Source Documents (SourceDocsView: "empty"|"uploading"|"extracted"|"adopt-gate"|"adopted") ──

describe("BF-A-1/A-2 SourceDocuments — full upload lifecycle", () => {
  it("empty state shows upload zone", () => {
    renderWithProviders(<SourceDocuments forceView="empty" />);
    expect(screen.getAllByText(/Drag & drop documents/i).length).toBeGreaterThan(0);
  });

  it("uploading state shows Extracting progress", () => {
    renderWithProviders(<SourceDocuments forceView="uploading" />);
    expect(screen.getAllByText(/Extracting…/i).length).toBeGreaterThan(0);
  });

  it("extracted state shows Adopt button", () => {
    renderWithProviders(<SourceDocuments forceView="extracted" />);
    expect(screen.getAllByText(/Adopt as Requirements artifact/i).length).toBeGreaterThan(0);
  });

  it("adopt-gate state shows awaiting gate message", () => {
    renderWithProviders(<SourceDocuments forceView="adopt-gate" />);
    expect(screen.getAllByText(/Adoption awaiting gate/i).length).toBeGreaterThan(0);
  });

  it("adopted state shows Legacy Billing Requirements", () => {
    renderWithProviders(<SourceDocuments forceView="adopted" />);
    expect(screen.getAllByText(/Legacy Billing Requirements/i).length).toBeGreaterThan(0);
  });

  it("state progression empty→uploading→extracted→adopt-gate→adopted all render", () => {
    const states = ["empty", "uploading", "extracted", "adopt-gate", "adopted"] as const;
    states.forEach((v) => {
      const { unmount } = renderWithProviders(<SourceDocuments forceView={v} />);
      expect(document.body.textContent).toBeTruthy();
      unmount();
    });
  });
});


// ── BF-A-5: Gap Report (GapReportView: "partial" | "empty" | "mature") ───────

describe("BF-A-5 GapReportScreen — resume phase detection", () => {
  it("partial state shows Resume at: Architecture", () => {
    renderWithProviders(<GapReportScreen forceView="partial" />);
    expect(screen.getAllByText(/Resume at: Architecture/i).length).toBeGreaterThan(0);
  });

  it("empty state shows Resume at: Ideation (nothing done yet)", () => {
    renderWithProviders(<GapReportScreen forceView="empty" />);
    expect(screen.getAllByText(/Resume at: Ideation/i).length).toBeGreaterThan(0);
  });

  it("mature state shows Resume at: Task Breakdown (most phases done)", () => {
    renderWithProviders(<GapReportScreen forceView="mature" />);
    expect(screen.getAllByText(/Resume at: Task Breakdown/i).length).toBeGreaterThan(0);
  });

  it("all three gap states render without crashing", () => {
    (["partial", "empty", "mature"] as const).forEach((v) => {
      const { unmount } = renderWithProviders(<GapReportScreen forceView={v} />);
      expect(document.body.textContent).toBeTruthy();
      unmount();
    });
  });
});


// ── BF-A-7: Contracts & Drift (ContractsDriftView: "healthy"|"drift-pending"|"wrong-role"|"decided") ──

describe("BF-A-7 ContractsDrift — full drift decision lifecycle", () => {
  it("healthy state shows Payments API contract as healthy", () => {
    renderWithProviders(<ContractsDrift forceView="healthy" />);
    expect(screen.getAllByText(/Payments API/i).length).toBeGreaterThan(0);
  });

  it("drift-pending state shows breaking change alert", () => {
    renderWithProviders(<ContractsDrift forceView="drift-pending" />);
    expect(screen.getAllByText(/Payments API v2.0.0 — breaking change/i).length).toBeGreaterThan(0);
  });

  it("wrong-role state shows Awaiting architect message", () => {
    renderWithProviders(<ContractsDrift forceView="wrong-role" />);
    expect(screen.getAllByText(/Awaiting architect/i).length).toBeGreaterThan(0);
  });

  it("decided state shows Accepted by Marcus Lee", () => {
    renderWithProviders(<ContractsDrift forceView="decided" />);
    expect(screen.getAllByText(/Accepted by Marcus Lee/i).length).toBeGreaterThan(0);
  });

  it("wrong-role: approve/reject buttons are absent or disabled (role enforcement visible)", () => {
    renderWithProviders(<ContractsDrift forceView="wrong-role" />);
    // When wrong role, the screen shows "Awaiting architect" not approve/reject actions
    // Product owner sees the gate is blocked for them
    expect(bodyHas(/awaiting architect/i)).toBe(true);
    // Approve button either absent or disabled
    const approveBtn = screen.queryByRole("button", { name: /approve/i });
    if (approveBtn) {
      expect(
        (approveBtn as HTMLButtonElement).disabled ||
        approveBtn.getAttribute("aria-disabled") === "true"
      ).toBe(true);
    }
  });

  it("decided state is final — shows accept/reject decision text", () => {
    renderWithProviders(<ContractsDrift forceView="decided" />);
    const text = document.body.textContent ?? "";
    expect(text.includes("Accepted") || text.includes("Rejected")).toBe(true);
  });
});


// ── BF-A-8: Artifact Registry (ArtifactsView: "populated"|"internal-only"|"empty") ──

describe("BF-A-8 ArtifactsRegistry", () => {
  it("populated state shows Artifacts heading", () => {
    renderWithProviders(<ArtifactsRegistry forceView="populated" />);
    expect(bodyHas(/artifacts/i)).toBe(true);
  });

  it("internal-only state shows Ideation Brief artifact", () => {
    renderWithProviders(<ArtifactsRegistry forceView="internal-only" />);
    expect(screen.getAllByText(/Ideation Brief — Loyalty Program/i).length).toBeGreaterThan(0);
  });

  it("empty state shows No artifacts yet", () => {
    renderWithProviders(<ArtifactsRegistry forceView="empty" />);
    expect(screen.getAllByText(/No artifacts yet/i).length).toBeGreaterThan(0);
  });
});

describe("BF-A-8 ArtifactPreview (ArtifactPreviewView: 'markdown'|'diagram'|'external'|'unavailable')", () => {
  it("markdown state shows PRD content and Version history", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="markdown" />);
    expect(screen.getAllByText(/PRD: Stripe Webhook Integration/i).length).toBeGreaterThan(0);
    expect(bodyHas(/version history/i)).toBe(true);
  });

  it("diagram state shows System Sequence Diagram", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="diagram" />);
    expect(screen.getAllByText(/System Sequence Diagram/i).length).toBeGreaterThan(0);
  });

  it("external state shows SoR artifact title", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="external" />);
    expect(screen.getAllByText(/Multi-Currency Requirements/i).length).toBeGreaterThan(0);
  });

  it("unavailable state shows Preview unavailable (not a crash)", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="unavailable" />);
    expect(screen.getAllByText(/Preview unavailable/i).length).toBeGreaterThan(0);
  });
});


// ── BF-A-9: Export/Publish (PublishView: "choose-target"|"publishing"|"success"|"blocked") ──

describe("BF-A-9 ExportPublish — gate-respecting publish", () => {
  it("choose-target shows Publish artifact and Gate approved precondition", () => {
    renderWithProviders(<ExportPublish forceView="choose-target" />);
    expect(screen.getAllByText(/Publish artifact/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Gate approved/i).length).toBeGreaterThan(0);
  });

  it("publishing state shows Publishing to Confluence progress", () => {
    renderWithProviders(<ExportPublish forceView="publishing" />);
    expect(screen.getAllByText(/Publishing to Confluence/i).length).toBeGreaterThan(0);
  });

  it("success state shows Published to Confluence with link", () => {
    renderWithProviders(<ExportPublish forceView="success" />);
    expect(screen.getAllByText(/Published to Confluence/i).length).toBeGreaterThan(0);
  });

  it("blocked state says publishing can't happen yet, and why", () => {
    renderWithProviders(<ExportPublish forceView="blocked" />);
    // Screen Words group 2 reworded this banner and made the status a label ("Waiting for
    // approval") rather than the stored token. The test below still checks it names the gate.
    expect(screen.getAllByText(/Can't publish yet/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Waiting for approval/i).length).toBeGreaterThan(0);
  });

  it("blocked state clearly explains why publishing is blocked", () => {
    renderWithProviders(<ExportPublish forceView="blocked" />);
    // The error message must make the gate requirement clear
    expect(bodyHas(/gate/i)).toBe(true);
  });
});


// ── BF-C: Partial lifecycle — all 16 phases visible in trigger picker ─────────

describe("BF-C Partial lifecycle — all 16 phases in picker", () => {
  it("PhasesAndRuns gallery shows more than 4 phases (all tiers present)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    const btns = screen.getAllByText(/▶/);
    expect(btns.length).toBeGreaterThan(4);
  });

  it("gallery includes Deployment (was incorrectly in remediation)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(bodyHas(/deployment/i)).toBe(true);
  });

  it("gallery includes Implementation (build tier)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(bodyHas(/implementation/i)).toBe(true);
  });

  it("brownfield epic lifecycle shows gate-pending tier (plan phases)", () => {
    renderWithProviders(<WorkItemEpic forceView="gate-pending" />);
    expect(bodyHas(/gate|approval|awaiting/i)).toBe(true);
  });
});


// ── BF Traceability (TraceabilityViewState: "small"|"highlighted"|"large-cluster"|"empty") ──

describe("BF Traceability — source doc chain", () => {
  it("small state shows Traceability heading", () => {
    renderWithProviders(<TraceabilityView forceView="small" />);
    expect(bodyHas(/traceability/i)).toBe(true);
  });

  it("highlighted state shows Requirements node highlighted", () => {
    renderWithProviders(<TraceabilityView forceView="highlighted" />);
    expect(screen.getAllByText(/Requirements/i).length).toBeGreaterThan(0);
  });

  it("large-cluster state shows accessible cluster aria-label", () => {
    renderWithProviders(<TraceabilityView forceView="large-cluster" />);
    expect(screen.getByLabelText(/Large lineage cluster/i)).toBeDefined();
  });

  it("empty state shows No lineage yet", () => {
    renderWithProviders(<TraceabilityView forceView="empty" />);
    expect(screen.getAllByText(/No lineage yet/i).length).toBeGreaterThan(0);
  });
});


// ── BF Dashboard (DashboardView: "busy"|"calm"|"new-project") ─────────────────

describe("BF Dashboard", () => {
  it("busy state shows pending gates and Needs me section", () => {
    renderWithProviders(<Dashboard forceView="busy" />);
    expect(screen.getAllByText(/Gates need your approval/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Needs me/i).length).toBeGreaterThan(0);
  });

  it("calm state shows all caught up (no pending items)", () => {
    renderWithProviders(<Dashboard forceView="calm" />);
    expect(screen.getAllByText(/You're all caught up/i).length).toBeGreaterThan(0);
  });

  it("new-project shows Get started and Not connected yet", () => {
    renderWithProviders(<Dashboard forceView="new-project" />);
    expect(screen.getAllByText(/Get started/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Not connected yet/i).length).toBeGreaterThan(0);
  });
});


// ── Integration failure resilience ───────────────────────────────────────────

describe("Integration failure — screen resilience (INTEGRATION_FAILURE scenarios)", () => {
  it("OnboardingHub renders with 503 (Confluence unavailable)", () => {
    vi.stubGlobal("fetch", vi.fn(stubFetchJson(503, { detail: "service unavailable" })));
    const { container } = renderWithProviders(<OnboardingHub />);
    expect(container).toBeDefined();
  });

  it("ContractsDrift renders with empty API response (no contracts yet)", () => {
    vi.stubGlobal("fetch", vi.fn(stubFetchJson(200, [])));
    const { container } = renderWithProviders(<ContractsDrift />);
    expect(container).toBeDefined();
  });

  it("GapReportScreen renders with 404 (no report built yet)", () => {
    vi.stubGlobal("fetch", vi.fn(stubFetchJson(404, { detail: "not found" })));
    const { container } = renderWithProviders(<GapReportScreen />);
    expect(container).toBeDefined();
  });

  it("GapReportScreen renders a REAL report — labels, evidence counts, not-started phases", async () => {
    // S5-6/S5-7/S5-28 regression. Every other test of this screen used either the hardcoded
    // gallery or a 404 stub, so nothing ever fed it a live payload — and the live payload was the
    // one that crashed. `evidence` is a list of artifact refs; the type said `string` and the
    // cell rendered it raw, so React threw "Objects are not valid as a React child" on every
    // report that had any evidence. Phase labels were looked up against the wrong keyspace and
    // came out as raw slugs. And phases the team simply hasn't reached read as failures.
    const me = {
      user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: false },
      tenant: { id: "t1", name: "Acme" },
      memberships: [{ project_id: "p1", project_name: "Legacy Billing", role: "developer" }],
    };
    const report = {
      gap_report_id: "a1",
      resume_phase: "task_breakdown",
      resume_label: "Task Breakdown",
      intel_present: true,
      blocking: ["task_breakdown"],
      phases: [
        { phase: "ideation", label: "Ideation", assessment: "complete",
          evidence: [{ artifact_id: "x1", type: "ideation", sor: "internal", status: "published" }] },
        { phase: "ux_design", label: "UX Design", assessment: "complete",
          evidence: [
            { artifact_id: "x2", type: "wireframe", sor: "internal", status: "published" },
            { artifact_id: "x3", type: "ux_design", sor: "internal", status: "published" },
          ] },
        { phase: "task_breakdown", label: "Task Breakdown", assessment: "missing", evidence: [] },
        { phase: "implementation", label: "Implementation", assessment: "missing", evidence: [] },
      ],
    };
    const json = (status: number, body: unknown) =>
      Promise.resolve({
        ok: status < 400, status, statusText: "stub",
        text: async () => JSON.stringify(body),
      } as Response);
    vi.stubGlobal("fetch", vi.fn((url: RequestInfo | URL) => {
      const u = String(url);
      if (u.includes("/auth/me/")) return json(200, me);
      if (u.includes("/gap-report/")) return json(200, report);
      return json(200, []);
    }));
    // Tear down every tree this file has left mounted before rendering ours. They are still live
    // (this file never calls cleanup), each with its own AuthProvider, and this is the only test
    // here that stubs a LOGGED-IN /auth/me/ — so they would refetch against a payload shaped for
    // a different screen while our assertions run.
    cleanup();
    const { container, unmount } = renderWithProviders(<GapReportScreen />);
    // Scoped to THIS render, not document.body: this file never calls cleanup(), so the gallery
    // tests above leave their DOM behind — and one of them renders "Resume at: Task Breakdown"
    // too, which would satisfy the wait before this component had fetched anything.
    const has = (re: RegExp) => re.test(container.textContent ?? "");
    await vi.waitFor(() => expect(has(/Lifecycle assessment/)).toBe(true));

    // labels, never slugs
    expect(has(/task_breakdown/)).toBe(false);
    expect(has(/ux_design/)).toBe(false);
    expect(has(/Resume at: Task Breakdown/i)).toBe(true);
    // evidence rendered as a count, not as [object Object]
    expect(has(/2 artifacts/)).toBe(true);
    expect(has(/1 artifact(?!s)/)).toBe(true);   // singular, and adjacent text runs together
    expect(has(/object Object/i)).toBe(false);
    // a phase PAST the resume point is "not started yet", not a failure
    expect(has(/Not started yet/i)).toBe(true);
    // This is the only test here that renders a LOGGED-IN tree, and the screen now polls. Left
    // mounted it keeps refetching into the next test's fetch stub, which answers `[]` for
    // /auth/me/ and blows up AuthContext. Unmount rather than leak into a neighbour.
    unmount();
  });

  it("ArtifactPreviewScreen shows unavailable on missing body", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="unavailable" />);
    expect(bodyHas(/preview unavailable/i)).toBe(true);
  });

  it("ExportPublish blocked state is shown instead of crashing when gate not approved", () => {
    renderWithProviders(<ExportPublish forceView="blocked" />);
    expect(bodyHas(/can't publish/i)).toBe(true);
  });
});
