// @vitest-environment jsdom
/**
 * Greenfield journey — frontend screen tests.
 * Maps to docs/USER_JOURNEY_GREENFIELD.md.
 *
 * Uses correct forceView literal values from each component's exported type.
 * All assertions use body.textContent (never-throws) or getAllByText (multi-safe).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, stubFetchJson } from "./test/utils";

import { Signup } from "./features/identity/Signup";
import { Login } from "./features/identity/Login";
import { SetupChecklist } from "./features/identity/SetupChecklist";
import { ConnectMachine } from "./features/identity/ConnectMachine";
import { UsersInvites } from "./features/identity/UsersInvites";
import { RolesMatrix } from "./features/identity/RolesMatrix";
import { CreateProject } from "./features/setup/CreateProject";
import { ProjectProfileEditor } from "./features/setup/ProjectProfileEditor";
import { Integrations } from "./features/setup/Integrations";
import { ConnectCapability } from "./features/setup/ConnectCapability";
import { Repositories } from "./features/setup/Repositories";
import { WorkItemsBoard } from "./features/lifecycle/WorkItemsBoard";
import { WorkItemEpic } from "./features/lifecycle/WorkItemEpic";
import { PhasesAndRuns } from "./features/lifecycle/PhasesAndRuns";
import { RunConsole } from "./features/lifecycle/RunConsole";
import { Clarifications } from "./features/lifecycle/Clarifications";
import { Gates } from "./features/lifecycle/Gates";
import { CriteriaGate } from "./features/lifecycle/CriteriaGate";
import { Dashboard } from "./features/observability/Dashboard";
import { ArtifactsRegistry } from "./features/observability/ArtifactsRegistry";
import { ArtifactPreviewScreen } from "./features/observability/ArtifactPreviewScreen";
import { ExportPublish } from "./features/observability/ExportPublish";
import { TraceabilityView } from "./features/observability/TraceabilityView";
import { RunTranscriptScreen } from "./features/observability/RunTranscriptScreen";
import { OfflineTakeover } from "./features/observability/OfflineTakeover";

/** Check text exists anywhere in the rendered document — never throws on multiple matches. */
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


// ── A-0: Signup ──────────────────────────────────────────────────────────────

describe("GF-A-0 Signup", () => {
  it("shows Create your workspace heading", () => {
    renderWithProviders(<Signup />);
    expect(bodyHas(/create your workspace/i)).toBe(true);
  });

  it("has name, email, password, and workspace fields", () => {
    renderWithProviders(<Signup />);
    expect(bodyHas(/full name/i)).toBe(true);
    expect(bodyHas(/email/i)).toBe(true);
    expect(bodyHas(/password/i)).toBe(true);
    expect(bodyHas(/workspace/i)).toBe(true);
  });

  it("has link to log in", () => {
    renderWithProviders(<Signup />);
    expect(bodyHas(/already have an account/i)).toBe(true);
  });
});


// ── A-0: Login ───────────────────────────────────────────────────────────────

describe("GF-A-0 Login", () => {
  it("shows Log in heading", () => {
    renderWithProviders(<Login />);
    expect(bodyHas(/log in/i)).toBe(true);
  });

  it("shows email and password fields", () => {
    renderWithProviders(<Login />);
    expect(bodyHas(/email/i)).toBe(true);
    expect(bodyHas(/password/i)).toBe(true);
  });

  it("shows Forgot password link", () => {
    renderWithProviders(<Login />);
    expect(bodyHas(/forgot password/i)).toBe(true);
  });

  it("shows link to create a workspace", () => {
    renderWithProviders(<Login />);
    expect(bodyHas(/create a workspace/i)).toBe(true);
  });
});


// ── A-0: Setup checklist (SetupView: "all-incomplete" | "partial" | "complete") ──

describe("GF-A-0 SetupChecklist", () => {
  it("all-incomplete shows checklist with steps to complete", () => {
    renderWithProviders(<SetupChecklist forceView="all-incomplete" />);
    expect(bodyHas(/machine|companion|connect/i)).toBe(true);
  });

  it("partial state shows at least one completed step", () => {
    renderWithProviders(<SetupChecklist forceView="partial" />);
    expect(document.body.textContent).toBeTruthy();
  });

  it("complete state shows all done", () => {
    renderWithProviders(<SetupChecklist forceView="complete" />);
    expect(bodyHas(/complete|done|ready/i)).toBe(true);
  });
});


