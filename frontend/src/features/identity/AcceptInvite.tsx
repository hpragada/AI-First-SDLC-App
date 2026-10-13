import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError, fieldError, formError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { AuthSplit, Banner, Button, Field, Input, Spinner, Strength } from "../../components/ui";
import { passwordHelp, passwordStrength, useAcceptInvitation, useInvitationPreview } from "./hooks";
import { grantsPhrase, roleLabel as labelOf } from "./roles";

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

// 2026-10-09 (team-approved mockup 4): one page, four honest wordings. Every refusal used to
// say "expired" — so a teammate who clicked the link again AFTER joining was told it had
// expired and read that as joining having failed. The server says which case it is.
type Refusal = "used" | "expired" | "revoked" | "invalid";

function refusalOf(error: unknown): { reason: Refusal; inviter: string | null } | null {
  if (!(error instanceof ApiError) || ![409, 410].includes(error.status)) return null;
  const d = (error.detail ?? {}) as { reason?: string; inviter_name?: string | null };
  const reason: Refusal =
    d.reason === "used" || d.reason === "expired" || d.reason === "revoked"
      ? d.reason
      : error.status === 409 ? "used" : "invalid";
  return { reason, inviter: d.inviter_name ?? null };
}

const REFUSAL_ICON: Record<Refusal, ReactNode> = {
  used: <path d="M8 12.5l2.5 2.5L16 9.5M12 3a9 9 0 100 18 9 9 0 000-18z" />,
  expired: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  revoked: <><circle cx="12" cy="12" r="9" /><path d="M5.6 5.6l12.8 12.8" /></>,
  invalid: <path d="M9 15l6-6M10.5 6.5l1-1a4 4 0 015.7 5.7l-1 1M13.5 17.5l-1 1a4 4 0 01-5.7-5.7l1-1" />,
};

