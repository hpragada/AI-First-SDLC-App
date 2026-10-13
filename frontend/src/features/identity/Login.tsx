import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { AuthSplit, Banner, Button, Field, Input, Spinner } from "../../components/ui";

const TAGLINE = "Welcome back.";
const SUB = "Pick up your lifecycle where you left off.";

// S-02 view states: default · invalid · locked · unreachable · submitting.
//
// Screen Words group 6c. `unreachable` is new. Every failure except "too many attempts" used to
// land on `invalid`, so a server that was down, a dropped connection or a 500 all told the user
// "Incorrect password." — about a password the server never checked. Someone typing the right
// password was told it was wrong, which sends them to reset a password that works.
export type LoginView = "default" | "invalid" | "locked" | "unreachable" | "submitting";

export function Login({ forceView }: { forceView?: LoginView }) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const locked = forceView === "locked" || error?.status === 429;
  // `failure` is `classify(status)` from api.ts: "offline" for a connection that never landed,
  // "server" for a 5xx. Neither one checked the password, so neither may say it was wrong.
  const unreachable =
    forceView === "unreachable" ||
    (!locked && (error?.failure === "offline" || error?.failure === "server"));
  // What is left is a real refusal from the server: 401/403, or a 4xx about the credentials.
  const invalid = forceView === "invalid" || (Boolean(error) && !locked && !unreachable);
  const view: LoginView =
    forceView ??
    (submitting
      ? "submitting"
      : locked
        ? "locked"
        : unreachable
          ? "unreachable"
          : invalid
            ? "invalid"
            : "default");

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
        ) : view === "unreachable" ? (
          // Screen Words group 6c: says whose fault it is and that the password is untouched,
          // so nobody resets a working password over a server that was briefly down.
          <Banner variant="danger" title="Can't reach the SDLC app right now">
            Your password wasn't checked. Try again in a moment.
          </Banner>
        ) : (
          <p className="auth-card__sub">Sign in to your workspace.</p>
        )}
        <Field label="Work email">
          <Input
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
        <Field
          label="Password"
          style={{ marginBottom: "var(--space-2)" }}
          error={view === "invalid" ? "Incorrect password." : undefined}
        >
          <Input
            type="password"
            placeholder="Your password"
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