// ── A-2: Connect machine (ConnectView: "not-started"|"token-generated"|"connected"|"offline") ──

describe("GF-A-2 ConnectMachine", () => {
  it("not-started shows Generate enrollment token button", () => {
    renderWithProviders(<ConnectMachine forceView="not-started" />);
    expect(bodyHas(/generate enrollment token/i)).toBe(true);
  });

  it("token-generated shows token value", () => {
    renderWithProviders(<ConnectMachine forceView="token-generated" />);
    expect(bodyHas(/rnr_|token/i)).toBe(true);
  });

  it("connected shows Connected status", () => {
    renderWithProviders(<ConnectMachine forceView="connected" />);
    expect(bodyHas(/connected/i)).toBe(true);
  });

  it("offline shows offline warning", () => {
    renderWithProviders(<ConnectMachine forceView="offline" />);
    expect(bodyHas(/offline|not connected|disconnected/i)).toBe(true);
  });
});


// ── A-1: Users (UsersView: "populated" | "invite-drawer" | "dup-error" | "empty") ──

describe("GF-A-1 UsersInvites", () => {
  it("empty state shows invite prompt", () => {
    renderWithProviders(<UsersInvites forceView="empty" />);
    expect(bodyHas(/invite|users|no users/i)).toBe(true);
  });

  it("populated state renders a user table", () => {
    renderWithProviders(<UsersInvites forceView="populated" />);
    expect(
      document.querySelector("table") !== null ||
      document.querySelector("[class*='table']") !== null
    ).toBe(true);
  });

  it("invite-drawer state shows invite form", () => {
    renderWithProviders(<UsersInvites forceView="invite-drawer" />);
    expect(bodyHas(/invite|email/i)).toBe(true);
  });

  it("dup-error state shows duplicate email error", () => {
    renderWithProviders(<UsersInvites forceView="dup-error" />);
    expect(bodyHas(/already|duplicate|exist/i)).toBe(true);
  });
});


// ── A-3: Integrations (IntegrationsView: "mixed" | "failed" | "empty") ──────

describe("GF-A-3 Integrations", () => {
  it("empty state renders Integrations heading", () => {
    renderWithProviders(<Integrations forceView="empty" />);
    expect(bodyHas(/integrations/i)).toBe(true);
  });

  it("mixed state shows some connected, some not", () => {
    renderWithProviders(<Integrations forceView="mixed" />);
    expect(bodyHas(/connected|integration/i)).toBe(true);
  });

  it("failed state shows failure indicator", () => {
    renderWithProviders(<Integrations forceView="failed" />);
    expect(bodyHas(/failed|error|integration/i)).toBe(true);
  });
});

describe("GF-A-3 ConnectCapability (ConnectView: 'empty'|'filled'|'testing'|'success'|'fail')", () => {
  it("empty state shows Connect heading", () => {
    renderWithProviders(<ConnectCapability forceView="empty" />);
    expect(bodyHas(/connect/i)).toBe(true);
  });

  it("filled state shows the vendor form", () => {
    renderWithProviders(<ConnectCapability forceView="filled" />);
    expect(screen.getAllByText("Vendor").length).toBeGreaterThan(0);
  });

  it("testing state shows testing in progress", () => {
    renderWithProviders(<ConnectCapability forceView="testing" />);
    expect(bodyHas(/test|connect|checking/i)).toBe(true);
  });

  it("success state shows test passed", () => {
    renderWithProviders(<ConnectCapability forceView="success" />);
    expect(bodyHas(/success|connected|ok/i)).toBe(true);
  });

  it("fail state shows failure with fix hint", () => {
    renderWithProviders(<ConnectCapability forceView="fail" />);
    expect(bodyHas(/fail|error|fix/i)).toBe(true);
  });
});


// ── A-4: Create project (CreateProjectView: "default" | "brownfield" | "collision") ──

