import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { AuthSplit, Banner, Button, Field, Input, Spinner } from "../../components/ui";

const TAGLINE = "Welcome back.";
const SUB = "Pick up your lifecycle where you left off.";

// S-02 view states: default · invalid · locked · submitting.
export type LoginView = "default" | "invalid" | "locked" | "submitting";

export function Login({ forceView }: { forceView?: LoginView }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";
  const [email, setEmail] = useState("sarah@acme.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const locked = forceView === "locked" || error?.status === 429;
  const invalid = forceView === "invalid" || (Boolean(error) && !locked);
  const view: LoginView =
    forceView ?? (submitting ? "submitting" : locked ? "locked" : invalid ? "invalid" : "default");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, "Login failed"));
    } finally {
      setSubmitting(false);
    }
  };

  if (view === "submitting") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card">
          <h1 className="auth-card__title">Log in</h1>
          <p className="auth-card__sub">Signing you in…</p>
          <Button variant="primary" block disabled aria-disabled="true">
            <Spinner /> Logging in…
          </Button>
        </div>
      </AuthSplit>
    );
  }

  if (view === "locked") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card">
          <h1 className="auth-card__title">Log in</h1>
          <Banner variant="warning" title="Too many attempts">
            Your account is locked for 15 minutes. Reset your password to regain access sooner.
          </Banner>
          <Button variant="secondary" block onClick={() => navigate("/reset")}>
            Reset password
          </Button>
        </div>
      </AuthSplit>
    );
  }

  return (
    <AuthSplit tagline={TAGLINE} sub={SUB}>
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-card__title">Log in</h1>
        {view === "invalid" ? (
          <Banner variant="danger">Email or password is incorrect.</Banner>
        ) : (
          <p className="auth-card__sub">Welcome back.</p>
        )}
        <Field label="Work email">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field
          label="Password"
          style={{ marginBottom: "var(--space-2)" }}
          error={view === "invalid" ? "Incorrect password." : undefined}
        >
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={view === "invalid"}
          />
        </Field>
        <div style={{ textAlign: "right", marginBottom: "var(--space-4)" }}>
          <Link to="/reset" className="t-sm">
            Forgot password?
          </Link>
        </div>
        <Button variant="primary" block type="submit">
          Log in
        </Button>
        <div className="auth-card__foot">
          New to Edvensoft? <Link to="/signup">Create a workspace</Link>
        </div>
      </form>
    </AuthSplit>
  );
}
