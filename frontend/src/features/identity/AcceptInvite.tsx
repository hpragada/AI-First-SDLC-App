import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, fieldError, formError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { AuthSplit, Banner, Button, Field, Input, Spinner, Strength } from "../../components/ui";
import { passwordStrength, useAcceptInvitation, useInvitationPreview } from "./hooks";

// Gallery fixture copy — forceView renders this fixed content for design review / tests
// (identity.test.tsx S-03), independent of any network call. Live usage (no forceView,
// the real /accept-invite route) fetches the actual invitation via useInvitationPreview
// and never shows these values.
const GALLERY = {
  tagline: "You're invited to Acme Corp.",
  title: "Join Acme Corp",
  inviter: "Sarah Chen",
  role: "engineer",
  project: "Payment Gateway v2",
  email: "raj@acme.com",
};
const SUB = "Set a password and join your team's workspace.";

// S-03 view states: default · expired (used/expired link) · submitting.
export type AcceptInviteView = "default" | "expired" | "submitting";

export function AcceptInvite({ forceView }: { forceView?: AcceptInviteView }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const accept = useAcceptInvitation();
  // Gallery mode never fetches — pass an empty token so the query stays disabled.
  const preview = useInvitationPreview(forceView ? "" : token);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);

  // Prefill the name field from the invitation (the admin may have set one when inviting)
  // once it loads, but never clobber what the user has already started typing.
  useEffect(() => {
    if (!forceView && preview.data?.name && !nameTouched) {
      setName(preview.data.name);
    }
  }, [forceView, preview.data, nameTouched]);
  const [password, setPassword] = useState("");

  const previewFailed =
    !forceView &&
    preview.error instanceof ApiError &&
    [409, 410].includes(preview.error.status);
  const noToken = !forceView && !token;
  const expired =
    forceView === "expired" ||
    previewFailed ||
    noToken ||
    (accept.error instanceof ApiError && [409, 410].includes(accept.error.status));
  const loadingPreview = !forceView && !expired && preview.isLoading;
  const view: AcceptInviteView =
    forceView ?? (accept.isPending ? "submitting" : expired ? "expired" : "default");

  // Bugs S.No 219: this branched on 409/410 (the invitation is gone) and dropped everything
  // else. A password under eight characters is a 400 naming the field, and the form did
  // nothing at all with it — the button came back and the person was left guessing.
  const nameError = fieldError(accept.error, "name");
  const passwordError = fieldError(accept.error, "password");
  const bannerError = expired ? undefined : formError(accept.error, ["name", "password"]);

  const tagline = forceView
    ? GALLERY.tagline
    : preview.data
      ? `You're invited to ${preview.data.tenant_name}.`
      : "You're invited.";
  const title = forceView ? GALLERY.title : preview.data ? `Join ${preview.data.tenant_name}` : "Join workspace";
  const primaryGrant = forceView ? undefined : preview.data?.grants[0];
  const inviterName = forceView ? GALLERY.inviter : preview.data?.inviter_name;
  const roleLabel = forceView ? GALLERY.role : primaryGrant?.role_label;
  const projectName = forceView ? GALLERY.project : primaryGrant?.project_name;
  const email = forceView ? GALLERY.email : (preview.data?.email ?? "");

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
      <AuthSplit tagline={tagline}>
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
      <AuthSplit tagline={tagline}>
        <div className="auth-card">
          <h1 className="auth-card__title">{title}</h1>
          <p className="auth-card__sub">Setting up your account…</p>
          <Button variant="primary" block disabled aria-disabled="true">
            <Spinner /> Joining workspace…
          </Button>
        </div>
      </AuthSplit>
    );
  }

  if (loadingPreview) {
    return (
      <AuthSplit tagline={tagline}>
        <div className="auth-card">
          <h1 className="auth-card__title">{title}</h1>
          <p className="auth-card__sub">Loading your invitation…</p>
          <Spinner />
        </div>
      </AuthSplit>
    );
  }

  return (
    <AuthSplit tagline={tagline} sub={SUB}>
      <form className="auth-card" onSubmit={onSubmit}>
        <h1 className="auth-card__title">{title}</h1>
        <p className="auth-card__sub">
          You've been invited by <strong>{inviterName ?? "a teammate"}</strong>
          {roleLabel && (
            <>
              {" "}
              as <strong>{roleLabel}</strong>
            </>
          )}
          {projectName && (
            <>
              {" "}
              on {projectName}
            </>
          )}
          .
        </p>
        {bannerError && <Banner variant="danger">{bannerError}</Banner>}
        <Field label="Your name" error={nameError}>
          <Input
            type="text"
            placeholder="e.g. Jordan Lee"
            value={name}
            onChange={(e) => {
              setNameTouched(true);
              setName(e.target.value);
            }}
            aria-invalid={Boolean(nameError)}
          />
        </Field>
        <Field label="Email">
          <Input type="email" value={email} disabled />
        </Field>
        <Field
          label="Set a password"
          error={passwordError}
          help={password && !passwordError ? "Strong password." : undefined}
        >
          <Input type="password" placeholder="At least 8 characters" value={password}
                 aria-invalid={Boolean(passwordError)}
                 onChange={(e) => setPassword(e.target.value)} />
          <Strength value={passwordStrength(password)} />
        </Field>
        <Button variant="primary" block type="submit">
          Join workspace
        </Button>
      </form>
    </AuthSplit>
  );
}