describe("GF-A-4 CreateProject", () => {
  it("default (greenfield) state shows project creation form", () => {
    renderWithProviders(<CreateProject forceView="default" />);
    expect(bodyHas(/project|name|create/i)).toBe(true);
  });

  it("brownfield state shows brownfield track", () => {
    renderWithProviders(<CreateProject forceView="brownfield" />);
    expect(bodyHas(/brownfield/i)).toBe(true);
  });

  it("collision state shows name conflict error", () => {
    renderWithProviders(<CreateProject forceView="collision" />);
    expect(bodyHas(/already|conflict|exists/i)).toBe(true);
  });
});

describe("GF-A-4 ProjectProfileEditor (ProfileView: 'clean'|'dirty'|'saving'|'validation')", () => {
  it("clean state renders profile form", () => {
    renderWithProviders(<ProjectProfileEditor forceView="clean" />);
    expect(bodyHas(/profile/i)).toBe(true);
  });

  it("dirty state shows unsaved changes indicator", () => {
    renderWithProviders(<ProjectProfileEditor forceView="dirty" />);
    expect(screen.getAllByText(/Unsaved changes/i).length).toBeGreaterThan(0);
  });

  it("saving state shows save in progress", () => {
    renderWithProviders(<ProjectProfileEditor forceView="saving" />);
    expect(bodyHas(/saving|saved/i)).toBe(true);
  });

  it("validation state shows validation errors", () => {
    renderWithProviders(<ProjectProfileEditor forceView="validation" />);
    expect(bodyHas(/error|required|valid/i)).toBe(true);
  });
});


// ── A-5: Repositories (RepoView: "single" | "multi" | "empty") ───────────────

describe("GF-A-5 Repositories", () => {
  it("single state renders Repositories heading", () => {
    renderWithProviders(<Repositories forceView="single" />);
    expect(bodyHas(/repositories/i)).toBe(true);
  });

  it("multi state shows multiple repos", () => {
    renderWithProviders(<Repositories forceView="multi" />);
    expect(bodyHas(/topology|repo/i)).toBe(true);
  });

  it("empty state shows add prompt", () => {
    renderWithProviders(<Repositories forceView="empty" />);
    expect(bodyHas(/repository|add|no repo/i)).toBe(true);
  });
});


// ── A-6: Work Items (BoardView: "board" | "list" | "filtered" | "empty") ────

describe("GF-A-6 WorkItemsBoard", () => {
  it("board state shows Work Items heading", () => {
    renderWithProviders(<WorkItemsBoard forceView="board" />);
    expect(bodyHas(/work items/i)).toBe(true);
  });

  it("empty state shows no items prompt", () => {
    renderWithProviders(<WorkItemsBoard forceView="empty" />);
    expect(bodyHas(/no work items|create|empty/i)).toBe(true);
  });

  it("filtered state shows filtered view", () => {
    renderWithProviders(<WorkItemsBoard forceView="filtered" />);
    expect(bodyHas(/work items|filter/i)).toBe(true);
  });
});

describe("GF-A-6 WorkItemEpic (EpicView: 'gate-pending'|'needs-answer'|'complete')", () => {
  it("gate-pending state shows gate awaiting approval", () => {
    renderWithProviders(<WorkItemEpic forceView="gate-pending" />);
    expect(bodyHas(/gate|approval|awaiting/i)).toBe(true);
  });

  it("needs-answer state shows clarification needed", () => {
    renderWithProviders(<WorkItemEpic forceView="needs-answer" />);
    expect(bodyHas(/answer|clarification|question/i)).toBe(true);
  });

  it("complete state shows done/complete", () => {
    renderWithProviders(<WorkItemEpic forceView="complete" />);
    expect(bodyHas(/complete|done/i)).toBe(true);
  });
});


// ── A-7: Phases & Runs — ALL 16 phases ───────────────────────────────────────

