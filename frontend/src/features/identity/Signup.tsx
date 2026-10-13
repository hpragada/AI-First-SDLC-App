import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, fieldError, formError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  AuthSplit,
  Banner,
  Button,
  Field,
  Input,
  Spinner,
  Strength,
} from "../../components/ui";
import { passwordHelp, passwordStrength, useSignup } from "./hooks";

const TAGLINE = "Run your whole software lifecycle with AI — and human approval gates.";
const SUB = "Create a workspace and you become its first admin. Teammates join by invitation.";

// S-01 view states: default · email-in-use · submitting · success.
export type SignupView = "default" | "email-in-use" | "submitting" | "success";

export function Signup({ forceView }: { forceView?: SignupView }) {
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const signup = useSignup();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const [done, setDone] = useState(false);

  const emailInUse =
    forceView === "email-in-use" ||
    (signup.error instanceof ApiError && signup.error.status === 409);
  const view: SignupView =
    forceView ??
    (done ? "success" : signup.isPending ? "submitting" : emailInUse ? "email-in-use" : "default");

  // Bugs S.No 219: this form branched on 409 (email already in use) and dropped everything
  // else. A blank name or a password under eight characters is a 400 with the server naming
  // the exact field — and the form simply sat there, saying nothing, having done nothing.
  const nameError = fieldError(signup.error, "name");
  const emailError = fieldError(signup.error, "email");
  // Mockups 4 + 5 (2026-10-09): an honest meter, and the server's refusal cleared on edit.
  const help = passwordHelp(password);
  const passwordError =
    fieldError(signup.error, "password") ?? (help?.tooShort ? help.text : undefined);
  const orgError = fieldError(signup.error, "org_name");
  const bannerError = emailInUse
    ? undefined
    : formError(signup.error, ["name", "email", "password", "org_name"]);

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
          <p className="auth-card__sub">Setting up {orgName || "your workspace"}…</p>
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
        {bannerError ? (
          <Banner variant="danger">{bannerError}</Banner>
        ) : (
          <p className="auth-card__sub">Start your free Edvensoft workspace.</p>
        )}
        <Field label="Full name" error={nameError}>
          <Input
            type="text"
            placeholder="e.g. Jordan Lee"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={Boolean(nameError)}
          />
        </Field>
        <Field
          label="Work email"
          error={
            view === "email-in-use" ? (
              <>
                An account with this email already exists. <Link to="/login">Log in instead</Link>.
              </>
            ) : emailError
          }
        >
          <Input
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={view === "email-in-use" || Boolean(emailError)}
          />
        </Field>
        <Field
          label="Password"
          error={passwordError}
          help={help && !passwordError ? help.text : undefined}
        >
          <Input
            type="password"
            placeholder="At least 8 characters"
            value={password}
            onChange={(e) => {
              if (signup.error) signup.reset();
              setPassword(e.target.value);
            }}
            aria-invalid={Boolean(passwordError)}
          />
          <Strength value={passwordStrength(password)} />
        </Field>
        <Field label="Workspace / org name" error={orgError}>
          <Input
            type="text"
            placeholder="e.g. Northwind Labs"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            aria-invalid={Boolean(orgError)}
          />
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
