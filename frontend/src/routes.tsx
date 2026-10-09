import { Link, Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { DevComponents } from "./components/dev/DevComponents";
import { Panel, Skeleton } from "./components/ui";
import {
  AcceptInvite,
  ConnectMachine,
  Login,
  ResetPassword,
  RolesMatrix,
  Signup,
  SetupChecklist,
  UsersInvites,
} from "./features/identity";
import {
  ConnectCapability,
  CreateProject,
  Integrations,
  ProjectProfileEditor,
  Repositories,
  TestReporting,
} from "./features/setup";
import { A11yAudit, A11yConformanceScreen, A11yFinding, A11yReview } from "./features/a11y";
import {
  Clarifications,
  CriteriaGate,
  Gates,
  PhasesAndRuns,
  RunConsole,
  TaskBreakdown,
  TestCases,
  WorkItemsBoard,
} from "./features/lifecycle";
import { WorkItemDetail } from "./features/lifecycle/WorkItemDetail";
import {
  ArtifactPreviewScreen,
  ArtifactsRegistry,
  ContractsDrift,
  Dashboard,
  ExportPublish,
  GapReportScreen,
  OfflineTakeover,
  OnboardingHub,
  RunTranscriptScreen,
  SourceDocuments,
  TraceabilityView,
} from "./features/observability";

function RequireAuth() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <main className="canvas-pad">
        <Panel title="Loading workspace">
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </main>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

function RedirectIfAuthed() {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/" replace />;
  return <Outlet />;
}

/** `/gates/:id` → `/gates?gate=:id`. See the routes below for why these are redirects. */
function RedirectToSelection({ list, param }: { list: string; param: string }) {
  const { id } = useParams();
  return <Navigate to={id ? `${list}?${param}=${encodeURIComponent(id)}` : list} replace />;
}

// Admin-only routes (Bugs.xlsx row 51): a signed-in non-admin who deep-links to
// /admin/* must see a clear "admin access needed" screen, not a broken blank render.
function RequireAdmin() {
  const { isAdmin } = useAuth();
  if (!isAdmin) {
    return (
      <main className="canvas-pad">
        <Panel title="Admin access needed">
          <p className="t-body">
            This page manages workspace users and roles, and is available to workspace
            admins only. Ask an admin to grant you the admin role if you need it.
          </p>
          <Link to="/" className="btn btn--secondary" style={{ marginTop: "var(--space-3)" }}>
            ← Back to the dashboard
          </Link>
        </Panel>
      </main>
    );
  }
  return <Outlet />;
}

// Brownfield-only routes (Bugs.xlsx S.No 221). The sidebar hides Onboarding on a greenfield
// project, but `/onboarding` is still a URL anyone can type or have bookmarked from another
// project — and the hub behind it does not check the track, it ASSERTS it ("Brownfield
// project", with a Brownfield badge) over whatever project is open. Guarding here rather than
// inside each of the three screens keeps one answer for all of them, and the assertion the hub
// makes becomes true by construction.
//
// Hides on an explicit "greenfield" only: an API too old to send the track must not lock a
// brownfield team out of its own onboarding mid-deploy.
function RequireBrownfield() {
  const { selectedProject } = useAuth();
  if (selectedProject?.track === "greenfield") {
    return (
      <main className="canvas-pad">
        <Panel title="Nothing to onboard yet">
          <p className="t-body">
            Onboarding reads an existing codebase and reports what is missing from it.{" "}
            <strong>{selectedProject.project_name}</strong> was started from scratch, so there
            is nothing for it to read — the lifecycle begins at Ideation instead.
          </p>
          <p className="t-body">
            If this project does have code already, change its track to Brownfield on the
            project profile and Onboarding will appear in the sidebar.
          </p>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
            <Link to="/" className="btn btn--secondary">← Back to the dashboard</Link>
            <Link to="/profile" className="btn btn--secondary">Project profile</Link>
          </div>
        </Panel>
      </main>
    );
  }
  return <Outlet />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<RedirectIfAuthed />}>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
      </Route>
      {/* 2026-10-09: outside the signed-in redirect for the same reason as /accept-invite —
          a reset link opened where someone is signed in must not vanish into their dashboard. */}
      <Route path="/reset" element={<ResetPassword />} />
      {/* 2026-10-09: outside the signed-in redirect on purpose. A link opened where someone is
          signed in must still say whose invite it is, not drop into their dashboard. */}
      <Route path="/accept-invite" element={<AcceptInvite />} />

      <Route path="/dev/components" element={<DevComponents />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="/work-items" element={<WorkItemsBoard />} />
          <Route path="/work-items/:id" element={<WorkItemDetail />} />
          <Route path="/work-items/:id/breakdown" element={<TaskBreakdown />} />
          <Route path="/work-items/:id/test-cases" element={<TestCases />} />
          <Route path="/runs" element={<PhasesAndRuns />} />
          <Route path="/runs/:id" element={<RunConsole />} />
          <Route path="/gates" element={<Gates />} />
          <Route path="/gates/:id/criteria" element={<CriteriaGate />} />
          {/* N2 — `/gates/:id` and `/clarifications/:id` are REDIRECTS, not screens.
              `OnboardingHub` already linked to `/gates/:id`; there was no such route, so the
              catch-all below silently bounced the user to the Dashboard and the primary action on
              a blocking onboarding step went nowhere. These make every URL of that shape already
              in the wild — a bookmark, a link pasted into chat — resolve to the gate it names.
              New code links straight to `?gate=` via `links.ts`.

              They are redirects rather than detail screens deliberately: the Gates screen holds
              the selection state and every phase-specific panel, and a real detail screen would
              be a THIRD gate-decision UI (`CriteriaGate` is already a second, partial one) —
              exactly the drift this pass exists to remove. It would also throw away the
              master-detail layout, which is not noise: a reviewer with five pending gates wants
              to see the other four. */}
          <Route path="/gates/:id" element={<RedirectToSelection list="/gates" param="gate" />} />
          <Route path="/clarifications" element={<Clarifications />} />
          <Route
            path="/clarifications/:id"
            element={<RedirectToSelection list="/clarifications" param="clarification" />}
          />
          <Route path="/artifacts" element={<ArtifactsRegistry />} />
          <Route path="/artifacts/:id" element={<ArtifactPreviewScreen />} />
          <Route path="/artifacts/:id/publish" element={<ExportPublish />} />
          <Route path="/traceability" element={<TraceabilityView />} />
          {/* Accessibility review console (QA-23, S-36). Always routed, never conditional on a
              run having happened — the empty state is what tells "nothing is waiting" apart
              from "nothing was ever checked". */}
          <Route path="/a11y" element={<A11yReview />} />
          <Route path="/a11y/pages" element={<A11yAudit />} />
          <Route path="/a11y/conformance" element={<A11yConformanceScreen />} />
          {/* Reached from a report, the backlog or the conformance statement — the
              screenshot every finding says it is describing (S-39). Reading it takes
              no review claim. */}
          <Route path="/a11y/finding/:findingId" element={<A11yFinding />} />
          <Route path="/profile" element={<ProjectProfileEditor />} />
          <Route path="/projects/new" element={<CreateProject />} />
          <Route element={<RequireBrownfield />}>
            <Route path="/onboarding" element={<OnboardingHub />} />
            {/* Uploading a specification is arguably useful on a greenfield project too, but
                it is only reachable from the hub, and "let a new project upload a spec" is a
                feature worth designing rather than leaving as a side door. Team decision,
                7 Sep 2026: hide it with the rest for now. */}
            <Route path="/onboarding/documents" element={<SourceDocuments />} />
            <Route path="/onboarding/gap-report" element={<GapReportScreen />} />
          </Route>
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/integrations/:capability" element={<ConnectCapability />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
            <Route path="/admin/users" element={<UsersInvites />} />
            <Route path="/admin/roles" element={<RolesMatrix />} />
            {/* Bugs S.No 225. An admin address the app does not know used to render a developer's
                placeholder — "Foundation route mounted. Feature screens land in T2-T5", "rendered
                inside the Phase 4.8 app shell" — one developer's note to another, shown to the
                client's own administrator with no way back. It now goes to the admin landing
                screen (the team's option A), the way an unknown address anywhere else goes to the
                dashboard; the placeholder screen is deleted, and this was its only use. */}
            <Route path="/admin/*" element={<Navigate to="/admin/users" replace />} />
            {/* Test reporting is a project resource but admin-only (mirrors the backend
                IsTenantAdmin on /ci-tokens/); a non-admin deep-link gets the admin panel. */}
            <Route path="/test-reporting" element={<TestReporting />} />
          </Route>
          <Route path="/connect" element={<ConnectMachine />} />
          <Route path="/recovery" element={<OfflineTakeover />} />
          <Route path="/setup" element={<SetupChecklist />} />
          <Route path="/transcripts" element={<RunTranscriptScreen />} />
          <Route path="/transcripts/:id" element={<RunTranscriptScreen />} />
          <Route path="/contracts" element={<ContractsDrift />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