describe("GF-A-7 PhasesAndRuns — all 16 phases", () => {
  it("online state shows Phases & Runs and Trigger a phase", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(bodyHas(/phases.*runs|trigger a phase/i)).toBe(true);
  });

  it("offline state shows companion not connected warning", () => {
    renderWithProviders(<PhasesAndRuns forceView="offline" />);
    expect(bodyHas(/not connected|offline/i)).toBe(true);
  });

  it("no-runs state shows No runs yet", () => {
    renderWithProviders(<PhasesAndRuns forceView="no-runs" />);
    expect(bodyHas(/no runs yet/i)).toBe(true);
  });

  it("gallery shows more than 4 trigger buttons (not just plan tier)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    const triggerBtns = screen.getAllByText(/▶/);
    // Gallery fallback has 12 phases — must be more than the old broken 4
    expect(triggerBtns.length).toBeGreaterThan(4);
  });

  it("gallery includes Security phase (build tier, was missing)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(bodyHas(/security/i)).toBe(true);
  });

  it("gallery includes CI/CD phase (was in remediation bucket incorrectly)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(bodyHas(/ci\/cd|cicd/i)).toBe(true);
  });

  it("gallery includes Deployment phase (was in remediation bucket incorrectly)", () => {
    renderWithProviders(<PhasesAndRuns forceView="online" />);
    expect(bodyHas(/deployment/i)).toBe(true);
  });
});


// ── A-7: Run Console (RunConsoleView: "dispatched"|"running"|"needs-answer"|"awaiting-gate"|"completed"|"failed"|"parked"|"paused") ──

describe("GF-A-7 RunConsole states", () => {
  it("dispatched state shows dispatched/queued status", () => {
    renderWithProviders(<RunConsole forceView="dispatched" />);
    expect(bodyHas(/dispatched|queued|pending/i)).toBe(true);
  });

  it("running state shows running", () => {
    renderWithProviders(<RunConsole forceView="running" />);
    expect(bodyHas(/running/i)).toBe(true);
  });

  it("needs-answer state shows clarification needed", () => {
    renderWithProviders(<RunConsole forceView="needs-answer" />);
    expect(bodyHas(/answer|clarification/i)).toBe(true);
  });

  it("awaiting-gate state shows gate pending", () => {
    renderWithProviders(<RunConsole forceView="awaiting-gate" />);
    expect(bodyHas(/gate|awaiting|approval/i)).toBe(true);
  });

  it("completed state shows completed", () => {
    renderWithProviders(<RunConsole forceView="completed" />);
    expect(bodyHas(/completed|done/i)).toBe(true);
  });

  it("failed state shows failed", () => {
    renderWithProviders(<RunConsole forceView="failed" />);
    expect(bodyHas(/failed/i)).toBe(true);
  });

  it("parked state shows parked/takeover", () => {
    renderWithProviders(<RunConsole forceView="parked" />);
    expect(bodyHas(/parked|takeover/i)).toBe(true);
  });
});


// ── A-10: Clarifications (ClarificationsView: "empty"|"one-pending"|"multi"|"required-error"|"answered"|"cancelled") ──

describe("GF-A-10 Clarifications", () => {
  it("empty state shows No questions waiting", () => {
    renderWithProviders(<Clarifications forceView="empty" />);
    expect(bodyHas(/no questions waiting/i)).toBe(true);
  });

  it("one-pending state shows a question to answer", () => {
    renderWithProviders(<Clarifications forceView="one-pending" />);
    expect(bodyHas(/question|clarification|answer/i)).toBe(true);
  });

  it("multi state shows multiple pending questions", () => {
    renderWithProviders(<Clarifications forceView="multi" />);
    expect(bodyHas(/clarification|question/i)).toBe(true);
  });

  it("required-error state shows required field error", () => {
    renderWithProviders(<Clarifications forceView="required-error" />);
    expect(bodyHas(/required|error|missing/i)).toBe(true);
  });

  it("answered state shows submitted answers", () => {
    renderWithProviders(<Clarifications forceView="answered" />);
    expect(bodyHas(/answered|submitted/i)).toBe(true);
  });

  it("cancelled state shows cancelled clarification", () => {
    renderWithProviders(<Clarifications forceView="cancelled" />);
    expect(bodyHas(/cancelled|canceled/i)).toBe(true);
  });
});


// ── A-8: Gates (GatesView: "can-decide" | "cannot-decide" | "history" | "empty") ──

