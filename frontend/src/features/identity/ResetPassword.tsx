import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api";
import { AuthSplit, Button, Field, Input, Spinner, Strength } from "../../components/ui";
import { passwordStrength, useRequestReset, useResetPassword } from "./hooks";

const TAGLINE = "Reset your password.";

// S-04 view states: request · sent · set-new · invalid-token · success.
export type ResetView = "request" | "sent" | "set-new" | "invalid-token" | "success";

export function ResetPassword({ forceView }: { forceView?: ResetView }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const requestReset = useRequestReset();
  const reset = useResetPassword();

  const [email, setEmail] = useState("sarah@acme.com");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [sent, setSent] = useState(false);
  const [done, setDone] = useState(false);

  const invalidToken =
    forceView === "invalid-token" ||
    (reset.error instanceof ApiError && reset.error.status === 410);

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

  const onReset = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await reset.mutateAsync({ token, password });
      setDone(true);
    } catch {
      /* invalid-token surfaced via reset.error */
    }
  };

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
          <Button variant="secondary" block>
            Request a new link
          </Button>
        </div>
      </AuthSplit>
    );
  }

  if (view === "set-new") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <form className="auth-card" onSubmit={onReset}>
          <h1 className="auth-card__title">Set a new password</h1>
          <p className="auth-card__sub">Choose a strong password for {email}.</p>
          <Field label="New password">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <Strength value={passwordStrength(password)} />
          </Field>
          <Field label="Confirm password">
            <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
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
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
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
