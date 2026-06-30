import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

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
} from "./features/setup";

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
          <Route index element={<AppPlaceholder title="Workspace Dashboard" />} />
          <Route path="/work-items" element={<AppPlaceholder title="Work Items" />} />
          <Route path="/work-items/:id" element={<AppPlaceholder title="Work Item Detail" />} />
          <Route path="/runs" element={<AppPlaceholder title="Phases & Runs" />} />
          <Route path="/runs/:id" element={<AppPlaceholder title="Run Console" />} />
          <Route path="/gates" element={<AppPlaceholder title="Gates" />} />
          <Route path="/clarifications" element={<AppPlaceholder title="Clarifications" />} />
          <Route path="/artifacts" element={<AppPlaceholder title="Artifacts" />} />
          <Route path="/artifacts/:id" element={<AppPlaceholder title="Artifact Preview" />} />
          <Route path="/traceability" element={<AppPlaceholder title="Traceability" />} />
          <Route path="/profile" element={<ProjectProfileEditor />} />
          <Route path="/projects/new" element={<CreateProject />} />
          <Route path="/onboarding" element={<AppPlaceholder title="Onboarding" />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/integrations/:capability" element={<ConnectCapability />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
          <Route path="/admin/users" element={<UsersInvites />} />
          <Route path="/admin/roles" element={<RolesMatrix />} />
          <Route path="/admin/*" element={<AppPlaceholder title="Workspace Admin" />} />
          <Route path="/connect" element={<ConnectMachine />} />
          <Route path="/setup" element={<SetupChecklist />} />
          <Route path="/transcripts" element={<AppPlaceholder title="Run Transcripts" />} />
          <Route path="/contracts" element={<AppPlaceholder title="Contracts & Drift" />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