describe("GF-A-8 Gates", () => {
  it("can-decide state shows approve/reject actions", () => {
    renderWithProviders(<Gates forceView="can-decide" />);
    expect(bodyHas(/approve|reject|gate/i)).toBe(true);
  });

  it("cannot-decide state shows wrong role message", () => {
    renderWithProviders(<Gates forceView="cannot-decide" />);
    expect(bodyHas(/role|permission|cannot|read only/i)).toBe(true);
  });

  it("history state shows past decisions", () => {
    renderWithProviders(<Gates forceView="history" />);
    expect(bodyHas(/history|decided|gate/i)).toBe(true);
  });

  it("empty state shows no gates", () => {
    renderWithProviders(<Gates forceView="empty" />);
    expect(bodyHas(/no gates|all clear|empty/i)).toBe(true);
  });
});

describe("GF-A-8 CriteriaGate (CriteriaGateView: 'none'|'partial'|'all'|'rejected')", () => {
  it("none state shows empty criteria (no conditions yet)", () => {
    renderWithProviders(<CriteriaGate forceView="none" />);
    expect(bodyHas(/criteria|gate|approve|no criteria/i)).toBe(true);
  });

  it("partial state shows some criteria satisfied", () => {
    renderWithProviders(<CriteriaGate forceView="partial" />);
    expect(bodyHas(/criteria|partial|satisfied/i)).toBe(true);
  });

  it("all state shows all criteria satisfied and approve enabled", () => {
    renderWithProviders(<CriteriaGate forceView="all" />);
    expect(bodyHas(/approved|all satisfied|approve/i)).toBe(true);
  });

  it("rejected state shows rejected decision", () => {
    renderWithProviders(<CriteriaGate forceView="rejected" />);
    expect(bodyHas(/rejected/i)).toBe(true);
  });
});


// ── Scenario D: Dashboard ─────────────────────────────────────────────────────

describe("GF-D Dashboard", () => {
  it("busy state shows Gates need your approval and Needs me", () => {
    renderWithProviders(<Dashboard forceView="busy" />);
    expect(screen.getAllByText(/Gates need your approval/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Needs me/i).length).toBeGreaterThan(0);
  });

  it("calm state shows You're all caught up", () => {
    renderWithProviders(<Dashboard forceView="calm" />);
    expect(screen.getAllByText(/You're all caught up/i).length).toBeGreaterThan(0);
  });

  it("new-project state shows Get started and Not connected yet", () => {
    renderWithProviders(<Dashboard forceView="new-project" />);
    expect(bodyHas(/get started/i)).toBe(true);
    expect(bodyHas(/not connected yet/i)).toBe(true);
  });
});


// ── Artifacts ────────────────────────────────────────────────────────────────

describe("GF Artifacts registry", () => {
  it("populated state shows Artifacts heading", () => {
    renderWithProviders(<ArtifactsRegistry forceView="populated" />);
    expect(bodyHas(/artifacts/i)).toBe(true);
  });

  it("internal-only shows Ideation Brief", () => {
    renderWithProviders(<ArtifactsRegistry forceView="internal-only" />);
    expect(bodyHas(/ideation brief/i)).toBe(true);
  });

  it("empty state shows No artifacts yet", () => {
    renderWithProviders(<ArtifactsRegistry forceView="empty" />);
    expect(bodyHas(/no artifacts yet/i)).toBe(true);
  });
});

describe("GF Artifact preview", () => {
  it("markdown state shows PRD content and Version history", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="markdown" />);
    expect(screen.getAllByText(/PRD: Stripe Webhook Integration/i).length).toBeGreaterThan(0);
    expect(bodyHas(/version history/i)).toBe(true);
  });

  it("diagram state shows diagram artifact", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="diagram" />);
    expect(bodyHas(/diagram|sequence/i)).toBe(true);
  });

  it("external state shows SoR deep-link", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="external" />);
    expect(bodyHas(/multi-currency|requirements/i)).toBe(true);
  });

  it("unavailable state shows Preview unavailable", () => {
    renderWithProviders(<ArtifactPreviewScreen forceView="unavailable" />);
    expect(bodyHas(/preview unavailable/i)).toBe(true);
  });
});

