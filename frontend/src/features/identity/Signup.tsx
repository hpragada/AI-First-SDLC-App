import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  AuthSplit,
  Button,
  Field,
  Input,
  Spinner,
  Strength,
} from "../../components/ui";
import { passwordStrength, useSignup } from "./hooks";

const TAGLINE = "Run your whole software lifecycle with AI — and human approval gates.";
const SUB = "Create a workspace and you become its first admin. Teammates join by invitation.";

// S-01 view states: default · email-in-use · submitting · success.
export type SignupView = "default" | "email-in-use" | "submitting" | "success";

export function Signup({ forceView }: { forceView?: SignupView }) {
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const signup = useSignup();
  const [name, setName] = useState("Sarah Chen");
  const [email, setEmail] = useState("sarah@acme.com");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("Acme Corp");
  const [done, setDone] = useState(false);

  const emailInUse =
    forceView === "email-in-use" ||
    (signup.error instanceof ApiError && signup.error.status === 409);
  const view: SignupView =
    forceView ??
    (done ? "success" : signup.isPending ? "submitting" : emailInUse ? "email-in-use" : "default");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await signup.mutateAsync({ name, email, password, org_name: orgName });
      await refresh();
      setDone(true);
    } catch {
      /* surfaced via signup.error → email-in-use / banner */
    }
  };

  if (view === "success") {
    return (
      <AuthSplit tagline={TAGLINE} sub={SUB}>
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="vstep__num vstep__num--done" style={{ margin: "0 auto var(--space-3)" }}>
            ✓
          </div>
          <h1 className="auth-card__title">Workspace created</h1>
          <p className="auth-card__sub">Taking you to your setup checklist…</p>
          <Button variant="primary" block onClick={() => navigate("/setup")}>
            Continue
          </Button>
        </div>
      </AuthSplit>
    );
  }

  if (view === "submitting") {
    return (
      <AuthSplit tagline={TAGLINE} sub={SUB}>
        <div className="auth-card">
          <h1 className="auth-card__title">Create your workspace</h1>
          <p className="auth-card__sub">Setting up {orgName}…</p>
          <Button variant="primary" block disabled aria-disabled="true">
            <Spinner /> Creating workspace…
          </Button>
        </div>
      </AuthSplit>
    );
  }

  return (
    <AuthSplit tagline={TAGLINE} sub={SUB}>
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-card__title">Create your workspace</h1>
        <p className="auth-card__sub">Start your free Edvensoft workspace.</p>
        <Field label="Full name">
          <Input type="text" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field
          label="Work email"
          error={
            view === "email-in-use" ? (
              <>
                An account with this email already exists. <Link to="/login">Log in instead</Link>.
              </>
            ) : undefined
          }
        >
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={view === "email-in-use"}
          />
        </Field>
        <Field
          label="Password"
          help={password ? "Strong — add a symbol to max it out." : undefined}
        >
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <Strength value={passwordStrength(password)} />
        </Field>
        <Field label="Workspace / org name">
          <Input type="text" value={orgName} onChange={(e) => setOrgName(e.target.value)} />
        </Field>
        <Button variant="primary" block type="submit">
          Create workspace
        </Button>
        <div className="auth-card__foot">
          Already have an account? <Link to="/login">Log in</Link>
        </div>
      </form>
    </AuthSplit>
  );
}
