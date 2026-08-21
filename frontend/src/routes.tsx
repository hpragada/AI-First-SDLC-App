import { Link, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { DevComponents } from "./components/dev/DevComponents";
import { EmptyState, Panel, Skeleton } from "./components/ui";
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

function AppPlaceholder({ title }: { title: string }) {
  return (
    <main className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">{title}</h1>
          <p className="page-head__sub">Foundation route mounted. Feature screens land in T2-T5.</p>
        </div>
      </div>
      <Panel title="Ready for screen implementation">
        <EmptyState title="No screen built yet" text="This route is auth-gated and rendered inside the Phase 4.8 app shell." />
      </Panel>
    </main>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<RedirectIfAuthed />}>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/accept-invite" element={<AcceptInvite />} />
        <Route path="/reset" element={<ResetPassword />} />
      </Route>

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
          <Route path="/clarifications" element={<Clarifications />} />
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
          <Route path="/onboarding" element={<OnboardingHub />} />
          <Route path="/onboarding/documents" element={<SourceDocuments />} />
          <Route path="/onboarding/gap-report" element={<GapReportScreen />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/integrations/:capability" element={<ConnectCapability />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
            <Route path="/admin/users" element={<UsersInvites />} />
            <Route path="/admin/roles" element={<RolesMatrix />} />
            <Route path="/admin/*" element={<AppPlaceholder title="Workspace Admin" />} />
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