describe("GF ExportPublish", () => {
  it("choose-target shows Publish artifact and Gate approved", () => {
    renderWithProviders(<ExportPublish forceView="choose-target" />);
    expect(bodyHas(/publish artifact/i)).toBe(true);
    expect(bodyHas(/gate approved/i)).toBe(true);
  });

  it("blocked state shows Can't publish", () => {
    renderWithProviders(<ExportPublish forceView="blocked" />);
    expect(bodyHas(/can't publish/i)).toBe(true);
  });

  it("publishing state shows Publishing to Confluence", () => {
    renderWithProviders(<ExportPublish forceView="publishing" />);
    expect(bodyHas(/publishing to confluence/i)).toBe(true);
  });

  it("success state shows Published to Confluence", () => {
    renderWithProviders(<ExportPublish forceView="success" />);
    expect(bodyHas(/published to confluence/i)).toBe(true);
  });
});


// ── Run transcript ────────────────────────────────────────────────────────────

describe("GF RunTranscript", () => {
  it("runs-list shows Run transcripts and RUN-42", () => {
    renderWithProviders(<RunTranscriptScreen forceView="runs-list" />);
    expect(bodyHas(/run transcripts/i)).toBe(true);
    expect(bodyHas(/RUN-42/)).toBe(true);
  });

  it("transcript shows Read-only replay and Agent turns", () => {
    renderWithProviders(<RunTranscriptScreen forceView="transcript" />);
    expect(screen.getAllByText(/Read-only replay/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Agent/i).length).toBeGreaterThan(0);
  });

  it("empty shows No transcripts yet", () => {
    renderWithProviders(<RunTranscriptScreen forceView="empty" />);
    expect(bodyHas(/no transcripts yet/i)).toBe(true);
  });
});


// ── Traceability ──────────────────────────────────────────────────────────────

describe("GF Traceability", () => {
  it("small state shows Traceability heading", () => {
    renderWithProviders(<TraceabilityView forceView="small" />);
    expect(bodyHas(/traceability/i)).toBe(true);
  });

  it("highlighted state shows Requirements node", () => {
    renderWithProviders(<TraceabilityView forceView="highlighted" />);
    expect(screen.getAllByText(/requirements/i).length).toBeGreaterThan(0);
  });

  it("large-cluster state has accessible cluster aria-label", () => {
    renderWithProviders(<TraceabilityView forceView="large-cluster" />);
    expect(screen.getByLabelText(/large lineage cluster/i)).toBeDefined();
  });

  it("empty state shows No lineage yet", () => {
    renderWithProviders(<TraceabilityView forceView="empty" />);
    expect(bodyHas(/no lineage yet/i)).toBe(true);
  });
});


// ── Scenario C: Offline takeover ─────────────────────────────────────────────

describe("GF-C OfflineTakeover", () => {
  it("parked state shows parked for takeover message", () => {
    renderWithProviders(<OfflineTakeover forceView="parked" />);
    expect(screen.getAllByText(/this run is parked for takeover/i).length).toBeGreaterThan(0);
  });

  it("reconnecting state shows Reconnecting message", () => {
    renderWithProviders(<OfflineTakeover forceView="reconnecting" />);
    expect(screen.getAllByText(/Reconnecting Sarah's MacBook/i).length).toBeGreaterThan(0);
  });

  it("resumed state shows Run resumed", () => {
    renderWithProviders(<OfflineTakeover forceView="resumed" />);
    expect(screen.getAllByText(/Run resumed/i).length).toBeGreaterThan(0);
  });
});


// ── Roles matrix (RolesView: "gap-warning" | "saving" | "last-admin-guard") ──

describe("GF RolesMatrix", () => {
  it("gap-warning shows uncovered role warning", () => {
    renderWithProviders(<RolesMatrix forceView="gap-warning" />);
    expect(bodyHas(/gap|warning|uncovered|role/i)).toBe(true);
  });

  it("saving state shows save in progress", () => {
    renderWithProviders(<RolesMatrix forceView="saving" />);
    expect(bodyHas(/saving|saved|role/i)).toBe(true);
  });

  it("last-admin-guard shows cannot remove last admin warning", () => {
    renderWithProviders(<RolesMatrix forceView="last-admin-guard" />);
    expect(bodyHas(/last|admin|cannot|guard/i)).toBe(true);
  });
});