export function AcceptInvite({ forceView }: { forceView?: AcceptInviteView }) {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { refresh, isAuthenticated, currentUser, logout } = useAuth();
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
  const [nameMissing, setNameMissing] = useState(false);

  const noToken = !forceView && !token;
  const refusal: { reason: Refusal; inviter: string | null } | null =
    forceView === "expired"
      ? { reason: "expired", inviter: null }
      : forceView
        ? null
        : noToken
          ? { reason: "invalid", inviter: null }
          : (refusalOf(preview.error) ?? refusalOf(accept.error));
  const expired = refusal !== null;
  // Mockup 5: the invite could not be LOADED (app unreachable, or broken on our side) — never
  // an empty form that fails on submit.
  const unloaded =
    !forceView && !expired && preview.error instanceof ApiError &&
    (preview.error.failure === "offline" || preview.error.failure === "server")
      ? preview.error.failure
      : null;
  const loadingPreview = !forceView && !expired && preview.isLoading;
  const view: AcceptInviteView =
    forceView ?? (accept.isPending ? "submitting" : expired ? "expired" : "default");

  // Bugs S.No 219: this branched on 409/410 (the invitation is gone) and dropped everything
  // else. A password under eight characters is a 400 naming the field, and the form did
  // nothing at all with it — the button came back and the person was left guessing.
  // Mockup 9: a name is required — left blank, the account went by its email everywhere.
  const nameError = nameMissing ? "Enter your name." : fieldError(accept.error, "name");
  // Mockups 4 + 5: the server's refusal in plain words, cleared as soon as the password changes
  // (see onChange); until then the meter says what the server would say.
  const help = passwordHelp(password);
  const passwordError =
    fieldError(accept.error, "password") ?? (help?.tooShort ? help.text : undefined);
  const bannerError = expired ? undefined : formError(accept.error, ["name", "password"]);

  const tagline = forceView
    ? GALLERY.tagline
    : preview.data
      ? `You're invited to ${preview.data.tenant_name}.`
      : // Mockup 1 (the team's words): whenever the workspace name is not known.
        "You're Invited to Edvensoft SDLC App";
  const title = forceView ? GALLERY.title : preview.data ? `Join ${preview.data.tenant_name}` : "Join workspace";
  const inviterName = forceView ? GALLERY.inviter : preview.data?.inviter_name;
  // Every role the invite grants, not just the first (team-approved mockup B, 2026-10-09).
  const joining = forceView
    ? grantsPhrase([{ project_name: GALLERY.project, role_label: labelOf(GALLERY.role) }])
    : grantsPhrase(preview.data?.grants ?? []);
  const email = forceView ? GALLERY.email : (preview.data?.email ?? "");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setNameMissing(true);
      return;
    }
    try {
      await accept.mutateAsync({ token, password, name: name.trim() });
      await refresh();
      // 2026-10-09: a new teammate lands on their own Get started (connect your machine), the
      // way a workspace owner does after signing up — not on a dashboard they can't run yet.
      navigate("/setup", { replace: true });
    } catch {
      /* surfaced via accept.error → expired card */
    }
  };

  if (view === "expired" && refusal) {
    const asker = refusal.inviter ?? "your workspace admin";
    const words: Record<Refusal, { title: string; line: string }> = {
      used: {
        title: "You've already joined",
        line: isAuthenticated
          ? "This invite was used, and you're signed in."
          : "This invite was used. Sign in instead.",
      },
      expired: { title: "This invite has expired", line: `Ask ${asker} to send a new one.` },
      revoked: {
        title: "This invite was cancelled",
        line: `Ask ${asker} if you still need access.`,
      },
      // Mockup 3: also what an OLD link says after Resend — the server cannot tell a replaced
      // link from a damaged one, so this covers both without blaming the reader.
      invalid: {
        title: "This link doesn't work any more",
        line:
          "A newer invite may have replaced it. Open the most recent invite email, or ask " +
          "your workspace admin.",
      },
    };
    const { title: refusedTitle, line } = words[refusal.reason];
    return (
      <AuthSplit tagline={tagline}>
        <div className="auth-card" style={{ textAlign: "center" }}>
          <div className="empty__icon" style={{ margin: "0 auto var(--space-3)" }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
                 aria-hidden="true">
              {REFUSAL_ICON[refusal.reason]}
            </svg>
          </div>
          <h1 className="auth-card__title">{refusedTitle}</h1>
          <p className="auth-card__sub">{line}</p>
          {/* The dead "Request a new invite" button is gone: it was wired to nothing. */}
          {refusal.reason === "used" &&
            (isAuthenticated ? (
              <Button variant="primary" block onClick={() => navigate("/", { replace: true })}>
                Go to my dashboard
              </Button>
            ) : (
              <Button variant="primary" block onClick={() => navigate("/login")}>
                Sign in
              </Button>
            ))}
        </div>
      </AuthSplit>
    );
  }

  if (unloaded) {
    const offline = unloaded === "offline";
    return (
      <AuthSplit tagline={tagline}>
        <div className="auth-card">
          <h1 className="auth-card__title">{title}</h1>
          <Banner
            variant="danger"
            title={offline ? "Can't reach the SDLC app right now" : "Something went wrong on our side"}
          >
            {offline
              ? "Your invite is safe. Check the app is running, then try again."
              : "Your invite is safe. Try again in a moment."}
          </Banner>
          <Button variant="secondary" block onClick={() => void preview.refetch()}>
            Try again
          </Button>
        </div>
      </AuthSplit>
    );
  }

  // Mockup 3: the link opened in a browser where someone is already signed in. This page used
  // to sit behind the signed-in redirect, so the invite vanished into that person's dashboard
  // without a word.
  if (!forceView && isAuthenticated && preview.data) {
    return (
      <AuthSplit tagline={tagline}>
        <div className="auth-card">
          <h1 className="auth-card__title">{title}</h1>
          <p className="auth-card__sub">This invite is for {preview.data.email}.</p>
          <Banner variant="warning">
            You're signed in as {currentUser?.user.email}. Sign out to accept this invite.
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
          {joining && ` ${joining}`}.
        </p>
        {bannerError && <Banner variant="danger">{bannerError}</Banner>}
        <Field label="Your name" error={nameError}>
          <Input
            type="text"
            placeholder="e.g. Jordan Lee"
            value={name}
            onChange={(e) => {
              setNameTouched(true);
              setNameMissing(false);
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
          help={help && !passwordError ? help.text : undefined}
        >
          <Input type="password" placeholder="At least 8 characters" value={password}
                 aria-invalid={Boolean(passwordError)}
                 onChange={(e) => {
                   if (accept.error) accept.reset();
                   setPassword(e.target.value);
                 }} />
          <Strength value={passwordStrength(password)} />
        </Field>
        <Button variant="primary" block type="submit">
          Join workspace
        </Button>
      </form>
    </AuthSplit>
  );
}
