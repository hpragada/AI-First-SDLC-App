import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, fieldError, formError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { AuthSplit, Banner, Button, Field, Input, Spinner, Strength } from "../../components/ui";
import { passwordHelp, passwordStrength, useRequestReset, useResetPassword } from "./hooks";

const TAGLINE = "Reset your password.";

// S-04 view states: request · sent · set-new · invalid-token · success.
export type ResetView = "request" | "sent" | "set-new" | "invalid-token" | "success";

export function ResetPassword({ forceView }: { forceView?: ResetView }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const requestReset = useRequestReset();
  const reset = useResetPassword();

  const navigate = useNavigate();
  const { isAuthenticated, currentUser, logout } = useAuth();
  // Mockup 6: was pre-filled with a made-up address, which a hurried person would submit.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [sent, setSent] = useState(false);
  const [done, setDone] = useState(false);

  const invalidToken =
    forceView === "invalid-token" ||
    // Only while a link is in hand: "Request a new link" goes to /reset (no token) on this same
    // screen, and the old refusal must not follow it there.
    (Boolean(token) && reset.error instanceof ApiError && reset.error.status === 410);

  // With a token present the screen is the "set new password" flow; otherwise the request flow.
  const view: ResetView =
    forceView ??
    (done
      ? "success"
      : invalidToken
        ? "invalid-token"
        : token
          ? "set-new"
          : sent
            ? "sent"
            : "request");

  const onRequest = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await requestReset.mutateAsync(email);
      setSent(true);
    } catch {
      setSent(true); // no account enumeration — always confirm
    }
  };

  // Bugs S.No 219: this branched on 410 (the link has expired) and dropped everything else, so
  // a password the server rejected as too short left the form untouched and silent.
  const help = passwordHelp(password);
  const passwordError =
    fieldError(reset.error, "password") ?? (help?.tooShort ? help.text : undefined);
  const bannerError = invalidToken ? undefined : formError(reset.error, ["password"]);

  // Found while fixing the above: the form asks you to confirm the new password and then NEVER
  // compares the two. Mistype the confirmation and your first value is silently accepted — you
  // set a password you do not think you set, and find out at the next login. Checked here, in
  // the browser, because only this screen knows there were two boxes; the server is sent one
  // password and cannot possibly detect it.
  const [confirmTouched, setConfirmTouched] = useState(false);
  const mismatch = confirmTouched && confirm.length > 0 && confirm !== password;

  const onReset = async (event: FormEvent) => {
    event.preventDefault();
    if (confirm !== password) {
      setConfirmTouched(true);
      return;
    }
    try {
      await reset.mutateAsync({ token, password });
      setDone(true);
    } catch {
      /* invalid-token surfaced via reset.error */
    }
  };

  // Mockup 7: /reset now sits outside the signed-in redirect (routes.tsx), so a reset link
  // opened where someone is signed in says so instead of vanishing into their dashboard. With no
  // link in hand, a signed-in person has nothing to do here — back to the dashboard as before.
  if (!forceView && isAuthenticated && view !== "success") {
    if (!token) return <Navigate to="/" replace />;
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card">
          <h1 className="auth-card__title">Set a new password</h1>
          <Banner variant="warning">
            You're signed in as {currentUser?.user.email}. Sign out to set a new password with this
            link.
          </Banner>
          <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
            <Button variant="primary" onClick={() => void logout()}>
              Sign out and continue
            </Button>
            <Button variant="secondary" onClick={() => navigate("/", { replace: true })}>
              Go to my dashboard
            </Button>
          </div>
        </div>
      </AuthSplit>
    );
  }

  if (view === "success") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="vstep__num vstep__num--done" style={{ margin: "0 auto var(--space-3)" }}>
            ✓
          </div>
          <h1 className="auth-card__title">Password updated</h1>
          <p className="auth-card__sub">You can now log in with your new password.</p>
          <Link to="/login" className="btn btn--primary btn--block">
            Log in
          </Link>
        </div>
      </AuthSplit>
    );
  }

  if (view === "sent") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="vstep__num vstep__num--done" style={{ margin: "0 auto var(--space-3)" }}>
            ✓
          </div>
          <h1 className="auth-card__title">Check your email</h1>
          <p className="auth-card__sub">
            If an account exists for <strong>{email}</strong>, a reset link is on its way. The link
            expires in 1 hour.
          </p>
          <Link to="/login" className="btn btn--secondary btn--block">
            Back to log in
          </Link>
        </div>
      </AuthSplit>
    );
  }

  if (view === "invalid-token") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="empty__icon" style={{ margin: "0 auto var(--space-3)" }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5M12 16h.01" />
            </svg>
          </div>
          <h1 className="auth-card__title">This reset link is invalid</h1>
          <p className="auth-card__sub">
            It may have expired or already been used. Request a fresh link to continue.
          </p>
          <Link to="/reset" className="btn btn--secondary btn--block">
            Request a new link
          </Link>
        </div>
      </AuthSplit>
    );
  }

  if (view === "set-new") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <form className="auth-card" onSubmit={onReset}>
          <h1 className="auth-card__title">Set a new password</h1>
          {bannerError ? (
            <Banner variant="danger">{bannerError}</Banner>
          ) : (
            <p className="auth-card__sub">Choose a strong password for your account.</p>
          )}
          <Field label="New password" error={passwordError}
                 help={help && !passwordError ? help.text : undefined}>
            <Input type="password" value={password} aria-invalid={Boolean(passwordError)}
                   onChange={(e) => {
                     if (reset.error && !invalidToken) reset.reset();
                     setPassword(e.target.value);
                   }} />
            <Strength value={passwordStrength(password)} />
          </Field>
          <Field
            label="Confirm password"
            error={mismatch ? "The two passwords don't match." : undefined}
          >
            <Input
              type="password"
              value={confirm}
              aria-invalid={mismatch}
              onChange={(e) => {
                setConfirmTouched(true);
                setConfirm(e.target.value);
              }}
            />
          </Field>
          <Button variant="primary" block type="submit" disabled={reset.isPending}>
            {reset.isPending ? (
              <>
                <Spinner /> Updating…
              </>
            ) : (
              "Update password"
            )}
          </Button>
        </form>
      </AuthSplit>
    );
  }

  // request (default)
  return (
    <AuthSplit tagline={TAGLINE}>
      <form className="auth-card" onSubmit={onRequest}>
        <h1 className="auth-card__title">Forgot your password?</h1>
        <p className="auth-card__sub">Enter your work email and we'll send a reset link.</p>
        <Field label="Work email">
          <Input type="email" placeholder="you@company.com" value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Button variant="primary" block type="submit" disabled={requestReset.isPending}>
          Send reset link
        </Button>
        <div className="auth-card__foot">
          <Link to="/login">Back to log in</Link>
        </div>
      </form>
    </AuthSplit>
  );
}
