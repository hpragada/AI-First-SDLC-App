import { useState, type FormEvent } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { DevComponents } from "./components/dev/DevComponents";
import {
  AuthSplit,
  Banner,
  Button,
  EmptyState,
  Field,
  Input,
  Panel,
  Skeleton,
} from "./components/ui";

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

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("sarah@acme.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to log in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="canvas-pad">
      <AuthSplit>
        <form className="auth-card" onSubmit={onSubmit}>
          <h1 className="auth-card__title">Log in</h1>
          <p className="auth-card__sub">Welcome back to Acme Corp.</p>
          {error && <Banner variant="danger">{error}</Banner>}
          <Field label="Work email">
            <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </Field>
          <Button variant="primary" block disabled={submitting}>
            {submitting ? "Logging in..." : "Log in"}
          </Button>
          <div className="auth-card__foot">
            <a href="/reset">Forgot password?</a>
          </div>
        </form>
      </AuthSplit>
    </main>
  );
}

function AuthPlaceholder({ title }: { title: string }) {
  return (
    <main className="canvas-pad">
      <AuthSplit>
        <div className="auth-card">
          <h1 className="auth-card__title">{title}</h1>
          <p className="auth-card__sub">This shell-less auth screen is reserved for the T2 implementation.</p>
          <EmptyState title="Screen contract ready" text="T2 will render every labelled gallery state here." />
        </div>
      </AuthSplit>
    </main>
  );
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
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<AuthPlaceholder title="Sign up" />} />
        <Route path="/accept-invite" element={<AuthPlaceholder title="Accept invite" />} />
        <Route path="/reset" element={<AuthPlaceholder title="Reset password" />} />
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
          <Route path="/profile" element={<AppPlaceholder title="Project Profile" />} />
          <Route path="/onboarding" element={<AppPlaceholder title="Onboarding" />} />
          <Route path="/integrations" element={<AppPlaceholder title="Integrations" />} />
          <Route path="/repositories" element={<AppPlaceholder title="Repositories" />} />
          <Route path="/admin/*" element={<AppPlaceholder title="Workspace Admin" />} />
          <Route path="/connect" element={<AppPlaceholder title="Connect Machine" />} />
          <Route path="/setup" element={<AppPlaceholder title="Setup Checklist" />} />
          <Route path="/transcripts" element={<AppPlaceholder title="Run Transcripts" />} />
          <Route path="/contracts" element={<AppPlaceholder title="Contracts & Drift" />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
