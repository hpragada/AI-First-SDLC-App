import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { AuthSplit, Button, Field, Input, Spinner, Strength } from "../../components/ui";
import { passwordStrength, useAcceptInvitation } from "./hooks";

const TAGLINE = "You're invited to Acme Corp.";
const SUB = "Set a password and join your team's workspace.";

// S-03 view states: default · expired (used/expired link) · submitting.
export type AcceptInviteView = "default" | "expired" | "submitting";

export function AcceptInvite({ forceView }: { forceView?: AcceptInviteView }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const accept = useAcceptInvitation();
  const [name, setName] = useState("Raj Patel");
  const [password, setPassword] = useState("");

  const expired =
    forceView === "expired" ||
    (accept.error instanceof ApiError && [409, 410].includes(accept.error.status));
  const view: AcceptInviteView =
    forceView ?? (accept.isPending ? "submitting" : expired ? "expired" : "default");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await accept.mutateAsync({ token, password, name });
      await refresh();
      navigate("/", { replace: true });
    } catch {
      /* surfaced via accept.error → expired card */
    }
  };

  if (view === "expired") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="empty__icon" style={{ margin: "0 auto var(--space-3)" }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5M12 16h.01" />
            </svg>
          </div>
          <h1 className="auth-card__title">This invite link has expired</h1>
          <p className="auth-card__sub">
            Invitation links are valid for 7 days, or expire once used. Ask your admin to resend it.
          </p>
          <Button variant="secondary" block>
            Request a new invite
          </Button>
        </div>
      </AuthSplit>
    );
  }

  if (view === "submitting") {
    return (
      <AuthSplit tagline={TAGLINE}>
        <div className="auth-card">
          <h1 className="auth-card__title">Join Acme Corp</h1>
          <p className="auth-card__sub">Setting up your account…</p>
          <Button variant="primary" block disabled aria-disabled="true">
            <Spinner /> Joining workspace…
          </Button>
        </div>
      </AuthSplit>
    );
  }

  return (
    <AuthSplit tagline={TAGLINE} sub={SUB}>
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-card__title">Join Acme Corp</h1>
        <p className="auth-card__sub">
          You've been invited by <strong>Sarah Chen</strong> as <strong>engineer</strong> on Payment
          Gateway v2.
        </p>
        <Field label="Your name">
          <Input type="text" placeholder="e.g. Jordan Lee" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Email">
          <Input type="email" value="raj@acme.com" disabled />
        </Field>
        <Field label="Set a password" help={password ? "Strong password." : undefined}>
          <Input type="password" placeholder="At least 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Strength value={passwordStrength(password)} />
        </Field>
        <Button variant="primary" block type="submit">
          Join workspace
        </Button>
      </form>
    </AuthSplit>
  );
}
